"""Explicit synthetic backend for offline product tests, never a model fallback."""
from __future__ import annotations

import json
from .backend_types import BackendResult

DEMO_TOPIC = "演示：长上下文中证据冲突的诊断实验（合成资料，不是研究结论）"
DEMO_PAPERS = [
    {"id": "demo-source-a", "title": "SYNTHETIC DEMO A — evidence conflict", "authors": [], "year": None, "url": "", "source": "synthetic_demo", "content_kind": "notes",
     "text": "This is a synthetic demonstration, not a scientific paper.\nIn a hypothetical task, conflicting passages can lead to inconsistent answers even when both passages are supplied.\nNo experiments were performed and no performance numbers are available."},
    {"id": "demo-source-b", "title": "SYNTHETIC DEMO B — diagnostic controls", "authors": [], "year": None, "url": "", "source": "synthetic_demo", "content_kind": "notes",
     "text": "This is a synthetic demonstration, not a scientific paper.\nA hypothetical diagnostic could keep retrieval fixed while varying contradiction and passage order.\nThese statements illustrate data flow only and do not establish novelty or effectiveness."},
]


def demo_design_plan(*, technical=True):
    """Synthetic planning fixture; these are not literature-derived findings."""
    axes = [
        {'id': 'relations', 'question': '怎样保留文本证据之间的关系？',
         'why_needed': '只有保留关系，才能讨论证据齐全时为什么仍发生使用错误。',
         'required_function': '在不使用答案标签的情况下表达支持、冲突与适用条件。',
         'search_directions': ['文本关系表示', '条件性知识表示']},
        {'id': 'use', 'question': '怎样让回答过程使用这些条件关系？',
         'why_needed': '关系记录需要参与推理，才能作用于候选提出的信息使用问题。',
         'required_function': '根据可见条件组织证据，使回答依据可追溯到对应关系。',
         'search_directions': ['条件推理', '证据约束生成']},
    ] if technical else []
    return {'research_question': 'How can supplied evidence support conditional reasoning?',
            'scope': 'Synthetic planning example, not a scientific finding.', 'design_axes': axes,
            'queries': [{'query': query, 'purpose': 'mechanism', 'rationale': reason,
                         'axis_ids': [axis] if technical else []}
                        for query, axis, reason in [
                            ('text evidence relation representation', 'relations', 'Find relation representations.'),
                            ('conditional evidence reasoning generation', 'use', 'Find ways to use conditional evidence.')]],
            'assumptions': ['Synthetic demonstration only.']}


