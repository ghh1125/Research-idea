"""Behavioral contracts for idea formation followed by technical exploration."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from research_idea.demo import demo_design_plan
from research_idea.config import DEFAULTS
from research_idea.controller import BudgetExhausted, Controller, make_evidence
from research_idea.literature import normalize_paper
from research_idea.presentation import stage_label
from research_idea.schema import SCHEMAS
from research_idea.search_scope import config_scope
from research_idea.store import Store
import test_controller as fixtures
from test_controller import FakeBackend, valid_shape


def data(task):
    return json.loads(task.prompt.split('BEGIN_RESEARCH_DATA\n')[1].split('\nEND_RESEARCH_DATA')[0])


class TechnicalDesignTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.temp.name))
        self.store.set('topic', 'Design informative environments for agents')
        self.config = dict(DEFAULTS, backend='test', auto_search=False, builtin_skills=False,
                           max_rounds=1, max_candidates=1, max_seconds=60)
        self.paper = fixtures.EvidenceIntegrityTests().paper()
        self.paper.update(title='Synthetic source from another CS subfield', url='https://example.org/source')
        self.store.put('papers', self.paper)
        self.observation = fixtures.EvidenceIntegrityTests().observation()
        self.evidence = make_evidence(self.paper, [self.observation], self.paper['text'])
        self.store.replace_evidence('paper-1', self.evidence)
        self.eid = self.evidence[0]['id']
        proposal = valid_shape(SCHEMAS['propose']['properties']['candidates']['items'])
        proposal['motivation']['evidence_ids'] = [self.eid]
        proposal['closest_work_ids'] = ['paper-1']
        self.candidate = {'id': 'idea-1', 'proposal': proposal, 'versions': [], 'design_search_plan': demo_design_plan()}

    def tearDown(self):
        self.store.close()
        self.temp.cleanup()

    def transfer(self):
        option = valid_shape(SCHEMAS['design_transfer']['properties']['options']['items'])
        option.update(question='How should the environment allocate diagnostic observations?',
                      source_technique='A budget-controlled allocation rule from the supplied source.',
                      shared_structure='Both problems allocate limited observations across unresolved alternatives.',
                      adaptation='Replace the source task outcome with the agent distinguishing environment rules.',
                      simpler_alternative='Allocate observations uniformly under the same budget.',
                      first_test='Compare rule discrimination at equal observation budgets.',
                      evidence_ids=[self.eid])
        return {'paper_id': 'paper-1', 'options': [option], 'reading_gaps': []}

    def test_angles_are_planned_before_reading_and_reach_design_without_network(self):
        self.candidate.pop('design_search_plan')
        plan = demo_design_plan()
        method = fixtures.EvidenceIntegrityTests().spec(self.eid)
        backend = FakeBackend([plan, self.transfer(), method, valid_shape(SCHEMAS['review'])])
        controller = Controller(self.store, backend, self.config)
        with patch('research_idea.literature.discover', side_effect=AssertionError('Network disabled')):
            controller.develop_candidate(self.candidate)
        self.assertEqual([t.stage for t in backend.calls], ['plan_search', 'design_transfer', 'develop', 'review'])
        for task in backend.calls[1:3]:
            self.assertEqual(data(task)['design_search_plan']['design_axes'], plan['design_axes'])
        self.assertEqual(self.candidate['spec']['design_decisions'][0]['axis_ids'], ['relations', 'use'])

    def test_full_reading_quota_still_plans_angles_before_using_known_sources(self):
        self.candidate.pop('design_search_plan')
        backend = FakeBackend([demo_design_plan(), self.transfer()])
        controller = Controller(self.store, backend, dict(self.config, auto_search=True, max_papers=1))
        with patch.object(controller, 'search_once', side_effect=AssertionError('No reading room')):
            controller.prepare_design(self.candidate)
        self.assertEqual([t.stage for t in backend.calls], ['plan_search', 'design_transfer'])

    def test_method_choice_cannot_silently_drop_a_planned_angle(self):
        method = fixtures.EvidenceIntegrityTests().spec(self.eid)
        import copy
        invalid = copy.deepcopy(method)
        invalid['design_decisions'][0]['axis_ids'] = ['relations']
        backend = FakeBackend([self.transfer(), invalid, method, valid_shape(SCHEMAS['review'])])
        Controller(self.store, backend, self.config).develop_candidate(self.candidate)
        self.assertEqual(sum(t.stage == 'develop' for t in backend.calls), 2)
        self.assertIn('Address both technical angles', backend.calls[2].prompt)

    def test_source_transfer_precedes_method_and_reuses_first_round_reading(self):
        method = fixtures.EvidenceIntegrityTests().spec(self.eid)
        backend = FakeBackend([self.transfer(), method, valid_shape(SCHEMAS['review'])])
        controller = Controller(self.store, backend, self.config)
        with patch.object(controller, 'focus_sources', side_effect=AssertionError('Needlessly reread source')):
            controller.develop_candidate(self.candidate)
        self.assertEqual([t.stage for t in backend.calls], ['design_transfer', 'develop', 'review'])
        developed = data(backend.calls[1])
        self.assertEqual(developed['design_transfers'], [self.transfer()])
        self.assertEqual(developed['candidate']['motivation'], self.candidate['proposal']['motivation'])
        self.assertTrue(self.candidate['development_complete'])
        self.assertEqual(self.store.rows('candidates')[0]['design_transfers'], [self.transfer()])

    def reading_backend(self, responses):
        case = self
        class ReadingBackend(FakeBackend):
            def generate(self, task):
                result = super().generate(task)
                if task.stage == 'design_transfer' and result.output['options']:
                    case.eid = data(task)['evidence'][0]['id']
                    for option in result.output['options']:
                        option['evidence_ids'] = [case.eid]
                return result
        return ReadingBackend(responses)

    def test_new_source_is_read_for_the_design_question_without_full_paper_card(self):
        self.store.replace_evidence('paper-1', [])
        self.paper['selection'] = {'reading_question': 'Which signal is needed by the allocation rule?'}
        self.store.put('papers', self.paper)
        backend = self.reading_backend([{'observations': [self.observation]}, self.transfer()])
        Controller(self.store, backend, self.config).prepare_design(self.candidate)
        self.assertEqual([t.stage for t in backend.calls], ['inspect_source', 'design_transfer'])
        self.assertEqual(data(backend.calls[0])['purpose'], 'technical_design')
        self.assertEqual(data(backend.calls[0])['reading_question'], self.paper['selection']['reading_question'])
        self.assertEqual(data(backend.calls[1])['evidence'][0]['id'], self.eid)

    def test_source_transfer_does_not_require_experimental_design(self):
        transfer = self.transfer()
        transfer['options'][0]['first_test'] = ''
        backend = FakeBackend([transfer])
        Controller(self.store, backend, self.config).prepare_design(self.candidate)
        self.assertEqual(len(backend.calls), 1)
        self.assertEqual(self.candidate['design_transfers'], [transfer])

    def test_unavailable_new_fulltexts_do_not_displace_reusable_read_sources(self):
        for index in range(3):
            self.store.put('papers', {'id': 'unavailable-' + str(index), 'title': 'Abstract only',
                                      'content_kind': 'abstract', 'abstract': 'An unverified method.'})
        self.candidate['retrieved_work_ids'] = ['unavailable-' + str(i) for i in range(3)]
        backend = FakeBackend([self.transfer()])
        Controller(self.store, backend, self.config).prepare_design(self.candidate)
        self.assertEqual([t.stage for t in backend.calls], ['design_transfer'])
        self.assertEqual(self.candidate['design_transfers'], [self.transfer()])

    def test_an_unanswered_design_question_triggers_one_focused_read(self):
        gap = 'Does the rule require training labels or only observable outcomes?'
        backend = self.reading_backend([{'paper_id': 'paper-1', 'options': [], 'reading_gaps': [gap]},
                               {'observations': [self.observation]}, self.transfer()])
        Controller(self.store, backend, self.config).prepare_design(self.candidate)
        self.assertEqual([t.stage for t in backend.calls], ['design_transfer', 'inspect_source', 'design_transfer'])
        self.assertEqual(data(backend.calls[1])['reading_question'], gap)

    def test_transfer_cannot_attribute_another_papers_evidence_to_this_source(self):
        self.store.put('papers', dict(self.paper, id='paper-2'))
        self.store.replace_evidence('paper-2', [dict(self.evidence[0], id='ev-other', paper_id='paper-2')])
        invalid = self.transfer()
        invalid['options'][0]['evidence_ids'] = ['ev-other']
        backend = FakeBackend([invalid, self.transfer()])
        Controller(self.store, backend, self.config).prepare_design(self.candidate)
        self.assertEqual(len(backend.calls), 2)
        self.assertIn('Unknown evidence ID', backend.calls[1].prompt)
        self.assertEqual(self.candidate['design_transfers'], [self.transfer()])

    def test_first_round_motivation_search_uses_recent_window_and_design_uses_strategy_window(self):
        config = dict(self.config, auto_search=True, search_date_mode='rolling', strategy_months=12,
                      novelty_months=6, max_papers=6)
        controller = Controller(self.store, FakeBackend([]), config)
        plan = {'queries': [{'query': 'agent environment gaps', 'purpose': 'motivation', 'rationale': 'Compare problems'},
                            {'query': 'active observation allocation', 'purpose': 'mechanism', 'rationale': 'Find techniques'}]}
        with patch.object(controller, 'plan_search', return_value=plan), \
             patch.object(controller, 'search_once', return_value='key') as search, \
             patch.object(controller, 'select_search_results'):
            controller.initial_search()
            self.assertEqual([c.kwargs['purpose'] for c in search.call_args_list], ['novelty', 'strategy'])
            search.reset_mock()
            controller.search_for_candidate(self.candidate)
            self.assertEqual([c.kwargs['purpose'] for c in search.call_args_list], ['design', 'design'])
        self.assertEqual(config_scope(config, 'design'), config_scope(config, 'strategy'))
        self.assertGreater(config_scope(config, 'novelty')['since'], config_scope(config, 'design')['since'])

    def test_design_selection_resumes_download_without_replanning_or_rescreening(self):
        config = dict(self.config, auto_search=True, max_papers=6)
        plan = {'research_question': 'How can observations distinguish competing causes?',
                'scope': 'Transfer active sensing to environment design.',
                'queries': [{'query': 'active sensing belief update', 'purpose': 'mechanism',
                             'rationale': 'Find a reusable update rule without restricting the application domain.'}],
                'assumptions': []}
        source = normalize_paper({'id': 'borrowed', 'title': 'Synthetic active sensing study',
                                  'abstract': 'A source for belief updates.', 'url': 'https://example.org/borrowed'})
        screen = {'selection_summary': 'This source answers the update question.',
                  'selected': [{'paper_id': source['id'], 'reason': 'Shared partial-observation structure.',
                                'reading_question': 'How does the belief update use observations?', 'reading_role': 'method', 'route_ids': []}]}
        backend = FakeBackend([plan, screen])
        controller = Controller(self.store, backend, config)
        with patch('research_idea.literature.discover', return_value=[source]), \
             patch.object(controller, 'retrieve_full_texts', side_effect=BudgetExhausted('Download paused')):
            with self.assertRaises(BudgetExhausted):
                controller.search_for_candidate(self.candidate)
        saved = self.store.rows('candidates')[0]
        self.assertTrue(saved['design_search_complete'])
        self.assertIn(source['id'], saved['retrieved_work_ids'])
        self.assertNotIn('spec', saved)
        self.assertEqual(data(backend.calls[0])['purpose'], 'technical_design')
        self.assertEqual(data(backend.calls[1])['purpose'], 'technical_design')
        self.assertEqual(data(backend.calls[0])['candidate'], self.candidate['proposal'])
        resumed_backend = FakeBackend([])
        resumed = Controller(self.store, resumed_backend, config)
        with patch.object(resumed, 'retrieve_full_texts', return_value=True) as download:
            resumed.search_for_candidate(saved)
        download.assert_called_once_with(saved['retrieved_work_ids'])
        self.assertEqual(resumed_backend.calls, [])

    def test_second_round_labels_do_not_reset_to_first_round_search(self):
        self.assertEqual(stage_label('propose')[0], 'concept')
        for stage in ('plan_search', 'screen_papers', 'inspect_source', 'design_transfer', 'develop', 'review'):
            tag, label = stage_label(stage, 'design')
            self.assertIn('第二阶段', label)
            self.assertNotEqual(tag, 'idea')

