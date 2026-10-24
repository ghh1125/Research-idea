# 进阶使用与实现说明

[返回 README](../README.md)。首次使用请先看安装启动与 CLI 操作；本页保留文献来源、skill、后端协议、预算与报告的详细说明。

## 使用自己的主题和论文

先建立独立项目，选择后端。CLI 后端需要用户已在本机完成安装和认证。

```bash
research-idea init "长上下文中的证据冲突" \
  --project ./research-projects/evidence-conflict --backend codex

research-idea add --project ./research-projects/evidence-conflict ./papers/paper.pdf
research-idea add --project ./research-projects/evidence-conflict ./notes/reading.md

research-idea run --project ./research-projects/evidence-conflict --no-search
```

可以提供已有的核心论文全文；默认全流程最多精读 6 篇。没有本地文献时可以从主题自动发现摘要：

```bash
research-idea run "长上下文中的证据冲突" \
  --project ./research-projects/conflict --backend claude

research-idea search "conflicting evidence language models" \
  --project ./research-projects/conflict --source arxiv --limit 10
```

`search` 支持 arXiv 和 OpenAlex；按会议检索时，COLM 另外使用 OpenReview 的录用记录。网络、索引覆盖和 API 配额取决于运行环境；OpenAlex 可用 `search_api_key_env` 指定密钥环境变量。建议使用英文检索词，并把机制、条件和竞争解释拆成不同查询。第一阶段把研究意图整理成最多三条英文查询，覆盖背景、动机问题、机制或失败条件；第二阶段围绕 idea 的核心困难，重新检索可迁移机制与技术路线，不要求所有查询都带上原应用领域。计划与实际搜索分别记录，初轮使用约一半文献容量，剩余容量留给技术探索。已导入足够文献时可跳过初始检索；`--no-search` 跳过联网检索，第二阶段仍会梳理两个技术角度并使用已有材料。

### 会议论文与全文

推荐先用近期 AI/CS 范围启动：

```bash
research-idea start "如何设计持续演化的 LLM agent 交互环境" \
  --project ./research-projects/agent-environment \
  --backend codex --model gpt-6.1-sol \
  --literature-preset ai-recent
```

`ai-recent` 先检索下方列出的 20 个会议及对应出版系列，再以 arXiv CS 预印本补充。范围覆盖 AI/NLP/Agent、数据挖掘与数据库、检索与 Web、视觉与多模态；选文仍依据当前研究主题。每次混合检索先为会议来源分配约三分之二的名额，其余留给预印本；会议索引失败或结果不足时可以补充更多 CS 预印本。结果名额有限时，按相关性和时间确定优先顺序，并兼顾不同会议，避免名单后面的会议固定被截掉。

新项目默认限制 CS，采用动态日期：背景与技术探索看近 12 个月，第一阶段动机与贡献对照看近 6 个月，每次运行按当天重新计算。已有固定日期项目保持原设置；可用 `/date` 切换，也可以精确覆盖：

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
- `ai-recent` / `ai-recommended` 默认包含 NeurIPS、ICML、ICLR、ACL、EMNLP、NAACL、COLM、AAAI、IJCAI、AAMAS、KDD、ICDM、ICDE、SIGMOD、VLDB、ACM MM、CVPR、ICCV、SIGIR、WWW。ICAPS、KR、UAI 不在默认范围。会议增加后仍按主题、相关度和时间筛选，全文阅读上限由 `/budget max_papers` 控制。
- `ACM MM`、`ACMMM`、`MM` 为同一会议；WWW 同时识别 The Web Conference 与 ACM Web Conference，VLDB 检索覆盖 PVLDB。SIGMOD 检索纳入 PACMMOD 系列，结果保留 PACMMOD 的真实出版名称，因为该系列也承载 PODS。评级目录的分级字段与此研究范围分开保存。
- 已有项目保留保存的会议设置；输入 `/scope ai-recent` 或 `/venues ai-recommended` 即可启用扩展范围。
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

## 先筛选，再围绕问题阅读

