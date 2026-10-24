# Research-idea

## 1. 我们的目的

**帮助研究者从 LLM、NLP、Agent 的相关文献中，形成一个值得研究、有实质新意、具备合理实现思路的 idea。**

你提供研究方向，也可以补充初步想法、参考论文和资源条件。系统阅读文献，理解已有工作解决了什么、还留下什么重要问题，再把背景、问题、动机和核心想法连成一条有说服力的论证。

最终内容直接回答：**新问题是什么、为什么重要、idea 怎样解决它。** 第一部分是核心研究 idea；第二部分围绕它提出两个技术角度，给出可借鉴的方法及改造理由。默认不展开具体例子和实验计划，也不执行训练或论文写作。

当前版本 **v0.3.0**，支持对话式 CLI、文献检索与正文分析、技术参考、讨论修订、论文链接与原文依据、预算管理和中断恢复。已使用 Codex CLI（`gpt-6.1-sol`、`high`）完成真实主题的端到端运行。

## 2. 找 idea 的核心要求

**以能够支撑 CCF-A 研究的完整思路为构思目标。** 问题的重要性、核心洞见、解决思路和预期贡献要一起成立；说明这项研究会让我们理解什么新现象、获得什么新能力，或突破什么关键限制。

**Motivation 是整个 idea 的核心。** 从背景的实际需要和已有工作留下的问题中，挖掘出“为什么需要开展这项研究”：现有办法依赖什么条件，为什么仍留下重要困难，因此需要理解什么关系或实现什么能力，以及做到之后为什么有意义。先把这项研究的理由讲清楚，再提出回应它的 idea。即使暂时拿掉具体技术的名字，读者仍应能理解这项研究为什么值得做。

**先把论文连成大逻辑，再形成 idea。** 围绕用户原本的大课题，归纳已有研究采用了哪些思路、共同推进了什么、为什么还留下值得研究的问题。论文里的数据集和实验场景提供依据；研究问题应指向有意义的能力、规律或学习过程。背景、问题和动机用详细、平实的中文讲清楚，让读者不用打开论文、查专业术语，也能理解为什么值得做。明确要求研究某个场景时，则遵循用户指定的范围。

**问题从两个角度引出。** 一是已有的重要问题，现有主要方法仍无法解决：解释这些方法为什么还跨不过关键障碍。二是现有方法在使用或发展过程中暴露出的新问题：解释它怎样产生、会影响什么，以及原有思路为什么解决不了。论文中的矛盾、假设和能力边界是发现这两类问题的线索；“某篇论文没测过一个因素”本身不能成为研究理由。由问题的根本原因推出动机，再提出能作用于这个原因的 idea。

1. **有意义、有新意，而且环环相扣。** 从背景中的实际需要出发，说明已有工作做到了什么、还存在什么问题、可能为什么发生、现有办法为什么仍不足，由此推导研究动机，再提出针对这个动机的 idea。问题本身要值得研究，即使后来需要更换解释或方法，其价值也应成立。新增模块、小幅提升、换一个场景或重新描述 trade-off，本身不足以构成实质贡献。
2. **看论文细节，判断具体贡献有没有重叠。** 阅读方法、实验条件和结果，区分作者的主张与实际支持的结论。比较已有方法完整的信息获取、主动探索和更新能力；相似标题、同类技术或相关主题不会直接否定 idea。方法可以借鉴，关键是新问题、新解释或新能力是否已经被回答，以及剩下的差异为什么重要。
3. **把能提前发现的可行性问题想清楚。** 说明谁能改变什么、需要哪些数据与信号、信息在什么时候可获得，以及核心思路怎样作用于问题。基本实施条件在第一阶段就推演；第二阶段再寻找适合的技术，包含其他计算机领域的可迁移方法。让方法有合理的实现路径，同时把研究假设和已有事实说清楚。

