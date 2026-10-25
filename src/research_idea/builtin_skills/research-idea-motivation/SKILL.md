---
name: research-idea-motivation
description: Derive consequential research problems from literature, choose them before constructing solutions, and carry that rationale into LLM/NLP ideas and technical design.
---

## Input and role

Use the supplied topic, user_notes, constraints, evidence and task schema. This skill guides reasoning; it is not scientific evidence. Work within the current task without tools or scripts.

The first phase develops alternatives before choosing one. **explore_problems opens different directions; deepen_problem gives each direction an independent, substantive argument; map compares those arguments and chooses; propose constructs an idea and communicates the resulting argument.** Preserve depth in problem_cases; use propose to select and explain the decisive reasoning rather than repeat the whole analysis. Think boldly about plausible new difficulties, beyond repairs already suggested by source papers.

## Form the problem before the solution

Use discovery_plan and discovery_coverage to see which different approaches were actually explored. Read the supplied papers' selection questions and route provenance, but let full-text findings correct the planned routes. Compare the important problems these different lines expose; do not build every alternative around one favorite relation. Link opportunities through research_route_ids where applicable. These records guide synthesis without adding a score or a new review call.

把用户原目标与我们提出的研究聚焦分开。research_frame.user_goal 保留原始 topic，明确补充以 user_notes 为准；选中的能力写入 research_question，在 scope_connection 解释它为何推进原目标。不能先把候选能力说成用户需要，再用符合需要证明其重要性。按解决思路综合已有工作：它们依靠什么原理，已经帮助我们走到了哪里。阅读者为某篇论文预制的改法不是出发点；保留论文的方法、实际结果、条件和证据，用它们形成更大的认识。

**承接已有贡献，再提出下一步问题。** 在构思中按已有方法及其报告结果成立来推演：它已经解决什么，这件事成功之后还会产生什么重要困难，或接下来哪项重要需要超出了它原本解决的范围？不以否定原贡献、质疑实验归因或指出缺少消融来制造我们的 motivation。论文证据仍按实际条件准确引用；主张审计负责界定能说到哪里，不负责替选题制造“别人没做好”。新的问题可以大胆推测，但要解释它如何从已有进展中产生、为何影响下一步目标。

只沿两个角度引出问题：

- **emerging_problem**：已有办法靠什么解决了原问题，成功使用或继续发展又怎样改变条件、产生新的困难，为什么原有回应仍会留下它，以及它怎样影响下一步目标。
- **unresolved_need**：大背景需要什么进展，现有主要思路靠什么推进、已经做到了哪里，为什么这些有效回应之后仍会有妨碍目标的障碍，由此提出研究问题。

两条路线都可以是合理猜想。已知机制、条件变化、文献现象之间的联系可以启发尚未被报告的困难。用“我们推测，在……时，……因为……”把条件、过程和后果讲清一次，再向前展开；不要求先有实验，也不要求问题在自己的关键假设错误时仍然成立。basis 记录 source_observation 或 research_hypothesis，引用真实前提不会把新推断变成观察事实。

形成 problem_cases 时，把已有回应、原因与意义深入连起来，再提出问题和动机；这是选题论证的思考过程，不是让 propose 把每项推敲复述成文：

1. **从有效回应向前推演。** 承接背景目标，先解释主要方法靠什么起作用、已经帮助我们做到了哪里。在有意义的使用或发展条件下，把它们的最强正常用法、动态改进和合理组合放进来，推演这些回应已经改变什么、为什么还可能留下或产生困难。若它已改变所猜的原因，就重新考虑改变之后的情况；不能只列完方法再说“不保证”“没显式考虑”，也不要求证明所有方法失败。
2. **从现象深入到有解释力的原因。** 为什么有效办法继续改进后，仍可能绕不过这个障碍？从其作用、信息、目标、反馈、依赖条件或发展后果中推演，而不是把“表现不好”换成“能力不足”。有价值的洞见应让人进一步理解困难怎样产生，并看出哪项认识或原则值得改变。可以是非显然的合理猜想，不固定为某种隐藏假设模板，不要求唯一根因，也不以“高洞见”标签代替推演。
3. **由后果说明问题为何重要。** 这段作用过程怎样妨碍原目标？如果跨过该障碍，什么重要事情会变得可做，或哪项认识会改变？困难重要和原因解释有深度应共同支撑优先研究的理由。不能从“还可能有没用好的信息”直接跳到关键障碍，也不以背景宏大代替它对具体目标的影响。
4. **据此提出问题和动机。** 在上述过渡之后，简明点出究竟要研究什么，再说明需要理解什么关系、获得什么能力或改变什么原则。动机在没有算法名时仍应说得通。不要先宣布“仍需解决的困难是”，到后文才解释现有方法为什么留下它；过渡不成立时改进问题认识，而非靠增加技术细节补洞。

