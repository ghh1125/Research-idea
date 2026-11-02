"""Loopback-only Web workbench for durable local research projects."""
from __future__ import annotations

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib.resources import files
import json
from pathlib import Path
import re
import secrets
import threading
from urllib.parse import parse_qs, urlsplit
import webbrowser

from .model_discovery import discover_models
from .web_runtime import WebWorkspace


def make_server(port=8769, *, codex_bin='codex', profile=None, projects=None, output=None):
    lock = threading.Lock()
    workspace = WebWorkspace(projects or Path.cwd() / 'research-projects', output=output,
                             codex_bin=codex_bin, profile=profile)
    token = secrets.token_urlsafe(32)

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def reply(self, status, body, content_type='application/json; charset=utf-8'):
            if not isinstance(body, bytes):
                body = json.dumps(body, ensure_ascii=False).encode('utf-8')
            self.send_response(status)
            self.send_header('Content-Type', content_type)
            self.send_header('Content-Length', str(len(body)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('Referrer-Policy', 'no-referrer')
            self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'")
            self.end_headers()
            try:
                self.wfile.write(body)
            except (BrokenPipeError, ConnectionResetError):
                pass

        def local_access(self):
            port = self.server.server_port
            hosts = {f'127.0.0.1:{port}', f'localhost:{port}'}
            if self.headers.get('Host') not in hosts or self.headers.get('Origin') not in {None, *(f'http://{h}' for h in hosts)}:
                self.reply(403, {'error': 'Local access only'})
                return False
            return True

        def do_GET(self):
            if not self.local_access():
                return
            try:
                self.get()
            except FileNotFoundError as exc:
                self.reply(404, {'error': str(exc)})
            except (ValueError, RuntimeError, OSError) as exc:
                self.reply(400, {'error': str(exc)})

        def get(self):
            url = urlsplit(self.path)
            if url.path in {'/', '/index.html'}:
                self.reply(200, files('research_idea').joinpath('web_assets/index.html').read_bytes(),
                           'text/html; charset=utf-8')
            elif url.path in {'/app.js', '/style.css'}:
                self.reply(200, files('research_idea').joinpath('web_assets', url.path[1:]).read_bytes(),
                           'text/javascript; charset=utf-8' if url.path.endswith('.js') else 'text/css; charset=utf-8')
            elif url.path == '/api/session':
                self.reply(200, {'token': token, 'projects_root': str(workspace.root)})
            elif url.path == '/api/projects':
                self.reply(200, {'projects': workspace.list_projects()})
            elif url.path == '/api/trash':
                self.reply(200, {'projects': workspace.list_trash()})
            elif match := re.fullmatch(r'/api/projects/([\w-]+)', url.path):
                self.reply(200, workspace.snapshot(match[1]))
            elif url.path.startswith('/api/skills/'):
                name = url.path.removeprefix('/api/skills/')
                if not re.fullmatch(r'research-idea-[a-z-]+', name):
                    self.reply(404, {'error': 'Skill not found'})
                    return
                source = files('research_idea').joinpath('builtin_skills', name, 'SKILL.md')
                if not source.is_file():
                    self.reply(404, {'error': 'Skill not found'})
                    return
                self.reply(200, {'name': name, 'content': source.read_text(encoding='utf-8')})
            elif url.path == '/api/models':
                params = parse_qs(url.query)
                if params.get('backend', ['codex'])[0] != 'codex':
                    self.reply(200, {'models': [], 'source': 'unsupported', 'error': '',
                                     'note': '此连接方式尚未接入模型发现；可沿用后端默认配置。'})
                    return
                if not lock.acquire(blocking=False):
                    self.reply(409, {'error': '模型列表正在刷新，请稍后重试'})
                    return
                try:
                    self.reply(200, discover_models(refresh=params.get('refresh') == ['1'],
                                                   codex_bin=codex_bin, profile=profile))
                finally:
                    lock.release()
            else:
                self.reply(404, {'error': 'Not found'})

        def do_POST(self):
            if not self.local_access():
                return
            if not secrets.compare_digest(self.headers.get('X-Research-Token', ''), token):
                self.reply(403, {'error': '页面已过期，请刷新后重试'})
                return
            if self.headers.get('Content-Type', '').split(';')[0] != 'application/json':
                self.reply(415, {'error': 'JSON required'})
                return
            try:
                size = int(self.headers.get('Content-Length', '0'))
                if not 0 < size <= 256 * 1024:
                    self.reply(413, {'error': '请求过大或为空'})
                    return
                data = json.loads(self.rfile.read(size))
                if not isinstance(data, dict):
                    raise ValueError('请求必须是 JSON 对象')
                path = urlsplit(self.path).path
                if path == '/api/projects':
                    self.reply(201, workspace.create(data.get('title', ''), data.get('model', 'gpt-6-astra'), data.get('effort', 'medium')))
                    return
                if match := re.fullmatch(r'/api/trash/([\w-]+)/restore', path):
                    self.reply(200, workspace.restore(match[1]))
                    return
                match = re.fullmatch(r'/api/projects/([\w-]+)/(settings|actions)', path)
                if not match:
                    self.reply(404, {'error': 'Not found'})
                    return
                ident, route = match.groups()
                if route == 'settings':
                    self.reply(200, workspace.configure(ident, data))
                elif data.get('action') == 'stop':
                    self.reply(200, workspace.stop(ident))
                elif data.get('action') == 'pin':
                    self.reply(200, workspace.pin(ident, data.get('pinned')))
                elif data.get('action') == 'archive':
                    self.reply(200, workspace.archive(ident))
                else:
                    self.reply(202, workspace.start(ident, data.get('action'), data.get('message', '')))
            except FileNotFoundError as exc:
                self.reply(404, {'error': str(exc)})
            except RuntimeError as exc:
                self.reply(409, {'error': str(exc)})
            except (ValueError, OSError, TypeError) as exc:
                self.reply(400, {'error': str(exc)})

    class Server(ThreadingHTTPServer):
        def server_close(self):
            super().server_close()
            workspace.close()

    try:
        server = Server(('127.0.0.1', port), Handler)
        server.workspace = workspace
        return server
    except Exception:
        workspace.close()
        raise


def serve(args):
    if not 0 <= args.port <= 65535:
        raise ValueError('port must be between 0 and 65535')
    with make_server(args.port, codex_bin=args.codex_bin, profile=args.codex_profile,
                     projects=args.projects, output=args.output) as server:
        url = f'http://127.0.0.1:{server.server_port}/'
        print(f'Web: {url}\n本地研究工作台 · 对话、调研与进度自动保存。Ctrl+C 关闭服务。', flush=True)
        if not args.no_browser:
            webbrowser.open(url)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
    return 0