默认每个检索式召回最多 20 篇元数据；1–3 个检索式合并去重，先用词项相关度和发表时间组织候选池，再用一次模型调用从最多 40 篇标题/摘要中选出值得精读的论文。选择围绕用户的问题、动机和机制，同等相关时优先近期工作，避免把只共享 agent、adaptation 等词汇的偏题论文读一遍。每篇显示选读原因和正文要回答的问题；只有题名的记录也可以入选核查，缺少的方法细节仍由正文确认。筛选计入调用预算并可缓存，不作创新性判决。

只给入选的 top-k 获取全文；默认总量 6 篇，初轮最多 3 篇用于形成问题、动机与基本思路，剩余名额用于技术设计的定向检索。不为凑满数量而选入偏题资料。已知较老近邻不会因滚动时间窗口而删除。读取仍有每篇分块与补读预算；没有实际补读新文本时，保留原分析卡并记录补读请求的处理结果，不重复生成整张卡。

第一阶段阅读同时比较问题现象、动机、限制条件、原因解释与研究主张；第二阶段复用这些证据，并寻找能回答具体设计问题的可迁移策略。方法相似不淘汰候选；新的故事必须形成不同的研究问题或可检验预测。输出优先说明问题、动机、现有方法不足、核心洞见和贡献，再附技术参考；内部审阅状态保留在详细记录中。

HTTP 429 遵守 `Retry-After`；较长配额等待不阻塞本轮，而是暂停该服务并使用替代来源。403 不反复重试。成功元数据缓存 24 小时，相同项目多次查询复用会议目录。OpenAlex/OpenReview 索引不可用时，可回退 ACL Anthology、PMLR、NeurIPS 主会目录、ICLR 论文列表及 COLM 官方录用列表。仅入选的 ICLR/COLM 论文再解析全文链接；COLM 的预印本匹配要求标题精确规范化相等。会议目录有时只给月份或年份，保留原始精度，不编造日级日期。

入选会议目录论文的 PDF 下载失败时，在同一次获取的时间预算内查询同标题 arXiv 预印本。匹配要求规范化标题相同；双方有作者信息时还需作者重合。报告分别保留会议元数据、实际阅读的预印本地址与版本。同一轮不会因为补全 PDF 地址而重复下载同一篇失败论文。

## 论文怎么分析

全文阅读默认启用。先定位章节及图表/公式标记，分块读取方法、实验和可用附录，再形成九维分析卡：**问题、动机、洞见、方法、已有工作差异、实验设计、结果、结论边界、研究启发**。每个维度区分原文支持、模型分析、证据不足和不适用；不会要求理论论文提供不存在的实验。

核心方法说明输入、输出、必要性和隔离模块贡献的检验；实验对照作者主张、实际设置、结果与可支持结论。作者明确承认的局限、模型疑点、待检验机会分开保存。有具体缺口时，按章节或图表 ID 定向读取尚未提供的文本，再更新分析卡。只进行一次有预算的补读循环，不为补齐表格无限循环。

默认每篇最多先读 3 个连续片段，每片最多 `source_chars` 字符，再按必要性最多补读 2 片。每片最多抽取 6 条原文证据。正文读取、分析卡生成和补读都计入统一调用预算。摘要和笔记保留来源受限标记，不能升级成全文分析。

章节和图表识别是启发式的；覆盖率表示交给成功阅读任务的文本范围，不证明模型理解完整。当前只分析提取文本，未视觉核对图片、表格布局和公式。未读内容、获取失败和缺少对照是待核查项，不是不存在或不可行的证明。

分析卡直接进入第一阶段构思和动机、贡献对照。第二阶段对最多三篇与设计相关的论文提取技术借鉴：原方法、共同结构、适用条件、改造方式与简单替代。已有证据优先复用；有具体阅读问题才补读，不默认重新生成九维分析卡。最终方案记录实际采用的设计选择及其理由。引文定位容忍 PDF 连字、排版引号、软连字符和行末断词，并保存未改写的原文及精确字符位置。词语、数字、否定和非连续拼接不会通过。定位失败时，控制器向模型提供失败引文和附近原文进行一次定向修复；仍失败的观察单独排除并记入 quote_gaps，保留其他有效证据继续研究。被排除的引文不会进入证据库，也不能用来否决候选。引文匹配只验证原文存在，语义解释与创新判断仍需核查。