一篇论文也能启发重要问题，不规定来源数量或共同缺陷。由某类方法带来的新问题可以依赖这类方法，不要求换掉它后问题仍存在。相似主题不代表问题已经解决；作者 claim 要结合实际方法与证据理解。

## Choose, then construct

**In explore_problems:** 先整理 approach_landscape，再从原目标和已有进展探索通常三个、最多四个不同的重要问题。用户明确聚焦时就在其范围内探索，不凑数量。question 用一句容易复述的短问题点明困难，条件与解释留在正文。每个 problem_seed 的 entry_reason 从已有方法的作用或发展变化引出疑问，说明它怎样影响原目标、哪里值得深入理解；此时不排序、不选解法。不同方向要有自己的研究价值，不能把偏爱的问题、它的一个副作用和一个容易否定的小修补写成三个选项。成本也能是重要问题，但应说明它限制了什么实质能力，而不只说更便宜。

**In deepen_problem:** 先以 response_analysis 给出主要方法的有效回应及其后果：它正常运行、合理适应之后已经解决了什么，剩余困难在什么条件下怎样影响目标，为什么这不是原方法的正常有益效果。过程改变并不等于问题产生；保留不同思路的实际作用，不能把原先风险原封不动放到回应之后。若已有回应解决了最初问题，就接着它的进展重新提出更有意义的问题，不靠否定论文贡献保留切口。这是研究判断摘要，辅助深入思考，不是新评分表或实验要求。

本次只深入指定的 problem_seed。先在 prior_art_delta 保存主要方法的深入回应分析，再由 bottleneck_hypothesis 推演有解释力的原因；derivation 接着解释其后果怎样妨碍背景目标，自然引出问题，不重写方法综述或先宣布困难后补理由。why_it_matters 解释跨过障碍会带来的实质进展，research_need 据此引出研究动机。各字段共同组成“已有进展及作用条件 → 为什么仍产生障碍 → 如何影响原目标”的论证。哪怕这个方向后来不被选中，也应有独立深入的推导；不预设另一个方向更好，不进入技术方案，不凭实现容易程度选择问题。

**In map:** 接收已经独立展开的 problem_cases，比较每个问题的研究价值和原因解释带来的新认识。problem_comparisons 为每项记录 strongest_case、remaining_obstacle、priority_reason：跨过它能带来什么进展、有效回应之后为什么仍有障碍，以及和其他问题相比为什么应优先或随后研究。不能只把 remaining_obstacle 写成困难名称，也不只选影响很大但原因空泛的问题。回应其他方向真正有力的理由；若认为某问题是前提，解释解决它怎样帮助其他方向、其他方向为何不能独立先推进，而不只说“更基础”。最后写 selected_problems（opportunity_id、selection_reason），最多 max_candidates 个，通常一个；原样保留各 case 的论证。选择的是有深入解释的问题价值，不是技术是否好写。不要求打分、证明全领域最重要或否定未选方向。

**In propose:** draft 和 complete 以 argument_handoff 及所选机会的完整论证为起点，提炼最能讲清问题、原因和价值的内容。先决定解决办法应起什么作用，再构思可获得的信息和可行操作。内部草案可以请求具体方法近邻或信息取得过程的定向阅读；complete 将新读到的方法能力融入当前论点，直接讲现在的认识，修订过程不充当正文。新证据可以修正问题解释；方案自身的信息获取、估计误差问题在 idea_core 内设计，不无声替代原研究问题。

