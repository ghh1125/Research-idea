"""Breadth survives selection, resumes, discussions and source promotion."""
from copy import deepcopy
from pathlib import Path
import json
import tempfile
import unittest
from unittest.mock import patch

from research_idea.backend_types import BackendResult
from research_idea.config import DEFAULTS
from research_idea.controller import Controller, BudgetExhausted
from research_idea.demo import DemoBackend, demo_design_plan
from research_idea.discussion_sources import research_requests
from research_idea.landscape import prepare_landscape, context_view, research_mode
from research_idea.literature import normalize_paper
from research_idea.store import Store
from research_idea.citations import Citations
from research_idea.research_context import expand_task_payload
from research_idea.report import export_report


class ReadingBackend(DemoBackend):
    def __init__(self):
        self.calls = []
        self.supplement = False
        self.supplement_purpose = 'strategy'
        self.interrupt_batch = 0

    def generate(self, task):
        p = expand_task_payload(json.loads(task.prompt.split('BEGIN_RESEARCH_DATA\n', 1)[1].split('\nEND_RESEARCH_DATA', 1)[0]))
        if task.stage == 'skim_papers':
            if self.interrupt_batch and len([s for s, _ in self.calls if s == 'skim_papers']) == self.interrupt_batch:
                raise KeyboardInterrupt()
            self.calls.append((task.stage, deepcopy(p)))
            return BackendResult({'notes': [dict(paper_id=x['id'], relevance='adjacent',
                problem=x['abstract'], approach='A distinct source method.', claimed_progress='Claimed under the stated conditions.',
                conditions='Synthetic fixture.', connection='A different explanation.', reading_question='') for x in p['papers']]})
        self.calls.append((task.stage, deepcopy(p)))
        if task.stage == 'synthesize_landscape':
            return BackendResult(dict(background='Synthetic breadth comparison.',
                approaches=[dict(name='Different approaches', principle='Compare their conditions.',
                                 achieved_progress='Author claims only.', paper_ids=[n['paper_id'] for n in p['paper_notes']])],
                connections=[dict(question='Which conditions matter?', reasoning='Compare explanations.',
                                  paper_ids=[n['paper_id'] for n in p['paper_notes']])],
                coverage='Synthetic fixture.', supplement_queries=[{'query': 'adjacent method', 'reason': 'An adjacent route is absent.',
                                                                    'purpose': self.supplement_purpose}]
                if self.supplement and p['allow_supplement'] else []))
        return super().generate(task)


class LandscapeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.temp.name))
        self.store.set_many({'topic': 'How can agents coordinate?', 'workflow': 'question'})
        self.backend = ReadingBackend()
        self.cfg = dict(DEFAULTS, backend='api', auto_search=True, fetch_full_text=False,
                        max_calls=80, max_seconds=120, builtin_skills=True)
        self.plan = demo_design_plan()
        self.enrich = patch('research_idea.paper_metadata.enrich_screening_pool',
                            side_effect=lambda papers, **kw: (papers, {'attempted': 0, 'enriched': 0, 'pages': []}))
        self.enrich.start()
        self.addCleanup(self.enrich.stop)

    def tearDown(self):
        self.store.close()
        self.temp.cleanup()

    def controller(self, **config):
        return Controller(self.store, self.backend, dict(self.cfg, **config))

    def seed(self, count=20, *, key='a', start=0):
        papers = [normalize_paper(dict(id=f'p{i}', title=f'Agent coordination approach {i}',
                      abstract=f'Approach {i} addresses a different coordination condition.',
                      year=2026, url=f'https://example.org/p{i}', source='fixture')) for i in range(start, start + count)]
        ledger = self.store.get('search_ledger', {})
        ledger[key] = dict(query='agent coordination', status='completed', metadata=papers)
        self.store.set('search_ledger', ledger)
        return papers

    def test_unselected_papers_reach_discussion_and_report_without_becoming_fulltext_evidence(self):
        papers = self.seed(40)
        c = self.controller()
        prepare_landscape(c, ['a'], self.plan)
        self.store.put('papers', papers[0])
        context = c.ideation_context()
        self.assertEqual(len(context['literature_landscape']['paper_notes']), 40)
        self.assertEqual(len(context['papers']), 40)
        self.assertEqual(len(self.store.rows('papers')), 1)
        self.assertEqual(context['evidence'], [])
        self.assertEqual(len(context['literature_landscape']['focused_abstracts']), 6)
        self.assertEqual(len([1 for stage, _ in self.backend.calls if stage == 'skim_papers']), 5)
        self.assertIn('https://example.org/p39', Citations.from_store(self.store).paper('p39'))
        _, report = export_report(self.store, Path(self.temp.name) / 'result')
        data = json.loads(report.read_text())
        self.assertEqual(len(data['literature_landscape']['notes']), 40)
        self.assertEqual(len(data['papers']), 40)

    def test_skims_reach_actual_exploration_and_user_discussion(self):
        from research_idea.problem_discovery import explore_problem_pool
        from research_idea.problem_dialogue import open_checkpoint, discuss
        from research_idea.conversation import append_message
        self.seed(12)
        c = self.controller()
        prepare_landscape(c, ['a'], self.plan)
        context = c.ideation_context()
        pool = explore_problem_pool(c, context, lambda value: None)
        open_checkpoint(c, pool, kind='direction')
        message = append_message(self.store, 'user', '请比较不同条件下的已有回应，不要换题。')
        discuss(c, message)
        supplied = {stage: data for stage, data in self.backend.calls
                    if stage in {'explore_problems', 'discuss_direction'}}
        self.assertEqual(set(supplied), {'explore_problems', 'discuss_direction'})
        for data in supplied.values():
            self.assertEqual(len(data['literature_landscape']['paper_notes']), 12)
            self.assertEqual(len(data['papers']), 12)
        self.assertEqual(self.store.get('problem_checkpoint')['state'], 'discussing')
        self.assertEqual(self.store.rows('papers'), [])
        self.assertFalse(any(stage == 'read_problem_source' for stage, _ in self.backend.calls))

    def test_feedback_keeps_original_coverage_basis_separate_from_revised_goal(self):
        self.seed(4)
        original = {'mode': 'refine', 'goal': 'agent coordination under shared memory'}
        self.store.set('research_intent', original)
        prepare_landscape(self.controller(), ['a'], self.plan)
        self.store.set('research_intent', {'mode': 'refine', 'goal': 'receiver compression fidelity'})
        before = len(self.backend.calls)
        context = self.controller().ideation_context(focus='receiver compression fidelity')
        basis = context['literature_landscape']['coverage_basis']
        self.assertEqual(basis['research_intent'], original)
        self.assertEqual(basis['queries'], ['agent coordination'])
        self.assertEqual(context['research_mode']['goal'], 'receiver compression fidelity')
        self.assertEqual(len(self.backend.calls), before)

    def test_title_similarity_does_not_merge_or_discard_sources_and_missing_abstract_is_not_read(self):
        papers = self.seed(3)
        papers[0]['title'] = papers[1]['title'] = 'Agent Memory'
        papers[0]['abstract'] = 'Training-time memory construction for known tasks.'
        papers[1]['abstract'] = 'Inference-time coordination under a changing environment.'
        papers[2]['abstract'] = papers[2]['text'] = ''
        self.store.set('search_ledger', {'a': dict(query='memory', metadata=papers)})
        c = self.controller()
        prepare_landscape(c, ['a'], self.plan)
        notes = {n['paper_id']: n for n in context_view(self.store)['paper_notes']}
        self.assertEqual(set(notes), {'p0', 'p1', 'p2'})
        self.assertNotEqual(notes['p0']['problem'], notes['p1']['problem'])
        self.assertEqual(notes['p2']['claimed_progress'], '')
        self.assertEqual(notes['p2']['basis'], 'title_only')
        self.assertEqual(context_view(self.store)['reading_counts'], {'skimmed': 2, 'title_only': 1})

    def test_interrupted_batches_resume_without_repeating_completed_model_calls(self):
        self.seed(20)
        self.backend.interrupt_batch = 1
        with self.assertRaises(KeyboardInterrupt):
            prepare_landscape(self.controller(), ['a'], self.plan)
        self.backend.interrupt_batch = 0
        prepare_landscape(self.controller(), ['a'], self.plan)
        batches = [p for s, p in self.backend.calls if s == 'skim_papers']
        self.assertEqual(len(batches), 3)
        before = len(self.backend.calls)
        prepare_landscape(self.controller(), ['a'], self.plan)
        self.assertEqual(len(self.backend.calls), before)

    def test_abstract_change_recomputes_affected_batch_and_synthesis(self):
        self.seed(16)
        prepare_landscape(self.controller(), ['a'], self.plan)
        ledger = self.store.get('search_ledger')
        ledger['a']['metadata'][0]['abstract'] = 'A corrected abstract with changed conditions.'
        self.store.set('search_ledger', ledger)
        prepare_landscape(self.controller(), ['a'], self.plan)
        self.assertEqual(len([1 for s, _ in self.backend.calls if s == 'skim_papers']), 3)
        self.assertEqual(len([1 for s, _ in self.backend.calls if s == 'synthesize_landscape']), 2)

    def test_supplement_is_bounded_and_its_new_route_survives(self):
        self.seed(40)
        self.seed(25, key='b', start=40)
        self.backend.supplement = True
        c = self.controller()
        with patch.object(c, 'search_once', return_value='b') as search:
            self.assertEqual(prepare_landscape(c, ['a'], self.plan), ['a', 'b'])
        search.assert_called_once()
        self.assertEqual(search.call_args.kwargs['purpose'], 'strategy')
        notes = context_view(self.store)['paper_notes']
        self.assertEqual(len(notes), 56)
        self.assertTrue(any(n['paper_id'] == 'p40' for n in notes))
        synth = [p for s, p in self.backend.calls if s == 'synthesize_landscape']
        self.assertEqual([p['allow_supplement'] for p in synth], [True, False])

    def test_foundational_supplement_uses_lineage_window(self):
        self.seed(4)
        self.seed(2, key='b', start=4)
        self.backend.supplement = True
        self.backend.supplement_purpose = 'lineage'
        c = self.controller()
        with patch.object(c, 'search_once', return_value='b') as search:
            prepare_landscape(c, ['a'], self.plan)
        self.assertEqual(search.call_args.kwargs['purpose'], 'lineage')

    def test_specific_problem_mode_and_current_focus_are_passed_without_forcing_alternative_topics(self):
        papers = self.seed(10)
        papers[-1]['abstract'] = 'Hidden receiver understanding affects compression fidelity.'
        self.store.set('search_ledger', {'a': dict(query='agent', metadata=papers)})
        for mode in ('refine', 'assess'):
            self.store.set('research_intent', {'mode': mode, 'goal': 'receiver compression fidelity'})
            prepare_landscape(self.controller(), ['a'], self.plan)
            context = self.controller().ideation_context(focus='hidden receiver understanding compression fidelity')
            self.assertEqual(context['research_mode']['compare'], 'explanations_and_existing_responses')
            self.assertEqual(context['literature_landscape']['focused_abstracts'][0]['paper_id'], 'p9')
        self.assertEqual(research_mode({'mode': 'explore'})['compare'], 'important_problems')
        for stage, payload in self.backend.calls:
            if stage in {'skim_papers', 'synthesize_landscape'}:
                self.assertEqual(payload['research_mode']['kind'], 'focused_question')

    def test_discussion_can_promote_a_previously_unselected_abstract_for_targeted_reading(self):
        self.seed(3)
        c = self.controller()
        prepare_landscape(c, ['a'], self.plan)
        with patch.object(c, 'retrieve_full_texts') as fetch, patch.object(c, 'focus_sources', return_value=[]) as read:
            result = research_requests(c, [{'question': 'What conditions does p2 actually require?',
                                           'query': '', 'paper_ids': ['p2']}], key='discussion')
        self.assertEqual(result['selected_ids'], ['p2'])
        fetch.assert_called_once_with(['p2'])
        self.assertEqual([p['id'] for p in self.store.rows('papers')], ['p2'])
        self.assertEqual(read.call_args.kwargs['reading_question'], 'What conditions does p2 actually require?')

    def test_initial_search_uses_full_background_allowance_and_passes_landscape_to_selection(self):
        papers = self.seed(12)
        c = self.controller(max_papers=6)
        with patch.object(c, 'plan_search', return_value=self.plan), patch.object(c, 'search_once', return_value='a'), \
             patch.object(c, 'retrieve_full_texts', return_value=False):
            c.initial_search()
        screens = [p for s, p in self.backend.calls if s == 'screen_papers']
        self.assertEqual(screens[0]['max_papers'], 6)
        self.assertEqual(len(screens[0]['literature_landscape']['paper_notes']), 12)
        self.assertEqual(len(self.store.rows('papers')), 6)

    def test_model_budget_still_bounds_skimming(self):
        self.seed(16)
        with self.assertRaises(BudgetExhausted):
            prepare_landscape(self.controller(max_calls=1), ['a'], self.plan)
        self.assertEqual(self.store.get('calls_used'), 1)
        prepare_landscape(self.controller(), ['a'], self.plan)
        self.assertEqual(len([1 for s, _ in self.backend.calls if s == 'skim_papers']), 2)


if __name__ == '__main__':
    unittest.main()
