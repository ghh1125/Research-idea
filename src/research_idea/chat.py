"""Persistent terminal conversation, with interruptible research in a subprocess."""
from __future__ import annotations

import asyncio
from datetime import datetime
import json
import os
from pathlib import Path
import re
import shlex
import signal
import shutil
import sqlite3
import sys
import time

from .config import load_config, write_config, REASONING_EFFORTS
from .interactive import read_topic_file
from .locking import project_lock
from .store import Store
from .presentation import STATUS_LABELS
from .citations import Citations, EVIDENCE_ID

INTRO = '''1. 输入你的研究方向，与模型讨论；第一条输入默认成为正式研究主题。
2. /model 选择模型，/reasoning 选择思考强度；设置会保存在当前项目。
3. 对话中的补充会带入下一轮研究；/topic 查看主题，/constraints 保存资源条件。
4. /scope ai-recent 使用近期 AI 会议 + CS arXiv；/papers 路径 可导入论文。
5. /budget 查看预算，准备好后输入 /run。讨论与研究共用本项目累计预算。
6. 第一阶段 [concept]：背景 → 问题 → 动机 → Idea；完成贡献对照和基本可行性判断。
   第二阶段 [design]：Idea → Method；提供可借鉴技术、适用理由与改造建议。
7. 最后 [idea] 显示核心想法、研究价值、工作差异与技术参考；/evidence 查看原文。
8. /details 展开上一步的完整分析；/details on 显示完整过程，off 恢复易读视图。
9. /new 开始空白研究，沿用设置，调用和时间从 0 开始；/open 路径 恢复旧项目。
运行中隐藏输入框；底部显示预算，Ctrl+C 停止，结束后可用 /run 继续。
/account 看登录方式，/models 看本地模型目录，/help 查看全部命令，/exit 退出。
Enter 发送 · Esc 然后 Enter 换行 · Tab 补全 · ↑↓ 历史 · Ctrl+C 停止任务/清空输入'''

HELP = '''/intro 使用介绍：从输入方向到得到 idea 的操作步骤。
直接输入：与模型讨论研究方向（会调用模型）；/run 才启动文献研究。
/model [模型ID|inherit]  选择模型       /models       本地模型目录
/reasoning [强度]        选择思考强度   /account      登录方式
/topic [研究方向]        查看/设置主题  /input 路径   读取多行输入
/run                    开始/恢复研究  /stop         停止当前任务
/papers [路径…]          列表/导入论文  /evidence [序号] 查看原文依据
/status                 研究状态      /report       显示 idea 方案
/details [on|off]        展开上一步分析；on/off 切换完整过程输出
/config                 当前设置      /constraints [文字] 资源限制
/budget [键 数值]        预算设置      /scope [ai-recent|local|日期 日期]
/venues [预设或会议列表]   查看/选择会议；支持 CCF、THCPL、CORE
/date                   时间窗口：动态技术/动机对照窗口，或固定日期
/new [研究方向]          新建空白研究，沿用设置，预算计数从 0 开始
/open 项目目录           切换项目      /history      最近对话
/help                   命令说明      /exit         退出
Enter 发送 · Esc 然后 Enter 换行 · Tab 补全 · ↑↓ 历史 · Ctrl+C 停止任务/清空输入'''
COMMANDS = [line.split()[0] for line in HELP.splitlines() if line.startswith('/')]
COMMANDS += ['/models', '/account', '/input', '/stop', '/evidence', '/report', '/constraints', '/scope', '/history', '/exit']
COLORS = {'system': 'ansicyan', 'assistant': 'ansigreen', 'skill': 'ansimagenta',
          'search': 'ansicyan', 'paper': 'ansiblue', 'read': 'ansiblue',
          'evidence': 'ansigreen', 'analysis': 'ansiyellow', 'thinking': 'ansiyellow',
          'review': 'ansimagenta', 'idea': 'ansigreen', 'error': 'ansired',
          'gap': 'ansired', 'stopped': 'ansiyellow', 'saved': 'ansicyan'}
COLORS.update(strategy='ansicyan', novelty='ansimagenta', budget='ansicyan', detail='ansicyan', gap='ansiyellow',
              concept='ansimagenta', design='ansicyan')
