---
name: research-idea-motivation
description: Derive consequential research problems from literature, choose them before constructing solutions, and carry that rationale into LLM/NLP ideas and technical design.
---

## Input and role

Use the supplied topic, user_notes, constraints, evidence and task schema. This skill guides reasoning; it is not scientific evidence. Work within the current task without tools or scripts.

The first phase develops alternatives before choosing one. **explore_problems opens different directions; deepen_problem gives each direction an independent, substantive argument; map compares those arguments and chooses; propose constructs an idea for that choice.** This is a division of thinking, not an extra review or approval. Think boldly about plausible new difficulties; do not limit ideas to repairs already suggested by source papers.

## Form the problem before the solution

Use discovery_plan and discovery_coverage to see which different approaches were actually explored. Read the supplied papers' selection questions and route provenance, but let full-text findings correct the planned routes. Compare the important problems these different lines expose; do not build every alternative around one favorite relation. Link opportunities through research_route_ids where applicable. These records guide synthesis without adding a score or a new review call.

把用户原目标与我们提出的研究聚焦分开。research_frame.user_goal 保留原始 topic，明确补充以 user_notes 为准；选中的能力写入 research_question，在 scope_connection 解释它为何推进原目标。不能先把候选能力说成用户需要，再用符合需要证明其重要性。按解决思路综合已有工作：它们依靠什么原理，已经帮助我们走到了哪里。阅读者为某篇论文预制的改法不是出发点；保留论文的方法、实际结果、条件和证据，用它们形成更大的认识。

**承接已有贡献，再提出下一步问题。** 在构思中按已有方法及其报告结果成立来推演：它已经解决什么，这件事成功之后还会产生什么重要困难，或接下来哪项重要需要超出了它原本解决的范围？不以否定原贡献、质疑实验归因或指出缺少消融来制造我们的 motivation。论文证据仍按实际条件准确引用；主张审计负责界定能说到哪里，不负责替选题制造“别人没做好”。新的问题可以大胆推测，但要解释它如何从已有进展中产生、为何影响下一步目标。

只沿两个角度引出问题：

- **emerging_problem**：已有办法靠什么解决了原问题，成功使用或继续发展又怎样改变条件、产生新的困难，为什么原有回应仍会留下它，以及它怎样影响下一步目标。
- **unresolved_need**：大背景需要什么进展，现有主要思路靠什么推进、已经做到了哪里，为什么这些有效回应之后仍会有妨碍目标的障碍，由此提出研究问题。

两条路线都可以是合理猜想。已知机制、条件变化、文献现象之间的联系可以启发尚未被报告的困难。用“我们推测，在……时，……因为……”把条件、过程和后果讲清一次，再向前展开；不要求先有实验，也不要求问题在自己的关键假设错误时仍然成立。basis 记录 source_observation 或 research_hypothesis，引用真实前提不会把新推断变成观察事实。

把已有回应、原因与意义连起来，再提出问题和动机：

1. **从有效回应向前推演。** 承接背景目标，先解释主要方法靠什么起作用、已经帮助我们做到了哪里。在有意义的使用或发展条件下，把它们的最强正常用法、动态改进和合理组合放进来，推演这些回应已经改变什么、为什么还可能留下或产生困难。若它已改变所猜的原因，就重新考虑改变之后的情况；不能只列完方法再说“不保证”“没显式考虑”，也不要求证明所有方法失败。
2. **从现象深入到有解释力的原因。** 为什么有效办法继续改进后，仍可能绕不过这个障碍？从其作用、信息、目标、反馈、依赖条件或发展后果中推演，而不是把“表现不好”换成“能力不足”。有价值的洞见应让人进一步理解困难怎样产生，并看出哪项认识或原则值得改变。可以是非显然的合理猜想，不固定为某种隐藏假设模板，不要求唯一根因，也不以“高洞见”标签代替推演。
3. **由后果说明问题为何重要。** 这段作用过程怎样妨碍原目标？如果跨过该障碍，什么重要事情会变得可做，或哪项认识会改变？困难重要和原因解释有深度应共同支撑优先研究的理由。不能从“还可能有没用好的信息”直接跳到关键障碍，也不以背景宏大代替它对具体目标的影响。
4. **据此提出问题和动机。** 在上述过渡之后，简明点出究竟要研究什么，再说明需要理解什么关系、获得什么能力或改变什么原则。动机在没有算法名时仍应说得通。不要先宣布“仍需解决的困难是”，到后文才解释现有方法为什么留下它；过渡不成立时改进问题认识，而非靠增加技术细节补洞。

一篇论文也能启发重要问题，不规定来源数量或共同缺陷。由某类方法带来的新问题可以依赖这类方法，不要求换掉它后问题仍存在。相似主题不代表问题已经解决；作者 claim 要结合实际方法与证据理解。

## Choose, then construct

**In explore_problems:** 先整理 approach_landscape，再从原目标和已有进展探索通常三个、最多四个不同的重要问题。用户明确聚焦时就在其范围内探索，不凑数量。每个 problem_seed 的 entry_reason 从已有方法的作用或发展变化引出疑问，说明它怎样影响原目标、哪里值得深入理解；此时不排序、不选解法。不同方向要有自己的研究价值，不能把偏爱的问题、它的一个副作用和一个容易否定的小修补写成三个选项。成本也能是重要问题，但应说明它限制了什么实质能力，而不只说更便宜。

