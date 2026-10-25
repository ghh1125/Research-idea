"""Parsing and transport helpers shared by execution adapters."""
from __future__ import annotations

import json
import logging
import math
import os
import shutil
import signal
import subprocess
import tempfile
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from research_idea.backend_types import BackendError
from research_idea.backend_errors import ProviderError, classify_provider_error

MAX_RESPONSE_BYTES = 16 * 1024 * 1024
_LOG = logging.getLogger(__name__)


@contextmanager
def cli_workspace(prefix: str):
    """Keep a Windows cleanup lock from replacing a model result or error.

    CLI descendants and file scanners may release handles after the launcher
    exits. Retry only Windows access/sharing locks, within a short fixed budget.
    A persistent lock leaves this one temporary directory for OS/user cleanup;
    it must not trigger another paid model call or mask the original failure.
    """
    directory = tempfile.mkdtemp(prefix=prefix)
    try:
        yield directory
    finally:
        for delay in (0, 0.1, 0.2, 0.4, 0.8):
            if delay:
                time.sleep(delay)
            try:
                shutil.rmtree(directory)
                break
            except FileNotFoundError:
                break
            except OSError as exc:
                if getattr(exc, 'winerror', None) not in {5, 32, 33}:
                    raise
        else:
            _LOG.warning('[cleanup] 临时目录仍被占用，已保留：%s；本次模型结果或原始错误保持不变。', directory)


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
    """Stop a timed-out CLI tree, including Windows launcher descendants."""
    if os.name == 'nt':
        try:
            subprocess.run(['taskkill', '/PID', str(process.pid), '/T', '/F'],
                           stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL, timeout=5, check=False)
        except (OSError, subprocess.TimeoutExpired):
            pass  # Still reap/terminate the direct child below.
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
            raise ProviderError('timeout', diagnostic=f"exceeded the {timeout_s:g}s task timeout") from exc
        except BaseException:
            _terminate_process_group(process)
            raise
        if process.returncode != 0:
            # Read only a bounded tail for classification. No raw stream enters
            # exception messages, terminal events or persisted research state.
            parts = []
            for stream in (stderr, stdout):
                stream.seek(0, 2)
                stream.seek(max(0, stream.tell() - 65536))
                parts.append(stream.read(65536).decode('utf-8', errors='replace'))
            raise ProviderError(classify_provider_error('\n'.join(parts)),
                                diagnostic=f'CLI exited with code {process.returncode}.')
        stdout.seek(0)
        raw = stdout.read(MAX_RESPONSE_BYTES + 1)
        if len(raw) > MAX_RESPONSE_BYTES:
            raise BackendError(f"{argv[0]} output exceeded the response size limit")
        try:
            return raw.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise BackendError(f"{argv[0]} returned non-UTF-8 output") from exc
