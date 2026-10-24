from __future__ import annotations

import base64
import json
import os
import subprocess
import sys
import tempfile
import unittest
import time
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from unittest.mock import MagicMock, patch

from research_idea.backend_types import BackendError, TaskSpec
from research_idea.backends import make_backend
from research_idea.backends.api import APIBackend, endpoint_url
from research_idea.backends.cli import ClaudeBackend, CodexBackend
from research_idea.backends.common import parse_object, run_cli

SCHEMA = {"type": "object", "properties": {"answer": {"type": "string"}},
          "required": ["answer"], "additionalProperties": False}


def task(directory: Path, timeout: float = 3.0) -> TaskSpec:
    return TaskSpec("task-1", "read", "Analyse only this supplied evidence.", SCHEMA,
                    directory, timeout_s=timeout, model="test-model")


def transport(payload: dict):
    return {"kind": "response", "body_base64": base64.b64encode(json.dumps(payload).encode()).decode()}


def openai_response(content: str = '{"answer":"supported"}', finish: str = "stop"):
    return {"model": "returned-model", "choices": [{"finish_reason": finish,
            "message": {"content": content}}], "usage": {"total_tokens": 12}}


class BackendTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_factory_and_unknown_backend(self):
        self.assertIsInstance(make_backend({"backend": "codex"}, self.root), CodexBackend)
        self.assertIsInstance(make_backend({"backend": "claude"}, self.root), ClaudeBackend)
        with self.assertRaises(BackendError):
            make_backend({"backend": "silent-mock"}, self.root)

    def test_json_requires_one_object(self):
        for invalid in ['[]', '```json\n{}\n```', '{"x":1}\n{"x":2}', 'nonsense']:
            with self.subTest(invalid=invalid), self.assertRaises(BackendError):
                parse_object(invalid, "test")

    def test_codex_passes_schema_and_prompt_without_shell(self):
        def execute(argv, prompt, cwd, timeout):
            self.assertEqual(argv[0], "codex")
            self.assertNotIn("--profile", argv)
            if "mcp" in argv:
                return "[]"
            self.assertIn("features.shell_tool=false", argv)
            self.assertIn("features.apps=false", argv)
            self.assertIn('web_search="disabled"', argv)
            self.assertEqual(prompt, task(self.root).prompt)
            self.assertNotEqual(cwd, self.root)
            self.assertEqual(argv[-1], "-")
            self.assertEqual(argv[argv.index("--sandbox") + 1], "read-only")
            self.assertEqual(argv[argv.index("--model") + 1], "test-model")
            schema = Path(argv[argv.index("--output-schema") + 1])
            self.assertEqual(json.loads(schema.read_text()), SCHEMA)
            Path(argv[argv.index("--output-last-message") + 1]).write_text('{"answer":"yes"}')
            return '\n'.join([json.dumps({"type": "thread.started", "thread_id": "thread-1"}),
                              json.dumps({"type": "turn.completed", "usage": {"input_tokens": 9}})])
        with patch("research_idea.backends.cli.run_cli", side_effect=execute):
            result = CodexBackend({}, self.root).generate(task(self.root))
        self.assertEqual(result.output, {"answer": "yes"})
        self.assertEqual(result.session_id, "thread-1")
        self.assertEqual(result.usage["input_tokens"], 9)

    def test_codex_custom_executable_and_profile_apply_to_both_invocations(self):
        selected = "~/Applications/Codex CLI/bin/codex"
        expected = str(Path(selected).expanduser())
        profile = "research profile"
        seen = []
        def execute(argv, prompt, cwd, timeout):
            seen.append(argv)
            self.assertEqual(argv[:3], [expected, "--profile", profile])
            self.assertEqual(argv.count(expected), 1)
            self.assertIn("features.shell_tool=false", argv)
            self.assertNotEqual(cwd, self.root)
            if "mcp" in argv:
                self.assertEqual(prompt, "")
                return "[]"
            Path(argv[argv.index("--output-last-message") + 1]).write_text('{"answer":"selected"}')
            return '{"type":"turn.completed"}'
        with patch.dict(os.environ, {"CODEX_HOME": str(self.root / "saved-auth-home")}), patch("research_idea.backends.cli.run_cli", side_effect=execute):
            result = CodexBackend({"codex_bin": selected, "codex_profile": profile}, self.root).generate(task(self.root))
            self.assertEqual(os.environ["CODEX_HOME"], str(self.root / "saved-auth-home"))
        self.assertEqual(result.output["answer"], "selected")
        self.assertEqual(len(seen), 2)
        self.assertIn("mcp", seen[0])
        self.assertIn("exec", seen[1])

    def test_codex_invalid_executable_fails_before_preflight(self):
        for selected in ["", "   ", None, [], "codex\x00"]:
            with self.subTest(selected=selected), patch("research_idea.backends.cli.run_cli") as execute:
                with self.assertRaisesRegex(BackendError, "codex_bin"):
                    CodexBackend({"codex_bin": selected}, self.root).generate(task(self.root))
                execute.assert_not_called()

    def test_codex_reasoning_override_reaches_preflight_and_execution(self):
        for effort in ["", "medium", "high", "max"]:
            calls = []
            def execute(argv, *args):
                calls.append(argv)
                settings = [arg for arg in argv if arg.startswith("model_reasoning_effort=")]
                self.assertEqual(settings, [f'model_reasoning_effort="{effort}"'] if effort else [])
                if "mcp" in argv:
                    return "[]"
                Path(argv[argv.index("--output-last-message") + 1]).write_text('{"answer":"yes"}')
                return '{"type":"turn.completed"}'
            with self.subTest(effort=effort), patch("research_idea.backends.cli.run_cli", side_effect=execute):
                CodexBackend({"reasoning_effort": effort}, self.root).generate(task(self.root))
            self.assertEqual(len(calls), 2)

    def test_codex_missing_result_is_failure(self):
        with patch("research_idea.backends.cli.run_cli", side_effect=["[]", "{}"]), self.assertRaises(BackendError):
            CodexBackend({}, self.root).generate(task(self.root))

    def test_codex_error_event_rejects_partial_file(self):
        def execute(argv, *args):
            if "mcp" in argv:
                return "[]"
            Path(argv[argv.index("--output-last-message") + 1]).write_text('{"answer":"partial"}')
            return '{"type":"turn.failed"}'
        with patch("research_idea.backends.cli.run_cli", side_effect=execute), self.assertRaises(BackendError):
            CodexBackend({}, self.root).generate(task(self.root))

    def test_codex_recovered_stream_error_accepts_completed_turn(self):
        def execute(argv, *args):
            if "mcp" in argv:
                return "[]"
            Path(argv[argv.index("--output-last-message") + 1]).write_text('{"answer":"recovered"}')
            return '\n'.join([
                json.dumps({"type": "error", "message": "Reconnecting... 2/5 (stream disconnected)"}),
                json.dumps({"type": "turn.completed", "usage": {"output_tokens": 8}}),
            ])
        with patch("research_idea.backends.cli.run_cli", side_effect=execute):
            result = CodexBackend({}, self.root).generate(task(self.root))
        self.assertEqual(result.output, {"answer": "recovered"})
        self.assertEqual(result.usage["output_tokens"], 8)

    def test_codex_result_requires_successful_terminal_event(self):
        streams = ["", '{"type":"error","message":"disconnected"}',
                   '{"type":"turn.completed"}\n{"type":"error"}',
                   '{"type":"turn.failed"}\n{"type":"turn.completed"}']
        for stream in streams:
            with self.subTest(stream=stream):
                def execute(argv, *args):
                    if "mcp" in argv:
                        return "[]"
                    Path(argv[argv.index("--output-last-message") + 1]).write_text('{"answer":"partial"}')
                    return stream
                with patch("research_idea.backends.cli.run_cli", side_effect=execute), self.assertRaises(BackendError):
                    CodexBackend({}, self.root).generate(task(self.root))

    def test_codex_enabled_mcp_stops_before_task_is_sent(self):
        for inventory in [[{"name": "external", "enabled": True}], [{"name": "unknown"}]]:
            with self.subTest(inventory=inventory), patch("research_idea.backends.cli.run_cli", return_value=json.dumps(inventory)) as call:
                with self.assertRaisesRegex(BackendError, "MCP servers enabled"):
                    CodexBackend({}, self.root).generate(task(self.root))
                self.assertEqual(call.call_count, 1)
                self.assertEqual(call.call_args.args[1], "")
                self.assertIn("mcp", call.call_args.args[0])

    def test_claude_structured_envelope_and_disabled_tools(self):
        envelope = {"subtype": "success", "is_error": False,
                    "structured_output": {"answer": "yes"}, "session_id": "s1",
                    "usage": {"input_tokens": 20}, "total_cost_usd": 0.02}
        with patch("research_idea.backends.cli.run_cli", return_value=json.dumps(envelope)) as call:
            result = ClaudeBackend({}, self.root).generate(task(self.root))
        argv = call.call_args.args[0]
        self.assertIn("--safe-mode", argv)
        self.assertEqual(argv[argv.index("--tools") + 1], "")
        self.assertEqual(argv[argv.index("--disallowedTools") + 1], "mcp__*")
        self.assertEqual(result.output, {"answer": "yes"})
        self.assertEqual(result.usage["estimated_cost_usd"], 0.02)

    def test_claude_refusal_and_missing_structured_output(self):
        for envelope in [{"is_error": True}, {"result": '{"answer":"maybe"}'},
                         {"subtype": "error_max_turns", "structured_output": {"answer": "partial"}}]:
            with self.subTest(envelope=envelope), patch("research_idea.backends.cli.run_cli", return_value=json.dumps(envelope)), self.assertRaises(BackendError):
                ClaudeBackend({}, self.root).generate(task(self.root))

    def test_missing_cli_is_actionable(self):
        with self.assertRaisesRegex(BackendError, "not installed"):
            run_cli([str(self.root / "no-such-command")], "", self.root, 1)

    def test_cli_timeout_reaps_process(self):
        with self.assertRaisesRegex(BackendError, "timeout"):
            run_cli([sys.executable, "-c", "import time; time.sleep(30)"], "", self.root, 0.05)

    def test_cli_does_not_echo_sensitive_stderr(self):
        with self.assertRaises(BackendError) as caught:
            run_cli([sys.executable, "-c", "import sys;sys.stderr.write('SECRET_TOKEN');sys.exit(2)"], "", self.root, 2)
        self.assertNotIn("SECRET_TOKEN", str(caught.exception))

    def api(self, **extra):
        return APIBackend({"base_url": "http://127.0.0.1:9999/v1", "api_key_env": "", **extra}, self.root)

    def test_endpoint_normalization_and_transport_policy(self):
        self.assertEqual(endpoint_url("https://api.example.org", "openai-compatible"),
                         "https://api.example.org/v1/chat/completions")
        self.assertEqual(endpoint_url("https://api.example.org/v1/messages", "anthropic"),
                         "https://api.example.org/v1/messages")
        for url in ["http://example.org/v1", "https://user:pass@example.org", "https://example.org?key=secret",
                    "https://example.org/#fragment", "file:///etc/passwd", "https://", "http://localhost.evil.test"]:
            with self.subTest(url=url), self.assertRaises(BackendError):
                endpoint_url(url, "openai-compatible")

    def test_openai_request_schema_and_usage(self):
        with patch("research_idea.backends.api._request_once", return_value=transport(openai_response())) as request:
            result = self.api().generate(task(self.root))
        payload = request.call_args.args[1]
        self.assertEqual(payload["response_format"]["json_schema"]["schema"], SCHEMA)
        self.assertTrue(payload["response_format"]["json_schema"]["strict"])
        self.assertEqual(payload["model"], "test-model")
        self.assertIn("max_completion_tokens", payload)
        self.assertEqual(result.output, {"answer": "supported"})
        self.assertEqual(result.usage["total_tokens"], 12)
        self.assertEqual(result.usage["transport_attempts"], 1)

    def test_anthropic_request_and_parse(self):
        value = {"stop_reason": "end_turn", "content": [{"type": "text", "text": '{"answer":"yes"}'}],
                 "usage": {"output_tokens": 7}}
        with patch("research_idea.backends.api._request_once", return_value=transport(value)) as request:
            result = self.api(api_provider="anthropic").generate(task(self.root))
        url, payload, headers, _ = request.call_args.args
        self.assertEqual(payload["output_config"]["format"]["schema"], SCHEMA)
        self.assertEqual(headers["anthropic-version"], "2023-06-01")
        self.assertTrue(url.endswith("/messages"))
        self.assertEqual(result.output["answer"], "yes")

    def test_api_refused_or_truncated_not_accepted(self):
        for value in [openai_response(finish="length"), openai_response(content="[]"),
                      {"choices": []}, {"choices": ["wrong"]}]:
            with self.subTest(value=value), patch("research_idea.backends.api._request_once", return_value=transport(value)):
                with self.assertRaises(BackendError) as caught:
                    self.api().generate(task(self.root))
                self.assertEqual(caught.exception.transport_attempts, 1)

    def test_anthropic_malformed_content_is_actionable(self):
        for content in [[], [{"type": "text", "text": None}], [{"type": "tool_use"}]]:
            value = {"stop_reason": "end_turn", "content": content}
            with self.subTest(content=content), patch("research_idea.backends.api._request_once", return_value=transport(value)):
                with self.assertRaisesRegex(BackendError, "text content"):
                    self.api(api_provider="anthropic").generate(task(self.root))

    def test_unsupported_schema_does_not_silently_degrade(self):
        with patch("research_idea.backends.api._request_once", return_value={"kind": "http_error", "status": 400}) as request:
            with self.assertRaisesRegex(BackendError, "no fallback") as caught:
                self.api().generate(task(self.root))
        self.assertEqual(caught.exception.transport_attempts, 1)
        self.assertEqual(request.call_count, 1)

    def test_adapter_makes_one_attempt_so_shared_retries_do_not_multiply(self):
        from research_idea.backend_errors import ProviderError
        for status in (429, 503):
            with self.subTest(status=status), patch('research_idea.backends.api._request_once',
                    return_value={'kind': 'http_error', 'status': status}) as request:
                with self.assertRaises(ProviderError) as caught:
                    self.api().generate(task(self.root))
                self.assertEqual(caught.exception.transport_attempts, 1)
                self.assertEqual(request.call_count, 1)

    def test_no_api_key_or_model_fails_before_network(self):
        backend = APIBackend({"base_url": "https://example.org/v1", "api_key_env": "RESEARCH_TEST_UNSET"}, self.root)
        with patch.dict(os.environ, {}, clear=True), self.assertRaisesRegex(BackendError, "RESEARCH_TEST_UNSET") as caught:
            backend.generate(task(self.root))
        self.assertEqual(caught.exception.transport_attempts, 0)
        no_model = TaskSpec("x", "read", "text", SCHEMA, self.root)
        with self.assertRaisesRegex(BackendError, "explicit model"):
            self.api().generate(no_model)

    def test_api_redirect_is_rejected(self):
        with patch("research_idea.backends.api._request_once", return_value={"kind": "http_error", "status": 307}) as request:
            with self.assertRaisesRegex(BackendError, "HTTP 307"):
                self.api().generate(task(self.root))
        self.assertEqual(request.call_count, 1)

    def test_error_body_identifies_cause_without_exposing_provider_text(self):
        from research_idea.backend_errors import ProviderError
        for status, code, expected in [(429, 'insufficient_quota', 'quota'),
                (429, 'rate_limit_exceeded', 'rate_limit'), (404, 'model_not_found', 'model'),
                (401, 'invalid_api_key', 'auth')]:
            body = json.dumps({'error': {'code': code, 'message': 'SECRET_TOKEN account@example.org'}})
            failure = {'kind': 'http_error', 'status': status,
                       'body_base64': base64.b64encode(body.encode()).decode()}
            with self.subTest(code=code), patch('research_idea.backends.api._request_once', return_value=failure):
                with self.assertRaises(ProviderError) as caught:
                    self.api().generate(task(self.root))
                self.assertEqual(caught.exception.category, expected)
                self.assertNotIn('SECRET_TOKEN', str(caught.exception))
                self.assertNotIn('account@example.org', str(caught.exception))

    def test_codex_error_event_is_classified_even_without_a_result_file(self):
        from research_idea.backend_errors import ProviderError
        with patch('research_idea.backends.cli.run_cli', side_effect=[
                '[]', '{"type":"turn.failed","error":{"message":"model_not_found SECRET_TOKEN"}}']):
            with self.assertRaises(ProviderError) as caught:
                CodexBackend({}, self.root).generate(task(self.root))
        self.assertEqual(caught.exception.category, 'model')
        self.assertNotIn('SECRET_TOKEN', str(caught.exception))

    def test_cli_failure_classifies_stderr_without_echoing_it(self):
        from research_idea.backend_errors import ProviderError
        with self.assertRaises(ProviderError) as caught:
            run_cli([sys.executable, '-c', "import sys;sys.stderr.write('insufficient_quota SECRET_TOKEN');sys.exit(1)"], '', self.root, 2)
        self.assertEqual(caught.exception.category, 'quota')
        self.assertNotIn('SECRET_TOKEN', str(caught.exception))

    def test_total_deadline_cancels_slow_drip_body(self):
        body_started = threading.Event()
        disconnected = threading.Event()
        stop_streaming = threading.Event()
        class SlowHandler(BaseHTTPRequestHandler):
            def do_POST(handler):
                handler.rfile.read(int(handler.headers["Content-Length"]))
                handler.send_response(200)
                handler.send_header("Content-Length", "100000000")
                handler.end_headers()
                try:
                    while not stop_streaming.is_set():
                        handler.wfile.write(b" " * 1024)
                        handler.wfile.flush()
                        body_started.set()
                        stop_streaming.wait(0.04)
                except (BrokenPipeError, ConnectionResetError):
                    disconnected.set()
            def log_message(self, *args):
                pass
        server = HTTPServer(("127.0.0.1", 0), SlowHandler)
        thread = threading.Thread(target=server.serve_forever)
        thread.start()
        try:
            backend = self.api(base_url=f"http://127.0.0.1:{server.server_port}/v1")
            started = time.monotonic()
            with self.assertRaisesRegex(BackendError, "total timeout") as caught:
                # Include ample interpreter-startup time under suite/CI load.
                # A 40 ms drip never hits urllib's 3 s socket inactivity timeout,
                # so only the outer total deadline can cancel this body read.
                backend.generate(task(self.root, timeout=3.0))
            self.assertLess(time.monotonic() - started, 5.0)
            self.assertEqual(caught.exception.transport_attempts, 1)
            self.assertTrue(body_started.is_set(),
                            "HTTP worker timed out before response streaming began; "
                            "the test did not exercise cancellation during a body read")
            self.assertTrue(disconnected.wait(2), "HTTP worker must close its connection on timeout")
        finally:
            stop_streaming.set()
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)

    def test_real_http_worker_preserves_response_envelope(self):
        observed = []
        class Handler(BaseHTTPRequestHandler):
            def do_POST(handler):
                observed.append(json.loads(handler.rfile.read(int(handler.headers["Content-Length"]))))
                payload = json.dumps(openai_response()).encode()
                handler.send_response(200)
                handler.send_header("Content-Length", str(len(payload)))
                handler.end_headers()
                handler.wfile.write(payload)
            def log_message(self, *args):
                pass
        server = HTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever)
        thread.start()
        try:
            result = self.api(base_url=f"http://127.0.0.1:{server.server_port}/v1").generate(task(self.root))
            self.assertEqual(result.output, {"answer": "supported"})
            self.assertEqual(observed[0]["model"], "test-model")
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)


if __name__ == "__main__":
    unittest.main()
