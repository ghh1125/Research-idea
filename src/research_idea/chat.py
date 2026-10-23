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
import sys
import time

from .config import load_config, write_config, REASONING_EFFORTS
from .interactive import read_topic_file
from .locking import project_lock
from .store import Store

INTRO = '''1. 输入你的研究方向，与模型讨论；第一条输入默认成为正式研究主题。
2. /model 选择模型，/reasoning 选择思考强度；设置会保存在当前项目。
3. /topic 查看或修改正式主题；讨论中的补充可用 /topic 和 /constraints 明确保存。
4. /scope ai-recent 使用近期 AI 会议 + CS arXiv；/papers 路径 可导入论文。
5. /budget 查看预算，准备好后输入 /run。讨论与研究共用调用和时间预算。
6. 跟随彩色 [search] [paper] [read] [analysis] [review] 查看步骤和证据。
7. 最后 [idea] 显示方案与第一步验证；/report 再看方案，/evidence ID 追溯原文。
运行中 /status 看状态，/stop 停止；/run 从检查点继续。
/account 看登录方式，/models 看本地模型目录，/help 查看全部命令，/exit 退出。
Enter 发送 · Esc 然后 Enter 换行 · Tab 补全 · ↑↓ 历史 · Ctrl+C 停止/清空'''

HELP = '''/intro 使用介绍：从输入方向到得到 idea 的操作步骤。
直接输入：与模型讨论研究方向（会调用模型）；/run 才启动文献研究。
/model [模型ID|inherit]  选择模型       /models       本地模型目录
/reasoning [强度]        选择思考强度   /account      登录方式
/topic [研究方向]        查看/设置主题  /input 路径   读取多行输入
/run                    开始/恢复研究  /stop         停止当前任务
/papers [路径…]          列表/导入论文  /evidence ID  查看原文依据
/status                 研究状态      /report       显示 idea 方案
/config                 当前设置      /constraints [文字] 资源限制
/budget [键 数值]        预算设置      /scope [ai-recent|local|日期 日期]
/open 项目目录           切换项目      /history      最近对话
/help                   命令说明      /exit         退出
Enter 发送 · Esc 然后 Enter 换行 · Tab 补全 · ↑↓ 历史 · Ctrl+C 停止/清空'''
COMMANDS = [line.split()[0] for line in HELP.splitlines() if line.startswith('/')]
COMMANDS += ['/models', '/account', '/input', '/stop', '/evidence', '/report', '/constraints', '/scope', '/history', '/exit']
COLORS = {'system': 'ansicyan', 'assistant': 'ansigreen', 'skill': 'ansimagenta',
          'search': 'ansicyan', 'paper': 'ansiblue', 'read': 'ansiblue',
          'evidence': 'ansigreen', 'analysis': 'ansiyellow', 'thinking': 'ansiyellow',
          'review': 'ansimagenta', 'idea': 'ansigreen', 'error': 'ansired',
          'gap': 'ansired', 'stopped': 'ansiyellow', 'saved': 'ansicyan'}
BUDGET_KEYS = ('max_papers', 'max_candidates', 'max_rounds', 'max_calls', 'max_seconds', 'timeout_s')
BRAND = '◆ RESEARCH IDEA\n  IDEAS ONLY · From papers to research proposals'


def safe_text(text):
    # Papers and model text must not inject terminal escape/OSC sequences.
    return ''.join(c for c in str(text) if c in '\n\t' or (ord(c) >= 32 and not 127 <= ord(c) < 160))