TAG_LABELS = {'system': '使用与设置', 'assistant': '研究讨论', 'skill': '分析方法',
    'search': '检索文献', 'strategy': '寻找方法', 'novelty': '对比研究动机',
    'paper': '论文', 'read': '阅读', 'analysis': '分析', 'thinking': '正在思考',
    'review': '方案讨论', 'idea': '研究 Idea', 'concept': 'Idea 构思', 'design': '技术参考', 'evidence': '原文依据', 'saved': '已保存',
    'error': '这一步未完成', 'gap': '检索与阅读进展', 'budget': '预算', 'stopped': '已停止', 'detail': '完整分析'}
BUDGET_LABELS = {'search_results_per_query': '每次检索先筛的论文数', 'max_papers': '全文阅读上限',
    'max_candidates': 'Idea 数量', 'max_rounds': '方案讨论轮数', 'max_calls': '模型调用上限',
    'max_seconds': '累计时间（秒）', 'timeout_s': '单次调用超时（秒）'}
BUDGET_KEYS = ('search_results_per_query', 'max_papers', 'max_candidates', 'max_rounds', 'max_calls', 'max_seconds', 'timeout_s')
BRAND = r'''             R E S E A R C H

       ___ ____  _____    _
      |_ _|  _ \| ____|  / \
       | || | | |  _|   / _ \
       | || |_| | |___ / ___ \
      |___|____/|_____/_/   \_\

       IDEAS ONLY
       From papers to research proposals'''
WELCOME_NOTES = '''从一个研究方向，到一份可以开始验证的 idea。

1. 输入方向和补充想法，直接与模型讨论。
2. 输入 /run：第一阶段 背景 → 问题 → 动机 → Idea；第二阶段 Idea → Method。
3. 最后得到核心想法、研究价值、与已有工作的差异，以及技术参考。

/model 选择模型 · /reasoning 思考强度 · /date 时间 · /budget 预算
/intro 使用介绍 · /new 新研究 · /help 全部命令

专注研究 idea，附技术参考。运行中显示进展，Ctrl+C 停止，/run 继续。'''


def safe_text(text):
    # Papers and model text must not inject terminal escape/OSC sequences.
    return ''.join(c for c in str(text) if c in '\n\t' or (ord(c) >= 32 and not 127 <= ord(c) < 160))


def resource_text(value):
    return '尚未设置。可用 /constraints 补充设备、时间或 API 预算。' if value.startswith('Resources unspecified;') else value


def fragments(tag, text):
    if tag == 'brand':
        return [('ansigreen bold', '\n' + safe_text(text) + '\n')]
    color = COLORS.get(tag, 'ansicyan')
    from prompt_toolkit.utils import get_cwidth
    width = shutil.get_terminal_size((88, 24)).columns
    heading = f'── [{safe_text(tag)}] {TAG_LABELS.get(tag, "")} '
    result = [(color + ' bold', '\n' + heading + '─' * max(0, min(width, 88) - get_cwidth(heading)) + '\n')]
    pattern = r'(ev_[a-zA-Z0-9_]+|https?://[^\s]+|arxiv:[^\s]+|doi:[^\s]+)'
    for line in safe_text(text).splitlines():
        title = line.startswith('#')
        line = re.sub(r'^#{1,6}\s+', '', line)
        line = re.sub(r'\[([^\]\n]+)\]\((https?://[^)]+)\)', r'\1 · \2', line)
        base = color + ' bold' if title else 'ansigreen' if line.replace('**', '').startswith(('原文：', '原文位置：')) else ''
        for span in re.split(r'(\*\*[^*\n]+\*\*)', line):
            emphasis = span.startswith('**') and span.endswith('**')
            if emphasis:
                span = span[2:-2]
            for part in re.split(pattern, span):
                style = 'ansigreen bold' if part.startswith('ev_') else 'ansiblue underline' if part.startswith(('http', 'arxiv:', 'doi:')) else color + ' bold' if emphasis else base
                result.append((style, part))
        result.append(('', '\n'))
    return result


def model_catalog():
    """Read only allowlisted public fields, never auth.json or cache identity."""
    path = Path(os.environ.get('CODEX_HOME', '~/.codex')).expanduser() / 'models_cache.json'
    try:
        if path.stat().st_size > 8 * 1024 * 1024:
            return [], '本地模型缓存过大，未读取'
        data = json.loads(path.read_text(encoding='utf-8'))
        models = [{'id': m['slug'], 'levels': [r['effort'] for r in m.get('supported_reasoning_levels', [])
                   if isinstance(r, dict) and r.get('effort') in REASONING_EFFORTS]}
                  for m in data.get('models', []) if isinstance(m, dict) and isinstance(m.get('slug'), str)
                  and m.get('visibility', 'list') == 'list']
        return models, f"来自本地 Codex 模型目录 · 更新于 {data.get('fetched_at', '未知')}"
    except (OSError, ValueError, TypeError, KeyError):
        return [], '未找到可读的本地模型缓存；可手动输入模型 ID'