class DemoBackend:
    name = "demo-synthetic"

    def generate(self, task):
        payload = json.loads(task.prompt.split("BEGIN_RESEARCH_DATA\n", 1)[1].split("\nEND_RESEARCH_DATA", 1)[0])
        refs = [e["id"] for e in payload.get("evidence", [])]
        papers = [p["id"] for p in payload.get("papers", [])]
        if task.stage == 'plan_search':
            output = demo_design_plan(technical=payload.get('purpose') == 'technical_design')
        elif task.stage == "screen_papers":
            output = {'selection_summary': 'Synthetic selection for workflow demonstration.',
                'selected': [{'paper_id': p['id'], 'reason': 'Synthetic topic-related source.',
                              'reading_question': 'Which synthetic statement illustrates the workflow?'}
                             for p in payload['papers'][:payload['max_papers']]]}
        elif task.stage == "extract":
            lines = [x for x in payload["excerpt"].splitlines() if len(x) >= 15]
            output = {"observations": [{"statement": "合成资料提出一个待检验的诊断场景；没有实测结果。", "quote": lines[1] if len(lines) > 1 else lines[0], "kind": "author_claim", "conditions": "synthetic example only", "source_section": "demo paragraph"}]}
        elif task.stage == "map":
            output = {"problem": "演示问题：区分检索遗漏与冲突处理失误。", "observations": ["输入是合成笔记，不提供经验证的现象。"], "competing_explanations": ["证据缺失", "证据冲突", "顺序影响"], "unresolved_questions": ["实际任务中是否存在该现象？"], "opportunity_types": ["unresolved_need", "emerging_problem"], "evidence_ids": refs}
            output['research_frame'] = {
                'user_goal': payload.get('topic') or '理解模型怎样更可靠地使用已有信息。',
                'literature_logic': '合成材料涉及两类解释：没有获得足够信息，以及没有用好已经获得的信息。这两类解释意味着不同的研究方向。',
                'research_question': '怎样分清信息缺失和信息使用困难，进而改善回答的可靠性？',
                'scope_connection': '合成笔记只演示推理流程；其中的任务不替代用户的总体研究目标，也不提供真实研究结论。'}
            output['opportunities'] = [
                {'id': key, 'question': question, 'basis': 'research_hypothesis',
                 'problem_origin': 'unresolved_need' if key == 'conflict' else 'emerging_problem',
                 'derivation': '合成笔记提供不同错误来源的线索；这些是假设而非已观测的结果。',
                 'insight': insight, 'why_it_matters': '若实际存在，可帮助解释已有证据为什么未被有效使用。',
                 'prior_art_delta': '演示把错误来源区分为可讨论的问题；合成材料不能证明科学创新。',
                 'feasibility_basis': '问题和文本证据可通过普通生成接口输入，无需模型内部信号。',
                 'evidence_ids': refs, 'closest_work_ids': papers}
                for key, question, insight in [
                    ('conflict', '完整证据存在时，冲突关系如何影响回答？', '区分证据缺失与使用已有证据的困难。'),
                    ('order', '相同证据的顺序为何影响回答？', '研究顺序与内容之间的影响区别。')]]
        elif task.stage == "propose":
            candidates = []
            for title, intervention in [("演示候选：固定检索的冲突诊断", "保持证据完整，改变冲突程度"), ("演示候选：证据顺序敏感性", "保持证据内容，随机交换段落顺序")][:payload["max_candidates"]]:
                candidates.append({"title": title, "problem": "诊断假想错误来源", "hypothesis": "待检验：输入证据的关系会影响答案稳定性。", "mechanism": "在信息保持可用时分离冲突或顺序因素。", "intervention": intervention, "prediction": "如果假设成立，控制条件之间会出现可重复差异。", "falsifier": "正确实现且测量充分时没有差异，或简单控制解释全部差异。", "evidence_ids": refs, "closest_work_ids": papers, "why_it_matters": "演示如何把假设转化为诊断，不宣称创新或有效。"})
                candidates[-1]['opportunity_id'] = payload['problem_model']['opportunities'][len(candidates) - 1]['id']
                candidates[-1]['selection_reason'] = '合成演示优先区分信息缺失与使用困难，保留研究问题和可用信息之间的联系。'
                candidates[-1]["motivation"] = {"basis": "research_hypothesis", "background": "多来源问答需要可靠地使用已经取得的证据。", "problem_observation": "合成笔记描述假想的证据冲突错误；尚无实测现象。", "evidence_ids": refs,
                    "existing_work": "合成场景中的现有做法通过检索向回答模型提供相关文本，以缓解信息缺失。",
                    "importance": "若实际存在，将影响依据多来源材料回答的可靠性；重要性仍待真实数据验证。",
                    "existing_approach_limit": "假设只增加检索无法区分证据缺失和冲突处理失误；尚需文献验证。",
                    "causal_explanation": "候选解释：证据关系或顺序影响模型使用已有信息。", "why_this_method": "固定检索与内容，对冲突或顺序作干预以区分原因。",
                    "research_need": "因此需要在证据已经提供的条件下，弄清关系与顺序怎样影响使用过程，才能确定问题应从检索还是推理环节解决。",
                    "expected_progress": "在限定条件下区分错误来源，形成可证伪解释；不是声称提升指标。",
                    "simplest_alternative": "随机交换顺序而不使用候选机制。", "necessity_test": "如果随机对照解释全部差异，则该机制没有额外解释力。"}
                candidates[-1]['positioning'] = [{'paper_id': p, 'addressed_problem': '合成材料提出证据冲突诊断。',
                    'remaining_question': '实际错误由缺失还是冲突引起？', 'contribution': '分离两类原因的可检验解释。',
                    'evidence_ids': [e['id'] for e in payload['evidence'] if e['paper_id'] == p]} for p in papers]
                candidates[-1]['feasibility_sketch'] = {
                    'inputs': '模型只接收问题和证据；参考答案只用于评测。',
                    'available_path': '先人工构造少量配对文本，通过普通文本生成接口比较输出，无需权重或 logits。',
                    'key_assumption': '输入变换保持任务语义，只改变研究因素。',
                    'first_check': '人工检查配对样本，确认随机变换不能解释全部差异。'}
                candidates[-1]['idea_core'] = {
                    'concrete_target': '合成资料中，同一问题的两条证据在结论上的冲突，以及证据出现的先后关系。',
                    'construction_path': '由资料中的陈述和条件组成配对输入，保留原句以核对内容是否变化；不让模型生成的判断充当真实标签。',
                    'capability_bridge': '固定已经取得的内容，只改变冲突或顺序，从回答变化中区分资料缺失与使用困难；这里提出解释，不宣称获得实测能力。',
                    'essential_difference': '相比继续增加检索内容，合成候选改变的是已有证据之间的关系，关注信息已提供时的使用困难；真实贡献仍需真实文献判断。'}
            output = {"candidates": candidates, "no_candidate_reason": ""}
        elif task.stage in {"develop", "refine"}:
            overlap_evidence = payload["evidence"][0] if payload["evidence"] else None
            comparisons = [{"dimension": dim, "prior_detail": "只有合成笔记，尚无真实论文方法细节。",
                "proposed_detail": "固定模型与检索条件，诊断证据冲突及顺序影响。", "relation": "unknown", "evidence_ids": []}
                for dim in ("problem", "mechanism", "information", "objective", "evaluation", "claim")]
            checks = [{"dimension": dim, "status": "unverified", "requirement": requirement, "evidence_ids": [],
                "verification_plan": plan, "failure_action": "先解决该前提；未解决时不开始正式实验。"}
                for dim, requirement, plan in [
                    ("data_access", "可合法访问包含冲突条件的数据", "检查数据许可和十个样本"),
                    ("inference_signal", "问题和证据可在推理时获得", "记录模型实际输入并检查答案泄漏"),
                    ("interface", "模型接受文本并返回可解析答案", "运行一个真实模型接口样本"),
                    ("learning_signal", "当前仅诊断，无训练监督", "核对实现未调用训练，评测答案仅进入评测器"),
                    ("compute", "预算覆盖配对推理", "测量十对样本的费用与时延，再估算总预算"),
                    ("evaluation", "变换保持任务语义且标签正确", "盲审成对样本并测试评测器"),
                    ("minimal_test", "小样本能测出所操纵因素", "先做人工验证与oracle诊断，不能当作部署方法"),
                ]]
            changes = ["实现输入条件变换器", "保存逐样本预测和条件标签"]
            if task.stage == "refine":
                changes.append("增加随机信号对照")
            output = {
                "design_axes": payload.get('design_search_plan', demo_design_plan()).get('design_axes', []),
                "design_decisions": [{'axis_ids': ['relations', 'use'], 'question': '怎样分离输入因素？', 'choice': '保持证据内容，做成对条件干预。',
                    'rationale': '直接操纵候选原因并观察预测变化。', 'adaptation': '将通用配对设计用于证据冲突。',
                    'alternative': '随机改变输入条件。', 'first_test': '先比较少量成对样本与随机对照。', 'evidence_ids': refs}],
                "review_responses": [{"issue": item['issue'], "decision": "adopt", "change": "增加随机信号对照", "reason": "区分机制收益与随机变化", "evidence_ids": []} for item in payload.get('review', {}).get('issues', [])],
                "motivation": payload["candidate"]["motivation"],
                "idea_core": payload["candidate"]["idea_core"],
                "method": {"summary": "固定模型与检索结果，只改变证据冲突程度或段落顺序；保存配对答案，比较错误与稳定性。先用随机变换作为简单对照，再判断专门干预是否有额外作用。", "base_implementation": "尚未选择；需要检查实际模型推理接口。", "changes": changes, "inputs": "问题、完整证据、条件标签；答案只供评测。", "outputs": "答案和逐样本诊断结果", "trainable_parameters": "不训练：首先诊断现象", "frozen_parameters": "模型参数保持不变", "objective": "不适用：无训练阶段", "supervision": "需要人工核对的评测答案；当前尚未获取", "inference_steps": ["构造匹配输入", "固定预算调用模型", "保存预测"], "resource_requirements": "未知，先测少量样本延迟与调用成本", "assumptions": [{"statement": "数据中存在可控制的证据冲突", "status": "unverified", "evidence_ids": [], "check": "人工检查样本并验证变换保留任务语义"}]},
                "prior_art": {"verdict": "uncertain", "justification": "合成资料不能支持查新结论。", "overlaps": [{"paper_id": (overlap_evidence or {}).get("paper_id", ""), "level": "topic", "covered_claim": "合成资料讨论相似主题", "evidence_ids": ([overlap_evidence["id"]] if overlap_evidence else []), "remaining_gap": "所有真实文献与机制仍待核查", "comparisons": comparisons}], "search_queries": ["long context conflicting evidence controlled evaluation"]},
                "novelty_claim": {"type": "explanation", "claim": "演示待检验解释：输入证据关系可能影响回答稳定性。", "changed_variable": "冲突程度或段落顺序", "observable_consequence": "内容固定时，配对条件之间的答案稳定性差异", "falsifier": "检查充分后没有差异，或简单控制解释全部差异", "nontriviality": "拟区分错误来源而非增加模块；真实贡献尚需文献与实验验证。"},
                "feasibility": {"checks": checks, "required_signals": [{"name": "问题与检索证据", "needed_at": "inference", "availability": "unverified", "evidence_ids": [], "acquisition_plan": "先取得并检查真实数据样本", "substitute": "没有合适样本则暂缓实验"}, {"name": "真实答案", "needed_at": "evaluation", "availability": "unverified", "evidence_ids": [], "acquisition_plan": "人工核对评测标签，禁止传入模型推理", "substitute": "缺少标签时只做人工诊断"}]},
                "validation": {"summary": "先人工检查少量成对样本，再用固定模型和预算比较原始输入、候选干预与随机对照。观察答案变化是否由研究因素解释。", "weakest_assumption": "输入变换真实操纵了待研究因素", "first_test": "人工检查成对样本，再运行固定预算的配对诊断。", "baselines": ["原始输入", "简单顺序随机化"], "controls": ["相同模型和预算", "真实答案不进入推理输入"], "positive": "只支持该设置下存在值得进一步验证的诊断信号。", "negative": "检查实现和测量能力，再判断是否削弱假设。", "inconclusive": "记录不确定性，不能直接否定方向。", "budget_estimate": "未测量；执行前确定样本量、模型和费用上限。"},
                "next_action": {"kind": "inspect_code", "description": "检查模型接口和数据条件变换器", "decision_impact": "确定关键输入与测量是否可获得。"},
            }
            if not overlap_evidence:
                output['prior_art']['overlaps'] = []
        elif task.stage == "review":
            needs_revision = "增加随机信号对照" not in payload["method_spec"]["method"]["changes"]
            output = {"verdict": "refine" if needs_revision else "continue", "issues": [{"severity": "important", "issue": "需要区分策略收益与随机选择带来的变化。", "evidence_ids": [], "action": "增加简单随机对照。"}] if needs_revision else [], "unresolved_questions": ["真实文献、数据和实测结果尚缺。"], "revision_instructions": "增加随机信号对照，保持原始问题。" if needs_revision else "", "next_action": {"kind": "revise" if needs_revision else "run_experiment", "description": "补充对照" if needs_revision else "在显式配置的实验环境运行诊断", "decision_impact": "区分方法机制与简单解释。"}}
            output["motivation_assessment"] = {"problem_significance": "unclear", "causal_link": "plausible", "progress": "unclear",
                "reason": "动机链可用于演示，但合成笔记不能证明真实问题的重要性或研究贡献。", "decisive_test": "先在真实样本确认问题，再比较干预与随机对照。"}
        else:
            raise ValueError(f"Unsupported demo stage {task.stage}")
        return BackendResult(output=output, usage={"synthetic": True, "cost_usd": None})
