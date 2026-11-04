# v0.8.0 Web 设计预览（历史归档）

[![English](https://img.shields.io/badge/Language-English-blue)](README.md) | **简体中文**

> 当前 Web 已接通真实研究，请参阅[本地研究工作台](../web-workbench.zh-CN.md)。本页保留早期预览的状态说明；下文“尚未连接”的描述仅指当时的预览版本。

## 启动

安装或升级后，在终端输入：

```bash
research-idea web
```

浏览器自动打开 <http://127.0.0.1:8769/>；Ctrl+C 停止服务。macOS、Linux、Windows 使用相同命令，不需要进入仓库目录。

```bash
research-idea web --no-browser --port 8770
research-idea web --codex-profile research
research-idea web --help
```

`--codex-bin` 可指定 Codex 可执行文件。服务只监听本机回环地址。旧的 `python -m http.server` 只能展示静态页面，不能读取本机模型，请使用上述入口。

## 界面

- 左侧：选择已有对话、增加新对话；草稿保存在当前浏览器。
- 中间：对话内容、输入框及当前阶段进度；已完成步骤用“查看详情”打开弹窗。
- 右上角：系统设置弹窗。模型和思考深度下拉选择；文献范围、预算、保存目录和 skill 按需展开。
- 讨论阶段：发送用于讨论、纠正或要求补查文献；“继续”推进到下一阶段。方向讨论后深入问题，问题讨论后整理研究主张；不在每篇论文后停下来确认。
- 关闭设置或详情弹窗、切换对话后，未发送的草稿保留。顶部测试用的“预览阶段”已移除。
- 过程详情按检索、阅读、skill、问题比较、本轮修改、调用与运行展示；每项说明输入、做了什么及对当前讨论的作用。Skill 原文读取当前安装版本，不是复制在页面里的示例文本。

## 预览时已连接与待接入的功能

**Codex 模型发现已经真实连接。** 打开页面读取本地模型缓存；“刷新模型”通过 `codex app-server` 的 `model/list` 接口读取完整目录，处理分页并显示来源。模型 ID、显示名称和思考强度来自返回数据，没有固定为一个模型。失败时保留上次列表和当前选择。配置档单独读取，避免把默认配置的缓存当成指定配置结果。

读取目录不启动推理，也不向浏览器返回凭据。目录不代表账户一定有推理权限，Codex 自身也可能使用缓存目录。见[官方协议](https://learn.chatgpt.com/docs/app-server#list-models-modellist)。

**预览时的研究流程仍是交互演示，尚未连接真实研究任务、项目存储、账户检查或其他后端的模型目录。** 浏览器草稿不能替代 CLI 项目；当时真实研究使用 `research-idea`。可在“系统设置 → 项目、资料与使用介绍 → 使用介绍 → 看看演示”体验讨论、详情和继续操作。

实现入口：[`web.py`](../../src/research_idea/web.py)、[`model_discovery.py`](../../src/research_idea/model_discovery.py)、[`web_assets/index.html`](../../src/research_idea/web_assets/index.html)。原有 CLI 的研究、证据、记忆和预算处理保持不变。
