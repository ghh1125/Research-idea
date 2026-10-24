---
name: research-idea-motivation
description: Synthesize literature into an important unresolved or emerging research problem, derive its motivation and form a meaningful idea. Use during problem mapping, proposal, development, refinement or review for LLM/NLP research.
---

## Input

Use the supplied topic, user_notes, constraints, evidence and current task schema. This skill guides reasoning; it is not scientific evidence. Work within the current task, without calling tools or executing scripts.

## Steps

先大胆拓展猜想，再把推导想深。文献帮助发现原因、条件和新切口，不用于在构思时预先淘汰所有有风险的想法；不要因预想的反对而只留下安全的小改动。

1. **回到用户的大课题。** 先说用户希望解决什么、为什么需要解决。不要为了适配一个方便实现的方法，提前把用户的目标定义成该方法想改善的局部能力。具体问题可以聚焦一个重要障碍；论文里的数据集和任务设置是依据，不自动成为研究目标。用户明确限定范围时遵循该范围。
2. **先理解已有思路怎样帮助实现目标。** 按机制梳理论文：使用什么信息、做什么改变、已经带来什么进展、依赖什么条件。正文按论点展开，详细逐篇比较放在 positioning。用 paper_claim_audits 区分作者解释、测试条件、结果与支持的结论。单篇结果可以启发更大的问题，但不是整个领域的事实。此时先不选择我们的方法。
3. **从线索推演问题，允许有根据的猜想。** 问题只走两条路线：unresolved_need 是“背景需要 → 已有进展 → 在什么条件下仍存在或可能出现关键障碍 → 为什么妨碍目标”；emerging_problem 是“方法的使用或发展 → 新困难怎样产生或可能产生 → 影响什么 → 原有思路为什么难以处理”。从共同依赖的前提、相互矛盾的发现、使用方式或规模变化中找线索，再顺着已知工作机制推演困难如何出现。derivation 写清已知前提、现实条件、关键推断和重要后果；问题本身也可以是推测，无需论文已经展示过失败。条件应来自研究需要，不是为了排除已有方法而添加。
4. **让已有方法认真回应同一个困难，再形成动机。** 在 prior_art_delta 中，先说明最接近方法在上述同样条件下会如何正常应对，包括已经具备的更新、探索或信息获取；再说明为什么我们仍有理由认为困难可能保留。具体的机制推论足以支持新问题，不要求证明所有方法必然失败；理论上能表示目标能力也不等于实际已经解决。仅“没采用我们的操作”“没有保证”“没测过”不足以解释障碍。从这段分析推出 research_need：需要重新理解什么关系或改变什么原则，为什么这会推进背景目标？再由 insight 提出应对原因的认识。不要直接从文献列表跳到“因此加入一个模块”。
5. **提出能作用于原因的 idea。** 先把所用信息说具体：涉及哪些对象，它们之间是什么关系，关系在什么条件下成立，依据从哪里来，怎样取得或核对。再讲清“准备做什么 → 相对原流程实际改变了哪项学习或判断要求 → 为什么有望获得目标能力 → 哪个关键假设连接这两者”。仅重排材料、并列展示而学习要求、反馈和操作约束未变，不能仅凭呈现方式宣称新机制。考虑一种能够完成表面任务却不具备目标能力的简单办法，说明当前设计为什么更指向所需关系、在信息或判断要求上怎样区别两者；不要只把它列成未来验证事项。用文字解释作用即可，不要求损失公式。追求有意义的新认识或新能力；不要用“挖掘关系、联合约束、促进迁移”等抽象表述、任意涨分或改名后的取舍代替贡献。问题可以聚焦，但不能为了方便实验而缩成一个与大目标联系很弱的细节。不要为保护喜欢的办法而制造限制。
6. **在构思时完成细节比较与基本可行性推演。** 相似标题和同类方法不能直接否定 idea；比较具体动机、问题、信息与核心贡献。已有技术可以借鉴，已有机制也不能因实验支持不足就变新。对真正重叠的贡献，利用文献改进问题认识或选择更有意义的切入点。推演所需信号是否可得、信息是否循环、谁能执行改变；把可预见的矛盾修掉。未做实验本身不是停止构思的理由。
7. **两次调用各有重点。** map 先比较问题推导、可能原因、重要后果与应改变的原则，feasibility_basis 只推演可观察/可改变的内容和基本信息途径；具体构造与能力连接放到 propose.idea_core。selection_reason 优先解释为什么这个问题值得深入。问题价值、原理上的启发和可着手性共同决定选择，不因熟悉的小操作容易实现就倒推必要性。固定的模块数量、分数或附加审查不能替代推理。用同伴听得懂的话讲明转折，不靠标题或重复重要性。

## Output

Return only the current task JSON. In map, research_frame connects the user's need, existing progress and a consequential obstacle; opportunities.derivation derives each focused problem before its insight proposes an approach. Each opportunity has one problem_origin: unresolved_need or emerging_problem, and opportunity_types lists the origins actually used. In propose, opportunity_id identifies the chosen problem, motivation.problem_origin matches that opportunity, and selection_reason explains why its obstacle deserves priority. motivation.problem_derivation is one connected paragraph showing why the background and existing progress lead to this specific problem; problem_observation states the resulting difficulty, and research_need explains what overcoming that same difficulty requires. Keep these roles distinct instead of repeating the background in every field.

Build one argument: background → how existing approaches help → clues and meaningful conditions → observed or inferred difficulty and consequence → possible cause and existing response → research_need → core idea. In propose/develop/refine, explain the idea through concrete_target, construction_path, capability_bridge and essential_difference. Phase two explores supporting techniques. Read selected_opportunity alongside the current rationale: its basis and prior_art_delta retain the inferred/observed distinction and the strongest existing response, not just the question. Older snapshots may lack those two fields. A justified reframing is allowed: explain it in problem_derivation and update problem_origin, basis, the problem, research_need and idea_core together; in refine also explain the change in review_responses. Do not revert a reasoned revision just to match the snapshot. Use the existing review task to improve a weak inference or transition.

依据论文的事实附 evidence_ids；basis 区分来源已报告的困难与我们推演的困难。引用了前提仍可为 research_hypothesis，不会自动变成 source_observation。已观察现象的原因也可以是假设；现象本身不直接证实原因。对于推演的新问题，判断“推断为什么合理，如果成立为什么重要”，不要要求它在关键假设不成立时仍然存在。用“我们推测，在……时，……因为……”自然交代一次，随后展开动机和想法；不反复插入“尚未确认”等审计式表述。

背景、问题、动机用连贯段落详细说明，不写成压缩摘要。先解释事情，再引入必要术语；让不了解源论文的人也能复述这条论证。不要附具体例子、实验计划或编造的参数。simplest_alternative、necessity_test 和 feasibility_sketch 只保留简短内部推敲。

## Weak-rationale handling

If the current rationale is weak, improve the problem or insight in the same task. More technical detail and stronger adjectives cannot repair an unimportant question. Do not hand the central difficulty to an unnamed reliable component or to a researcher who must first identify the correct relationships: explain how that prerequisite can be obtained, or revise the idea around information the setting provides. Distinguish a plausible proposed cause from a reported finding without turning ordinary research assumptions into rejection conditions. A useful proposal explains a meaningful purpose and an obtainable information path; it does not promise that experiments have succeeded or that a venue will accept it.
