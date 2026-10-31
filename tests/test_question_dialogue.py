"""Discussion changes the saved research, including after source-work failures."""
from copy import deepcopy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from research_idea.backend_types import BackendResult
from research_idea.config import DEFAULTS
from research_idea.controller import Controller
from research_idea.conversation import append_message, revised_memory
from research_idea.demo import DemoBackend
from research_idea.problem_dialogue import discuss, source_key
from research_idea.store import Store
import json


def payload(task):
    return json.loads(task.prompt.split('BEGIN_RESEARCH_DATA\n')[1].split('\nEND_RESEARCH_DATA')[0])


class Backend(DemoBackend):
    def __init__(self):
        self.answer = None
        self.calls = []

    def generate(self, task):
        self.calls.append(task.stage)
        if task.stage in {'discuss_direction', 'discuss_question'} and self.answer:
            return BackendResult({'updated_intent': [], 'reasoning_updates': [], **self.answer(payload(task))})
        return super().generate(task)


class QuestionDialogueTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.temp.name))
        self.store.set('topic', '多agent如何共享信息而不遗漏关键关系')
        self.config = dict(DEFAULTS, backend='demo', auto_search=False, builtin_skills=False,
                           max_calls=100, max_seconds=120, max_candidates=1)
        self.backend = Backend()
        self.controller().run_questions(interactive=True)

    def tearDown(self):
        self.store.close()
        self.temp.cleanup()

    def controller(self):
        return Controller(self.store, self.backend, self.config)

    def test_direction_correction_reaches_deepening_and_final_claim(self):
        def answer(data):
            pool = deepcopy(data['problem_model'])
            pool['problem_seeds'] = pool['problem_seeds'][:1]
            pool['problem_seeds'][0]['question'] = '团队为何无法利用分散的信息？'
            return dict(answer='我们把问题聚焦到分散信息。', updated_pool=[pool], research_requests=[],
                        memory_updates=[dict(action='add', entry_id='', scope='research', content='聚焦分散信息',
                            source_message_id=data['current_user_message']['id'])])
        self.backend.answer = answer
        discuss(self.controller(), append_message(self.store, 'user', '聚焦分散信息，不做实验计划'))
        self.controller().run_questions(interactive=True, continue_problem=True)
        self.assertEqual(len(self.store.get('problem_model')['opportunities']), 1)
        self.controller().run_questions(interactive=True, continue_problem=True)
        self.assertEqual(self.store.get('status'), 'completed')
        self.assertFalse({'propose', 'develop', 'review'} & set(self.backend.calls))

    def test_failed_followup_keeps_own_sources_resumable_and_memory_atomic(self):
        msg = append_message(self.store, 'user', '请查清共享信息的条件，先不要写算法')
        old = dict(action='add', entry_id='', scope='research', content='旧理解', source_message_id=msg['id'])
        self.store.set('conversation_memory', revised_memory(self.store, [old], {msg['id']}))
        memory_id = self.store.get('conversation_memory')[0]['id']
        self.store.set('pending_chat_message', msg['id'])
        previous_notice = deepcopy(self.store.get('last_turn_changes'))
        fail = [True]
        def answer(data):
            if data['source_work_done'] and fail[0]:
                raise RuntimeError('followup interrupted')
            content = '最终理解' if data['source_work_done'] else '初步理解'
            return dict(answer=content, updated_pool=[],
                research_requests=[] if data['source_work_done'] else [dict(
                    question='已有共享怎样保留条件？', query='multi agent shared information', paper_ids=[])],
                memory_updates=[dict(action='replace', entry_id=memory_id, scope='research', content=content,
                                     source_message_id=msg['id'])])
        self.backend.answer = answer
        def acquire(controller, requests, key):
            controller.store.put('papers', dict(id='new-paper', title='New', content_kind='notes', text='New reading.'))
            return {'performed': True, 'search_status': 'completed', 'readings': []}
        with patch('research_idea.discussion_sources.research_requests', side_effect=acquire):
            with self.assertRaisesRegex(RuntimeError, 'interrupted'):
                discuss(self.controller(), msg)
            self.assertEqual(self.store.get('conversation_memory')[0]['content'], '旧理解')
            self.assertEqual(self.store.get('problem_checkpoint')['revision'], 1)
            self.assertEqual(self.store.get('last_turn_changes'), previous_notice)
            self.assertEqual(self.store.get('problem_checkpoint')['source_key'], source_key(self.controller()))
            fail[0] = False
            discuss(self.controller(), msg)
        active = [m for m in self.store.get('conversation_memory') if m['active']]
        self.assertEqual([m['content'] for m in active], ['最终理解'])
        self.assertEqual(self.store.get('problem_checkpoint')['revision'], 2)
        self.assertIsNone(self.store.get('pending_chat_message'))
        self.assertIsNone(self.store.get('pending_discussion'))
        self.assertEqual(self.backend.calls.count('discuss_direction'), 3)
        self.assertIn('最终理解', str(self.store.get('last_turn_changes')['changed']))
        self.assertNotIn('初步理解', str(self.store.get('last_turn_changes')['changed']))

    def test_early_user_reference_is_allowed_after_many_turns(self):
        first = append_message(self.store, 'user', '研究重点是环境交互，不要限定游戏')
        for i in range(20):
            append_message(self.store, 'user', f'一般讨论{i}')
        self.store.set('memory_reviewed_messages', [m['id'] for m in self.store.get('chat_messages')])
        message = append_message(self.store, 'user', '还记得环境交互不要限定游戏吗？')
        def answer(data):
            self.assertIn(first['id'], [m['id'] for m in data['retrieved_history']])
            return dict(answer='保留原范围。', updated_pool=[], research_requests=[], memory_updates=[
                dict(action='add', entry_id='', scope='research', content='环境交互，不限游戏', source_message_id=first['id'])])
        self.backend.answer = answer
        discuss(self.controller(), message)
        self.assertEqual(self.store.get('conversation_memory')[0]['source_message_id'], first['id'])

    def test_saved_change_notice_does_not_trust_verbal_claims(self):
        self.controller().run_questions(interactive=True, continue_problem=True)
        previous = deepcopy(self.store.get('problem_checkpoint')['current'])
        self.backend.answer = lambda data: dict(answer='已经修改了背景和优先问题。',
            updated_problems=[], updated_background=[], selected_problems=[], memory_updates=[], research_requests=[])
        message = append_message(self.store, 'user', '请解释刚才的判断')
        discuss(self.controller(), message)
        self.assertEqual(self.store.get('problem_checkpoint')['current'], previous)
        changes = self.store.get('last_turn_changes')
        self.assertEqual(changes['changed'], [])
        self.assertEqual(changes['source_message_id'], message['id'])
        from research_idea.discussion_changes import changes_text
        self.assertIn('未修改', changes_text(changes))

    def test_question_selection_updates_following_brief(self):
        self.controller().run_questions(interactive=True, continue_problem=True)
        msg = append_message(self.store, 'user', '优先看第二个问题')
        def answer(data):
            selected = data['problem_model']['opportunities'][1]
            return dict(answer='把第二个问题作为当前重点。', updated_problems=[], research_requests=[], updated_background=[],
                selected_problems=[dict(opportunity_id=selected['id'], selection_reason='新的研究重点')], memory_updates=[])
        self.backend.answer = answer
        discuss(self.controller(), msg)
        changes = self.store.get('last_turn_changes')
        self.assertIn('优先问题调整', changes['changed'][0])
        self.assertEqual(changes['focus'], self.store.get('problem_model')['opportunities'][1]['question'])
        self.controller().run_questions(interactive=True, continue_problem=True)
        self.assertIn('新的研究重点', self.store.get('research_brief')['why_priority'])

    def test_background_correction_changes_saved_version_and_final_context(self):
        self.controller().run_questions(interactive=True, continue_problem=True)
        message = append_message(self.store, 'user', '背景不是增加处理速度，要理解成员怎样形成新的认识')
        def answer(data):
            frame = deepcopy(data['problem_model']['research_frame'])
            frame['literature_logic'] = '关心共同形成新认识，而不是处理速度。'
            return dict(answer='已修订背景和主要方法的梳理。', updated_problems=[], selected_problems=[],
                memory_updates=[], research_requests=[], updated_background=[dict(research_frame=frame,
                    approach_landscape=[dict(name='现有思路', principle='合并互补材料',
                        achieved_progress='已能利用互补信息', paper_ids=[], evidence_ids=[])])])
        self.backend.answer = answer
        discuss(self.controller(), message)
        working = self.store.get('problem_checkpoint')['current']
        self.assertIn('共同形成新认识', working['research_frame']['literature_logic'])
        self.assertEqual(working['approach_landscape'][0]['principle'], '合并互补材料')
        changes = self.store.get('last_turn_changes')['changed']
        self.assertIn('已更新：背景与研究范围。', changes)
        self.assertIn('已更新：现有方法梳理。', changes)
        self.controller().run_questions(interactive=True, continue_problem=True)
        self.assertIn('共同形成新认识', self.store.get('research_brief')['background'])
        self.assertIn('已能利用互补信息', self.store.get('research_brief')['existing_methods'])


if __name__ == '__main__':
    unittest.main()
