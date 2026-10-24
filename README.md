# Research-idea

从一个 LLM/NLP 研究主题出发，建立文献证据、提出机制假设、检查最近工作和实施前提，输出能开始验证的研究方案。

**定位：只辅助构思和筛选有意义、具备明确实施路径的 LLM/NLP 研究 idea。** 最小实验只输出验证计划；系统不执行训练、实验或论文写作。

**当前版本：v0.3.0，可用的研究 Idea CLI。** 支持对话式输入与配置、文献检索和正文分析、方案生成与修订、原文引用追溯、预算管理和中断恢复。已使用 Codex CLI（`gpt-6.1-sol`、`high`）完成真实研究主题的端到端运行，并通过 Python 3.11、3.12、3.13 自动化测试。

提供 Codex CLI、Claude Code CLI、OpenAI-compatible API 和原生 Anthropic API 适配器；目前真实账户实跑验证覆盖 Codex。研究流程和证据存储独立于模型会话。交付完整研究方案与第一步验证设计，idea 的实际效果通过后续研究实验评估。

## 三个核心要求

1. **说明问题为何值得研究，以及方法为什么必要。** 候选从已有观察或明确的问题假设出发，解释问题的重要性、现有方法的局限和因果假设，连接到拟议方法及预期进展；同时列出最简单替代方案，以及判断复杂方法是否必要的测试。贡献主张要说明属于机制、解释、边界、效率还是评测，改变什么变量、预期观察到什么、什么结果会推翻它。审阅分别判断问题意义、因果联系和进展是否实质，保留增量改进与不明确的判断，不能只因换了模块或产生数值提升就认定创新。
2. **最近工作必须逐项对照。** 每篇相关工作按问题、机制、可用信息、目标、评测、核心主张六个维度列出现有方法与候选方案，并绑定原文证据；相同、不同、未知分别记录。针对候选选出的最多三篇最近工作全文补读方法与成立条件，摘要不作为这一步的精读材料。
3. **可行性必须落到操作前提。** 检查数据访问、推理信号、接口、学习信号、计算资源、评测和最小测试七个维度；逐个说明所需信号在训练、推理还是评测阶段使用、是否已可获得、如何获取以及缺失时怎么办。尤其不能把评测答案当成推理时可用信息。

**大胆提出完整方案，通过讨论把它改好。** 尚未做实验、资源未测量、方法相似，都不会自动淘汰候选。资料暂少时可以明确提出问题假设，并设计一个低成本首测。真实引用仍对应原文；设想写成假设，不写成已有实验结果。

## 研究流程

**输入方向 → 查读关键论文 → 写出方法与首测草稿 → 对比最近工作 → 讨论修订并交付 idea。**

阅读者、方案设计者和研究讨论者通过分析卡、完整方案、逐条意见回应协作，沿用同一个模型与预算。详见 [工作流设计](docs/workflow.md)。

论文分析只服务三个判断：问题是否值得做、与已有工作到底差在哪、最小验证怎么开展。默认最多三个候选、两轮修订，不要求用户管理多个 agent 或逐项填写表格。

运行后先看 `outputs/report.md` 顶部：问题与意义、方法、已有工作差异、第一步验证和最脆弱假设。完整方案、论文分析卡和证据放在详细部分，按需查看。程序不自动执行实验；“有明确验证路径”和“实验已经有效”分别记录。

## 快速开始

需要 Python 3.11+。核心流程使用 Python 标准库，对话界面使用 prompt-toolkit；PDF 导入另外需要 Poppler 的 `pdftotext`。优先在 Linux/macOS 使用，Windows 的进程清理仍需实际环境验证。

```bash
git clone https://github.com/ghh1125/Research-idea.git
cd Research-idea
python -m venv .venv
source .venv/bin/activate
python -m pip install -e .

research-idea --help
research-idea doctor
research-idea demo --project ./research-projects/demo
research-idea inspect --project ./research-projects/demo
```

`demo` 使用明确标注的合成笔记和确定性后端，不联网、不调用真实模型，不产生科学结论。它演示证据抽取、问题建模、候选发展、质疑、修订、保存和报告导出。重复运行 `resume` 会复用已校验的检查点：

```bash
research-idea resume --project ./research-projects/demo
```

### 对话终端：在同一个窗口讨论、研究和调整设置

启动页用绿色大号 ASCII `IDEA` 标识，配有 `RESEARCH` 和 `IDEAS ONLY · From papers to research proposals`，下方显示编号使用说明。交付研究方案与验证设计，不执行科学实验。底部长期显示 `/intro` 使用介绍和常用命令。

```bash
research-idea chat --project ./research-projects/my-idea
# 交互终端中直接运行 research-idea 也会打开一个新的对话项目
```

