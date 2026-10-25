---
name: research-idea-motivation
description: Derive consequential research problems from literature, choose them before constructing solutions, and carry that rationale into LLM/NLP ideas and technical design.
---

## Input and role

Use the supplied topic, user_notes, constraints, evidence and task schema. This skill guides reasoning; it is not scientific evidence. Work within the current task without tools or scripts.

The first phase develops alternatives before choosing one. **explore_problems opens different directions; deepen_problem gives each direction an independent, substantive argument; map compares those arguments and chooses; propose constructs an idea for that choice.** This is a division of thinking, not an extra review or approval. Think boldly about plausible new difficulties; do not limit ideas to repairs already suggested by source papers.

## Form the problem before the solution

Use discovery_plan and discovery_coverage to see which different approaches were actually explored. Read the supplied papers' selection questions and route provenance, but let full-text findings correct the planned routes. Compare the important problems these different lines expose; do not build every alternative around one favorite relation. For each problem, explain how the strongest existing responses work and precisely where their information, objective, assumptions or interactions may leave a consequential obstacle. This can be a reasoned hypothesis; naming methods and saying they do not guarantee a solution is not the explanation. Link opportunities through research_route_ids where applicable. These records guide synthesis without adding a score or a new review call.


把用户原目标与我们提出的研究聚焦分开。research_frame.user_goal 保留原始 topic，明确补充以 user_notes 为准；选中的能力写入 research_question，在 scope_connection 解释它为何推进原目标。不能先把候选能力说成用户需要，再用符合需要证明其重要性。按解决思路综合已有工作：它们依靠什么原理，已经帮助我们走到了哪里。阅读者为某篇论文预制的改法不是出发点；保留论文的方法、实际结果、条件和证据，用它们形成更大的认识。

**承接已有贡献，再提出下一步问题。** 在构思中按已有方法及其报告结果成立来推演：它已经解决什么，这件事成功之后还会产生什么重要困难，或接下来哪项重要需要超出了它原本解决的范围？不以否定原贡献、质疑实验归因或指出缺少消融来制造我们的 motivation。论文证据仍按实际条件准确引用；主张审计负责界定能说到哪里，不负责替选题制造“别人没做好”。新的问题可以大胆推测，但要解释它如何从已有进展中产生、为何影响下一步目标。

只沿两个角度引出问题：

- **emerging_problem**：已有办法解决了原问题，但成功使用或继续发展时又产生重要困难。说明困难怎样产生、影响什么、为什么原有思路难以处理。
- **unresolved_need**：从大背景提出一个重要问题，说明现有主要思路推进后还可能跨不过什么障碍，以及它怎样妨碍所需的进展。

两条路线都可以是合理猜想。已知机制、条件变化、文献现象之间的联系可以启发尚未被报告的困难。用“我们推测，在……时，……因为……”把条件、过程和后果讲清一次，再向前展开；不要求先有实验，也不要求问题在自己的关键假设错误时仍然成立。basis 记录 source_observation 或 research_hypothesis，引用真实前提不会把新推断变成观察事实。

把问题、原因与意义连起来，而不只是为三个字段填话：

1. **从目标到困难。** 先说明原目标需要哪种实质进展，再解释哪件做不到或变坏的事情会阻碍它。不能从“可能存在没学好的关系或没用好的信息”直接跳到关键障碍；需要说明目标为什么依赖它。“泛化”“关系”“效率”等类别还不足以让读者知道问题是什么。
2. **让已有回应改变我们的判断。** 将最强的正常已有办法放进所猜的条件，推演它怎样影响原因、会缓解什么、介入之后还可能剩下什么困难。若它已经在改变所猜的原因，就不能原样重复干预之前的困难。不是列完方法后加一句“不保证”“没显式考虑”，也不要求证明所有方法失败。这里的剩余困难同样可以是有机制理由的新猜想。
3. **说明为什么值得优先研究。** 如果跨过该障碍，什么重要事情会变得可做，或哪项认识会改变？如果只继续推进已有思路却留下它，为什么原目标还会受限？大背景重要，不代表每个有关的小缺点都重要。局部变化也能有重大意义，但要说明这条联系，不能以宏大措辞代替。
4. **由剩余困难产生动机。** 据此需要理解什么关系、获得什么能力或改变什么原则？这一需要应在没有算法名、模块名时仍然说得通。过渡不成立时重新考虑问题或原因，不往技术里加细节来掩盖它。

一篇论文也能启发重要问题，不规定来源数量或共同缺陷。由某类方法带来的新问题可以依赖这类方法，不要求换掉它后问题仍存在。相似主题不代表问题已经解决；作者 claim 要结合实际方法与证据理解。

