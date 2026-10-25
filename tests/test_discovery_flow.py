"""Route-aware discovery stays connected to reading and first-phase reasoning."""
from __future__ import annotations

import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from research_idea.backend_types import BackendResult
from research_idea.config import DEFAULTS
from research_idea.controller import Controller
from research_idea.literature import normalize_paper
from research_idea.store import Store


def discovery_plan():
    return {
        'research_question': 'Which different mechanisms affect the original objective?',
        'scope': 'Compare lines of inquiry before choosing a research problem.',
        'research_routes': [
            {'id': route, 'question': question, 'why_relevant': 'A distinct connection to the original objective.'}
            for route, question in [('a', 'How is information obtained?'),
                                    ('b', 'How is available information used?'),
                                    ('c', 'When does the environment change?')]],
        'design_axes': [],
        'queries': [{'query': query, 'purpose': 'background', 'rationale': 'Explore this line of inquiry.',
                     'axis_ids': [], 'route_ids': [route]}
                    for route, query in [('a', 'information acquisition models'),
                                         ('b', 'conditional information use'),
                                         ('c', 'changing environment feedback')]],
        'assumptions': [],
    }


class DiscoveryBackend:
    name = 'discovery-flow-fixture'

    def __init__(self):
        self.calls = []

    def generate(self, task):
        payload = json.loads(task.prompt.split('BEGIN_RESEARCH_DATA\n', 1)[1].split('\nEND_RESEARCH_DATA', 1)[0])
        self.calls.append((task.stage, copy.deepcopy(payload)))
        if task.stage == 'plan_search':
            output = discovery_plan()
        elif task.stage == 'screen_papers':
            output = {'selection_summary': 'Read representatives of the supplied inquiries.', 'selected': [
                {'paper_id': paper['id'], 'reason': 'A useful source for the inquiry.',
                 'reading_question': 'Which source details explain this mechanism?', 'reading_role': 'method',
                 'route_ids': list(dict.fromkeys(route for hit in paper.get('discovery_provenance', [])
                                                for route in hit['route_ids']))}
                for paper in payload['papers'][:payload['max_papers']]]}
        elif task.stage == 'extract':
            quote = payload['excerpt'].splitlines()[0]
            output = {'observations': [{'statement': quote, 'quote': quote, 'kind': 'author_claim',
                'conditions': 'Synthetic fixture only.', 'source_section': 'Supplied text'}]}
        elif task.stage == 'explore_problems':
            output = {'background_logic': 'Compare the supplied mechanisms.',
                      'approach_landscape': [], 'problem_seeds': []}
        elif task.stage == 'map':
            output = {'approach_landscape': [], 'problem_comparisons': [], 'research_frame': {'user_goal': payload['topic'],
                'literature_logic': 'Compare the supplied mechanisms.',
                'research_question': 'Which mechanism explains the difficulty?',
                'scope_connection': 'The sources inform the original objective.'},
                'problem': 'Synthetic flow fixture.', 'observations': [], 'competing_explanations': [],
                'unresolved_questions': [], 'opportunity_types': [], 'opportunities': [],
                'evidence_ids': [item['id'] for item in payload['evidence']], 'selected_problems': []}
        elif task.stage == 'propose':
            output = {'candidates': [], 'no_candidate_reason': 'This fixture tests the reading handoff only.'}
        else:
            raise AssertionError('Unexpected task: ' + task.stage)
        return BackendResult(output)


class DiscoveryFlowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.temp.name))
        self.store.set('topic', '让模型更好地使用已有信息')
        self.config = dict(DEFAULTS, backend='api', builtin_skills=False, auto_search=True,
                           fetch_full_text=False, deep_reading=False, max_papers=6,
                           max_calls=50, max_seconds=60)
        self.backend = DiscoveryBackend()

    def tearDown(self):
        self.store.close()
        self.temp.cleanup()

    def controller(self, **changes):
        return Controller(self.store, self.backend, dict(self.config, **changes))

    def seed_searches(self):
        plan = discovery_plan()
        self.store.set('search_plans', {'initial': plan})
        def metadata(identifier, title, aliases=None):
            return normalize_paper({'id': identifier, 'title': title, 'abstract': '',
                                    'aliases': aliases or [identifier], 'source': 'synthetic_fixture'})
        shared_a = metadata('shared-a', 'Shared information mechanism', ['shared-a', 'common-identity'])
        shared_b = metadata('shared-b', 'Shared information mechanism', ['shared-b', 'common-identity'])
        pools = [[shared_a, metadata('only-a', 'Information acquisition models')],
                 [shared_b, metadata('only-b', 'Conditional information use')], []]
        ledger = {route: {'query': query['query'], 'reason': query['rationale'], 'status': 'completed',
                          'source': 'synthetic_fixture', 'metadata': papers}
                  for route, query, papers in zip(('a', 'b', 'c'), plan['queries'], pools)}
        self.store.set('search_ledger', ledger)
        return plan, ledger

    def select(self, enrich=None):
        if enrich is None:
            enrich = lambda pool, **_: (pool, {'attempted': 0, 'enriched': 0, 'pages': []})
        with patch('research_idea.controller.enrich_screening_pool', side_effect=enrich):
            self.controller().select_search_results(['a', 'b', 'c'], 3)
        return next(payload for stage, payload in self.backend.calls if stage == 'screen_papers')

    def test_search_plan_receives_original_topic_and_user_followups(self):
        notes = ['优先理解不同原因。', '也允许参考相邻的计算机领域。']
        self.store.set('chat_messages', [{'role': 'user', 'content': notes[0]},
            {'role': 'assistant', 'content': 'An earlier assistant suggestion.'},
            {'role': 'user', 'content': notes[1]}])
        plan = self.controller().plan_search()
        stage, payload = self.backend.calls[0]
        self.assertEqual(stage, 'plan_search')
        self.assertEqual(payload['topic'], self.store.get('topic'))
        self.assertEqual(payload['user_notes'], notes)
        self.assertEqual(plan['research_routes'], discovery_plan()['research_routes'])
        self.assertEqual(self.store.get('search_plans')['initial'], plan)

    def test_real_query_provenance_reaches_screen_and_saved_paper_context(self):
        plan, _ = self.seed_searches()
        payload = self.select()
        self.assertEqual(payload['discovery_plan'], plan)
        shared = next(paper for paper in payload['papers'] if paper['title'] == 'Shared information mechanism')
        self.assertEqual(shared['discovery_provenance'], [
            {'query': plan['queries'][0]['query'], 'route_ids': ['a']},
            {'query': plan['queries'][1]['query'], 'route_ids': ['b']}])
        self.assertEqual(len(payload['papers']), 3)
        saved = {paper['id']: paper for paper in self.store.rows('papers')}
        contextual = {paper['id']: paper for paper in self.controller().context()['papers']}
        for paper in payload['papers']:
            stored = saved[paper['id']]
            expected = list(dict.fromkeys(route for hit in paper['discovery_provenance'] for route in hit['route_ids']))
            self.assertEqual(stored['selection']['route_ids'], expected)
            self.assertEqual(stored['selection']['phase'], 'ideation')
            self.assertEqual(stored['discovery_provenance'], paper['discovery_provenance'])
            self.assertEqual(contextual[paper['id']]['selection'], stored['selection'])
            self.assertEqual(contextual[paper['id']]['discovery_provenance'], paper['discovery_provenance'])

    def test_metadata_enrichment_preserves_provenance_in_screen_storage_and_ledger(self):
        self.seed_searches()
        incoming = []
        def enrich(pool, **_):
            incoming.extend(copy.deepcopy(pool))
            return ([dict(paper, abstract='A newly retrieved source abstract.',
                          abstract_source='synthetic_page') for paper in pool],
                    {'attempted': len(pool), 'enriched': len(pool), 'pages': []})
        payload = self.select(enrich)
        origins = {paper['id']: paper['discovery_provenance'] for paper in incoming}
        for paper in payload['papers']:
            self.assertEqual(paper['discovery_provenance'], origins[paper['id']])
            self.assertEqual(paper['abstract'], 'A newly retrieved source abstract.')
        for paper in self.store.rows('papers'):
            self.assertEqual(paper['discovery_provenance'], origins[paper['id']])
            self.assertEqual(paper['abstract_source'], 'synthetic_page')
        for entry in self.store.get('search_ledger').values():
            self.assertTrue(all(paper['abstract'] == 'A newly retrieved source abstract.' for paper in entry['metadata']))
        self.assertEqual(self.store.get('paper_selections')[-1]['metadata_enrichment']['enriched'], 3)

    def test_route_coverage_is_saved_in_audit_and_ideation_context_including_empty_route(self):
        self.seed_searches()
        self.select()
        coverage = self.store.get('discovery_coverage')
        by_route = {item['route_id']: item for item in coverage}
        shared = next(p['id'] for p in self.store.rows('papers') if p['title'] == 'Shared information mechanism')
        for route, exclusive in [('a', 'only-a'), ('b', 'only-b')]:
            self.assertEqual(set(by_route[route]['recalled_paper_ids']), {shared, exclusive})
            self.assertEqual(set(by_route[route]['selected_paper_ids']), {shared, exclusive})
        self.assertEqual(by_route['c']['recalled_paper_ids'], [])
        self.assertEqual(by_route['c']['selected_paper_ids'], [])
        self.assertEqual(self.store.get('paper_selections')[-1]['route_coverage'], coverage)
        contextual = self.controller().ideation_context()['discovery_coverage']
        self.assertEqual([{key: route[key] for key in saved} for route, saved in zip(contextual, coverage)], coverage)

    def test_later_discovery_keeps_existing_paper_routes_and_accumulated_coverage(self):
        self.seed_searches()
        self.select()
        previous = {paper['id']: paper for paper in self.store.rows('papers')}
        previous_coverage = {item['route_id']: item for item in self.store.get('discovery_coverage')}
        ledger = self.store.get('search_ledger')
        ledger['c']['metadata'] = [normalize_paper({'id': 'only-c', 'title': 'Changing environment feedback',
                                                    'source': 'synthetic_fixture'})]
        self.store.set('search_ledger', ledger)
        self.select()
        current = {paper['id']: paper for paper in self.store.rows('papers')}
        for identifier, paper in previous.items():
            self.assertEqual(current[identifier]['selection']['route_ids'], paper['selection']['route_ids'])
            self.assertEqual(current[identifier]['selection']['phase'], 'ideation')
            self.assertEqual(current[identifier]['discovery_provenance'], paper['discovery_provenance'])
        coverage = {item['route_id']: item for item in self.store.get('discovery_coverage')}
        for route in ('a', 'b'):
            self.assertEqual(set(coverage[route]['selected_paper_ids']),
                             set(previous_coverage[route]['selected_paper_ids']))
        self.assertEqual(coverage['c']['selected_paper_ids'], ['only-c'])

    def test_existing_paper_recalled_by_a_new_route_gains_provenance_and_recall_coverage(self):
        plan, _ = self.seed_searches()
        self.select()
        shared = next(paper for paper in self.store.rows('papers')
                      if paper['title'] == 'Shared information mechanism')
        ledger = self.store.get('search_ledger')
        ledger['c']['metadata'] = [normalize_paper({
            'id': shared['id'], 'title': shared['title'], 'aliases': shared['aliases'],
            'source': 'synthetic_fixture'})]
        self.store.set('search_ledger', ledger)
        calls_before = len(self.backend.calls)
        self.select()
        self.assertEqual(len(self.backend.calls), calls_before)
        updated = next(paper for paper in self.store.rows('papers') if paper['id'] == shared['id'])
        self.assertEqual(updated['discovery_provenance'], [
            {'query': query['query'], 'route_ids': query['route_ids']} for query in plan['queries']])
        self.assertEqual(updated['selection'], shared['selection'])
        coverage = {item['route_id']: item for item in self.store.get('discovery_coverage')}
        self.assertIn(shared['id'], coverage['c']['recalled_paper_ids'])
        self.assertEqual(coverage['c']['selected_paper_ids'], [])
        self.assertEqual(self.store.get('paper_selections')[-1]['semantic_pool_ids'], [])

    def test_initial_search_reserves_two_thirds_of_reading_capacity_rounded_up(self):
        for total in (1, 2, 3, 4, 6, 10):
            with self.subTest(max_papers=total):
                controller = self.controller(max_papers=total)
                with patch.object(controller, 'plan_search', return_value=discovery_plan()), \
                     patch.object(controller, 'search_once', side_effect=lambda query, *args, **kwargs: query), \
                     patch.object(controller, 'select_search_results') as choose:
                    controller.initial_search()
                self.assertEqual(choose.call_args.args[1], (2 * total + 2) // 3)

    def test_reasoning_coverage_distinguishes_selected_downloaded_and_read_sources(self):
        papers = [normalize_paper({'id': pid, 'title': pid, 'text': 'Synthetic source statement.',
                   'content_kind': kind}) for pid, kind in
                  [('read', 'full_text'), ('unread', 'full_text'), ('abstract', 'abstract')]]
        papers[-1]['full_text_error'] = 'HTTP 404'
        for paper in papers:
            self.store.put('papers', paper)
        selected = [paper['id'] for paper in papers]
        coverage = [{'route_id': 'a', 'question': 'A research inquiry.',
                     'recalled_paper_ids': selected, 'selected_paper_ids': selected}]
        self.store.set('discovery_coverage', coverage)
        controller = self.controller(auto_search=False)
        controller.extract_papers(selected_ids=['read'])
        route = controller.ideation_context()['discovery_coverage'][0]
        self.assertEqual(route['full_text_paper_ids'], ['read', 'unread'])
        self.assertEqual(route['full_text_read_paper_ids'], ['read'])
        self.assertEqual(route['abstract_only_paper_ids'], ['abstract'])
        self.assertEqual(route['retrieval_failed_paper_ids'], ['abstract'])
        self.assertEqual(self.store.get('discovery_coverage'), coverage)

    def seed_legacy_phases(self):
        for identifier in ('initial', 'shared', 'design', 'marked-design', 'manual'):
            paper = normalize_paper({'id': identifier, 'title': 'Synthetic ' + identifier,
                'content_kind': 'notes', 'text': 'This is a synthetic source statement for ' + identifier + '.'})
            if identifier == 'marked-design':
                paper['selection'] = {'phase': 'design'}
            self.store.put('papers', paper)
        self.store.set('cohort', {'key': 'old-cohort', 'initial_paper_ids': ['initial', 'shared', 'missing'],
                                 'proposed': {'candidates': [], 'no_candidate_reason': 'Legacy fixture.'}})
        self.store.put('candidates', {'id': 'old-idea', 'retrieved_work_ids': ['shared', 'design']})

    def test_legacy_cohort_recovers_initial_sources_without_adopting_design_sources(self):
        self.seed_legacy_phases()
        controller = self.controller(auto_search=False)
        self.assertEqual(set(controller.initial_paper_ids()), {'initial', 'shared', 'manual'})
        self.assertEqual({paper['id'] for paper in controller.ideation_context()['papers']},
                         {'initial', 'shared', 'manual'})
        self.assertEqual({paper['id'] for paper in controller.context()['papers']},
                         {'initial', 'shared', 'manual', 'design', 'marked-design'})

    def test_run_reads_only_initial_sources_before_map_even_with_old_design_corpus(self):
        self.seed_legacy_phases()
        self.controller(auto_search=False).run()
        read_ids = {payload['paper_id'] for stage, payload in self.backend.calls if stage == 'extract'}
        self.assertEqual(read_ids, {'initial', 'shared', 'manual'})
        mapped = next(payload for stage, payload in self.backend.calls if stage == 'map')
        self.assertEqual({paper['id'] for paper in mapped['papers']}, read_ids)
        self.assertEqual({item['paper_id'] for item in mapped['evidence']}, read_ids)
        self.assertEqual(set(self.store.get('cohort')['initial_paper_ids']), read_ids)
        self.assertEqual(self.store.get('status'), 'completed')

    def test_legacy_design_isolation_survives_archiving_the_old_candidate(self):
        self.seed_legacy_phases()
        self.controller(auto_search=False).run()
        self.assertEqual(self.store.rows('candidates'), [])
        resumed = self.controller(auto_search=False)
        self.assertEqual(set(resumed.initial_paper_ids()), {'initial', 'shared', 'manual'})
        resumed.run()
        read_ids = {payload['paper_id'] for stage, payload in self.backend.calls if stage == 'extract'}
        self.assertEqual(read_ids, {'initial', 'shared', 'manual'})
        self.assertEqual({paper['id'] for paper in resumed.ideation_context()['papers']}, read_ids)


if __name__ == '__main__':
    unittest.main()