直接输入文字即可与模型讨论，聊天记录保存在项目 SQLite 中。第一条消息默认成为研究主题，运行前可用 `/topic 新方向` 修改。`/run` 才开始正式的文献检索、论文分析和候选审阅，最后在窗口内显示 idea 方案与第一步验证。运行过程中隐藏输入框，只显示步骤输出和底部状态栏；Ctrl+C 停止并保留检查点，完成或失败后恢复输入。同一项目同一时刻执行一个任务。底部三行分别显示模型与当前步骤、调用与时间预算、常驻使用介绍。用户在对话中的补充会进入下一轮正式研究。

| 命令 | 用途 |
| --- | --- |
| `/intro` | 使用介绍：从输入研究方向到得到 idea；底部长期显示此入口和常用命令 |
| `/model`、`/model gpt-6.1-sol` | 打开选择菜单或直接指定模型；`inherit` 沿用后端配置 |
| `/reasoning`、`/reasoning high` | 选择思考强度；`inherit` 沿用 Codex 配置 |
| `/models` | 显示 Codex 本地模型缓存的 ID、强度和更新时间；不是实时授权保证 |
| `/account` | 查看后端、模型、配置档和登录方式；不读取或显示认证文件、密钥 |
| `/topic`、`/topic 新方向` | 查看或设置正式研究主题；已有研究任务的项目请用 `/new 新方向` |
| `/new`、`/new 新方向` | 开始空白研究，沿用模型、思考强度、检索和预算设置，调用与时间从 0 开始；旧项目保留 |
| `/input /path/to/brief.txt` | 读取 UTF-8 多行文字并发送讨论 |
| `/run`、`/stop` | 开始/恢复研究，或停止并保留检查点 |
| `/papers`、`/papers "带空格的论文.pdf"` | 列出或导入论文 |
| `/evidence ev_…` | 查看证据所属论文、链接、原文与位置 |
| `/status`、`/report`、`/history` | 查看状态、idea 方案和最近对话 |
| `/details`、`/details on`、`/details off` | 展开上一步分析，或切换完整过程与易读视图 |
| `/constraints 单卡24GB，两周` | 保存资源限制 |
| `/scope ai-recent`、`/scope local` | 最近 AI 会议加 CS arXiv，或仅本地资料 |
| `/scope 2025-01-01 2026-10-23` | 指定发表日期范围 |
| `/date`、`/date rolling 12 6` | 找方法看近 12 个月，动机查重看近 6 个月；运行时动态计算 |
| `/date fixed 2025-01-01 2026-10-23` | 使用固定时间范围；查重在该范围内取最近 6 个月 |
| `/venues`、`/venues ACL COLM ICLR` | 查看分级来源，或选择会议 |
| `/budget search_results_per_query 20` | 每个检索式召回的元数据量，不会全部精读 |
| `/budget max_papers 6` | 全流程论文阅读上限；默认初轮 3 篇，候选阶段再补最多 3 篇 |
| `/budget`、`/budget max_calls 100` | 查看/修改预算；讨论与研究共用调用与时间预算 |
| `/config`、`/open 项目目录` | 查看配置、打开已有或新项目 |
| `/help`、`/exit` | 帮助和退出 |

Enter 发送，先按 Esc 再按 Enter 换行，Tab 补全命令，↑↓ 浏览本次输入历史。多行粘贴作为一个输入框处理。Ctrl+C 停止正在运行的任务；空闲时清空输入。再次打开相同 `--project` 可继续对话或研究。

底部预算标为“本项目累计”，重新打开、清空输入和恢复研究都会保留计数；方案完成后显示“方案已生成”。要开始新的研究，在窗口输入 `/new`，也可以 `/new 你的新方向`。新项目会在当前项目的同级目录生成，沿用设置，论文、对话和用量从空白开始；用 `/status` 查看当前路径，`/open 旧项目路径` 返回原研究。

输出用彩色标签分区：紫色 `[skill]` / `[review]`，青色 `[search]`，蓝色 `[paper]` / `[read]`，黄色 `[analysis]` / `[thinking]`，绿色 `[evidence]` / `[idea]`。证据 ID、来源链接、原文引文和缺口各有强调；文字标签使无颜色终端也可理解。`[thinking]` 仅表示等待模型回复，不展示模型隐藏思维链。每一步先显示主要发现与新引用，完整结构化分析通过 `/details` 展开。当前回复以完整答复显示，研究步骤逐项实时输出，不提供模型 token 流。

所有步骤事件保存在 `terminal-events.jsonl`，聊天保存在 `research.sqlite3`，方案及论文分析卡保存在 `outputs/`。最终屏幕优先显示 idea；完整原文证据可用 `/evidence` 查询。

