# Research-idea

从一个 LLM/NLP 研究主题出发，建立文献证据、提出机制假设、检查最近工作和实施前提，输出能开始验证的研究方案。

**定位：只辅助构思和筛选有意义、具备明确实施路径的 LLM/NLP 研究 idea。** 最小实验只输出验证计划；系统不执行训练、实验或论文写作。

**当前版本：可运行的早期 MVP。** 支持 Codex CLI、Claude Code CLI、OpenAI-compatible API 和原生 Anthropic API。研究流程和证据存储独立于模型会话。生成的方案不自动等于创新、可行或有效。

## 三个核心要求

1. **说明问题为何值得研究，以及方法为什么必要。** 候选从有证据的问题现象出发，解释问题的重要性、现有方法的局限和因果假设，连接到拟议方法及预期进展；同时列出最简单替代方案，以及判断复杂方法是否必要的测试。贡献主张要说明属于机制、解释、边界、效率还是评测，改变什么变量、预期观察到什么、什么结果会推翻它。审阅分别判断问题意义、因果联系和进展是否实质，保留增量改进与不明确的判断，不能只因换了模块或产生数值提升就认定创新。
2. **最近工作必须逐项对照。** 每篇相关工作按问题、机制、可用信息、目标、评测、核心主张六个维度列出现有方法与候选方案，并绑定原文证据；相同、不同、未知分别记录。针对候选选出的最多三篇最近工作全文补读方法与成立条件，摘要不作为这一步的精读材料。
3. **可行性必须落到操作前提。** 检查数据访问、推理信号、接口、学习信号、计算资源、评测和最小测试七个维度；逐个说明所需信号在训练、推理还是评测阶段使用、是否已可获得、如何获取以及缺失时怎么办。尤其不能把评测答案当成推理时可用信息。

报告会保留待核实（pending）与阻塞（blocked）的前提、证据缺口和具体检查动作。可行性状态分别为 `prerequisites_unverified`（前提待核实）、`blocked`（前提阻塞）或 `specified_not_executed`（规格明确但未执行）；有阻塞或待核实项时，优先建议解决这些前提。填完整表格、模型审阅通过或验证计划足够详细，都不代表真实研究已经验证；未执行的研究方案仍为 `untested`。系统不能自动裁定一项主张是否具有实质创新或发表价值。

## 研究流程

1. **输入想研究什么及资源约束。** 先明确科学问题与范围假设，规划英文检索词。
2. **检索并深读。** 读取正文中的方法、实验、结果与可用附录，抽取带原文位置的证据；记录未读取和获取失败的部分。
3. **审计论文主张。** 分开记录作者说了什么、在哪些任务/数据/模型/预算下测试、结果能支持什么。缺失对照、混杂因素与过度推广都有明确依据或待核查标记，不能猜测作者意图。
4. **头脑风暴。** 从真实问题、竞争解释、成立条件和证据矛盾构建有意义的候选，不以堆叠模块作为创新。
5. **围绕每个 idea 再检索、深读和比较。** 用候选机制及假设搜索最近工作，逐项比较六个维度，区分既有机制与未证明的效果。全文中的作者主张也不能单独支持“问题已经解决”；`covered` 还要求评测维度有全文报告结果。证据不足不会把旧机制变成新机制。
6. **检查实施前提并有界修订。** 输出具体操作、最弱假设的最小验证计划、正/负/不明确结果的解释。每轮保存原始问题锚点、上轮质疑、变化字段和新证据；内容与证据都未变化时停止重复修订并保留候选。

第一版分析论文，不自动检查代码或执行科学实验。论文分析能提前发现不可用的推理信号、泄漏、接口矛盾和不公平比较，却不能证明一个新方法一定有效。`no_detectable_progress` 只是逐字段精确比较发现重复，不代表语义上判定研究没有价值。

## 快速开始

需要 Python 3.11+。核心运行时只使用 Python 标准库；PDF 导入另外需要 Poppler 的 `pdftotext`。优先在 Linux/macOS 使用，Windows 的进程清理仍需实际环境验证。

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

不安装包也可以运行：

```bash
PYTHONPATH=src python -m research_idea demo --project ./research-projects/demo
```

## 本地 Codex 与两类 skill

