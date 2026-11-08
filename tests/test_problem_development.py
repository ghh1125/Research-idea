"""Argument-first acquisition, selective revisions, and interrupted handoffs."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from research_idea.config import DEFAULTS
from research_idea.controller import Controller
from research_idea.demo import DemoBackend
from research_idea.problem_discovery import reconsider_after_reading
from research_idea.research_context import expand_task_payload
from research_idea.store import Store


def data(task):
    return expand_task_payload(json.loads(task.prompt.split('BEGIN_RESEARCH_DATA\n')[1].split('\nEND_RESEARCH_DATA')[0]))


class Backend(DemoBackend):
    def __init__(self, hook=None):
        self.calls, self.hook = [], hook

    def generate(self, task):
        self.calls.append(task)
        result = super().generate(task)
        if self.hook:
            self.hook(task, result.output)
        return result


class DevelopmentTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.store = Store(Path(tmp.name))
        self.addCleanup(self.store.close)
        self.store.set('topic', 'How can agents learn from changing environments?')
        self.config = dict(DEFAULTS, backend='demo', auto_search=False, builtin_skills=False,
                           max_calls=80, max_seconds=60)
        self.backend = Backend()
        self.controller().run_questions(interactive=True)
        self.pool = deepcopy(self.store.get('problem_checkpoint')['current'])
        self.ids = [s['id'] for s in self.pool['problem_seeds']]
        self.read_calls = []

    def controller(self, **config):
        return Controller(self.store, self.backend, dict(self.config, **config))

    def read(self, controller, seed, *, analysis):
        self.read_calls.append(seed['id'])
        self.assertEqual(len(self.store.get('problem_cases')), len(self.ids))
        self.assertIn('bottleneck_hypothesis', analysis['opportunity'])
        self.assertTrue(analysis['response_analysis'])
        paper_id = 'source-' + seed['id']
        self.store.put('papers', {'id': paper_id, 'title': 'Concrete existing response',
            'url': 'https://example.org/' + paper_id, 'content_kind': 'full_text',
            'text': 'The existing method revises future decisions after receiving feedback.'})
        return {'readings': [{'paper_id': paper_id, 'evidence_ids': [],
                             'reading_question': analysis['opportunity']['bottleneck_hypothesis']}]}

    def revise_second(self, task, output):
        if task.stage != 'reconsider_problems':
            return
        before = data(task)['problem_analyses']
        self.assertEqual(len(before), len(self.ids))
        updated = deepcopy(before[1])
        updated['opportunity']['bottleneck_hypothesis'] = 'Feedback arrives after an irreversible action.'
        updated['opportunity']['research_need'] = 'Understand when timely correction is possible.'
        updated['response_analysis'][0]['why_it_remains'] = 'Correction can improve later actions, not undo prior ones.'
        updated['explanation_comparison'][0]['explanation'] = 'Timing rather than missing information.'
        updated['revision_reason'] = 'The first source resolves the assumed lack of information.'
        output['case_updates'] = [updated]
        output['changes'] = [{'previous_ids': [self.ids[1]], 'current_ids': [self.ids[1]],
            'reason': updated['revision_reason'], 'evidence_ids': []}]

    def test_reading_follows_analysis_and_only_affected_case_changes_before_selection(self):
        self.backend.hook = self.revise_second
        with patch('research_idea.discussion_sources.investigate_problem', side_effect=self.read):
            self.controller().run_questions(interactive=True, continue_problem=True)
        stages = [t.stage for t in self.backend.calls]
        self.assertEqual(stages.count('deepen_problem'), len(self.ids))
        self.assertEqual(stages.count('reconsider_problems'), 1)
        self.assertLess(stages.index('reconsider_problems'), stages.index('map'))
        initial = self.store.get('problem_development')['initial']
        mapping = data(next(t for t in self.backend.calls if t.stage == 'map'))
        self.assertEqual(mapping['problem_cases'][0], initial[self.ids[0]]['opportunity'])
        self.assertEqual(mapping['problem_cases'][1]['bottleneck_hypothesis'],
                         'Feedback arrives after an irreversible action.')
        self.assertEqual(mapping['response_analyses'][self.ids[1]][0]['why_it_remains'],
                         'Correction can improve later actions, not undo prior ones.')
        self.assertEqual(mapping['explanation_comparisons'][self.ids[1]][0]['explanation'],
                         'Timing rather than missing information.')
        checkpoint = self.store.get('problem_checkpoint')
        self.assertEqual(checkpoint['kind'], 'problem')
        self.assertEqual(checkpoint['state'], 'discussing')
        self.assertNotIn('frame_question', stages)
        journal = next(iter(self.store.get('problem_reconsiderations').values()))
        self.assertEqual(journal['analyses_before'][0], journal['analyses_after'][0])
        self.assertNotEqual(journal['analyses_before'][1], journal['analyses_after'][1])

    def test_resume_after_new_source_does_not_repeat_initial_analysis_or_completed_reading(self):
        failed = False
        def interrupted(controller, seed, *, analysis):
            nonlocal failed
            if seed['id'] == self.ids[1] and not failed:
                failed = True
                raise RuntimeError('interrupted during second source')
            return self.read(controller, seed, analysis=analysis)
        with patch('research_idea.discussion_sources.investigate_problem', side_effect=interrupted):
            with self.assertRaisesRegex(RuntimeError, 'second source'):
                self.controller().run_questions(interactive=True, continue_problem=True)
            self.assertTrue(self.store.rows('papers'))
            saved_context = deepcopy(self.store.get('problem_development')['context'])
            self.controller(max_calls=100).run_questions(interactive=True)
        stages = [t.stage for t in self.backend.calls]
        self.assertEqual(stages.count('deepen_problem'), len(self.ids))
        self.assertEqual(self.read_calls, self.ids)
        self.assertEqual(self.store.get('problem_development')['context'], saved_context)
        self.assertEqual(stages.count('reconsider_problems'), 1)

    def test_no_reading_keeps_analyses_without_revision_call(self):
        with patch('research_idea.discussion_sources.investigate_problem',
                   return_value={'readings': [], 'search_status': 'no_results'}):
            self.controller().run_questions(interactive=True, continue_problem=True)
        self.assertNotIn('reconsider_problems', [t.stage for t in self.backend.calls])
        self.assertEqual(self.store.get('problem_cases'),
                         [v['opportunity'] for v in self.store.get('problem_development')['initial'].values()])

    def test_changed_model_invalidates_saved_analysis(self):
        with patch('research_idea.discussion_sources.investigate_problem', return_value=None):
            self.controller().discover_problems(pool=self.pool)
            self.controller(model='different-model').discover_problems(pool=self.pool)
        self.assertEqual([t.stage for t in self.backend.calls].count('deepen_problem'), 2 * len(self.ids))

    def test_replaced_direction_cannot_inherit_an_unrelated_old_analysis(self):
        controller = self.controller()
        with patch('research_idea.discussion_sources.investigate_problem', return_value=None):
            controller.discover_problems(pool=self.pool)
        analyses = list(self.store.get('problem_development')['initial'].values())
        attempts = []
        def replace(task, output):
            if task.stage != 'reconsider_problems':
                return
            attempts.append(task)
            output['pool']['problem_seeds'][0]['id'] = 'replacement'
            output['changes'] = [{'previous_ids': [self.ids[0]], 'current_ids': ['replacement'],
                                  'reason': 'The old premise is resolved.', 'evidence_ids': []}]
            if len(attempts) > 1:
                update = deepcopy(analyses[0])
                update['opportunity']['id'] = 'replacement'
                update['opportunity']['bottleneck_hypothesis'] = 'A different causal explanation.'
                output['case_updates'] = [update]
        self.backend.hook = replace
        pool, revised = reconsider_after_reading(controller, self.pool, controller.ideation_context(),
            [{'readings': [{'paper_id': 'synthetic', 'evidence_ids': []}]}], analyses)
        self.assertEqual(len(attempts), 2)
        self.assertIn('complete updated analyses', attempts[1].prompt)
        self.assertEqual(revised[0]['opportunity']['id'], pool['problem_seeds'][0]['id'])
        self.assertEqual(revised[1], analyses[1])


if __name__ == '__main__':
    unittest.main()
