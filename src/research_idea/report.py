"""Human-readable reports alongside machine-readable evidence and versions."""
from __future__ import annotations

from .presentation import activity_summary, idea_markdown
from .citations import Citations

import json
from pathlib import Path
from .store import Store, now, digest
from .claims import current_claim_audits
from .paper_reading import current_cards, FACET_LABELS


COMPARISON_DIMENSIONS = {
    "problem": "研究问题", "mechanism": "作用机制", "information": "可用信息",
    "objective": "优化目标", "evaluation": "评测条件", "claim": "贡献主张",
}
FEASIBILITY_DIMENSIONS = {
    "data_access": "数据可得性", "inference_signal": "推理时信号", "interface": "实现接口",
    "learning_signal": "学习信号", "compute": "计算资源", "evaluation": "评测有效性",
    "minimal_test": "最小验证",
}
SIGNAL_STAGES = {"training": "训练", "inference": "推理", "evaluation": "评测"}


def bullets(items):
    return "\n".join("- " + str(x).replace("\n", "\n  ") for x in items) or "- 尚未提供"


def table(headers, rows):
    """Keep generated prose, pipes and line breaks inside their table cells."""
    def cell(value):
        return str(value).replace("\\", "\\\\").replace("|", "\\|").replace("\r", " ").replace("\n", "；")
    return "\n".join(["| " + " | ".join(map(cell, headers)) + " |",
                      "| " + " | ".join("---" for _ in headers) + " |",
                      *("| " + " | ".join(map(cell, row)) + " |" for row in rows)])


def comparison_table(overlap):
    rows = []
    comparisons = overlap.get("comparisons", [])
    for dimension, label in COMPARISON_DIMENSIONS.items():
        matching = [item for item in comparisons if item.get("dimension") == dimension]
        for item in matching or [{}]:
            rows.append((label, item.get("prior_detail", "尚未提供"),
                         item.get("proposed_detail", "尚未提供"), {"same": "相同", "different": "不同", "unknown": "需进一步对照"}.get(item.get("relation"), "需进一步对照"),
                         ", ".join(item.get("evidence_ids", [])) or "无"))
    return table(["维度", "现有工作", "候选方案", "关系", "原文证据"], rows)


def feasibility_markdown(candidate, spec):
    feasibility = spec.get('feasibility', {})
    rows = [(FEASIBILITY_DIMENSIONS.get(c['dimension'], c['dimension']), c['requirement'],
             c['verification_plan'], c['failure_action']) for c in feasibility.get('checks', [])]
    lines = ['### 实施安排', '', table(['方面', '需要什么', '第一步怎么检查', '替代安排'], rows), '']
    signals = feasibility.get('required_signals', [])
    if signals:
        lines.extend(['### 输入与信号', '', table(['信号', '使用阶段', '获取方式', '替代方案'], [
            (i['name'], SIGNAL_STAGES.get(i['needed_at'], i['needed_at']),
             ('当前不可用；' if i['availability'] == 'unavailable' else '') + i['acquisition_plan'], i['substitute'])
            for i in signals]), ''])
    return '\n'.join(lines)


