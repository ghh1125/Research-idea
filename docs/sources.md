# 工作流借鉴与接口资料

本项目的控制器、存储、适配器、八个内置 skill 和测试为本次自主实现；未复制或打包下列项目的源代码。它们是工作流设计的参考，不构成本项目已获得研究效果的证据。

- [ARIS / Auto-Research-In-Sleep](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep)：研究任务分解、迭代和状态保存。
- [ARIS idea-creator](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep/blob/main/skills/idea-creator/SKILL.md)：生成后再验证、候选 pilot、正负与不明确结果的解释。
- [ARIS research-refine](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep/blob/main/skills/research-refine/SKILL.md)：问题锚定、实现规格、避免增加无用模块。
- [ARIS experiment-bridge](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep/blob/main/skills/experiment-bridge/SKILL.md)：实现与计划核对、sanity check、结果收集。
- [Karpathy autoresearch program.md](https://github.com/karpathy/autoresearch/blob/master/program.md)：固定评测、运行预算、实验与代码版本记录。
- [CCFA Skills](https://github.com/mikubaka88/CCFA-Skills)：问题—机制—证据关系、最近工作比较、实验到主张的证据边界。

在 Research-idea 中只采用支持构思的部分：原始问题和假设随候选保留；每轮修改、审阅和未解决前提写入版本记录；先明确关键假设的判据再输出验证计划；负面意见和资料缺失不自动淘汰研究方向。没有接入上述框架的训练、实验执行或论文写作循环。

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
- [CCF 人工智能目录](https://www.ccf.org.cn/Academic_Evaluation/AI/)：代码中的 `ccf-a-ai-2022` 固定于 2022 目录的人工智能 A 类七会；网站和后续目录可能更新，因此该预设不声称当前评级或完整 CCF-A 覆盖。

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
