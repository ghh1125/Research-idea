---
name: research-idea-motivation
description: Synthesize literature into an important unresolved or emerging research problem, derive its motivation and form a meaningful idea. Use during problem mapping, proposal, development, refinement or review for LLM/NLP research.
---

## Input

Use the supplied topic, user_notes, constraints, evidence and current task schema. This skill guides reasoning; it is not scientific evidence. Work within the current task, without calling tools or executing scripts.

## Steps

1. **回到用户的大课题。** 先说用户希望解决什么、为什么需要解决。不要为了适配一个方便实现的方法，提前把用户的目标定义成该方法想改善的局部能力。具体问题可以聚焦一个重要障碍；论文里的数据集和任务设置是依据，不自动成为研究目标。用户明确限定范围时遵循该范围。
2. **把论文梳理成大逻辑。** 按解决思路理解已有工作：它们试图改变什么，已经让我们做到了什么，又依赖哪些信息、目标或假设。比较这些进展的联系，从中提炼仍存在的根本障碍。正文按论点展开，详细的逐篇比较放在 positioning。用 paper_claim_audits 区分作者主张、实际测试条件、结果与支持的结论。不要把一个数据集的结果写成整个领域的事实。
3. **沿两条路线推导问题。** unresolved_need 从已有重要需要出发，经过现有主要路线的进展，说明在什么实际条件下仍留下什么能力障碍、为什么正常使用还跨不过去。emerging_problem 从已有方法的一项使用、扩展或发展出发，说明这项变化怎样造成或暴露新困难，以及它为什么重要。derivation 先确定独立于拟议方法的问题，再由 insight 提出应对原因的认识。“不保证做到”“没有采用我们的操作”“没有测过”均不能代替这条推导。两条路线都允许有理由的新问题，不要求先有实验；文献矛盾和跨领域启发是线索，不是第三种来源。
4. **从同一个障碍推出动机。** 研究需要回答的是：为了跨过刚才的障碍，必须理解什么关系、改变什么原则或获得什么能力，才会推进背景目标？完整考虑现有方法正常获取信息、探索和更新的能力。research_need 承接推导出的同一困难，不悄悄换题，也不把增加喜欢的操作当成动机。若现有正常用法已经足够，就重新推导重要问题；解释研究也需要具体且有意义的未知关系，不能当作保留原方法的退路。
5. **提出能作用于原因的 idea。** 先把所用信息说具体：涉及哪些对象，它们之间是什么关系，关系在什么条件下成立，依据从哪里来，怎样取得或核对。再讲清“准备做什么 → 相对原流程实际改变了哪项学习或判断要求 → 为什么有望获得目标能力 → 哪个关键假设连接这两者”。仅重排材料、并列展示而学习要求、反馈和操作约束未变，不能仅凭呈现方式宣称新机制。考虑一种能够完成表面任务却不具备目标能力的简单办法，说明当前设计为什么更指向所需关系、在信息或判断要求上怎样区别两者；不要只把它列成未来验证事项。用文字解释作用即可，不要求损失公式。追求有意义的新认识或新能力；不要用“挖掘关系、联合约束、促进迁移”等抽象表述、任意涨分或改名后的取舍代替贡献。问题可以聚焦，但不能为了方便实验而缩成一个与大目标联系很弱的细节。不要为保护喜欢的办法而制造限制。
6. **在构思时完成细节比较与基本可行性推演。** 相似标题和同类方法不能直接否定 idea；比较具体动机、问题、信息与核心贡献。已有技术可以借鉴，已有机制也不能因实验支持不足就变新。对真正重叠的贡献，利用文献改进问题认识或选择更有意义的切入点。推演所需信号是否可得、信息是否循环、谁能执行改变；把可预见的矛盾修掉。未做实验本身不是停止构思的理由。
7. **先选值得解决的障碍，再落实办法。** 在已有 map/propose 任务内，selection_reason 先说明为什么优先研究这项具体障碍、它怎样影响用户目标，再说明洞见和可行路径怎样帮助着手。信息容易取得、技术容易实现或操作看起来新鲜不能反过来替问题制造必要性。不新增评分、审批或拒绝轮次。用研究同伴听得懂的话讲清“为什么值得做、已有办法卡在哪里、我们准备怎样改变”，让每段推进解释，不靠大标题或反复陈述重要性。

## Output

Return only the current task JSON. In map, research_frame connects the user's need, existing progress and a consequential obstacle; opportunities.derivation derives each focused problem before its insight proposes an approach. Each opportunity has one problem_origin: unresolved_need or emerging_problem, and opportunity_types lists the origins actually used. In propose, opportunity_id identifies the chosen problem, motivation.problem_origin matches that opportunity, and selection_reason explains why its obstacle deserves priority. motivation.problem_derivation is one connected paragraph showing why the background and existing progress lead to this specific problem; problem_observation states the resulting difficulty, and research_need explains what overcoming that same difficulty requires. Keep these roles distinct instead of repeating the background in every field.

Build one argument: background → existing_work → problem_derivation → problem_observation and importance → causal_explanation and existing_approach_limit → research_need → why_this_method → expected_progress. In propose/develop/refine, express the objects, information and conditions in idea_core.concrete_target, and the operation-to-capability explanation in capability_bridge; keep construction_path and essential_difference consistent. Phase one delivers this explainable core idea; phase two explores supporting technical routes. In develop/refine/review, read the selected_opportunity snapshot alongside the current rationale. A justified reframing is allowed: explain it in problem_derivation and update problem_origin, the problem, research_need and idea_core together; in refine also explain the change in review_responses. Preserve a reasoned revision rather than automatically reverting to the snapshot. In review, use the existing motivation_assessment, issues and revision_instructions to repair the actual weak link, without adding a task.

依据论文的事实附 evidence_ids；basis 区分 source_observation 和 research_hypothesis。新原因可以直接说“我们怀疑”，新问题可以说“我们想弄清”，不必反复插入“所供材料”“尚未确认”等审计式表述。保持来源的真实范围，同时允许从具体证据提出更大的研究问题。重要条件放在它实际影响的判断里。

背景、问题、动机用连贯段落详细说明，不写成压缩摘要。先解释事情，再引入必要术语；让不了解源论文的人也能复述这条论证。不要附具体例子、实验计划或编造的参数。simplest_alternative、necessity_test 和 feasibility_sketch 只保留简短内部推敲。

## Weak-rationale handling

If the current rationale is weak, improve the problem or insight in the same task. More technical detail and stronger adjectives cannot repair an unimportant question. Do not hand the central difficulty to an unnamed reliable component or to a researcher who must first identify the correct relationships: explain how that prerequisite can be obtained, or revise the idea around information the setting provides. Distinguish a plausible proposed cause from a reported finding without turning ordinary research assumptions into rejection conditions. A useful proposal explains a meaningful purpose and an obtainable information path; it does not promise that experiments have succeeded or that a venue will accept it.
