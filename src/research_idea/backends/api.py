"""Direct API adapters with a hard end-to-end transport deadline.

A generate() task makes one HTTP attempt. The shared caller retries provider
failures every 30 seconds, counting each attempt against max_calls. Successful
usage.transport_attempts and errors report the attempted request count. A worker
process owns each request and is killed/reaped on timeout: no daemon thread can
continue an invisible HTTP request after this adapter returns.
"""
from __future__ import annotations

import base64
import ipaddress
import json
import os
import re
import time
import sys
import urllib.parse
from pathlib import Path
from typing import Any

from research_idea.backend_types import BackendError, BackendResult, TaskSpec
from research_idea.backend_errors import ProviderError, classify_provider_error
from .common import MAX_RESPONSE_BYTES, parse_object, positive_timeout, run_cli


class APITransportError(BackendError):
    def __init__(self, message: str, attempts: int):
        super().__init__(message)
        self.transport_attempts = attempts


def _request_once(url: str, body: dict[str, Any], headers: dict[str, str], timeout_s: float) -> dict[str, Any]:
    """Run one HTTP exchange in a child that can be forcibly cancelled."""
    spec = {"url": url, "body": body, "headers": headers, "timeout_s": timeout_s}
    worker = Path(__file__).with_name("_http_worker.py")
    raw = run_cli([sys.executable, "-I", str(worker)], json.dumps(spec), worker.parent, timeout_s)
    return parse_object(raw, "HTTP worker")


def _local_hostname(host: str | None) -> bool:
    if host == "localhost":
        return True
    try:
        return ipaddress.ip_address(host or "").is_loopback
    except ValueError:
        return False


def endpoint_url(base_url: str, provider: str) -> str:
    try:
        parts = urllib.parse.urlsplit(base_url)
        _ = parts.port
    except ValueError as exc:
        raise BackendError("Invalid API base_url") from exc
    if not parts.hostname or parts.username or parts.password or parts.query or parts.fragment:
        raise BackendError("API base_url must be an absolute URL without credentials, query, or fragment")
    if parts.scheme != "https" and not (parts.scheme == "http" and _local_hostname(parts.hostname)):
        raise BackendError("API base_url requires HTTPS; HTTP is allowed only on a loopback host")
    suffix = "/messages" if provider == "anthropic" else "/chat/completions"
    path = parts.path.rstrip("/")
    if not path:
        path = "/v1"
    if not path.endswith(suffix):
        path += suffix
    return urllib.parse.urlunsplit((parts.scheme, parts.netloc, path, "", ""))


