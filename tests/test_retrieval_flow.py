"""Retrieval boundaries: conference selection, source upgrades, and honest gaps."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from research_idea.config import DEFAULTS
from research_idea.controller import BudgetExhausted, Controller
from research_idea.literature import LiteratureError, normalize_paper
from research_idea.report import export_report
from research_idea.store import Store


class UnusedBackend:
    name = "test"

    def generate(self, task):
        raise AssertionError("Retrieval must not invoke a model")


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
        return Controller(self.store, UnusedBackend(), dict(self.config, **overrides))

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
        self.assertIsNone(self.store.get("calls_used"))

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
        md, js = export_report(self.store)
        self.assertIn("PDF unavailable", md.read_text())
        self.assertIn("EMNLP", md.read_text())
        self.assertEqual(len(json.loads(js.read_text())["full_text_ledger"]), 1)

    def test_full_text_retry_is_bounded_across_invocations(self):
        self.store.put("papers", self.paper)
        with patch("research_idea.literature.fetch_full_text", side_effect=LiteratureError("PDF unavailable")) as fetch:
            for _ in range(3):
                self.controller().retrieve_full_texts()
        self.assertEqual(fetch.call_count, 2)

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
        md, _ = export_report(self.store)
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