def initialize(args):
    from .cli import execution_config
    project = (args.project or Path('research-projects') / ('chat-' + datetime.now().strftime('%Y%m%d-%H%M%S-%f'))).expanduser().resolve()
    fresh = not (project / 'research.toml').exists()
    if fresh:
        if args.backend in {None, 'codex'}:
            if args.model is None:
                args.model = 'gpt-6.1-sol'
            if args.reasoning_effort is None:
                args.reasoning_effort = 'medium'
        if args.literature_preset is None and args.search_source is None and args.venues is None:
            args.literature_preset = 'ai-recent'
        for key, value in {'max_papers': 6, 'max_candidates': 1, 'max_rounds': 2, 'max_seconds': 6600, 'timeout_s': 1200}.items():
            if getattr(args, key) is None:
                setattr(args, key, value)
    with project_lock(project):
        cfg, _ = execution_config(args, project)
        write_config(project, cfg)
        store = Store(project)
        store.close()
    return project


class Chat:
    def __init__(self, project, output=None):
        self.project = project
        self.cfg = load_config(project)
        self.job = None
        self.process = None
        self.started = 0
        self.step_started = 0
        self.base_elapsed = 0
        self.state = '就绪'
        self.output = output
        self.session = None
        self.details_full = False

    @property
    def busy(self):
        return self.job is not None and not self.job.done()

    def show(self, tag, text):
        if tag == 'detail' and not self.details_full:
            return
        if EVIDENCE_ID.search(str(text)):
            try:
                store = Store(self.project, readonly=True)
                try:
                    text = Citations.from_store(store).text(text)
                finally:
                    store.close()
            except (OSError, RuntimeError, sqlite3.Error):
                pass
        if self.output:
            self.output(tag, safe_text(text))
        else:
            from prompt_toolkit import print_formatted_text
            from prompt_toolkit.formatted_text import FormattedText
            print_formatted_text(FormattedText(fragments(tag, text)))

    def toolbar(self):
        calls, elapsed, status = '?', 0, 'initialized'
        try:
            store = Store(self.project, readonly=True)
            try:
                calls, elapsed = store.get('calls_used', 0), store.get('elapsed_s', 0)
                status = store.get('status', 'initialized')
            finally:
                store.close()
        except (OSError, RuntimeError):
            pass
        if self.busy:
            elapsed = max(elapsed, self.base_elapsed + time.monotonic() - self.started)
        from prompt_toolkit.utils import get_cwidth
        width = shutil.get_terminal_size((88, 24)).columns
        def fit(value):
            value = safe_text(value)
            if get_cwidth(value) <= width:
                return value
            while value and get_cwidth(value + '…') > width:
                value = value[:-1]
            return value + '…'
        state = self.state if self.busy else STATUS_LABELS.get(status, '就绪')
        spinner = ''
        if self.busy:
            tick = time.monotonic()
            spinner = '⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏'[int(tick * 5) % 10] + ' '
            seconds = max(0, int(tick - (self.step_started or self.started)))
            state += f' · 本步 {seconds // 60}:{seconds % 60:02d}'
        if not self.busy and status == 'running':
            state = '已有进度'
        footer = (' /intro 使用介绍 · Ctrl+C 停止 · 完成后恢复输入' if self.busy else
                  ' /intro 使用介绍 · /new 新研究 · ' + ('/report 看方案' if status == 'completed' else '/run 开始研究'))
        context = '' if self.busy else ' · ' + self.project.name
        return [('bg:ansiblue ansiwhite', fit(f" {spinner}{self.cfg['model'] or '继承模型'} · {self.cfg['reasoning_effort'] or '继承强度'} · {state}{context}") + '\n'),
                ('bg:ansiblack ansiwhite', fit(f" 本项目累计 · 调用 {calls}/{self.cfg['max_calls']} · 时间 {elapsed / 60:.1f}/{self.cfg['max_seconds'] / 60:g} 分") + '\n'),
                ('bg:ansiblack ansicyan', fit(footer))]

    def idle_required(self):
        if self.busy:
            raise ValueError('当前任务正在运行。可用 /status、/evidence、/stop；停止后再修改配置或发送消息。')

    def settings(self, **updates):
        self.idle_required()
        with project_lock(self.project):
            cfg = load_config(self.project)
            cfg.update(updates)
            write_config(self.project, cfg)
        self.cfg = load_config(self.project)
        labels = {**BUDGET_LABELS, 'model': '模型', 'reasoning_effort': '思考强度', 'constraints': '资源条件',
                  'search_venues': '会议', 'search_date_mode': '日期模式', 'strategy_months': '方法窗口（月）',
                  'novelty_months': '第一阶段动机对照窗口（月）', 'search_source': '文献来源', 'auto_search': '自动检索',
                  'search_since': '起始日期', 'search_until': '截止日期'}
        values = lambda value: '、'.join(value) if isinstance(value, list) else {'rolling': '动态', 'fixed': '固定', 'hybrid': '会议 + arXiv'}.get(str(value), str(value))
        self.show('system', '已保存，下次运行生效。\n' + '\n'.join(f'{labels.get(k, k)}：{values(v) or "沿用后端配置"}' for k, v in updates.items()))

    def topic(self, text=''):
        self.idle_required()
        with project_lock(self.project):
            store = Store(self.project)
            try:
                if text:
                    if store.get('cohort') or store.db.execute('SELECT COUNT(*) FROM tasks').fetchone()[0]:
                        raise ValueError('已有研究任务的主题不能替换；使用 /new 新方向 开始新研究。')
                    store.set('topic', text)
                    store.set('status', 'initialized')
                return store.get('topic', '')
            finally:
                store.close()

    def new_project(self, topic=''):
        self.idle_required()
        if len(topic) > 128 * 1024 or '\x00' in topic:
            raise ValueError('输入过长或包含空字符')
        previous = self.project
        cfg = load_config(previous)
        project = previous.parent / ('chat-' + datetime.now().strftime('%Y%m%d-%H%M%S-%f'))
        project.mkdir(exist_ok=False)
        with project_lock(project):
            write_config(project, cfg)
            store = Store(project)
            try:
                store.set('status', 'initialized')
                if topic:
                    store.set('topic', topic)
            finally:
                store.close()
        self.project, self.cfg = project, cfg
        self.started, self.base_elapsed, self.state = 0, 0, '就绪'
        if self.session:
            from prompt_toolkit.history import InMemoryHistory
            self.session.history = InMemoryHistory()
            self.session.default_buffer.history = self.session.history
            self.session.default_buffer.reset()
            self.session.app.invalidate()
        self.show('system', f'已开始空白研究 · 调用 0 · 时间 0 分\n沿用模型、思考强度、检索和预算设置。\n项目：{project}\n上次研究：{previous}\n' +
                  (f'主题：{topic}\n输入 /run 开始研究。' if topic else '直接输入新方向，或 /topic 设置主题。'))

    async def pick(self, title, choices):
        self.show('system', title + '\n' + '\n'.join(f'{i}. {v}' for i, v in enumerate(choices, 1)) + '\n输入编号或值；空行取消。')
        value = (await self.session.prompt_async('选择 › ')).strip()
        if value.isdecimal() and 1 <= int(value) <= len(choices):
            return choices[int(value) - 1]
        return value

    async def start(self, mode, message=''):
        self.idle_required()
        self.cfg = load_config(self.project)
        store = Store(self.project, readonly=True)
        try:
            self.base_elapsed = store.get('elapsed_s', 0)
        finally:
            store.close()
        self.started, self.state = time.monotonic(), '研究中' if mode == 'run' else '答复中'
        self.step_started = self.started
        self.job = asyncio.create_task(self.work(mode, message))
        # Let process creation begin before the next prompt or /stop.
        await asyncio.sleep(0)

    async def work(self, mode, message):
        log = self.project / 'terminal-events.jsonl'
        reported_error = False
        try:
            self.process = await asyncio.create_subprocess_exec(
                sys.executable, '-u', '-m', 'research_idea.chat_worker',
                stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL, limit=32 * 1024 * 1024,
                start_new_session=(os.name == 'posix'))
            request = json.dumps({'project': str(self.project), 'mode': mode, 'message': message}, ensure_ascii=False)
            self.process.stdin.write(request.encode())
            await self.process.stdin.drain()
            self.process.stdin.close()
            while line := await self.process.stdout.readline():
                event = json.loads(line)
                if event['tag'] in {'error', 'budget'}:
                    reported_error = True
                if event['tag'] in {'search', 'read', 'analysis', 'review', 'idea', 'thinking', 'concept', 'design'}:
                    heading = event['text'].split('\n', 1)[0]
                    state = (re.sub(r'\s*·\s*模型调用.*$', '', heading) if re.match(r'(?:\d/4|第[一二](?:轮|阶段)(?:完成)?) · ', heading)
                             else TAG_LABELS[event['tag']])
                    if state != self.state or '模型调用' in heading or event['tag'] == 'thinking':
                        self.step_started = time.monotonic()
                    self.state = state
                with log.open('a', encoding='utf-8') as stream:
                    stream.write(json.dumps(event, ensure_ascii=False) + '\n')
                self.show(event['tag'], event['text'])
            code = await self.process.wait()
            if code not in {0, 130, -signal.SIGINT} and not reported_error:
                self.show('error', f'任务中断（退出码 {code}）。已保存的进度可以用 /run 继续。')
        except (OSError, ValueError, KeyError) as exc:
            self.show('error', str(exc))
        finally:
            if self.process and self.process.returncode is None:
                await self.interrupt_process()
            self.process = None
            self.state = '就绪'
            if self.session:
                self.session.app.invalidate()

    async def interrupt_process(self):
        process = self.process
        if process and process.returncode is None:
            try:
                process.send_signal(signal.SIGINT)
            except ProcessLookupError:
                return
            # Worker handles KeyboardInterrupt and reaps its model process group.
            await process.wait()

    async def stop(self):
        if not self.busy:
            return
        self.show('stopped', '正在停止当前任务并保存检查点…')
        while self.process is None and self.busy:
            await asyncio.sleep(0.02)
        await self.interrupt_process()
        await self.job

    async def account(self):
        from .backends.cli import _codex_command
        cfg = self.cfg
        details = f"后端：{cfg['backend']}\n模型：{cfg['model'] or '沿用后端配置'}\n配置档：{cfg['codex_profile'] or '默认'}"
        if cfg['backend'] == 'codex':
            proc = await asyncio.create_subprocess_exec(*_codex_command(cfg), 'login', 'status',
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT)
            try:
                raw, _ = await asyncio.wait_for(proc.communicate(), timeout=10)
            except asyncio.TimeoutError:
                proc.kill()
                await proc.wait()
                raise ValueError('登录状态检查超时') from None
            value = raw.decode(errors='replace').lower()
            login = ('ChatGPT 登录' if proc.returncode == 0 and 'chatgpt' in value else
                     'API key 登录' if proc.returncode == 0 and 'api key' in value else
                     '未登录' if 'not logged in' in value else '无法确定，请直接运行 codex login status')
            details += '\n登录方式：' + login + '\nCodex 路径：' + cfg['codex_bin']
        elif cfg['backend'] == 'api':
            key = cfg['api_key_env']
            details += f"\n认证变量：{key}；{'已设置' if os.environ.get(key) else '未设置'}"
        else:
            details += '\n登录方式：由 Claude CLI 管理；本界面不读取认证文件。'
        self.show('account', details)

    async def send(self, text):
        self.idle_required()
        if len(text) > 128 * 1024 or '\x00' in text:
            raise ValueError('输入过长或包含空字符')
        if not self.topic():
            self.topic(text)
            self.show('system', '已将第一条输入设为研究主题。可用 /topic 修改，/run 启动研究。')
        await self.start('chat', text)
        return True

    async def handle(self, text):
        if not text.startswith('/'):
            return await self.send(text)
        command, _, value = text.partition(' ')
        value = value.strip()
        if command in {'/exit', '/quit'}:
            await self.stop()
            return False
        if command == '/stop':
            await self.stop()
        elif command == '/help':
            self.show('system', HELP)
        elif command == '/intro':
            self.show('system', INTRO)
        elif command == '/details':
            if value in {'on', 'off'}:
                self.details_full = value == 'on'
                self.show('system', '过程输出：' + ('完整分析' if self.details_full else '易读视图（每步结论和新引用）'))
            elif value:
                raise ValueError('/details 查看上一步；/details on 或 off 切换过程输出。')
            else:
                store = Store(self.project, readonly=True)
                try:
                    last = store.get('last_activity', {})
                    citations = Citations.from_store(store)
                finally:
                    store.close()
                if last:
                    from .chat_worker import outline
                    self.show('analysis', '\n'.join(outline(last['result'], citations=citations)))
                else:
                    self.show('system', '还没有研究分析。输入 /run 开始。')
        elif command in {'/model', '/reasoning'}:
            self.idle_required()
            models, note = model_catalog()
            if command == '/model':
                if not value:
                    self.show('system', note)
                    value = await self.pick('选择模型（也可以直接输入 ID）', list(dict.fromkeys([self.cfg['model'] or 'gpt-6.1-sol'] + [m['id'] for m in models] + ['inherit'])))
                if value:
                    if any(c.isspace() for c in value) or '\x00' in value:
                        raise ValueError('模型 ID 不能包含空白或空字符')
                    self.settings(model='' if value == 'inherit' else value)
            else:
                levels = next((m['levels'] for m in models if m['id'] == self.cfg['model']), list(REASONING_EFFORTS))
                value = value or await self.pick('思考强度（依赖模型与客户端支持）', ['inherit', *levels])
                if value:
                    if value != 'inherit' and value not in levels:
                        raise ValueError('该模型的本地目录未列出此强度；可用：' + ', '.join(levels))
                    self.settings(reasoning_effort='' if value == 'inherit' else value)
        elif command == '/models':
            models, note = model_catalog()
            self.show('system', note + '\n' + '\n'.join(m['id'] + ' · ' + ', '.join(m['levels']) for m in models))
        elif command == '/account':
            await self.account()
        elif command == '/topic':
            self.show('system', self.topic(value) or '尚未设置研究主题')
        elif command == '/input':
            return await self.send(read_topic_file(value))
        elif command == '/run':
            if value:
                self.topic(value)
            if not self.topic():
                raise ValueError('请先输入研究方向，或 /run 研究方向')
            await self.start('run')
        elif command in {'/status', '/papers', '/evidence', '/history'} and not (command == '/papers' and value):
            store = Store(self.project, readonly=True)
            try:
                if command == '/status':
                    status = store.get('status', 'initialized')
                    self.show('system', f"项目：{self.project}\n主题：{store.get('topic', '未设置')}\n进展：{STATUS_LABELS.get(status, status)}\n模型：{self.cfg['model'] or '继承配置'} · {self.cfg['reasoning_effort'] or '继承强度'}\n调用：{store.get('calls_used', 0)}/{self.cfg['max_calls']}（本项目累计，讨论与研究合计）\n时间：{store.get('elapsed_s', 0) / 60:.1f}/{self.cfg['max_seconds'] / 60:g} 分\n论文：{len(store.rows('papers'))}；原文依据：{len(store.rows('evidence'))}")
                elif command == '/papers':
                    kinds = {'full_text': '已获取正文', 'abstract': '摘要与元数据', 'notes': '导入的笔记'}
                    citations = Citations.from_store(store)
                    self.show('paper', '\n\n'.join(f"{i}. {citations.paper(p['id'])} ({p.get('year') or '年份未标注'})\n   {p.get('venue') or '预印本 / 导入资料'} · {kinds.get(p.get('content_kind'), '论文资料')}" for i, p in enumerate(store.rows('papers'), 1)) or '暂无论文；/run 自动检索，或 /papers 路径 导入。')
                elif command == '/evidence':
                    citations = Citations.from_store(store)
                    entries = list(citations.evidence.values())
                    if not value:
                        self.show('evidence', '\n\n'.join(f"{i}. {citations.reference(e['id'])}\n   {e.get('statement', '')}" for i, e in enumerate(entries, 1)) +
                                  '\n\n输入 /evidence 序号 查看对应原文。' if entries else '还没有原文依据；/run 阅读论文后会在这里显示。')
                    else:
                        ev = (entries[int(value) - 1] if value.isascii() and value.isdecimal() and 1 <= int(value) <= len(entries)
                              else citations.evidence.get(value))
                        if not ev:
                            raise ValueError('未找到这条原文；输入 /evidence 查看列表，再选择序号。')
                        self.show('evidence', citations.block(ev))
                else:
                    for m in store.get('chat_messages', [])[-12:]:
                        self.show(m['role'], m['content'])
            finally:
                store.close()
        elif command == '/papers':
            self.idle_required()
            from .cli import collect_paper_files, read_paper_records, import_papers
            records = read_paper_records(collect_paper_files(shlex.split(value)))
            with project_lock(self.project):
                store = Store(self.project)
                try:
                    import_papers(store, records)
                finally:
                    store.close()
            self.show('paper', f'已导入 {len(records)} 条论文记录')
        elif command == '/report':
            from .chat_worker import idea_text
            self.show('idea', idea_text(self.project))
        elif command == '/config':
            from .search_scope import config_scope
            cfg = load_config(self.project)
            strategy, novelty = config_scope(cfg), config_scope(cfg, 'novelty')
            self.show('system', '\n'.join([
                '项目：' + str(self.project), f"模型：{cfg['model'] or '继承配置'} · 思考强度 {cfg['reasoning_effort'] or '继承配置'} · 后端 {cfg['backend']}",
                f"背景与技术探索：{strategy['since']} → {strategy['until']}", f"第一阶段动机对照：{novelty['since']} → {novelty['until']}",
                '会议：' + ('、'.join(cfg['search_venues']) or '按主题检索'),
                f"选文：每次查询 {cfg['search_results_per_query']} 篇元数据 → 全流程最多精读 {cfg['max_papers']} 篇",
                f"产出：最多 {cfg['max_candidates']} 个 idea，讨论 {cfg['max_rounds']} 轮",
                f"预算：{cfg['max_calls']} 次调用 / {cfg['max_seconds'] / 60:g} 分钟",
                '资源条件：' + resource_text(cfg['constraints']),
                '用 /model、/reasoning、/date、/venues、/budget 修改设置。']))
        elif command == '/constraints':
            if value:
                self.settings(constraints=value)
            else:
                self.show('system', resource_text(self.cfg['constraints']))
        elif command == '/budget':
            if value:
                key, number = shlex.split(value)
                if key not in BUDGET_KEYS:
                    raise ValueError('允许设置：' + ', '.join(BUDGET_KEYS))
                self.settings(**{key: int(number)})
            else:
                self.show('budget', '\n'.join(f'{BUDGET_LABELS[k]}：{self.cfg[k]}  ·  {k}' for k in BUDGET_KEYS)
                          + '\n\n“调用”是模型请求次数，包含讨论、分析和格式修复；上限不必用满。\n例如 /budget max_calls 100 · /budget max_papers 6')
        elif command == '/venues':
            from .venues import normalize_venues, supported_venues
            if value:
                self.idle_required()
                self.settings(search_venues=normalize_venues(value.split()), search_source='hybrid')
            else:
                selected = set(self.cfg['search_venues'])
                rows = [row for row in supported_venues() if row['code'] in selected]
                self.show('search', '\n'.join(f"{r['code']}: CCF2026 {r.get('ccf_2026_ai_grade') or '—'} · CORE2026 {r.get('core_2026_grade') or '—'} · THCPL2019 {r.get('tsinghua_2019_ai_grade') or '—'}" for r in rows)
                          + '\n预设：ai-recommended / ccf-a-ai-2026 / tsinghua-a-ai-2019 / core-astar-ai-2026；也可 /venues ACL COLM ICLR')
        elif command == '/date':
            self.idle_required()
            from .search_scope import config_scope
            strategy, novelty = config_scope(self.cfg), config_scope(self.cfg, 'novelty')
            mode = '动态，每次运行按当天计算' if self.cfg['search_date_mode'] == 'rolling' else '固定日期'
            self.show('system', f"日期模式：{mode}\n背景与技术探索：{strategy['since']} → {strategy['until']}\n第一阶段动机对照：{novelty['since']} → {novelty['until']}\n已知的更早相关论文也会参与对比。")
            if not value:
                choice = await self.pick('修改时间设置', ['返回', '动态窗口', '固定日期'])
                if choice == '动态窗口':
                    months = await self.session.prompt_async('技术探索月数 动机对照月数 [12 6] › ')
                    value = 'rolling ' + (months.strip() or '12 6')
                elif choice == '固定日期':
                    dates = await self.session.prompt_async('起始日期 截止日期 YYYY-MM-DD › ')
                    value = 'fixed ' + dates.strip()
                elif choice not in {'', '返回'}:
                    raise ValueError('请选择编号，或 /date rolling 12 6、/date fixed 起始日期 截止日期')
            if value:
                fields = shlex.split(value)
                if fields[0] == 'rolling' and len(fields) in {1, 3}:
                    strategy_months, novelty_months = map(int, fields[1:] or [12, 6])
                    self.settings(search_date_mode='rolling', strategy_months=strategy_months, novelty_months=novelty_months)
                elif fields[0] == 'fixed' and len(fields) == 3:
                    self.settings(search_date_mode='fixed', search_since=fields[1], search_until=fields[2])
                else:
                    raise ValueError('/date rolling 12 6 或 /date fixed YYYY-MM-DD YYYY-MM-DD')
        elif command == '/scope':
            from .search_scope import recent_defaults, AI_VENUES, config_scope
            if value == 'ai-recent':
                self.settings(**recent_defaults(), search_source='hybrid', search_venues=list(AI_VENUES), auto_search=True, search_date_mode='rolling')
            elif value == 'local':
                self.settings(auto_search=False)
            elif value:
                since, until = shlex.split(value)
                self.settings(search_since=since, search_until=until, search_date_mode='fixed')
            else:
                self.show('search', f"{config_scope(self.cfg)['since']} → {config_scope(self.cfg)['until']} · {self.cfg['search_source']} · 自动检索 {self.cfg['auto_search']}\n/scope ai-recent | local | YYYY-MM-DD YYYY-MM-DD")
        elif command == '/new':
            self.new_project(value)
        elif command == '/open':
            self.idle_required()
            if not value:
                raise ValueError('/open 项目路径')
            from .cli import build_parser
            project = initialize(build_parser().parse_args(['chat', '--project', value]))
            self.project, self.cfg = project, load_config(project)
            self.show('system', '已打开：' + str(project))
        else:
            raise ValueError('未知命令；输入 /help 查看可用命令')
        return True

    async def loop(self):
        from prompt_toolkit import PromptSession
        from prompt_toolkit.completion import WordCompleter
        from prompt_toolkit.key_binding import KeyBindings
        from prompt_toolkit.patch_stdout import patch_stdout
        bindings = KeyBindings()
        @bindings.add('escape', 'enter')
        def newline(event):
            event.current_buffer.insert_text('\n')
        self.session = PromptSession(completer=WordCompleter(sorted(set(COMMANDS))),
                                     complete_while_typing=True, key_bindings=bindings,
                                     bottom_toolbar=self.toolbar, refresh_interval=1)
        with patch_stdout():
            self.show('brand', BRAND)
            self.show('system', WELCOME_NOTES + f'\n\n项目：{self.project}')
            try:
                while True:
                    try:
                        text = (await self.session.prompt_async('› ')).strip()
                        if text and not await self.handle(text):
                            break
                        if self.busy:
                            await self.wait_running()
                    except KeyboardInterrupt:
                        if self.busy:
                            await self.stop()
                        else:
                            self.show('system', '已清空输入框；底部是本项目累计用量。\n/new 开始空白研究（计数从 0 开始）；/exit 或 Ctrl+D 退出。')
                    except EOFError:
                        break
                    except (ValueError, RuntimeError, OSError) as exc:
                        self.show('error', str(exc))
            finally:
                await self.stop()
        return 0

    async def wait_running(self):
        """Show live status only. No editable prompt is present during work."""
        from prompt_toolkit.application import Application
        from prompt_toolkit.key_binding import KeyBindings
        from prompt_toolkit.layout import Layout, Window
        from prompt_toolkit.layout.controls import FormattedTextControl
        keys = KeyBindings()
        @keys.add('c-c')
        @keys.add('c-d')
        def stop(event):
            event.app.exit(result='stop')
        app = Application(layout=Layout(Window(FormattedTextControl(self.toolbar), height=3)),
                          key_bindings=keys, full_screen=False, refresh_interval=0.2)
        async def finish():
            await asyncio.shield(self.job)
            if app.is_running:
                app.exit(result='done')
        waiter = None
        def ready():
            nonlocal waiter
            waiter = asyncio.create_task(finish())
        try:
            result = await app.run_async(pre_run=ready)
            if result == 'stop':
                await self.stop()
        finally:
            if waiter and not waiter.done():
                waiter.cancel()
                await asyncio.gather(waiter, return_exceptions=True)


def launch_chat(args):
    if not sys.stdin.isatty():
        raise ValueError('chat 需要交互终端；脚本请使用 start/run/resume。')
    return asyncio.run(Chat(initialize(args)).loop())
