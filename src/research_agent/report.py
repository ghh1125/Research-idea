"""Human-readable reports alongside machine-readable evidence and versions."""
from __future__ import annotations

import json
from pathlib import Path
from .store import Store, now


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
                         item.get("proposed_detail", "尚未提供"), item.get("relation", "pending"),
                         ", ".join(item.get("evidence_ids", [])) or "无"))
    return table(["维度", "现有工作", "候选方案", "关系", "原文证据"], rows)


def feasibility_markdown(candidate, spec):
    feasibility = spec.get("feasibility", {})
    assessment = candidate.get("feasibility_assessment", {})
    lines = ["### 七维可行性检查", "",
             f"**当前状态：** {candidate.get('feasibility_status', assessment.get('status', 'pending'))}", "",
             "`pending` / `prerequisites_unverified` 表示前提待核查；`blocked` 表示存在阻塞。"
             "`source_supported` 只表示来源支持，`specified_not_executed` 只表示前提已描述，均不代表实际运行通过。", ""]
    checks = feasibility.get("checks", [])
    rows = []
    for dimension, label in FEASIBILITY_DIMENSIONS.items():
        matching = [item for item in checks if item.get("dimension") == dimension]
        for item in matching or [{}]:
            rows.append((label, item.get("status", "pending"), item.get("requirement", "尚未提供"),
                         ", ".join(item.get("evidence_ids", [])) or "无",
                         item.get("verification_plan", "尚未提供"), item.get("failure_action", "尚未提供")))
    lines.extend([table(["维度", "状态", "具体前提", "原文证据", "执行前核查", "前提失败后的动作"], rows), "",
                  "### 所需信号与可得阶段", ""])
    signals = feasibility.get("required_signals", [])
    if signals:
        lines.extend([table(["信号", "需要阶段", "可得性", "原文证据", "获取与核查计划", "不可得时的替代方案"],
                            [(item.get("name", "尚未提供"), SIGNAL_STAGES.get(item.get("needed_at"), item.get("needed_at", "pending")),
                              item.get("availability", "pending"), ", ".join(item.get("evidence_ids", [])) or "无",
                              item.get("acquisition_plan", "尚未提供"), item.get("substitute", "尚未提供"))
                             for item in signals]), ""])
    else:
        lines.extend(["尚未列出所需信号；不能据此认定训练、推理或评测输入可得。", ""])
    for key, label in [("blocking_checks", "阻塞前提"), ("unverified_checks", "待核查前提")]:
        items = assessment.get(key, [])
        if items:
            lines.extend([f"**{label}：**", ""])
            for item in items:
                name = FEASIBILITY_DIMENSIONS.get(item.get("dimension"), item.get("name", "未知前提"))
                stage = item.get("needed_at")
                if stage:
                    name += "（" + SIGNAL_STAGES.get(stage, stage) + "）"
                lines.append(f"- {name}：{item.get('reason', item.get('requirement', '待核查'))}")
            lines.append("")
    if assessment.get("warnings"):
        lines.extend(["**可行性判断边界：**", "", bullets(assessment["warnings"]), ""])
    return "\n".join(lines)


