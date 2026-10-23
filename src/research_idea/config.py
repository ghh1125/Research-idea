"""Project-local settings. Credentials are environment variable names, never values."""
from __future__ import annotations

import json
from pathlib import Path
import tomllib

DEFAULTS = {
    "backend": "codex", "model": "", "api_provider": "openai-compatible",
    "base_url": "https://api.openai.com/v1", "api_key_env": "OPENAI_API_KEY",
    "timeout_s": 180, "max_calls": 80, "max_seconds": 3600,
    "max_output_tokens": 8192, "api_max_tokens_field": "max_completion_tokens",
    "codex_bin": "codex", "codex_profile": "",
    "skill_paths": [], "skill_roots": [], "skill_max_chars": 48000, "builtin_skills": True,
    "max_candidates": 3, "max_rounds": 2, "max_papers": 12,
    "source_chars": 24000, "search_source": "arxiv", "auto_search": True,
    "deep_reading": True, "max_paper_read_chunks": 3, "max_followup_reads": 2,
    "search_venues": [], "fetch_full_text": True,
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
    data = {key: list(value) if isinstance(value, list) else value for key, value in DEFAULTS.items()}
    data.update(supplied)
    for key in ("backend", "model", "api_provider", "base_url", "api_key_env",
                "api_max_tokens_field", "search_source", "search_api_key_env", "constraints",
                "codex_bin", "codex_profile"):
        if not isinstance(data[key], str):
            raise ValueError(f"{key} must be a string")
    if not data["codex_bin"].strip() or "\x00" in data["codex_bin"]:
        raise ValueError("codex_bin must be a nonempty executable name or path")
    if "\x00" in data["codex_profile"]:
        raise ValueError("codex_profile must not contain a null character")
    for key in ("skill_paths", "skill_roots"):
        if not isinstance(data[key], list) or any(
            not isinstance(value, str) or not value.strip() or "\x00" in value for value in data[key]
        ):
            raise ValueError(f"{key} must be a list of nonempty paths")
    if not isinstance(data["search_venues"], list) or any(
        not isinstance(value, str) or not value.strip() or "\x00" in value for value in data["search_venues"]
    ):
        raise ValueError("search_venues must be a list of nonempty venue names")
    if data["api_provider"] not in PROVIDER_DEFAULTS:
        raise ValueError("api_provider must be openai-compatible or anthropic")
    for key, value in PROVIDER_DEFAULTS[data["api_provider"]].items():
        if key not in supplied:
            data[key] = value
    if data["backend"] not in {"codex", "claude", "api", "demo"}:
        raise ValueError("backend must be codex, claude, api, or demo")
    for key in ("timeout_s", "max_calls", "max_seconds", "max_candidates", "max_rounds",
                "max_papers", "source_chars", "max_output_tokens", "skill_max_chars", "max_paper_read_chunks"):
        if isinstance(data[key], bool) or not isinstance(data[key], int) or data[key] <= 0:
            raise ValueError(f"{key} must be a positive integer")
    if data["max_candidates"] > 10 or data["max_rounds"] > 10 or data["max_papers"] > 100:
        raise ValueError("Maximum limits: 10 candidates, 10 rounds, 100 papers")
    if type(data["max_followup_reads"]) is not int or not 0 <= data["max_followup_reads"] <= 10:
        raise ValueError("max_followup_reads must be an integer from 0 to 10")
    if data["max_paper_read_chunks"] > 50:
        raise ValueError("max_paper_read_chunks must not exceed 50")
    for key in ("auto_search", "builtin_skills", "fetch_full_text", "deep_reading"):
        if not isinstance(data[key], bool):
            raise ValueError(f"{key} must be a boolean")
    if data["deep_reading"] and data["source_chars"] < 256:
        raise ValueError("deep_reading requires source_chars >= 256")
    if data["search_source"] not in {"arxiv", "openalex"}:
        raise ValueError("search_source must be arxiv or openalex")
    if data["search_venues"]:
        if "search_source" in supplied and data["search_source"] == "arxiv":
            raise ValueError("Venue filtering requires search_source='openalex'; arxiv does not verify conference venues")
        data["search_source"] = "openalex"
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
    lines = ["# Research-idea configuration. Put credentials in environment variables."]
    for key, value in settings.items():
        literal = str(value).lower() if isinstance(value, bool) else json.dumps(value, ensure_ascii=False)
        lines.append(f"{key} = {literal}")
    (project / "research.toml").write_text("\n".join(lines) + "\n", encoding="utf-8")
