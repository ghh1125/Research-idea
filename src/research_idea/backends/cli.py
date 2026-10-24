"""Non-interactive Codex and Claude Code execution adapters.

Only task-local material is supplied. The research controller owns retrieval,
state transitions, and evidence reading. CLI installations/authentication
are deliberately not modified by this package.
"""
from __future__ import annotations

import json
import tempfile
import time
from pathlib import Path
from typing import Any

from research_idea.backend_types import BackendError, BackendResult, TaskSpec
from research_idea.backend_errors import ProviderError, classify_provider_error
from research_idea.config import REASONING_EFFORTS
from .common import MAX_RESPONSE_BYTES, parse_object, positive_timeout, run_cli


def _codex_inference_options() -> list[str]:
    """Documented per-invocation overrides; do not rewrite user config/auth.

    Read-only sandbox alone does not constrain hosted/MCP tools. Disable the
    documented execution, app, search, delegation and plugin capabilities, and
    separately inspect external MCP configuration before passing task content.
    """
    settings = [
        "features.shell_tool=false", "features.shell_snapshot=false",
        "features.apps=false", "features.multi_agent=false", "features.hooks=false",
        "features.memories=false", "features.plugins=false", 'web_search="disabled"',
        "tools.view_image=false", "project_doc_max_bytes=0",
    ]
    return [arg for setting in settings for arg in ("--config", setting)]


def _codex_command(config: dict[str, Any]) -> list[str]:
    """Select one executable and optional saved profile without touching auth."""
    binary = config.get("codex_bin", "codex")
    profile = config.get("codex_profile", "")
    if not isinstance(binary, str) or not binary.strip() or "\x00" in binary:
        raise BackendError("codex_bin must be a nonempty executable name or path")
    if not isinstance(profile, str) or "\x00" in profile:
        raise BackendError("codex_profile must be a profile name or an empty string")
    try:
        executable = Path(binary).expanduser()
    except RuntimeError as exc:
        raise BackendError("Could not expand the home directory in codex_bin") from exc
    # Relative paths are relative to the caller, not the isolated task cwd.
    # Bare executable names remain bare so subprocess can use the user's PATH.
    if not executable.is_absolute() and ("/" in binary or "\\" in binary):
        executable = executable.resolve()
    command = [str(executable)]
    if profile:
        command += ["--profile", profile]
    effort = config.get("reasoning_effort", "")
    if effort not in ("", *REASONING_EFFORTS):
        raise BackendError("Unsupported reasoning_effort")
    if effort:
        command += ["--config", "model_reasoning_effort=" + json.dumps(effort)]
    return command


def _check_codex_mcp(command: list[str], options: list[str], cwd: Path, timeout_s: float) -> None:
    """Fail closed if external MCP tools remain, without reading credentials.

    Do not use mcp_servers={} as a clear operation: TOML configuration layers
    may merge the table and leave inherited servers active.
    """
    raw = run_cli([*command, *options, "mcp", "list", "--json"], "", cwd, timeout_s)
    try:
        servers = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise BackendError("Could not verify Codex MCP isolation from its JSON inventory") from exc
    if not isinstance(servers, list) or any(not isinstance(server, dict) for server in servers):
        raise BackendError("Codex returned an unsupported MCP inventory format")
    if any(server.get("enabled") is not False for server in servers):
        raise BackendError(
            "Codex has external MCP servers enabled. Choose a Codex profile or configuration "
            "with external MCP servers disabled; existing settings and credentials were not changed"
        )


