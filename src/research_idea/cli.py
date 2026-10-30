"""Command-line interface. All research outputs are persisted before display."""
from __future__ import annotations

import argparse
from contextlib import nullcontext
import json
import os
from pathlib import Path
import shutil
import sys
import time

from . import __version__
from .config import load_config, write_config, DEFAULTS, REASONING_EFFORTS
from .controller import Controller, BudgetExhausted
from .backend_types import BackendError
from .demo import DemoBackend, DEMO_PAPERS, DEMO_TOPIC
from .literature import discover, read_source, normalize_paper, deduplicate, LiteratureError
from .locking import project_lock
from .report import export_report
from .store import Store, now
from .local_skills import builtin_skill_paths, discover_skills, discovery_roots, load_selected_skills
from .search_scope import AI_VENUES, recent_defaults, config_scope


def emit(value):
    print(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False))


def ensure_project(project: Path, topic: str | None = None, overrides=None):
    project.mkdir(parents=True, exist_ok=True)
    existing = (project / "research.sqlite3").exists()
    if not existing and not topic:
        raise ValueError("New project requires a research topic")
    store = Store(project)
    if existing and topic and store.get("topic") not in {None, topic}:
        store.close()
        raise ValueError("Project already has a different topic; choose a new project directory")
    if topic and not store.get("topic"):
        store.set("topic", topic)
        store.set("status", "initialized")
    if not (project / "research.toml").exists():
        write_config(project, overrides)
    return store


def require_project(project: Path, *, readonly: bool = False):
    if not (project / "research.sqlite3").is_file():
        raise ValueError("Project not initialized. Run 'research-idea init TOPIC --project PATH'.")
    return Store(project, readonly=readonly)


def import_papers(store, records, kind=None):
    normalized = []
    for record in records:
        p = normalize_paper(record)
        if kind:
            p["content_kind"] = kind
        normalized.append(p)
    previous = store.rows("papers")
    merged = deduplicate(previous + normalized)
    # An explicitly re-imported full text is a source revision, even when a
    # cleaner extraction is shorter. Discovery still prefers fuller content.
    for incoming in normalized:
        if incoming["content_kind"] != "full_text" or not incoming.get("text", "").strip():
            continue
        aliases = set(incoming["aliases"])
        current = next(p for p in merged if aliases.intersection(p["aliases"]))
        for key, value in incoming.items():
            if key not in {"id", "aliases", "sources", "versions"} and value not in (None, "", []):
                current[key] = value
        if not incoming.get("full_text_error"):
            current.pop("full_text_error", None)
    if merged == previous:
        return 0
    with store.db:
        store.db.execute("DELETE FROM papers")
        store.db.executemany("INSERT INTO papers VALUES (?,?)", [(p["id"], json.dumps(p, ensure_ascii=False, allow_nan=False)) for p in merged])
        # Evidence is reconstructed via cached extraction tasks on next run.
        store.db.execute("DELETE FROM evidence")
    store.set("cohort", None)
    store.set("source_revision", store.get("source_revision", 0) + 1)
    store.set("status", "sources_changed")
    store.event("sources_imported", {"before": len(previous), "after": len(merged), "imported": len(normalized)})
    return max(0, len(merged) - len(previous))


def collect_paper_files(paths):
    """Expand explicitly selected source directories, without following symlinks."""
    supported = {".pdf", ".txt", ".md", ".json"}
    control_files = {"AGENTS.md", "CLAUDE.md", "SKILL.md"}
    found = {}
    for value in paths:
        path = Path(value).expanduser().resolve()
        if path.is_file():
            if path.suffix.lower() not in supported:
                raise ValueError(f"Unsupported paper format: {path.name}")
            found[path] = False
        elif path.is_dir():
            for directory, dirs, files in os.walk(path, followlinks=False):
                dirs[:] = sorted(d for d in dirs if not d.startswith(".") and d not in {"node_modules", "__pycache__", "venv"})
                for name in sorted(files):
                    file = Path(directory) / name
                    if name.startswith(".") or name in control_files or file.is_symlink() or file.suffix.lower() not in supported:
                        continue
                    found.setdefault(file.resolve(), True)
                    if len(found) > 100:
                        raise ValueError("At most 100 paper files may be imported at once; choose a smaller directory")
        else:
            raise ValueError(f"Paper path does not exist: {path}")
        if len(found) > 100:
            raise ValueError("At most 100 paper files may be imported at once")
    if paths and not found:
        raise ValueError("No PDF/TXT/Markdown/JSON paper files were found in the selected paths")
    return sorted(found.items(), key=lambda item: str(item[0]))


