"""Changed research inputs refresh discovery within the existing project budget."""
from __future__ import annotations

from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from research_idea.config import DEFAULTS
from research_idea.controller import BudgetExhausted, Controller
from research_idea.literature import normalize_paper
from research_idea.store import Store, digest
from test_discovery_flow import DiscoveryBackend


class RefreshBackend(DiscoveryBackend):
    def generate(self, task):
        result = super().generate(task)
        if task.stage == 'plan_search' and self.calls[-1][1]['user_notes']:
            for query in result.output['queries']:
                query['query'] += ' revised'
            for route in result.output['research_routes']:
                route['question'] = 'A new interpretation of route ' + route['id'] + '?'
                route['why_relevant'] = 'A different connection introduced by the follow-up.'
        return result


class DiscoveryRefreshTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.temp.name))
        self.store.set('topic', 'Understand different barriers to useful information use.')
        self.config = dict(DEFAULTS, backend='api', builtin_skills=False, auto_search=True,
                           fetch_full_text=False, deep_reading=False, max_papers=6,
                           max_calls=50, max_seconds=60)
        self.backend = RefreshBackend()
        self.progress = []
        self.enrichment = patch('research_idea.controller.enrich_screening_pool',
            side_effect=lambda pool, **_: (pool, {'attempted': 0, 'enriched': 0, 'pages': []}))
        self.enrichment.start()

    def tearDown(self):
        self.enrichment.stop()
        self.store.close()
        self.temp.cleanup()

    def controller(self, **changes):
        return Controller(self.store, self.backend, dict(self.config, **changes), progress=self.progress.append)

    def discover(self, query, **kwargs):
        return [normalize_paper({'id': digest([query, index])[:12], 'title': query + f' study {index}',
            'abstract': 'Synthetic source abstract for this retrieval fixture.', 'source': 'synthetic_fixture'})
            for index in range(3)]

    def seed_sources(self, count):
        for index in range(count):
            self.store.put('papers', normalize_paper({'id': f'existing-{index}',
                'title': f'Existing source {index}', 'content_kind': 'notes',
                'text': 'Synthetic previously supplied material.'}))

    def test_unchanged_input_resumes_without_new_model_or_network_calls(self):
        with patch('research_idea.literature.discover', side_effect=self.discover) as search:
            self.controller().initial_search()
        self.assertEqual(len(self.store.rows('papers')), 4)
        self.assertEqual(search.call_count, 3)
        self.assertEqual([stage for stage, _ in self.backend.calls], ['plan_search', 'screen_papers'])
        saved_key = self.store.get('discovery_input_key')
        calls_before = len(self.backend.calls)
        with patch('research_idea.literature.discover') as search:
            self.controller().initial_search()
        search.assert_not_called()
        self.assertEqual(len(self.backend.calls), calls_before)
        self.assertEqual(self.store.get('discovery_input_key'), saved_key)
        self.assertEqual(len(self.store.rows('papers')), 4)

    def test_changed_notes_use_remaining_room_after_initial_allocation_is_full(self):
        with patch('research_idea.literature.discover', side_effect=self.discover):
            self.controller().initial_search()
        before = {paper['id'] for paper in self.store.rows('papers')}
        previous_key = self.store.get('discovery_input_key')
        self.store.set('chat_messages', [{'role': 'user', 'content': 'Also investigate a different causal explanation.'}])
        with patch('research_idea.literature.discover', side_effect=self.discover) as search:
            self.controller().initial_search()
        self.assertEqual(search.call_count, 3)
        self.assertEqual(len(self.store.rows('papers')), 6)
        self.assertTrue(before <= {paper['id'] for paper in self.store.rows('papers')})
        self.assertNotEqual(self.store.get('discovery_input_key'), previous_key)
        plans = [payload for stage, payload in self.backend.calls if stage == 'plan_search']
        self.assertEqual(len(plans), 2)
        self.assertEqual(plans[-1]['user_notes'], ['Also investigate a different causal explanation.'])
        screens = [payload for stage, payload in self.backend.calls if stage == 'screen_papers']
        self.assertEqual([payload['max_papers'] for payload in screens], [4, 2])
        self.assertEqual(self.config['max_papers'], 6)

    def test_existing_sources_without_a_discovery_key_still_trigger_exploration(self):
        self.seed_sources(4)
        with patch('research_idea.literature.discover', side_effect=self.discover) as search:
            self.controller().initial_search()
        self.assertEqual(search.call_count, 3)
        self.assertEqual(len(self.store.rows('papers')), 6)
        self.assertEqual([stage for stage, _ in self.backend.calls], ['plan_search', 'screen_papers'])
        self.assertEqual(self.backend.calls[-1][1]['max_papers'], 2)

    def test_reusing_route_ids_does_not_relabel_old_readings_or_accumulate_old_coverage(self):
        with patch('research_idea.literature.discover', side_effect=self.discover):
            self.controller().initial_search()
        previous_plan = self.store.get('search_plans')['initial']
        previous_key = digest(previous_plan)
        old_ids = {paper['id'] for paper in self.store.rows('papers')}
        # Simulate a saved project from before reading-route snapshots existed.
        for paper in self.store.rows('papers'):
            paper['selection'].pop('discovery_plan_key')
            paper['selection'].pop('research_routes')
            self.store.put('papers', paper)
        old_coverage = self.store.get('discovery_coverage')
        for entry in old_coverage:
            entry.pop('discovery_plan_key')
        self.store.set('discovery_coverage', old_coverage)
        self.store.set('chat_messages', [{'role': 'user', 'content': 'Use a different explanation for the same objective.'}])
        with patch('research_idea.literature.discover', side_effect=self.discover):
            self.controller().initial_search()
        current_plan = self.store.get('search_plans')['initial']
        current_key = digest(current_plan)
        self.assertEqual([route['id'] for route in current_plan['research_routes']],
                         [route['id'] for route in previous_plan['research_routes']])
        self.assertNotEqual(current_key, previous_key)
        for paper in self.store.rows('papers'):
            selection = paper['selection']
            if paper['id'] in old_ids:
                self.assertEqual(selection['discovery_plan_key'], previous_key)
                self.assertEqual(selection['research_routes'], previous_plan['research_routes'])
                self.assertTrue(paper['discovery_provenance'])
                self.assertTrue(all(not hit['route_ids'] for hit in paper['discovery_provenance']))
            else:
                self.assertEqual(selection['discovery_plan_key'], current_key)
                self.assertEqual(selection['research_routes'], current_plan['research_routes'])
        for entry in self.store.get('discovery_coverage'):
            self.assertEqual(entry['discovery_plan_key'], current_key)
            self.assertFalse(old_ids.intersection(entry['recalled_paper_ids']))
            self.assertFalse(old_ids.intersection(entry['selected_paper_ids']))

    def test_run_with_a_larger_limit_adds_only_available_room_then_resumes_without_calls(self):
        with patch('research_idea.literature.discover', side_effect=self.discover):
            self.controller(max_papers=3).run()
        old_ids = {paper['id'] for paper in self.store.rows('papers')}
        self.assertEqual(len(old_ids), 2)
        with patch('research_idea.literature.discover') as search:
            self.controller(max_papers=5).run()
        search.assert_not_called()
        self.assertEqual(len(self.store.rows('papers')), 5)
        self.assertTrue(old_ids <= {paper['id'] for paper in self.store.rows('papers')})
        screens = [payload for stage, payload in self.backend.calls if stage == 'screen_papers']
        self.assertEqual([payload['max_papers'] for payload in screens], [2, 3])
        calls_before = len(self.backend.calls)
        with patch('research_idea.literature.discover') as search:
            self.controller(max_papers=5).run()
        search.assert_not_called()
        self.assertEqual(len(self.backend.calls), calls_before)
        self.assertEqual(len(self.store.rows('papers')), 5)
        self.assertEqual(self.store.get('status'), 'completed')

    def test_full_project_refreshes_metadata_without_new_reading_or_expanded_budget(self):
        self.seed_sources(6)
        before = self.store.rows('papers')
        with patch('research_idea.literature.discover', side_effect=self.discover) as search, \
             patch('research_idea.literature.fetch_full_text') as fetch:
            self.controller(fetch_full_text=True).initial_search()
        self.assertEqual(search.call_count, 3)
        fetch.assert_not_called()
        self.assertEqual([stage for stage, _ in self.backend.calls], ['plan_search'])
        self.assertEqual(self.store.rows('papers'), before)
        self.assertEqual(sum(len(entry['metadata']) for entry in self.store.get('search_ledger').values()), 9)
        coverage = self.store.get('discovery_coverage')
        self.assertEqual(len(coverage), 3)
        self.assertTrue(all(item['recalled_paper_ids'] for item in coverage))
        self.assertTrue(all(not item['selected_paper_ids'] for item in coverage))
        self.assertIn('不增加精读', '\n'.join(self.progress))
        self.assertTrue(self.store.get('discovery_input_key'))

    def test_interrupted_queries_resume_cached_plan_and_keep_the_original_reading_allocation(self):
        attempts = []
        def interrupt_second_query(query, **kwargs):
            attempts.append(query)
            if len(attempts) == 2:
                raise KeyboardInterrupt()
            return self.discover(query, **kwargs)
        with patch('research_idea.literature.discover', side_effect=interrupt_second_query):
            with self.assertRaises(KeyboardInterrupt):
                self.controller().initial_search()
        self.assertIsNone(self.store.get('discovery_input_key'))
        self.assertTrue(self.store.get('discovery_refresh'))
        with patch('research_idea.literature.discover', side_effect=self.discover) as search:
            self.controller().initial_search()
        self.assertEqual(search.call_count, 2)
        self.assertEqual([stage for stage, _ in self.backend.calls], ['plan_search', 'screen_papers'])
        self.assertEqual(len(self.store.rows('papers')), 4)
        self.assertIsNone(self.store.get('discovery_refresh'))

    def test_interruption_after_selection_does_not_allocate_a_second_batch_on_resume(self):
        controller = self.controller()
        with patch('research_idea.literature.discover', side_effect=self.discover), \
             patch.object(controller, 'retrieve_full_texts', side_effect=BudgetExhausted('Interrupted download')):
            with self.assertRaises(BudgetExhausted):
                controller.initial_search()
        self.assertEqual(len(self.store.rows('papers')), 4)
        self.assertTrue(self.store.get('discovery_input_key'))
        calls_before = len(self.backend.calls)
        with patch('research_idea.literature.discover') as search:
            self.controller().initial_search()
        search.assert_not_called()
        self.assertEqual(len(self.backend.calls), calls_before)
        self.assertEqual(len(self.store.rows('papers')), 4)


if __name__ == '__main__':
    unittest.main()
