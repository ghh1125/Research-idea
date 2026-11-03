"""Web command adapter: reuse CLI semantics without a terminal or arbitrary file access."""
from __future__ import annotations

import asyncio
from pathlib import Path

from .chat import Chat
from .command_help import COMMAND_HELP, COMMAND_LOOKUP, BUDGET_LABELS
from .config import load_config


# Web instructions describe controls, not terminal keystrokes or terminal menus.
WEB_USAGE = {
    '/intro': '打开网页使用指南，了解发送消息、开始调研和继续的区别。',
    '/help': '打开网页命令说明。可用 /help date 查看单项说明。命令后的 --help 只显示说明。',
    '/topic': '查看主题；调研前可以用 /topic 新主题 修改。调研后直接发消息纠正，换题用左侧“新建研究”。',
    '/input': '点击输入框旁“＋” → 研究说明，选择文本文件；内容会放入输入框，确认后发送。网页不接受本机文件路径。',
    '/constraints': '右上角“研究设置”中的“资源与研究约束”可以填写设备、周期和数据条件。',
    '/run': '等讨论回复完成后，点击输入框上方“开始文献调研”；中断后这里显示“恢复研究”。也可 /run 研究方向。',
    '/continue': '点击输入框上方“继续深入分析”或“整理研究主张”。请先发送并讨论尚未提交的修改意见。',
    '/stop': '点击运行提示右侧“停止运行”。保留已完成步骤；关闭网页不会停止任务。',
    '/problems': '弹窗重看当前方向或问题的论证；/problems detail 查看完整版本。修改意见直接发到讨论中。',
    '/model': '使用输入框下方的模型下拉框；“刷新模型”重新读取本机 Codex 目录。inherit 表示沿用后端配置。',
    '/reasoning': '使用模型右侧的思考强度下拉框。可选档位随模型目录变化，inherit 沿用后端配置。',
    '/models': '查看本机模型目录；它不是账户调用权限或余额查询。',
    '/account': '研究设置 → 查看登录方式。只显示登录类型、后端和模型，不显示密钥或查询余额。',
    '/papers': '点击上方“文献”，展开摘要、泛读笔记和原文依据。导入请点击输入框旁“＋” → 论文资料，选择 PDF、文本或论文 JSON。',
    '/scope': '研究设置 → 文献范围。关闭自动检索会沿用已有资料；/scope ai-recent 恢复推荐范围，local 关闭自动检索。',
    '/date': '研究设置 → 文献范围，选择动态月数或固定日期。会议可单独选择“最新公开一届”。',
    '/venues': '研究设置 → 文献范围，填写会议名称或预设。例：ACL EMNLP COLM ICLR，或 ai-recommended。',
    '/status': '侧栏显示当前阶段和累计用量；此命令弹窗查看详细状态。',
    '/report': '点击上方“研究主张”；使用“导出 Markdown”保存到浏览器下载目录。尚未形成终稿时显示当前讨论。',
    '/evidence': '文献页中每篇论文可展开原文依据。此命令列出带出处的依据；/evidence 1 展开第一条。',
    '/details': '每条过程记录可展开查看；此命令弹窗显示最近一步完整分析。on/off 切换当前网页是否默认展开过程。',
    '/memory': '点击上方“研究要点”，查看持续要求与修改理由；纠正这些记录请直接发消息。',
    '/history': '弹窗查阅原始对话；/history 关键词 搜索整个项目。不会调用模型。',
    '/config': '弹窗查看当前配置；修改请使用研究设置或对应快捷命令。',
    '/budget': '研究设置中可改调用和分钟上限。命令使用整数；max_seconds、timeout_s 的单位是秒。提高上限不会清零用量。',
    '/output': '查看自动保存位置。网页导出使用“研究主张 → 导出 Markdown”；更改本机保存根目录请重启服务并指定 --output，或在 CLI 中调整已有项目。',
    '/new': '点击左侧“新建研究”。沿用当前设置，主题、论文和用量从零开始，旧研究保留。',
    '/open': '点击左侧研究名称切换。命令可接当前工作空间内的项目名称；打开其他目录请在启动 Web 时指定 --projects。',
    '/exit': '网页直接关闭标签页即可。任务仍在后台运行；暂停用“停止运行”。关闭服务请在启动它的终端按 Ctrl+C。',
}


def help_text(topic=''):
    topic = topic.strip()
    if topic and topic != 'all':
        name = '/' + topic.lstrip('/')
        item = COMMAND_LOOKUP.get(name)
        if not item:
            raise ValueError('没有这个命令；输入 /help 查看网页用法。')
        return _detail(item)
    return ('网页快捷命令\n\n大部分操作都可以直接点击完成；输入 / 开头的命令不会作为研究意见发送给模型。'
            '\n只有讨论、开始调研和继续会调用研究模型。\n\n' + '\n\n'.join(_detail(item) for item in COMMAND_HELP))