def candidate_markdown(candidate, citations=None):
    lines = [idea_markdown(candidate), '']
    if candidate['proposal'].get('selection_reason'):
        lines.extend(['### 构思时的选择理由', '', candidate['proposal']['selection_reason'], ''])
    if candidate['proposal'].get('positioning'):
        lines.extend(['### 构思时的动机与贡献对照', ''])
        for item in candidate['proposal']['positioning']:
            paper = citations.paper(item['paper_id']) if citations else item['paper_id']
            lines.extend([paper, '', '**已有工作回答了：** ' + item['addressed_problem'], '',
                          '**我们继续回答：** ' + item['remaining_question'], '',
                          '**为什么是实质进展：** ' + item['contribution'], '', ', '.join(item['evidence_ids']), ''])
    spec = candidate.get('spec') or {}
    if not spec:
        text = '\n'.join(lines)
        return citations.text(text) if citations else text
    method = spec['method']
    if spec.get('design_decisions'):
        lines.extend(['### 技术选择与理由', ''])
        for item in spec['design_decisions']:
            lines.extend(['**设计问题：** ' + item['question'], '', '**采用：** ' + item['choice'], '',
                          '**为什么适合：** ' + item['rationale'], '', '**需要的修改：** ' + item['adaptation'], '',
                          '**简单替代方案：** ' + item['alternative'], '',
                          ', '.join(item['evidence_ids']), ''])
    lines.extend(['### 技术参考记录', ''])
    lines.extend(['**具体改动：**', '', bullets(method['changes']), '', '**执行步骤：**', '',
                  '\n'.join(f'{i}. {step}' for i, step in enumerate(method['inference_steps'], 1)), ''])
    for key, label in [('inputs', '可用输入'), ('outputs', '预期输出'),
                       ('base_implementation', '基础实现'), ('trainable_parameters', '训练部分'),
                       ('frozen_parameters', '保持不变的部分'), ('objective', '目标'),
                       ('supervision', '学习信号'), ('resource_requirements', '资源条件')]:
        lines.extend([f'**{label}：** {method[key]}', ''])
    for assumption in method['assumptions']:
        lines.extend(['**设计假设：** ' + assumption['statement'], '', '检验方式：' + assumption['check'], ''])
    lines.extend(['### 最近工作对照', ''])
    for overlap in spec['prior_art']['overlaps']:
        lines.extend(['#### ' + (citations.paper(overlap['paper_id']) if citations else overlap['paper_id']), '',
                      '**已有工作涉及：** ' + overlap['covered_claim'], '',
                      '**本方案继续研究：** ' + overlap['remaining_gap'], '', comparison_table(overlap), ''])
    lines.extend([feasibility_markdown(candidate, spec), ''])
    validation = spec['validation']
    # Old projects may contain a full plan; retain it only in expanded records.
    if validation.get('first_test'):
        lines.extend(['### 已保存的验证记录', '', validation['first_test'], '',
                      '**比较对象：**', '', bullets(validation['baselines']), '',
                      '**控制条件：**', '', bullets(validation['controls']), ''])
    lines.extend(['### 设计讨论与改进', ''])
    for version in candidate.get('versions', []):
        responses = version['spec'].get('review_responses', [])
        if responses:
            lines.extend([f"第 {version['round']} 轮：", '', table(['讨论点', '设计选择', '理由'],
                [(r['issue'], r['change'], r['reason']) for r in responses]), ''])
    for item in (candidate.get('review') or {}).get('issues', []):
        lines.extend(['**讨论点：** ' + item['issue'], '', '**具体处理：** ' + item['action'], ''])
    refs = spec['motivation']['evidence_ids']
    if refs:
        lines.extend(['### 主要原文依据', '', ', '.join(refs), ''])
    text = '\n'.join(lines)
    return citations.text(text) if citations else text


def claim_audits_markdown(audits, citations=None):
    lines = ["## 论文主张与实验支持", "", "以下是对已读取论文材料的审计，不是独立复现。主张的范围、实验的范围和实际有效性必须分开；未读到不能当作论文没有。", ""]
    for audit in audits.values():
        coverage = audit.get("reading_coverage", {})
        lines.extend(["### " + (citations.paper(audit['paper_id']) if citations else audit['paper_id']), "",
            f"审计状态：{audit['status']}；实验阅读：{coverage.get('experiments', 'unavailable')}；附录阅读：{coverage.get('appendix', 'unavailable')}", "",
            coverage.get("notes", ""), ""])
        for claim in audit.get("claims", []):
            lines.extend([f"**作者主张：** {claim['claim']}", "",
                "主张证据：" + (", ".join(claim["claim_evidence_ids"]) or "无"), "",
                "**实际测试范围：**", "",
                table(["任务", "数据", "模型", "设置", "预算"], [[claim["tested_scope"][key] for key in ("tasks", "data", "models", "settings", "budget")]]), "",
                f"**支持判断：** {claim['support_judgment']}（模型原判断：{claim.get('requested_support_judgment', claim['support_judgment'])}）", "",
                f"**有依据的结论边界：** {claim['warranted_conclusion']}", "",
                "结果证据：" + (", ".join(claim["result_evidence_ids"]) or "无"), ""])
            for field, label in (("limitations", "限制"), ("confounds", "混杂因素"), ("missing_controls", "待核查的对照"), ("audit_gaps", "证据缺口"), ("next_reading", "下一步阅读")):
                if claim.get(field):
                    lines.extend([f"**{label}：**", "", bullets(claim[field]), ""])
    text = '\n'.join(lines)
    return citations.text(text) if citations else text


