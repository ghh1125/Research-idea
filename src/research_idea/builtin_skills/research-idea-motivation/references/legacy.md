## Input and role

Use the supplied topic, user_notes, constraints, evidence and task schema. This skill guides reasoning; it is not scientific evidence. Work within the current task without tools or scripts.

Background orientation reads introductions, related work and conclusions to open directions for discussion. After /continue, focused reading examines the closest actual responses, deepen_problem develops each argument independently, map compares them, and frame_question explains the research claim. Full nine-part paper cards and experimental audits are not prerequisites for the first discussion.

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

## Explore, discuss, and deepen

**explore_problems：** 从原目标和已有进展探索通常三个、最多四个原因不同的重要问题。先按大类梳理现有办法的原理和有效作用，再提出问题方向；不提前选答案。不同方向要有各自的研究价值，不把偏爱问题的副作用凑成其他选项。随后暂停供用户纠正背景、调整范围和方向。

**plan_problem_reading：** 对当前问题找到真正最接近的回应。已有材料足够就直接深入；有影响判断的具体缺口才补查。查询应能找到已经解决这件事或改变我们解释的工作，而非只找支持猜想的材料。阅读引言和 related work 建立主要思路，再看原方法和结果确认具体能力。标题相似不等于问题重叠，引用者的概述也不等于已经读过原作。

**deepen_problem：** 独立深入每个问题。先在 response_analysis 说明主要方法正常发挥、合理适应后做到了什么，再推导仍会产生的困难。prior_art_delta 保存已有回应；bottleneck_hypothesis 解释可能原因；derivation 连接对原目标的影响；why_it_matters 解释重要性；research_need 提炼动机。既有回应解决了最初猜想，就沿其进展重新理解问题，不靠否定贡献保留切口。不能把研究中最困难的能力改写为“让agent准确判断”的操作要求来充当解法。本产品在这里研究问题，并不生成解决方案。

**map：** 比较所有深入的问题，解释各自最有力的研究理由、关键障碍与相对优先性。选择有洞见且影响原目标的问题，不因某个技术容易实现而选题。保留其他方向的完整论证，不通过改写它们来突出偏好。不要求分数或证明全领域最重要。

## Explain why the difficulty survives

“如果没发现重要关系就会失败”“如果反馈不足就无法更新”只重述了困难。把推演往前移：正常使用、推广或持续发展的什么过程造成了这项限制？已有最强方法怎样获取信息、利用反馈、改变判断，它发挥这些能力后为什么仍可能留下困难？从这个具体过程连接回背景目标，再说明研究动机。原因可以是合理的新猜想，不要求先有实验，也不把提供难点本身当成对 agent 的操作要求。

每个问题找直接回应其动机的原作，不能只与初始背景论文比。检索使用每条 2–4 个核心概念、必要的同义词或已知标题；不同查询分别寻找已有回应与问题现象。较早的直接回应也值得读。不要通过否认原贡献或仅换措辞保留问题；可以沿已有进展继续提出新的重要疑问。

## Discussion changes the research

在方向梳理后、问题深入比较后各暂停一次。普通消息继续讨论，只有 /continue 才推进。可以一直追问背景如何引出问题、已有办法为什么不够、困难是否真的关键；模型据此修订当前研究记录，而不只是解释或维护旧判断。

讨论中需要新资料时，提出具体补查问题，实际检索/阅读后重新回答并更新当前版本。查不到不能说查到了；不因一次检索缺失就断言没有先例。已有资料足够时无需重复补查。完成后的追问也应继续修订当前问题与动机，不自动转入技术方案。

完整对话、当前有效用户要点、研究判断版本分别保存。记忆只引用真实用户消息，助手建议不是用户决定；用户偏好也不是科学证据。较早纠正应通过原文检索和带出处要点继续可用。更改要求时替换旧项，保留前后来源；临时要求只属于提出它的那次讨论，/continue后不带到别的阶段。研究目标可以由用户修订，不冻结不可变的选题锚点。

## Deliver the research question and motivation

**frame_question 只写背景、现有方法、问题、动机以及一句明确的研究主张。** 不生成算法、技术路线、两个设计角度、工程计划或实验。

- 背景讲大方向中的真实需要，不把某篇论文的任务当成用户全部目标。
- 现有方法按几个主要角度解释怎么做、取得了什么进展，再给代表论文；不是堆论文摘要。
- 问题承接这些有效进展，讲清谁在什么条件下仍做不到什么，或方法发展怎样引出新困难。最关键的是为什么会这样，以及已有回应为何不能自然消除它。允许大胆但有原因的猜想，以自然语言指出推断；不用重复免责声明。
- 动机解释跨过这个障碍为什么会推进原目标、增加什么重要理解，不能只换个词重复问题。
- 一句研究主张说明我们到底想研究什么以及新的认识在哪里，不把方法清单当idea。

各部分用连贯、平实的中文详细解释前因后果。重要术语先解释具体事情，再给名字；读者不查术语也能复述研究问题。最后说明相较其他已分析问题，为什么当前优先此问题。全文围绕研究理由，不展开具体例子与实验计划。