`research-idea` 调用你机器上的 Codex CLI，沿用 Codex 自己管理的登录、模型及用户配置，不要求为 Codex 模式另外提供 API key。可用 `codex login status` 确认当前登录方式：ChatGPT 登录使用该账户对应的订阅额度与限制；API key 登录按 API 方式计费。本工具不读取剩余额度、不复制登录凭据，也不会自动把 API 登录改成订阅登录。实际认证以 Codex 为准；例如继承的 `CODEX_API_KEY` 可覆盖已保存登录方式。当前开发环境没有安装真实 Codex，所以真实账户兼容性仍需本机确认。可先运行 `research-idea doctor` 查看命令路径。

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

推荐把 CCFA idea optimizer/reviewer、experiment designer 作为补充，按需要显式附加它们的具体参考文件。系统内置七个 skill 为项目自主编写，未打包第三方代码或文档；ARIS/CCFA 的设计借鉴见 [来源](docs/sources.md)。

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
- 支持 ACL、AAAI、IJCAI、NeurIPS、ICML、CVPR、ICCV，也支持 EMNLP、NAACL、COLM 和 ICLR。`ccf-a-ai-2022` 是明确带年份的 **CCF 2022 人工智能 A 类会议子集**；不代表全部 CCF-A 或实时评级。默认不限会议的检索也可返回其他出版来源。
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

使用 `claude --safe-mode -p`、JSON Schema、禁用内置工具与 MCP 的设置。需要支持这些参数的版本；保留现有认证。CLI 的工具循环不负责当前 MVP 的文献检索，检索与读取由研究控制器执行。

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

## 研究流程与可靠性边界

1. 导入/检索来源，按 DOI/arXiv 等标识去重；不按标题相似就合并论文。
2. 提取可定位的原文证据，记录来源类型、条件、页/行/字符位置。
3. 建立问题、竞争解释和关键未知项。
4. 生成有问题动机、因果解释、方法必要性、预测和反例的候选。
5. 对候选关联的最近工作全文定向补读，提取方法细节及成立条件。
6. 写明贡献主张，完成六维最近工作对照、七维可行性检查和信号阶段说明。
7. 用独立任务提出具体质疑；在预算内修订或按明确查询补充文献。
8. 保存方案、版本、待核实/阻塞项与下一步验证动作。

每次来源抽取最多保存六条证据。候选定向补读使用 `closest_work_ids` 中最多三篇 `full_text` 来源，每篇再抽取最多六条与该候选有关的方法/条件证据；摘要和笔记跳过此步骤，不能被升级成全文证据。长文仍按 `source_chars` 预算选取开头及方法/结果等原文片段，并标记 `partial`；这是有限的定向补读，不是穷尽全文的精读保证。原文匹配只证明引文存在，不证明模型解释完全受到引文支持。只凭摘要不能确认核心主张已被覆盖；全文引文支持的重叠也仍需人工判断语义与条件。

研究审阅默认使用同一个配置后端的独立任务，不能称为跨模型独立验证。审阅指出的阻塞、待修订和轮数用尽会单独记录。模型“继续”意见不提升实验证据状态，所有未执行方案保持 `untested`。

## 预算与恢复

```toml
max_candidates = 3
max_rounds = 2
max_papers = 12
max_calls = 40
max_seconds = 3600
timeout_s = 180
source_chars = 24000
auto_search = true
constraints = "单张24GB GPU；两周；允许小规模微调；禁止调用推理时真实答案"
```

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
research-idea inspect --project ./research-projects/conflict --events
research-idea export --project ./research-projects/conflict
```

输出位于项目的 `outputs/report.md`、`report.json` 和各候选 Markdown 文件。JSON 报告的 `schema_version` 为 `3`，包含问题—动机—方法的论证、贡献主张、逐篇六维对照、七维可行性检查、所需信号及其阶段，以及 `feasibility_status`、`comparison_gaps` 和 `feasibility_assessment`。还包含 `search_plans`、`paper_claim_audits` 和每版本的 `revision_record`；主张审计的结论是基于原文的模型判断，不是独立复现。运行数据库为 `research.sqlite3`；研究材料与运行目录不要提交到源码仓库。

## 开发与测试

```bash
PYTHONPATH=src python -m unittest discover -s tests -v
```

测试覆盖证据定位、引用一致性、断点恢复、预算、CLI 协议、API 本机 HTTP、超时、文献解析、本地 skill 和缓存失效。开发环境未安装 Codex/Claude CLI，未连接真实模型账户、远程学术搜索或 GPU；这些真实环境联调仍需完成。离线测试通过不能证明生成 idea 的研究质量。

下一步重点：真实主题质量评测、更细粒度的全文定位与覆盖审计，以及最小验证计划的区分能力。参见 [架构](docs/architecture.md) 和 [借鉴来源](docs/sources.md)。
