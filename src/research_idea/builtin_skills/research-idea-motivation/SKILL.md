---
name: research-idea-motivation
description: Synthesize source analyses into consequential research problems and motivations before proposing an idea. Use during problem mapping, proposal, development, refinement or review for LLM/NLP research.
---

## Input

Use the supplied topic, user_notes, constraints, evidence and task schema. This skill guides reasoning; it is not scientific evidence. Work within the current task without tools or scripts.

## Procedure

先大胆提出猜想，再借文献把推导想深。不要因预想的审稿反对只留下安全的小改动，也不要把一篇论文已经写好的改进方向当作用户要研究的问题。

1. **先问什么进展真正值得追求。** 从用户的大背景说明希望模型或研究者多做到什么、理解什么，以及为什么重要。尊重用户主动限定的范围；具体问题可以聚焦，研究理由仍须连接到原目标。不要把目标提前改写成某篇论文的指标或操作。
2. **综合已有思路。** 按解决思路说明已有工作推进了目标的哪一部分、依靠什么原理、适用于什么条件。用 paper_claim_audits 区分作者解释与实际结论，不把不同设置的结果当作直接比较。第一阶段暂不带入论文卡里预制的改法、idea_relevance 和实验建议，但保留方法、结果、疑点与原文。论文是形成认识的材料，不是逐篇修补的清单。一篇论文也能启发大问题，不规定论文数量或共同缺陷。
3. **只沿两个角度提出问题。** emerging_problem：已有方法解决原问题，但解决、使用或发展过程又产生重要的新困难。unresolved_need：从大背景提出一个重要的新问题，现有主要思路跨不过其中的关键障碍。沿“线索 → 有意义的条件或变化 → 困难如何产生 → 对目标的影响”推演。问题和原因都可以是猜想，不必先有失败观察或实验。bottleneck_hypothesis 解释根本关系或过程，不写成缺少我们想加的模块。
4. **分清关键障碍和实现中的小缺点。** 即使源论文按设计正常工作，我们真正想追求的进展是什么，还有什么困难？若新困难恰由某类方法的成功使用产生，讲明依赖及重要后果，不要求它脱离这类方法仍然存在。why_it_matters 连接“跨过障碍 → 获得重要能力或认识 → 推进原目标”。局部改动可以服务大问题，但仅修补操作或重新平衡取舍，不能靠宏大措辞成为重要问题。问题过小时回到背景重新头脑风暴，不增加门禁或风险清单。
5. **从原因推出动机。** prior_art_delta 认真考虑已有主要思路对同一问题的正常回应，包括更新、探索和信息获取，再解释为什么关键障碍可能仍在。不是挑最容易批评的一篇；理论表达能力不等于实际已解决，相似主题也不等于贡献重合。research_need 由原因推出需要理解什么关系、实现什么能力或改变什么原则，以及为什么有必要。此时不指定组件、算法或实施路径。
6. **在 propose 才构思想法。** 先比较问题与动机，selection_reason 说明为何所选障碍更重要、原因猜想更有启发；再从该 research_need 大胆构思能作用于原因的 idea。用 idea_core 解释作用对象、信息来源、核心改变与能力之间的连接、同最接近工作的实质关系。基本可行性在这里推演，不能依赖隐藏答案、循环监督或未定义的可靠组件。方法可以简单、可以借鉴其他领域，问题不会因此缩成对某个组件的修补。
7. **把问题与动机带到后续。** map 输出问题、原因猜想、研究意义、已有回应和研究需要；不再提前填方法洞见或实现路径。propose 形成核心 idea，第二阶段再探索技术参考。后续可以合理调整问题，但要一起更新原因、动机和贡献，说明理由。避免越做越像修补借来的方法。沿用现有调用，不加评分、审批、审查轮次或实验要求。

## Output

Return only the current task JSON. In map, research_frame connects the user goal, literature logic and consequential questions. Each opportunity has question, problem_origin, basis, derivation, bottleneck_hypothesis, why_it_matters, prior_art_delta, research_need and real source IDs. opportunity_types lists the two origins actually used. Different opportunities should differ in the problem or explanation, not just name different interventions. Leave selection to propose.

In propose, opportunity_id identifies the chosen problem and motivation.problem_origin matches it. Carry its research_need and connection to the broader goal into the argument. problem_observation first states in one or two plain sentences what cannot be done or would go wrong; then explain the cause. The reader should understand the problem without first learning the proposed technology. motivation.research_need develops the selected motivation, while why_this_method and idea_core explain the resulting idea. A larger slogan does not replace the missing causal link.

Build one argument: background → existing progress → consequential problem → possible cause and existing response → research_need → idea. selected_opportunity preserves the starting derivation, basis, why_it_matters, bottleneck_hypothesis, prior_art_delta and research_need; older snapshots may lack fields. Compare it with the current rationale. Reasoned reframing is allowed: update the problem, origin, basis, motivation and core idea together, explaining the change in review_responses when refining.

basis 区分来源报告的困难和我们推演的新困难。引用真实前提仍可以是 research_hypothesis，不会自动变成 source_observation。已观察现象的原因也可以是假设。对于推测的新问题，问“推断为什么合理，如果成立为什么重要”，不要求它在关键假设错误时仍然存在。用“我们推测，在……时，……因为……”自然交代一次，后面展开动机与想法，不堆叠免责声明。

表达像和研究同伴讨论：详细、平实地解释事情，先说明谁遇到了什么困难，再解释原因与思路；必要术语先解释后命名。每段推进一个环节，避免压缩摘要、抽象名词堆砌和重复重要性。第一阶段不给具体例子或实验计划；feasibility_sketch、simplest_alternative 与 necessity_test 只保留简短内部推敲。

## Improving a weak rationale

If a question only repairs one source's operation, return to the user's goal and ask what consequential problem the source helps reveal. Improve the question within the same task instead of adding technical detail or stronger adjectives. Consider the strongest normal existing responses without weakening them. Related methods are useful building blocks; the contribution may be a new capability, relation or explanation. Explain what makes it meaningful and how the idea could work. Missing experiments and a reasoned uncertain hypothesis are normal at this stage, not reasons to stop brainstorming.