这些要求直接进入现有的选题、构思、技术设计和讨论修订。大胆提出想法，在比较中改进薄弱环节；不额外增加评分表、审批步骤或先完成实验的要求。CCF-A 是研究目标，生成结果的价值仍需后续研究检验。

## 3. 整体框架

```mermaid
flowchart TD
    U["输入研究方向、初步想法、论文与资源条件"]
    subgraph S1["第一阶段 · Background → Problem → Motivation → Idea"]
        A["检索近期文献，按相关性与时间筛选"]
        B["阅读正文：已有方法、实验支持、剩余问题"]
        C["跨论文梳理主线，从大问题中挖掘研究动机"]
        D["结合贡献对照与基本可行性，提出核心 idea"]
        A --> B --> C --> D
    end
    subgraph S2["第二阶段 · Idea → 两个技术角度 → 方法参考"]
        E["从 idea 推导两个需要解决的技术问题"]
        F["围绕问题寻找技术：复用已读材料，也探索相邻领域"]
        G["选择与改造方法，说明为什么适合当前 idea"]
        H["讨论关键判断，按预算完善思路"]
        E --> F --> G --> H
    end
    O["交付：核心 idea + 技术参考 + 相关论文与依据"]
    U --> A
    D --> E
    H --> O
    classDef concept fill:#eff6ff,stroke:#3b82f6,color:#172554
    classDef design fill:#f0fdf4,stroke:#22c55e,color:#14532d
    class A,B,C,D concept
    class E,F,G,H design
```

**第一阶段到提出 idea 结束。** 阅读与构思时就完成动机、贡献对照，形成 Background → Problem → Motivation → Idea 的连续解释。核心想法会在 CLI 和主报告中展开四点，让读者知道它具体怎样起作用：

1. **具体改变什么。** 谁使用哪些对象、关系或信号；说清关系连接什么、信号表达什么。
2. **这些信息怎样得到。** 从实际可获得的输入出发，说明如何构造、提取和核对所需信息。
3. **为什么能带来新的能力。** 把“执行什么操作 → 模型需要怎样学习、推理或行动 → 为什么能解决前面的困难”连起来。
4. **与最接近的方法差在哪里。** 考虑已有方法正常使用时已经能做什么，再说明本想法改变了哪个关键环节、为什么这一改变有意义。

**第二阶段服务于这个 idea 的实现。** 先明确两个互补的技术问题，再寻找方法，解释“借鉴什么、为什么适用、怎样为当前目的改造、两个角度如何共同起作用”。技术探索可以重新检索文献，也可以跨领域寻找思路。上述核心解释随 idea 进入第二阶段；讨论改变了想法时，同步更新解释，最终展示修订后的版本。四点在现有构思与修订步骤中完成，不增加审查调用或实验计划。

控制器组织检索、阅读和模型调用；八个内置研究 skill 按阶段提供分析指导。阅读者、设计者和讨论者通过论文分析卡、idea 与逐条回应协作，沿用项目选择的模型和预算。运行状态保存在 SQLite，报告输出为 Markdown 和 JSON。详见 [工作流](docs/workflow.md)、[架构](docs/architecture.md)与[开源思路借鉴](docs/sources.md)。

## 4. 安装与启动 CLI

需要 **Python 3.11+ 和 Git**。使用 Codex 或 Claude 后端时，先在同一个系统环境中安装并登录对应 CLI。

