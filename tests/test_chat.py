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

    async def test_worker_protocol_preserves_unicode_with_legacy_stdio(self):
        # Run the real parent/worker JSON protocol under non-UTF-8 child stdio.
        # Only the research/model operation is replaced; no API call is made.
        script = r'''
import research_idea.chat_worker as worker
def echo(project, message):
    worker.event('skill', '\u672c\u8f6e\u5206\u6790\u65b9\u6cd5')
    worker.event('assistant', message)
    worker.event('paper', str(project))
worker.chat_turn = echo
raise SystemExit(worker.main())
'''
        unicode_project = self.project / '中文项目-🧠'
        unicode_project.mkdir()
        self.chat.project = unicode_project
        message = '旧数据学习新模式 🧠\n保留中文、é 和希腊字母 α'
        spawn = asyncio.create_subprocess_exec
        for encoding in ('gbk', 'cp1252', 'ascii'):
            with self.subTest(encoding=encoding):
                async def encoded_worker(*args, **kwargs):
                    return await spawn(sys.executable, '-u', '-c', script,
                        env=dict(os.environ, PYTHONIOENCODING=encoding, PYTHONUTF8='0'), **kwargs)
                self.events.clear()
                with patch('research_idea.chat.asyncio.create_subprocess_exec', side_effect=encoded_worker):
                    await self.chat.work('chat', message)
                self.assertEqual(self.events, [('skill', '本轮分析方法'),
                    ('assistant', message), ('paper', str(unicode_project.resolve()))])
                self.assertIsNone(self.chat.process)
                self.assertEqual(self.chat.state, '就绪')
        saved = [json.loads(line) for line in (unicode_project / 'terminal-events.jsonl')
                 .read_text(encoding='utf-8').splitlines()]
        self.assertEqual([e['text'] for e in saved if e['tag'] == 'assistant'], [message] * 3)

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
        self.assertIn('arXiv 背景与已有方法', self.events[-1][1])
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
                return BackendResult({'answer': '可检查的答复', 'memory_updates': []})
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

    async def test_memory_repair_keeps_one_user_turn_and_cites_its_source(self):
        class Backend:
            calls = 0
            def generate(self, spec):
                self.calls += 1
                return BackendResult({'answer': '保留跨任务目标。', 'memory_updates': [dict(
                    action='add', scope='research', entry_id='', content='保留跨任务目标。',
                    source_message_id='invented' if self.calls == 1 else 'msg_000001')]})
        backend = Backend()
        with patch('research_idea.chat_worker.make_backend', return_value=backend), redirect_stdout(io.StringIO()):
            chat_turn(self.project, '不要缩到单个数据集，要保留跨任务目标。')
        store = Store(self.project)
        try:
            self.assertEqual(store.get('calls_used'), 2)
            self.assertEqual(len(store.get('chat_messages')), 2)
            self.assertEqual(store.get('conversation_memory')[0]['source_message_id'], 'msg_000001')
            self.assertIsNone(store.get('pending_chat_message'))
        finally:
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

    async def test_research_worker_pauses_for_direction_and_problem_then_finishes_brief(self):
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
        self.assertIn('direction', [e['tag'] for e in events])
        self.assertNotIn('idea', [e['tag'] for e in events])
        self.assertNotIn('design', [e['tag'] for e in events])
        store = Store(self.project, readonly=True)
        self.assertEqual(store.get('status'), 'awaiting_direction_discussion')
        self.assertEqual(store.get('problem_checkpoint')['kind'], 'direction')
        calls_before = store.get('calls_used')
        store.close()
        # Reopening or /run redisplays the saved pause without consuming a call.
        with patch('research_idea.chat_worker.make_backend', return_value=DemoBackend()), redirect_stdout(stream):
            research(self.project)
        store = Store(self.project, readonly=True)
        self.assertEqual(store.get('calls_used'), calls_before)
        store.close()
        with patch('research_idea.chat_worker.make_backend', return_value=DemoBackend()), redirect_stdout(stream):
            research(self.project, continue_problem=True)
        events = [json.loads(line) for line in stream.getvalue().splitlines()]
        self.assertIn('problem', [e['tag'] for e in events])
        self.assertNotIn('idea', [e['tag'] for e in events])
        store = Store(self.project, readonly=True)
        self.assertEqual(store.get('status'), 'awaiting_problem_discussion')
        self.assertEqual(store.get('problem_checkpoint')['kind'], 'problem')
        self.assertIsNone(store.get('research_brief'))
        store.close()
        with patch('research_idea.chat_worker.make_backend', return_value=DemoBackend()), redirect_stdout(stream):
            research(self.project, continue_problem=True)
        events = [json.loads(line) for line in stream.getvalue().splitlines()]
        self.assertIn('concept', [e['tag'] for e in events])
        self.assertNotIn('design', [e['tag'] for e in events])
        self.assertEqual(sum(e['tag'] == 'idea' for e in events), 1)
        final = next(e['text'] for e in events if e['tag'] == 'idea')
        for label in ('Background', 'Existing methods', 'Problem', 'Motivation', '研究主张'):
            self.assertIn(label, final)
        self.assertNotIn('技术参考', final)
        self.assertNotIn('第一步验证', final)
        self.assertNotIn('<details>', final)
        store = Store(self.project, readonly=True)
        self.assertEqual(store.get('status'), 'completed')
        self.assertEqual(store.get('workflow'), 'question')
        self.assertTrue(store.get('research_brief')['research_claim'])
        task_stages = {row['stage'] for row in store.db.execute('SELECT stage FROM tasks')}
        self.assertIn('frame_question', task_stages)
        self.assertTrue(task_stages.isdisjoint({'propose', 'develop', 'refine', 'review', 'design_transfer'}))
        calls_completed = store.get('calls_used')
        store.close()
        resumed = io.StringIO()
        with patch('research_idea.chat_worker.make_backend', return_value=DemoBackend()), redirect_stdout(resumed):
            research(self.project)
        reused_events = [json.loads(line) for line in resumed.getvalue().splitlines()]
        self.assertNotIn('evidence', [e['tag'] for e in reused_events])
        reused = [e['text'] for e in reused_events if '已复用' in e['text']]
        self.assertTrue(all('\n' not in text and len(text) < 80 for text in reused))
        self.assertIn('idea', [e['tag'] for e in reused_events])
        store = Store(self.project, readonly=True)
        self.assertEqual(store.get('calls_used'), calls_completed)
        store.close()

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

    async def test_continue_command_and_paused_footer(self):
        from research_idea.problem_dialogue import WAITING
        store = Store(self.project)
        store.set_many({'status': WAITING, 'problem_checkpoint': {'state': 'discussing'}})
        store.close()
        footer = ''.join(text for _, text in self.chat.toolbar())
        self.assertIn('/continue', footer)
        with patch.object(self.chat, 'start', new_callable=AsyncMock) as start:
            await self.chat.handle('/continue')
            start.assert_awaited_once_with('continue')
        with self.assertRaisesRegex(ValueError, '先直接发送'):
            await self.chat.handle('/continue 这里还有重要纠正')
        await self.chat.handle('/memory')
        self.assertIn('尚无提炼的要点', self.events[-1][1])

    async def test_pause_next_step_matches_saved_discussion_on_reopen(self):
        for kind, next_step in [('direction', '深入比较问题'), ('problem', '整理研究主张')]:
            with self.subTest(kind=kind):
                store = Store(self.project)
                store.set_many({'status': f'awaiting_{kind}_discussion',
                                'problem_checkpoint': {'kind': kind, 'state': 'discussing'}})
                store.close()
                with patch('research_idea.chat.shutil.get_terminal_size', return_value=os.terminal_size((140, 24))):
                    footer = ''.join(text for _, text in self.chat.toolbar())
                self.assertIn('/continue ' + next_step, footer)
                await self.chat.handle('/status')
                self.assertIn('/continue ' + next_step, self.events[-1][1])
                await self.chat.handle('/open ' + str(self.project))
                self.assertIn('/continue ' + next_step, self.events[-1][1])
                with patch.object(self.chat, 'start', new_callable=AsyncMock) as start:
                    await self.chat.handle('/continue')
                    start.assert_awaited_once_with('continue')

    async def test_problem_details_and_history_route_without_calling_model(self):
        with patch('research_idea.chat.problem_text', return_value='完整论证') as render:
            await self.chat.handle('/problems detail')
            self.assertTrue(render.call_args.kwargs['detail'])
            self.assertEqual(self.events[-1][1], '完整论证')
            await self.chat.handle('/problems')
            self.assertFalse(render.call_args.kwargs['detail'])
        with patch('research_idea.chat.history_text', return_value='msg_000001 · 用户：保留大方向') as history:
            await self.chat.handle('/history 大方向')
            self.assertEqual(history.call_args.kwargs['query'], '大方向')
            self.assertIn('msg_000001', self.events[-1][1])
            await self.chat.handle('/history')
            self.assertEqual(history.call_args.kwargs['query'], '')
        with self.assertRaisesRegex(ValueError, '/problems detail'):
            await self.chat.handle('/problems invalid')
        self.assertFalse(self.chat.busy)

    async def test_long_activity_is_previewed_but_explicit_details_are_complete(self):
        long_analysis = '\n\n'.join(f'第 {i} 段：' + '解释研究问题的意义。' * 100 for i in range(20))
        long_analysis += '\n\n最终选择：优先研究阻碍原目标的核心困难。'
        self.chat.show('analysis', long_analysis)
        self.assertLess(len(self.events[-1][1]), 6300)
        self.assertIn('/details', self.events[-1][1])
        self.assertIn('最终选择：优先研究阻碍原目标的核心困难。', self.events[-1][1])
        self.chat.show('analysis', long_analysis, full=True)
        self.assertEqual(self.events[-1][1], long_analysis)
        store = Store(self.project)
        store.set('last_activity', {'stage': 'map', 'result': {'problem': long_analysis}})
        store.close()
        await self.chat.handle('/details')
        self.assertIn(long_analysis, self.events[-1][1])
        await self.chat.handle('/details on')
        self.chat.show('analysis', long_analysis)
        self.assertEqual(self.events[-1][1], long_analysis)

    async def test_history_shows_original_user_words_without_resolving_evidence_keys(self):
        from research_idea.conversation import append_message
        store = Store(self.project)
        append_message(store, 'user', 'ev_123 这个内部编号应该给我换成论文链接。')
        store.close()
        await self.chat.handle('/history ev_123')
        self.assertIn('ev_123 这个内部编号应该给我换成论文链接。', self.events[-1][1])
        self.assertIn('msg_000001', self.events[-1][1])
        self.assertNotIn('原文来源未找到', self.events[-1][1])

    async def test_main_analysis_uses_paper_link_and_evidence_preserves_location(self):
        store = Store(self.project)
        store.put('papers', {'id': 'p1', 'title': 'Readable paper', 'url': 'https://example.org/p1'})
        store.replace_evidence('p1', [{'id': 'ev_first', 'paper_id': 'p1', 'page': 4, 'quote': 'first'},
                                     {'id': 'ev_second', 'paper_id': 'p1', 'page': 5, 'quote': 'second'}])
        store.close()
        self.chat.show('analysis', '已有进展：ev_first、ev_second')
        self.assertEqual(self.events[-1][1].count('https://example.org/p1'), 1)
        self.assertNotIn('第 4 页', self.events[-1][1])
        await self.chat.handle('/evidence 1')
        self.assertIn('第 4 页', self.events[-1][1])
        self.assertIn('first', self.events[-1][1])

    async def test_research_brief_shows_the_argument_and_compact_paper_links(self):
        from research_idea.citations import Citations
        from research_idea.presentation import research_brief_markdown, activity_summary, stage_label
        citations = Citations([{'id': 'p1', 'title': 'Recent work', 'url': 'https://example.org/paper'}],
                              [{'id': 'ev_first', 'paper_id': 'p1', 'page': 4},
                               {'id': 'ev_second', 'paper_id': 'p1', 'page': 7}])
        brief = {'title': '值得研究的问题', 'background': '背景中的实际需要。',
                 'existing_methods': '已有办法已经带来的进展。', 'problem': '进展之后仍会发生的困难。',
                 'motivation': '这个困难为什么阻碍原来的目标。', 'research_claim': '我们希望弄清的核心关系。',
                 'why_priority': '优先解决它有助于理解多种方法共同遇到的困难。',
                 'closest_work_ids': ['p1'], 'evidence_ids': ['ev_first', 'ev_second']}
        text = research_brief_markdown(brief, citations)
        positions = [text.index(brief[key]) for key in ('background', 'existing_methods', 'problem',
                                                       'motivation', 'research_claim', 'why_priority')]
        self.assertEqual(positions, sorted(positions))
        self.assertEqual(text.count('https://example.org/paper'), 1)
        self.assertNotIn('ev_first', text)
        self.assertNotIn('第 4 页', text)
        self.assertNotIn('技术路线', text)
        self.assertEqual(activity_summary('frame_question', brief, citations), text)
        self.assertEqual(stage_label('frame_question')[0], 'concept')
        self.assertNotIn('方案设计', stage_label('inspect_source', 'problem')[1])
        self.assertIn('问题补读', stage_label('inspect_source', 'problem')[1])
        self.assertIn('背景', stage_label('inspect_source', 'orientation')[1])

    async def test_discussion_activity_shows_reply_without_dumping_updated_artifact(self):
        from research_idea.presentation import activity_summary
        for stage in ('discuss_direction', 'discuss_question', 'discuss_problem'):
            text = activity_summary(stage, {'answer': '已说明两个问题之间的区别。',
                                           'updated_problems': ['完整后端分析记录'],
                                           'memory_updates': ['内部用户记忆记录']})
            self.assertIn('已说明两个问题之间的区别', text)
            self.assertNotIn('完整后端分析记录', text)
            self.assertNotIn('内部用户记忆记录', text)

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
        self.assertIn('方向讨论后 /continue 深入问题', self.events[-1][1])
        self.assertIn('研究主张', self.events[-1][1])
        self.assertNotIn('进入第二阶段', self.events[-1][1])
        self.assertNotIn('技术参考', self.events[-1][1])
        await self.chat.handle('/help')
        self.assertIn('/history [关键词]', self.events[-1][1])
        self.assertIn('/problems [detail]', self.events[-1][1])
        await self.chat.handle('/config')
        self.assertIn('背景、现有方法、问题、动机与研究主张', self.events[-1][1])
        self.assertNotIn('技术参考', self.events[-1][1])
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
        self.assertIn('研究主张已生成', toolbar)
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
