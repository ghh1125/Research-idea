"""Shared execution boundary. Research state belongs to the controller."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol


class BackendError(RuntimeError):
    """An execution backend could not produce a usable response."""


@dataclass(frozen=True)
class TaskSpec:
    task_id: str
    stage: str
    prompt: str
    output_schema: dict[str, Any]
    workspace: Path
    timeout_s: float = 180.0
    model: str | None = None


@dataclass
class BackendResult:
    output: dict[str, Any]
    usage: dict[str, Any] = field(default_factory=dict)
    session_id: str | None = None
    raw: str = ""


class Backend(Protocol):
    name: str

    def generate(self, task: TaskSpec) -> BackendResult: ...
