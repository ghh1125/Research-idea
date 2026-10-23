"""Project-local settings. Credentials are environment variable names, never values."""
from __future__ import annotations

import json
from pathlib import Path
import tomllib

DEFAULTS = {
    "backend": "codex", "model": "", "api_provider": "openai-compatible",
    "base_url": "https://api.openai.com/v1", "api_key_env": "OPENAI_API_KEY",
    "timeout_s": 180, "max_calls": 40, "max_seconds": 3600,
    "max_output_tokens": 8192, "api_max_tokens_field": "max_completion_tokens",
    "max_candidates": 3, "max_rounds": 2, "max_papers": 12,
    "source_chars": 24000, "search_source": "arxiv", "auto_search": True,
    "search_api_key_env": "", "constraints": "Resources unspecified; do not assume GPU access, model weights, logits, labels, or unlimited API budget.",
}

PROVIDER_DEFAULTS = {
    "openai-compatible": {
        "base_url": "https://api.openai.com/v1", "api_key_env": "OPENAI_API_KEY",
    },
    "anthropic": {
        "base_url": "https://api.anthropic.com/v1", "api_key_env": "ANTHROPIC_API_KEY",
    },
}


def _validated_settings(supplied: dict) -> dict:
    """Resolve provider defaults only for absent keys, then validate all settings.

    Explicit endpoints and credential-variable names belong to the user. In
    particular, an empty credential-variable name is meaningful for local APIs.
    """
    unknown = set(supplied) - set(DEFAULTS)
    if unknown:
        raise ValueError(f"Unknown configuration keys: {', '.join(sorted(unknown))}")
    data = dict(DEFAULTS)
    data.update(supplied)
    for key in ("backend", "model", "api_provider", "base_url", "api_key_env",
                "api_max_tokens_field", "search_source", "search_api_key_env", "constraints"):
        if not isinstance(data[key], str):
            raise ValueError(f"{key} must be a string")
    if data["api_provider"] not in PROVIDER_DEFAULTS:
        raise ValueError("api_provider must be openai-compatible or anthropic")
    for key, value in PROVIDER_DEFAULTS[data["api_provider"]].items():
        if key not in supplied:
            data[key] = value
    if data["backend"] not in {"codex", "claude", "api", "demo"}:
        raise ValueError("backend must be codex, claude, api, or demo")
    for key in ("timeout_s", "max_calls", "max_seconds", "max_candidates", "max_rounds",
                "max_papers", "source_chars", "max_output_tokens"):
        if isinstance(data[key], bool) or not isinstance(data[key], int) or data[key] <= 0:
            raise ValueError(f"{key} must be a positive integer")
    if data["max_candidates"] > 10 or data["max_rounds"] > 10 or data["max_papers"] > 100:
        raise ValueError("Maximum limits: 10 candidates, 10 rounds, 100 papers")
    if not isinstance(data["auto_search"], bool):
        raise ValueError("auto_search must be a boolean")
    if data["search_source"] not in {"arxiv", "openalex"}:
        raise ValueError("search_source must be arxiv or openalex")
    if data["api_max_tokens_field"] not in {"max_completion_tokens", "max_tokens"}:
        raise ValueError("api_max_tokens_field must be max_completion_tokens or max_tokens")
    return data


def load_config(project: Path) -> dict:
    path = project / "research.toml"
    supplied = {}
    if path.exists():
        with path.open("rb") as f:
            supplied = tomllib.load(f)
    return _validated_settings(supplied)


def write_config(project: Path, overrides: dict | None = None) -> None:
    settings = _validated_settings(overrides or {})
    lines = ["# Research Agent CLI configuration. Put credentials in environment variables."]
    for key, value in settings.items():
        literal = str(value).lower() if isinstance(value, bool) else json.dumps(value, ensure_ascii=False)
        lines.append(f"{key} = {literal}")
    (project / "research.toml").write_text("\n".join(lines) + "\n", encoding="utf-8")
