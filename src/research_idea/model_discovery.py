"""Read public Codex model metadata without exposing credentials or starting turns."""
from __future__ import annotations

import json
import os
from pathlib import Path
import queue
import subprocess
import threading
import time

from . import __version__
from .config import REASONING_EFFORTS


def normalize_models(items):
    models, seen = [], set()
    if not isinstance(items, list):
        return models
    for item in items:
        if not isinstance(item, dict) or item.get('hidden') or item.get('visibility', 'list') != 'list':
            continue
        ident = item.get('model') or item.get('slug') or item.get('id')
        if not isinstance(ident, str) or not ident or any(c.isspace() for c in ident) or ident in seen:
            continue
        levels = item.get('supportedReasoningEfforts', item.get('supported_reasoning_levels', []))
        levels = levels if isinstance(levels, list) else []
        efforts = list(dict.fromkeys(r.get('reasoningEffort', r.get('effort')) for r in levels
                      if isinstance(r, dict) and r.get('reasoningEffort', r.get('effort')) in REASONING_EFFORTS))
        name = item.get('displayName', item.get('display_name', ident))
        default = item.get('defaultReasoningEffort', item.get('default_reasoning_level', ''))
        models.append({'id': ident, 'name': name if isinstance(name, str) else ident,
                       'levels': efforts, 'default_effort': default if default in efforts else ''})
        seen.add(ident)
    return models


def cached_catalog():
    path = Path(os.environ.get('CODEX_HOME', '~/.codex')).expanduser() / 'models_cache.json'
    try:
        if path.stat().st_size > 8 * 1024 * 1024:
            raise ValueError('cache size')
        data = json.loads(path.read_text(encoding='utf-8'))
        models = normalize_models(data.get('models'))
        fetched = data.get('fetched_at')
        return {'models': models, 'source': 'cache', 'updated_at': fetched if isinstance(fetched, str) else '',
                'note': '本地 Codex 缓存；可刷新读取 CLI 目录', 'error': ''}
    except (OSError, ValueError, TypeError, AttributeError):
        return {'models': [], 'source': 'unavailable', 'updated_at': '',
                'note': '没有可读的 Codex 模型缓存，请刷新', 'error': ''}


def read_codex_models(codex_bin='codex', profile=None, timeout=20):
    command = [codex_bin]
    if profile:
        command += ['--profile', profile]
    command += ['app-server', '--listen', 'stdio://']
    process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                               stderr=subprocess.DEVNULL, text=True, encoding='utf-8', errors='replace')
    messages = queue.Queue()
    deadline = time.monotonic() + timeout

    def read():
        try:
            for line in iter(lambda: process.stdout.readline(2 * 1024 * 1024), ''):
                if len(line) >= 2 * 1024 * 1024:
                    break
                try:
                    message = json.loads(line)
                    # Ignore notifications; never forward raw diagnostics/account fields.
                    if isinstance(message, dict) and 'id' in message:
                        messages.put(message)
                except ValueError:
                    continue
        finally:
            messages.put(None)

    reader = threading.Thread(target=read, daemon=True)
    reader.start()

    def send(message):
        process.stdin.write(json.dumps(message) + '\n')
        process.stdin.flush()

    def request(ident, method, params):
        send({'id': ident, 'method': method, 'params': params})
        while True:
            try:
                message = messages.get(timeout=max(0, deadline - time.monotonic()))
            except queue.Empty:
                raise TimeoutError('Codex model list timed out') from None
            if message is None:
                raise RuntimeError('Codex model list closed')
            if message.get('id') == ident and 'method' not in message:
                if 'error' in message or not isinstance(message.get('result'), dict):
                    raise RuntimeError('Codex model list request failed')
                return message['result']

    try:
        request(1, 'initialize', {'clientInfo': {'name': 'research_idea', 'version': __version__}})
        send({'method': 'initialized', 'params': {}})
        items, cursor, cursors = [], None, set()
        for page in range(50):
            params = {'limit': 100, 'includeHidden': False}
            if cursor:
                params['cursor'] = cursor
            result = request(page + 2, 'model/list', params)
            if not isinstance(result.get('data'), list):
                raise RuntimeError('Invalid Codex model list')
            items.extend(result['data'])
            cursor = result.get('nextCursor')
            if not cursor:
                return normalize_models(items)
            if not isinstance(cursor, str) or cursor in cursors:
                raise RuntimeError('Invalid Codex model cursor')
            cursors.add(cursor)
        raise RuntimeError('Codex model pagination did not finish')
    finally:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=3)
        reader.join(timeout=1)
        process.stdin.close()
        process.stdout.close()


def discover_models(*, refresh=False, codex_bin='codex', profile=None):
    cached = cached_catalog()
    if not refresh and cached['models'] and not profile and codex_bin == 'codex':
        return cached
    try:
        models = read_codex_models(codex_bin, profile)
        return {'models': models, 'source': 'codex', 'updated_at': '', 'error': '',
                'note': '刚从 Codex CLI 读取模型目录（CLI 可能使用自身缓存）'}
    except (OSError, RuntimeError, TimeoutError):
        if profile or codex_bin != 'codex':
            cached = {'models': [], 'source': 'unavailable', 'updated_at': '', 'note': '', 'error': ''}
        cached['error'] = '读取 CLI 目录失败，请检查 Codex 安装与登录后重试。'
        cached['note'] = '刷新失败，显示本地缓存' if cached['models'] else '暂时无法读取模型列表'
        return cached
