"""Explicit, opt-in local experiment execution.

This module executes a user-supplied command specification. It is not a sandbox
and does not infer scientific success from process exit codes or metric values.
The research controller must never call it merely because a model proposed code.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
from pathlib import Path
import signal
import subprocess
import time
from typing import Any
import uuid


MAX_SPEC_BYTES = 1024 * 1024
MAX_METRICS_BYTES = 4 * 1024 * 1024


class ExperimentError(RuntimeError):
    """An invalid experiment specification prevented execution."""


def _digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _relative_file(cwd: Path, name: str, *, required: bool) -> Path:
    if not isinstance(name, str) or not name.strip() or "\x00" in name:
        raise ExperimentError("Artifact paths must be nonempty relative strings.")
    relative = Path(name)
    if relative.is_absolute():
        raise ExperimentError("Artifact paths must be relative to the experiment cwd.")
    try:
        path = (cwd / relative).resolve()
    except (OSError, RuntimeError) as exc:
        raise ExperimentError(f"Artifact path cannot be resolved: {name}") from exc
    if not path.is_relative_to(cwd):
        raise ExperimentError("Artifact paths must remain inside the experiment cwd.")
    if path.exists() and not path.is_file():
        raise ExperimentError(f"Artifact is not a regular file: {name}")
    if required and not path.is_file():
        raise ExperimentError(f"Protected file does not exist: {name}")
    return path


def _reject_nonfinite(value: str) -> None:
    raise ValueError(f"Non-finite JSON number: {value}")


def load_spec(spec_path: Path) -> dict[str, Any]:
    """Validate a JSON spec without starting a process.

    The returned dictionary includes an absolute resolved cwd and the exact
    input-byte hash; it does not contain inherited environment variables.
    """
    spec_path = Path(spec_path).expanduser().resolve()
    try:
        if spec_path.stat().st_size > MAX_SPEC_BYTES:
            raise ExperimentError("Experiment specification exceeds 1 MiB.")
        raw = spec_path.read_bytes()
        spec = json.loads(raw.decode("utf-8"), parse_constant=_reject_nonfinite)
    except (OSError, UnicodeError, ValueError) as exc:
        raise ExperimentError(f"Cannot read experiment specification: {exc}") from exc
    if not isinstance(spec, dict):
        raise ExperimentError("Experiment specification must be a JSON object.")
    allowed = {"argv", "cwd", "timeout_s", "metrics_file", "protected_files"}
    unknown = set(spec) - allowed
    if unknown:
        raise ExperimentError("Unknown experiment fields: " + ", ".join(sorted(unknown)))
    argv = spec.get("argv")
    if not isinstance(argv, list) or not argv or any(
        not isinstance(arg, str) or "\x00" in arg for arg in argv
    ) or not argv[0].strip():
        raise ExperimentError("argv must be a nonempty array of strings with a command.")
    cwd_value = spec.get("cwd")
    if not isinstance(cwd_value, str) or not cwd_value.strip() or "\x00" in cwd_value:
        raise ExperimentError("cwd must be a nonempty path relative to the spec file.")
    if Path(cwd_value).is_absolute():
        raise ExperimentError("cwd must be relative to the spec file, not absolute.")
    cwd = (spec_path.parent / cwd_value).resolve()
    if not cwd.is_dir():
        raise ExperimentError("Experiment cwd does not exist or is not a directory.")
    timeout = spec.get("timeout_s", 600)
    if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or (
        not math.isfinite(timeout) or timeout <= 0 or timeout > 86400
    ):
        raise ExperimentError("timeout_s must be greater than 0 and at most 86400.")
    protected = spec.get("protected_files", [])
    if not isinstance(protected, list) or any(not isinstance(p, str) for p in protected):
        raise ExperimentError("protected_files must be an array of relative file paths.")
    # Validate before any execution or output directory creation.
    for name in protected:
        _relative_file(cwd, name, required=True)
    metrics_name = spec.get("metrics_file")
    if metrics_name is not None:
        _relative_file(cwd, metrics_name, required=False)
    return {
        "argv": argv,
        "cwd": str(cwd),
        "timeout_s": float(timeout),
        "metrics_file": metrics_name,
        "protected_files": list(dict.fromkeys(protected)),
        "spec_sha256": hashlib.sha256(raw).hexdigest(),
        "spec_path": str(spec_path),
    }


def _file_state(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    stat = path.stat()
    return {
        "sha256": _digest(path),
        "size": stat.st_size,
        "mtime_ns": stat.st_mtime_ns,
        "ctime_ns": stat.st_ctime_ns,
        "inode": stat.st_ino,
    }


def _stop_process_group(process: subprocess.Popen[Any]) -> None:
    """Terminate the POSIX session, including children retaining log handles."""
    if os.name == "posix":
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            return
        try:
            process.wait(timeout=1.0)
        except subprocess.TimeoutExpired:
            pass
        # The leader may have exited while a descendant ignored SIGTERM.
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    else:
        process.terminate()
        try:
            process.wait(timeout=1.0)
        except subprocess.TimeoutExpired:
            process.kill()
    process.wait()


def run_experiment(spec_path: Path, output_dir: Path) -> dict[str, Any]:
    """Run an explicitly selected spec and return an auditable execution report.

    Each call creates a unique directory below output_dir. stdout/stderr are
    streamed to files (not retained in memory). Metrics freshness is determined
    by comparing file identity, timestamps and contents before/after this run;
    this is an audit check, not protection against a malicious experiment.
    """
    spec = load_spec(spec_path)
    cwd = Path(spec["cwd"])
    protected_before = {
        name: _digest(_relative_file(cwd, name, required=True))
        for name in spec["protected_files"]
    }
    metrics_name = spec["metrics_file"]
    metrics_before = None
    if metrics_name:
        metrics_path = _relative_file(cwd, metrics_name, required=False)
        if metrics_path.exists() and metrics_path.stat().st_size > MAX_METRICS_BYTES:
            raise ExperimentError("Existing metrics file exceeds 4 MiB.")
        metrics_before = _file_state(metrics_path)
    run_id = "exp-" + time.strftime("%Y%m%dT%H%M%SZ", time.gmtime()) + "-" + uuid.uuid4().hex[:10]
    run_dir = Path(output_dir).expanduser().resolve() / run_id
    run_dir.mkdir(parents=True, exist_ok=False)
    stdout_path = run_dir / "stdout.log"
    stderr_path = run_dir / "stderr.log"
    errors: list[str] = []
    status = "failed"
    returncode: int | None = None
    started = time.monotonic()
    process: subprocess.Popen[Any] | None = None
    try:
        with stdout_path.open("wb") as stdout, stderr_path.open("wb") as stderr:
            try:
                process = subprocess.Popen(
                    spec["argv"],
                    cwd=cwd,
                    stdin=subprocess.DEVNULL,
                    stdout=stdout,
                    stderr=stderr,
                    shell=False,
                    start_new_session=(os.name == "posix"),
                )
                try:
                    returncode = process.wait(timeout=spec["timeout_s"])
                    status = "succeeded" if returncode == 0 else "failed"
                    # This runner is synchronous. Do not leave background
                    # descendants running after their command has completed.
                    if os.name == "posix":
                        _stop_process_group(process)
                except subprocess.TimeoutExpired:
                    status = "timed_out"
                    _stop_process_group(process)
                    returncode = process.returncode
            except OSError as exc:
                errors.append(f"Process launch failed: {exc}")
                stderr.write((errors[-1] + "\n").encode("utf-8"))
    except BaseException:
        if process is not None:
            _stop_process_group(process)
        raise
    duration = time.monotonic() - started
    protected_after: dict[str, str | None] = {}
    for name in spec["protected_files"]:
        try:
            protected_after[name] = _digest(_relative_file(cwd, name, required=True))
        except (OSError, ExperimentError) as exc:
            protected_after[name] = None
            errors.append(f"Protected file cannot be verified: {name}: {exc}")
    changed = [name for name in protected_before if protected_before[name] != protected_after[name]]
    integrity = "changed" if changed else "unchanged" if protected_before else "not_configured"
    metrics: dict[str, Any] = {}
    metrics_valid = False
    metrics_status = "not_configured"
    if metrics_name:
        try:
            metrics_path = _relative_file(cwd, metrics_name, required=False)
            if not metrics_path.is_file():
                metrics_status = "missing"
            elif metrics_path.stat().st_size > MAX_METRICS_BYTES:
                metrics_status = "too_large"
            elif _file_state(metrics_path) == metrics_before:
                metrics_status = "stale"
            else:
                parsed = json.loads(metrics_path.read_text("utf-8"), parse_constant=_reject_nonfinite)
                if not isinstance(parsed, dict):
                    raise ValueError("Metrics JSON must be an object.")
                # Failed execution may leave a partial metrics file; retain its
                # bytes as an artifact, but never treat it as valid run metrics.
                if status != "succeeded":
                    metrics_status = "incomplete_run"
                elif integrity == "changed":
                    metrics_status = "integrity_violation"
                else:
                    encoded = json.dumps(parsed, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
                    (run_dir / "metrics.json").write_text(
                        encoded,
                        encoding="utf-8",
                    )
                    metrics = parsed
                    metrics_valid = True
                    metrics_status = "fresh"
        except (OSError, UnicodeError, ValueError, ExperimentError) as exc:
            metrics_status = "invalid"
            errors.append(f"Metrics unavailable: {exc}")
    report: dict[str, Any] = {
        "id": run_id,
        "execution_status": status,
        "integrity_status": integrity,
        "scientific_status": "unreviewed",
        "returncode": returncode,
        "duration_s": round(duration, 6),
        "metrics": metrics,
        "metrics_valid": metrics_valid,
        "metrics_status": metrics_status,
        "stdout_path": str(stdout_path),
        "stderr_path": str(stderr_path),
        "report_path": str(run_dir / "result.json"),
        "spec_sha256": spec["spec_sha256"],
        "spec_path": spec["spec_path"],
        "cwd": str(cwd),
        "protected_hashes_before": protected_before,
        "protected_hashes_after": protected_after,
        "changed_protected_files": changed,
        "errors": errors,
    }
    (run_dir / "result.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    return report
