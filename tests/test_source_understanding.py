"""Exercise actual reading, quote repair, provenance and downstream handoffs."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest

from research_idea.backend_types import BackendResult
from research_idea.config import DEFAULTS
from research_idea.controller import Controller
from research_idea.demo import DemoBackend
from research_idea.discussion_sources import research_requests
from research_idea.presentation import activity_summary
from research_idea.citations import Citations
from research_idea.source_understanding import current_understandings, validate_reading_points
from research_idea.store import Store

QUOTES = [
    'Training labels are obtained from the simulator; no correctness labels are available during deployment.',
    'At deployment the policy receives an observation and retrieves a previously stored estimate.',
    'The policy outputs a tool choice, not a correctness certificate for the returned answer.',
]
PAPER = dict(id='routing', title='Synthetic routing source', url='https://example.org/routing',
             content_kind='full_text', text='1 Introduction\nA synthetic method description.\n2 Method\n' + '\n\n'.join(QUOTES))


def point(role, text, indices, kind='paper_claim'):
    return dict(role=role, text=text, information_type=kind, observation_indices=indices)


def output():
    return dict(observations=[dict(statement=q, quote=q, kind='author_claim',
                conditions='Synthetic method description', source_section='Method') for q in QUOTES],
        reading_points=[point('information_source', '正确性标签来自训练模拟器，部署时无法获得。', ['0']),
                        point('input', '部署时只使用观察和已经存下的估计。', ['1']),
                        point('processing', '依据观察检索旧估计，并决定工具。', ['1', '2']),
                        point('output', '输出工具选择，不提供答案正确性保证。', ['2']),
                        point('research_impact', '判断反馈能否帮助部署，必须分清训练标签与实际可用信号。', ['0', '1'], 'reasoned_inference')])


class Backend(DemoBackend):
    def __init__(self):
        self.calls = []
        self.value = output()
    def generate(self, task):
        payload = json.loads(task.prompt.split('BEGIN_RESEARCH_DATA\n')[1].split('\nEND_RESEARCH_DATA')[0])
        self.calls.append((task.stage, payload, task.output_schema))
        if task.stage == 'read_problem_source':
            return BackendResult(deepcopy(self.value))
        return super().generate(task)


class UnderstandingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.temp.name))
        self.store.put('papers', deepcopy(PAPER))
        self.store.set('topic', '模型怎样获得可靠的决策反馈？')
        self.backend = Backend()
        self.config = dict(DEFAULTS, backend='demo', builtin_skills=False, auto_search=False,
                           fetch_full_text=False, max_calls=80, max_seconds=120)
    def tearDown(self):
        self.store.close()
        self.temp.cleanup()
    def controller(self):
        return Controller(self.store, self.backend, self.config)
    def read(self):
        return research_requests(self.controller(), [dict(question='部署时怎样获得反馈？',
            query='', paper_ids=['routing'])], key='question-1')

    def test_single_call_persists_pipeline_and_reaches_ideation_with_real_links(self):
        self.read()
        self.assertEqual([s for s, _, _ in self.backend.calls], ['read_problem_source'])
        self.assertIn('reading_points', self.backend.calls[0][2]['properties'])
        context = self.controller().ideation_context()
        reading = context['source_understandings'][0]
        points = reading['reading_points']
        self.assertEqual(points[0]['role'], 'information_source')
        self.assertNotIn('observation_indices', points[0])
        evidence = {e['id']: e for e in context['evidence']}
        self.assertEqual(evidence[points[0]['evidence_ids'][0]]['quote'], QUOTES[0])
        self.assertEqual(evidence[points[-1]['evidence_ids'][1]]['quote'], QUOTES[1])
        self.controller().discover_problems()
        for stage, data, _ in self.backend.calls:
            if stage in {'explore_problems', 'deepen_problem', 'map'}:
                self.assertEqual(data['source_understandings'][0]['reading_points'], points)

    def test_resume_reuses_the_reading_without_an_extra_analysis_call(self):
        first = self.read()
        self.store.close()
        self.store = Store(Path(self.temp.name))
        self.assertEqual(self.read(), first)
        self.assertEqual(len(self.backend.calls), 1)
        self.assertEqual(len(current_understandings(self.controller())), 1)

    def test_duplicate_observations_do_not_shift_provenance_indices(self):
        self.backend.value['observations'].insert(1, deepcopy(self.backend.value['observations'][0]))
        self.backend.value['reading_points'] = [point('output', '只输出工具选择。', ['3']),
                                               point('input', '训练用模拟器标签。', ['0', '1'])]
        self.read()
        reading = current_understandings(self.controller())[0]
        evidence = {e['id']: e for e in self.store.rows('evidence')}
        self.assertEqual(evidence[reading['reading_points'][0]['evidence_ids'][0]]['quote'], QUOTES[2])
        self.assertEqual(len(reading['reading_points'][1]['evidence_ids']), 1)

    def test_failed_quote_drops_dependent_explanation_but_preserves_other_reading(self):
        self.backend.value['observations'][0]['quote'] = 'This invented sentence does not occur in the original source.'
        self.read()
        self.assertEqual(len(self.backend.calls), 2)  # Existing one-repair budget.
        points = current_understandings(self.controller())[0]['reading_points']
        self.assertEqual([p['role'] for p in points], ['input', 'processing', 'output'])
        evidence = {e['id']: e for e in self.store.rows('evidence')}
        self.assertEqual(evidence[points[0]['evidence_ids'][0]]['quote'], QUOTES[1])
        self.assertTrue(self.store.get('quote_gaps'))
        # A cached partial result still has a valid schema and original source mapping.
        self.assertEqual(self.read()['reading_status'], 'completed')
        self.assertEqual(len(self.backend.calls), 2)

    def test_changed_source_intent_or_guidance_cannot_supply_old_interpretation(self):
        self.read()
        old = self.store.get('source_understandings')
        self.store.set('research_intent', {'goal': '新的研究目标'})
        self.assertEqual(current_understandings(self.controller()), [])
        self.store.set('research_intent', None)
        controller = self.controller()
        controller.guidance_keys['read_problem_source'] = 'new-guidance'
        self.assertEqual(current_understandings(controller), [])
        self.store.put('papers', {**PAPER, 'text': PAPER['text'] + '\nChanged source.'})
        self.assertEqual(current_understandings(self.controller()), [])
        self.assertEqual(self.store.get('source_understandings'), old)  # Kept for history.

    def test_missing_evidence_invalidates_the_reading_view(self):
        self.read()
        self.store.replace_evidence('routing', [])
        self.assertEqual(current_understandings(self.controller()), [])

    def test_facts_need_local_support_but_hypotheses_can_be_proposed(self):
        value = output()
        value['reading_points'] = [point('research_impact', '可能存在条件变化后的新困难。', [], 'hypothesis')]
        validate_reading_points(value)
        value['reading_points'][0]['information_type'] = 'prior_literature'
        with self.assertRaisesRegex(ValueError, 'quoted observations'):
            validate_reading_points(value)
        value['reading_points'][0]['observation_indices'] = ['99']
        with self.assertRaisesRegex(ValueError, 'this source call'):
            validate_reading_points(value)

    def test_display_leads_with_impact_and_resolves_the_paper_link(self):
        reading = self.read()['readings'][0]
        rendered = activity_summary('read_problem_source', reading, Citations.from_store(self.store))
        self.assertIn('[Synthetic routing source](https://example.org/routing)', rendered)
        self.assertLess(rendered.index('对当前研究的启发'), rendered.index('关键信息怎样取得'))
        self.assertIn('分析推断', rendered)
        self.assertIn('论文所述', rendered)
        self.assertNotIn('observation_indices', rendered)