**In deepen_problem:** 本次只深入指定的 problem_seed。先在 prior_art_delta 保存主要方法的深入回应分析，再由 bottleneck_hypothesis 推演有解释力的原因；derivation 接着解释其后果怎样妨碍背景目标，自然引出问题，不重写方法综述或先宣布困难后补理由。why_it_matters 解释跨过障碍会带来的实质进展，research_need 据此引出研究动机。各字段共同组成“已有进展及作用条件 → 为什么仍产生障碍 → 如何影响原目标”的论证。哪怕这个方向后来不被选中，也应有独立深入的推导；不预设另一个方向更好，不进入技术方案，不凭实现容易程度选择问题。

**In map:** 接收已经独立展开的 problem_cases，比较每个问题的研究价值和原因解释带来的新认识。problem_comparisons 为每项记录 strongest_case、remaining_obstacle、priority_reason：跨过它能带来什么进展、有效回应之后为什么仍有障碍，以及和其他问题相比为什么应优先或随后研究。不能只把 remaining_obstacle 写成困难名称，也不只选影响很大但原因空泛的问题。回应其他方向真正有力的理由；若认为某问题是前提，解释解决它怎样帮助其他方向、其他方向为何不能独立先推进，而不只说“更基础”。最后写 selected_problems（opportunity_id、selection_reason），最多 max_candidates 个，通常一个；原样保留各 case 的论证。选择的是有深入解释的问题价值，不是技术是否好写。不要求打分、证明全领域最重要或否定未选方向。

**In propose:** draft 和 complete 都以 argument_handoff 及所选机会的完整论证为起点，承接主要方法的回应、原因洞见、目标影响和研究需要，不只拿困难名称重写问题。内部草案可指出缺失的具体方法近邻，由控制器按 comparison_search 定向检索阅读；补充后把新方法的真实能力纳入原有回应，同步修订 existing_work、existing_approach_limit、causal_explanation 及后续推导。不是每个想法都加一轮审查，也不从论文标题作覆盖判断。新证据可以深化或修正原问题的解释；我们拟采用方案的信息获取、估计误差等实现难点先进入 idea_core，不无声替代原问题。若它确实是已有方法发展中影响原目标的新问题，说明这一来源及调整重点的理由。

接收已经保存的选择，继承理由；本次选择解决办法。先从所需进展与障碍推导操作应起什么作用，再考虑利用什么可获得的信息、采用什么思路。idea_core 展开对象、获取路径、作用与能力的连接、同最近工作的实质区别。路径行不通时换办法，不悄悄把问题改成某种技术容易完成的小任务。基本可行性在这里推演，第二阶段再探索技术参考；不要求详细工程或实验。

**In develop/refine/review:** selected_opportunity 保存最初问题、推导、研究需要和选择理由；旧快照可能缺字段。可以因新的认识调整问题，同步解释原因并更新动机、核心想法与贡献。不能为了借用某个技术而无声缩小目标，也不因快照存在而强迫恢复一个已经有理由修正的判断。

## Explain the resulting argument

Background → Existing methods → Possible problem → Motivation → Idea 是一条前向论证。背景解释现实需要；existing_work 先讲主要做法、作用与进展，再提代表论文。问题部分按 existing_approach_limit → causal_explanation → problem_derivation → problem_observation → importance 展开：先承接主要方法在当前需要下已有效回应什么、靠什么起作用及其条件，再深入解释为何仍会产生障碍，把其后果连回背景目标，然后简明点出研究问题及跨过它的价值。各段推进一步，不各自重写整条链。research_need 据此说明需要改变什么、为何针对该原因、成功会带来什么，idea 再直接回应这个需要。读者应在看到解决办法之前理解选题的必要性。

像向研究同伴解释为什么觉得这件事值得做：详细、平实，每段推进一步，必要术语先解释再命名。不要用篇幅、抽象名词或重复强调重要性代替过渡。第一阶段不写具体例子、实验计划或退路声明。大胆提出有理由的想法，缺少实测不是停止构思的理由；输出遵守当前任务 JSON，不新增评分、审批或额外审查。

把背景、现有方法、问题和动机直接写成读者能理解的正文，不留给报告再翻译。每段展开过程和因果联系，不能靠“表示、关系、机制、泛化”等词代替说明。原目标与起步实现保持区别：难获取的信息应促使我们设计取得和利用它的办法，不把研究问题偷偷换成只处理已经容易取得信息的情形。

explore_problems 整理的 approach_landscape 会传给每次问题深入和比较：按解决背景目标的原理归纳主要角度，代表论文只是各类的实例。可利用综述、系统比较及已读论文的引言/相关工作理解领域，不把引用到的原作伪装成自己已读。类别可以由多个来源共同支撑，一篇综述也可说明多个类别；不把当前精读列表等同于领域全貌。让这些主要思路参与问题推导与对照，existing_work 也按类别解释做法和作用。
