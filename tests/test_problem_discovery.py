"""Problem discovery gives alternatives separate work before choosing a solution."""
import copy
import json
from pathlib import Path
import tempfile
import unittest

from research_idea.config import DEFAULTS
from research_idea.controller import Controller, BudgetExhausted
from research_idea.demo import DemoBackend
from research_idea.presentation import activity_summary
from research_idea.report import export_report
from research_idea.store import Store


def payload(task):
    return json.loads(task.prompt.split('BEGIN_RESEARCH_DATA\n')[1].split('\nEND_RESEARCH_DATA')[0])


class Backend(DemoBackend):
    def __init__(self, hook=None):
        self.calls, self.hook = [], hook

    def generate(self, task):
        self.calls.append(task)
        result = super().generate(task)
        if task.stage == 'explore_problems':
            result.output['problem_seeds'].append(dict(id='feedback',
                question='任务结果延迟出现时，怎样判断交互是否提供了有用信息？',
                problem_origin='unresolved_need', entry_reason='反馈能否指导下一步是另一个问题。',
                research_route_ids=[]))
        if self.hook:
            self.hook(task, result.output)
        return result


class ProblemDiscoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.temp.name))
        self.store.set('topic', '怎样让 agent 在不断变化的环境中学习')
        self.config = dict(DEFAULTS, backend='demo', auto_search=False,
                           builtin_skills=False, max_candidates=1, max_seconds=60)

    def tearDown(self):
        self.store.close()
        self.temp.cleanup()

    def test_each_direction_gets_isolated_analysis_before_selection(self):
        def observe(task, output):
            if task.stage == 'map':
                self.assertEqual(len(self.store.get('problem_cases')), 3)
                self.assertIsNone(self.store.get('problem_model'))
                self.assertEqual(payload(task)['problem_cases'], self.store.get('problem_cases'))
        backend = Backend(observe)
        result = Controller(self.store, backend, self.config).form_ideas()
        self.assertEqual([t.stage for t in backend.calls],
                         ['explore_problems'] + ['deepen_problem'] * 3 + ['map', 'propose'])
        deep = [payload(t) for t in backend.calls if t.stage == 'deepen_problem']
        self.assertEqual({d['problem_seed']['id'] for d in deep}, {'conflict', 'order', 'feedback'})
        for data in deep:
            self.assertEqual(data['topic'], self.store.get('topic'))
            for key in ('problem_cases', 'selected_problems', 'max_candidates', 'candidates'):
                self.assertNotIn(key, data)
            neutral = {k: v for k, v in data.items() if k != 'problem_seed'}
            self.assertEqual(neutral, {k: v for k, v in deep[0].items() if k != 'problem_seed'})
        self.assertEqual(len(result['candidates']), 1)
        self.assertEqual(len(self.store.get('problem_model')['problem_comparisons']), 3)

    def test_selection_cannot_rewrite_other_directions_to_justify_choice(self):
        original = []
        def change(task, output):
            if task.stage == 'deepen_problem':
                original.append(copy.deepcopy(output['opportunity']))
            elif task.stage == 'map':
                output['opportunities'][1]['why_it_matters'] = 'Rewritten as an unimportant side issue.'
        backend = Backend(change)
        Controller(self.store, backend, self.config).form_ideas()
        self.assertEqual(self.store.get('problem_model')['opportunities'], original)
        export_report(self.store, self.store.project)
        report = json.loads((self.store.project / self.store.get('output_folder') / 'report.json').read_text())
        self.assertEqual(report['problem_cases'], original)
        self.assertEqual(len(report['problem_exploration']['problem_seeds']), 3)

    def test_partial_problem_analysis_resumes_from_cached_cases(self):
        backend = Backend()
        with self.assertRaises(BudgetExhausted):
            Controller(self.store, backend, dict(self.config, max_calls=2)).form_ideas()
        self.assertEqual(len(self.store.get('problem_cases')), 1)
        self.assertIsNone(self.store.get('problem_model'))
        first = copy.deepcopy(self.store.get('problem_cases')[0])
        export_report(self.store, self.store.project)
        partial = self.store.project / self.store.get('output_folder') / 'report.md'
        self.assertIn(first['derivation'], partial.read_text())
        Controller(self.store, backend, self.config).form_ideas()
        self.assertEqual([t.stage for t in backend.calls].count('explore_problems'), 1)
        self.assertEqual([t.stage for t in backend.calls].count('deepen_problem'), 3)
        self.assertEqual(self.store.get('problem_cases')[0], first)

    def test_comparison_covers_every_case_before_proposal(self):
        attempts = []
        def omit(task, output):
            if task.stage == 'map':
                attempts.append(task)
                if len(attempts) == 1:
                    output['problem_comparisons'].pop()
        backend = Backend(omit)
        Controller(self.store, backend, self.config).form_ideas()
        self.assertEqual(len(attempts), 2)
        self.assertIn('every developed problem', attempts[1].prompt)
        self.assertEqual([t.stage for t in backend.calls].count('propose'), 1)
        problem = self.store.get('problem_model')
        shown = activity_summary('map', problem)
        for item in problem['problem_comparisons']:
            self.assertIn(item['strongest_case'], shown)
            self.assertIn(item['priority_reason'], shown)

    def test_narrow_scope_can_develop_one_problem_without_a_quota(self):
        def narrow(task, output):
            if task.stage == 'explore_problems':
                output['problem_seeds'] = output['problem_seeds'][:1]
        backend = Backend(narrow)
        Controller(self.store, backend, self.config).form_ideas()
        self.assertEqual([t.stage for t in backend.calls],
                         ['explore_problems', 'deepen_problem', 'map', 'propose'])

    def test_deep_analysis_cannot_substitute_a_different_problem(self):
        attempts = []
        def substitute(task, output):
            if task.stage == 'deepen_problem':
                attempts.append(task)
                if len(attempts) == 1:
                    output['opportunity']['id'] = 'a-different-problem'
        backend = Backend(substitute)
        Controller(self.store, backend, self.config).form_ideas()
        self.assertEqual(len(attempts), 4)
        self.assertIn('assigned problem ID', attempts[1].prompt)
        self.assertEqual([c['id'] for c in self.store.get('problem_cases')],
                         ['conflict', 'order', 'feedback'])
