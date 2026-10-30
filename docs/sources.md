# 工作流借鉴与接口资料

## K-Dense scientific-agent-skills：综合、构思与讨论

参考其工作方法，在现有控制器中实现状态传递与恢复，没有引入该框架依赖：

- [scientific-brainstorming](https://github.com/K-Dense-AI/scientific-agent-skills/blob/main/skills/scientific-brainstorming/SKILL.md) 和 [facilitation_workflows](https://github.com/K-Dense-AI/scientific-agent-skills/blob/main/skills/scientific-brainstorming/references/facilitation_workflows.md)：借鉴生成与选择分开、新材料后重新构思、保留合并和修订理由。对应独立问题深入、一次 `reconsider_problems`、前后版本记录。
- [hypothesis-generation](https://github.com/K-Dense-AI/scientific-agent-skills/blob/main/skills/hypothesis-generation/SKILL.md)：借鉴区分现象与解释、比较不同原因。对应 `explanation_comparison`，与已有回应和研究意义一起进入问题选择。
- [literature_search_strategies](https://github.com/K-Dense-AI/scientific-agent-skills/blob/main/skills/hypothesis-generation/references/literature_search_strategies.md)：借鉴沿引用追溯代表原作。对应题名出处、召回检查、必要时按题名补查，共用现有补读预算。
- [literature-review core_workflow](https://github.com/K-Dense-AI/scientific-agent-skills/blob/main/skills/literature-review/references/core_workflow.md)：借鉴围绕主题综合研究。对应跨论文前提、进展、条件变化和可能后果，避免逐篇摘要直接变成局部改进。

动机 skill 按综合、原因比较、重新构思、讨论和表达拆分加载。讨论理由与用户决定分别持久保存。产品仍只交付问题和动机，不采用评分淘汰、实验注册或额外审批流程。

> v0.6.0 当前流程专注研究问题与动机。本文保留历次设计来源记录；早期技术方案相关条目属于历史实现，当前主流程不再执行。讨论与记忆的设计来源见文末 v0.5.0 一节；本轮交互与记忆改进见[版本更新](../CHANGELOG.md)。


本项目的控制器、存储、适配器、八个内置 skill 和测试为本次自主实现；未复制或打包下列项目的源代码。它们是工作流设计的参考，不构成本项目已获得研究效果的证据。

- [ARIS / Auto-Research-In-Sleep](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep)：研究任务分解、迭代和状态保存。
- [ARIS idea-creator](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep/blob/main/skills/idea-creator/SKILL.md)：生成后再验证、候选 pilot、正负与不明确结果的解释。
- [ARIS research-refine](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep/blob/main/skills/research-refine/SKILL.md)：问题锚定、实现规格、避免增加无用模块。
- [ARIS experiment-bridge](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep/blob/main/skills/experiment-bridge/SKILL.md)：实现与计划核对、sanity check、结果收集。
- [Karpathy autoresearch program.md](https://github.com/karpathy/autoresearch/blob/master/program.md)：固定评测、运行预算、实验与代码版本记录。
- [CCFA Skills](https://github.com/mikubaka88/CCFA-Skills)：问题—机制—证据关系、最近工作比较、实验到主张的证据边界。

在 Research-idea 中只采用支持构思的部分：原始问题和假设随候选保留；每轮修改、审阅和未解决前提写入版本记录；围绕关键假设说明信息来源与作用理由，技术路线服务于核心 idea；负面意见和资料缺失不自动淘汰研究方向。没有接入上述框架的训练、实验执行或论文写作循环。

已加入原始问题锚点、上轮修订要求、逐字段变化、新证据与未解决质疑记录；关键内容与证据完全重复时停止修订。`max_rounds` 和调用预算继续约束迭代；程序尚不能自动判断两版方案是否取得语义上的研究进展。

接口参考：

- [Codex non-interactive mode](https://developers.openai.com/codex/non-interactive-mode)
- [Codex configuration reference](https://developers.openai.com/codex/config-reference)
- [Claude Code programmatic execution](https://code.claude.com/docs/en/headless)
- [Claude Code CLI reference](https://code.claude.com/docs/en/cli-reference)
- [OpenAI Chat Completions](https://platform.openai.com/docs/api-reference/chat/create)
- [Anthropic structured outputs](https://platform.claude.com/docs/en/build-with-claude/structured-outputs)
- [arXiv API manual](https://info.arxiv.org/help/api/user-manual.html)
- [OpenAlex API](https://developers.openalex.org/)
- [OpenAlex authentication](https://help.openalex.org/api/authentication/)：支持环境变量中的 key 作为 Bearer header，避免进入查询 URL。
- [OpenAlex filtering](https://help.openalex.org/api/filtering/) / [publication sources](https://help.openalex.org/data/sources/)：按出版来源 ID 过滤，不用论文标题推测会议。
- [OpenReview accepted-note retrieval](https://docs.openreview.net/how-to-guides/data-retrieval-and-modification/how-to-get-all-notes-for-submissions-reviews-rebuttals-etc) / [API v2](https://docs.openreview.net/reference/api-v2/openapi-definition)：COLM 使用录用的 `content.venueid`，保留年份与有限分页范围。
- [COLM 2026](https://colm.cc/Conferences/2026/CallForPapers)：官方会议与 OpenReview 入口。
- [ACL Anthology metadata example](https://aclanthology.org/2025.naacl-long.1/)：出版来源、NAACL 全称、DOI 与 PDF 的对应方式。
- [CCF 人工智能目录](https://www.ccf.org.cn/Academic_Evaluation/AI/)：默认使用 CCF 2026 第七版。ICLR 为 A、IJCAI 为 B；2022 预设仅保留兼容。

后端采用已核对文档的接口；2026-10-23 已用真实 Codex CLI 与 `gpt-6.1-sol` 核对结构化输出和重连恢复。Claude/API 真实账户兼容性仍待验证。以后复制第三方代码时，应单独核实许可证、固定版本并保留必要声明。

- [Codex local skills](https://developers.openai.com/codex/skills)：本地 SKILL.md 形式与路径约定。本 CLI 采用显式加载和阶段分配，未声称复制全部原生插件机制。

## OpenResearch 的本地 Codex 与技能接入

核对 [alphaXiv/OpenResearch，commit fe36f7424855d7218e64812c5fec6f7db955586f](https://github.com/alphaXiv/OpenResearch/tree/fe36f7424855d7218e64812c5fec6f7db955586f)（2026-10-23）中的以下实现：

- [`src/local/harness/codex.rs`](https://github.com/alphaXiv/OpenResearch/blob/fe36f7424855d7218e64812c5fec6f7db955586f/src/local/harness/codex.rs)：新版本主要使用本地 `codex app-server`，保留旧版 `codex exec` 路径；检测已配置的 provider 与现有认证类型，不代表强制使用 ChatGPT 登录。原生 skill 目标是用户 `.agents/skills/orx/SKILL.md`，会话技能目录也是 `.agents/skills`。
- [`src/local/native_store.rs`](https://github.com/alphaXiv/OpenResearch/blob/fe36f7424855d7218e64812c5fec6f7db955586f/src/local/native_store.rs)：识别现有 `CODEX_HOME`，为隔离会话准备与现有认证、配置、plugins、skills 等文件的链接。这里讨论的是源码行为，本项目没有读取用户凭据。
- [`src/commands/install_skills.rs`](https://github.com/alphaXiv/OpenResearch/blob/fe36f7424855d7218e64812c5fec6f7db955586f/src/commands/install_skills.rs) 与 [`src/local/user_skills.rs`](https://github.com/alphaXiv/OpenResearch/blob/fe36f7424855d7218e64812c5fec6f7db955586f/src/local/user_skills.rs)：提供模块技能安装，以及从本地 coding agent 和插件目录发现/镜像技能的机制。

本项目借用“本地模型客户端负责认证、控制器负责研究流程、内置模块与用户技能可组合”的分工。当前使用每任务 `codex exec`，直接继承现有登录环境；不建立或复制认证文件。技能采用显式选择、按阶段冻结 Markdown 内容的方式，尚未复刻 OpenResearch 的完整原生技能、插件镜像或交互式 app-server 会话。两者的执行边界不同，不能把文本加载说成执行了技能脚本。

账号额度依据 [Codex authentication](https://developers.openai.com/codex/auth) 与 [non-interactive mode](https://developers.openai.com/codex/non-interactive-mode)：`codex exec` 默认复用保存的 CLI 登录；ChatGPT 登录和 API key 登录具有不同计费路径。用户应在本机确认实际登录和环境配置，本程序不查询剩余额度。


## 论文分析框架

参考已安装 `nature-paper-card` 的来源范围、阅读覆盖、模块必要性和实验—主张证据链原则。Research-idea 自主实现有界九维分析卡和定向补读，不打包该技能正文，不要求生成完整长篇 Paper Card；分析只服务 idea 的意义、差异和最小验证路径。

## 自动研究系统的文献检索对照

2026-10-23 按固定源码版本检查，采用思路并自主实现，没有复制第三方代码：

| 系统与源码 | 本次核对的行为 | 本项目采用的部分 |
| --- | --- | --- |
| [AutoResearchClaw，be4ba47](https://github.com/aiming-lab/AutoResearchClaw/blob/be4ba4755bf1b52220f25e13b2293b5956590070/researchclaw/literature/search.py) | 合并 OpenAlex、Semantic Scholar、arXiv；传递年份下限；去重后按引用数、年份排序。主入口没有统一强制 CS/会议范围 | 多源合并和去重；本项目继续按查询相关性与日期窗口筛选，不采用引用数优先 |
| [ARIS research-lit，23745b6](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep/blob/23745b69a14880b5716d1773e5d20f5f1e6ab1d6/skills/research-lit/SKILL.md) | 指导优先最近两年，经典工作例外；示例 arXiv helper 调用未直接传入日期参数 | 近期工作优先与显式经典资料；本项目把日期落实为程序参数 |
| [AI-Scientist，1de1dbc](https://github.com/SakanaAI/AI-Scientist/blob/1de1dbc1f4ee2c5f61e9c94348d55eb51d7fa2eb/ai_scientist/generate_ideas.py) | 检索函数请求标题、年份、会议、摘要等元数据；该入口的 S2 请求未添加时间或学科过滤 | 结构化元数据；本项目增加服务端过滤及返回后的核验 |
| [Karpathy autoresearch，228791f](https://github.com/karpathy/autoresearch/blob/228791fb499afffb54b46200aca536f79142f117/program.md) | 指定固定训练、评测和实验循环；该文件没有文献检索流程 | 实验预算思路；不将它当作文献检索实现 |

核对源码不能证明这些系统的总体研究质量。当前实现仍需评估检索召回、会议索引覆盖、全文读取和实际 idea 的质量。


## 本轮构思机制与选文改进（2026-10-23）

以下固定版本作为设计资料阅读，未执行其技能或复制代码。重点是问题与动机，而不是增加角色数量或输出篇幅。

| 参考 | 核对的机制 | 本轮落地 |
| --- | --- | --- |
| [IdeaScientist roles，82a98a0](https://github.com/jiarui-liu/IdeaScientist/blob/82a98a08772eab08d11fd097445afa4a8eaaa5b3/ideascientist/harness/roles.py) 与 [gap rubric](https://github.com/jiarui-liu/IdeaScientist/blob/82a98a08772eab08d11fd097445afa4a8eaaa5b3/ideascientist/rewards/gap_finder/rubric.py) | 同问题近邻用于找具体缺口，其他问题中的方法用于迁移；阅读摘要是角色间的接口；逐项检查缺口的价值和依据 | 将问题诊断先于方法组合，要求具体失败条件、最强已有替代方案和影响；证据卡跨阶段复用。未移植其 RL 训练或结果屏蔽语料 |
| [ResearchStudio IdeaSpark，063f100](https://github.com/microsoft/ResearchStudio/blob/063f10088af49909e1a4a7ea8d29efe19633f34e/ResearchStudio-Idea/skills/idea_spark/SKILL.md) | 先构思，再检查已有工作与实施连贯性，修订后核对；独立简单基线；资源上限不因评审改变 | motivation-first 候选复查与必要性测试；报告先显示问题和方法，审计细节折叠。未把文字审阅说成已经执行其公式/实现检查 |
| [Supervisor-Skills idea-evaluator，a20d76e](https://github.com/HKUSTDial/Supervisor-Skills/blob/a20d76ef3979b804d7dbf599d577826957e0a8a9/skills/idea-evaluator/SKILL.md) 与 [search strategy](https://github.com/HKUSTDial/Supervisor-Skills/blob/a20d76ef3979b804d7dbf599d577826957e0a8a9/skills/deep-research/references/search-strategy.md) | 按研究范式与阶段判断价值、资源和方法；多种关键词视角与未选资料中的盲区线索 | 保留元数据候选池和选文原因，不把未入选资料当作不存在；审查问题价值与原因，而非只检查表格完整 |
| [ARIS research-lit，23745b6](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep/blob/23745b69a14880b5716d1773e5d20f5f1e6ab1d6/skills/research-lit/SKILL.md) | 多源检索，近期与经典工作结合，针对缺口重新查询 | 12/6 个月动态窗口，候选阶段单独检索，保留已知旧近邻；继续使用 gpt-6.1-sol，不暗中引入其他模型 |

## 两轮构思与技术探索（2026-10-24）

在上述固定版本源码和技能文本上进一步核对了以下机制，并按本项目的两轮目标实现。参考材料用于设计，不作为论文证据，也不直接执行第三方技能。

| 参考机制 | 本项目的实现 |
| --- | --- |
| IdeaScientist 的 gap_finder 区分问题缺口，innovator 寻找其他子领域中可迁移的机制；reader 带着目标阅读并复用已答问题 | 第一轮 `positioning` 随构思给出动机与贡献对照；第二轮技术查询可以脱离原应用领域，`design_transfer` 记录共同结构、原条件和改造。已有证据复用，有具体缺口才定向补读 |
| ResearchStudio IdeaSpark 将概念与技术细化分开，并要求可独立解释的简单基线 | 第一轮先说明问题价值、基本干预和可行路径；第二轮再给参考路线、必要性理由与简单替代。没有照搬其额外评审关卡 |
| Supervisor-Skills 按研究阶段与价值类型理解贡献，允许有理由的未检验机制进入实验 | 问题价值与方法必要性成为一条连贯论证；效率改善要解释解除的约束，跨域迁移要解释新增能力或理解。没有引入固定分数淘汰机制 |
| ARIS research-lit 复用已有知识、组织方法线索、指出论文对当前问题的关系 | 技术阅读产出直接面向设计决定，最终 `design_decisions` 留下采用或改造的原因，未选技术不自动成为方法模块 |

上述行为由本项目的阶段路由、结构化输出、缓存和回归测试实现；没有移植外部框架的训练或实验执行流程。

### 构思与技术设计的具体代码对应

| 固定版本的参考文件 | 借鉴后的实现位置与行为 | 验证 |
| --- | --- | --- |
| [ARIS idea-creator](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep/blob/23745b69a14880b5716d1773e5d20f5f1e6ab1d6/skills/idea-creator/SKILL.md)，构思角度与核心机制 | [idea_instructions.py](../src/research_idea/idea_instructions.py) 的 `map/propose` 将这些视角作为文献线索，再按本项目要求归到“已有重要问题未解决”或“现有方法暴露新问题”，从根本原因推导动机与 idea。按用户要求，已知动机与贡献对照在提出 idea 时完成 | [test_idea_workflow.py](../tests/test_idea_workflow.py)：第一轮必须给最近工作对照和基本实现路径，资料少仍能提出可检验假设 |
| [IdeaScientist roles](https://github.com/jiarui-liu/IdeaScientist/blob/82a98a08772eab08d11fd097445afa4a8eaaa5b3/ideascientist/harness/roles.py)，`reader/gap_finder/innovator` | [controller.py](../src/research_idea/controller.py) 的 `plan_search/prepare_design/focus_sources` 与 [build-mechanism skill](../src/research_idea/builtin_skills/research-idea-build-mechanism/SKILL.md)：问题驱动阅读、已读证据复用、来源对象到目标对象的对应、成立条件与最简单替代，形成 `design_transfers` 后选择适合 idea 的参考路线 | [test_technical_design.py](../tests/test_technical_design.py)：阶段顺序、定向补读、来源归属、时间窗口和下载恢复 |
| [ARIS experiment-bridge](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep/blob/23745b69a14880b5716d1773e5d20f5f1e6ab1d6/skills/experiment-bridge/SKILL.md)，sanity → baseline → main 的次序 | 借鉴先看关键前提和简单替代的思路；当前 [design-falsification skill](../src/research_idea/builtin_skills/research-idea-design-falsification/SKILL.md) 仅在审阅时比较核心解释。按用户要求，默认不再规划实验，未接入该框架的执行流程 | 内置 skill 路由与结构测试；[test_idea_workflow.py](../tests/test_idea_workflow.py) 验证不提供实验计划仍可完整交付 |
| CORAL [reflect](https://github.com/Human-Agent-Society/CORAL/blob/0123dfb939b35228cf2c1fde224cd0561e727408/coral/hub/prompts/reflect.md) / [consolidate](https://github.com/Human-Agent-Society/CORAL/blob/0123dfb939b35228cf2c1fde224cd0561e727408/coral/hub/prompts/consolidate.md) | [controller.py](../src/research_idea/controller.py) 的设计讨论传递上一轮意见、实际版本变化和设计者回应；[prompts.py](../src/research_idea/prompts.py) 要求重复批评先说明原回应为什么仍不足，保留已经有理由的选择。采用共享记录与反思思路，材料仍是文献和设计意见，不当成实验评分 | [test_idea_workflow.py](../tests/test_idea_workflow.py)：下一轮审阅收到正确的上一轮意见、修改记录与对应回应 |

默认仍使用用户配置的同一个后端、模型和总预算，不因参考框架而启动额外模型、自动实验或长期循环。

### 从文献提炼问题与判断贡献重叠

2026-10-24 进一步对照以下原始实现，保留有用的思考方法，在本项目的问题探索、逐个深入、比较选择与构思中完成：

| 参考 | 本项目的采用方式 |
| --- | --- |
| [ARIS idea-creator](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep/blob/23745b69a14880b5716d1773e5d20f5f1e6ab1d6/skills/idea-creator/SKILL.md) 的结构性缺口与不同构思视角 | 由 `explore_problems` 打开不同问题，`deepen_problem` 逐个从已有回应推导困难成因、问题与意义，`map` 比较后选择，再交给 `propose` 构思想法；不照搬固定数量候选、多模型调用或实验执行 |
| [ARIS novelty-check](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep/blob/23745b69a14880b5716d1773e5d20f5f1e6ab1d6/skills/novelty-check/SKILL.md) 区分相邻研究与具体结果已被覆盖 | 对照需要指出论文实际覆盖的主张；已知组件可以揭示新的相互作用或发现，逐个组件存在不等于整个贡献重复 |
| [Supervisor-Skills paradigm-shift probe](https://github.com/HKUSTDial/Supervisor-Skills/blob/a20d76ef3979b804d7dbf599d577826957e0a8a9/skills/idea-evaluator/references/paradigm-shift-probe.md) 的隐藏假设与问题重要性追问 | 用核心洞见、重要能力或认识的变化解释意义；不照搬固定分数、裁决标签或履历限制 |
| [research-idea-explorer 的构思结构](https://github.com/jameslemon2002/research-idea-explorer/blob/14232d97213b4c21127342ee1f429a4d2a77e158/skills/research-idea-explorer/references/schema.md) 与[生成流程](https://github.com/jameslemon2002/research-idea-explorer/blob/14232d97213b4c21127342ee1f429a4d2a77e158/research_idea_explorer/engine.py) | 借鉴从未解释的问题、主张、区分关系和研究意义组织构思，保存来源与选择关系；其词项相似度、检索相近程度和拥挤度启发式不用于本项目的科学查重判断 |

这些参考帮助设计思考流程，不能证明生成的 idea 已经具有科学创新。回归测试检查切口传递、选择关联、来源有效性、恢复和报告；真实产出另行查看问题意义、洞见与贡献论证。

### 背景、问题与动机怎样推导

2026-10-25 进一步核对以下固定版本的具体做法。这里只借鉴推理方式，没有执行第三方 skill 或复制其正文。

| 参考及源码行为 | 本项目采用的思路 |
| --- | --- |
| ARIS [idea-creator](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep/blob/23745b69a14880b5716d1773e5d20f5f1e6ab1d6/skills/idea-creator/SKILL.md) 从共同假设、矛盾结果和扩展条件寻找结构性问题；[research-refine](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep/blob/23745b69a14880b5716d1773e5d20f5f1e6ab1d6/skills/research-refine/SKILL.md) 保留原问题，分析原流程卡点、简单修补为何不足，再找最小干预，并允许反驳造成问题漂移或堆模块的意见 | 从已有机制推演有意义的使用条件与可能困难，先形成研究需要，再选操作；修订围绕同一目标推进，必要时有理由地调整问题 |
| IdeaScientist [gap_finder](https://github.com/jiarui-liu/IdeaScientist/blob/82a98a08772eab08d11fd097445afa4a8eaaa5b3/ideascientist/harness/roles.py#L139) 按机制组织已有进展，解释最接近的方法为何仍留下困难，随后才交给 innovator；[rubric](https://github.com/jiarui-liu/IdeaScientist/blob/82a98a08772eab08d11fd097445afa4a8eaaa5b3/ideascientist/rewards/gap_finder/rubric.py#L180) 追问谁受到阻碍、解决后能获得什么能力或认识 | 在同一条件下考虑已有方法的正常回应，避免用“没采用我们的操作”替代剩余问题；动机说明跨过障碍为什么推进背景目标 |
| Supervisor-Skills [paradigm-shift probe](https://github.com/HKUSTDial/Supervisor-Skills/blob/a20d76ef3979b804d7dbf599d577826957e0a8a9/skills/idea-evaluator/references/paradigm-shift-probe.md) 追问隐藏前提、发展变化与问题意义；[idea-evaluator](https://github.com/HKUSTDial/Supervisor-Skills/blob/a20d76ef3979b804d7dbf599d577826957e0a8a9/skills/idea-evaluator/SKILL.md) 接受尚无实测结果但有机制论证的 idea | 允许基于文献线索提出合理猜想，用成立条件和推导说明问题为何可能出现；研究意义由它对原目标的影响解释，不要求先完成实验 |

综合后的流程由 [idea_instructions.py](../src/research_idea/idea_instructions.py) 与 [motivation skill](../src/research_idea/builtin_skills/research-idea-motivation/SKILL.md) 实现：`deepen_problem` 先解释最强已有方法在同样条件下怎样正常工作、实际缓解了什么，再推导为什么仍会留下或产生困难、怎样妨碍原目标，由此形成问题和动机。`bottleneck_hypothesis` 要提出有解释力的因果洞见，说明不显然的依赖、假设或相互作用，以及常规改进为何不能自然消除障碍，而非给困难换个术语。`map` 比较各问题的价值与洞见后选择，`propose` 才构思 idea 与基本可行路径。问题来自现有办法解决原问题时产生的新困难，或背景中提出、现有主要思路难以解决的新问题。允许大胆猜想与单篇启发，不要求共同缺陷、唯一起因或先证明全领域无解。

为落实分工，初期检索先围绕原目标的不同原因与已有思路建立 `research_routes`，查询、实际召回、互补选文和正文阅读沿同一路线关联，优先把约三分之二阅读额度用于第一阶段。[research_context.py](../src/research_idea/research_context.py) 为构思建立材料副本，控制器限定初期来源，暂不带入旧候选解释、论文卡里的预制改法与实验建议；源论文的方法、实验、结果、条件和原文引用仍保留，对原贡献的审计疑点留在完整记录中。构思承接已有进展，不靠否定原贡献制造新动机；完整记录供第二阶段参考。路线不是预设技术角度，也不要求各路线凑足论文。

控制器保留用户原始目标，系统在 `research_question` 中聚焦，并用 `scope_connection` 解释为什么这个聚焦值得研究。`map` 结合检索计划、实际路线覆盖与各问题的独立论证进行比较，保留全部问题池、路线关联及 `selected_problems` 的理由。控制器从已选字段构造 `argument_handoff`，按已有回应、因果洞见、问题推导、目标影响和研究需要交给 `propose`，补读后的完成版同样接收；后续通过 `selected_opportunity` 保留问题与选择依据。新来源可以修订原认识，同时区分原科学问题与方案实现时才出现的困难。相比直接把单篇论文建议当成候选，这一分工让问题推导先于方案构思。它是本项目的综合设计，不增加模型调用、评分或审查轮次，也不是上述框架统一规定的流程。

这是面向本项目的综合设计，不固定示例中的领域、困难数量或方法模块，也不引入上述框架的评分、额外审查或实验执行。第二阶段继续由 [build-mechanism skill](../src/research_idea/builtin_skills/research-idea-build-mechanism/SKILL.md) 从 idea 推导两个技术问题，借助 `design_axes` 连接检索、迁移与方法选择；一种技术可以服务两个问题。测试检查阶段衔接和材料传递，实际论证是否更好仍应通过产出判断。

## 目录与会议来源核对

- [CCF 2026 目录原文副本](https://dengpingfan.github.io/papers/CCF-Recommend-2026.pdf)：第 57–58 页；[CCF 官方目录入口](https://www.ccf.org.cn/Academic_Evaluation/By_category/)。官方页面当前有浏览器验证，本轮以目录原文核对分级。
- [清华 TH-CPL 校内原文](https://numbda.cs.tsinghua.edu.cn/~yuwj/TH-CPL.pdf)：2019-08-13 通过，第 11 页人工智能与模式识别 A 类会议。没有把 2019 文件称为 2026 版本。
- [ICORE2026 官方数据库](https://portal.core.edu.au/conf-ranks/?search=&by=all&source=ICORE2026&sort=arank&page=1)：按等级排序前两页共 62 个 A*。默认仅启用用户指定的 LLM/NLP/Agent 子集。
- [CCFDDL](https://github.com/ccfddl/ccf-deadlines)：提供 CCF/CORE/THCPL 三套筛选和会议主页、时间，作为人工查阅入口；评级采用上述明确版本的原文。
- [OpenAlex 错误说明](https://help.openalex.org/api/errors/)：429 可能是速率或每日额度；403 不应无限重试。本轮实测 429 的剩余额度为 0，Retry-After 超过十小时。
- [COLM 2026 官方录用列表](https://colm.cc/Conferences/2026/AcceptedPapers)、[ICLR 2026 论文列表](https://iclr.cc/virtual/2026/papers.html)、[ACL 2026 长文集](https://aclanthology.org/2026.acl-long/)、[PMLR 目录](https://proceedings.mlr.press/)、[NeurIPS 2025 主会](https://papers.nips.cc/paper_files/paper/2025/vol38-main-conference)：索引 API 受限时的公开替代来源。只记录目录实际提供的信息。

### 扩展会议的出版名称（2026-10-24 核对）

- [ACM Multimedia 官方页面](https://2026.acmmm.org/)：ACM MM 的完整名称为 ACM International Conference on Multimedia。
- [The Web Conference 官方页面](https://www2026.thewebconf.org/)：WWW 同时使用 The Web Conference / ACM Web Conference 名称。
- [VLDB Endowment](https://www.vldb.org/)：VLDB 的研究论文评审通过 PVLDB 进行；检索包含 Proceedings of the VLDB Endowment，与 The VLDB Journal 分开。
- [SIGMOD 2026 研究论文说明](https://2026.sigmod.org/calls_papers_sigmod_research.shtml)：研究论文发表在对应 PACMMOD 期次。[DBLP 的 PACMMOD 目录](https://dblp.org/db/journals/pacmmod/index.html)同时列出 SIGMOD 和 PODS 的出版关联，因此检索纳入该系列时保留真实系列名称。

这次扩展更新研究范围、名称匹配与公开正文来源。新增会议使用已匹配的 OpenAlex 出版源检索，不代表为每个会议都增加了独立官方目录适配器。
## 上下文组织参考

- [IdeaScientist：独立论文读取上下文](https://github.com/jiarui-liu/IdeaScientist/blob/main/ideascientist/harness/runner.py)：读取全文使用独立上下文和输入预算，返回聚焦摘要供后续角色使用。借鉴阶段材料分离；本项目保留原文证据及实验结果，继续用已有分块读取。
- [ARIS：会话恢复与 Research Contract](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep/blob/main/docs/SESSION_RECOVERY_GUIDE_CN.md)：保存精简项目状态与当前 idea 的聚焦文档，用于恢复工作。借鉴明确研究主线与持久化交接，本项目通过 SQLite 和 `research_frame` 实现，不引入额外审批或角色。


## 问题讨论与记忆（2026-10-25）

阅读以下实际实现后，本项目在现有 SQLite 控制器中实现暂停、增量要点和版本衔接，没有增加框架依赖或复制其代码：

- [ARIS run_state.py](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep/blob/main/tools/run_state.py) 与 [resumable-runs](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep/blob/main/skills/shared-references/resumable-runs.md)：持久记录阶段与产物，从明确的位置恢复。我们借鉴阶段恢复，暂停的确认来自用户 `/continue`，没有引入它的跨模型验收规则。
- [ARIS idea-creator 的研究 Wiki 写入](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep/blob/main/skills/idea-creator/SKILL.md)：通过程序写入 idea 与论文/缺口的联系，保留已有结果。对应本项目由程序保存问题版本、选择理由与消息出处，而不只提示模型记住。
- [OpenHands condenser](https://github.com/OpenHands/software-agent-sdk/blob/main/openhands-sdk/openhands/sdk/context/condenser/README.md)：追加事件日志与供模型使用的压缩视图分离。对应完整对话保留，模型使用现行要点、近期对话和待整理原话。
- [Mem0 prompts.py](https://github.com/mem0ai/mem0/blob/main/mem0/configs/prompts.py)：用户消息提取与 ADD/UPDATE/DELETE/NONE 更新操作。对应带来源消息 ID 的 add/replace/remove；无更新保留原要点，替换项保留历史，不将助手建议当用户决定。
- [LangGraph interrupts](https://github.com/langchain-ai/docs/blob/main/src/oss/langgraph/interrupts.mdx)：持久暂停并以同一会话恢复。对应问题讨论前后的明确阶段边界；恢复不会重复已完成的研究阶段。

这些工程机制用于避免对话遗忘和重复运行，不是研究结论正确或 idea 有创新性的证明。

### v0.5.0：更频繁的讨论与跨阶段会话

进一步核对 ARIS 与 CORAL 的讨论、恢复和知识保存实现后，本项目采用下列分工：完整对话保留原文，当前研究要点可替换或撤回，讨论阶段单独恢复；模型每轮使用与当前问题相关的材料。

| 已核对的源码行为 | 本项目采用的思路 |
| --- | --- |
| ARIS [idea-discovery 文献范围讨论](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep/blob/main/skills/idea-discovery/SKILL.md#L237) 在 `AUTO_PROCEED=false` 时请用户确认文献地图与范围，收到纠正后调整查询；[候选讨论](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep/blob/main/skills/idea-discovery/SKILL.md#L275) 允许重新构思或返回文献阶段 | 把讨论放到方向与问题尚可修改的时候，用户纠正实际影响后续材料、问题与选择，而不只产生一段聊天回复 |
| ARIS [run_state.py](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep/blob/main/tools/run_state.py) 保存阶段、产物与恢复信息；[research-refine](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep/blob/main/skills/research-refine/SKILL.md#L58) 保存阶段、轮次与会话标识，并从阶段文档恢复 | 已完成的研究材料与当前讨论分别持久化，恢复后从暂停处继续；研究主线可被用户明确修订 |
| ARIS [research_wiki.py](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep/blob/main/tools/research_wiki.py#L225) 从 brief、论文与 idea 关系组织有长度限制的查询材料；该材料不等同于完整聊天记录 | 按本轮问题选择相关上下文，保留可回查的出处；历史内容无需每次全量塞进模型 |
| CORAL [Codex 适配器](https://github.com/Human-Agent-Society/CORAL/blob/main/coral/agent/builtin/codex.py) 从运行记录获取会话 ID，通过 `codex exec resume` 延续原生会话；其默认执行方式不等待用户对话 | 借鉴恢复连续性。Research-idea 继续自行保存研究会话，由显式讨论与 `/continue` 驱动；没有把 CORAL 的原生会话恢复描述成用户讨论流程 |
| CORAL [steering.py](https://github.com/Human-Agent-Society/CORAL/blob/main/coral/hub/steering.py) 持久记录引导内容及创建、应用时间，[manager.py](https://github.com/Human-Agent-Society/CORAL/blob/main/coral/agent/manager.py#L860) 在恢复时应用引导 | 用户纠正必须有保存、应用与阶段归属，不能只依赖模型记住最近几条消息 |
| CORAL [create-notes](https://github.com/Human-Agent-Society/CORAL/blob/main/coral/template/skills/create-notes/SKILL.md) 区分原始来源、研究记录与综合认识，并保存替代关系及依据；[checkpoint.py](https://github.com/Human-Agent-Society/CORAL/blob/main/coral/hub/checkpoint.py) 追踪共享知识版本 | 区分用户原话、当前要求和研究者的推测；修改当前要求时保留旧版本与来源 |

[conversation.py](../src/research_idea/conversation.py) 中的用户决定账本是本项目自行实现的组合设计：只有用户消息可以作为要点来源；`add/replace/remove` 保留替代关系；临时要求绑定产生时的讨论阶段和实例，`/continue` 只结束当前讨论的临时要求。长期要求持续使用，完整原话不改写。模型同时接收当前要点的原话出处、近期对话和按当前问题召回的较早用户消息；已撤回要求附带失效记录，避免旧选择被重新当成当前决定。已处理但没有提炼为要点的早期消息也可以再次检索，`/history [关键词]` 则面向用户查阅全部历史中的相关原话。

以上源码启发了讨论与上下文的组织方式；没有发现 ARIS 或 CORAL 在这些入口中直接提供与本项目相同的、仅接受用户原话来源且可替代或撤回的决定账本。Research-idea 没有复制它们的代码，也不依赖后端原生会话记住研究要求。
