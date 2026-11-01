# v0.8.0 Web interface preview / Web 界面预览

This is an interactive design preview, not a working research frontend. Version v0.8.0 includes this preview alongside the working CLI. Model discovery, account checks, search, research runs, and project persistence are demonstrated with sample data; they are not connected to the CLI backend.

这是 v0.8.0 的交互设计预览。v0.8.0 同时保留可运行的 CLI；此页面尚未接入研究引擎、模型自动获取、账户检测或真实项目存储。按钮用于体验交互，不会发起研究调用。

## Open locally / 本地查看

From the repository root / 在仓库根目录运行：

```bash
python -m http.server 8769 --bind 127.0.0.1 --directory docs/web-preview
```

Open <http://127.0.0.1:8769/> in your browser. Stop the preview server with Ctrl+C. You can also open `index.html` directly. `research-idea web` is a proposed future command and is not implemented yet.

在浏览器打开 <http://127.0.0.1:8769/>；Ctrl+C 关闭预览服务。也可以直接打开 `index.html`。页面中的 `research-idea web` 是拟议入口，目前尚未实现。

## Interaction / 交互设计

- **Start with a conversation.** Enter a topic, optionally attach materials, and start. Research pauses for discussion; continue chatting or press Continue when ready. 首页只展示输入、添加材料和开始；讨论阶段可以反复追问，再按“继续”推进。
- **Choose models from a dropdown.** The planned backend reads the available model list from the selected provider or local CLI, with Refresh and a source/status indication. Keep the current choice if discovery fails; distinguish cached results from live availability. No model ID entry is required. 模型自动读取并下拉选择，思考深度同样下拉选择；示例列表不代表账户实时权限。
- **Keep supporting material nearby.** Papers and source links, the research proposition, active notes, and conversation history live under Research materials. “研究资料”保留文献、原文依据、研究主张、要点和完整对话。
- **Use defaults first.** Model/account settings are visible first; literature sources, dates, venues, reading limits, budgets, output paths, skills, and diagnostics remain under More settings. 默认配置即可开始，其他能力按需展开。
- **Make progress clear.** Show the current activity, usage, stop/resume actions, and retry feedback. The stage selector above the app is a preview control, not part of the proposed product. 运行中显示步骤、用量、停止及重试状态；顶部“预览阶段”只用于体验不同状态。

The Web frontend should reuse the CLI research engine, evidence handling, conversation memory, budgets, and project storage. This change adds the design only and does not modify those functions.

正式 Web 前端应复用现有 CLI 的研究流程、证据处理、对话记忆、预算和存储。本次提交只保存界面设计，不修改核心功能。

## Files / 文件

- `index.html`: standalone browser preview / 可直接打开的预览。
- `source.html`: editable interface fragment / 可编辑的界面源文件。

The standalone preview includes its display wrapper and may load display assets from a CDN. Selected files and chat text are used only in the current browser preview; do not use this page as a research project store.