def read_paper_records(files):
    """Shared add/start importer; directory JSON must actually contain papers."""
    records = []
    for file, from_directory in files:
        if file.suffix.lower() == ".json":
            if file.stat().st_size > 32 * 1024 * 1024:
                raise ValueError("JSON import exceeds 32 MiB")
            value = json.loads(file.read_text(encoding="utf-8"))
            if isinstance(value, dict):
                value = value["papers"] if "papers" in value else [value]
            valid = isinstance(value, list) and all(
                isinstance(item, dict) and isinstance(item.get("title") or item.get("display_name"), str)
                and (item.get("title") or item.get("display_name")).strip() for item in value
            )
            if not valid:
                if from_directory:
                    print(f"Skipping non-paper JSON: {file}", file=sys.stderr)
                    continue
                raise ValueError("JSON import must contain paper objects with titles, or {papers: [...]}")
            records.extend(value)
        else:
            records.append(read_source(file))
    if files and not records:
        raise ValueError("No paper records were found; configuration JSON files are not research sources")
    return records


def _absolute_roots(values):
    return list(dict.fromkeys(str(Path(value).expanduser().resolve()) for value in values))


def _binary_setting(value):
    expanded = os.path.expanduser(value)
    if os.path.isabs(expanded) or any(separator in expanded for separator in ("/", "\\")):
        return str(Path(expanded).resolve())
    return expanded


def _skill_selector(value):
    path = Path(value).expanduser()
    if path.exists() or path.suffix.lower() == ".md" or any(separator in value for separator in ("/", "\\")):
        return str(path.resolve())
    return value


def validate_active_skills(cfg, project):
    selectors = (builtin_skill_paths() if cfg["builtin_skills"] else []) + cfg["skill_paths"]
    return load_selected_skills(selectors, project=project, extra_roots=cfg["skill_roots"], max_chars=cfg["skill_max_chars"])


def apply_scope_options(args, cfg):
    before = dict(cfg)
    if getattr(args, "literature_preset", None) == "ai-recent":
        cfg.update(recent_defaults(), search_source="hybrid", search_venues=list(AI_VENUES), search_date_mode='rolling', conference_policy='latest')
    if getattr(args, 'since', None) is not None or getattr(args, 'until', None) is not None:
        cfg['search_date_mode'] = 'fixed'
        cfg['conference_policy'] = 'window'
    if getattr(args, 'search_date_mode', None) == 'fixed':
        cfg['conference_policy'] = 'window'
    for key in ('search_date_mode', 'strategy_months', 'novelty_months', 'conference_policy'):
        if getattr(args, key, None) is not None:
            cfg[key] = getattr(args, key)
    for arg, key in (("since", "search_since"), ("until", "search_until"),
                     ("cs_only", "search_cs_only"), ("arxiv_categories", "arxiv_categories")):
        value = getattr(args, arg, None)
        if value is not None:
            cfg[key] = value
    config_scope(cfg)
    return cfg != before


def execution_config(args, project):
    cfg = load_config(project)
    changed = apply_scope_options(args, cfg)
    if getattr(args, 'output_dir', None) is not None:
        cfg['output_dir'] = str(args.output_dir.expanduser().resolve())
        changed = True
    for key in ("backend", "model", "codex_bin", "codex_profile", "reasoning_effort", "constraints",
                "search_results_per_query", "max_papers", "max_candidates", "max_rounds", "max_calls", "max_seconds", "timeout_s", "auto_search"):
        value = getattr(args, key, None)
        if value is not None:
            cfg[key] = (_binary_setting(value) if key == "codex_bin" else
                        "" if key == "reasoning_effort" and value == "inherit" else value)
            changed = True
    launcher_binary = os.environ.get("RESEARCH_IDEA_CODEX_BIN")
    if (launcher_binary and cfg["backend"] == "codex" and cfg["codex_bin"] == "codex"
            and getattr(args, "codex_bin", None) is None):
        cfg["codex_bin"] = _binary_setting(launcher_binary)
        changed = True
    if getattr(args, "builtin_skills", None) is not None:
        cfg["builtin_skills"] = args.builtin_skills
        changed = True
    source = getattr(args, "search_source", None)
    venues = getattr(args, "venues", None)
    if source is not None:
        cfg["search_source"] = source
        changed = True
    if venues is not None:
        from .literature import normalize_venues
        cfg["search_venues"] = normalize_venues(venues)
        if cfg["search_venues"] and source is None and cfg["search_source"] != "hybrid":
            cfg["search_source"] = "openalex"
        changed = True
    if cfg["search_venues"] and cfg["search_source"] == "arxiv":
        raise ValueError("Venue filtering requires OpenAlex. Use --source openalex; arxiv does not verify conference venues.")
    if getattr(args, "fetch_full_text", None) is not None:
        cfg["fetch_full_text"] = args.fetch_full_text
        changed = True
    roots = getattr(args, "skill_root", None)
    selectors = getattr(args, "skill", None)
    if roots is not None:
        cfg["skill_roots"] = _absolute_roots(roots)
        changed = True
    if selectors is not None or roots is not None:
        chosen = load_selected_skills([_skill_selector(value) for value in selectors] if selectors is not None else cfg["skill_paths"],
                                      project=project, extra_roots=cfg["skill_roots"], max_chars=cfg["skill_max_chars"])
        cfg["skill_paths"] = [item["path"] for item in chosen]
        changed = True
    validate_active_skills(cfg, project)
    return cfg, changed