下面按系统选择一套步骤，安装一次，以后直接输入 `research-idea`。使用 [pipx](https://pipx.pypa.io/latest/how-to/install-pipx.html) 为命令管理独立环境，无需每次激活虚拟环境或进入仓库目录。

### macOS（终端）

先安装 Homebrew，然后执行：

```bash
brew install pipx poppler
git clone https://github.com/ghh1125/Research-idea.git
cd Research-idea
pipx install --editable .
pipx ensurepath
```

### Linux（Ubuntu / Debian）

先确认 `python3 --version` 为 3.11 或更高；Ubuntu 24.04+、Debian 12+ 可使用以下步骤：

```bash
sudo apt update
sudo apt install git python3-venv pipx poppler-utils
git clone https://github.com/ghh1125/Research-idea.git
cd Research-idea
pipx install --editable .
pipx ensurepath
```

Fedora 可用 `sudo dnf install git pipx poppler-utils` 安装工具，再执行同样的克隆和 pipx 命令。Windows 的 **WSL2** 也按对应 Linux 发行版安装；研究项目与所选模型 CLI 都放在 WSL 环境中使用。

### Windows（PowerShell）

先安装 Python 3.11+（含 `py` 启动器）和 Git，然后在 PowerShell 中执行：

```powershell
py -3 -m pip install --user pipx
git clone https://github.com/ghh1125/Research-idea.git
cd Research-idea
py -3 -m pipx install --editable .
py -3 -m pipx ensurepath
```

读取 PDF 需要 Poppler 的 `pdftotext`。Windows 可通过 [WinGet 中的 Poppler 包](https://github.com/microsoft/winget-pkgs/tree/master/manifests/o/oschwartz10612/Poppler)安装：

```powershell
winget install --id oschwartz10612.Poppler --exact --source winget
```

macOS、Linux 步骤已包含 PDF 工具。Windows 原生模型调用和中断恢复尚未完成端到端实机验证；目前实跑覆盖 macOS，自动化测试运行于 Linux。

### 安装后检查

三种系统都在安装后**关闭并重新打开终端**，让命令路径生效，再运行：

```bash
research-idea --version
research-idea doctor
```

`doctor` 会检查模型 CLI 与 `pdftotext` 是否可找到。如果仍提示找不到 `research-idea`，macOS/Linux 再运行 `pipx ensurepath`，Windows 再运行 `py -3 -m pipx ensurepath`，然后重新打开终端。

安装使用本地仓库的可编辑模式，请保留仓库目录。已有可用的虚拟环境或本地启动命令可以继续使用，无需重复安装。开发用的虚拟环境安装方式见 [进阶使用](docs/advanced-usage.md#虚拟环境安装)。

### 打开对话窗口

以后在终端输入：

```bash
research-idea
```

这会直接打开对话窗口，并在当前目录的 `research-projects/` 下新建一个项目。窗口内用 `/model` 选模型、`/reasoning` 调整思考强度、`/intro` 看介绍；输入研究方向讨论，准备好后输入 **`/run`** 开始研究。

需要打开指定项目或在启动时指定模型，可以使用：

```bash
research-idea chat --project ./research-projects/my-idea --backend codex --model gpt-6.1-sol --reasoning-effort high
```

再次运行相同的 `--project` 命令会打开原项目，保留对话、设置和进度；也可以在窗口内用 `/open 项目目录` 恢复已有研究。

希望逐项选择主题、模型、论文和预算时，运行 `research-idea launch`。

### 一条命令直接开始研究

```bash
research-idea start "如何设计帮助 LLM agent 持续学习的交互环境" \
  --project ./research-projects/agent-environment \
  --backend codex --model gpt-6.1-sol --reasoning-effort high \
  --literature-preset ai-recent \
  --max-papers 6 --max-candidates 1 --max-rounds 2 \
  --max-calls 80 --max-seconds 6600 --timeout-s 1200
```

只想体验离线流程时，运行 `research-idea demo --project ./research-projects/demo`。Demo 使用合成材料与确定性后端，不调用真实模型。

## 5. CLI 操作与参数设置

### 在窗口中讨论与研究

直接输入文字会与模型讨论，第一条消息默认成为研究主题。**`/run` 才开始正式检索与构思。** 运行时隐藏输入框，显示步骤输出和旋转指示；Ctrl+C 停止并保存进度，结束后恢复输入。每一步先显示主要发现，`/details` 可以展开完整分析。

| 过程标签 | 展示内容 |
| --- | --- |
| `[search]` / `[paper]` / `[read]` | 在找什么、选择了哪篇论文、正在阅读什么 |
| `[skill]` / `[analysis]` | 当前采用的分析方法与主要发现 |
| `[thinking]` | 等待模型回复；底部旋转指示与本步用时持续刷新 |
| `[concept]` | 第一阶段的背景、问题、动机与 idea |
| `[design]` / `[review]` | 两个技术角度、可借鉴方法与讨论修订 |
| `[evidence]` / `[idea]` | 论文依据与最终研究 idea |

论文引用直接显示**标题、文章链接和原文位置**，不需要查后台证据编号。当前显示的是步骤进展与分析结果，不是逐 token 的模型思考流。

### 最常用的操作

| 想做什么 | 在窗口中输入 |
| --- | --- |
| 看使用介绍 / 全部命令 | `/intro` / `/help`，介绍入口常驻底部 |
| 选择模型 / 思考强度 | `/model` / `/reasoning`，打开选择菜单 |
| 直接设置模型与强度 | `/model gpt-6.1-sol`，然后 `/reasoning high` |
| 沿用 Codex 配置 | `/model inherit` / `/reasoning inherit` |
| 看模型目录 / 登录方式 | `/models` / `/account` |
| 查看或修改研究主题 | `/topic` / `/topic 新方向` |
| 导入多行研究说明 | `/input /path/to/brief.txt` |
| 添加已有论文 | `/papers /path/to/paper.pdf`，支持带引号的空格路径 |
| 保存资源条件 | `/constraints 单张24GB GPU，两周，允许小规模微调` |
| 开始或恢复研究 | `/run`；运行时按 Ctrl+C 停止 |
| 查看方案 / 论文依据 | `/report` / `/evidence`；`/evidence 1` 展开指定依据 |
| 看详细过程 | `/details` 展开上一步，`/details on` 持续显示完整输出 |
| 查看设置 / 进度 | `/config` / `/status` |
| 查看 / 修改保存位置 | `/output` / `/output /path/to/results`；`/output default` 恢复默认 |
| 新建研究 / 打开旧项目 | `/new 新方向` / `/open 项目目录` |
| 退出 | `/exit` 或 Ctrl+D |

Enter 发送；先按 Esc 再按 Enter 换行；Tab 补全命令；↑↓ 浏览输入历史。多行粘贴作为一条输入处理。

### 文献范围与日期

| 设置 | 命令 |
| --- | --- |
| 近期会议 + CS arXiv | `/scope ai-recent` |
| 只使用本地资料 | `/scope local` |
| 查看 / 调整 arXiv 日期与会议届次 | `/date` |
| arXiv 动态窗口：技术 12 个月、动机对照 6 个月 | `/date rolling 12 6` |
| 会议采用最新公开的一届（默认） | `/date conference latest` |
| 会议也限定在日期窗口内 | `/date conference window` |
| 所有来源采用固定发表日期范围 | `/date fixed 2025-01-01 2026-10-23` |
| 查看 / 选择会议 | `/venues` / `/venues ACL EMNLP COLM ICLR` |

**会议与 arXiv 分开处理时间。** arXiv 默认按运行当天更新窗口：背景与技术探索看近 12 个月，第一阶段动机与贡献对照关注近 6 个月，并限定 CS 范围。会议默认查看每个会议最新已经公开或收录论文的一届；本届尚未公开就取上一届，不会因为会议周期超过半年而被排除。不同会议可以采用不同年份，仍按研究相关性筛选，不为填满会议名单而精读无关论文。

**围绕同一问题，优先参考较新届次。** 例如，2026 届优先于 2025 届；较早论文用于补足关键方法、研究脉络和必要对照。排序采用已核实的会议年份，不会把会议论文较早上传 arXiv 的时间误当成会议年份。CLI 会同时显示论文标题、会议届次和链接。

`/date fixed` 会让会议和 arXiv 都使用指定日期范围。也可随后运行 `/date conference latest`，让会议按截止日期查找最新公开一届。`/scope ai-recent` 恢复默认的“最新会议届次 + arXiv 动态窗口”。已读资料及显式导入的经典论文仍可使用。

`ai-recent` / `ai-recommended` 的会议范围包含 **NeurIPS、ICML、ICLR、ACL、EMNLP、NAACL、COLM、AAAI、IJCAI、AAMAS、KDD、ICDM、ICDE、SIGMOD、VLDB、ACM MM、CVPR、ICCV、SIGIR、WWW**。先按主题、相关性与时间筛选，再决定精读哪些论文；会议名单不代表每篇都要阅读。已有项目可用 `/scope ai-recent` 更新范围，完整分级与来源见 `research-idea venues`。

### 预计耗时与模型调用

以 **`gpt-6.1-sol / high`、最多精读 6 篇论文、生成 1 个 idea、最多 2 轮方案讨论（初版加一次修订）** 估算，首次完整研究可按以下范围预留：

| 项目 | 预估 |
| --- | --- |
| 总耗时 | **约 1–2 小时** |
| 模型调用次数 | **约 30–60 次** |

这里的一轮完整研究包含文献检索与筛选、正文分析、第一阶段的 idea 构思，以及第二阶段的技术参考与讨论修订。论文篇幅、补读数量、模型响应速度和修订需求都会影响耗时与调用次数。已有成功检查点可以复用，恢复运行时只计算剩余工作。

正文按块阅读；构思时使用论文分析和原文依据。检索请求日志压缩为覆盖摘要，章节清单保留位置标识与阅读覆盖，完整记录仍保存在项目中，原文引文和适用条件完整保留。`[context]` 会显示主要构思步骤的输入字符数；它不是 token 数，也不是账户上下文上限。

**预估用量与预算上限不同。** 默认的 80 次调用、110 分钟是可调整的累计上限，不是固定耗时或必须用满的调用数。希望预留完整两小时，可设置 `/budget max_seconds 7200`；预算用完后也可提高上限，再输入 `/run` 继续。

### 预算与恢复

| 设置 | 命令 | 新建对话项目的默认值 |
| --- | --- | --- |
| 每个查询召回的论文元数据数 | `/budget search_results_per_query 20` | 20 |
| 全流程精读上限 | `/budget max_papers 6` | 6，通常第一阶段最多 3 篇，第二阶段补充最多 3 篇 |
| Idea 数量 | `/budget max_candidates 1` | 1 |
| 方案讨论轮数 | `/budget max_rounds 2` | 2，初版加一次修订 |
| 模型调用上限 | `/budget max_calls 80` | 80 |
| 累计运行时间（秒） | `/budget max_seconds 6600` | 110 分钟 |
| 单次模型调用超时（秒） | `/budget timeout_s 1200` | 20 分钟 |

底部的 **“调用 3/80”表示本项目累计使用了 3 次模型调用，上限为 80 次**，不是论文数量。讨论、研究、结构化输出修复和失败重试共享预算；达到预算后可以提高上限并继续。

清空输入、退出或重新打开项目都会保留累计用量。**`/new` 才开始计数为零的新研究**，并沿用当前模型、日期与预算设置。原项目保留，可用 `/open` 返回。

### 错误提示与重试

模型服务出错时，窗口会显示具体类别：`[network]` 网络连接、`[timeout]` 超时、`[api]` 接口请求、`[model]` 模型不可用或无权限、`[auth]` 登录认证、`[quota]` 余额或额度不足、`[rate_limit]` 限流，以及服务端异常。余额不足和限流会根据服务商返回的信息区分。

**首次失败后，每隔 30 秒重试一次，最多重试 10 次（共最多 11 次尝试）。** `[retry]` 显示原因、等待时间和次数；成功后显示 `[recovered]`，继续当前步骤。重试始终沿用所选模型、思考强度和本次任务材料。

仍失败时，`[error]` 提示原因并结束当前任务，对话窗口恢复输入。已完成的分析和进度会保留，处理问题后可用 `/run` 继续研究；普通对话可以重新发送消息。等待期间可按 Ctrl+C 停止。每次尝试计入调用预算，等待时间计入累计时间；预算不足时会提前停止，不会额外超支调用。

### 结果保存位置

从源码安装时，结果默认自动保存在 **Research-idea 代码目录下的 `idea-时间戳/`**，例如 `idea-20261024-193304-123456/`。从其他目录输入 `research-idea` 启动也使用这个位置。

```text
/output                       查看当前保存位置
/output ~/research-results    修改保存父目录
/output default               恢复默认位置
```

Windows 也可以直接输入 `/output D:\ResearchResults`；带空格的路径可加引号。**只能修改父目录，文件夹名由程序自动生成。** 同一项目继续运行、恢复或导出时沿用原文件夹名；`/new` 会生成新的时间戳文件夹，并沿用当前保存位置。修改位置会把已有结果重新导出到新位置，原文件保留；`/report` 会读取新位置。

文件夹包含 `report.md`（主方案）、`report.json`（结构化结果）、各 idea 的详细 Markdown 和 `papers/`（论文分析卡）。配置、原始材料、对话和 SQLite 检查点仍保存在研究项目目录。旧版 `outputs/` 中的报告仍可查看，下一次导出会使用新的命名规则。非源码安装没有代码仓库时，默认使用启动目录；可以用 `/output` 指定固定位置。

### 命令行参数与项目配置

| 参数 | 用途 |
| --- | --- |
| `--project PATH` | 指定项目目录，保存配置、材料、对话和检查点 |
| `--output PATH` | 指定结果父目录；文件夹固定命名为 `idea-时间戳` |
| `--backend codex --model MODEL_ID` | 选择后端和模型 |
| `--reasoning-effort high` | 设置 Codex 思考强度；`inherit` 沿用原配置 |
| 主题位置参数 / `--topic-file ./brief.txt` | 直接输入主题或使用 UTF-8 文件，二选一 |
| `--papers ./papers paper.pdf` | 导入 PDF、TXT、Markdown、论文 JSON 或目录 |
| `--constraints "资源条件"` | 记录设备、时间和数据等条件 |
| `--literature-preset ai-recent` | 使用近期会议与 CS arXiv |
| `--date-mode rolling --strategy-months 12 --novelty-months 6` | 设置 arXiv 动态窗口；会议时间策略单独选择 |
| `--conference-policy latest` / `--conference-policy window` | 会议按最新公开一届，或按日期窗口筛选 |
| `--since YYYY-MM-DD --until YYYY-MM-DD` | 设置固定日期范围，会议默认也按此窗口；可显式传入 `--conference-policy latest` |
| `--venues ACL COLM` / `--arxiv-categories cs.CL cs.AI` | 指定会议或 arXiv 分类 |
| `--max-papers` / `--max-candidates` / `--max-rounds` | 设置论文、idea 与讨论轮数上限 |
| `--max-calls` / `--max-seconds` / `--timeout-s` | 设置调用与时间上限 |
| `--skill /path/to/SKILL.md` | 附加本地 skill，可重复传入；内置八个 skill 默认启用 |
| `--no-search` | 使用已有资料，跳过联网检索 |
| `--setup-only` | 仅保存配置并导入资料，暂不调用模型 |

上表汇总不同命令的参数；完整支持范围用 `research-idea start --help` 或 `research-idea chat --help` 查看。设置保存在项目的 `research.toml` 中，`resume` 会沿用它们。例如：

```toml
backend = "codex"
model = "gpt-6.1-sol"
reasoning_effort = "high"
conference_policy = "latest"
max_papers = 6
max_candidates = 1
max_rounds = 2
max_calls = 80
max_seconds = 6600
timeout_s = 1200
```

```bash
research-idea resume --project ./research-projects/my-idea
research-idea status --project ./research-projects/my-idea
```

结果位置可随时用 `/output` 查看。成功任务可以缓存；只修改保存位置不会重新调用模型，材料或相关研究设置变化时才重新计算。文献导入格式、skill 选择、引文处理和恢复细节见 [进阶使用](docs/advanced-usage.md)。

## 6. 可以绑定的模型与后端

项目不固定某一个模型。**选择后端，再指定该后端和账户实际支持的模型 ID；同一轮研究默认沿用同一个后端与模型。**

| 后端 | 如何选择模型 | 认证与适用范围 |
| --- | --- | --- |
| **Codex CLI**：`--backend codex` | `--model MODEL_ID` 或窗口中的 `/model`；留空则继承 Codex 配置 | 沿用本地 Codex 登录；支持项目内设置思考强度。已实跑 `gpt-6.1-sol` + `high` |
| **Claude Code CLI**：`--backend claude` | `--model MODEL_ID`；留空则继承 Claude CLI 配置 | 沿用本地 Claude 登录；需要支持适配器参数的 CLI 版本 |
| **OpenAI-compatible API**：`backend = "api"` | 在项目配置中填写服务支持的 `model` | 支持 `/chat/completions` 和严格 JSON Schema 的云服务或本地兼容服务 |
| **Anthropic API**：`backend = "api"` | 指定 `api_provider = "anthropic"` 与支持结构化输出的模型 | 使用原生 `/messages` 协议，通过环境变量提供密钥 |

### Codex 模型与思考强度

```bash
research-idea chat --project ./research-projects/my-idea \
  --backend codex --model gpt-6.1-sol --reasoning-effort high
```

进入窗口后随时通过 `/model` 和 `/reasoning` 调整。程序接受 `none/minimal/low/medium/high/xhigh/max/ultra`，具体可用档位以所选模型和 CLI 为准；`inherit` 表示继承。设置只覆盖本项目的调用，不修改 Codex 全局配置。

`/models` 查看本地模型缓存，`/account` 查看后端、模型、配置档与登录方式。模型缓存不是账户的实时授权列表，实际调用由后端处理。当前思考强度参数仅支持 Codex；切换到其他后端时使用 `--reasoning-effort inherit`。

需要已有 Codex profile 时，启动命令附加 `--codex-profile research`；需要指定可执行文件时附加 `--codex-bin /path/to/codex`。认证由 Codex 管理，Research-idea 不复制登录文件或显示密钥。

### API 模型配置

在项目的 `research.toml` 中设置：

```toml
backend = "api"
api_provider = "openai-compatible"
base_url = "https://api.openai.com/v1"
api_key_env = "RESEARCH_API_KEY"
model = "填写服务支持的模型ID"
reasoning_effort = ""
max_output_tokens = 8192
api_max_tokens_field = "max_completion_tokens"
```

在终端环境中设置 `RESEARCH_API_KEY` 后，运行 `research-idea chat --project 项目目录` 或 `research-idea run --project 项目目录`。密钥通过环境变量读取，配置文件只保存变量名。

使用原生 Anthropic 时，将 `api_provider` 改为 `anthropic`，`base_url` 改为 `https://api.anthropic.com/v1`，`api_key_env` 改为 `ANTHROPIC_API_KEY`，并填写对应模型 ID。详细协议、CLI 兼容要求与本地服务配置见 [后端配置](docs/advanced-usage.md#后端配置)。

目前真实账户验证覆盖 Codex，其余适配器已有协议测试。开发者可运行 `PYTHONPATH=src python -m unittest discover -s tests -v`；自动化测试覆盖 Python 3.11、3.12、3.13。
