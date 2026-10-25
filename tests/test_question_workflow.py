"""The question workflow pauses twice and never enters method construction."""
from copy import deepcopy
from pathlib import Path
import json
import tempfile
import time
import unittest
from unittest.mock import patch

from research_idea.controller import BudgetExhausted
from research_idea.conversation import append_message, discussion_key
from research_idea.question_workflow import run_questions
from research_idea.store import Store, digest, now


WAITING = {'direction': 'awaiting_direction_discussion', 'problem': 'awaiting_problem_discussion'}
POOL = {'background_logic': '有限资源下仍希望提高跨任务能力。', 'approach_landscape': [],
        'problem_seeds': [{'id': 'p1', 'question': '为什么现有进展仍不能满足目标？',
            'entry_reason': '已有方法的目标与实际使用要求有差距。',
            'problem_origin': 'unresolved_need', 'research_route_ids': []}]}
PROBLEM = {'research_frame': {'user_goal': '提高跨任务能力'},
           'opportunities': [{'id': 'p1', 'question': '什么阻碍了能力迁移？',
                'prior_art_delta': '已有方法提高已见任务表现。',
                'bottleneck_hypothesis': '共同规律没有在变化条件下持续发挥作用。',
                'derivation': '真实使用需要跨条件迁移。', 'why_it_matters': '决定能力能否复用。',
                'research_need': '理解迁移受阻的原因。', 'evidence_ids': ['e1'],
                'closest_work_ids': ['paper1']}],
           'selected_problems': [{'opportunity_id': 'p1', 'selection_reason': '直接关系到原始目标。'}]}
BRIEF = {'title': '有限资源下的能力迁移', 'background': '希望提高跨任务能力。',
         'existing_methods': '已有方法改善已见任务表现。', 'problem': '换条件后能力难以延续。',
         'motivation': '研究能力迁移受阻的原因。', 'research_claim': '考察条件变化如何影响迁移。',
         'why_priority': '它直接关系到能力的实际使用。',
         'closest_work_ids': ['paper1'], 'evidence_ids': ['e1']}


def source_key(controller):
    return digest([controller.store.get('source_revision', 0), controller.store.get('topic')])


def open_checkpoint(controller, data, kind='problem'):
    store = controller.store
    old = store.get('problem_checkpoint')
    if old:
        store.event('problem_checkpoint_archived', old)
    checkpoint = {'kind': kind, 'checkpoint_id': f'{kind}-{now()}', 'state': 'discussing',
        'revision': 1, 'confirmed_revision': None, 'source_key': source_key(controller),
        'created_at': now(), 'current': deepcopy(data), 'original': deepcopy(data), 'revisions': []}
    store.set_many({'problem_checkpoint': checkpoint, 'status': WAITING[kind]})
    return checkpoint


class FakeController:
    def __init__(self, store, calls):
        self.store, self.calls = store, calls
        self.started = time.monotonic()
        self.previous_elapsed = store.get('elapsed_s', 0)
        self.skill_key = 'skills'
        self.config = {'max_candidates': 1}
        self.failure = None
        self.add_source_before_failure = False
        self.last_payload = None

    def progress(self, text):
        pass

    def user_notes(self):
        return [m['content'] for m in self.store.get('conversation_memory', []) if m['active']]

    def initial_search(self):
        self.calls.append('initial_search')

    def initial_paper_ids(self):
        return ['paper1']

    def retrieve_full_texts(self, ids):
        self.calls.append('retrieve_full_texts')

    def read_papers(self, ids):
        self.calls.append('read_papers')

    def audit_papers(self, ids):
        self.calls.append('audit_papers')

    def ideation_context(self):
        return {'topic': self.store.get('topic'), 'papers': [{'id': 'paper1'}],
                'evidence': [{'id': 'e1'}], 'discovery_plan': {'research_routes': []}}

    def discover_problems(self, pool=None):
        self.calls.append('discover_problems')
        self.last_payload = deepcopy(pool)
        if self.add_source_before_failure:
            self.store.set('source_revision', self.store.get('source_revision', 0) + 1)
        if self.failure:
            raise self.failure
        return deepcopy(PROBLEM)

    def task(self, stage, payload, checker=None):
        self.calls.append(stage)
        if stage == 'frame_question' and self.failure:
            raise self.failure
        self.last_payload = deepcopy(payload)
        value = deepcopy(POOL if stage == 'explore_problems' else BRIEF)
        if checker:
            checker(value)
        return value


class QuestionWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name)
        self.store = Store(self.path)
        self.store.set('topic', '一个通用研究方向')
        self.calls = []
        patches = [patch('research_idea.problem_dialogue.WAITING_BY_KIND', WAITING, create=True),
                   patch('research_idea.problem_dialogue.source_key', source_key),
                   patch('research_idea.problem_dialogue.open_checkpoint', open_checkpoint)]
        for patcher in patches:
            patcher.start()
            self.addCleanup(patcher.stop)

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    def controller(self):
        return FakeController(self.store, self.calls)

    def reopen(self):
        self.store.close()
        self.store = Store(self.path)

    def pause_direction(self):
        run_questions(self.controller(), interactive=True)
        self.assertEqual(self.store.get('status'), WAITING['direction'])

    def pause_problem(self):
        self.pause_direction()
        run_questions(self.controller(), interactive=True, continue_problem=True)
        self.assertEqual(self.store.get('status'), WAITING['problem'])

    def test_two_durable_discussions_then_research_claim(self):
        self.pause_direction()
        self.assertNotIn('discover_problems', self.calls)
        checkpoint = self.store.get('problem_checkpoint')
        checkpoint['current']['problem_seeds'][0]['question'] = '用户纠正后的方向'
        checkpoint['revision'] = 2
        self.store.set('problem_checkpoint', checkpoint)
        self.reopen()
        controller = self.controller()
        run_questions(controller, interactive=True, continue_problem=True)
        self.assertEqual(controller.last_payload['problem_seeds'][0]['question'], '用户纠正后的方向')
        self.assertEqual(self.store.get('status'), WAITING['problem'])
        self.assertNotIn('frame_question', self.calls)
        self.reopen()
        controller = self.controller()
        run_questions(controller, interactive=True, continue_problem=True)
        self.assertEqual(self.store.get('status'), 'completed')
        self.assertEqual(self.store.get('research_brief'), BRIEF)
        handoff = controller.last_payload['discussion_handoff']
        self.assertEqual(handoff['stage_confirmations']['direction']['confirmed_revision'], 2)
        self.assertEqual(handoff['stage_confirmations']['problem']['confirmed_by'], '/continue')
        self.assertEqual(controller.last_payload['argument_handoff'][0]['opportunity_id'], 'p1')
        self.assertEqual(self.calls.count('explore_problems'), 1)
        self.assertFalse({'propose', 'develop', 'design_transfer'} & set(self.calls))

    def test_batch_finishes_without_method_and_keeps_old_candidates(self):
        self.store.put('candidates', {'id': 'old', 'proposal': {'title': '旧技术方案'}})
        run_questions(self.controller())
        self.assertEqual(self.store.get('workflow'), 'question')
        self.assertEqual(self.store.get('status'), 'completed')
        self.assertEqual(self.store.rows('candidates')[0]['id'], 'old')
        self.assertEqual(self.calls, ['initial_search', 'retrieve_full_texts', 'read_papers',
            'audit_papers', 'explore_problems', 'discover_problems', 'frame_question'])
        before = list(self.calls)
        run_questions(self.controller())
        self.assertEqual(self.calls, before)

    def test_long_discussion_versions_stay_in_storage_not_frame_payload(self):
        self.pause_problem()
        old_history = '旧讨论逐字内容，不应重复注入' * 4000
        old_landscape = '旧方向完整文献地图，不应重复注入' * 4000
        cycle = self.store.get('question_cycle')
        direction = cycle['confirmations']['direction']
        direction['revisions'] = [{'revision': 1, 'answer': old_history}]
        direction['current']['background_logic'] = old_landscape
        self.store.set('question_cycle', cycle)
        checkpoint = self.store.get('problem_checkpoint')
        checkpoint['revisions'] = [{'revision': 1, 'answer': old_history}]
        self.store.set('problem_checkpoint', checkpoint)

        controller = self.controller()
        run_questions(controller, interactive=True, continue_problem=True)
        payload = controller.last_payload
        rendered = json.dumps(payload, ensure_ascii=False)
        self.assertNotIn('旧讨论逐字内容', rendered)
        self.assertNotIn('旧方向完整文献地图', rendered)
        confirmations = payload['discussion_handoff']['stage_confirmations']
        self.assertEqual(confirmations['direction']['directions'], [
            {'id': seed['id'], 'question': seed['question']} for seed in POOL['problem_seeds']])
        self.assertEqual(confirmations['problem']['selected_problems'], PROBLEM['selected_problems'])
        self.assertEqual(payload['problem_model'], PROBLEM)
        saved = self.store.get('question_brief_provenance')['stage_confirmations']
        self.assertEqual(saved['direction']['current']['background_logic'], old_landscape)
        self.assertEqual(saved['direction']['revisions'][0]['answer'], old_history)
        self.assertEqual(saved['problem']['revisions'][0]['answer'], old_history)
        self.assertEqual(self.store.get('question_cycle')['confirmations'], saved)

    def test_run_cannot_bypass_saved_discussion_or_spend_time(self):
        self.pause_direction()
        checkpoint = self.store.get('problem_checkpoint')
        elapsed = self.store.get('elapsed_s')
        before = list(self.calls)
        self.reopen()
        run_questions(self.controller())
        self.assertEqual(self.calls, before)
        self.assertEqual(self.store.get('problem_checkpoint'), checkpoint)
        self.assertEqual(self.store.get('elapsed_s'), elapsed)

    def test_deepening_failure_recovers_after_its_own_source_additions(self):
        self.pause_direction()
        controller = self.controller()
        controller.failure = RuntimeError('interrupted deepening')
        controller.add_source_before_failure = True
        with self.assertRaisesRegex(RuntimeError, 'interrupted deepening'):
            run_questions(controller, interactive=True, continue_problem=True)
        checkpoint = self.store.get('problem_checkpoint')
        self.assertEqual(checkpoint['state'], 'confirmed')
        self.assertEqual(checkpoint['source_key'], source_key(controller))
        confirmed_at = checkpoint['confirmed_at']
        self.reopen()
        run_questions(self.controller())  # /run need not know the saved interaction mode.
        self.assertEqual(self.store.get('status'), WAITING['problem'])
        self.assertEqual(self.calls.count('explore_problems'), 1)
        self.assertEqual(self.store.get('question_cycle')['confirmations']['direction']['confirmed_at'], confirmed_at)

    def test_frame_failure_preserves_confirmation_and_resumes(self):
        self.pause_problem()
        controller = self.controller()
        controller.failure = RuntimeError('frame failed')
        with self.assertRaisesRegex(RuntimeError, 'frame failed'):
            run_questions(controller, interactive=True, continue_problem=True)
        checkpoint = self.store.get('problem_checkpoint')
        self.assertEqual(checkpoint['state'], 'confirmed')
        confirmed_at = checkpoint['confirmed_at']
        self.reopen()
        run_questions(self.controller(), interactive=True, continue_problem=True)
        self.assertEqual(self.store.get('status'), 'completed')
        self.assertEqual(self.store.get('problem_checkpoint')['confirmed_at'], confirmed_at)
        self.assertEqual(self.calls.count('discover_problems'), 1)

    def test_source_change_reopens_directions_and_archives_old_brief(self):
        run_questions(self.controller())
        user = append_message(self.store, 'user', '保留跨任务研究目标')
        memory = [{'id': 'm1', 'scope': 'research', 'active': True,
                   'source_message_id': user['id'], 'content': '保留跨任务研究目标'}]
        self.store.set('conversation_memory', memory)
        self.store.set('source_revision', 1)
        with self.assertRaisesRegex(ValueError, '已变化'):
            run_questions(self.controller(), continue_problem=True)
        run_questions(self.controller(), interactive=True)
        self.assertEqual(self.store.get('status'), WAITING['direction'])
        self.assertIsNone(self.store.get('research_brief'))
        self.assertEqual(self.store.get('conversation_memory'), memory)
        self.assertTrue(any(e['kind'] == 'research_brief_archived' for e in self.store.recent_events()))

    def test_source_invalidation_binds_legacy_temporary_memory_to_old_discussion(self):
        self.pause_direction()
        old_key = discussion_key(self.store.get('problem_checkpoint'))
        self.store.set('conversation_memory', [{'id': 'temporary', 'active': True,
            'scope': 'discussion', 'content': '旧讨论期间暂缓'}])
        self.store.set('source_revision', 1)
        run_questions(self.controller())
        self.assertEqual(self.store.get('status'), WAITING['direction'])
        memory = self.store.get('conversation_memory')[0]
        self.assertEqual(memory['discussion_key'], old_key)
        self.assertNotEqual(memory['discussion_key'], discussion_key(self.store.get('problem_checkpoint')))

    def test_changed_model_effort_or_skill_reframes_without_repeating_research(self):
        run_questions(self.controller())
        confirmation = self.store.get('problem_checkpoint')['confirmed_at']
        for model, effort, skill in [('different-model', 'high', 'skills'),
                                      ('different-model', 'xhigh', 'skills'),
                                      ('different-model', 'xhigh', 'revised-skills')]:
            controller = self.controller()
            controller.config.update(model=model, reasoning_effort=effort)
            controller.skill_key = skill
            run_questions(controller)
        self.assertEqual(self.calls.count('frame_question'), 4)
        self.assertEqual(self.calls.count('initial_search'), 1)
        self.assertEqual(self.calls.count('discover_problems'), 1)
        self.assertEqual(self.store.get('problem_checkpoint')['confirmed_at'], confirmation)

    def test_legacy_checkpoint_continues_directly_to_research_claim(self):
        checkpoint = open_checkpoint(self.controller(), PROBLEM)
        checkpoint.pop('kind')
        self.store.set('problem_checkpoint', checkpoint)
        run_questions(self.controller(), interactive=True, continue_problem=True)
        self.assertEqual(self.calls, ['frame_question'])
        self.assertEqual(self.store.get('status'), 'completed')
        self.assertEqual(self.store.get('question_brief_provenance')['confirmed_by'], '/continue')

    def test_pending_message_cannot_be_skipped(self):
        self.pause_direction()
        message = append_message(self.store, 'user', '先重新考虑研究范围')
        self.store.set('pending_chat_message', message['id'])
        with self.assertRaisesRegex(ValueError, '尚未成功处理'):
            run_questions(self.controller(), continue_problem=True)
        self.assertEqual(self.store.get('problem_checkpoint')['state'], 'discussing')

    def test_discussion_source_refresh_keeps_prior_stage_decisions(self):
        self.pause_problem()
        direction = self.store.get('question_cycle')['confirmations']['direction']
        self.store.set('source_revision', 1)
        checkpoint = self.store.get('problem_checkpoint')
        checkpoint.update(source_key=source_key(self.controller()), revision=2)
        self.store.set('problem_checkpoint', checkpoint)
        run_questions(self.controller(), interactive=True, continue_problem=True)
        confirmations = self.store.get('question_brief_provenance')['stage_confirmations']
        self.assertEqual(confirmations['direction'], direction)
        self.assertEqual(confirmations['problem']['confirmed_revision'], 2)
        self.assertEqual(self.calls.count('initial_search'), 1)

    def test_continue_only_retires_current_discussion_memory(self):
        self.pause_direction()
        current = discussion_key(self.store.get('problem_checkpoint'))
        memory = [{'id': 'current', 'active': True, 'scope': 'discussion',
                   'discussion_key': current, 'content': '先讨论方向'},
                  {'id': 'other', 'active': True, 'scope': 'discussion',
                   'discussion_key': 'problem:other', 'content': '另一个讨论的要求'},
                  {'id': 'ongoing', 'active': True, 'scope': 'research', 'content': '不要缩小目标'}]
        self.store.set('conversation_memory', memory)
        run_questions(self.controller(), interactive=True, continue_problem=True)
        saved = self.store.get('conversation_memory')
        self.assertFalse(saved[0]['active'])
        self.assertTrue(saved[1]['active'])
        self.assertTrue(saved[2]['active'])

    def test_budget_and_interrupt_leave_confirmed_work_resumable(self):
        self.pause_problem()
        for failure, status in [(BudgetExhausted('budget'), 'budget_exhausted'),
                                (KeyboardInterrupt(), 'interrupted')]:
            controller = self.controller()
            controller.failure = failure
            self.store.begin_task('abandoned', 'frame_question')
            with self.assertRaises(type(failure)):
                run_questions(controller, interactive=True, continue_problem=True)
            self.assertEqual(self.store.get('status'), status)
            self.assertEqual(self.store.get('problem_checkpoint')['state'], 'confirmed')
            self.assertEqual(self.store.task('abandoned')['status'], 'failed')
            self.assertGreaterEqual(self.store.get('elapsed_s'), 0)
        run_questions(self.controller(), interactive=True)
        self.assertEqual(self.store.get('status'), 'completed')