class CodexBackend:
    name = "codex"

    def __init__(self, config: dict[str, Any], workspace: Path):
        self.config = config
        self.workspace = workspace

    def generate(self, task: TaskSpec) -> BackendResult:
        command = _codex_command(self.config)
        # Use an OS temporary directory, not the user's project: do not inherit
        # project-local AGENTS.md or accidentally treat a paper as instructions.
        with tempfile.TemporaryDirectory(prefix="research-codex-") as directory:
            deadline = time.monotonic() + positive_timeout(task.timeout_s)
            cwd = Path(directory)
            schema = cwd / "schema.json"
            output = cwd / "result.json"
            schema.write_text(json.dumps(task.output_schema, ensure_ascii=False), encoding="utf-8")
            options = _codex_inference_options()
            _check_codex_mcp(command, options, cwd, max(0.001, deadline - time.monotonic()))
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise BackendError("Codex task timed out during configuration preflight")
            argv = [
                *command, *options, "--ask-for-approval", "never", "exec",
                "--skip-git-repo-check", "--sandbox", "read-only", "--json",
                "--output-schema", str(schema), "--output-last-message", str(output),
            ]
            model = task.model or self.config.get("model")
            if model:
                argv += ["--model", str(model)]
            argv.append("-")
            raw = run_cli(argv, task.prompt, cwd, remaining)
            usage: dict[str, Any] = {}
            session_id = None
            completed = False
            pending_error = False
            last_error = ''
            for line in raw.splitlines():
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if not isinstance(event, dict):
                    continue
                if event.get("type") == "turn.failed":
                    raise ProviderError(classify_provider_error(event.get('error') or last_error))
                if event.get("type") == "error":
                    # Codex also emits error events while reconnecting a stream.
                    # A later successful terminal event confirms recovery.
                    pending_error = True
                    last_error = event.get('message') or event.get('error') or ''
                if event.get("type") == "thread.started":
                    session_id = event.get("thread_id")
                if event.get("type") == "turn.completed":
                    completed = True
                    pending_error = False
                    if isinstance(event.get("usage"), dict):
                        usage.update(event["usage"])
            if not completed or pending_error:
                raise ProviderError(classify_provider_error(last_error))
            if not output.is_file():
                raise BackendError("Codex did not produce its structured result file")
            if output.stat().st_size > MAX_RESPONSE_BYTES:
                raise BackendError("Codex structured result exceeded the size limit")
            try:
                result = parse_object(output.read_text(encoding="utf-8"), "Codex")
            except (OSError, UnicodeDecodeError) as exc:
                raise BackendError("Could not read Codex structured result") from exc
            return BackendResult(result, usage, session_id, raw)


class ClaudeBackend:
    name = "claude"

    def __init__(self, config: dict[str, Any], workspace: Path):
        self.config = config
        self.workspace = workspace

    def generate(self, task: TaskSpec) -> BackendResult:
        with tempfile.TemporaryDirectory(prefix="research-claude-") as directory:
            cwd = Path(directory)
            # Safe mode preserves the user's existing auth, unlike --bare.
            # Built-in and MCP tools are both disabled for bounded inference.
            argv = [
                "claude", "--safe-mode", "-p", "--output-format", "json",
                "--json-schema", json.dumps(task.output_schema, ensure_ascii=False),
                "--tools", "", "--disallowedTools", "mcp__*",
                "--strict-mcp-config", "--mcp-config", '{"mcpServers":{}}',
                "--setting-sources", "",
            ]
            model = task.model or self.config.get("model")
            if model:
                argv += ["--model", str(model)]
            raw = run_cli(argv, task.prompt, cwd, task.timeout_s)
            envelope = parse_object(raw, "Claude Code")
            if envelope.get("is_error") or envelope.get("subtype", "success") != "success":
                raise ProviderError(classify_provider_error({key: envelope.get(key) for key in ('error', 'errors', 'result')}))
            result = envelope.get("structured_output")
            if not isinstance(result, dict):
                raise BackendError("Claude Code response is missing structured_output")
            usage = envelope.get("usage") if isinstance(envelope.get("usage"), dict) else {}
            usage = dict(usage)
            if isinstance(envelope.get("total_cost_usd"), (int, float)):
                usage["estimated_cost_usd"] = envelope["total_cost_usd"]
            return BackendResult(result, usage, envelope.get("session_id"), raw)