def skill_metadata(items):
    return [{key: value for key, value in item.items() if key != "content"} for item in items]


def execute_manual_search(store, args, cfg, project):
    from .literature import normalize_venues, fetch_full_text
    cfg = dict(cfg)
    apply_scope_options(args, cfg)
    venues = normalize_venues(args.venues if args.venues is not None else cfg["search_venues"])
    source = args.source or ("openalex" if venues and cfg["search_source"] != "hybrid" else cfg["search_source"])
    if venues and source == "arxiv":
        raise ValueError("Venue filtering requires OpenAlex. Use --source openalex; arxiv does not verify conference venues.")
    scope = config_scope(cfg)
    entry = {"query": args.query, "source": source, "venues": venues, "filters": scope, "time": now(),
             "status": "started", "found": 0, "full_text_fetched": 0, "full_text_errors": 0,
             "full_text_requested": args.full_text}
    ledger = (store.get("manual_search_ledger", []) + [entry])[-100:]
    store.set("manual_search_ledger", ledger)
    store.event("manual_search_started", entry)
    deadline = time.monotonic() + cfg["max_seconds"]
    try:
        papers = discover(args.query, source=source, limit=args.limit,
                          timeout_s=min(60, cfg["max_seconds"]),
                          api_key_env=cfg.get("search_api_key_env") or None, venues=venues, **scope)
    except (LiteratureError, OSError, ValueError) as exc:
        entry.update(status="failed", error_type=type(exc).__name__)
        store.set("manual_search_ledger", ledger)
        store.set("manual_search_errors", store.get("manual_search_errors", 0) + 1)
        store.event("manual_search_failed", entry)
        raise
    entry["found"] = len(papers)
    entry["coverage"] = getattr(papers, "coverage", {})
    for index, paper in enumerate(papers):
        if not args.full_text or paper.get("content_kind") == "full_text":
            continue
        try:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise LiteratureError("Manual search time budget exhausted before full-text retrieval")
            retrieved = fetch_full_text(paper, project / "sources", timeout_s=min(30, remaining))
            if retrieved.get("content_kind") != "full_text" or not retrieved.get("text", "").strip():
                papers[index] = dict(paper, full_text_error=retrieved.get("full_text_error") or "Full text was not retrieved; abstract retained",
                                     full_text_retrieval=retrieved.get("full_text_retrieval") or {"status": "failed"})
                entry["full_text_errors"] += 1
                store.event("manual_full_text_failed", {"paper_id": paper.get("id"),
                            "error": papers[index]["full_text_error"],
                            "retrieval": papers[index].get("full_text_retrieval", {})})
                continue
            papers[index] = retrieved
            entry["full_text_fetched"] += 1
        except (LiteratureError, OSError, ValueError) as exc:
            safe_error = str(exc) if isinstance(exc, LiteratureError) else type(exc).__name__
            paper = dict(paper, full_text_error=safe_error,
                         full_text_retrieval={"status": "failed", "error_type": type(exc).__name__, "error": safe_error})
            papers[index] = paper
            entry["full_text_errors"] += 1
            store.event("manual_full_text_failed", {"paper_id": paper.get("id"), "error_type": type(exc).__name__, "error": safe_error})
    added = import_papers(store, papers)
    entry.update(status="completed", new_papers=added)
    store.set("manual_search_ledger", ledger)
    store.set("manual_full_text_errors", store.get("manual_full_text_errors", 0) + entry["full_text_errors"])
    store.event("manual_search", entry)
    full_text = sum(p.get("content_kind") == "full_text" and bool(p.get("text", "").strip()) for p in papers)
    emit({"found": len(papers), "new_papers": added, "source": source, "venues": venues,
          "source_coverage": {"full_text": full_text, "abstract_only": len(papers) - full_text},
          "full_text_fetched": entry["full_text_fetched"], "full_text_errors": entry["full_text_errors"],
          "error_count": entry["full_text_errors"], "search_coverage": entry["coverage"]})


