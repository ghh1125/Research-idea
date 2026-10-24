---
name: research-idea-motivation
description: Synthesize literature into an important unresolved or emerging research problem, derive its motivation and form a meaningful idea. Use during problem mapping, proposal, development, refinement or review for LLM/NLP research.
---

## Input

Use the supplied topic, user_notes, constraints, evidence and current task schema. This skill guides reasoning; it is not scientific evidence. Work within the current task, without calling tools or executing scripts.

## Steps

1. **回到用户的大课题。** 先说用户希望解决什么、为什么需要解决。具体研究问题应聚焦一个重要的能力或原因；论文里的数据集、算术题、任务设置是依据，不自动成为研究目标。用户明确限定范围时遵循该范围。
2. **把论文梳理成大逻辑。** 按解决思路理解已有工作：它们试图改变什么，已经让我们做到了什么，又依赖哪些信息、目标或假设。比较这些进展的联系，从中提炼仍存在的根本障碍。正文按论点展开，详细的逐篇比较放在 positioning。用 paper_claim_audits 区分作者主张、实际测试条件、结果与支持的结论。不要把一个数据集的结果写成整个领域的事实。
3. **问题只有两种来源。** unresolved_need 是已有重要问题仍未被现有主要方法解决：解释它们为什么仍跨不过关键障碍。emerging_problem 是现有方法的使用或发展会暴露新问题：解释什么做法、在什么条件下、为什么会引出这个问题，以及后果为何重要。它可以是我们合理推导的新问题，不必已经被论文观察到。矛盾、未检验假设、跨领域启发等帮助发现问题，但不是第三种来源。“某篇论文没测过”本身不构成研究理由。
4. **从问题的根本推出动机。** 面对这个困难，为什么现有主要路线的正常使用仍不够？完整考虑它们能获取的信息、探索和更新能力。然后说明需要理解什么或改变什么原则，才能推进用户的目标。先把这个研究需要讲清楚，再挑技术；去掉技术名字之后，动机仍应成立。未检索到不是普遍无解的证据，推理应落在可说明的条件和机制上。
5. **提出能作用于原因的 idea。** 先把所用信息说具体：涉及哪些对象，它们之间是什么关系，关系在什么条件下成立，依据从哪里来，怎样取得或核对。再讲清“准备做什么 → 相对原流程实际改变了哪项学习或判断要求 → 为什么有望获得目标能力 → 哪个关键假设连接这两者”。仅重排材料、并列展示而学习要求、反馈和操作约束未变，不能仅凭呈现方式宣称新机制。考虑一种能够完成表面任务却不具备目标能力的简单办法，说明当前设计为什么更指向所需关系、在信息或判断要求上怎样区别两者；不要只把它列成未来验证事项。用文字解释作用即可，不要求损失公式。追求有意义的新认识或新能力；不要用“挖掘关系、联合约束、促进迁移”等抽象表述、任意涨分或改名后的取舍代替贡献。问题可以聚焦，但不能为了方便实验而缩成一个与大目标联系很弱的细节。不要为保护喜欢的办法而制造限制。
6. **在构思时完成细节比较与基本可行性推演。** 相似标题和同类方法不能直接否定 idea；比较具体动机、问题、信息与核心贡献。已有技术可以借鉴，已有机制也不能因实验支持不足就变新。对真正重叠的贡献，利用文献改进问题认识或选择更有意义的切入点。推演所需信号是否可得、信息是否循环、谁能执行改变；把可预见的矛盾修掉。未做实验本身不是停止构思的理由。
7. **选择并讲透。** 在已有 map/propose 任务内比较方向，优先选研究理由、核心认识和可行路径最强的一个；不新增评分、审批或拒绝轮次。用研究同伴听得懂的话说明“为什么值得做、原来的办法卡在哪里、我们准备怎样改变”。让每一段推进这条解释，不反复换词重述研究目标。重要性来自问题影响的能力和实际后果，不能只靠“大问题”“解释原则”“实质贡献”等标签。

## Output

Return only the current task JSON. In map, save the cross-paper synthesis in research_frame (user_goal, literature_logic, research_question, scope_connection), then derive opportunities. Each opportunity has one problem_origin: unresolved_need or emerging_problem. opportunity_types lists the origins actually used. In propose, opportunity_id carries the chosen problem into the candidate, and selection_reason explains its research value.

Build motivation as a connected argument: background → existing_work → problem_observation and importance → causal_explanation and existing_approach_limit → research_need → why_this_method → expected_progress. In propose/develop/refine, express the specific objects, information and conditions in idea_core.concrete_target, and the operation-to-capability explanation in idea_core.capability_bridge; keep construction_path and essential_difference consistent with that explanation. These are part of the readable idea, not hidden reasoning. The first phase ends with an explainable core idea: what it uses, what changes and why that change addresses the problem are already clear. Phase two explores technical ways to realize that idea; it must not be left to invent its missing scientific rationale. In develop/refine, preserve this purpose while choosing technical references; a borrowed technique serves the problem rather than replacing it with its own benchmark. In review, use the existing motivation_assessment, issues and revision_instructions to improve a specific weak link.

依据论文的事实附 evidence_ids；basis 区分 source_observation 和 research_hypothesis。新原因可以直接说“我们怀疑”，新问题可以说“我们想弄清”，不必反复插入“所供材料”“尚未确认”等审计式表述。保持来源的真实范围，同时允许从具体证据提出更大的研究问题。重要条件放在它实际影响的判断里。

背景、问题、动机用连贯段落详细说明，不写成压缩摘要。先解释事情，再引入必要术语；让不了解源论文的人也能复述这条论证。不要附具体例子、实验计划或编造的参数。simplest_alternative、necessity_test 和 feasibility_sketch 只保留简短内部推敲。

## Weak-rationale handling

If the current rationale is weak, improve the problem or insight in the same task. More technical detail and stronger adjectives cannot repair an unimportant question. Do not hand the central difficulty to an unnamed reliable component or to a researcher who must first identify the correct relationships: explain how that prerequisite can be obtained, or revise the idea around information the setting provides. Distinguish a plausible proposed cause from a reported finding without turning ordinary research assumptions into rejection conditions. A useful proposal explains a meaningful purpose and an obtainable information path; it does not promise that experiments have succeeded or that a venue will accept it.
