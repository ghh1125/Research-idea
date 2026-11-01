"""Loopback Web preview with real, read-only model discovery."""
from __future__ import annotations

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib.resources import files
import json
import re
import threading
from urllib.parse import parse_qs, urlsplit
import webbrowser

from .model_discovery import discover_models


def make_server(port=8769, *, codex_bin='codex', profile=None):
    lock = threading.Lock()

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
            self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'")
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            port = self.server.server_port
            hosts = {f'127.0.0.1:{port}', f'localhost:{port}'}
            if self.headers.get('Host') not in hosts or self.headers.get('Origin') not in {None, *(f'http://{h}' for h in hosts)}:
                self.reply(403, {'error': 'Local access only'})
                return
            url = urlsplit(self.path)
            if url.path in {'/', '/index.html'}:
                self.reply(200, files('research_idea').joinpath('web_assets/index.html').read_bytes(),
                           'text/html; charset=utf-8')
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

    return ThreadingHTTPServer(('127.0.0.1', port), Handler)


def serve(args):
    if not 0 <= args.port <= 65535:
        raise ValueError('port must be between 0 and 65535')
    with make_server(args.port, codex_bin=args.codex_bin, profile=args.codex_profile) as server:
        url = f'http://127.0.0.1:{server.server_port}/'
        print(f'Web: {url}\n模型列表读取本机 Codex；研究交互仍为预览。Ctrl+C 退出。', flush=True)
        if not args.no_browser:
            webbrowser.open(url)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
    return 0
