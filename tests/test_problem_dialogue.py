"""Pause, durable corrections, provenance and continuation across processes."""
import copy
import io
import json
from pathlib import Path
import tempfile
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

from research_idea.backend_types import BackendResult
from research_idea.config import DEFAULTS, write_config
from research_idea.controller import Controller
from research_idea.conversation import (append_message, finish_turn, memory_context,
    research_notes, revised_memory, transcript)
from research_idea.demo import DemoBackend
from research_idea.problem_dialogue import WAITING, discuss, problem_text
from research_idea.report import export_report
from research_idea.store import Store


def payload(task):
    return json.loads(task.prompt.split('BEGIN_RESEARCH_DATA\n')[1].split('\nEND_RESEARCH_DATA')[0])


class RecordingBackend(DemoBackend):
    def __init__(self):
        self.calls = []
        self.discussion = None
        self.fail_proposal = False

    def generate(self, task):
        self.calls.append(task)
        if task.stage == 'discuss_problem':
            return BackendResult(self.discussion(payload(task)))
        if task.stage == 'propose' and self.fail_proposal:
            raise RuntimeError('interruption after confirmation')
        return super().generate(task)


class ProblemDialogueTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name)
        self.store = Store(self.path)
        self.store.set('topic', '一个跨任务的研究方向')
        self.cfg = dict(DEFAULTS, backend='demo', builtin_skills=False,
                        auto_search=False, deep_reading=False, max_calls=100, max_seconds=60)
        self.backend = RecordingBackend()

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    def controller(self, **config):
        return Controller(self.store, self.backend, dict(self.cfg, **config))

    def pause(self):
        self.controller().run(interactive=True)
        self.assertEqual(self.store.get('status'), WAITING)
        self.assertNotIn('propose', [t.stage for t in self.backend.calls])

    def test_pause_is_durable_and_run_cannot_bypass_or_spend_budget(self):
        self.pause()
        checkpoint = self.store.get('problem_checkpoint')
        calls, elapsed = self.store.get('calls_used'), self.store.get('elapsed_s')
        self.store.close()
        self.store = Store(self.path)
        self.controller().run()  # batch resume also respects a saved human pause
        self.assertEqual(self.store.get('problem_checkpoint'), checkpoint)
        self.assertEqual(self.store.get('calls_used'), calls)
        self.assertEqual(self.store.get('elapsed_s'), elapsed)
        report, _ = export_report(self.store, self.path)
        self.assertIn('/continue', report.read_text(encoding='utf-8'))
        self.assertIn('优先考虑这个问题', problem_text(self.store))

    def test_discussion_changes_selected_problem_and_survives_restart(self):
        self.pause()
        original = copy.deepcopy(self.store.get('problem_checkpoint')['original'])
        message = append_message(self.store, 'user', '优先看第二个问题，别限制到单一任务。')
        def correction(data):
            case = copy.deepcopy(data['problem_model']['opportunities'][1])
            case['why_it_matters'] = '这是用户要求关注的跨任务能力，而不只是局部成绩。'
            return dict(answer='改为第二个问题，保留跨任务目标。',
                updated_problems=[case], selected_problems=[dict(opportunity_id=case['id'],
                    selection_reason='用户选择第二个问题，研究目标跨任务。')],
                memory_updates=[dict(action='add', scope='research', entry_id='', content='保留跨任务范围。',
                    source_message_id=data['current_user_message']['id'])])
        self.backend.discussion = correction
        discuss(self.controller(), message)
        checkpoint = self.store.get('problem_checkpoint')
        self.assertEqual(checkpoint['original'], original)
        self.assertEqual(checkpoint['revision'], 2)
        self.assertEqual(checkpoint['state'], 'discussing')
        self.assertEqual(self.store.rows('candidates'), [])
        self.store.close()
        self.store = Store(self.path)
        self.controller().run(interactive=True, continue_problem=True)
        drafts = [payload(t) for t in self.backend.calls if t.stage == 'propose']
        chosen = checkpoint['current']['selected_problems'][0]['opportunity_id']
        self.assertEqual(drafts[0]['problem_model']['opportunities'][0]['id'], chosen)
        self.assertIn('跨任务', drafts[0]['argument_handoff'][0]['selection_reason'])
        self.assertIn('保留跨任务范围', str(drafts[0]['user_notes']))
        self.assertEqual(drafts[0]['problem_discussion']['confirmed_revision'], 2)
        self.assertEqual(sum(t.stage == 'explore_problems' for t in self.backend.calls), 1)
        self.assertEqual(self.store.get('status'), 'completed')
        self.assertTrue(any('跨任务' in str(payload(t)['user_notes'])
                            for t in self.backend.calls if t.stage == 'develop'))

    def test_failed_discussion_cannot_be_silently_skipped(self):
        self.pause()
        m = append_message(self.store, 'user', '先改变问题')
        self.store.set('pending_chat_message', m['id'])
        with self.assertRaisesRegex(ValueError, '尚未成功处理'):
            self.controller().run(continue_problem=True)
        self.assertEqual(self.store.get('problem_checkpoint')['state'], 'discussing')

    def test_confirmation_survives_interrupted_proposal(self):
        self.pause()
        self.backend.fail_proposal = True
        with self.assertRaisesRegex(RuntimeError, 'interruption'):
            self.controller().run(continue_problem=True)
        self.assertEqual(self.store.get('problem_checkpoint')['state'], 'confirmed')
        self.backend.fail_proposal = False
        self.controller().run(interactive=True)
        self.assertEqual(self.store.get('status'), 'completed')
        self.assertEqual(sum(t.stage == 'explore_problems' for t in self.backend.calls), 1)

    def test_source_revision_reopens_discussion_without_deleting_user_memory(self):
        self.pause()
        self.store.set('source_revision', 1)
        with self.assertRaisesRegex(ValueError, '已变化'):
            self.controller().run(continue_problem=True)
        self.controller().run(interactive=True)
        self.assertEqual(self.store.get('status'), WAITING)
        self.assertNotIn('propose', [t.stage for t in self.backend.calls])

    def test_model_change_keeps_problem_choice(self):
        self.pause()
        self.controller(model='another-model', reasoning_effort='high').run(continue_problem=True)
        self.assertEqual(sum(t.stage == 'explore_problems' for t in self.backend.calls), 1)
        self.assertEqual(self.store.get('status'), 'completed')

    def test_changed_sources_do_not_reuse_a_completed_cohort(self):
        self.pause()
        self.controller().run(continue_problem=True)
        self.store.set('source_revision', 1)
        self.controller().run(interactive=True)
        self.assertEqual(self.store.get('status'), WAITING)
        self.assertEqual(self.store.get('problem_checkpoint')['state'], 'discussing')
        self.assertIsNone(self.store.get('cohort'))

    def test_memories_outlive_recent_window_and_can_be_replaced(self):
        first = append_message(self.store, 'user', '只考虑有公开权重的模型。')
        finish_turn(self.store, dict(answer='已记录。', memory_updates=[dict(action='add', scope='research', entry_id='',
            content='仅考虑公开权重模型。', source_message_id=first['id'])]), {first['id']})
        for i in range(15):
            user = append_message(self.store, 'user', f'讨论细节 {i}')
            finish_turn(self.store, dict(answer='讨论答复', memory_updates=[]), {user['id']})
        self.assertNotIn(first['id'], str(memory_context(self.store)['recent_history']))
        self.assertIn('公开权重', str(self.controller().context()['user_notes']))
        latest = append_message(self.store, 'user', '改成允许 API 模型。')
        finish_turn(self.store, dict(answer='已替换。', memory_updates=[dict(action='replace', scope='research',
            entry_id='memory_000001', content='允许 API 模型。', source_message_id=latest['id'])]), {latest['id']})
        self.assertNotIn('仅考虑公开权重', str(research_notes(self.store)))
        self.assertIn('允许 API 模型', str(research_notes(self.store)))
        self.assertFalse(self.store.get('conversation_memory')[0]['active'])
        self.assertEqual(transcript(self.store)[0]['content'], first['content'])

    def test_continue_ends_temporary_instructions_but_keeps_research_constraints(self):
        self.pause()
        user = append_message(self.store, 'user', '先别提出方案；保持跨任务目标，不展开实验计划。')
        finish_turn(self.store, dict(answer='先讨论问题。', memory_updates=[
            dict(action='add', scope='discussion', entry_id='', content='先别提出方案。', source_message_id=user['id']),
            dict(action='add', scope='research', entry_id='', content='保持跨任务目标。', source_message_id=user['id']),
            dict(action='add', scope='research', entry_id='', content='不展开实验计划。', source_message_id=user['id']),
        ]), {user['id']})
        self.assertIn('先别提出方案', str(research_notes(self.store)))
        self.controller().run(continue_problem=True)
        draft = next(payload(t) for t in self.backend.calls if t.stage == 'propose')
        self.assertNotIn('先别提出方案', str(draft['user_notes']))
        self.assertIn('跨任务目标', str(draft['user_notes']))
        self.assertIn('不展开实验计划', str(draft['user_notes']))
        self.assertEqual(self.store.get('conversation_memory')[0]['retired_by_command'], '/continue')
        self.assertIn('先别提出方案', transcript(self.store)[0]['content'])

    def test_memory_cannot_cite_assistant_and_bad_patch_is_atomic(self):
        user = append_message(self.store, 'user', '保持大方向')
        assistant = append_message(self.store, 'assistant', '建议只做单任务')
        with self.assertRaisesRegex(ValueError, 'user message'):
            revised_memory(self.store, [dict(action='add', scope='research', entry_id='', content='只做单任务',
                source_message_id=assistant['id'])], {user['id']})
        self.assertEqual(self.store.get('conversation_memory', []), [])
        finish_turn(self.store, dict(answer='好', memory_updates=[dict(action='add', scope='research', entry_id='',
            content='保持大方向', source_message_id=user['id'])]), {user['id']})
        before = copy.deepcopy(self.store.get('conversation_memory'))
        with self.assertRaises(ValueError):
            revised_memory(self.store, [dict(action='remove', scope='research', entry_id='memory_000001', content='',
                source_message_id=user['id']), dict(action='replace', scope='research', entry_id='missing', content='错',
                source_message_id=user['id'])], {user['id']})
        self.assertEqual(self.store.get('conversation_memory'), before)

    def test_legacy_and_failed_messages_are_not_dropped(self):
        self.store.set('chat_messages', [dict(role='user', content=f'原始要求 {i}') for i in range(20)])
        self.assertEqual(len(memory_context(self.store)['unreviewed_user_messages']), 20)
        self.assertIn('原始要求 0', self.controller().user_notes())
        self.assertEqual(transcript(self.store)[0]['id'], transcript(self.store)[0]['id'])

    def test_unscoped_legacy_memory_brings_back_original_source_for_migration(self):
        user = append_message(self.store, 'user', '先别写方案，保留跨任务范围。')
        self.store.set('conversation_memory', [dict(id='old', active=True,
            content='先别写方案，保留跨任务范围。', source_message_id=user['id'])])
        self.store.set('memory_reviewed_messages', [user['id']])
        for _ in range(15):
            append_message(self.store, 'assistant', '讨论')
        context = memory_context(self.store)
        self.assertNotIn(user['id'], str(context['recent_history']))
        self.assertIn(user, context['unreviewed_user_messages'])
        with self.assertRaisesRegex(ValueError, 'scope'):
            revised_memory(self.store, [], {user['id']})
        ledger = revised_memory(self.store, [dict(action='replace', entry_id='old', scope='discussion',
            content='先别写方案。', source_message_id=user['id']), dict(action='add', entry_id='', scope='research',
            content='保留跨任务范围。', source_message_id=user['id'])], {user['id']})
        self.assertEqual([m['scope'] for m in ledger if m['active']], ['discussion', 'research'])

    def test_worker_routes_paused_message_to_research_discussion(self):
        from research_idea.chat_worker import chat_turn
        self.pause()
        write_config(self.path, self.cfg)
        original = self.store.get('problem_checkpoint')['current']
        self.backend.discussion = lambda data: dict(answer='先解释问题的原因。', updated_problems=[],
            selected_problems=[], memory_updates=[])
        with patch('research_idea.chat_worker.make_backend', return_value=self.backend), redirect_stdout(io.StringIO()):
            chat_turn(self.path, '这个问题为什么重要？')
        self.assertEqual(self.backend.calls[-1].stage, 'discuss_problem')
        self.assertEqual(self.store.get('status'), WAITING)
        self.assertIsNone(self.store.get('pending_chat_message'))
        self.assertEqual(self.store.get('problem_checkpoint')['current'], original)


if __name__ == '__main__':
    unittest.main()