## Choose, then construct

**In explore_problems:** 先整理 approach_landscape，再从原目标和已有进展探索通常三个、最多四个不同的重要问题。用户明确聚焦时就在其范围内探索，不凑数量。每个 problem_seed 说明问题、来源和为什么值得深入；此时不排序、不选解法。不同方向要有自己的研究价值，不能把偏爱的问题、它的一个副作用和一个容易否定的小修补写成三个选项。成本也能是重要问题，但应说明它限制了什么实质能力，而不只说更便宜。

**In deepen_problem:** 本次只深入指定的 problem_seed。把它当成值得认真研究的方向，用 derivation、bottleneck_hypothesis、prior_art_delta、why_it_matters、research_need 完整推导上述论证。讨论主要方法的最强正常回应，包括它们能合理结合时的作用；既说明会缓解什么，也推演为什么还可能留有重要困难。哪怕它后来不被选中，也应有独立的动机和价值。不要预设另一个方向更好，不进入技术方案，不凭实现容易程度选择问题。

**In map:** 接收已经独立展开的 problem_cases，比较每个问题最值得研究之处。problem_comparisons 为每项记录 strongest_case、remaining_obstacle、priority_reason：跨过它能带来什么进展、最强已有回应后还留下什么，以及和其他问题相比为什么应优先或随后研究。回应其他方向真正有力的理由，不能把它们简写成次要涨分或效率问题。若认为某问题是前提，解释解决它怎样帮助其他方向、其他方向为何不能独立先推进，而不只说“更基础”。最后写 selected_problems（opportunity_id、selection_reason），最多 max_candidates 个，通常一个；原样保留各 case 的论证。选择的是问题价值，不是技术是否好写。不要求打分、证明全领域最重要或否定未选方向；这是给出有理由的研究优先次序。

**In propose:** 内部草案可指出缺失的具体方法近邻，由控制器按 comparison_search 定向检索阅读；补充后继续同一个问题的构思，完成后才展示。不是每个想法都加一轮审查，也不从论文标题作覆盖判断。

 接收已经保存的选择，继承理由；本次选择解决办法。先从所需进展与障碍推导操作应起什么作用，再考虑利用什么可获得的信息、采用什么思路。idea_core 展开对象、获取路径、作用与能力的连接、同最近工作的实质区别。路径行不通时换办法，不悄悄把问题改成某种技术容易完成的小任务。基本可行性在这里推演，第二阶段再探索技术参考；不要求详细工程或实验。

**In develop/refine/review:** selected_opportunity 保存最初问题、推导、研究需要和选择理由；旧快照可能缺字段。可以因新的认识调整问题，同步解释原因并更新动机、核心想法与贡献。不能为了借用某个技术而无声缩小目标，也不因快照存在而强迫恢复一个已经有理由修正的判断。

## Explain the resulting argument

Background → Existing methods → Possible problem → Motivation → Idea 是一条因果论证。单独讲背景的需要，再承接现有方法已实现的进展；问题先用普通话说明什么重要事情做不到、为什么从背景会遇到它；动机说明已有回应后还需要改变什么；idea 直接回应这个需要。读者应在看到解决办法之前就理解选题的必要性。

像向研究同伴解释为什么觉得这件事值得做：详细、平实，每段推进一步，必要术语先解释再命名。不要用篇幅、抽象名词或重复强调重要性代替过渡。第一阶段不写具体例子、实验计划或退路声明。大胆提出有理由的想法，缺少实测不是停止构思的理由；输出遵守当前任务 JSON，不新增评分、审批或额外审查。

把背景、现有方法、问题和动机直接写成读者能理解的正文，不留给报告再翻译。背景解释现实需要；现有方法先解释做法和作用，再提论文名；问题说明哪件事仍做不到或会变坏，以及为何会这样；动机接着说明需要改变什么、为何针对这个原因、成功会多带来什么。每段展开过程和因果联系，必要术语先用普通话解释，不能靠“表示、关系、机制、泛化”等词代替说明。原目标与起步实现保持区别：难获取的信息应促使我们设计取得和利用它的办法，不把研究问题偷偷换成只处理已经容易取得信息的情形。

explore_problems 整理的 approach_landscape 会传给每次问题深入和比较：按解决背景目标的原理归纳主要角度，代表论文只是各类的实例。可利用综述、系统比较及已读论文的引言/相关工作理解领域，不把引用到的原作伪装成自己已读。类别可以由多个来源共同支撑，一篇综述也可说明多个类别；不把当前精读列表等同于领域全貌。让这些主要思路参与问题推导与对照，existing_work 也按类别解释做法和作用。
