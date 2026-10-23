"""Command-line interface. All research outputs are persisted before display."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import sys

from . import __version__
from .config import load_config, write_config, DEFAULTS
from .controller import Controller, BudgetExhausted
from .backend_types import BackendError
from .demo import DemoBackend, DEMO_PAPERS, DEMO_TOPIC
from .literature import discover, read_source, normalize_paper, deduplicate, LiteratureError
from .locking import project_lock
from .report import export_report
from .store import Store, digest


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


def require_project(project: Path):
    if not (project / "research.sqlite3").is_file():
        raise ValueError("Project not initialized. Run 'research init TOPIC --project PATH'.")
    return Store(project)


def import_papers(store, records, kind=None):
    normalized = []
    for record in records:
        p = normalize_paper(record)
        if kind:
            p["content_kind"] = kind
        normalized.append(p)
    previous = store.rows("papers")
    merged = deduplicate(previous + normalized)
    if merged == previous:
        return 0
    with store.db:
        store.db.execute("DELETE FROM papers")
        store.db.executemany("INSERT INTO papers VALUES (?,?)", [(p["id"], json.dumps(p, ensure_ascii=False, allow_nan=False)) for p in merged])
        # Evidence is reconstructed via cached extraction tasks on next run.
        store.db.execute("DELETE FROM evidence")
    store.set("cohort", None)
    store.set("status", "sources_changed")
    store.event("sources_imported", {"before": len(previous), "after": len(merged), "imported": len(normalized)})
    return max(0, len(merged) - len(previous))


def build_parser():
    parser = argparse.ArgumentParser(prog="research", description="Evidence-driven LLM/NLP research ideation. No automatic claim of novelty or effectiveness.")
    parser.add_argument("--version", action="version", version=__version__)
    sub = parser.add_subparsers(dest="command", required=True)
    def project_arg(p):
        p.add_argument("--project", type=Path, required=True, help="Project directory")
    def backend_args(p):
        p.add_argument("--backend", choices=["codex", "claude", "api"], default=None)
        p.add_argument("--model", default=None)
    p = sub.add_parser("init", help="Initialize an isolated research project")
    p.add_argument("topic")
    project_arg(p)
    backend_args(p)
    p = sub.add_parser("run", help="Discover/import evidence and develop research candidates")
    p.add_argument("topic", nargs="?")
    project_arg(p)
    backend_args(p)
    p.add_argument("--no-search", action="store_true", help="Use only imported source material")
    p.add_argument("--replan", action="store_true", help="Archive current cohort and regenerate against current sources")
    p = sub.add_parser("resume", help="Resume the same project using validated task checkpoints")
    project_arg(p)
    backend_args(p)
    p.add_argument("--no-search", action="store_true")
    p.add_argument("--replan", action="store_true")
    p = sub.add_parser("add", help="Import PDF/TXT/Markdown or JSON paper records")
    project_arg(p)
    p.add_argument("files", type=Path, nargs="+")
    p.add_argument("--kind", choices=["full_text", "abstract", "notes"], help="Explicit source type; use full_text only for actual paper text")
    p = sub.add_parser("search", help="Search arXiv/OpenAlex and persist source records")
    project_arg(p)
    p.add_argument("query")
    p.add_argument("--source", choices=["arxiv", "openalex"], default="arxiv")
    p.add_argument("--limit", type=int, default=10)
    p = sub.add_parser("status", help="Show project state and budget use")
    project_arg(p)
    p = sub.add_parser("inspect", help="Inspect a candidate, source, or evidence record")
    project_arg(p)
    p.add_argument("id", nargs="?")
    p.add_argument("--events", action="store_true")
    p = sub.add_parser("export", help="Export Markdown and JSON reports")
    project_arg(p)
    p.add_argument("--output", type=Path)
    p = sub.add_parser("doctor", help="Check local executables and configuration without sending requests")
    p.add_argument("--project", type=Path)
    p = sub.add_parser("demo", help="Run an explicitly synthetic offline demonstration")
    project_arg(p)
    p = sub.add_parser("experiment", help="Explicitly run a local experiment spec (not a sandbox)")
    project_arg(p)
    p.add_argument("spec", type=Path)
    p.add_argument("--idea", help="Candidate ID to associate with the execution")
    p.add_argument("--check-only", action="store_true", help="Validate spec without executing")
    return parser


def execute(args):
    command = args.command
    if command == "doctor":
        cfg = load_config(args.project.resolve()) if args.project else dict(DEFAULTS)
        key_name = cfg.get("api_key_env")
        emit({"python": sys.version.split()[0], "backend": cfg["backend"], "model": cfg["model"],
              "executables": {x: shutil.which(x) is not None for x in ("codex", "claude", "pdftotext")},
              "api_key_env": key_name, "api_key_present": bool(os.environ.get(key_name, "")) if key_name else None,
              "note": "Local inspection only; no authentication, network, or model connection was tested."})
        return 0
    project = args.project.expanduser().resolve()
    with project_lock(project):
        store = None
        try:
            if command == "demo":
                if (project / "research.sqlite3").exists():
                    store = require_project(project)
                    if not store.get("demo", False):
                        raise ValueError("Refusing to replace a real research project with demo data")
                else:
                    store = ensure_project(project, DEMO_TOPIC, {"backend": "demo", "auto_search": False})
                    store.set("demo", True)
                    import_papers(store, DEMO_PAPERS)
            elif command in {"init", "run"}:
                overrides = {k: getattr(args, k) for k in ("backend", "model") if getattr(args, k, None) is not None}
                store = ensure_project(project, getattr(args, "topic", None), overrides)
            else:
                store = require_project(project)
            if command == "init":
                emit({"project": str(project), "topic": store.get("topic"), "config": str(project / "research.toml")})
            elif command in {"run", "resume", "demo"}:
                cfg = load_config(project)
                overrides = {k: getattr(args, k) for k in ("backend", "model") if getattr(args, k, None) is not None}
                if overrides:
                    cfg.update(overrides)
                    write_config(project, cfg)
                if getattr(args, "no_search", False):
                    cfg["auto_search"] = False
                if getattr(args, "replan", False):
                    store.set("cohort", None)
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
                    controller.run()
                finally:
                    report, machine = export_report(store)
                    print(f"Report: {report}", file=sys.stderr)
                emit({"project": str(project), "status": store.get("status"), "demo": store.get("demo", False), "report": str(report), "json": str(machine)})
            elif command == "add":
                records = []
                for file in args.files:
                    file = file.expanduser().resolve()
                    if file.suffix.lower() == ".json":
                        if file.stat().st_size > 32 * 1024 * 1024:
                            raise ValueError("JSON import exceeds 32 MiB")
                        value = json.loads(file.read_text(encoding="utf-8"))
                        if isinstance(value, dict):
                            value = value["papers"] if "papers" in value else [value]
                        if not isinstance(value, list) or any(not isinstance(x, dict) for x in value):
                            raise ValueError("JSON import must contain a paper object, list, or {papers: [...]} object")
                        records.extend(value)
                    else:
                        records.append(read_source(file))
                added = import_papers(store, records, args.kind)
                emit({"imported_records": len(records), "new_papers": added, "total_papers": len(store.rows("papers"))})
            elif command == "search":
                cfg = load_config(project)
                papers = discover(args.query, source=args.source, limit=args.limit, api_key_env=cfg.get("search_api_key_env") or None)
                added = import_papers(store, papers)
                store.event("manual_search", {"query": args.query, "source": args.source, "found": len(papers)})
                emit({"found": len(papers), "new_papers": added, "source_coverage": "abstract_only"})
            elif command == "status":
                cfg = load_config(project)
                emit({"topic": store.get("topic"), "status": store.get("status"), "demo": store.get("demo", False),
                    "papers": len(store.rows("papers")), "evidence": len(store.rows("evidence")), "candidates": len(store.rows("candidates")),
                    "calls_used": store.get("calls_used", 0), "max_calls": cfg["max_calls"], "elapsed_s": round(store.get("elapsed_s", 0), 2),
                    "known_http_attempts": store.get("known_http_attempts", 0), "cli_internal_http_attempts": "unknown",
                    "tasks": store.task_summary(), "experiments": len(store.rows("experiments"))})
            elif command == "inspect":
                if args.events:
                    emit(store.recent_events())
                elif args.id:
                    found = next((r for table in ("papers", "evidence", "candidates", "experiments") for r in store.rows(table) if r["id"] == args.id), None)
                    if found is None:
                        raise ValueError("Unknown record ID")
                    emit(found)
                else:
                    emit({"candidates": [{"id": c["id"], "title": c["proposal"]["title"], "research_status": c["research_status"]} for c in store.rows("candidates")], "papers": [{"id": p["id"], "title": p["title"]} for p in store.rows("papers")]})
            elif command == "export":
                md, js = export_report(store, args.output)
                emit({"markdown": str(md), "json": str(js)})
            elif command == "experiment":
                from .experiments import load_spec, run_experiment
                candidate_ids = {c["id"] for c in store.rows("candidates")}
                if args.idea and args.idea not in candidate_ids:
                    raise ValueError("Unknown candidate ID")
                if args.check_only:
                    spec = load_spec(args.spec.resolve())
                    emit({"valid": True, "executed": False, "argv": spec["argv"]})
                else:
                    result = run_experiment(args.spec.resolve(), project / "experiments")
                    result["id"] = "exp_" + digest([result.get("spec_sha256"), result.get("stdout_path"), result])[:12]
                    result["idea_id"] = args.idea
                    result["origin"] = "explicit_local_execution"
                    store.put("experiments", result)
                    store.event("experiment_completed", {"id": result["id"], "execution_status": result["execution_status"]})
                    export_report(store)
                    emit(result)
                    if result["execution_status"] != "succeeded" or result["integrity_status"] == "changed":
                        return 1
            return 0
        finally:
            if store:
                store.close()


def main(argv=None):
    args = build_parser().parse_args(argv)
    try:
        return execute(args)
    except BudgetExhausted as exc:
        print(f"Budget stopped: {exc}", file=sys.stderr)
        return 3
    except (BackendError, LiteratureError, ValueError, RuntimeError, OSError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("Interrupted. Resume with the same project directory.", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