class QuestionWorkflowIntegrationTests(unittest.TestCase):
    def test_real_controller_and_checkpoint_interfaces(self):
        from research_idea.backend_types import BackendResult
        from research_idea.config import DEFAULTS
        from research_idea.controller import Controller
        from research_idea.demo import DemoBackend, DEMO_PAPERS

        class RecordingBackend(DemoBackend):
            def __init__(self):
                self.stages = []

            def generate(self, task):
                self.stages.append(task.stage)
                if task.stage == 'frame_question':
                    data = json.loads(task.prompt.split('BEGIN_RESEARCH_DATA\n')[1].split('\nEND_RESEARCH_DATA')[0])
                    output = deepcopy(BRIEF)
                    output['closest_work_ids'] = [p['id'] for p in data['papers']]
                    output['evidence_ids'] = [e['id'] for e in data['evidence']]
                    return BackendResult(output)
                return super().generate(task)

        with tempfile.TemporaryDirectory() as directory:
            store = Store(Path(directory))
            self.addCleanup(store.close)
            store.set('topic', '一个通用研究方向')
            for paper in DEMO_PAPERS:
                store.put('papers', deepcopy(paper))
            backend = RecordingBackend()
            config = dict(DEFAULTS, backend='demo', builtin_skills=False, auto_search=False,
                          deep_reading=False, max_calls=80, max_seconds=60)
            for status, continuing in [(WAITING['direction'], False),
                                        (WAITING['problem'], True), ('completed', True)]:
                Controller(store, backend, config).run_questions(interactive=True, continue_problem=continuing)
                self.assertEqual(store.get('status'), status)
            self.assertEqual(backend.stages.count('explore_problems'), 1)
            self.assertEqual(backend.stages.count('map'), 1)
            self.assertEqual(backend.stages.count('frame_question'), 1)
            self.assertFalse({'propose', 'develop', 'design_transfer'} & set(backend.stages))
            self.assertTrue(store.get('research_brief')['evidence_ids'])


if __name__ == '__main__':
    unittest.main()
