"""Behavioral acceptance tests for a constructive, readable ideation workflow."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from research_idea.backend_types import BackendError, BackendResult
from research_idea.chat import Chat, fragments
from research_idea.config import DEFAULTS, write_config
from research_idea.controller import Controller, BudgetExhausted
from research_idea.demo import DemoBackend, DEMO_PAPERS
from research_idea.motivation import assess_motivation
from research_idea.presentation import activity_summary, idea_markdown, error_summary
from research_idea.prompts import stage_version
from research_idea.report import export_report
from research_idea.store import Store


class RecordingBackend(DemoBackend):
    def __init__(self, change=None):
        self.calls, self.change = [], change

    def generate(self, task):
        self.calls.append(task)
        result = super().generate(task)
        if self.change:
            self.change(task, result.output)
        return result


class IdeaWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.project = Path(self.temp.name)
        self.store = Store(self.project)
        self.store.set('topic', '如何设计帮助 agent 发现新规则的环境')
        self.config = dict(DEFAULTS, backend='demo', auto_search=False, builtin_skills=False,
                           max_candidates=1, max_rounds=2, max_seconds=60)
        write_config(self.project, self.config)

    def tearDown(self):
        self.store.close()
        self.temp.cleanup()

    def run_flow(self, backend=None):
        backend = backend or RecordingBackend()
        Controller(self.store, backend, self.config).run()
        return self.store.rows('candidates')[0], backend

    def test_sparse_literature_still_delivers_a_hypothesis_and_real_method_plan(self):
        candidate, backend = self.run_flow()
        self.assertEqual(self.store.get('status'), 'completed')
        self.assertEqual(candidate['spec']['motivation']['basis'], 'research_hypothesis')
        self.assertEqual(candidate['spec']['motivation']['evidence_ids'], [])
        self.assertEqual(candidate['empirical_status'], 'untested')
        self.assertIn('refine', [task.stage for task in backend.calls])
        response = candidate['spec']['review_responses'][0]
        self.assertEqual(response['issue'], candidate['versions'][0]['review']['issues'][0]['issue'])
        self.assertEqual(response['decision'], 'adopt')
        self.assertIn(response['change'], candidate['spec']['method']['changes'])
        self.assertEqual([m['from'] for m in candidate['dialogue']], ['designer', 'reviewer', 'designer', 'reviewer'])
        reviews = [t for t in backend.calls if t.stage == 'review']
        second_review = json.loads(reviews[1].prompt.split('BEGIN_RESEARCH_DATA\n')[1].split('\nEND_RESEARCH_DATA')[0])
        self.assertEqual(second_review['previous_review'], candidate['versions'][0]['review'])
        self.assertEqual(second_review['method_spec']['review_responses'][0]['issue'],
                         second_review['previous_review']['issues'][0]['issue'])
        self.assertIn('previous_revision_record', second_review)
        export_report(self.store)
        front = (self.project / 'outputs/report.md').read_text().split('<details>')[0]
        for label in ('具体方法', '输入 → 输出', '第一步验证', '最简单的对照'):
            self.assertIn(label, front)
        self.assertIn('执行步骤', (self.project / ('outputs/' + candidate['id'] + '.md')).read_text())
        for internal in ('prerequisites_unverified', 'motivation_unresolved', '待补证', 'blocked', 'pending'):
            self.assertNotIn(internal, front)
        self.assertTrue(candidate['spec']['validation']['first_test'])

    def test_observations_still_need_real_references_but_hypotheses_do_not(self):
        candidate, _ = self.run_flow()
        idea = copy.deepcopy(candidate['spec'])
        critique = candidate['review']
        assess_motivation(idea, critique, [])
        idea['motivation']['basis'] = 'source_observation'
        with self.assertRaisesRegex(ValueError, 'supporting evidence'):
            assess_motivation(idea, critique, [])
        idea['motivation']['basis'] = 'research_hypothesis'
        idea['motivation']['evidence_ids'] = ['fabricated']
        with self.assertRaisesRegex(ValueError, 'unknown evidence'):
            assess_motivation(idea, critique, [])

    def test_idea_cannot_defer_named_closest_work_comparison_to_technical_design(self):
        from research_idea.literature import normalize_paper
        self.store.put('papers', normalize_paper(DEMO_PAPERS[0]))
        attempts = []
        def omit_first_comparison(task, output):
            if task.stage == 'propose':
                attempts.append(task)
                if len(attempts) == 1:
                    output['candidates'][0]['positioning'] = []
        candidate, backend = self.run_flow(RecordingBackend(omit_first_comparison))
        self.assertEqual(len(attempts), 2)
        self.assertIn('Compare each named closest work during ideation', attempts[1].prompt)
        self.assertEqual(set(candidate['proposal']['closest_work_ids']),
                         {p['paper_id'] for p in candidate['proposal']['positioning']})
        stages = [task.stage for task in backend.calls]
        self.assertLess(stages.index('propose'), stages.index('develop'))

    def test_idea_includes_a_working_path_before_detailed_design(self):
        attempts = []
        def omit_first_path(task, output):
            if task.stage == 'propose':
                attempts.append(task)
                if len(attempts) == 1:
                    output['candidates'][0]['feasibility_sketch']['available_path'] = ''
        candidate, _ = self.run_flow(RecordingBackend(omit_first_path))
        self.assertEqual(len(attempts), 2)
        sketch = candidate['proposal']['feasibility_sketch']
        self.assertTrue(sketch['inputs'])
        self.assertTrue(sketch['available_path'])
        self.assertTrue(sketch['first_check'])
        summary = activity_summary('propose', {'candidates': [candidate['proposal']]})
        self.assertNotIn(sketch['available_path'], summary)
        self.assertIn(sketch['key_assumption'], summary)
        self.assertIn('Idea → Method', summary)
        self.assertIn(candidate['proposal']['motivation']['background'], summary)

    def test_refinement_must_answer_the_actual_objection_and_repair_is_bounded(self):
        def remove_response(task, output):
            if task.stage == 'refine':
                output['review_responses'] = []
        backend = RecordingBackend(remove_response)
        with self.assertRaisesRegex(BackendError, 'Respond once'):
            self.run_flow(backend)
        self.assertEqual(sum(t.stage == 'refine' for t in backend.calls), 2)
        # The previously useful idea survives a malformed revision.
        self.assertTrue(self.store.rows('candidates')[0]['spec']['validation']['first_test'])

    def test_technical_design_repairs_a_route_without_a_reason_before_review(self):
        attempts = []
        def omit_first_rationale(task, output):
            if task.stage == 'develop':
                attempts.append(task)
                if len(attempts) == 1:
                    output['design_decisions'][0]['rationale'] = ''
        candidate, backend = self.run_flow(RecordingBackend(omit_first_rationale))
        self.assertEqual(len(attempts), 2)
        self.assertIn('design choices with rationale', attempts[1].prompt)
        self.assertTrue(candidate['spec']['design_decisions'][0]['rationale'])
        review = next(t for t in backend.calls if t.stage == 'review')
        payload = json.loads(review.prompt.split('BEGIN_RESEARCH_DATA\n')[1].split('\nEND_RESEARCH_DATA')[0])
        self.assertTrue(payload['method_spec']['design_decisions'][0]['rationale'])

    def test_discussion_notes_reach_the_designer_and_invalidate_old_proposals(self):
        first, backend = self.run_flow()
        before = len(backend.calls)
        self.store.set('chat_messages', [{'role': 'user', 'content': '方法可以沿用，重点是环境如何提供可区分的观察。'},
                                         {'role': 'assistant', 'content': 'Do not treat this answer as a user decision.'}])
        self.run_flow(backend)
        proposal = next(t for t in backend.calls[before:] if t.stage == 'propose')
        payload = json.loads(proposal.prompt.split('BEGIN_RESEARCH_DATA\n')[1].split('\nEND_RESEARCH_DATA')[0])
        self.assertEqual(payload['user_notes'], ['方法可以沿用，重点是环境如何提供可区分的观察。'])

    def test_missing_resources_request_redesign_instead_of_dropping_the_idea(self):
        def unavailable(task, output):
            if task.stage == 'develop':
                output['feasibility']['required_signals'][0]['availability'] = 'unavailable'
            if task.stage == 'review':
                output.update(verdict='continue', issues=[], revision_instructions='')
        candidate, backend = self.run_flow(RecordingBackend(unavailable))
        self.assertIn('refine', [t.stage for t in backend.calls])
        self.assertEqual(candidate['development_complete'], True)
        self.assertEqual(candidate['spec']['feasibility']['required_signals'][0]['availability'], 'unverified')
        self.assertTrue(candidate['spec']['method']['changes'])

    def test_readable_findings_and_narrow_terminal_preserve_navigation_and_budget(self):
        candidate, _ = self.run_flow()
        text = activity_summary('develop', candidate['spec'])
        self.assertIn('第一步验证', text)
        self.assertNotIn('required_signals', text)
        chat = Chat(self.project)
        from prompt_toolkit.utils import get_cwidth
        with patch('research_idea.chat.shutil.get_terminal_size', return_value=__import__('os').terminal_size((52, 24))):
            lines = ''.join(value for _, value in chat.toolbar()).splitlines()
        self.assertEqual(len(lines), 3)
        self.assertTrue(all(get_cwidth(line) <= 52 for line in lines))
        self.assertIn('调用', lines[1])
        self.assertIn('/intro', lines[2])
        rendered = ''.join(value for _, value in fragments('idea', idea_markdown(candidate)))
        self.assertNotIn('**', rendered)
        self.assertIn('具体方法', rendered)

    def test_ideation_update_reuses_unchanged_reader_version(self):
        self.assertEqual(stage_version('read_section'), '8')
        self.assertNotEqual(stage_version('develop'), stage_version('read_section'))

    def test_budget_before_review_keeps_method_and_resume_does_not_regenerate_it(self):
        backend = RecordingBackend()
        with self.assertRaises(BudgetExhausted):
            Controller(self.store, backend, dict(self.config, max_calls=3)).run()
        self.assertTrue(self.store.rows('candidates')[0]['spec']['method']['changes'])
        export_report(self.store)
        self.assertIn('具体方法', (self.project / 'outputs/report.md').read_text())
        Controller(self.store, backend, self.config).run()
        self.assertEqual(sum(t.stage == 'develop' for t in backend.calls), 1)
        self.assertEqual(self.store.get('status'), 'completed')

    def test_timeout_explains_the_setting_and_resume_action(self):
        message = error_summary(BackendError('/private/model exceeded the 599.9s task timeout'))
        self.assertIn('10.0 分钟', message)
        self.assertIn('/budget timeout_s', message)
        self.assertIn('/run', message)
        self.assertNotIn('/private/model', message)

    def test_resume_keeps_design_sources_out_of_first_round_full_reading(self):
        class DesignBackend(RecordingBackend):
            def generate(self, task):
                if task.stage in {'inspect_source', 'design_transfer'}:
                    self.calls.append(task)
                    return BackendResult({'observations': []} if task.stage == 'inspect_source' else
                                         {'paper_id': 'new-technique', 'options': [], 'reading_gaps': []})
                return super().generate(task)
        backend = DesignBackend()
        first = Controller(self.store, backend, self.config)
        def pause_search(candidate):
            self.store.put('papers', {'id': 'new-technique', 'title': 'A synthetic technical source',
                                      'content_kind': 'full_text', 'text': 'Method details for a focused design question.'})
            candidate['retrieved_work_ids'] = ['new-technique']
            self.store.put('candidates', candidate)
            raise BudgetExhausted('Paused in technical exploration')
        first.search_for_candidate = pause_search
        with self.assertRaises(BudgetExhausted):
            first.run()
        self.assertEqual(self.store.get('cohort')['initial_paper_ids'], [])
        self.assertNotIn('spec', self.store.rows('candidates')[0])
        resumed = Controller(self.store, backend, self.config)
        with patch.object(resumed, 'read_papers', wraps=resumed.read_papers) as read:
            resumed.run()
        read.assert_called_once_with([])
        stages = [t.stage for t in backend.calls]
        self.assertEqual(stages.count('propose'), 1)
        self.assertNotIn('paper_card', stages)
        self.assertNotIn('extract', stages)
        self.assertIn('design_transfer', stages)
        self.assertEqual(self.store.get('status'), 'completed')
