"""The conversational question survives restart without becoming a user decision."""
from copy import deepcopy
from pathlib import Path
import json
import tempfile
import unittest
from unittest.mock import patch

from research_idea.backend_types import BackendResult
from research_idea.config import DEFAULTS
from research_idea.controller import Controller, OutputValidationError
from research_idea.conversation import append_message, transcript
from research_idea.demo import DemoBackend
from research_idea.discussion_focus import previous_focus
from research_idea.problem_dialogue import discuss, open_checkpoint
from research_idea.store import Store


class Backend(DemoBackend):
    def __init__(self):
        self.focus = []
        self.payloads = []
        self.fail = False
        self.read = False

    def generate(self, task):
        if task.stage in {'discuss_direction', 'discuss_question'}:
            payload = json.loads(task.prompt.split('BEGIN_RESEARCH_DATA\n')[1].split('\nEND_RESEARCH_DATA')[0])
            self.payloads.append(payload)
            if self.fail:
                raise RuntimeError('interrupted')
            result = super().generate(task).output
            result.update(answer='先解释当前分歧。', discussion_focus=deepcopy(self.focus))
            if self.read and not payload['source_work_done']:
                result['research_requests'] = [dict(question='需要核对的回应', query='response', paper_ids=[])]
            return BackendResult(result)
        return super().generate(task)


class FocusTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name)
        self.store = Store(self.path)
        self.store.set('topic', '多agent怎样理解不同成员的信息')
        self.config = dict(DEFAULTS, backend='demo', auto_search=False, builtin_skills=False,
                           max_calls=100, max_seconds=60)
        self.backend = Backend()
        self.controller().run_questions(interactive=True)
        self.question = dict(question='你更关心信息没传到，还是传到了却被误解？',
                             why_it_matters='区分传递失败与含义理解失败，会改变问题成因。')

    def tearDown(self):
        self.store.close()
        self.temp.cleanup()

    def controller(self):
        return Controller(self.store, self.backend, self.config)

    def ask(self, text='帮我想清楚'):
        return discuss(self.controller(), append_message(self.store, 'user', text))

    def test_short_reply_after_restart_receives_actual_question_not_a_preference(self):
        self.backend.focus = [self.question]
        original = deepcopy(self.store.get('problem_checkpoint')['current'])
        answer = self.ask()
        self.assertEqual(answer.count(self.question['question']), 1)
        self.assertEqual(transcript(self.store)[-1]['content'], answer)
        self.assertEqual(self.store.get('problem_checkpoint')['current'], original)
        self.assertEqual(self.store.get('conversation_memory'), [])
        self.store.close()
        self.store = Store(self.path)
        self.backend.focus = []
        self.ask('后者')
        data = self.backend.payloads[-1]
        self.assertEqual(data['previous_discussion_focus'][0]['question'], self.question['question'])
        self.assertEqual(data['previous_discussion_focus'][0]['origin'], 'assistant_question')
        self.assertEqual(self.store.get('problem_checkpoint')['discussion_focus'], [])
        self.assertEqual(data['active_memory'], [])
        self.assertEqual(data['current_user_message']['content'], '后者')

    def test_unanswered_question_does_not_block_continue_or_leak_to_new_stage(self):
        self.backend.focus = [self.question]
        self.ask()
        self.controller().run_questions(interactive=True, continue_problem=True)
        self.assertEqual(self.store.get('problem_checkpoint')['kind'], 'problem')
        self.assertEqual(previous_focus(self.store.get('problem_checkpoint')), [])
        self.ask('还想讨论')
        self.controller().run_questions(interactive=True, continue_problem=True)
        self.assertEqual(self.store.get('status'), 'completed')
        self.assertEqual(self.store.get('problem_checkpoint')['discussion_focus'], [])
        self.assertEqual(self.store.get('conversation_memory'), [])

    def test_failure_keeps_previous_focus_and_retry_commits_new_one(self):
        self.backend.focus = [self.question]
        self.ask()
        before = deepcopy(self.store.get('problem_checkpoint'))
        message = append_message(self.store, 'user', '后者')
        self.backend.fail = True
        with self.assertRaisesRegex(RuntimeError, 'interrupted'):
            discuss(self.controller(), message)
        self.assertEqual(self.store.get('problem_checkpoint'), before)
        self.backend.fail = False
        self.backend.focus = []
        discuss(self.controller(), message)
        self.assertEqual(self.store.get('problem_checkpoint')['discussion_focus'], [])
        self.assertEqual(self.backend.payloads[-1]['previous_discussion_focus'][0]['question'], self.question['question'])

    def test_invalid_focus_is_repaired_once_without_publishing_a_questionnaire(self):
        self.backend.focus = [self.question, self.question]
        before = deepcopy(self.store.get('problem_checkpoint'))
        with self.assertRaises(OutputValidationError):
            self.ask()
        self.assertEqual(len(self.backend.payloads), 2)
        self.assertEqual(self.store.get('problem_checkpoint'), before)
        self.assertFalse(any(m['role'] == 'assistant' for m in transcript(self.store)))

    def test_followup_only_publishes_final_question_and_preserves_previous_hint(self):
        self.backend.focus = [self.question]
        self.ask()
        self.backend.read = True
        preliminary = dict(question='这是补读前的问题？', why_it_matters='补读可能改变判断。')
        final = dict(question='这是读完后真正需要区分的地方？', why_it_matters='根据读到的材料继续讨论。')
        self.backend.focus = [preliminary]
        def acquire(*args, **kwargs):
            self.backend.focus = [final]
            return dict(performed=True, readings=[])
        with patch('research_idea.discussion_sources.research_requests', side_effect=acquire):
            answer = self.ask('请补读再解释')
        self.assertNotIn(preliminary['question'], answer)
        self.assertIn(final['question'], answer)
        self.assertEqual(self.backend.payloads[-1]['previous_discussion_focus'][0]['question'], self.question['question'])
        self.assertEqual(self.store.get('problem_checkpoint')['discussion_focus'][0]['question'], final['question'])

    def test_old_checkpoint_and_pending_reply_remain_readable(self):
        checkpoint = self.store.get('problem_checkpoint')
        self.assertEqual(previous_focus(checkpoint), [])
        # Old persisted replies lack discussion_focus and are allowed to complete.
        from research_idea.store import digest
        message = append_message(self.store, 'user', '解释就好')
        result = dict(answer='旧版成功答复', updated_pool=[], updated_intent=[],
                      memory_updates=[], reasoning_updates=[], research_requests=[])
        key = digest([checkpoint['checkpoint_id'], checkpoint['revision'], message['id']])
        self.store.set('pending_discussion', dict(key=key, result=result))
        self.assertEqual(discuss(self.controller(), message), '旧版成功答复')
        self.assertEqual(self.backend.payloads, [])
        self.assertEqual(self.store.get('problem_checkpoint')['discussion_focus'], [])


if __name__ == '__main__':
    unittest.main()
