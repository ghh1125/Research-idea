# Research Agent CLI

从一个 LLM/NLP 研究主题出发，建立文献证据、提出机制假设、检查最近工作和实施前提，输出能开始验证的研究方案。

**当前版本：可运行的早期 MVP。** 支持 Codex CLI、Claude Code CLI、OpenAI-compatible API 和原生 Anthropic API。研究流程和证据存储独立于模型会话。生成的方案不自动等于创新、可行或有效。

## 三个核心要求

1. **说明问题为何值得研究，以及方法为什么必要。** 候选从有证据的问题现象出发，解释问题的重要性、现有方法的局限和因果假设，连接到拟议方法及预期进展；同时列出最简单替代方案，以及判断复杂方法是否必要的测试。贡献主张要说明属于机制、解释、边界、效率还是评测，改变什么变量、预期观察到什么、什么结果会推翻它。审阅分别判断问题意义、因果联系和进展是否实质，保留增量改进与不明确的判断，不能只因换了模块或产生数值提升就认定创新。
2. **最近工作必须逐项对照。** 每篇相关工作按问题、机制、可用信息、目标、评测、核心主张六个维度列出现有方法与候选方案，并绑定原文证据；相同、不同、未知分别记录。针对候选选出的最多三篇最近工作全文补读方法与成立条件，摘要不作为这一步的精读材料。
3. **可行性必须落到操作前提。** 检查数据访问、推理信号、接口、学习信号、计算资源、评测和最小测试七个维度；逐个说明所需信号在训练、推理还是评测阶段使用、是否已可获得、如何获取以及缺失时怎么办。尤其不能把评测答案当成推理时可用信息。

报告会保留待核实（pending）与阻塞（blocked）的前提、证据缺口和具体检查动作。可行性状态分别为 `prerequisites_unverified`（前提待核实）、`blocked`（前提阻塞）或 `specified_not_executed`（规格明确但未执行）；有阻塞或待核实项时，优先建议解决这些前提。填完整表格、模型审阅通过或实验脚本成功退出，都不代表真实研究已经验证；未执行的研究方案仍为 `untested`。系统不能自动裁定一项主张是否具有实质创新或发表价值。

## 快速开始

需要 Python 3.11+。核心运行时只使用 Python 标准库；PDF 导入另外需要 Poppler 的 `pdftotext`。优先在 Linux/macOS 使用，Windows 的进程清理仍需实际环境验证。

```bash
git clone https://github.com/ghh1125/Research-idea.git
cd Research-idea
python -m venv .venv
source .venv/bin/activate
python -m pip install -e .

research --help
research doctor
research demo --project ./research-projects/demo
research inspect --project ./research-projects/demo
```

`demo` 使用明确标注的合成笔记和确定性后端，不联网、不调用真实模型，不产生科学结论。它演示证据抽取、问题建模、候选发展、质疑、修订、保存和报告导出。重复运行 `resume` 会复用已校验的检查点：

```bash
research resume --project ./research-projects/demo
```

不安装包也可以运行：

```bash
PYTHONPATH=src python -m research_agent demo --project ./research-projects/demo
```

## 使用自己的主题和论文

先建立独立项目，选择后端。CLI 后端需要用户已在本机完成安装和认证。

```bash
research init "长上下文中的证据冲突" \
  --project ./research-projects/evidence-conflict --backend codex

research add --project ./research-projects/evidence-conflict ./papers/paper.pdf
research add --project ./research-projects/evidence-conflict ./notes/reading.md

research run --project ./research-projects/evidence-conflict --no-search
```

推荐先提供 5–10 篇核心论文全文。没有本地文献时可以从主题自动发现摘要：

```bash
research run "长上下文中的证据冲突" \
  --project ./research-projects/conflict --backend claude

research search "conflicting evidence language models" \
  --project ./research-projects/conflict --source arxiv --limit 10
```

`search` 支持 `arxiv` 和 `openalex`，网络和服务可用性取决于运行环境。OpenAlex 的凭据要求可能因服务策略变化而不同；可用 `search_api_key_env` 指定环境变量。搜索只导入元数据和摘要，不自动下载全文。模型输出中的检索建议不等于已经执行过的检索。

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

模型为空时沿用 CLI 的模型选择，也可 `research run --project PATH --model MODEL_ID`。适配器使用非交互执行、只读沙箱和结构化输出；禁用研究任务不需要的内置执行/搜索能力。发送研究材料前检查 MCP 清单：存在启用或未知的外部 MCP 配置时明确停止，请使用单独认证的干净 Codex 配置。程序不修改现有认证或全局设置。不兼容的 CLI 版本会报错，不会退化为假结果。

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

在终端中设置 `RESEARCH_API_KEY`，然后运行 `research run --project PATH`。使用 `/chat/completions` 与严格 `json_schema` 输出；自定义服务必须支持该协议。旧服务如果使用 `max_tokens`，可调整 `api_max_tokens_field`。不支持严格 schema 时明确报错，不会静默改成自由文本。

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
research status --project ./research-projects/conflict
research resume --project ./research-projects/conflict
research inspect --project ./research-projects/conflict
research inspect --project ./research-projects/conflict EVIDENCE_OR_IDEA_ID
research inspect --project ./research-projects/conflict --events
research export --project ./research-projects/conflict
```

输出位于项目的 `outputs/report.md`、`report.json` 和各候选 Markdown 文件。JSON 报告的 `schema_version` 为 `2`，包含问题—动机—方法的论证、贡献主张、逐篇六维对照、七维可行性检查、所需信号及其阶段，以及 `feasibility_status`、`comparison_gaps` 和 `feasibility_assessment`。运行数据库为 `research.sqlite3`；研究材料与运行目录不要提交到源码仓库。

## 显式运行最小实验

当前版本提供本地执行器，**不自动编写或执行模型生成的实验代码，不自动申请 GPU**。用户先检查脚本和实验规格，再显式运行。执行器不是安全沙箱，只运行你信任的代码。

```bash
research experiment --project ./research-projects/demo \
  examples/toy-experiment.json --check-only

research experiment --project ./research-projects/demo \
  examples/toy-experiment.json
```

示例只是基础设施验证，不是 LLM/NLP 科学实验。真实规格采用：

```json
{
  "argv": ["python", "experiment.py"],
  "cwd": ".",
  "timeout_s": 600,
  "metrics_file": "metrics.json",
  "protected_files": ["evaluate.py"]
}
```

`cwd` 相对规格文件；指标和保护文件相对工作目录。执行时不用 shell，超时清理子进程，保留 stdout/stderr 与结果。旧指标、失败进程残留指标、非法数值或评测文件变化都不能当作有效结果。文件散列只能发现前后变化，不是防篡改沙箱。`scientific_status` 始终为 `unreviewed`，不会因为进程退出码为 0 就认定假设成立。

## 开发与测试

```bash
PYTHONPATH=src python -m unittest discover -s tests -v
```

测试覆盖证据定位、引用一致性、断点恢复、预算、CLI 协议、API 本机 HTTP、超时、文献解析和实验完整性。开发环境未安装 Codex/Claude CLI，未连接真实模型账户、远程学术搜索或 GPU；这些真实环境联调仍需完成。离线测试通过不能证明生成 idea 的研究质量。

下一步重点：真实主题质量评测、更细粒度的全文定位与覆盖审计、实验结果到主张的解释回路，以及实测校准的候选选择。参见 [架构](docs/architecture.md) 和 [借鉴来源](docs/sources.md)。
