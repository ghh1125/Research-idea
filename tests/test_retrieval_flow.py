"""Retrieval boundaries: conference selection, source upgrades, and honest gaps."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from research_idea.config import DEFAULTS
from research_idea.backend_types import BackendResult
from research_idea.controller import BudgetExhausted, Controller
from research_idea.literature import LiteratureError, normalize_paper, FULL_TEXT_STRATEGY_VERSION
from research_idea.report import export_report
from research_idea.store import Store, digest


class ScreeningBackend:
    name = "test"

    def generate(self, task):
        if task.stage != 'screen_papers':
            raise AssertionError('Retrieval may only call metadata screening')
        data = json.loads(task.prompt.split('BEGIN_RESEARCH_DATA\n')[1].split('\nEND_RESEARCH_DATA')[0])
        return BackendResult({'selection_summary': 'Read the conflict study.',
            'selected': [{'paper_id': p['id'], 'reason': 'Relevant conflict problem.',
                          'reading_question': 'How is conflicting evidence controlled?', 'route_ids': []}
                         for p in data['papers'][:data['max_papers']]]})


class RetrievalFlowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.temp.name))
        self.store.set("topic", "Evidence conflicts")
        self.config = dict(DEFAULTS, backend="codex", auto_search=True,
                           fetch_full_text=True, search_source="openalex",
                           search_venues=["EMNLP", "NAACL", "COLM"])
        self.paper = normalize_paper({"id": "paper-1", "title": "Evidence conflicts",
                                     "abstract": "An abstract only.", "venue": "EMNLP",
                                     "url": "https://aclanthology.org/2024.emnlp-main.1/"})

    def tearDown(self):
        self.store.close()
        self.temp.cleanup()

    def controller(self, **overrides):
        return Controller(self.store, ScreeningBackend(), dict(self.config, **overrides))

    def test_venue_filter_and_full_text_are_used_and_cached(self):
        full = dict(self.paper, content_kind="full_text", text="Methods\nActual extracted source.")
        with patch("research_idea.literature.discover", return_value=[self.paper]) as search, \
             patch("research_idea.literature.fetch_full_text", return_value=full) as fetch:
            controller = self.controller()
            self.assertTrue(controller.search_once("conflicts", "closest methods"))
            self.assertFalse(controller.search_once("conflicts", "cached"))
            controller.retrieve_full_texts()
        self.assertEqual(search.call_args.kwargs["venues"], ["EMNLP", "NAACL", "COLM"])
        self.assertEqual(fetch.call_count, 1)
        self.assertEqual(self.store.rows("papers")[0]["content_kind"], "full_text")
        ledger = list(self.store.get("search_ledger").values())[0]
        self.assertEqual(ledger["source"], "openalex")
        self.assertEqual(ledger["found"], 1)
        self.assertEqual(self.store.get("calls_used"), 1)

    def test_failed_full_text_remains_abstract_with_reported_gap(self):
        with patch("research_idea.literature.discover", return_value=[self.paper]), \
             patch("research_idea.literature.fetch_full_text", side_effect=LiteratureError("PDF unavailable")) as fetch:
            controller = self.controller()
            controller.search_once("conflicts", "initial")
            controller.retrieve_full_texts()
        self.assertEqual(fetch.call_count, 1)
        paper = self.store.rows("papers")[0]
        self.assertEqual(paper["content_kind"], "abstract")
        self.assertNotIn("text", paper)
        self.assertEqual(paper["full_text_error"], "PDF unavailable")
        self.assertEqual(controller.context()["retrieval_gaps"][0]["status"], "failed")
        md, js = export_report(self.store, self.store.project)
        self.assertIn("PDF unavailable", md.read_text())
        self.assertIn("EMNLP", md.read_text())
        self.assertEqual(len(json.loads(js.read_text())["full_text_ledger"]), 1)

    def test_latest_conference_download_time_respects_project_budget(self):
        cases = [({}, 1000, 120), ({'conference_policy': 'window'}, 1000, 60),
                 ({'search_source': 'arxiv', 'search_venues': []}, 1000, 60),
                 ({}, 12, 12)]
        for i, (settings, remaining, expected) in enumerate(cases):
            with self.subTest(settings=settings, remaining=remaining):
                controller = self.controller(**settings)
                with patch.object(controller, 'check_budget', return_value=remaining), \
                     patch('research_idea.literature.discover', return_value=[]) as search:
                    controller.search_once(f'query {i}', 'budget regression', max_new=0)
                self.assertEqual(search.call_args.kwargs['timeout_s'], expected)

    def test_full_text_retry_is_bounded_across_invocations(self):
        self.store.put("papers", self.paper)
        with patch("research_idea.literature.fetch_full_text", side_effect=LiteratureError("PDF unavailable")) as fetch:
            for _ in range(3):
                self.controller().retrieve_full_texts()
        self.assertEqual(fetch.call_count, 2)

    def test_legacy_exhausted_failure_gets_new_strategy_without_resetting_budget(self):
        self.store.put('papers', self.paper)
        legacy_key = digest([self.paper['id'], self.paper.get('url'),
                             self.paper.get('pdf_url'), self.paper.get('locations')])
        previous = {'paper_id': self.paper['id'], 'status': 'failed',
                    'attempts': 2, 'error': 'Old resolver returned HTTP 404'}
        self.store.set('full_text_ledger', {legacy_key: previous})
        self.store.set('calls_used', 7)
        self.store.set('elapsed_s', 12)
        full = dict(self.paper, content_kind='full_text', text='Recovered public source.')
        with patch('research_idea.literature.fetch_full_text', return_value=full) as fetch:
            self.assertTrue(self.controller().retrieve_full_texts())
            self.assertFalse(self.controller().retrieve_full_texts())
        fetch.assert_called_once()
        ledger = self.store.get('full_text_ledger')
        self.assertEqual(ledger[legacy_key], previous)
        current = next(entry for key, entry in ledger.items() if key != legacy_key)
        self.assertEqual(current['strategy_version'], FULL_TEXT_STRATEGY_VERSION)
        self.assertEqual(current['attempts'], 1)
        self.assertEqual(current['status'], 'completed')
        self.assertEqual(self.store.get('calls_used'), 7)
        self.assertGreaterEqual(self.store.get('elapsed_s'), 12)

    def test_two_failures_remain_exhausted_until_strategy_changes(self):
        self.store.put('papers', self.paper)
        with patch('research_idea.literature.fetch_full_text', side_effect=LiteratureError('PDF unavailable')) as fetch:
            for _ in range(3):
                self.controller().retrieve_full_texts()
            self.assertEqual(fetch.call_count, 2)
            with patch('research_idea.literature.FULL_TEXT_STRATEGY_VERSION', FULL_TEXT_STRATEGY_VERSION + 1):
                for _ in range(3):
                    self.controller().retrieve_full_texts()
            self.assertEqual(fetch.call_count, 4)
        entries = list(self.store.get('full_text_ledger').values())
        self.assertEqual(len(entries), 2)
        self.assertTrue(all(entry['attempts'] == 2 for entry in entries))
        self.assertEqual({entry['strategy_version'] for entry in entries},
                         {FULL_TEXT_STRATEGY_VERSION, FULL_TEXT_STRATEGY_VERSION + 1})

    def test_strategy_change_keeps_existing_full_text_without_redownload(self):
        full = dict(self.paper, content_kind='full_text', text='Already acquired source.')
        self.store.put('papers', full)
        with patch('research_idea.literature.FULL_TEXT_STRATEGY_VERSION', FULL_TEXT_STRATEGY_VERSION + 1), \
             patch('research_idea.literature.fetch_full_text') as fetch:
            self.assertFalse(self.controller().retrieve_full_texts())
        fetch.assert_not_called()
        self.assertEqual(self.store.rows('papers')[0], full)

    def test_new_strategy_still_respects_exhausted_project_budget(self):
        self.store.put('papers', self.paper)
        self.store.set('calls_used', self.config['max_calls'])
        with patch('research_idea.literature.fetch_full_text') as fetch:
            with self.assertRaises(BudgetExhausted):
                self.controller().retrieve_full_texts()
        fetch.assert_not_called()
        self.assertEqual(self.store.get('calls_used'), self.config['max_calls'])
        self.assertEqual(self.store.get('full_text_ledger', {}), {})

    def test_recovered_or_removed_source_is_not_a_current_retrieval_gap(self):
        self.store.put('papers', self.paper)
        self.store.set('full_text_ledger', {
            'old': {'paper_id': self.paper['id'], 'status': 'failed', 'error': 'HTTP 403'},
            'removed': {'paper_id': 'no-longer-selected', 'status': 'failed', 'error': 'HTTP 404'},
        })
        self.assertEqual(len(self.controller().context()['retrieval_gaps']), 1)
        self.store.put('papers', dict(self.paper, content_kind='full_text', text='Recovered source text.'))
        self.assertEqual(self.controller().context()['retrieval_gaps'], [])
        self.assertEqual(len(self.store.get('full_text_ledger')), 2)

    def test_enriched_download_url_does_not_retry_the_same_failure_in_one_run(self):
        source = dict(self.paper, source='official_proceedings')
        self.store.put('papers', source)
        enriched = dict(source, pdf_url='https://aclanthology.org/2024.emnlp-main.1.pdf')
        with patch('research_idea.proceedings.enrich_selected', return_value=enriched), \
             patch('research_idea.literature.fetch_full_text', side_effect=LiteratureError('HTTP 403')) as fetch:
            controller = self.controller()
            controller.retrieve_full_texts()
            controller.retrieve_full_texts()
        self.assertEqual(fetch.call_count, 1)
        self.assertEqual(self.store.rows('papers')[0]['pdf_url'], enriched['pdf_url'])

    def test_metadata_access_failure_still_attempts_public_full_text(self):
        source = dict(self.paper, source='official_proceedings')
        self.store.put('papers', source)
        full = dict(source, content_kind='full_text', text='Text from the matched public source.')
        with patch('research_idea.proceedings.enrich_selected', side_effect=LiteratureError('HTTP 403')), \
             patch('research_idea.literature.fetch_full_text', return_value=full) as fetch:
            self.assertTrue(self.controller().retrieve_full_texts())
        self.assertEqual(fetch.call_count, 1)
        self.assertEqual(self.store.rows('papers')[0]['content_kind'], 'full_text')
        entry = next(iter(self.store.get('full_text_ledger').values()))
        self.assertEqual(entry['metadata_error'], 'HTTP 403')
        self.assertEqual(entry['status'], 'completed')

    def test_imported_only_and_disabled_fetch_do_not_access_network(self):
        self.store.put("papers", self.paper)
        with patch("research_idea.literature.fetch_full_text") as fetch:
            self.controller(auto_search=False).retrieve_full_texts()
            self.controller(fetch_full_text=False).retrieve_full_texts()
            self.controller(backend="demo").retrieve_full_texts()
        fetch.assert_not_called()

    def test_venue_selection_changes_search_cache_identity(self):
        with patch("research_idea.literature.discover", return_value=[]) as search:
            self.controller(fetch_full_text=False).search_once("conflicts", "first")
            self.controller(fetch_full_text=False, search_venues=["ACL"]).search_once("conflicts", "changed venues")
        self.assertEqual(search.call_count, 2)

    def test_incomplete_search_coverage_reaches_model_context_and_report(self):
        self.store.set("manual_search_ledger", [{"query": "conflicts", "source": "openalex",
            "venues": ["EMNLP"], "status": "completed", "found": 0,
            "coverage": {"gaps": ["EMNLP source could not be resolved"]}}])
        context = self.controller().context()
        self.assertEqual(context["search_coverage"][0]["coverage"]["gaps"], ["EMNLP source could not be resolved"])
        md, _ = export_report(self.store, self.store.project)
        self.assertIn("EMNLP source could not be resolved", md.read_text())

    def test_full_text_budget_exhaustion_is_not_swallowed(self):
        with patch("research_idea.literature.discover", return_value=[self.paper]), \
             patch.object(Controller, "retrieve_full_texts", side_effect=BudgetExhausted("spent")):
            with self.assertRaises(BudgetExhausted):
                self.controller().search_once("conflicts", "initial")

    def test_rediscovery_updates_metadata_without_duplicating_known_paper(self):
        self.store.put("papers", self.paper)
        with patch("research_idea.literature.discover", return_value=[dict(self.paper, doi="10.1234/abc")]):
            self.controller(fetch_full_text=False).search_once("conflicts", "metadata update")
        records = self.store.rows("papers")
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["id"], "paper-1")
        self.assertEqual(records[0]["doi"], "10.1234/abc")


if __name__ == "__main__":
    unittest.main()