def paper_card_markdown(card, citations=None):
    lines = ["# 论文分析卡：" + (citations.paper(card['paper_id']) if citations else card['paper_id']), "", f"状态：{card['status']}", ""]
    source_inventory = card.get("inventory")
    if source_inventory:
        lines.extend([f"文本覆盖：{source_inventory['text_coverage']}；已提供 {source_inventory['characters_supplied']} / {source_inventory['characters']} 字符。", "",
            "覆盖表示文本已交给成功完成的阅读任务，不保证理解完整。图像、表格布局和公式渲染均未视觉核查。", "",
            "## 章节清单", "", table(["ID", "章节", "角色", "文本覆盖"],
                [(s['id'], s['title'], s['family'], s['text_coverage']) for s in source_inventory['sections']]), "",
            "## 图表与公式标记清单", "", table(["ID", "类型", "标记", "文本覆盖", "视觉检查"],
                [(s['id'], s['kind'], s['label'], s['text_coverage'], s['visual_status']) for s in source_inventory['assets']]), "",
            bullets(source_inventory['inventory_gaps']), ""])
    if card['status'] != 'analyzed':
        lines.extend([card.get('reason', '分析尚未完成。'), ""])
        text = '\n'.join(lines)
        return citations.text(text) if citations else text
    lines.extend([f"论文类型：{card['paper_type']}", "", "## 九维分析框架", ""])
    for item in card['framework']:
        lines.extend([f"### {FACET_LABELS[item['dimension']]}", "", f"[{item['status']}] {item['summary']}", "",
                      "依据：" + (", ".join(item['evidence_ids']) or "无；不可推断未读内容"), ""])
    lines.extend(["## 核心模块", ""])
    for item in card['components']:
        lines.extend([f"### {item['name']}", ""])
        for key, label in (("function", "功能"), ("inputs", "输入"), ("outputs", "输出"), ("necessity", "必要性"), ("contribution_test", "隔离模块贡献的检验")):
            lines.extend([f"**{label}：** {item[key]}", ""])
        lines.extend(["**假设：**", "", bullets(item['assumptions']), "", "依据：" + ", ".join(item['evidence_ids']), ""])
    lines.extend(["## 实验—主张证据链", ""])
    for item in card['experiments']:
        lines.extend([f"### {item['name']}", ""])
        for key, label in (("tested_claim", "检验主张"), ("setup", "设置"), ("comparator", "比较对象"), ("controls", "控制条件"),
                           ("reported_result", "报告结果"), ("supported_conclusion", "可支持结论"), ("unsupported_inference", "不支持的更强推断")):
            lines.extend([f"**{label}：** {item[key]}", ""])
        lines.extend(["依据：" + ", ".join(item['evidence_ids']), "", "图表/公式：" + (", ".join(item['asset_ids']) or "未关联；不可视作已检查全部图表"), ""])
    lines.extend(["## 作者明确承认的局限", "", bullets([x['statement'] + "；依据：" + ", ".join(x['evidence_ids']) for x in card['author_limitations']]), "",
                  "## 模型分析出的疑点", ""])
    for item in card['analyst_concerns']:
        lines.extend([item['concern'], "", "竞争解释：" + item['alternative_explanation'], "", "区分检验：" + item['discriminating_test'], "",
                      "依据：" + ", ".join(item['evidence_ids']), ""])
    lines.extend(["## 待检验的研究机会", ""])
    for item in card['opportunities']:
        lines.extend([item['hypothesis'], "", "意义：" + item['why_meaningful'], "", "首个检验：" + item['first_test'], "",
                      "证伪条件：" + item['falsifier'], "", "依据：" + ", ".join(item['evidence_ids']), ""])
    lines.extend(["## 阅读缺口与补读", "", bullets(card['reading_gaps']), "",
                  table(["目标", "问题", "影响", "执行记录"], [(r['target_id'], r['question'], r['decision_impact'], r['status']) for r in card.get('followup_attempts', [])]), "",
                  "**仍建议补读（不代表已执行）：**", "", bullets([r['target_id'] + "：" + r['question'] for r in card['followup_requests']]), "",
                  card['assessment_boundary'], ""])
    text = '\n'.join(lines)
    return citations.text(text) if citations else text