PDF 使用 Poppler 的默认阅读顺序抽取，保留分页；不使用会把双栏文字按行交错的物理版式模式。表格和公式仍需按阅读缺口处理。已有项目不会自动重写旧正文，可重新导入更正的全文；显式导入的非空全文即使更短也会更新来源，并使旧证据及候选批次失效，普通摘要补充不会覆盖全文。

研究审阅默认使用同一个配置后端的独立任务，不能称为跨模型独立验证。审阅指出的阻塞、待修订和轮数用尽会单独记录。模型“继续”意见不提升实验证据状态，所有未执行方案保持 `untested`。

## 内置与本地 skill

**CLI 自带 skill 默认启用**，安装 wheel 后也可读取；按阶段加载，不会每次把全部技能都放进提示词：

| Skill | 研究职责 |
| --- | --- |
| `research-idea-analyze-paper` | 按九维框架分析问题、方法与实验，针对影响判断的缺口补读 |
| `research-idea-read-evidence` | 提取方法、条件、限制和原文证据 |
| `research-idea-audit-claims` | 对照作者主张与实验实际支持，保留测试范围、混杂和未读附录 |
| `research-idea-motivation` | 建立 Background → Problem → Motivation → Idea 的论证，推敲问题价值与核心想法 |
| `research-idea-compare-methods` | 六维比较最近工作，定位核心主张的实际差异 |
| `research-idea-build-mechanism` | 明确干预、信息流、机制和可检验预测 |
| `research-idea-check-feasibility` | 检查信号、接口、数据、学习路径与资源前提 |
| `research-idea-design-falsification` | 检视核心解释与最脆弱的假设，默认不展开实验计划 |

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

推荐把 CCFA idea optimizer/reviewer、experiment designer 作为补充，按需要显式附加它们的具体参考文件。系统内置八个 skill 为项目自主编写，未打包第三方代码或文档；ARIS、Supervisor-Skills、IdeaScientist 和 research-idea-explorer 等的设计借鉴见 [来源](sources.md)。

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

输出位于项目的 `outputs/report.md`、`report.json` 和各候选 Markdown 文件。逐篇分析卡位于 `outputs/papers/`。JSON 报告的 `schema_version` 为 `6`，包含已有工作进展与研究需要之间的论证、两个 `design_axes` 及查询和方法的 `axis_ids` 关联、第一阶段 `positioning` 与 `feasibility_sketch`、第二阶段 `design_transfers` 与最终 `design_decisions`、贡献主张、逐篇六维对照、七维可行性检查、所需信号及其阶段，以及兼容旧项目的 `validation` 字段（默认不生成实验计划）、`feasibility_status`、`comparison_gaps` 和 `feasibility_assessment`。还包含 `paper_cards`（含实际阅读范围与补读记录）、`search_plans`、`paper_claim_audits` 和每版本的 `revision_record`；主张审计的结论是基于原文的模型判断，不是独立复现。运行数据库为 `research.sqlite3`；研究材料与运行目录不要提交到源码仓库。

## 开发与测试

```bash
PYTHONPATH=src python -m unittest discover -s tests -v
```

测试覆盖证据定位、引用一致性、断点恢复、预算、CLI 协议、API 本机 HTTP、超时、文献解析、本地 skill、范围筛选和缓存失效。已在 macOS 使用真实 Codex CLI 与 `gpt-6.1-sol` 验证结构化输出、重连恢复，并检索下载真实 arXiv CS 论文。会议检索在本次环境遇到 OpenAlex HTTP 429、OpenReview HTTP 403，报告保留这些覆盖缺口；Claude/API 真实账户、GPU 和系统性的 idea 质量评估仍待完成。离线测试通过不能证明研究质量。

下一步重点是用真实主题评估能否产出值得做、可开始验证的 idea，而不是继续增加流程。参见 [架构](architecture.md) 和 [借鉴来源](sources.md)。