class APIBackend:
    name = "api"

    def __init__(self, config: dict[str, Any], workspace: Path):
        self.config = config
        self.workspace = workspace
        self.provider = config.get("api_provider", "openai-compatible")
        if self.provider not in {"openai-compatible", "anthropic"}:
            raise BackendError("api_provider must be 'openai-compatible' or 'anthropic'")
        default_url = "https://api.anthropic.com/v1" if self.provider == "anthropic" else "https://api.openai.com/v1"
        self.url = endpoint_url(str(config.get("base_url") or default_url), self.provider)

    def _headers(self) -> dict[str, str]:
        default_env = "ANTHROPIC_API_KEY" if self.provider == "anthropic" else "OPENAI_API_KEY"
        env_name = self.config.get("api_key_env", default_env)
        if env_name == "" and _local_hostname(urllib.parse.urlsplit(self.url).hostname):
            key = ""
        else:
            if not isinstance(env_name, str) or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", env_name):
                raise BackendError("api_key_env must name an environment variable")
            key = os.environ.get(env_name, "")
            if not key:
                raise BackendError(f"Set the {env_name} environment variable before using the API backend")
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        if self.provider == "anthropic":
            headers["anthropic-version"] = "2023-06-01"
            if key:
                headers["x-api-key"] = key
        elif key:
            headers["Authorization"] = "Bearer " + key
        return headers

    def _post(self, body: dict[str, Any], timeout_s: float) -> tuple[dict[str, Any], str, int]:
        deadline = time.monotonic() + positive_timeout(timeout_s)
        try:
            headers = self._headers()
        except BackendError as exc:
            raise APITransportError(str(exc), 0) from None
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise ProviderError('timeout', transport_attempts=0)
        try:
            transport = _request_once(self.url, body, headers, remaining)
        except BackendError as exc:
            category = getattr(exc, 'category', 'network')
            raise ProviderError(category, transport_attempts=1,
                                diagnostic='API transport failed or exceeded its total timeout') from None
        kind = transport.get("kind")
        if kind == "response":
            try:
                payload = base64.b64decode(transport["body_base64"], validate=True)
                if len(payload) > MAX_RESPONSE_BYTES:
                    raise ValueError("oversize")
                raw = payload.decode("utf-8")
                value = parse_object(raw, "API")
            except (KeyError, ValueError, TypeError, BackendError):
                raise ProviderError('api', transport_attempts=1,
                                    diagnostic='API 返回了无法解析的响应。') from None
            return value, raw, 1
        if kind == "http_error":
            status = transport.get("status")
            try:
                detail = base64.b64decode(transport.get('body_base64', ''), validate=True).decode('utf-8', errors='replace')
            except (ValueError, TypeError):
                detail = ''
            hint = ('Verify model, endpoint and native strict JSON-schema support (no fallback was attempted).'
                    if status in {400, 404, 422} else '')
            raise ProviderError(classify_provider_error(detail, status), status=status,
                                transport_attempts=1, diagnostic=hint)
        if kind == "connection_error":
            raise ProviderError('network', transport_attempts=1)
        if kind == "oversize":
            raise APITransportError("API response exceeded the size limit", 1)
        raise ProviderError('api', transport_attempts=1)

    def generate(self, task: TaskSpec) -> BackendResult:
        model = task.model or self.config.get("model")
        if not isinstance(model, str) or not model.strip():
            raise BackendError("The API backend requires an explicit model")
        limit = self.config.get("max_output_tokens", 8192)
        if isinstance(limit, bool) or not isinstance(limit, int) or limit < 1:
            raise BackendError("max_output_tokens must be a positive integer")
        if self.provider == "anthropic":
            body = {
                "model": model, "max_tokens": limit,
                "messages": [{"role": "user", "content": task.prompt}],
                "output_config": {"format": {"type": "json_schema", "schema": task.output_schema}},
            }
        else:
            token_field = self.config.get("api_max_tokens_field", "max_completion_tokens")
            if token_field not in {"max_completion_tokens", "max_tokens"}:
                raise BackendError("api_max_tokens_field must be max_completion_tokens or max_tokens")
            body = {
                "model": model, token_field: limit,
                "messages": [{"role": "user", "content": task.prompt}],
                "response_format": {"type": "json_schema", "json_schema": {
                    "name": "research_result", "strict": True, "schema": task.output_schema,
                }},
            }
        envelope, raw, attempts = self._post(body, task.timeout_s)
        if envelope.get('error'):
            raise ProviderError(classify_provider_error(envelope['error']), transport_attempts=attempts)
        try:
            result = self._decode(envelope)
        except BackendError as exc:
            raise APITransportError(str(exc), attempts) from None
        usage = dict(envelope["usage"]) if isinstance(envelope.get("usage"), dict) else {}
        usage.update({"provider": self.provider, "model": envelope.get("model", model),
                      "transport_attempts": attempts, "http_attempts": attempts})
        return BackendResult(result, usage, None, raw)

    def _decode(self, envelope: dict[str, Any]) -> dict[str, Any]:
        if self.provider == "anthropic":
            if envelope.get("stop_reason") != "end_turn":
                raise BackendError("Anthropic response did not complete normally; no partial result accepted")
            content = envelope.get("content")
            if not isinstance(content, list):
                raise BackendError("Anthropic response is missing content")
            texts = [block.get("text") for block in content
                     if isinstance(block, dict) and block.get("type") == "text"]
            if not texts or any(not isinstance(value, str) for value in texts):
                raise BackendError("Anthropic response is missing valid text content")
            text = "".join(texts)
        else:
            try:
                choice = envelope["choices"][0]
                message = choice["message"]
            except (KeyError, IndexError, TypeError) as exc:
                raise BackendError("API response is missing choices[0].message") from exc
            if not isinstance(choice, dict) or not isinstance(message, dict):
                raise BackendError("API response contains an invalid message")
            if choice.get("finish_reason") != "stop" or message.get("refusal"):
                raise BackendError("API response was refused, truncated, or incomplete")
            text = message.get("content")
            if not isinstance(text, str):
                raise BackendError("API message content is not a JSON string")
        return parse_object(text, "API model")
