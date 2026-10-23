"""Parsing and transport helpers shared by execution adapters."""
from __future__ import annotations

import json
import math
import os
import signal
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any

from research_idea.backend_types import BackendError

MAX_RESPONSE_BYTES = 16 * 1024 * 1024


def parse_object(value: str, source: str) -> dict[str, Any]:
    """Require one JSON object. Do not silently extract JSON from prose."""
    try:
        result = json.loads(value)
    except (json.JSONDecodeError, TypeError) as exc:
        raise BackendError(f"{source} returned invalid JSON; no research result was accepted") from exc
    if not isinstance(result, dict):
        raise BackendError(f"{source} must return a JSON object")
    return result


def positive_timeout(value: Any) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise BackendError("timeout_s must be a positive finite number") from exc
    if not math.isfinite(result) or result <= 0:
        raise BackendError("timeout_s must be a positive finite number")
    return result


def _terminate_process_group(process: subprocess.Popen) -> None:
    """Stop a timed-out CLI and its children on POSIX, then reap the process."""
    try:
        if os.name == "posix":
            os.killpg(process.pid, signal.SIGTERM)
        else:
            process.terminate()
    except ProcessLookupError:
        pass
    try:
        process.communicate(timeout=2)
    except subprocess.TimeoutExpired:
        try:
            if os.name == "posix":
                os.killpg(process.pid, signal.SIGKILL)
            else:
                process.kill()
        except ProcessLookupError:
            pass
        process.communicate()


def run_cli(argv: list[str], prompt: str, cwd: Path, timeout_s: float) -> str:
    """No shell; input over stdin; output spooled to disk with a read limit."""
    timeout_s = positive_timeout(timeout_s)
    deadline = time.monotonic() + timeout_s
    with tempfile.TemporaryFile(mode="w+b") as stdout, tempfile.TemporaryFile(mode="w+b") as stderr:
        try:
            process = subprocess.Popen(
                argv, cwd=cwd, stdin=subprocess.PIPE, stdout=stdout, stderr=stderr,
                start_new_session=(os.name == "posix"),
            )
        except FileNotFoundError as exc:
            raise BackendError(f"{argv[0]} is not installed or is not on PATH") from exc
        except OSError as exc:
            raise BackendError(f"Could not start {argv[0]}") from exc
        try:
            process.communicate(input=prompt.encode("utf-8"), timeout=max(0.0, deadline - time.monotonic()))
        except subprocess.TimeoutExpired as exc:
            _terminate_process_group(process)
            raise BackendError(f"{argv[0]} exceeded the {timeout_s:g}s task timeout") from exc
        except BaseException:
            _terminate_process_group(process)
            raise
        if process.returncode != 0:
            # CLI stderr may contain credentials or full prompts. Keep it out of
            # project logs and user-facing exception messages.
            raise BackendError(
                f"{argv[0]} exited with code {process.returncode}; check its installation, "
                "authentication, selected model, and supported CLI options directly"
            )
        stdout.seek(0)
        raw = stdout.read(MAX_RESPONSE_BYTES + 1)
        if len(raw) > MAX_RESPONSE_BYTES:
            raise BackendError(f"{argv[0]} output exceeded the response size limit")
        try:
            return raw.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise BackendError(f"{argv[0]} returned non-UTF-8 output") from exc