def candidate_markdown(candidate):
    p = candidate["proposal"]
    lines = [f"## {p['title']}", "", f"ID: `{candidate['id']}`", "",
        f"- 新颖性状态：{candidate.get('novelty_status', 'unchecked')}",
        f"- 动机审阅状态：{candidate.get('motivation_status', 'pending')}",
        f"- 可行性状态：{candidate.get('feasibility_status', 'pending')}",
        f"- 研究进度：{candidate['research_status']}", f"- 实施状态：{candidate['execution_status']}",
        f"- 实验证据：{candidate['empirical_status']}", "",
        "### 问题与机制", "", f"**问题：** {p['problem']}", "", f"**假设：** {p['hypothesis']}", "",
        f"**机制：** {p['mechanism']}", "", f"**干预：** {p['intervention']}", "",
        f"**预测：** {p['prediction']}", "", f"**反例/证伪条件：** {p['falsifier']}", "",
        f"**价值：** {p['why_it_matters']}", "", "支持证据：" + ", ".join(p["evidence_ids"]), ""]
    motivation = candidate.get("spec", {}).get("motivation", p.get("motivation", {}))
    lines.extend(["### 问题—动机—方法", ""])
    for key, label in [("problem_observation", "实际问题与现象"), ("importance", "问题的重要性"),
                       ("existing_approach_limit", "现有方法为什么不足"), ("causal_explanation", "导致问题的机制解释"),
                       ("why_this_method", "为何这个方法对应上述原因"), ("expected_progress", "预期实质进展"),
                       ("simplest_alternative", "最简单的替代方案"), ("necessity_test", "新方法必要性的验证")]:
        lines.extend([f"**{label}：** {motivation.get(key, '尚未提供；保持 pending')}", ""])
    lines.extend(["动机依据：" + (", ".join(motivation.get("evidence_ids", [])) or "无；待补原文证据"), ""])
    if not candidate.get("spec"):
        lines.extend(["尚未完成实施规格；不能标记为可实施或已经验证。", ""])
        return "\n".join(lines)
    s = candidate["spec"]
    method = s["method"]
    novelty = s.get("novelty_claim", {})
    lines.extend(["### 待检验的贡献主张", ""])
    for key, label in [("type", "贡献类型"), ("claim", "具体贡献"), ("changed_variable", "改变的变量"),
                       ("observable_consequence", "可观测后果"), ("falsifier", "证伪条件"), ("nontriviality", "非平凡性依据")]:
        lines.extend([f"**{label}：** {novelty.get(key, '尚未提供；保持 pending')}", ""])
    lines.extend(["### 实施规格", ""])
    for key, label in [("base_implementation", "基础实现"), ("inputs", "输入"), ("outputs", "输出"), ("trainable_parameters", "训练参数"), ("frozen_parameters", "冻结参数"), ("objective", "训练目标"), ("supervision", "监督来源"), ("resource_requirements", "资源前提")]:
        lines.extend([f"**{label}：** {method[key]}", ""])
    lines.extend(["**修改：**", "", bullets(method["changes"]), "", "**推理步骤：**", "", bullets(method["inference_steps"]), "", "**关键假设：**", ""])
    for a in method["assumptions"]:
        lines.append(f"- [{a['status']}] {a['statement']}；检查方法：{a['check']}；证据：{', '.join(a['evidence_ids']) or '无'}")
    lines.extend(["", "### 最近工作与差异", "", s["prior_art"]["justification"], ""])
    lines.extend(["以下按研究问题、机制、可用信息、目标、评测和贡献主张逐项对照。"
                  "`unknown` / `pending` 表示未核清；发现局部差异不等于已经确认创新。", ""])
    for overlap in s["prior_art"]["overlaps"]:
        lines.extend([f"#### {overlap['paper_id']}", "",
                      f"重叠层级：{overlap['level']}。已涉及主张：{overlap['covered_claim']}。剩余问题：{overlap['remaining_gap']}。证据：{', '.join(overlap['evidence_ids']) or '无'}", "",
                      comparison_table(overlap), ""])
    if not s["prior_art"]["overlaps"]:
        lines.extend(["尚无逐篇方法对照；新颖性保持待核查。", ""])
    if candidate.get("comparison_gaps"):
        lines.extend(["**对照仍缺的信息：**", "", bullets(candidate["comparison_gaps"]), ""])
    lines.extend(["建议的后续检索（不等于已执行）：", "", bullets(s["prior_art"]["search_queries"]), "",
                  feasibility_markdown(candidate, s), "", "### 最小验证计划", ""])
    v = s["validation"]
    for key, label in [("weakest_assumption", "最脆弱前提"), ("first_test", "第一步"), ("positive", "正结果解释"), ("negative", "负结果解释"), ("inconclusive", "不明确结果解释"), ("budget_estimate", "预算")]:
        lines.extend([f"**{label}：** {v[key]}", ""])
    lines.extend(["**基线：**", "", bullets(v["baselines"]), "", "**控制变量：**", "", bullets(v["controls"]), "", "### 待解决问题", ""])
    review = candidate.get("review", {})
    motivation_review = review.get("motivation_assessment", {})
    lines.extend(["**问题与方法的审阅：**", ""])
    for key, label in [("problem_significance", "问题价值"), ("causal_link", "动机与方法的因果联系"),
                       ("progress", "实质进展或增量修改"), ("reason", "判断依据"), ("decisive_test", "决定性检验")]:
        lines.extend([f"**{label}：** {motivation_review.get(key, '尚未审阅；保持 pending')}", ""])
    lines.extend([bullets(review.get("unresolved_questions", [])), ""])
    for issue in review.get("issues", []):
        lines.append(f"- [{issue['severity']}] {issue['issue']} → {issue['action']}")
    action = candidate.get("recommended_action") or review.get("next_action", s["next_action"])
    lines.extend(["", f"**下一步：** [{action['kind']}] {action['description']}", "", f"**将解决：** {action['decision_impact']}", ""])
    if candidate.get("warnings"):
        lines.extend(["**证据边界：**", "", bullets(candidate["warnings"]), ""])
    return "\n".join(lines)