`/account` 对 Codex 调用其 `login status`，只显示识别出的登录方式，不透传可能含敏感内容的输出。API 后端只显示认证环境变量是否设置；Claude 登录方式由其 CLI 管理。模型缓存可能过时或属于不同配置档，实际可用性以调用结果为准。界面不会自动更换失败的模型。

### 交互启动：逐项选择

安装后运行：

```bash
research-idea launch
```

菜单依次选择项目目录、研究主题、模型、思考强度、论文文件、检索范围和运行预算。新项目默认提供 `gpt-6.1-sol`，也可沿用 Codex 配置或手动输入其他模型 ID；这不是账户可用模型的实时列表。主题可以直接输入，也可输入 `@/path/to/brief.txt` 读取多行研究说明。最后选择“开始研究”或“仅保存配置，稍后运行”。非交互脚本请使用 `start`。

### 命令行参数：直接启动

```bash
research-idea start "如何设计促进 agent 适应的交互环境" \
  --project ./research-projects/environment \
  --backend codex --model gpt-6.1-sol --reasoning-effort medium \
  --literature-preset ai-recent \
  --constraints "资源尚未确定；先设计无需训练的最小验证" \
  --max-papers 6 --max-candidates 1 --max-rounds 2 \
  --max-calls 80 --max-seconds 6600 --timeout-s 1200
```

| 选择 | 参数 | 说明 |
| --- | --- | --- |
| 模型 | `--model MODEL_ID` | 使用本机 CLI/账户支持的模型 ID |
| 思考强度 | `--reasoning-effort medium` | Codex 后端支持；`inherit` 清除项目覆盖并沿用 Codex 配置 |
| 研究输入 | 位置参数主题，或 `--topic-file ./brief.txt` | 二选一；文件为 UTF-8，最多 128 KiB |
| 参考论文 | `--papers ./papers paper.pdf` | PDF、正文、论文 JSON 或目录 |
| 资源限制 | `--constraints "单张24GB GPU，两周"` | 仅填写实际拥有的条件；未知可以明确写未知 |
| 文献范围 | `--literature-preset ai-recent --since YYYY-MM-DD --until YYYY-MM-DD` | 日期、CS 分类和会议筛选 |
| 研究规模 | `--max-papers 6 --max-candidates 1 --max-rounds 2` | 控制文献、候选和修订轮数 |
| 调用与时间 | `--max-calls 80 --max-seconds 6600 --timeout-s 1200` | 调用总数、累计运行秒数、单次调用超时 |
| 先配置 | `--setup-only` | 保存选项并导入资料，不调用模型 |

