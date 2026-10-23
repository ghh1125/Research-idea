"""Construct interchangeable task execution backends without changing auth."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from research_agent.backend_types import Backend, BackendError
from .api import APIBackend
from .cli import ClaudeBackend, CodexBackend


def make_backend(config: dict[str, Any], workspace: Path) -> Backend:
    name = config.get("backend", "codex")
    if name == "codex":
        return CodexBackend(config, workspace)
    if name == "claude":
        return ClaudeBackend(config, workspace)
    if name == "api":
        return APIBackend(config, workspace)
    raise BackendError(f"Unsupported backend: {name!r}; choose codex, claude, or api")


__all__ = ["make_backend", "CodexBackend", "ClaudeBackend", "APIBackend"]