def fragments(tag, text):
    if tag == 'brand':
        return [('ansicyan bold', '\n' + safe_text(text) + '\n')]
    color = COLORS.get(tag, 'ansicyan')
    result = [(color + ' bold', f'\n── [{safe_text(tag)}] ' + '─' * 34 + '\n')]
    pattern = r'(ev_[a-zA-Z0-9_]+|https?://[^\s]+|arxiv:[^\s]+|doi:[^\s]+)'
    for line in safe_text(text).splitlines():
        base = ('ansiyellow' if any(w in line for w in ('未知', '缺口', '未验证', 'insufficient', 'unknown', 'unavailable'))
                else 'ansigreen' if any(w in line for w in ('原文：', 'quote：', '原文位置：')) else '')
        for part in re.split(pattern, line):
            style = 'ansigreen bold' if part.startswith('ev_') else 'ansiblue underline' if part.startswith(('http', 'arxiv:', 'doi:')) else base
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
        return models, f"本地缓存 · {path} · 更新于 {data.get('fetched_at', '未知')}；不是实时账户授权保证"
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
        for key, value in {'max_papers': 6, 'max_candidates': 1, 'max_rounds': 2, 'max_seconds': 6600, 'timeout_s': 600}.items():
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
        self.state = '就绪'
        self.output = output
        self.session = None

    @property
    def busy(self):
        return self.job is not None and not self.job.done()

    def show(self, tag, text):
        if self.output:
            self.output(tag, safe_text(text))
        else:
            from prompt_toolkit import print_formatted_text
            from prompt_toolkit.formatted_text import FormattedText
            print_formatted_text(FormattedText(fragments(tag, text)))

    def toolbar(self):
        elapsed = f' · {int(time.monotonic() - self.started)}s' if self.busy else ''
        return [('bg:ansiblue ansiwhite', safe_text(f" {self.cfg['model'] or '继承模型'} | {self.cfg['reasoning_effort'] or '继承强度'} | {self.state}{elapsed}\n")),
                ('bg:ansiblack ansicyan', ' /intro 使用介绍 · /model 模型 · /reasoning 强度 · /run 开始研究 · /help 命令 ')]

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
        self.show('system', '已保存：' + json.dumps(updates, ensure_ascii=False) + '\n下一次调用生效；研究缓存按模型和强度重新校验。')

    def topic(self, text=''):
        self.idle_required()
        with project_lock(self.project):
            store = Store(self.project)
            try:
                if text:
                    if store.get('cohort') or store.db.execute('SELECT COUNT(*) FROM tasks').fetchone()[0]:
                        raise ValueError('已有研究任务的主题不能替换；使用 /open 新目录。')
                    store.set('topic', text)
                    store.set('status', 'initialized')
                return store.get('topic', '')
            finally:
                store.close()

    async def pick(self, title, choices):
        self.show('system', title + '\n' + '\n'.join(f'{i}. {v}' for i, v in enumerate(choices, 1)) + '\n输入编号或值；空行取消。')
        value = (await self.session.prompt_async('选择 › ')).strip()
        if value.isdecimal() and 1 <= int(value) <= len(choices):
            return choices[int(value) - 1]
        return value

    async def start(self, mode, message=''):
        self.idle_required()
        self.cfg = load_config(self.project)
        self.started, self.state = time.monotonic(), '研究中' if mode == 'run' else '答复中'
        self.job = asyncio.create_task(self.work(mode, message))
        # Let process creation begin before the next prompt or /stop.
        await asyncio.sleep(0)

    async def work(self, mode, message):
        log = self.project / 'terminal-events.jsonl'
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
                with log.open('a', encoding='utf-8') as stream:
                    stream.write(json.dumps(event, ensure_ascii=False) + '\n')
                self.show(event['tag'], event['text'])
            code = await self.process.wait()
            if code not in {0, 130, -signal.SIGINT}:
                self.show('error', f'任务退出码 {code}；已返回对话窗口，可调整设置后重试。')
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
                    self.show('system', f"主题：{store.get('topic', '未设置')}\n状态：{store.get('status', '待开始')}\n调用：{store.get('calls_used', 0)}/{self.cfg['max_calls']}（讨论与研究合计）\n论文：{len(store.rows('papers'))}；证据：{len(store.rows('evidence'))}")
                elif command == '/papers':
                    self.show('paper', '\n\n'.join(f"{p['title']} ({p.get('year', '')})\n{p['id']}\n{p.get('url', '')}\n{p.get('content_kind', '')}" for p in store.rows('papers')) or '暂无论文；使用 /papers 路径 导入。')
                elif command == '/evidence':
                    ev = next((e for e in store.rows('evidence') if e['id'] == value), None)
                    if not ev:
                        raise ValueError('未找到证据；用 /evidence ev_… 查询')
                    paper = next((p for p in store.rows('papers') if p['id'] == ev['paper_id']), {})
                    from .chat_worker import outline
                    self.show('paper', f"{paper.get('title', '')}\n{paper.get('url', '')}")
                    self.show('evidence', '\n'.join(outline(ev)))
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
            self.show('system', '项目：' + str(self.project) + '\n' + json.dumps(load_config(self.project), ensure_ascii=False, indent=2))
        elif command == '/constraints':
            if value:
                self.settings(constraints=value)
            else:
                self.show('system', self.cfg['constraints'])
        elif command == '/budget':
            if value:
                key, number = shlex.split(value)
                if key not in BUDGET_KEYS:
                    raise ValueError('允许设置：' + ', '.join(BUDGET_KEYS))
                self.settings(**{key: int(number)})
            else:
                self.show('system', '\n'.join(f'{k} = {self.cfg[k]}' for k in BUDGET_KEYS) + '\n例如 /budget max_calls 100')
        elif command == '/scope':
            from .search_scope import recent_defaults, AI_VENUES
            if value == 'ai-recent':
                self.settings(**recent_defaults(), search_source='hybrid', search_venues=list(AI_VENUES), auto_search=True)
            elif value == 'local':
                self.settings(auto_search=False)
            elif value:
                since, until = shlex.split(value)
                self.settings(search_since=since, search_until=until)
            else:
                self.show('search', f"{self.cfg['search_since']} → {self.cfg['search_until']} · {self.cfg['search_source']} · 自动检索 {self.cfg['auto_search']}\n/scope ai-recent | local | YYYY-MM-DD YYYY-MM-DD")
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
            self.show('system', f'项目：{self.project}\n直接输入研究方向，或 /intro 查看使用介绍。/model 换模型，/reasoning 调强度，/run 开始研究。\n分析输出为可核查摘要；[thinking] 仅表示等待模型答复。')
            try:
                while True:
                    try:
                        text = (await self.session.prompt_async('› ')).strip()
                        if text and not await self.handle(text):
                            break
                    except KeyboardInterrupt:
                        if self.busy:
                            await self.stop()
                        else:
                            self.show('system', '输入已清空；/exit 或 Ctrl+D 退出。')
                    except EOFError:
                        break
                    except (ValueError, RuntimeError, OSError) as exc:
                        self.show('error', str(exc))
            finally:
                await self.stop()
        return 0


def launch_chat(args):
    if not sys.stdin.isatty():
        raise ValueError('chat 需要交互终端；脚本请使用 start/run/resume。')
    return asyncio.run(Chat(initialize(args)).loop())
