"""Bounded retry, endpoint cooldown and optional project-local metadata cache."""
from contextvars import ContextVar
from functools import wraps
from email.utils import parsedate_to_datetime
import hashlib
import json
from pathlib import Path
import time
from urllib.parse import urlparse

SESSION = ContextVar('literature_session', default=None)


def retrieval_session(function):
    @wraps(function)
    def wrapped(*args, **kwargs):
        cache = kwargs.pop('cache_dir', None)
        if SESSION.get() is not None:
            return function(*args, **kwargs)
        state = {'cooldowns': {}, 'cache': Path(cache) if cache else None,
                 'cache_hits': 0, 'requests': 0, 'retries': 0, 'skipped': 0}
        if state['cache']:
            state['cache'].mkdir(parents=True, exist_ok=True)
            try:
                state['cooldowns'] = json.loads((state['cache'] / 'cooldowns.json').read_text())
            except (OSError, ValueError):
                pass
        token = SESSION.set(state)
        try:
            result = function(*args, **kwargs)
            result.coverage['transport'] = {k: state[k] for k in ('cache_hits', 'requests', 'retries', 'skipped')}
            return result
        finally:
            if state['cache']:
                (state['cache'] / 'cooldowns.json').write_text(json.dumps(state['cooldowns']))
            SESSION.reset(token)
    return wrapped


def retry_seconds(headers):
    value = (headers or {}).get('Retry-After', '')
    try:
        return max(0, float(value))
    except (ValueError, TypeError):
        try:
            return max(0, parsedate_to_datetime(value).timestamp() - time.time())
        except (ValueError, TypeError, OverflowError):
            return 1.0


def request_with_policy(fetch, url, timeout_s, headers, error_type):
    state = SESSION.get()
    identity = hashlib.sha256(json.dumps(headers or {}, sort_keys=True).encode()).hexdigest()
    host = urlparse(url).hostname or ''
    endpoint = host + ':' + identity
    key = hashlib.sha256((url + identity).encode()).hexdigest()
    cached = state['cache'] / (key + '.bin') if state and state['cache'] else None
    if cached and cached.exists() and time.time() - cached.stat().st_mtime < 86400:
        data = cached.read_bytes()
        if len(data) <= 8 * 1024 * 1024:
            state['cache_hits'] += 1
            return data
    previous = state['cooldowns'].get(endpoint, {}) if state else {}
    if previous.get('until', 0) > time.time():
        state['skipped'] += 1
        raise error_type(f"{host}: provider cooldown after HTTP {previous['status']}; using alternate metadata sources")
    deadline = time.monotonic() + timeout_s
    for attempt in range(3):
        try:
            if state:
                state['requests'] += 1
            data = fetch(url, max(.001, deadline - time.monotonic()), headers)
            if cached:
                cached.write_bytes(data)
            return data
        except error_type as exc:
            status = getattr(exc, 'status', None)
            delay = getattr(exc, 'retry_after', 1.0) if status == 429 else 2 ** attempt
            transient = status in {429, 500, 502, 503, 504}
            if transient and attempt < 2 and delay <= 3 and deadline - time.monotonic() > delay + 1:
                if state:
                    state['retries'] += 1
                time.sleep(delay)
                continue
            if state and status in {401, 403, 429, 500, 502, 503, 504}:
                state['cooldowns'][endpoint] = {'status': status,
                    'until': time.time() + (max(60, delay) if status == 429 else 300)}
            raise
