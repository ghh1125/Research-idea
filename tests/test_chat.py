"""Conversation configuration, provenance, budgets, and worker recovery."""
import asyncio
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch, AsyncMock

from research_idea.backend_types import BackendError, BackendResult
from research_idea.chat import Chat, initialize, model_catalog, fragments, safe_text
from research_idea.chat_worker import chat_turn, research
from research_idea.cli import build_parser, main
from research_idea.config import load_config, write_config
from research_idea.controller import BudgetExhausted
from research_idea.demo import DemoBackend, DEMO_PAPERS
from research_idea.store import Store


class ChatTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.project = Path(self.tmp.name) / 'project'
        args = build_parser().parse_args(['chat', '--project', str(self.project), '--output', str(self.project.parent / 'results')])
        initialize(args)
        self.events = []
        self.chat = Chat(self.project, lambda tag, text: self.events.append((tag, text)))

    def tearDown(self):
        self.tmp.cleanup()

    async def test_date_and_shortlist_settings_are_editable(self):
        await self.chat.handle('/date rolling 12 6')
        self.assertEqual(load_config(self.project)['novelty_months'], 6)
        await self.chat.handle('/date fixed 2025-01-01 2026-10-23')
        self.assertEqual(load_config(self.project)['search_date_mode'], 'fixed')
        self.assertEqual(load_config(self.project)['conference_policy'], 'window')
        with self.assertRaises(ValueError):
            await self.chat.handle('/date rolling 6 12')
        await self.chat.handle('/budget search_results_per_query 30')
        self.assertEqual(load_config(self.project)['search_results_per_query'], 30)
        await self.chat.handle('/venues ACL COLM ICLR')
        self.assertEqual(load_config(self.project)['search_venues'], ['ACL', 'COLM', 'ICLR'])
        await self.chat.handle('/venues')
        self.assertIn('ICLR: CCF2026 A', self.events[-1][1])

    async def test_date_conference_choice_is_independent_and_visible(self):
        self.assertEqual(load_config(self.project)['conference_policy'], 'latest')
        await self.chat.handle('/date conference window')
        self.assertEqual(load_config(self.project)['conference_policy'], 'window')
        self.assertEqual(load_config(self.project)['search_date_mode'], 'rolling')
        await self.chat.handle('/date fixed 2025-01-01 2026-10-23')
        await self.chat.handle('/date conference latest')
        cfg = load_config(self.project)
        self.assertEqual(cfg['conference_policy'], 'latest')
        self.assertEqual(cfg['search_until'], '2026-10-23')
        with self.assertRaises(ValueError):
            await self.chat.handle('/date conference arbitrary')
        self.assertEqual(load_config(self.project)['conference_policy'], 'latest')
        with patch.object(self.chat, 'pick', new=AsyncMock(return_value='返回')):
            await self.chat.handle('/date')
        self.assertIn('arXiv 背景与技术探索', self.events[-1][1])
        self.assertIn('本届未公开则选上一届', self.events[-1][1])
        await self.chat.handle('/config')
        self.assertIn('会议时间：各会议最新公开的一届', self.events[-1][1])
        await self.chat.handle('/scope 2025-01-01 2026-10-23')
        self.assertEqual(load_config(self.project)['conference_policy'], 'window')
        await self.chat.handle('/scope ai-recent')
        self.assertEqual(load_config(self.project)['conference_policy'], 'latest')

    async def test_settings_persist_and_invalid_strength_preserves_config(self):
        await self.chat.handle('/model custom-model')
        await self.chat.handle('/reasoning high')
        self.assertEqual(load_config(self.project)['model'], 'custom-model')
        with self.assertRaises(ValueError):
            await self.chat.handle('/reasoning definitely-invalid')
        self.assertEqual(load_config(self.project)['reasoning_effort'], 'high')
        await self.chat.handle('/reasoning inherit')
        self.assertEqual(load_config(self.project)['reasoning_effort'], '')

    async def test_busy_blocks_mutation_but_status_remains_available(self):
        self.chat.job = asyncio.create_task(asyncio.sleep(100))
        try:
            for command in ('/model changed', '/new another topic'):
                with self.assertRaises(ValueError):
                    await self.chat.handle(command)
            await self.chat.handle('/status')
            self.assertIn('调用', self.events[-1][1])
        finally:
            self.chat.job.cancel()
            await asyncio.gather(self.chat.job, return_exceptions=True)

    async def test_paper_evidence_lookup_contains_exact_source(self):
        store = Store(self.project)
        store.put('papers', {'id': 'p1', 'title': 'A paper', 'url': 'https://example.org/p1'})
        store.replace_evidence('p1', [{'id': 'ev_123', 'paper_id': 'p1', 'quote': 'exact words', 'page': 4}])
        store.close()
        await self.chat.handle('/evidence ev_123')
        self.assertIn('https://example.org/p1', self.events[-1][1])
        self.assertIn('exact words', self.events[-1][1])
        self.assertNotIn('ev_123', self.events[-1][1])
        await self.chat.handle('/evidence')
        self.assertIn('1. [A paper]', self.events[-1][1])
        await self.chat.handle('/evidence 1')
        self.assertIn('exact words', self.events[-1][1])
        self.chat.show('analysis', '此判断依据 ev_123。')
        self.assertIn('[A paper](https://example.org/p1)', self.events[-1][1])
        self.assertNotIn('ev_123', self.events[-1][1])

    async def test_spinner_advances_while_waiting_and_disappears_when_done(self):
        self.chat.job = asyncio.create_task(asyncio.sleep(60))
        self.chat.started = self.chat.step_started = 100
        self.chat.state = '4/4 · 设计具体方法'
        try:
            with patch('research_idea.chat.shutil.get_terminal_size', return_value=os.terminal_size((120, 24))):
                with patch('research_idea.chat.time.monotonic', return_value=102):
                    first = ''.join(text for _, text in self.chat.toolbar())
                with patch('research_idea.chat.time.monotonic', return_value=102.25):
                    second = ''.join(text for _, text in self.chat.toolbar())
            self.assertIn('⠋', first)
            self.assertIn('⠙', second)
            self.assertIn('设计具体方法 · 本步 0:02', second)
            self.assertIn('Ctrl+C 停止', second)
        finally:
            self.chat.job.cancel()
            await asyncio.gather(self.chat.job, return_exceptions=True)
        idle = ''.join(text for _, text in self.chat.toolbar())
        self.assertNotRegex(idle, '[⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏]')
        self.assertNotIn('本步', idle)

    async def test_chat_followup_uses_history_selected_model_and_shared_budget(self):
        captured = []
        class Backend:
            def generate(self, spec):
                captured.append(spec)
                return BackendResult({'answer': '可检查的答复'})
        self.chat.topic('环境设计')
        self.chat.settings(model='gpt-6.1-sol', reasoning_effort='high', max_calls=2)
        with patch('research_idea.chat_worker.make_backend', return_value=Backend()), redirect_stdout(io.StringIO()):
            chat_turn(self.project, '第一条')
            chat_turn(self.project, '追问')
            with self.assertRaises(BudgetExhausted):
                chat_turn(self.project, '超出预算')
        self.assertIn('第一条', captured[1].prompt)
        self.assertIn('可检查的答复', captured[1].prompt)
        self.assertEqual(captured[1].model, 'gpt-6.1-sol')
        store = Store(self.project)
        self.assertEqual(store.get('calls_used'), 2)
        self.assertEqual(len(store.get('chat_messages')), 4)
        store.close()

    async def test_interrupted_chat_releases_lock_and_records_attempt(self):
        class Backend:
            def generate(self, spec):
                raise KeyboardInterrupt()
        with patch('research_idea.chat_worker.make_backend', return_value=Backend()), redirect_stdout(io.StringIO()):
            with self.assertRaises(KeyboardInterrupt):
                chat_turn(self.project, '中断')
        self.chat.settings(reasoning_effort='high')
        store = Store(self.project)
        self.assertEqual(store.get('calls_used'), 1)
        self.assertGreater(store.get('elapsed_s'), 0)
        store.close()

    async def test_chat_total_deadline_reports_budget_and_preserves_input(self):
        self.chat.settings(max_seconds=60, timeout_s=120)
        with patch('research_idea.chat_worker.time.monotonic', return_value=0) as clock:
            class Backend:
                def generate(self, spec):
                    clock.return_value = 60
                    raise BackendError('model task timed out')
            with patch('research_idea.chat_worker.make_backend', return_value=Backend()), redirect_stdout(io.StringIO()):
                with self.assertRaisesRegex(BudgetExhausted, 'max_seconds'):
                    chat_turn(self.project, '保留这条讨论')
        store = Store(self.project)
        try:
            self.assertEqual(store.get('calls_used'), 1)
            self.assertEqual(store.get('elapsed_s'), 60)
            self.assertEqual(store.get('chat_messages')[-1]['content'], '保留这条讨论')
        finally:
            store.close()

    async def test_research_worker_emits_findings_and_finishes_with_idea(self):
        store = Store(self.project)
        store.set('topic', 'Synthetic test only')
        for p in DEMO_PAPERS:
            from research_idea.literature import normalize_paper
            store.put('papers', normalize_paper(p))
        store.close()
        cfg = load_config(self.project)
        cfg.update(auto_search=False, deep_reading=False)
        write_config(self.project, cfg)
        stream = io.StringIO()
        with patch('research_idea.chat_worker.make_backend', return_value=DemoBackend()), redirect_stdout(stream):
            research(self.project)
        events = [json.loads(line) for line in stream.getvalue().splitlines()]
        self.assertIn('paper', [e['tag'] for e in events])
        self.assertIn('evidence', [e['tag'] for e in events])
        self.assertIn('review', [e['tag'] for e in events])
        self.assertIn('concept', [e['tag'] for e in events])
        self.assertIn('design', [e['tag'] for e in events])
        self.assertEqual(sum(e['tag'] == 'idea' for e in events), 1)
        concept = next(e for e in events if e['tag'] == 'concept' and '核心想法' in e['text'])
        self.assertIn('第一阶段到此完成', concept['text'])
        self.assertIn('核心想法', concept['text'])
        self.assertIn('第二阶段', next(e['text'] for e in events if e['tag'] == 'design'))
        self.assertEqual(events[-2]['tag'], 'idea')
        self.assertIn('Problem · 要解决的问题与原因', events[-2]['text'])
        self.assertIn('技术参考', events[-2]['text'])
        self.assertNotIn('第一步验证', events[-2]['text'])
        self.assertNotIn('<details>', events[-2]['text'])
        resumed = io.StringIO()
        with patch('research_idea.chat_worker.make_backend', return_value=DemoBackend()), redirect_stdout(resumed):
            research(self.project)
        reused_events = [json.loads(line) for line in resumed.getvalue().splitlines()]
        self.assertNotIn('evidence', [e['tag'] for e in reused_events])
        reused = [e['text'] for e in reused_events if '已复用' in e['text']]
        self.assertTrue(reused)
        self.assertTrue(all('\n' not in text and len(text) < 80 for text in reused))
        self.assertIn('detail', [e['tag'] for e in reused_events])
        self.assertEqual(reused_events[-2]['tag'], 'idea')

    async def test_stop_real_worker_process_and_return_to_prompt(self):
        script = Path(self.tmp.name) / 'fake-worker'
        script.write_text('#!/bin/sh\nexec "' + sys.executable + '" -c "import time; time.sleep(60)"\n')
        script.chmod(0o755)
        with patch('research_idea.chat.sys.executable', str(script)):
            await self.chat.start('chat', 'test')
            for _ in range(100):
                if self.chat.process:
                    break
                await asyncio.sleep(.01)
            await asyncio.wait_for(self.chat.stop(), 5)
        self.assertFalse(self.chat.busy)
        self.assertIsNone(self.chat.process)

    async def test_account_status_does_not_echo_provider_secret(self):
        script = Path(self.tmp.name) / 'account-cli'
        script.write_text('#!/bin/sh\necho "Logged in using API key: sk-secret-sentinel"\n')
        script.chmod(0o755)
        self.chat.settings(codex_bin=str(script))
        await self.chat.handle('/account')
        self.assertIn('API key 登录', self.events[-1][1])
        self.assertNotIn('sk-secret-sentinel', self.events[-1][1])

    async def test_topic_change_after_research_is_rejected(self):
        self.chat.topic('first')
        store = Store(self.project)
        store.begin_task('one', 'map')
        store.close()
        with self.assertRaises(ValueError):
            self.chat.topic('changed')

    async def test_input_file_is_message_not_command(self):
        brief = Path(self.tmp.name) / 'brief.txt'
        brief.write_text('/model accidental-command', encoding='utf-8')
        with patch.object(self.chat, 'start', new_callable=AsyncMock) as start:
            await self.chat.handle('/input ' + str(brief))
        start.assert_awaited_once_with('chat', '/model accidental-command')
        self.assertEqual(load_config(self.project)['model'], 'gpt-6.1-sol')

    async def test_catalog_allowlists_fields_and_colors_untrusted_text(self):
        cache = Path(self.tmp.name) / 'models_cache.json'
        cache.write_text(json.dumps({'identity': 'private-account', 'models': [
            {'slug': 'hidden-model', 'visibility': 'hide'},
            {'slug': 'gpt-6.1-sol', 'secret': 'private', 'supported_reasoning_levels': [{'effort': 'high'}]}]}))
        with patch.dict(os.environ, CODEX_HOME=self.tmp.name):
            models, note = model_catalog()
        self.assertEqual(models, [{'id': 'gpt-6.1-sol', 'levels': ['high']}])
        self.assertNotIn('private', str(models) + note)
        colored = fragments('evidence', 'ev_abc https://example.org\n原文：hello\n未知')
        self.assertTrue(any(style == 'ansigreen bold' and text == 'ev_abc' for style, text in colored))
        self.assertNotIn('\x1b', safe_text('\x1b]52;clipboard\x07'))

    async def test_non_tty_chat_rejected(self):
        with patch('sys.stdin.isatty', return_value=False):
            self.assertEqual(main(['chat', '--project', str(self.project), '--output', str(self.project.parent / 'results')]), 1)

    async def test_intro_is_always_in_toolbar_and_does_not_call_model(self):
        self.assertIn('/intro 使用介绍', ''.join(text for _, text in self.chat.toolbar()))
        await self.chat.handle('/intro')
        self.assertIn('技术参考', self.events[-1][1])
        self.assertFalse(self.chat.busy)

    async def test_new_project_starts_empty_with_same_settings_and_old_project_can_reopen(self):
        self.chat.settings(reasoning_effort='high', max_seconds=7800, max_papers=4)
        settings = load_config(self.project)
        store = Store(self.project)
        store.set('topic', '旧方向')
        store.set('calls_used', 61)
        store.set('elapsed_s', 6892)
        store.set('status', 'completed')
        store.set('chat_messages', [{'role': 'user', 'content': '旧讨论'}])
        store.put('papers', {'id': 'old-paper'})
        store.replace_evidence('old-paper', [{'id': 'ev_old', 'paper_id': 'old-paper'}])
        store.put('candidates', {'id': 'old-idea'})
        store.begin_task('old-task', 'develop')
        store.finish_task('old-task', {'saved': True}, {})
        store.close()
        (self.project / 'outputs').mkdir()
        (self.project / 'outputs/report.md').write_text('旧方案')

        with patch.object(self.chat, 'start', new_callable=AsyncMock) as start:
            await self.chat.handle('/new')
        start.assert_not_awaited()
        fresh = self.chat.project
        self.assertNotEqual(fresh, self.project)
        self.assertEqual(fresh.parent, self.project.parent)
        self.assertEqual(load_config(fresh), settings)
        store = Store(fresh, readonly=True)
        try:
            self.assertEqual(store.get('calls_used', 0), 0)
            self.assertEqual(store.get('elapsed_s', 0), 0)
            self.assertIsNone(store.get('topic'))
            self.assertEqual(store.get('chat_messages', []), [])
            self.assertEqual(store.get('status'), 'initialized')
            for table in ('papers', 'evidence', 'candidates'):
                self.assertEqual(store.rows(table), [])
            self.assertEqual(store.task_summary(), {})
        finally:
            store.close()
        self.assertIn('调用 0/80', ''.join(text for _, text in self.chat.toolbar()))
        await self.chat.handle('/report')
        self.assertIn('尚无方案', self.events[-1][1])

        await self.chat.handle('/open ' + str(self.project))
        store = Store(self.project, readonly=True)
        try:
            self.assertEqual(store.get('calls_used'), 61)
            self.assertEqual(store.get('elapsed_s'), 6892)
            self.assertEqual(store.get('chat_messages')[0]['content'], '旧讨论')
            self.assertEqual(store.task('old-task')['status'], 'succeeded')
            self.assertEqual(len(store.rows('papers')), 1)
        finally:
            store.close()
        await self.chat.handle('/report')
        self.assertEqual(self.events[-1][1], '旧方案')
        toolbar = ''.join(text for _, text in self.chat.toolbar())
        self.assertIn('方案已生成', toolbar)
        self.assertIn('本项目累计', toolbar)
        self.assertIn('调用 61/80', toolbar)
        self.assertIn('/new 新研究', toolbar)

    async def test_new_topic_is_literal_and_prompt_history_is_cleared(self):
        from prompt_toolkit import PromptSession
        from prompt_toolkit.input import create_pipe_input
        from prompt_toolkit.output import DummyOutput
        with create_pipe_input() as pipe:
            self.chat.session = PromptSession(input=pipe, output=DummyOutput())
            self.chat.session.history.append_string('old discussion')
            with patch.object(self.chat, 'start', new_callable=AsyncMock) as start:
                await self.chat.handle('/new /model is a research topic')
            start.assert_not_awaited()
            self.assertEqual(self.chat.topic(), '/model is a research topic')
            self.assertEqual(self.chat.cfg['model'], 'gpt-6.1-sol')
            self.assertEqual(self.chat.session.history.get_strings(), [])
            self.assertIs(self.chat.session.default_buffer.history, self.chat.session.history)

    async def test_budget_is_live_in_status_bar(self):
        store = Store(self.project)
        store.set('calls_used', 7)
        store.set('elapsed_s', 120)
        store.close()
        text = ''.join(text for _, text in self.chat.toolbar())
        self.assertIn('调用 7/80', text)
        self.assertIn('时间 2.0/110', text)

    async def test_running_view_has_no_prompt_and_control_c_stops(self):
        from prompt_toolkit.input import create_pipe_input
        from prompt_toolkit.output import DummyOutput
        from prompt_toolkit.application import create_app_session
        self.chat.job = asyncio.create_task(asyncio.sleep(60))
        async def stop():
            self.chat.job.cancel()
            await asyncio.gather(self.chat.job, return_exceptions=True)
        with create_pipe_input() as pipe, create_app_session(input=pipe, output=DummyOutput()):
            with patch.object(self.chat, 'stop', new_callable=AsyncMock, side_effect=stop) as stopped:
                view = asyncio.create_task(self.chat.wait_running())
                await asyncio.sleep(.05)
                pipe.send_text('ignored input')
                pipe.send_bytes(b'\x03')
                await asyncio.wait_for(view, 3)
                stopped.assert_awaited_once()
        self.assertFalse(self.chat.busy)

    async def test_running_view_returns_automatically_when_job_finishes(self):
        from prompt_toolkit.input import create_pipe_input
        from prompt_toolkit.output import DummyOutput
        from prompt_toolkit.application import create_app_session
        self.chat.job = asyncio.create_task(asyncio.sleep(.05))
        with create_pipe_input() as pipe, create_app_session(input=pipe, output=DummyOutput()):
            await asyncio.wait_for(self.chat.wait_running(), 3)
        self.assertFalse(self.chat.busy)


if __name__ == '__main__':
    unittest.main()