def execute_skills(args):
    project = args.project.expanduser().resolve() if args.project else None
    cfg = load_config(project) if project else dict(DEFAULTS)
    roots = _absolute_roots(args.root) if getattr(args, "root", None) is not None else cfg["skill_roots"]
    if args.skill_command == "list":
        emit({"skills": discover_skills(project=project, extra_roots=roots),
              "discovery_roots": discovery_roots(project=project, extra_roots=roots),
              "selected_skill_paths": cfg["skill_paths"], "builtin_skills": cfg["builtin_skills"]})
        return 0
    if args.skill_command == "show":
        emit(load_selected_skills([_skill_selector(args.selector)], project=project or Path.cwd(), extra_roots=roots,
                                  max_chars=cfg["skill_max_chars"])[0])
        return 0
    with project_lock(project):
        store = require_project(project)
        try:
            cfg = load_config(project)
            if args.skill_command == "use":
                roots = _absolute_roots(args.root) if args.root is not None else cfg["skill_roots"]
                selected = load_selected_skills([_skill_selector(value) for value in args.selectors], project=project, extra_roots=roots,
                                                max_chars=cfg["skill_max_chars"])
                cfg["skill_paths"] = [item["path"] for item in selected]
                cfg["skill_roots"] = roots
                validate_active_skills(cfg, project)
            else:
                selected = []
                cfg["skill_paths"] = []
            write_config(project, cfg)
            emit({"selected_skills": skill_metadata(selected), "skill_roots": cfg["skill_roots"],
                  "builtin_skills": cfg["builtin_skills"],
                  "note": "External skill selection cleared; built-in research skills remain enabled."
                  if args.skill_command == "clear" and cfg["builtin_skills"] else None,
                  "config": str(project / "research.toml")})
            return 0
        finally:
            store.close()