选项保存在项目的 `research.toml`，`resume` 沿用它们；也可在 `init/start/run/resume` 中覆盖模型、强度、资源和预算。模型/强度可选值以所选模型及 Codex 客户端为准，程序不会自动降级。通用强度值为 `none/minimal/low/medium/high/xhigh/max/ultra`；这不代表每个模型都支持全部值。GPT-6.1 Sol 的常用选择为 `low/medium/high/xhigh/max`，不支持 `none/minimal`。参见 [OpenAI 模型文档](https://developers.openai.com/api/docs/models/gpt-6.1-sol)与 [Codex 配置参考](https://learn.chatgpt.com/docs/config-file/config-reference)。

```toml
model = "gpt-6.1-sol"
reasoning_effort = "medium" # 空字符串表示继承 Codex 配置
max_papers = 6
max_candidates = 1
max_rounds = 2
max_calls = 80
max_seconds = 6600
timeout_s = 1200
```

思考强度作为每次 `codex` 调用的配置覆盖传入，不修改全局设置；变更强度会重新计算相关任务和候选。其他后端暂不接受非空 `reasoning_effort`，切换时用 `--reasoning-effort inherit` 清除它。未指定模型/强度的新项目继续沿用 Codex 配置。预算是上限，不保证在上限内完成；交互式新项目默认允许单次等待 20 分钟，累计预算仍为 110 分钟；已有项目配置保持不变，可用 `/budget timeout_s 1200` 调整。

```bash
research-idea start --topic-file ./brief.txt --project ./research-projects/my-idea \
  --model gpt-6.1-sol --reasoning-effort high --setup-only
research-idea run --project ./research-projects/my-idea
research-idea status --project ./research-projects/my-idea
research-idea resume --project ./research-projects/my-idea --timeout-s 1200
```

不安装包也可以运行：

```bash
PYTHONPATH=src python -m research_idea demo --project ./research-projects/demo
```

## 本地 Codex 与两类 skill

`research-idea` 调用你机器上的 Codex CLI，沿用 Codex 自己管理的登录、模型及用户配置，不要求为 Codex 模式另外提供 API key。可用 `codex login status` 确认当前登录方式：ChatGPT 登录使用该账户对应的订阅额度与限制；API key 登录按 API 方式计费。本工具不读取剩余额度、不复制登录凭据，也不会自动把 API 登录改成订阅登录。实际认证以 Codex 为准；例如继承的 `CODEX_API_KEY` 可覆盖已保存登录方式。已使用本机 Codex CLI 0.160.1 与 `gpt-6.1-sol` 验证结构化输出及网络重连后的成功结果；其他版本和账户仍需本机确认。可先运行 `research-idea doctor` 查看命令路径。

一次创建项目、导入本地论文并开始构思：

```bash
research-idea start "长上下文中证据冲突的处理机制" \
  --project ./research-projects/conflict \
  --papers ./papers --backend codex --no-search
```

`--papers` 支持文件或目录，递归收集 PDF、TXT、Markdown、论文 JSON，最多 100 个文件。目录应只放要导入的文献。PDF 需要 `pdftotext`。`--setup-only` 只建立配置与导入资料，不调用模型。TTY 终端中省略主题会提示输入；脚本中须显式给出主题。

**CLI 自带 skill 默认启用**，安装 wheel 后也可读取；按阶段加载，不会每次把全部技能都放进提示词：

| Skill | 研究职责 |
| --- | --- |
| `research-idea-analyze-paper` | 按九维框架分析问题、方法与实验，针对影响判断的缺口补读 |
| `research-idea-read-evidence` | 提取方法、条件、限制和原文证据 |
| `research-idea-audit-claims` | 对照作者主张与实验实际支持，保留测试范围、混杂和未读附录 |
| `research-idea-motivation` | 建立 problem → motivation → method，检验问题价值与方法必要性 |
| `research-idea-compare-methods` | 六维比较最近工作，定位核心主张的实际差异 |
| `research-idea-build-mechanism` | 明确干预、信息流、机制和可检验预测 |
| `research-idea-check-feasibility` | 检查信号、接口、数据、学习路径与资源前提 |
| `research-idea-design-falsification` | 设计最弱假设的最小证伪计划，区分三种结果解释 |

**本地已安装 skill 可额外选择**。常见项目/用户目录中的 `.agents/skills`、`.codex/skills`、`.claude/skills` 可被发现；`CODEX_HOME/skills` 受支持。自定义安装位置用 `--root` 或 `--skill-root` 指定。这里只扫描受限目录，不是完整复刻 Codex 的全局插件发现逻辑。

```bash
research-idea skills list
research-idea skills list --root ~/code/CCFA-Skills
research-idea skills show research-idea-motivation

research-idea skills use ccf-idea-optimizer ccf-idea-reviewer \
  --project ./research-projects/conflict --root ~/code/CCFA-Skills
research-idea resume --project ./research-projects/conflict --no-search
```

`skills use` 保存外部 skill 的明确路径；`skills clear --project PATH` 只清外部选择。也可在 `start/run/resume/init` 用重复的 `--skill NAME_OR_PATH` 和 `--skill-root DIRECTORY` 传入。路径歧义明确报错，不会悄悄选中同名 skill。链接安装的 skill 目录可读取其直接 `SKILL.md`。

```bash
research-idea start "你的研究主题" --project ./research-projects/my-idea \
  --papers ./papers --no-search \
  --codex-bin /absolute/path/to/codex --codex-profile research \
  --skill ~/code/CCFA-Skills/ccf-idea-optimizer/SKILL.md
```

`--codex-profile` 指向你已在 Codex 中配置的 profile；不指定则沿用默认设置。`--codex-bin` 是可执行文件路径或 PATH 中的名称，不是 shell 命令。全局认证文件不由本程序读取或改写。

本机启动脚本可设置 `RESEARCH_IDEA_CODEX_BIN` 提供默认 Codex 可执行文件。它只替代项目中的默认名称 `codex`，保留已保存的自定义路径；显式 `--codex-bin` 优先。

对应项目配置：

```toml
codex_bin = "codex"
codex_profile = ""
builtin_skills = true
skill_paths = []
skill_roots = []
skill_max_chars = 48000
```

设置 `builtin_skills = false` 或运行时指定 `--no-builtin-skills` 可关闭内置技能，用于自定义或对照评估。外部 skill 默认不会因为“安装了”就自动启用。单个文件最多 32 KiB，总加载文本受 `skill_max_chars` 限制；超出则报错，不静默截断。

加载的是指定 Markdown 文本。引用文件需额外显式选择；技能内的脚本、网络访问与工具不会自动执行，也不会改变研究任务的输出格式、证据规则和预算。原文证据与 skill 指导严格分开。每次记录名称、来源、阶段、路径与 SHA-256；修改 skill 后相关任务和候选批次会失效重算，旧历史保留。

推荐把 CCFA idea optimizer/reviewer、experiment designer 作为补充，按需要显式附加它们的具体参考文件。系统内置八个 skill 为项目自主编写，未打包第三方代码或文档；ARIS/CCFA 的设计借鉴见 [来源](docs/sources.md)。

## 使用自己的主题和论文

先建立独立项目，选择后端。CLI 后端需要用户已在本机完成安装和认证。

```bash
research-idea init "长上下文中的证据冲突" \
  --project ./research-projects/evidence-conflict --backend codex

research-idea add --project ./research-projects/evidence-conflict ./papers/paper.pdf
research-idea add --project ./research-projects/evidence-conflict ./notes/reading.md

research-idea run --project ./research-projects/evidence-conflict --no-search
```

推荐先提供 5–10 篇核心论文全文。没有本地文献时可以从主题自动发现摘要：

```bash
research-idea run "长上下文中的证据冲突" \
  --project ./research-projects/conflict --backend claude

research-idea search "conflicting evidence language models" \
  --project ./research-projects/conflict --source arxiv --limit 10
```

`search` 支持 arXiv 和 OpenAlex；按会议检索时，COLM 另外使用 OpenReview 的录用记录。网络、索引覆盖和 API 配额取决于运行环境；OpenAlex 可用 `search_api_key_env` 指定密钥环境变量。建议使用英文检索词，并把机制、条件和竞争解释拆成不同查询。自动流程先调用模型把研究意图整理成最多三条英文检索词，覆盖背景、机制和反面证据；计划与实际搜索分别记录。初始检索只使用约一半的文献容量，另一半留给候选 idea 的定向检索。已导入足够文献时可跳过初始检索；`--no-search` 完全跳过检索规划和联网。

### 会议论文与全文

推荐先用近期 AI/CS 范围启动：

```bash
research-idea start "如何设计持续演化的 LLM agent 交互环境" \
  --project ./research-projects/agent-environment \
  --backend codex --model gpt-6.1-sol \
  --literature-preset ai-recent
```

`ai-recent` 先检索 NeurIPS、ICML、ICLR、ACL、EMNLP、NAACL、COLM、AAAI、IJCAI 的已核实主会来源，再以 arXiv CS 预印本补充；预印本不会冒认为录用论文。每次混合检索先为会议分配约三分之二的名额，其余留给预印本；会议索引失败或结果不足时可以补充更多 CS 预印本，报告明确记录实际构成和缺口。

新项目默认限制 CS，采用动态日期：找方法看近 12 个月，候选动机与贡献对照看近 6 个月，每次运行按当天重新计算。已有固定日期项目保持原设置；可用 `/date` 切换，也可以精确覆盖：

```bash
research-idea start "你的研究方向" \
  --project ./research-projects/scoped --backend codex \
  --literature-preset ai-recent \
  --since 2025-01-01 --until 2026-10-23 \
  --venues NeurIPS ICML ICLR ACL EMNLP \
  --arxiv-categories cs.AI cs.CL cs.LG cs.MA
```

对应配置为 `search_source = "hybrid"`、`search_since`、`search_until`、`search_cs_only = true`、`arxiv_categories` 和 `search_venues`。arXiv 请求同时携带分类和首次提交日期范围；OpenAlex 使用发表日期、出版来源 ID，未指定会议时使用 Computer Science 字段。返回记录还要再次通过日期和领域检查，缺少必要元数据的记录被排除并保留原因。旧论文的新版本不会仅因更新时间较新就通过日期筛选。普通关键词以 AND 组合，带引号短语和原生布尔查询保留。

这些限制作用于新执行的联网检索。已有资料和显式导入的经典论文保留为项目上下文；要建立完全受新范围约束的语料，请使用新项目目录。范围和会议变化进入检索缓存身份，不能拿旧范围的缓存当成新检索结果。`--no-cs-only` 可取消 CS 字段检查；arXiv 分类仍由 `--arxiv-categories` 单独控制。传入不带值的 `--venues` 可以清空已保存的会议范围。

```bash
research-idea venues
research-idea init "长上下文中的证据冲突" --project ./research-projects/venues
research-idea search "conflicting evidence language models" \
  --project ./research-projects/venues \
  --venues ACL EMNLP NAACL COLM --full-text --limit 12
research-idea run --project ./research-projects/venues --no-search
```

也可以一次启动：

```bash
research-idea start "conflicting evidence in language models" \
  --project ./research-projects/conflict-venues --backend codex \
  --venues ACL EMNLP NAACL COLM
```

- `--venues` 自动选择 OpenAlex 路由；会议身份来自出版来源元数据，不从论文标题推测。COLM 按 OpenReview 的已录用 `venueid` 读取，最近最多三届、每届有限分页，再用标题和摘要的英文关键词匹配排序。这不是完整语义检索。
- `ai-recent` / `ai-recommended` 默认限定为 NeurIPS、ICML、ICLR、ACL、EMNLP、NAACL、COLM、AAAI、IJCAI、AAMAS。ICAPS、KR、UAI 不在默认范围。其他会议可显式选择，不自动把整个评级目录加入任务。
- 分别记录 CCF 2026、ICORE2026、TH-CPL 2019 评级来源。CCF 2026 的 ICLR 为 A、IJCAI 为 B；COLM 为单独关注会议。清华版本对应已核实的校内公开文件，不声称是 2026 修订。`ccf-a-ai-2026`、`tsinghua-a-ai-2019`、`core-astar-ai-2026` 是有版本的范围预设；`core-astar-2026` 提供完整 62 个 A* 会议供显式选择。`ccf-a-ai-2022` 只为旧配置兼容保留。
- 显式会议筛选针对主会议；Findings、workshop、demo、industry 等不被冒认为主会。解析不到会议来源、分页截断或服务失败会记录在 `coverage.gaps`，不会退回无过滤搜索并冒称命中指定会议。
- `search --full-text` 尝试下载允许的公开学术来源 PDF 并提取正文；未加此参数的手动搜索只导入元数据和摘要。需要 Poppler `pdftotext`。OpenReview 等来源可能要求浏览器校验；无法直接读取时记录缺口，可自行取得 PDF 后用 `add` 导入。
- `start/run` 默认尝试获取摘要记录对应的全文；`--no-fetch-full-text` 关闭下载，`--no-search` 只使用已导入材料，也关闭自动全文下载。
- 只有下载并提取到非空正文才标为 `full_text`；下载失败、扫描 PDF 或未支持的网站保留摘要与具体缺口。已下载全文仍会受阅读预算限制，报告区分完整提供文本与部分片段。

`report.json` 保留自动/手动检索记录、会议范围、索引覆盖缺口和全文获取记录。模型提出的检索建议不等于实际执行过的检索。

TXT/Markdown 默认作为 `notes`，PDF 提取文本作为 `full_text`。如果 TXT/Markdown 确实是论文全文，可显式 `--kind full_text`。这是来源声明，不是内容真实性认证。

JSON 可以包含一个论文对象、对象数组或 `{"papers": [...]}`。例如：

```json
{
  "id": "local-paper-001",
  "title": "实际论文标题",
  "authors": ["作者"],
  "year": 2026,
  "url": "https://example.org/paper",
  "content_kind": "full_text",
  "text": "实际论文正文……"
}
```

这里的 `example.org` 只是格式示例，不是论文来源。

## 后端配置

每个项目有自己的 `research.toml`。密钥只通过环境变量读取；不要把密钥写进配置、论文或 Git。

### Codex CLI

```toml
backend = "codex"
model = ""
```

模型为空时沿用 CLI 的模型选择，也可 `research-idea run --project PATH --model MODEL_ID`。适配器使用非交互执行、只读沙箱和结构化输出；禁用研究任务不需要的内置执行/搜索能力。发送研究材料前检查 MCP 清单：存在启用或未知的外部 MCP 配置时明确停止，请通过 `--codex-profile` 选择禁用外部 MCP 的配置，或在自己的 Codex 配置中明确禁用它们。程序不修改现有认证或全局设置。不兼容的 CLI 版本会报错，不会退化为假结果。

### Claude Code CLI

```toml
backend = "claude"
model = ""
```

使用 `claude --safe-mode -p`、JSON Schema、禁用内置工具与 MCP 的设置。需要支持这些参数的版本；保留现有认证。文献检索与正文读取由 Research-idea 控制器执行，Claude CLI 接收当前任务的材料进行分析。

### OpenAI-compatible API

下面可以作为项目配置的完整最小内容；未列出的参数使用默认值。

```toml
backend = "api"
api_provider = "openai-compatible"
base_url = "https://api.openai.com/v1"
api_key_env = "RESEARCH_API_KEY"
model = "填写账户可用的模型ID"
max_output_tokens = 8192
api_max_tokens_field = "max_completion_tokens"
```

在终端中设置 `RESEARCH_API_KEY`，然后运行 `research-idea run --project PATH`。使用 `/chat/completions` 与严格 `json_schema` 输出；自定义服务必须支持该协议。旧服务如果使用 `max_tokens`，可调整 `api_max_tokens_field`。不支持严格 schema 时明确报错，不会静默改成自由文本。

本机兼容服务可配置 `base_url = "http://127.0.0.1:8000/v1"`、`api_key_env = ""`；远程服务要求 HTTPS。凭据不放在 URL 中。

### 原生 Anthropic API

```toml
backend = "api"
api_provider = "anthropic"
base_url = "https://api.anthropic.com/v1"
api_key_env = "ANTHROPIC_API_KEY"
model = "填写支持结构化输出的模型ID"
max_output_tokens = 8192
```

使用原生 `/messages` 和结构化输出协议。更换 provider 时应同步修改已写入配置的 endpoint/key；用户显式配置值会被保留。

## 先筛选，再围绕问题阅读

默认每个检索式召回最多 20 篇元数据；1–3 个检索式合并去重，先用词项相关度和发表时间组织候选池，再用一次模型调用从最多 40 篇标题/摘要中选出值得精读的论文。选择围绕用户的问题、动机和机制，同等相关时优先近期工作，避免把只共享 agent、adaptation 等词汇的偏题论文读一遍。每篇显示选读原因和正文要回答的问题；只有题名的记录也可以入选核查，缺少的方法细节仍由正文确认。筛选计入调用预算并可缓存，不作创新性判决。

只给入选的 top-k 获取全文；默认总量 6 篇，初轮最多 3 篇用于形成问题与方法，剩余名额用于候选 motivation 的针对性检索。不为凑满数量而选入偏题资料。已知较老近邻不会因滚动时间窗口而删除。读取仍有每篇分块与补读预算；没有实际补读新文本时，保留原分析卡并记录补读请求的处理结果，不重复生成整张卡。

找方法与查重共享已读证据，但问题不同：前者找可迁移策略，后者比较问题现象、限制条件、原因解释与研究主张。方法相似不淘汰候选；新的故事必须形成不同的研究问题或可检验预测。输出优先说明问题、动机、现有方法不足、原因解释、具体方法和第一步验证；内部审阅状态保留在详细记录中。

HTTP 429 遵守 `Retry-After`；较长配额等待不阻塞本轮，而是暂停该服务并使用替代来源。403 不反复重试。成功元数据缓存 24 小时，相同项目多次查询复用会议目录。OpenAlex/OpenReview 索引不可用时，可回退 ACL Anthology、PMLR、NeurIPS 主会目录、ICLR 论文列表及 COLM 官方录用列表。仅入选的 ICLR/COLM 论文再解析全文链接；COLM 的预印本匹配要求标题精确规范化相等。会议目录有时只给月份或年份，保留原始精度，不编造日级日期。

入选会议目录论文的 PDF 下载失败时，在同一次获取的时间预算内查询同标题 arXiv 预印本。匹配要求规范化标题相同；双方有作者信息时还需作者重合。报告分别保留会议元数据、实际阅读的预印本地址与版本。同一轮不会因为补全 PDF 地址而重复下载同一篇失败论文。

## 论文怎么分析

全文阅读默认启用。先定位章节及图表/公式标记，分块读取方法、实验和可用附录，再形成九维分析卡：**问题、动机、洞见、方法、已有工作差异、实验设计、结果、结论边界、研究启发**。每个维度区分原文支持、模型分析、证据不足和不适用；不会要求理论论文提供不存在的实验。

核心方法说明输入、输出、必要性和隔离模块贡献的检验；实验对照作者主张、实际设置、结果与可支持结论。作者明确承认的局限、模型疑点、待检验机会分开保存。有具体缺口时，按章节或图表 ID 定向读取尚未提供的文本，再更新分析卡。只进行一次有预算的补读循环，不为补齐表格无限循环。

默认每篇最多先读 3 个连续片段，每片最多 `source_chars` 字符，再按必要性最多补读 2 片。每片最多抽取 6 条原文证据。正文读取、分析卡生成和补读都计入统一调用预算。摘要和笔记保留来源受限标记，不能升级成全文分析。

章节和图表识别是启发式的；覆盖率表示交给成功阅读任务的文本范围，不证明模型理解完整。当前只分析提取文本，未视觉核对图片、表格布局和公式。未读内容、获取失败和缺少对照是待核查项，不是不存在或不可行的证明。

分析卡进入后续头脑风暴和候选对比。候选阶段仍对最多三篇最近工作定向补读，按问题、机制、信息、目标、评测、主张逐项比较。引文定位容忍 PDF 连字、排版引号、软连字符和行末断词，并保存未改写的原文及精确字符位置。词语、数字、否定和非连续拼接不会通过。定位失败时，控制器向模型提供失败引文和附近原文进行一次定向修复；仍失败的观察单独排除并记入 quote_gaps，保留其他有效证据继续研究。被排除的引文不会进入证据库，也不能用来否决候选。引文匹配只验证原文存在，语义解释与创新判断仍需核查。

PDF 使用 Poppler 的默认阅读顺序抽取，保留分页；不使用会把双栏文字按行交错的物理版式模式。表格和公式仍需按阅读缺口处理。已有项目不会自动重写旧正文，可重新导入更正的全文；显式导入的非空全文即使更短也会更新来源，并使旧证据及候选批次失效，普通摘要补充不会覆盖全文。

研究审阅默认使用同一个配置后端的独立任务，不能称为跨模型独立验证。审阅指出的阻塞、待修订和轮数用尽会单独记录。模型“继续”意见不提升实验证据状态，所有未执行方案保持 `untested`。

## 预算与恢复

```toml
max_candidates = 3
max_rounds = 2
max_papers = 6
search_results_per_query = 20
search_date_mode = "rolling"
strategy_months = 12
novelty_months = 6
max_calls = 80
max_seconds = 3600
timeout_s = 180
source_chars = 24000
deep_reading = true
max_paper_read_chunks = 3
max_followup_reads = 2
auto_search = true
constraints = "单张24GB GPU；两周；允许小规模微调；禁止调用推理时真实答案"
```

- 新建项目默认上限为 80 次；旧项目显式设置的上限不变。上限不是必须用满的目标。`max_followup_reads = 0` 关闭额外补读，`deep_reading = false` 恢复简要证据抽取。
- `max_calls` 是持久化的后端 `generate` 调用次数，结构化输出修复也计入。API 每次最多三次 HTTP 尝试，并记录已知尝试数；CLI 内部请求次数未知。
- `max_seconds` 是项目累计控制器运行时间，在任务边界检查并保存。强制杀死进程可能丢失最后一个检查点之后的时间；它不是操作系统级全局计费限额。
- 每次后端调用有本地超时，API 请求在可终止子进程中执行。断开连接不能保证远端服务立刻停止推理或计费。
- 成功任务按输入、提示词和后端配置缓存。已有候选批次会保留；内部补充文献不重新生成整批候选。
- 显式 `add/search` 更改语料，或 `run --replan`，会重新建立候选批次；旧批次留在事件记录。
- 预算不足返回退出码 `3` 并导出当前报告；提高配置上限后 `resume`。普通错误返回 `1`。

```bash
research-idea status --project ./research-projects/conflict
research-idea resume --project ./research-projects/conflict
research-idea inspect --project ./research-projects/conflict
research-idea inspect --project ./research-projects/conflict EVIDENCE_OR_IDEA_ID
research-idea inspect --project ./research-projects/conflict PAPER_ID --paper-card
research-idea inspect --project ./research-projects/conflict --events
research-idea export --project ./research-projects/conflict
```

`status` 和 `inspect` 使用 SQLite 只读快照，可在研究流程运行期间查看进度；修改项目的命令仍受单写入进程锁保护。

输出位于项目的 `outputs/report.md`、`report.json` 和各候选 Markdown 文件。逐篇分析卡位于 `outputs/papers/`。JSON 报告的 `schema_version` 为 `4`，包含问题—动机—方法的论证、贡献主张、逐篇六维对照、七维可行性检查、所需信号及其阶段，以及 `feasibility_status`、`comparison_gaps` 和 `feasibility_assessment`。还包含 `paper_cards`（含实际阅读范围与补读记录）、`search_plans`、`paper_claim_audits` 和每版本的 `revision_record`；主张审计的结论是基于原文的模型判断，不是独立复现。运行数据库为 `research.sqlite3`；研究材料与运行目录不要提交到源码仓库。

## 开发与测试

```bash
PYTHONPATH=src python -m unittest discover -s tests -v
```

测试覆盖证据定位、引用一致性、断点恢复、预算、CLI 协议、API 本机 HTTP、超时、文献解析、本地 skill、范围筛选和缓存失效。已在 macOS 使用真实 Codex CLI 与 `gpt-6.1-sol` 验证结构化输出、重连恢复，并检索下载真实 arXiv CS 论文。会议检索在本次环境遇到 OpenAlex HTTP 429、OpenReview HTTP 403，报告保留这些覆盖缺口；Claude/API 真实账户、GPU 和系统性的 idea 质量评估仍待完成。离线测试通过不能证明研究质量。

下一步重点是用真实主题评估能否产出值得做、可开始验证的 idea，而不是继续增加流程。参见 [架构](docs/architecture.md) 和 [借鉴来源](docs/sources.md)。
