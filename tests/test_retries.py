"""Operational retries preserve the task, its evidence rules and shared budget."""
import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import Mock, call, patch

from research_idea.backend_errors import ProviderError, RetryExhausted, classify_provider_error
from research_idea.backend_types import BackendResult
from research_idea.chat_worker import chat_turn, main as worker_main
from research_idea.config import DEFAULTS, write_config
from research_idea.controller import BudgetExhausted, Controller, OutputValidationError
from research_idea.presentation import error_summary
from research_idea.store import Store


class RetryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.project = Path(self.tmp.name)
        self.store = Store(self.project)
        self.store.set('topic', 'environment design')
        self.cfg = {**DEFAULTS, 'model': 'gpt-6.1-sol', 'max_calls': 30, 'max_seconds': 1000}
        write_config(self.project, self.cfg)
        self.messages = []
        self.backend = Mock(name='backend')
        self.backend.name = 'test'

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    def run_task(self):
        return Controller(self.store, self.backend, self.cfg, progress=self.messages.append).task(
            'extract', {'paper_id': 'p1', 'excerpt': 'Some supplied source text.'})

    def test_recovery_repeats_same_request_and_accounts_for_failed_attempts(self):
        self.backend.generate.side_effect = [
            ProviderError('network', transport_attempts=1),
            ProviderError('rate_limit', status=429, transport_attempts=1),
            BackendResult({'observations': []}, {'transport_attempts': 1})]
        with patch('research_idea.retries.time.sleep') as sleep:
            self.assertEqual(self.run_task(), {'observations': []})
        self.assertEqual(sleep.call_args_list, [call(30), call(30)])
        specs = [c.args[0] for c in self.backend.generate.call_args_list]
        self.assertEqual(len({(s.task_id, s.prompt, s.model) for s in specs}), 1)
        self.assertEqual(specs[0].model, 'gpt-6.1-sol')
        self.assertEqual(self.store.get('calls_used'), 3)
        self.assertEqual(self.store.get('known_http_attempts'), 3)
        self.assertEqual(self.store.task(specs[0].task_id)['attempts'], 3)
        self.assertTrue(any('[recovered]' in m for m in self.messages))
        self.run_task()  # completed result is reused, not another provider call
        self.assertEqual(self.backend.generate.call_count, 3)

    def test_ten_retries_then_exit_and_can_resume_the_same_task(self):
        self.backend.generate.side_effect = ProviderError('quota', status=429, transport_attempts=1)
        with patch('research_idea.retries.time.sleep') as sleep, self.assertRaises(RetryExhausted) as caught:
            self.run_task()
        self.assertEqual(self.backend.generate.call_count, 11)
        self.assertEqual(sleep.call_args_list, [call(30)] * 10)
        self.assertEqual(self.store.get('calls_used'), 11)
        self.assertEqual(self.store.get('known_http_attempts'), 11)
        self.assertIn('重试 10 次', error_summary(caught.exception))
        self.assertIn('[quota]', error_summary(caught.exception))
        task_id = self.backend.generate.call_args.args[0].task_id
        self.assertEqual(self.store.task(task_id)['status'], 'failed')
        self.backend.generate.side_effect = None
        self.backend.generate.return_value = BackendResult({'observations': []})
        self.run_task()
        self.assertEqual(self.store.task(task_id)['status'], 'succeeded')
        self.assertEqual(self.store.get('calls_used'), 12)

    def test_call_budget_stops_before_an_extra_wait_or_request(self):
        self.cfg['max_calls'] = 2
        self.backend.generate.side_effect = ProviderError('server')
        with patch('research_idea.retries.time.sleep') as sleep, self.assertRaises(BudgetExhausted):
            self.run_task()
        self.assertEqual(self.backend.generate.call_count, 2)
        sleep.assert_called_once_with(30)

    def test_wait_time_is_charged_and_remaining_timeout_is_recomputed(self):
        self.cfg.update(max_seconds=50, timeout_s=120)
        clock = [100.0]
        self.backend.generate.side_effect = [ProviderError('network'), BackendResult({'observations': []})]
        with patch('research_idea.controller.time.monotonic', side_effect=lambda: clock[0]), \
                patch('research_idea.retries.time.sleep', side_effect=lambda seconds: clock.__setitem__(0, clock[0] + seconds)):
            self.run_task()
        self.assertEqual(self.store.get('elapsed_s'), 30)
        self.assertEqual([c.args[0].timeout_s for c in self.backend.generate.call_args_list], [50, 20])

    def test_insufficient_wait_budget_stops_without_sleep(self):
        self.cfg['max_seconds'] = 20
        self.backend.generate.side_effect = ProviderError('auth')
        with patch('research_idea.retries.time.sleep') as sleep, self.assertRaises(BudgetExhausted):
            self.run_task()
        sleep.assert_not_called()
        self.assertEqual(self.store.get('calls_used'), 1)

    def test_ctrl_c_during_wait_preserves_progress(self):
        self.backend.generate.side_effect = ProviderError('network')
        with patch('research_idea.retries.time.sleep', side_effect=KeyboardInterrupt), self.assertRaises(KeyboardInterrupt):
            self.run_task()
        self.assertEqual(self.store.get('calls_used'), 1)
        task_id = self.backend.generate.call_args.args[0].task_id
        self.assertEqual(self.store.task(task_id)['status'], 'failed')

    def test_invalid_evidence_still_has_only_one_repair(self):
        self.backend.generate.return_value = BackendResult({'observations': []})
        controller = Controller(self.store, self.backend, self.cfg)
        def reject(_):
            raise ValueError('Unknown evidence ID')
        with patch('research_idea.retries.time.sleep') as sleep, self.assertRaises(OutputValidationError):
            controller.task('extract', {'excerpt': 'source'}, checker=reject)
        self.assertEqual(self.backend.generate.call_count, 2)
        sleep.assert_not_called()

    def test_chat_uses_the_same_policy_without_duplicating_history(self):
        self.backend.generate.side_effect = [ProviderError('model', status=404, transport_attempts=1),
            BackendResult({'answer': '继续讨论研究方向'}, {'transport_attempts': 1})]
        output = io.StringIO()
        with patch('research_idea.chat_worker.make_backend', return_value=self.backend), \
                patch('research_idea.retries.time.sleep') as sleep, redirect_stdout(output):
            chat_turn(self.project, '我的研究方向')
        sleep.assert_called_once_with(30)
        self.assertEqual(self.store.get('calls_used'), 2)
        self.assertEqual(self.store.get('known_http_attempts'), 2)
        self.assertEqual(len(self.store.get('chat_messages')), 2)
        events = [json.loads(line) for line in output.getvalue().splitlines()]
        self.assertEqual([e['tag'] for e in events], ['thinking', 'retry', 'thinking', 'recovered', 'assistant'])
        self.assertIn('[model]', events[1]['text'])

    def test_worker_returns_failure_after_exhaustion_without_losing_input(self):
        self.backend.generate.side_effect = ProviderError('quota')
        output = io.StringIO()
        request = json.dumps({'project': str(self.project), 'mode': 'chat', 'message': '保存我的方向'})
        with patch('research_idea.chat_worker.make_backend', return_value=self.backend), \
                patch('research_idea.retries.time.sleep'), patch('sys.stdin', io.StringIO(request)), redirect_stdout(output):
            self.assertEqual(worker_main(), 1)
        events = [json.loads(line) for line in output.getvalue().splitlines()]
        self.assertEqual(events[-1]['tag'], 'error')
        self.assertIn('10 次', events[-1]['text'])
        self.assertEqual(self.store.get('chat_messages')[-1]['content'], '保存我的方向')

    def test_classification_distinguishes_quota_from_rate_limit_and_unknowns(self):
        cases = [({'error': {'code': 'insufficient_quota'}}, 429, 'quota'),
                 ('rate_limit_exceeded', 429, 'rate_limit'),
                 ('', 401, 'auth'), ('', 403, 'permission'),
                 ('model_not_found', 404, 'model'), ('', 503, 'server'),
                 ('stream disconnected', None, 'network'), ('timed out', None, 'timeout'),
                 ('opaque upstream failure', 400, 'api')]
        for detail, status, category in cases:
            with self.subTest(detail=detail):
                self.assertEqual(classify_provider_error(detail, status), category)

    def test_exhausted_timeout_keeps_retry_count_in_frontend_message(self):
        error = RetryExhausted(ProviderError('timeout', diagnostic='exceeded the 60s task timeout'), 10)
        self.assertIn('重试 10 次', error_summary(error))
