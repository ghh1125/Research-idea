"""CLI results must survive Windows temporary-directory sharing locks."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from research_idea.backend_types import BackendError, TaskSpec
from research_idea.backends.cli import CodexBackend, ClaudeBackend
from research_idea.backends.common import cli_workspace, run_cli


def sharing_error(code=32):
    error = PermissionError('Directory in use')
    error.winerror = code
    return error


class WorkspaceTests(unittest.TestCase):
    def test_transient_windows_lock_is_retried_and_removed(self):
        original = shutil.rmtree
        attempts = []
        def remove(path):
            attempts.append(path)
            if len(attempts) < 3:
                raise sharing_error()
            original(path)
        with patch('research_idea.backends.common.shutil.rmtree', side_effect=remove), \
             patch('research_idea.backends.common.time.sleep') as sleep:
            with cli_workspace('research-test-') as directory:
                Path(directory, 'result.json').write_text('{}')
        self.assertFalse(Path(directory).exists())
        self.assertEqual(len(attempts), 3)
        self.assertEqual(sleep.call_count, 2)

    def test_persistent_lock_preserves_success_without_rerunning_model(self):
        for backend_class in (CodexBackend, ClaudeBackend):
            directories = []
            calls = []
            def execute(argv, prompt, cwd, timeout):
                directories.append(cwd)
                calls.append(argv)
                if 'mcp' in argv:
                    return '[]'
                if backend_class is CodexBackend:
                    Path(argv[argv.index('--output-last-message') + 1]).write_text('{"answer":"ok"}')
                    return '{"type":"turn.completed"}'
                return json.dumps({'structured_output': {'answer': 'ok'}, 'subtype': 'success'})
            try:
                with self.subTest(backend=backend_class.name), \
                     patch('research_idea.backends.cli.run_cli', side_effect=execute), \
                     patch('research_idea.backends.common.shutil.rmtree', side_effect=sharing_error()), \
                     patch('research_idea.backends.common.time.sleep'), \
                     self.assertLogs('research_idea.backends.common', level='WARNING') as logs:
                    task = TaskSpec('test', 'read', 'prompt', {'type': 'object'}, Path.cwd(), timeout_s=3)
                    result = backend_class({}, Path.cwd()).generate(task)
                self.assertEqual(result.output, {'answer': 'ok'})
                self.assertEqual(len(calls), 2 if backend_class is CodexBackend else 1)
                self.assertIn('[cleanup]', logs.output[0])
            finally:
                for directory in set(directories):
                    shutil.rmtree(directory)

    def test_lock_does_not_replace_original_backend_error(self):
        for error in (BackendError('model failed'), KeyboardInterrupt()):
            directory = None
            try:
                with self.subTest(error=type(error).__name__), \
                     patch('research_idea.backends.common.shutil.rmtree', side_effect=sharing_error(5)), \
                     patch('research_idea.backends.common.time.sleep'), \
                     self.assertLogs('research_idea.backends.common', level='WARNING'), \
                     self.assertRaises(type(error)) as caught:
                    with cli_workspace('research-test-') as directory:
                        raise error
                self.assertIs(caught.exception, error)
            finally:
                if directory:
                    shutil.rmtree(directory)

    def test_unrelated_cleanup_error_is_not_silently_discarded(self):
        directory = None
        try:
            with patch('research_idea.backends.common.shutil.rmtree', side_effect=OSError('disk failure')), \
                 self.assertRaisesRegex(OSError, 'disk failure'):
                with cli_workspace('research-test-') as directory:
                    pass
        finally:
            if directory:
                shutil.rmtree(directory)

    @unittest.skipUnless(os.name == 'nt', 'Requires real Windows directory sharing semantics')
    def test_real_child_cwd_lock_does_not_discard_completed_codex_result(self):
        child = None
        directory = None
        def execute(argv, prompt, cwd, timeout):
            nonlocal child, directory
            if 'mcp' in argv:
                return '[]'
            directory = cwd
            child = subprocess.Popen([sys.executable, '-c',
                "import sys,time; print('ready',flush=True); time.sleep(30)"],
                cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
            self.assertEqual(child.stdout.readline().strip(), b'ready')
            Path(argv[argv.index('--output-last-message') + 1]).write_text('{"answer":"ok"}')
            return '{"type":"turn.completed"}'
        try:
            with patch('research_idea.backends.cli.run_cli', side_effect=execute), \
                 self.assertLogs('research_idea.backends.common', level='WARNING'):
                result = CodexBackend({}, Path.cwd()).generate(
                    TaskSpec('test', 'read', 'prompt', {'type': 'object'}, Path.cwd(), timeout_s=5))
            self.assertEqual(result.output, {'answer': 'ok'})
            self.assertTrue(directory.exists())
        finally:
            if child:
                child.kill()
                child.communicate(timeout=5)
            if directory and directory.exists():
                shutil.rmtree(directory)

    @unittest.skipUnless(os.name == 'nt', 'Requires Windows taskkill process-tree semantics')
    def test_timeout_kills_child_holding_working_directory(self):
        with tempfile.TemporaryDirectory() as outer:
            root = Path(outer)
            cwd = root / 'working'
            cwd.mkdir()
            child_code = "import time;from pathlib import Path;Path('ready').write_text('ready');time.sleep(30)"
            launcher = ("import subprocess,sys,time;from pathlib import Path;"
                        "subprocess.Popen([sys.executable,'-c'," + repr(child_code) + "]);"
                        "time.sleep(30)")
            with self.assertRaises(BackendError):
                run_cli([sys.executable, '-c', launcher], '', cwd, 3)
            self.assertTrue((cwd / 'ready').exists(), 'The descendant must start before timeout')
            # An orphan holding cwd prevents removal on Windows.
            shutil.rmtree(cwd)
            self.assertFalse(cwd.exists())


if __name__ == '__main__':
    unittest.main()