def build_parser():
    parser = argparse.ArgumentParser(prog="research-idea",
        description="从文献梳理背景、现有方法、重要问题与动机，形成研究主张。",
        epilog="直接输入 research-idea 打开对话窗口。单项帮助：research-idea start --help；窗口内：/help 或 /help date。")
    parser.add_argument("--version", action="version", version=__version__, help="显示当前安装版本并退出")
    sub = parser.add_subparsers(dest="command", required=True)
    def command(name, description, example):
        return sub.add_parser(name, help=description, description=description,
            epilog='示例：\n  ' + example, formatter_class=argparse.RawDescriptionHelpFormatter)
    def project_arg(p):
        p.add_argument("--project", type=Path, required=True, help="项目目录；保存配置、材料、对话和进度，例如 ./research-projects/my-idea")
    def scope_args(p):
        p.add_argument('--date-mode', dest='search_date_mode', choices=['rolling', 'fixed'], default=None,
                       help='rolling 按运行当天计算月份窗口；fixed 使用指定起止日期')
        p.add_argument('--conference-policy', choices=['latest', 'window'], default=None,
                       help='会议时间：latest 取最新公开一届（默认）；window 按日期窗口')
        p.add_argument('--strategy-months', type=int, default=None, help='背景与已有方法的动态窗口，单位月，默认 12')
        p.add_argument('--novelty-months', type=int, default=None, help='动机与贡献对照的动态窗口，单位月，默认 6')
        p.add_argument("--literature-preset", choices=["ai-recent"], default=None,
                       help="采用近期 AI 会议与 CS arXiv 的预设范围")
        p.add_argument("--since", default=None, help="最早发表日期，格式 YYYY-MM-DD")
        p.add_argument("--until", default=None, help="最晚发表日期，格式 YYYY-MM-DD")
        p.add_argument("--cs-only", action=argparse.BooleanOptionalAction, default=None,
                       help="限定计算机领域或已核实的 AI 会议；--no-cs-only 取消该限制")
        p.add_argument("--arxiv-categories", nargs="*", action="extend", default=None,
                       help="允许的 arXiv 分类，例如 cs.CL cs.AI；命令行中 cs.* 建议加引号")
    def backend_args(p):
        scope_args(p)
        p.add_argument("--backend", choices=["codex", "claude", "api"], default=None,
                       help="模型后端：本地 Codex CLI、Claude Code CLI 或 API；省略时沿用项目设置")
        p.add_argument("--model", default=None, help="后端与账户支持的模型 ID，例如 gpt-6.1-sol；省略时沿用项目设置")
        p.add_argument('--output', dest='output_dir', type=Path,
                       help='结果父目录；程序自动创建 idea-时间戳 文件夹')
        p.add_argument("--reasoning-effort", choices=["inherit", *REASONING_EFFORTS], default=None,
                       help="Codex 思考强度；inherit 沿用后端配置，可用档位依模型而定")
        p.add_argument("--constraints", default=None, help="设备、时间、数据等研究资源条件；包含空格时加引号")
        for name, help_text in (("search-results-per-query", "每个查询召回的论文记录数，不是精读篇数"), ("max-papers", "初次选读规模；后续定向补读共用总预算"), ("max-candidates", "优先问题数量；系统先比较不同问题再决定重点"),
                                ("max-rounds", "Revision-round limit"), ("max-calls", "累计模型调用次数上限，包括讨论、分析、修复和重试"),
                                ("max-seconds", "累计运行时间上限，单位秒；6600 为 110 分钟"),
                                ("timeout-s", "单次模型调用超时，单位秒；1200 为 20 分钟")):
            p.add_argument("--" + name, type=int, default=None, help=argparse.SUPPRESS if name == "max-rounds" else help_text)
        p.add_argument("--codex-bin", default=None, help="Codex 可执行文件名称或完整路径")
        p.add_argument("--codex-profile", default=None, help="已有的 Codex 配置档名称，例如 research")
        p.add_argument("--skill", action="append", default=None, help="选用本地 skill 名称或路径；可重复传入")
        p.add_argument("--skill-root", action="append", type=Path, default=None, help="额外的 skill 查找目录；可重复传入")
        p.add_argument("--no-builtin-skills", dest="builtin_skills", action="store_false", default=None,
                       help="在本项目停用内置研究 skill；默认启用")
        p.add_argument("--source", "--search-source", dest="search_source", choices=["arxiv", "openalex", "hybrid"], default=None,
                       help="检索来源：arxiv、openalex 或 hybrid；会议筛选会使用会议检索来源")
        p.add_argument("--venues", nargs="*", action="extend", default=None,
                       help="会议筛选，例如 ACL EMNLP NAACL COLM；名单见 venues")
        p.add_argument("--fetch-full-text", action=argparse.BooleanOptionalAction, default=None,
                       help="保存自动获取正文的设置；默认启用，--no-fetch-full-text 关闭")
    p = command("init", "创建或配置研究项目，只保存主题和设置，不调用模型。",
                'research-idea init "研究方向" --project ./research-projects/my-idea')
    p.add_argument("topic", nargs="?", help="研究方向；也可用 --topic-file 导入，二选一")
    p.add_argument("--topic-file", type=Path, help="UTF-8 研究说明文件，最多 128 KiB；与直接输入主题二选一")
    project_arg(p)
    backend_args(p)
    p = command("start", "设置主题和材料后直接开始研究；需要边研究边讨论时使用 chat。",
                'research-idea start "研究方向" --project ./research-projects/my-idea --backend codex --model gpt-6.1-sol')
    p.add_argument("topic", nargs="?", help="研究方向；也可用 --topic-file 导入，二选一")
    p.add_argument("--topic-file", type=Path, help="UTF-8 研究说明文件，最多 128 KiB；与直接输入主题二选一")
    project_arg(p)
    backend_args(p)
    p.add_argument("--papers", nargs="+", type=Path, action="extend", default=None, help="论文文件或目录，最多 100 个文件；多个路径用空格分隔")
    p.add_argument("--no-search", action="store_true", help="本次只使用项目内已有或导入的材料，不自动联网检索")
    p.add_argument("--setup-only", action="store_true", help="只保存配置并导入材料，不调用模型")
    p = command("launch", "启动设置向导，逐项选择主题、模型、论文和预算，再开始研究。",
                'research-idea launch\n  research-idea launch --setup-only')
    p.add_argument("topic", nargs="?", help="可选研究方向；省略时由向导询问")
    p.add_argument("--topic-file", type=Path, help="UTF-8 研究说明文件，最多 128 KiB；与直接输入主题二选一")
    p.add_argument("--project", type=Path, help="项目目录；省略时由向导询问")
    backend_args(p)
    p.add_argument("--papers", nargs="+", type=Path, action="extend", default=None, help="导入论文文件或目录；多个路径用空格分隔")
    p.add_argument("--no-search", action="store_true", help="只使用已有或导入材料，不自动联网检索")
    p.add_argument("--setup-only", action="store_true", help="向导完成后只保存配置与材料，不调用模型")
    p = command("chat", "打开对话窗口，用 /run 开始研究，/continue 推进讨论，/help 查看命令。",
                'research-idea\n  research-idea chat --project ./research-projects/my-idea')
    p.add_argument("--project", type=Path, help="已有或新项目；省略时创建独立项目目录")
    backend_args(p)
    p = command("run", "运行项目：检索、阅读并整理问题与动机，复用已完成的步骤。",
                'research-idea run --project ./research-projects/my-idea\n  research-idea run --project ./research-projects/my-idea --replan')
    p.add_argument("topic", nargs="?", help="可选研究方向；省略时使用项目已保存的主题")
    p.add_argument("--topic-file", type=Path, help="UTF-8 研究说明文件，最多 128 KiB；与直接输入主题二选一")
    project_arg(p)
    backend_args(p)
    p.add_argument("--no-search", action="store_true", help="本次只使用已有或导入材料，不自动联网检索")
    p.add_argument("--replan", action="store_true", help="用当前材料重新探索研究方向；保留完整对话")
    p = command("resume", "恢复已有项目并复用检查点；交互暂停中的项目需回到 chat 输入 /continue。",
                'research-idea resume --project ./research-projects/my-idea')
    project_arg(p)
    backend_args(p)
    p.add_argument("--no-search", action="store_true", help="本次恢复只使用已有材料，不自动联网检索")
    p.add_argument("--replan", action="store_true", help="用当前材料重新探索研究方向；保留完整对话")
    p = command("add", "导入 PDF、TXT、Markdown 或论文 JSON；只导入，不调用模型分析。",
                'research-idea add --project ./research-projects/my-idea paper.pdf notes.md')
    project_arg(p)
    p.add_argument("files", type=Path, nargs="+", help="一个或多个论文文件；路径含空格时加引号")
    p.add_argument("--kind", choices=["full_text", "abstract", "notes"], help="材料类型：full_text 正文、abstract 摘要、notes 笔记；仅实际论文正文使用 full_text")
    p = command("search", "手动检索并将论文记录加入项目；可选择下载正文，不调用模型精读。",
                'research-idea search "multi-agent collaboration" --project ./research-projects/my-idea --limit 10 --full-text')
    project_arg(p)
    scope_args(p)
    p.add_argument("query", help="检索词；包含空格时加引号，例如 \"multi-agent collaboration\"")
    p.add_argument("--source", choices=["arxiv", "openalex", "hybrid"], default=None,
                   help="检索来源；省略时沿用项目设置，会议筛选会使用会议检索来源")
    p.add_argument("--limit", type=int, default=10, help="本次最多返回的论文记录数，默认 10；不是精读数量")
    p.add_argument("--venues", nargs="*", action="extend", default=None,
                   help="会议名称，例如 ACL COLM；会启用会议检索来源")
    p.add_argument("--full-text", action="store_true", help="同时尝试获取正文；获取失败时保留摘要")
    command("venues", "列出支持的会议、分类、预设和来源；不修改项目设置。", 'research-idea venues')
    p = command("status", "查看项目阶段、累计预算和已保存的任务进度。",
                'research-idea status --project ./research-projects/my-idea')
    project_arg(p)
    p = command("inspect", "查看论文或证据记录、论文分析卡及运行事件；不调用模型。",
                'research-idea inspect --project ./research-projects/my-idea\n  research-idea inspect --project ./research-projects/my-idea --events')
    project_arg(p)
    p.add_argument("id", nargs="?", help="论文、证据或旧版候选 ID；省略时列出论文和候选，普通引用可在窗口用 /evidence 查看")
    p.add_argument("--events", action="store_true", help="查看最近的运行事件；不能与 --paper-card 一起使用")
    p.add_argument("--paper-card", action="store_true", help="显示给定论文 ID 的分析卡；必须传 ID，不能与 --events 同用")
    p = command("export", "从已保存结果导出 Markdown、JSON 和论文分析卡，不重新研究。",
                'research-idea export --project ./research-projects/my-idea --output ./results')
    project_arg(p)
    p.add_argument("--output", type=Path, help='结果父目录；沿用该项目已有的 idea-时间戳 文件夹名')
    p = command("doctor", "检查本机模型 CLI、PDF 工具和可选项目配置，不发送模型请求。",
                'research-idea doctor\n  research-idea doctor --project ./research-projects/my-idea')
    p.add_argument("--project", type=Path, help="可选项目目录；同时检查该项目的配置")
    p = command("skills", "列出、查看或选择本地分析 skill；选中的指导文本用于后续研究。",
                'research-idea skills list\n  research-idea skills use --project ./research-projects/my-idea /path/to/SKILL.md')
    skill_sub = p.add_subparsers(dest="skill_command", required=True)
    skill_examples = {'list': 'research-idea skills list', 'show': 'research-idea skills show /path/to/SKILL.md',
                      'use': 'research-idea skills use --project ./research-projects/my-idea /path/to/SKILL.md',
                      'clear': 'research-idea skills clear --project ./research-projects/my-idea'}
    for name, help_text in (("list", "列出已发现的本地 skill；可指定额外搜索目录。"), ("show", "查看一个 skill 的指导文本。"),
                            ("use", "替换项目选中的本地 skill；可一次指定多个，不执行其中的脚本。"),
                            ("clear", "清除项目额外选中的本地 skill；保留内置 skill 的启用设置。")):
        sp = skill_sub.add_parser(name, help=help_text, description=help_text,
            epilog='示例：\n  ' + skill_examples[name], formatter_class=argparse.RawDescriptionHelpFormatter)
        sp.add_argument("--project", type=Path, required=name in {"use", "clear"},
                        help="项目目录；use/clear 必填，list/show 可省略")
        if name != "clear":
            sp.add_argument("--root", action="append", type=Path, default=None, help="额外的 skill 查找目录；可重复传入")
        if name == "show":
            sp.add_argument("selector", help="skill 名称或 SKILL.md 路径；可先运行 skills list 查看")
        if name == "use":
            sp.add_argument("selectors", nargs="+", help="一个或多个 skill 名称或 SKILL.md 路径")
    p = command("demo", "运行合成材料的离线演示，不联网、不调用真实模型。",
                'research-idea demo --project ./research-projects/demo')
    project_arg(p)
    p.add_argument('--output', type=Path, help='结果父目录；用于保存离线演示报告')
    return parser


