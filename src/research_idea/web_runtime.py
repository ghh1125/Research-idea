"""Local Web workspace backed by the same durable CLI projects and workers."""
from __future__ import annotations

from datetime import datetime
import base64
import binascii
import json
import os
from pathlib import Path
import re
import signal
import shutil
import subprocess
import sys
import threading
import tempfile
import time
import uuid

from .config import load_config, write_config
from .conversation import memory_text, transcript
from .locking import project_lock
from .output_paths import saved_report
from .problem_dialogue import WAITING_BY_KIND, problem_text
from .store import Store
from .landscape import reference_papers


SETTINGS = {'model', 'reasoning_effort', 'max_calls', 'max_seconds', 'timeout_s',
            'max_papers', 'max_candidates', 'constraints', 'auto_search',
            'search_results_per_query', 'search_date_mode', 'strategy_months', 'novelty_months',
            'search_since', 'search_until', 'conference_policy', 'search_venues', 'search_source',
            'arxiv_categories'}
PUBLIC_SETTINGS = SETTINGS | {'backend', 'output_dir', 'search_source'}
STEPS = ['明确方向', '文献调研', '方向讨论', '深入分析', '问题讨论', '研究主张']


class WebWorkspace:
    def __init__(self, root, *, output=None, codex_bin='codex', profile=None):
        self.root = Path(root).expanduser().resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.output = Path(output).expanduser().resolve() if output else self.root.parent / 'results'
        self.codex_bin, self.profile = codex_bin, profile
        self.lock = threading.RLock()
        self.jobs = {}
        self.closed = False
        # A second server must not mistake another server's live worker for an
        # interrupted job. CLI workers retain their existing per-project lock.
        self.guard = project_lock(self.root / '.web')
        self.guard.__enter__()

    def project(self, ident):
        if not isinstance(ident, str) or not re.fullmatch(r'[\w-]{1,100}', ident):
            raise ValueError('无效的研究项目')
        path = (self.root / ident).resolve()
        if path.parent != self.root or not (path / 'research.toml').is_file() or not (path / 'research.sqlite3').is_file():
            raise FileNotFoundError('研究项目不存在')
        return path

    def create(self, title='', model=None, effort=None, *, inherit=None):
        if not isinstance(title, str) or len(title) > 8000:
            raise ValueError('研究方向最多 8000 字')
        previous = load_config(self.project(inherit)) if inherit else None
        model = model if model is not None else previous['model'] if previous else 'gpt-6-astra'
        effort = effort if effort is not None else previous['reasoning_effort'] if previous else 'medium'
        from .config import REASONING_EFFORTS
        if not isinstance(model, str) or model and not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_./:-]{0,149}', model):
            raise ValueError('无效的模型名称')
        if effort not in ('', *REASONING_EFFORTS):
            raise ValueError('无效的思考强度')
        from .chat import initialize
        from .cli import build_parser
        ident = 'idea-' + datetime.now().strftime('%Y%m%d-%H%M%S-') + uuid.uuid4().hex[:6]
        args = ['chat', '--project', str(self.root / ident), '--backend', 'codex',
                '--model', model, '--reasoning-effort', effort or 'inherit', '--codex-bin', self.codex_bin,
                '--output', str(self.output)]
        if self.profile:
            args += ['--codex-profile', self.profile]
        project = initialize(build_parser().parse_args(args))
        if previous:
            write_config(project, {**previous, 'model': model, 'reasoning_effort': effort})
        store = Store(project)
        try:
            store.set_many({'topic': title.strip(), 'status': 'initialized'})
        finally:
            store.close()
        return self.snapshot(ident)

    def list_projects(self):
        projects = []
        for path in self.root.iterdir():
            if path.is_dir() and (path / 'research.toml').is_file() and (path / 'research.sqlite3').is_file():
                try:
                    projects.append(self.snapshot(path.name, brief=True))
                except (ValueError, OSError):
                    continue
        return sorted(projects, key=lambda p: (p['pinned'], p['modified']), reverse=True)

    def pin(self, ident, pinned):
        if type(pinned) is not bool:
            raise ValueError('置顶状态必须为布尔值')
        project = self.project(ident)
        store = Store(project)
        try:
            store.set('web_pinned', pinned)
        finally:
            store.close()
        return {'pinned': pinned}

    def trash_root(self):
        trash = (self.root / '.trash').resolve()
        if trash.parent != self.root:
            raise ValueError('回收站必须位于当前工作空间内')
        return trash

    def archive(self, ident):
        with self.lock:
            self.require_idle(ident)
            project = self.project(ident)
            # Release the file lock before rename: Windows locks cannot move.
            # A CLI acquiring the file in this interval makes rename fail safely.
            with project_lock(project):
                pass
            trash = self.trash_root()
            trash.mkdir(exist_ok=True)
            destination = trash / ident
            if destination.exists():
                raise RuntimeError('回收站中已有同名研究，请先恢复')
            project.rename(destination)
            self.jobs.pop(ident, None)
        return {'archived': True, 'id': ident}

    def list_trash(self):
        trash = self.trash_root()
        if not trash.exists():
            return []
        entries = []
        for path in trash.iterdir():
            if path.resolve().parent != trash or not (path / 'research.sqlite3').is_file():
                continue
            store = Store(path, readonly=True)
            try:
                entries.append({'id': path.name, 'title': store.get('topic') or '新的研究'})
            finally:
                store.close()
        return entries

    def restore(self, ident):
        if not isinstance(ident, str) or not re.fullmatch(r'[\w-]{1,100}', ident):
            raise ValueError('无效的研究项目')
        with self.lock:
            trash = self.trash_root()
            source = (trash / ident).resolve()
            destination = self.root / ident
            if source.parent != trash or not (source / 'research.toml').is_file():
                raise FileNotFoundError('回收站中没有这项研究')
            if destination.exists():
                raise RuntimeError('已有同名研究，恢复未执行')
            source.rename(destination)
        return self.snapshot(ident)

    def snapshot(self, ident, *, brief=False):
        project = self.project(ident)
        cfg = load_config(project)
        store = Store(project, readonly=True)
        try:
            with self.lock:
                job = self.jobs.get(ident)
                busy = bool(job and not job['done'].is_set())
                stopping = bool(busy and job['stop'].is_set())
                mode = job['mode'] if busy else None
                extra_time = time.monotonic() - job['started'] if busy else 0
                base_time = job['elapsed'] if busy else 0
            # External CLI runs cannot be stopped by this server or overwritten.
            external = False
            if not busy:
                try:
                    # Two simultaneous read requests must not mistake each
                    # other's short lock probe for an external CLI writer.
                    with self.lock:
                        with project_lock(project):
                            pass
                except RuntimeError:
                    external = True
            checkpoint = store.get('problem_checkpoint') or {}
            cycle = store.get('question_cycle') or {}
            status = store.get('status', 'initialized')
            last_job = store.get('web_job') or {}
            interrupted = not busy and not external and last_job.get('state') in {'running', 'stopping'}
            index = 0
            if cycle or status == 'running' or (busy and mode != 'chat'):
                index = 1
            if checkpoint.get('kind') == 'direction':
                index = 2 if checkpoint.get('state') == 'discussing' else 3
            elif checkpoint.get('kind') in {'problem', 'idea'}:
                index = 4 if checkpoint.get('state') == 'discussing' else 5
            if status == 'completed':
                index = 5
            steps = [{'label': label, 'state': ('complete' if i < index or status == 'completed' else
                     'current' if i == index else 'pending')} for i, label in enumerate(STEPS)]
            result = {'id': ident, 'title': store.get('topic') or '新的研究', 'status': status,
                      'pinned': bool(store.get('web_pinned', False)),
                      'busy': busy or external, 'external': external, 'stopping': stopping,
                      'mode': mode, 'interrupted': interrupted, 'stage': index, 'steps': steps,
                      'can_continue': bool(checkpoint.get('state') == 'discussing' and not store.get('pending_chat_message')),
                      'pending_message': bool(store.get('pending_chat_message')),
                      'modified': (project / 'research.sqlite3').stat().st_mtime,
                      'calls': store.get('calls_used', 0), 'max_calls': cfg['max_calls'],
                      'elapsed': max(store.get('elapsed_s', 0), base_time + extra_time),
                      'max_seconds': cfg['max_seconds'], 'model': cfg['model'],
                      'paper_count': len(reference_papers(store))}
            if brief:
                return result
            rows = store.db.execute("SELECT id,timestamp,payload FROM events WHERE kind='web_output' ORDER BY id DESC LIMIT 240").fetchall()
            events = [{'id': r[0], 'time': r[1], **json.loads(r[2])} for r in reversed(rows)]
            report_path = saved_report(store)
            from .citations import Citations
            citations = Citations.from_store(store)
            result.update(config={k: cfg[k] for k in PUBLIC_SETTINGS}, path=str(project),
                          checkpoint_time=checkpoint.get('created_at'),
                          messages=transcript(store), events=events,
                          memory=memory_text(store), problem=problem_text(store, detail=True),
                          report=report_path.read_text(encoding='utf-8') if report_path.is_file() else '',
                          report_path=str(report_path) if report_path.is_file() else '',
                          papers=[{**{k: p.get(k) for k in ('id', 'title', 'url', 'year', 'abstract', 'content_kind', 'authors')},
                                   'text_excerpt': str(p.get('text') or '')[:8000]}
                                  for p in reference_papers(store)],
                          literature_landscape=store.get('literature_landscape'),
                          evidence=[{**e, 'display_text': citations.block(e)} for e in citations.evidence.values()], last_job=last_job)
            return result
        finally:
            store.close()

    def configure(self, ident, values):
        if not isinstance(values, dict) or not values or set(values) - SETTINGS:
            raise ValueError('不支持的设置字段')
        if 'model' in values and (not isinstance(values['model'], str) or values['model'] and
                not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_./:-]{0,149}', values['model'])):
            raise ValueError('无效的模型名称')
        if 'search_venues' in values:
            from .venues import normalize_venues
            raw = values['search_venues']
            if not isinstance(raw, list) or any(not isinstance(v, str) for v in raw):
                raise ValueError('会议名单需要使用会议名称列表')
            values = {**values, 'search_venues': normalize_venues(raw)}
        project = self.project(ident)
        with self.lock:
            self.require_idle(ident)
            with project_lock(project):
                cfg = load_config(project)
                cfg.update(values)
                write_config(project, cfg)
        return self.snapshot(ident)

    def require_idle(self, ident):
        if self.closed:
            raise RuntimeError('服务正在关闭')
        job = self.jobs.get(ident)
        if job and not job['done'].is_set():
            raise RuntimeError('本研究正在运行，请先停止或等待完成')

    def import_uploads(self, ident, uploads):
        """Import selected bytes, never a client-supplied path, using the CLI importer."""
        if not isinstance(uploads, list) or not 1 <= len(uploads) <= 10:
            raise ValueError('请选择 1–10 个论文文件')
        decoded, total = [], 0
        for item in uploads:
            if not isinstance(item, dict) or not isinstance(item.get('name'), str) or not isinstance(item.get('data'), str):
                raise ValueError('无效的附件')
            name = item['name']
            if not name or len(name) > 180 or '/' in name or '\\' in name or any(ord(c) < 32 for c in name):
                raise ValueError('附件名称不能包含路径或控制字符')
            if Path(name).suffix.lower() not in {'.pdf', '.txt', '.md', '.json'}:
                raise ValueError('论文支持 PDF、TXT、Markdown 和论文 JSON')
            try:
                raw = base64.b64decode(item['data'], validate=True)
            except (ValueError, binascii.Error):
                raise ValueError('附件传输不完整，请重新选择文件') from None
            total += len(raw)
            if not raw or total > 8 * 1024 * 1024:
                raise ValueError('附件不能为空，合计最多 8 MB')
            decoded.append((name, raw))
        project = self.project(ident)
        with self.lock:
            self.require_idle(ident)
        with project_lock(project):
            root = (project / 'uploads').resolve()
            if root.parent != project:
                raise ValueError('附件目录必须位于当前研究中')
            root.mkdir(exist_ok=True)
            folder = Path(tempfile.mkdtemp(prefix='papers-', dir=root))
            try:
                from .cli import read_paper_records, import_papers
                paths = []
                for i, (name, raw) in enumerate(decoded):
                    sub = folder / str(i)
                    sub.mkdir()
                    path = sub / name
                    path.write_bytes(raw)
                    paths.append((path, False))
                records = read_paper_records(paths)
                store = Store(project)
                try:
                    added = import_papers(store, records)
                finally:
                    store.close()
            except Exception:
                shutil.rmtree(folder)
                raise
        self.record(project, 'paper', f'已导入 {len(records)} 条论文资料（新增 {added} 篇），可在文献页查看。尚未调用模型阅读。')
        return {'imported': len(records), 'added': added}

    def record(self, project, tag, text):
        store = Store(project)
        try:
            store.event('web_output', {'tag': tag, 'text': str(text)})
        finally:
            store.close()

    def start(self, ident, mode, message=''):
        if mode not in {'chat', 'run', 'continue'}:
            raise ValueError('未知操作')
        if not isinstance(message, str) or len(message) > 32000 or '\x00' in message:
            raise ValueError('消息最多 32000 字，且不能包含空字符')
        if mode == 'chat' and not message.strip():
            raise ValueError('请先输入研究方向或讨论意见')
        if mode == 'chat' and message.lstrip().startswith('/'):
            from .web_commands import execute
            return execute(self, ident, message.strip())
        project = self.project(ident)
        with self.lock:
            self.require_idle(ident)
            with project_lock(project):
                store = Store(project)
                try:
                    if store.get('demo'):
                        raise ValueError('合成演示项目不能调用真实模型，请新建研究')
                    if mode != 'chat' and not store.get('topic'):
                        raise ValueError('请先发送研究方向，再开始调研')
                    checkpoint = store.get('problem_checkpoint') or {}
                    if mode == 'continue' and (checkpoint.get('state') != 'discussing' or store.get('pending_chat_message')):
                        raise ValueError('目前不能推进；请先完成当前讨论，失败的消息可重新发送')
                    if mode == 'run' and checkpoint.get('state') == 'discussing':
                        raise ValueError('当前已暂停讨论，请发送意见或点击继续下一阶段')
                    if mode == 'chat' and not store.get('topic'):
                        store.set('topic', message.strip())
                    base = store.get('elapsed_s', 0)
                    store.interrupt_running_tasks()
                    store.set('web_job', {'state': 'running', 'mode': mode})
                finally:
                    store.close()
            job = {'mode': mode, 'message': message, 'started': time.monotonic(), 'elapsed': base,
                   'stop': threading.Event(), 'done': threading.Event(), 'process': None}
            self.jobs[ident] = job
            thread = threading.Thread(target=self.work, args=(ident, project, job), daemon=True)
            job['thread'] = thread
            thread.start()
        return {'accepted': True}

    def work(self, ident, project, job):
        failed = False
        code = 1
        process = None
        try:
            self.record(project, 'start', {'chat': '正在回应你的想法', 'run': '开始调研文献', 'continue': '继续下一阶段'}[job['mode']])
            env = dict(os.environ, PYTHONUTF8='1', PYTHONIOENCODING='utf-8')
            options = {'creationflags': subprocess.CREATE_NO_WINDOW} if os.name == 'nt' else {'start_new_session': True}
            process = subprocess.Popen([sys.executable, '-u', '-m', 'research_idea.chat_worker'],
                       stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                       env=env, **options)
            with self.lock:
                job['process'] = process
            request = json.dumps({'project': str(project), 'mode': job['mode'], 'message': job['message']}, ensure_ascii=True)
            process.stdin.write(request.encode('ascii'))
            process.stdin.close()
            if job['stop'].is_set():
                self.terminate(process)
            for line in iter(process.stdout.readline, b''):
                try:
                    event = json.loads(line)
                    tag, text = event['tag'], event['text']
                    failed |= tag in {'error', 'budget'}
                    self.record(project, tag, text)
                except (ValueError, KeyError, TypeError):
                    continue
            code = process.wait()
            if code and not failed and not job['stop'].is_set():
                failed = True
                self.record(project, 'error', f'任务退出（{code}）。已完成的步骤已保存，可以重试。')
        except Exception as exc:
            failed = True
            self.record(project, 'error', str(exc))
        finally:
            try:
                if process:
                    if process.poll() is None:
                        self.terminate(process)
                    process.stdout.close()
                stopped = job['stop'].is_set()
                # Do not touch a project currently owned by an external CLI.
                with project_lock(project):
                    store = Store(project)
                    try:
                        store.set('web_job', {'state': 'stopped' if stopped else 'failed' if failed else 'done',
                                             'mode': job['mode'], 'exit_code': code})
                        if stopped or failed:
                            store.interrupt_running_tasks()
                            store.set('elapsed_s', max(store.get('elapsed_s', 0), job['elapsed'] + time.monotonic() - job['started']))
                    finally:
                        store.close()
                if stopped:
                    self.record(project, 'stopped', '已停止。对话与已完成的检查点已保留。')
            finally:
                job['done'].set()

    @staticmethod
    def terminate(process):
        if process.poll() is not None:
            return
        if os.name == 'nt':
            subprocess.run(['taskkill', '/PID', str(process.pid), '/T', '/F'],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=10,
                           creationflags=subprocess.CREATE_NO_WINDOW)
        else:
            try:
                os.killpg(process.pid, signal.SIGINT)
            except ProcessLookupError:
                pass
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)

    def stop(self, ident):
        self.project(ident)
        with self.lock:
            job = self.jobs.get(ident)
            if not job or job['done'].is_set():
                return {'stopped': True}
            job['stop'].set()
            process = job['process']
        if process:
            self.terminate(process)
        return {'stopping': True}

    def close(self):
        with self.lock:
            if self.closed:
                return
            self.closed = True
            jobs = list(self.jobs.items())
        for ident, job in jobs:
            if not job['done'].is_set():
                self.stop(ident)
                job['thread'].join(timeout=15)
        self.guard.__exit__(None, None, None)
