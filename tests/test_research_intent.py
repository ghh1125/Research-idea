"""Workflow invariants with varied research situations, not keyword detectors."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest

from research_idea.backend_types import BackendResult
from research_idea.config import DEFAULTS
from research_idea.controller import Controller, OutputValidationError
from research_idea.conversation import append_message
from research_idea.demo import DemoBackend
from research_idea.problem_dialogue import discuss
from research_idea.research_intent import validate_intent, validate_formulation
from research_idea.store import Store


def read_payload(task):
    return json.loads(task.prompt.split('BEGIN_RESEARCH_DATA\n')[1].split('\nEND_RESEARCH_DATA')[0])


def intent(topic, mode='refine', relation='joint'):
    source = [dict(message_id='topic', quote=topic)]
    return dict(mode=mode, goal=topic, goal_sources=source, interpretation='先理解这些需要怎样一起影响原目标。',
        concerns=[dict(id='a', statement='第一个需要', kind='need', sources=source),
                  dict(id='b', statement='第二个假设', kind='hypothesis', sources=source)],
        relationships=[dict(from_id='a', to_id='b', relation=relation, reason='当前用户的整体研究主张。')])


class Backend(DemoBackend):
    def __init__(self, research_intent, strategy='synthesize'):
        self.intent = research_intent
        self.strategy = strategy
        self.calls = []
        self.correction = None

    def generate(self, task):
        payload = read_payload(task)
        self.calls.append((task.stage, deepcopy(payload)))
        if task.stage == 'interpret_research':
            return BackendResult(deepcopy(self.intent))
        output = super().generate(task).output
        if task.stage == 'map' and payload.get('problem_cases'):
            cases = payload['problem_cases']
            form = output['formulation'][0]
            form['strategy'] = self.strategy
            form['member_ids'] = [c['id'] for c in cases[:2 if self.strategy == 'synthesize' else 1]]
            if self.strategy != 'select':
                form['opportunity']['id'] = 'integrated-question'
                form['opportunity']['question'] = '两个条件怎样共同影响原目标？'
            form['relationship_assessment'] = '相互依赖的需要应当一起解释，不是假定其中一项已经解决。'
            form['scope_reason'] = '研究共同关系比单独改进某一方面更接近用户目标。'
            form['concern_disposition'][1].update(treatment='revised' if self.strategy == 'reframe' else 'central',
                                                reason='已有回应改变了这个假设，但不取消原目标。')
        if task.stage == 'discuss_direction' and self.correction:
            corrected = deepcopy(self.intent)
            corrected['goal'] = self.correction
            corrected['goal_sources'] = [dict(message_id=payload['current_user_message']['id'], quote=self.correction)]
            corrected['mode'] = 'assess'
            output.update(updated_intent=[corrected], answer='改为审视当前问题。')
        return BackendResult(output)


class IntentTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.temp.name))
        self.config = dict(DEFAULTS, backend='demo', auto_search=False, builtin_skills=False,
                           max_calls=80, max_seconds=60, max_candidates=1)

    def tearDown(self):
        self.store.close()
        self.temp.cleanup()

    def run_case(self, topic, mode='refine', relation='joint', strategy='synthesize'):
        self.store.set('topic', topic)
        backend = Backend(intent(topic, mode, relation), strategy)
        Controller(self.store, backend, self.config).run_questions()
        return backend

    def test_linked_concerns_reach_reading_deepening_selection_and_final(self):
        backend = self.run_case('压缩内容应适合接收模型，也要保留内容间的联系。')
        stages = [s for s, _ in backend.calls]
        self.assertLess(stages.index('interpret_research'), stages.index('explore_problems'))
        for stage, payload in backend.calls:
            if stage in ('explore_problems', 'plan_problem_reading', 'deepen_problem', 'map', 'frame_question'):
                self.assertEqual(len(payload['research_intent']['concerns']), 2)
        model = self.store.get('problem_model')
        self.assertEqual(model['selected_problems'][0]['opportunity_id'], 'integrated-question')
        self.assertEqual(len(model['opportunities']), 3)  # Both analyses remain, plus synthesis.
        frame = next(p for s, p in backend.calls if s == 'frame_question')
        self.assertEqual(frame['argument_handoff'][0]['formulation'][0]['member_ids'], ['conflict', 'order'])
        self.assertEqual(frame['discussion_handoff']['research_intent']['mode'], 'refine')
        self.assertEqual(len(self.store.get('research_intent_history')), 1)
        before = len(backend.calls)
        Controller(self.store, backend, self.config).run_questions()
        self.assertEqual(len(backend.calls), before)

    def test_independent_directions_can_select_without_forced_synthesis(self):
        self.run_case('比较模型校准与训练数据去重两个研究方向。', 'explore', 'alternative', 'select')
        model = self.store.get('problem_model')
        self.assertEqual(len(model['opportunities']), 2)
        self.assertEqual(model['selected_problems'][0]['opportunity_id'], 'conflict')

    def test_rejected_premise_can_reframe_without_rejecting_goal(self):
        self.run_case('希望多智能体有效协作，猜测更多共享消息总能帮助协作。', 'assess', 'depends_on', 'reframe')
        model = self.store.get('problem_model')
        self.assertEqual(model['formulation'][0]['concern_disposition'][1]['treatment'], 'revised')
        self.assertEqual(model['research_intent']['concerns'][1]['kind'], 'hypothesis')
        self.assertEqual(model['opportunities'][-1]['id'], 'integrated-question')

    def test_source_validation_and_missing_concern_are_structural_not_semantic(self):
        topic = '研究长期记忆与知识变化之间的关系'
        value = intent(topic)
        validate_intent(value, {'topic': topic})
        bad = deepcopy(value)
        bad['goal_sources'][0]['quote'] = '助手推断的新目标'
        with self.assertRaises(ValueError):
            validate_intent(bad, {'topic': topic})
        backend = self.run_case(topic)
        model = self.store.get('problem_model')
        form = deepcopy(model['formulation'])
        form[0]['concern_disposition'].pop()
        with self.assertRaisesRegex(ValueError, 'every recorded user concern'):
            validate_formulation(form, model['opportunities'][:-1], value)

    def test_dialogue_updates_intent_atomically_and_survives_reopen(self):
        topic = '让机器人在变化环境下持续适应，并保留已有技能。'
        self.store.set('topic', topic)
        backend = Backend(intent(topic))
        Controller(self.store, backend, self.config).run_questions(interactive=True)
        backend.correction = '先审视保留已有技能是否真的妨碍适应。'
        message = append_message(self.store, 'user', backend.correction)
        discuss(Controller(self.store, backend, self.config), message)
        self.assertEqual(len(self.store.get('research_intent_history')), 2)
        self.assertEqual(self.store.get('research_intent_history')[-1]['source_message_id'], message['id'])
        self.store.close()
        self.store = Store(Path(self.temp.name))
        Controller(self.store, backend, self.config).run_questions(continue_problem=True)
        deepest = [p for s, p in backend.calls if s == 'deepen_problem'][-1]
        self.assertEqual(deepest['research_intent']['goal'], backend.correction)
        self.assertEqual(deepest['research_intent']['mode'], 'assess')
        self.assertEqual([s for s, _ in backend.calls].count('interpret_research'), 1)

    def test_invalid_discussion_does_not_commit_a_partial_intent(self):
        topic = '研究工具反馈与长期记忆怎样共同支持适应。'
        self.store.set('topic', topic)
        backend = Backend(intent(topic))
        Controller(self.store, backend, self.config).run_questions(interactive=True)
        saved = deepcopy(self.store.get('research_intent'))
        checkpoint = deepcopy(self.store.get('problem_checkpoint'))
        original = backend.generate
        def invalid(task):
            result = original(task)
            if task.stage == 'discuss_direction':
                bad = deepcopy(saved)
                bad['goal_sources'][0]['quote'] = '用户从未说过的新目标'
                result.output['updated_intent'] = [bad]
            return result
        backend.generate = invalid
        with self.assertRaisesRegex(OutputValidationError, 'Intent sources'):
            discuss(Controller(self.store, backend, self.config), append_message(self.store, 'user', '解释一下两者的关系'))
        self.assertEqual(self.store.get('research_intent'), saved)
        self.assertEqual(self.store.get('problem_checkpoint'), checkpoint)
        self.assertEqual(len(self.store.get('research_intent_history')), 1)

    def test_revised_intent_changes_search_payload_and_cache(self):
        topic = '研究多智能体协作'
        self.store.set('topic', topic)
        value = intent(topic)
        self.store.set('research_intent', value)
        backend = Backend(value)
        controller = Controller(self.store, backend, self.config)
        controller.plan_search()
        value['goal'] = '研究多智能体分歧与信息共享的关系'
        self.store.set('research_intent', value)
        controller.plan_search()
        plans = [p for stage, p in backend.calls if stage == 'plan_search']
        self.assertEqual(len(plans), 2)
        self.assertNotEqual(plans[0]['research_intent']['goal'], plans[1]['research_intent']['goal'])
        controller.plan_search()
        self.assertEqual(len([s for s, _ in backend.calls if s == 'plan_search']), 2)

    def test_research_about_concise_model_answers_is_not_a_style_request(self):
        topic = '研究模型为什么难以给出简短又完整的回答。'
        value = intent(topic)
        validate_intent(value, {'topic': topic})

    def test_temporary_reply_preference_is_not_research_intent(self):
        value = intent('本次回答只用三句话。')
        with self.assertRaisesRegex(ValueError, 'Temporary presentation'):
            validate_intent(value, {'topic': '本次回答只用三句话。'})

    def test_broad_input_does_not_require_inventing_specific_concerns(self):
        topic = '探索递归自我改进的重要研究问题'
        value = intent(topic, 'explore')
        value.update(concerns=[], relationships=[])
        validate_intent(value, {'topic': topic})
        self.store.set('topic', topic)
        backend = Backend(value, 'select')
        # Demo's empty-concern output is a valid broad-input formulation.
        backend.generate = lambda task: (BackendResult(value) if task.stage == 'interpret_research'
                                        else DemoBackend().generate(task))
        Controller(self.store, backend, self.config).run_questions()
        self.assertEqual(self.store.get('research_intent')['concerns'], [])