idea_core 的主文解释对象、取得路径的关键操作、如何产生所需能力、与最近工作的实质差别。详细取得、核对和误差处理保存在 information_path，主文只解释决定想法能否工作的主干。路径困难时调整办法，保留原研究价值。第一阶段把基本可行性想通，第二阶段再探索技术参考。

**In develop/refine/review:** selected_opportunity 保存最初问题、推导、研究需要和选择理由；旧快照可能缺字段。可以因新的认识调整问题，同步解释原因并更新动机、核心想法与贡献。不能为了借用某个技术而无声缩小目标，也不因快照存在而强迫恢复一个已经有理由修正的判断。

## Explain the resulting argument

先让读者抓住问题和想法：problem_observation 通常用一两句说清谁想完成什么、哪里做不到；why_this_method 通常用两三句普通话说明拿什么输入、做什么改变、希望得到什么。它们是开头的简明回答，后面的五部分再解释理由。

Background → Existing methods → Problem → Motivation → Idea 各有成文职责：

- background 讲大背景和现实需要，研究聚焦由后文推导。existing_work 按方法大类写两三个短段，先讲做法与作用，再给代表论文。保留会影响问题判断的条件和结果，模型规模、基准名称与逐项成绩留在论文分析中。
- Problem 的 existing_approach_limit 讲最接近方法怎样作用后仍留下什么；causal_explanation 解释不显然的具体原因；problem_derivation 接着讲这个后果为什么卡住原目标。直接说谁在什么条件下会遗漏什么、做不到什么、带来什么后果，不用抽象提问让读者补全关键推理。各用一个短段推进一步，详细程度随实际过程调整，不各自复述整条论证。
- research_need 直接说明因此需要改变或弄清什么、为什么必要。动机接上原因，idea 接上这一需要。
- Idea 的 concrete_target、construction_path、capability_bridge、essential_difference 通常各一个短段，只讲关键对象、实际操作、作用过程和实质差别。主文保留核对依靠的额外可观察依据、判断怎样改变处理，以及新增操作为什么能触及原流程遗漏的东西；让模型再次检查本身不能解释改善从何而来。信息取得的详细核对与误差处理进入 information_path，供报告详情查看，不在主文逐项复制。

像向研究同伴解释一个想法：谁在做什么、怎样产生后果、为什么值得改变。先讲实际过程，再命名必要术语；抽象词不能独自承担解释。概览概括想法，后文增加原因和具体作用，不在各段重新列同一套区别。详细来自关键步骤讲透，不来自重复内部分析。importance、expected_progress、贡献对照与可行性等结构字段继续完整保存，正文不承担所有细节。大胆提出有理由的猜想；输出使用现有 JSON，第一阶段不展开具体例子、工程规格或实验计划。

explore_problems 整理的 approach_landscape 会传给每次问题深入和比较：按解决背景目标的原理归纳主要角度，代表论文只是各类的实例。可利用综述、系统比较及已读论文的引言/相关工作理解领域，不把引用到的原作伪装成自己已读。类别可以由多个来源共同支撑，一篇综述也可说明多个类别；不把当前精读列表等同于领域全貌。让这些主要思路参与问题推导与对照，existing_work 也按类别解释做法和作用。

## Discuss the problem with the researcher

在交互 CLI 中，map 后暂停。discuss_problem 根据用户反馈解释或修改问题，不提前设计方案。保留其他候选的原论证，并说明重点为何改变。追问不是同意，助手建议不是用户决定。当前问题的版本、完整原始对话、带用户消息出处的现行要点分别保存。只有 /continue 后才进入 propose；后续使用确认版本及现行要点，不能重新选题把纠正挤掉。确认的是研究方向，可以大胆提出原因猜想，并不声称其科学结论已证实。

记忆中的每个要点只表达一个可独立修改的要求；区分持续的 research 范围、资源与表达要求和仅本次 discussion 的暂停要求。/continue 结束临时讨论要求，保留持续的研究要求，不把“先别提出方案”带成永久限制。