def _detail(item):
    examples = '\n\n示例：' + ' · '.join('`' + example + '`' for example in item.examples[:3])
    if item.name in {'/input', '/papers', '/output', '/open', '/exit'}:
        examples = ''
    budget = '\n\n' + '\n'.join(f'- `{k}`：{v}' for k, v in BUDGET_LABELS.items()) if item.name == '/budget' else ''
    return f'### {item.name} · {item.summary}\n\n{WEB_USAGE[item.name]}{budget}{examples}'


class WebChat(Chat):
    """Run shared local commands; workers and browser navigation stay in WebWorkspace."""

    def __init__(self, workspace, ident):
        self.workspace, self.ident = workspace, ident
        self.reply = {'command': '', 'messages': [], 'project_id': ident}
        super().__init__(workspace.project(ident), output=self.capture)
        self.details_full = True

    def capture(self, tag, text):
        self.reply['messages'].append({'tag': tag, 'text': text})

    @property
    def busy(self):
        with self.workspace.lock:
            job = self.workspace.jobs.get(self.ident)
            return bool(job and not job['done'].is_set())

    def settings(self, **updates):
        self.workspace.configure(self.ident, updates)
        self.cfg = load_config(self.project)
        self.show('system', '设置已保存，后续调用生效。\n' + '\n'.join(
            f'{BUDGET_LABELS.get(k, k)}：{v if v != "" else "沿用后端配置"}' for k, v in updates.items()))

    async def pick(self, title, choices):
        # The browser has real controls; never attempt a terminal prompt here.
        self.reply['ui'] = 'settings'
        return ''

    async def start(self, mode, message=''):
        self.reply.update(self.workspace.start(self.ident, mode, message))

    async def stop(self):
        result = self.workspace.stop(self.ident)
        self.show('system', '已请求停止；完成的进度会保留。' if result.get('stopping') else '当前没有由网页启动的运行任务。')

    async def handle_web(self, text):
        parts = text.strip().split(maxsplit=1)
        command, value = parts[0], parts[1].strip() if len(parts) > 1 else ''
        self.reply['command'] = command
        if command not in COMMAND_LOOKUP:
            raise ValueError('未知命令；输入 /help 查看网页支持的操作。')
        if command in {'/help', '/intro'} or value in {'--help', '-h'}:
            self.reply['ui'] = 'help' if command == '/intro' or command == '/help' and not value else 'result'
            self.show('system', help_text(command if value in {'--help', '-h'} else value))
        elif command == '/input' or command == '/papers' and value or command == '/output' and value:
            raise ValueError(WEB_USAGE[command])
        elif command in {'/exit', '/quit'}:
            self.show('system', WEB_USAGE['/exit'])
        elif command == '/new':
            created = self.workspace.create(value, inherit=self.ident)
            self.reply['project_id'] = created['id']
            self.show('system', '已新建研究，沿用当前设置；旧研究保留在左侧。')
        elif command == '/open':
            if not value:
                self.show('system', WEB_USAGE['/open'])
            else:
                # Only registered projects; never initialize arbitrary paths from HTTP.
                candidate = Path(value.strip('"\''))
                ident = candidate.name
                if not candidate.is_absolute() and str(candidate) != ident:
                    raise ValueError(WEB_USAGE['/open'])
                path = self.workspace.project(ident)
                if candidate.is_absolute() and candidate.resolve() != path:
                    raise ValueError(WEB_USAGE['/open'])
                self.reply['project_id'] = ident
        elif command in {'/model', '/reasoning'} and not value:
            self.reply['ui'] = command[1:]
        elif command == '/details' and value in {'on', 'off'}:
            self.reply['details'] = value == 'on'
            self.show('system', '已切换为' + ('展开过程详情。' if value == 'on' else '折叠过程详情，仍可逐项打开。'))
        elif command in {'/papers', '/memory', '/report'} and not value:
            self.reply['ui'] = {'/papers': 'papers', '/memory': 'memory', '/report': 'report'}[command]
        else:
            await self.handle(command + (' ' + value if value else ''))
        return self.reply


def execute(workspace, ident, text):
    adapter = WebChat(workspace, ident)
    result = asyncio.run(adapter.handle_web(text))
    # Read-only views do not duplicate histories into the activity feed. Setting
    # changes remain traceable, separate from model messages and research memory.
    changed = [m['text'] for m in result['messages'] if m['text'].startswith('设置已保存')]
    if changed:
        workspace.record(adapter.project, 'system', '\n\n'.join(changed))
    return result
