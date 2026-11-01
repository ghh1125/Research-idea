# v0.8.0 Web

## 启动 / Start

安装或升级后，在终端输入 / After installation or upgrade:

```bash
research-idea web
```

浏览器自动打开 <http://127.0.0.1:8769/>；Ctrl+C 停止服务。macOS、Linux、Windows 使用相同命令，不需要进入仓库目录。

The browser opens <http://127.0.0.1:8769/> automatically. Press Ctrl+C to stop the server. The same command works on macOS, Linux, and Windows from any directory.

```bash
research-idea web --no-browser --port 8770
research-idea web --codex-profile research
research-idea web --help
```

`--codex-bin` can select a local Codex executable. The service binds only to loopback. The old `python -m http.server` command cannot discover models; use the command above.

`--codex-bin` 可指定 Codex 可执行文件。服务只监听本机。旧的 `python -m http.server` 只能展示静态页面，不能读取本机模型，请使用上述新入口。

## 界面 / Interface

- 左侧：选择已有对话、增加新对话；草稿保存在当前浏览器。
- 中间：对话内容、输入框及当前阶段进度；已完成步骤用“查看详情”打开弹窗。
- 右上角：系统设置弹窗。模型和思考深度下拉选择；文献范围、预算、保存目录和 skill 按需展开。
- 讨论阶段：发送用于讨论、纠正或要求补查文献；“继续”推进到下一阶段。方向讨论后深入问题，问题讨论后整理研究主张；不在每篇论文后停下来确认。
- 关闭设置或详情弹窗、切换对话后，未发送的草稿保留。顶部测试用的“预览阶段”已移除。
- 过程详情按检索、阅读、Skill、问题比较、本轮修改、调用与运行展示；每项说明输入、做了什么及对当前讨论的作用。Skill 原文读取当前安装版本，不是复制在页面里的示例文本。

The sidebar switches conversations and creates new ones. The central conversation shows progress and step summaries; details and settings open in dialogs. Sending a message discusses or revises the current stage, including requests for more literature. Continue advances from direction discussion to deeper comparison, or from problem discussion to the final research argument. Drafts survive dialog closing and conversation switching.

## 已连接与待接入 / Connected and remaining

**Codex 模型发现已经真实连接。** 打开页面读取本地模型缓存；“刷新模型”通过 `codex app-server` 的 `model/list` 接口读取完整目录，处理分页并显示来源。模型 ID、显示名称和思考强度来自返回数据；没有固定为一个模型。失败时保留上次列表和当前选择。配置档单独读取，避免把默认配置的缓存当成指定配置结果。

**Codex model discovery is live.** Initial loading reads the local model cache; Refresh reads the paginated `model/list` catalog through the local app-server. IDs, names, and reasoning options come from returned metadata. Failed refreshes preserve the previous catalog and selection. No inference turn is started and no credentials are returned to the browser. A catalog is not proof of inference entitlement, and Codex may itself use a cached catalog. See [the official protocol](https://learn.chatgpt.com/docs/app-server#list-models-modellist).

**研究流程仍是交互演示，尚未连接真实研究任务或项目存储。** 当前网页中的讨论草稿保存在本浏览器，不能替代 CLI 项目；其他后端的模型发现也尚未接入。真实研究继续使用 `research-idea`。可以在“系统设置 → 项目、资料与使用介绍 → 使用介绍 → 看看演示”中体验讨论、详情和继续操作。

**Research interactions remain a demonstration.** Browser drafts are not CLI projects. Research execution, project persistence, account checks, and other providers' catalogs are not connected yet. Run `research-idea` for real research. A sample discussion is available through System settings → Projects and help → Introduction → Demo.

实现入口 / Source: [`web.py`](../../src/research_idea/web.py), [`model_discovery.py`](../../src/research_idea/model_discovery.py), [`web_assets/index.html`](../../src/research_idea/web_assets/index.html). Existing CLI research, evidence, memory, and budget handling are unchanged.