def export_report(store: Store, output_dir: Path | None = None):
    from .evidence_matching import current_quote_gaps
    target = output_dir or store.project / "outputs"
    target.mkdir(parents=True, exist_ok=True)
    candidates = store.rows("candidates")
    papers = store.rows("papers")
    evidence = store.rows("evidence")
    citations = Citations(papers, evidence)
    demo = store.get("demo", False)
    cards = current_cards(papers, evidence, store.get("paper_cards", {}), store.get("paper_readings", {}))
    data = {"schema_version": 6, "generated_at": now(), "demo": demo, "topic": store.get("topic"), "status": store.get("status", "initialized"),
        "problem_model": store.get("problem_model"), "no_candidate_reason": store.get("no_candidate_reason", ""), "calls_used": store.get("calls_used", 0),
        "papers": [{k: v for k, v in p.items() if k not in {"text", "abstract"}} for p in papers], "evidence": evidence,
        "candidates": candidates, "search_ledger": store.get("search_ledger", {}),
        "manual_search_ledger": store.get("manual_search_ledger", []),
        "search_scope": store.get("active_search_scope", {}),
        "search_windows": store.get('active_search_windows', {}),
        "paper_selections": store.get('paper_selections', []),
        "full_text_ledger": store.get("full_text_ledger", {}),
        "search_plans": store.get("search_plans", {}),
        "quote_gaps": current_quote_gaps(store),
        "paper_claim_audits": current_claim_audits(papers, evidence, store.get("paper_claim_audits", {})),
        "paper_cards": cards,
        "paper_card_files": {key: "papers/paper_" + digest(key)[:16] + ".md" for key in cards},
        "active_skills": store.get("active_skills", [])}
    json_path = target / "report.json"
    json_path.write_text(json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    title = '研究方案' if data['status'] == 'completed' else '当前构思与方法草稿'
    lines = ["# Research-idea — " + title, "", store.get("topic", ""), ""]
    if demo:
        lines.extend(["> **合成演示：所有资料和候选仅用于验证软件流程。没有调用真实模型，没有完成科学实验，不构成创新或效果结论。**", ""])

    # Keep the main deliverable focused on the idea and supporting techniques. Existing
    # evidence, paper cards and audit details remain accessible below.
    if candidates:
        lines.extend(["## 研究 Idea", ""])
        for candidate in candidates:
            lines.extend([citations.text(idea_markdown(candidate)), ''])
            compared = [o['paper_id'] for o in (candidate.get('spec') or {}).get('prior_art', {}).get('overlaps', [])]
            references = compared or candidate['proposal'].get('closest_work_ids', [])
            linked = [p for ref in dict.fromkeys(references) for p in papers if p['id'] == ref][:3]
            if linked:
                lines.extend(['**相关论文：**', ''])
                lines.extend('- ' + citations.paper(p['id']) for p in linked)
                lines.append('')
            lines.extend([f"[展开方法与论文对照]({candidate['id']}.md)", ""])
    else:
        lines.extend([data['no_candidate_reason'] or "方案正在形成中，可从已保存的进度继续运行。", ""])
    lines.extend(["<details>", "<summary>详细分析与原文依据</summary>", "", f"项目状态：{data['status']}；模型任务调用：{data['calls_used']}", "", "方案是实验前的研究设计；原文引文、审阅与执行记录如下。", ""])
    if data['quote_gaps']:
        lines.extend(['## 未采用的引用', '', '下列引用未通过来源定位，未进入证据库；对应结论保持未知。', ''])
        for task_id, gap in data['quote_gaps'].items():
            lines.append(f"- {gap['paper_id']} / {task_id}：排除 {len(gap['rejected'])} 条，保留 {gap['accepted_count']} 条已校验观察。")
        lines.append('')
    if data["active_skills"]:
        lines.extend(["## 本次加载的研究 Skill", "", "这些文件提供研究步骤；它们不是论文证据，也不代表其中的脚本或外部工具已执行。", "",
            table(["名称", "来源", "阶段", "SHA-256"], [(s["name"], s.get("origin", "local"), ", ".join(s["stages"]), s["sha256"]) for s in data["active_skills"]]), ""])
    problem = data["problem_model"]
    if problem:
        lines.extend(["## 问题模型", "", problem["problem"], "", "**竞争解释：**", "", bullets(problem["competing_explanations"]), "", "**未知项：**", "", bullets(problem["unresolved_questions"]), ""])
        if problem.get('opportunities'):
            lines.extend(['## 文献导出的研究切口', '', activity_summary('map', problem, citations), ''])
    if not candidates:
        lines.extend([data["no_candidate_reason"] or "暂无已完成的候选。检查项目状态和任务日志。", ""])
    for c in candidates:
        lines.append(candidate_markdown(c, citations))
        (target / (c["id"] + ".md")).write_text(("# 合成演示；非科学结论\n\n" if demo else "") + candidate_markdown(c, citations), encoding="utf-8")
    if data["paper_claim_audits"]:
        lines.append(claim_audits_markdown(data["paper_claim_audits"], citations))
    if cards:
        (target / "papers").mkdir(exist_ok=True)
        lines.extend(["## 逐篇结构化分析", ""])
        for key, card in cards.items():
            filename = data['paper_card_files'][key]
            (target / filename).write_text(paper_card_markdown(card, citations), encoding='utf-8')
            coverage = card.get('inventory') or {}
            lines.append(f"- {citations.paper(key)}；文本覆盖：{coverage.get('text_coverage', 'unavailable')}；[分析卡]({filename})")
        lines.append("")
    if data["search_plans"]:
        lines.extend(["## 研究意图与检索计划", "", "计划不等于已执行；实际结果和覆盖缺口见下一节。", ""])
        for key, plan in data["search_plans"].items():
            lines.extend([f"### {key}", "", plan["research_question"], "", "范围：" + plan["scope"], "",
                table(["英文查询", "目的", "理由"], [(q["query"], q["purpose"], q["rationale"]) for q in plan["queries"]]), "",
                "假设：", "", bullets(plan["assumptions"]), ""])
    lines.extend(["## 检索与阅读覆盖", "",
        "检索结果受来源索引、查询、会议过滤和数量预算限制；未检索到不等于不存在。全文下载成功也不等于每一节都已阅读。", ""])
    scope = data["search_scope"]
    if scope:
        lines.extend([f"当前联网检索日期：{scope.get('since') or '不限起点'} 至 {scope.get('until') or '不限终点'}；"
                      f"来源：{scope.get('source', 'unknown')}；CS 硬限制：{scope.get('cs_only', False)}；"
                      f"arXiv 分类：{', '.join(scope.get('arxiv_categories', [])) or '不限'}。", "",
                      "已有或显式导入的资料保留为项目上下文；上述限制针对新执行的联网检索。", ""])
    searches = list(data["search_ledger"].values()) + data["manual_search_ledger"]
    if searches:
        lines.extend([table(["查询", "来源", "会议范围", "日期范围", "状态", "返回记录"],
            [(s.get("query", ""), s.get("source", ""), ", ".join(s.get("venues", [])) or "不限会议",
              (s.get("filters", {}).get("since") or "不限起点") + " 至 " + (s.get("filters", {}).get("until") or "不限终点"),
              s.get("status", "unknown"), s.get("found", s.get("added", 0))) for s in searches]), ""])
        gaps = [f"{s.get('query', '')}：{gap}" for s in searches
                for gap in (s.get("coverage") or {}).get("gaps", [])]
        if gaps:
            lines.extend(["**本次检索的具体缺口：**", "", bullets(gaps), ""])
    else:
        lines.extend(["本项目没有已记录的联网检索；仅据提供的来源分析。", ""])
    lines.extend(["## 文献与来源", ""])
    for p in papers:
        venue = p.get('venue') or ('arXiv 预印本' if p.get('source') == 'arxiv' else '会议未核实')
        lines.append(f"- {citations.paper(p['id'])}；{p.get('publication_date') or p.get('year') or '日期未核实'}；{venue}；{p.get('content_kind', 'abstract')}")
        if p.get("full_text_error"):
            lines.append("  全文缺口：" + str(p["full_text_error"]))
        if p.get('full_text_origin'):
            origin = p['full_text_origin']
            lines.append(f"  实际阅读版本：arXiv {origin.get('version') or '版本未标明'}；{origin.get('url', '')}；会议元数据与预印本版本分别保留。")
    lines.extend(["", "## 原文证据", ""])
    for index, e in enumerate(evidence, 1):
        lines.extend([f"### 原文依据 {index}", "", citations.block(e, markdown=True), ""])
    md_path = target / "report.md"
    lines.extend(["", "</details>"])
    md_path.write_text(citations.text("\n".join(lines)) + "\n", encoding="utf-8")
    return md_path, json_path