def export_report(store: Store, output_dir: Path | None = None):
    target = output_dir or store.project / "outputs"
    target.mkdir(parents=True, exist_ok=True)
    candidates = store.rows("candidates")
    papers = store.rows("papers")
    evidence = store.rows("evidence")
    demo = store.get("demo", False)
    data = {"schema_version": 2, "generated_at": now(), "demo": demo, "topic": store.get("topic"), "status": store.get("status", "initialized"),
        "problem_model": store.get("problem_model"), "no_candidate_reason": store.get("no_candidate_reason", ""), "calls_used": store.get("calls_used", 0),
        "papers": [{k: v for k, v in p.items() if k not in {"text", "abstract"}} for p in papers], "evidence": evidence,
        "candidates": candidates, "experiments": store.rows("experiments"), "search_ledger": store.get("search_ledger", {})}
    json_path = target / "report.json"
    json_path.write_text(json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    lines = ["# Research Agent — 研究方案", "", store.get("topic", ""), ""]
    if demo:
        lines.extend(["> **合成演示：所有资料和候选仅用于验证软件流程。没有调用真实模型，没有完成科学实验，不构成创新或效果结论。**", ""])
    lines.extend([f"项目状态：{data['status']}；模型任务调用：{data['calls_used']}", "", "> 引文匹配仅验证原文存在，不证明引文支持全部解释。模型审阅不等于独立实验。候选列出顺序不代表有效性排名。", ""])
    problem = data["problem_model"]
    if problem:
        lines.extend(["## 问题模型", "", problem["problem"], "", "**竞争解释：**", "", bullets(problem["competing_explanations"]), "", "**未知项：**", "", bullets(problem["unresolved_questions"]), ""])
    if not candidates:
        lines.extend([data["no_candidate_reason"] or "暂无已完成的候选。检查项目状态和任务日志。", ""])
    for c in candidates:
        lines.append(candidate_markdown(c))
        (target / (c["id"] + ".md")).write_text(("# 合成演示；非科学结论\n\n" if demo else "") + candidate_markdown(c), encoding="utf-8")
    lines.extend(["## 文献与来源", ""])
    for p in papers:
        lines.append(f"- `{p['id']}` — {p['title']}；{p.get('content_kind', 'abstract')}；{p.get('url', '')}")
    lines.extend(["", "## 原文证据", ""])
    for e in evidence:
        lines.extend([f"### {e['id']}", "", f"来源 `{e['paper_id']}`，第 {e['page']} 页 / 第 {e['line']} 行；{e['source_kind']}；{e['reading_coverage']}", "", e["statement"], "", "> " + e["quote"].replace("\n", "\n> "), "", "条件：" + e["conditions"], ""])
    if data["experiments"]:
        lines.extend(["## 实验执行记录", "", "执行完成不代表研究主张成立；结果需另行解释。", ""])
        for experiment in data["experiments"]:
            lines.append(f"- `{experiment['id']}`：执行={experiment.get('execution_status')}，科学判断={experiment.get('scientific_status', 'unreviewed')}，有效指标={experiment.get('metrics_valid')}")
    md_path = target / "report.md"
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return md_path, json_path