def execute(args):
    if args.command == "chat":
        from .chat import launch_chat
        return launch_chat(args)
    if getattr(args, "topic_file", None):
        if args.topic:
            raise ValueError("Use either TOPIC or --topic-file, not both")
        from .interactive import read_topic_file
        args.topic = read_topic_file(args.topic_file)
    if args.command == "launch":
        from .interactive import configure_launch
        configure_launch(args)
    command = args.command
    if command == "venues":
        from .literature import supported_venues
        emit({"venues": supported_venues(),
              "note": "Curated supported conference filters; not a complete or current CCF ranking catalog. Publication metadata coverage may be incomplete."})
        return 0
    if command == "skills":
        return execute_skills(args)
    if command == "doctor":
        project = args.project.expanduser().resolve() if args.project else None
        cfg = load_config(project) if project else dict(DEFAULTS)
        key_name = cfg.get("api_key_env")
        codex_path = shutil.which(os.path.expanduser(cfg["codex_bin"]))
        warnings = []
        if cfg["backend"] == "codex" and not codex_path:
            warnings.append("Codex executable not found. Set codex_bin in research.toml or use --codex-bin /path/to/codex with start/run.")
        if cfg["backend"] == "claude" and not shutil.which("claude"):
            warnings.append("Claude Code executable not found. Install it and ensure claude is on PATH before running.")
        selected = []
        try:
            selectors = (builtin_skill_paths() if cfg["builtin_skills"] else []) + cfg["skill_paths"]
            selected = load_selected_skills(selectors, project=project or Path.cwd(),
                                            extra_roots=cfg["skill_roots"], max_chars=cfg["skill_max_chars"])
        except (ValueError, RuntimeError, OSError) as exc:
            warnings.append(f"Selected skill cannot be loaded: {exc}")
        emit({"python": sys.version.split()[0], "backend": cfg["backend"], "model": cfg["model"],
              "executables": {x: shutil.which(x) is not None for x in ("codex", "claude", "pdftotext")},
              "codex_bin": cfg["codex_bin"], "codex_resolved_path": str(Path(codex_path).resolve()) if codex_path else None,
              "codex_profile": cfg["codex_profile"], "reasoning_effort": cfg["reasoning_effort"],
              "selected_skills": skill_metadata(selected),
              "builtin_skills": cfg["builtin_skills"],
              "discovery_roots": discovery_roots(project=project, extra_roots=cfg["skill_roots"]), "warnings": warnings,
              "api_key_env": key_name, "api_key_present": bool(os.environ.get(key_name, "")) if key_name else None,
              "note": "Local inspection only; no authentication, network, or model connection was tested."})
        return 1 if warnings else 0
    project = args.project.expanduser().resolve()
    if command == "start" and not args.topic:
        if not sys.stdin.isatty():
            raise ValueError("Non-interactive start requires TOPIC: research-idea start '研究主题' --project PATH; use resume for an existing project")
        print("研究主题：", end="", file=sys.stderr, flush=True)
        try:
            args.topic = input().strip()
        except EOFError:
            raise ValueError("No topic supplied. Use research-idea start '研究主题' --project PATH") from None
        if not args.topic:
            raise ValueError("Research topic cannot be empty")
    readonly = command in {"status", "inspect"}
    with nullcontext() if readonly else project_lock(project):
        store = None
        try:
            cfg = None
            config_changed = False
            if command in {"init", "run", "resume", "start"}:
                cfg, config_changed = execution_config(args, project)
            start_records = read_paper_records(collect_paper_files(args.papers)) if command == "start" and args.papers else []
            if command == "demo":
                if (project / "research.sqlite3").exists():
                    store = require_project(project)
                    if not store.get("demo", False):
                        raise ValueError("Refusing to replace a real research project with demo data")
                else:
                    store = ensure_project(project, DEMO_TOPIC, {"backend": "demo", "auto_search": False})
                    store.set("demo", True)
                    import_papers(store, DEMO_PAPERS)
            elif command in {"init", "run", "start"}:
                store = ensure_project(project, getattr(args, "topic", None), cfg)
            else:
                store = require_project(project, readonly=readonly)
            if command in {'demo', 'export'} and args.output is not None:
                cfg = load_config(project)
                cfg['output_dir'] = str(args.output.expanduser().resolve())
                config_changed = True
            if config_changed:
                write_config(project, cfg)
            if command == "start" and start_records:
                import_papers(store, start_records)
            if command == "init":
                emit({"project": str(project), "topic": store.get("topic"), "config": str(project / "research.toml")})
            elif command == "start" and args.setup_only:
                emit({"project": str(project), "topic": store.get("topic"), "setup_only": True,
                      "model_invoked": False, "papers": len(store.rows("papers")),
                      "skill_paths": cfg["skill_paths"], "builtin_skills": cfg["builtin_skills"],
                      "search_source": cfg["search_source"], "search_venues": cfg["search_venues"],
                      "fetch_full_text": cfg["fetch_full_text"],
                      "config": str(project / "research.toml"),
                      "next": f"research-idea run --project {str(project)!r}" + (" --no-search" if args.no_search else "")})
            elif command in {"run", "resume", "demo", "start"}:
                cfg = cfg or load_config(project)
                if getattr(args, "no_search", False):
                    cfg["auto_search"] = False
                if getattr(args, "replan", False):
                    store.set("cohort", None)
                    store.set("source_revision", store.get("source_revision", 0) + 1)
                if store.get("demo") and cfg["backend"] != "demo":
                    raise ValueError("Demo sources cannot be promoted into a real project; initialize a new project")
                if cfg["backend"] == "demo":
                    backend = DemoBackend()
                    store.set("demo", True)
                else:
                    from .backends import make_backend
                    backend = make_backend(cfg, project)
                controller = Controller(store, backend, cfg, progress=lambda msg: print(msg, file=sys.stderr))
                try:
                    controller.run_questions()
                finally:
                    report, machine = export_report(store)
                    print(f"Report: {report}", file=sys.stderr)
                emit({"project": str(project), "status": store.get("status"), "demo": store.get("demo", False), "report": str(report), "json": str(machine)})
            elif command == "add":
                records = read_paper_records(collect_paper_files(args.files))
                added = import_papers(store, records, args.kind)
                emit({"imported_records": len(records), "new_papers": added, "total_papers": len(store.rows("papers"))})
            elif command == "search":
                cfg = load_config(project)
                execute_manual_search(store, args, cfg, project)
            elif command == "status":
                cfg = load_config(project)
                from .output_paths import output_parent, saved_report
                emit({"topic": store.get("topic"), "status": store.get("status"), "demo": store.get("demo", False),
                    "output_dir": str(output_parent(project, cfg)), "output_folder": store.get('output_folder'),
                    "report": str(saved_report(store)),
                    "papers": len(store.rows("papers")), "evidence": len(store.rows("evidence")), "candidates": len(store.rows("candidates")),
                    "calls_used": store.get("calls_used", 0), "max_calls": cfg["max_calls"], "elapsed_s": round(store.get("elapsed_s", 0), 2),
                    "known_http_attempts": store.get("known_http_attempts", 0), "cli_internal_http_attempts": "unknown",
                    "manual_search_errors": store.get("manual_search_errors", 0),
                    "manual_full_text_errors": store.get("manual_full_text_errors", 0),
                    "tasks": store.task_summary()})
            elif command == "inspect":
                if args.paper_card:
                    if not args.id or args.events:
                        raise ValueError("--paper-card requires a paper ID and cannot be combined with --events")
                    from .paper_reading import current_cards
                    cards = current_cards(store.rows("papers"), store.rows("evidence"), store.get("paper_cards", {}), store.get("paper_readings", {}))
                    if args.id not in cards:
                        raise ValueError("Unknown paper ID")
                    emit(cards[args.id])
                elif args.events:
                    emit(store.recent_events())
                elif args.id:
                    found = next((r for table in ("papers", "evidence", "candidates") for r in store.rows(table) if r["id"] == args.id), None)
                    if found is None:
                        raise ValueError("Unknown record ID")
                    emit(found)
                else:
                    emit({"candidates": [{"id": c["id"], "title": c["proposal"]["title"], "research_status": c["research_status"]} for c in store.rows("candidates")], "papers": [{"id": p["id"], "title": p["title"]} for p in store.rows("papers")]})
            elif command == "export":
                md, js = export_report(store, args.output)
                emit({"markdown": str(md), "json": str(js)})
            return 0
        finally:
            if store:
                store.close()


def main(argv=None):
    if argv is None:
        argv = sys.argv[1:]
    if not argv and sys.stdin.isatty():
        argv = ["chat"]
    args = build_parser().parse_args(argv)
    try:
        return execute(args)
    except BudgetExhausted as exc:
        print(f"Budget stopped: {exc}", file=sys.stderr)
        return 3
    except (BackendError, LiteratureError, ValueError, RuntimeError, OSError) as exc:
        from .presentation import error_summary
        print(f"[error] {error_summary(exc)}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("Interrupted. Resume with the same project directory.", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
