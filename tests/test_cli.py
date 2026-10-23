"""End-to-end offline CLI and interrupted-project recovery tests."""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from research_agent.cli import import_papers
from research_agent.config import DEFAULTS
from research_agent.controller import Controller, BudgetExhausted, select_excerpt, make_evidence
from research_agent.demo import DEMO_PAPERS, DEMO_TOPIC, DemoBackend
from research_agent.store import Store

ROOT = Path(__file__).resolve().parents[1]


class CLIIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.project = Path(self.tmp.name) / "project"

    def tearDown(self):
        self.tmp.cleanup()

    def call(self, *args):
        env = dict(os.environ, PYTHONPATH=str(ROOT / "src"))
        return subprocess.run([sys.executable, "-m", "research_agent", *map(str, args)], env=env,
                              capture_output=True, text=True, timeout=20)

    def test_demo_and_resume_are_explicit_and_do_not_repeat_calls(self):
        first = self.call("demo", "--project", self.project)
        self.assertEqual(first.returncode, 0, first.stderr)
        report = json.loads((self.project / "outputs/report.json").read_text())
        self.assertTrue(report["demo"])
        self.assertEqual(len(report["candidates"]), 2)
        self.assertTrue(all(c["empirical_status"] == "untested" for c in report["candidates"]))
        self.assertIn("合成演示", (self.project / "outputs/report.md").read_text())
        second = self.call("resume", "--project", self.project)
        self.assertEqual(second.returncode, 0, second.stderr)
        resumed = json.loads((self.project / "outputs/report.json").read_text())
        self.assertEqual(resumed["calls_used"], report["calls_used"])
        self.assertEqual([c["id"] for c in resumed["candidates"]], [c["id"] for c in report["candidates"]])

    def test_new_source_invalidates_cohort_without_losing_archive(self):
        self.assertEqual(self.call("demo", "--project", self.project).returncode, 0)
        notes = self.project.parent / "new.txt"
        notes.write_text("This additional synthetic note describes a new diagnostic control.\nNo real experiment has been performed.")
        added = self.call("add", "--project", self.project, notes)
        self.assertEqual(added.returncode, 0, added.stderr)
        result = self.call("resume", "--project", self.project)
        self.assertEqual(result.returncode, 0, result.stderr)
        store = Store(self.project)
        try:
            self.assertEqual(len(store.rows("papers")), 3)
            archived = store.db.execute("SELECT COUNT(*) FROM events WHERE kind='cohort_archived'").fetchone()[0]
            self.assertEqual(archived, 1)
        finally:
            store.close()

    def test_unknown_project_and_topic_conflict_are_errors(self):
        self.assertNotEqual(self.call("status", "--project", self.project).returncode, 0)
        self.assertEqual(self.call("init", "topic A", "--project", self.project).returncode, 0)
        conflict = self.call("init", "topic B", "--project", self.project)
        self.assertNotEqual(conflict.returncode, 0)
        self.assertIn("different topic", conflict.stderr)

    def test_bad_config_fails_before_backend(self):
        self.call("init", "topic A", "--project", self.project)
        (self.project / "research.toml").write_text('unknown_key = "bad"\n')
        result = self.call("run", "--project", self.project, "--no-search")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Unknown configuration", result.stderr)

    def test_experiment_check_only_does_not_execute(self):
        self.call("init", "topic", "--project", self.project)
        marker = self.project.parent / "executed.txt"
        spec = self.project.parent / "experiment.json"
        spec.write_text(json.dumps({"argv": [sys.executable, "-c", "from pathlib import Path; Path('executed.txt').touch()"], "cwd": ".", "timeout_s": 2}))
        result = self.call("experiment", "--project", self.project, spec, "--check-only")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(marker.exists())

    def test_real_project_cannot_be_overwritten_by_demo(self):
        self.call("init", "real topic", "--project", self.project)
        result = self.call("demo", "--project", self.project)
        self.assertNotEqual(result.returncode, 0)
        store = Store(self.project)
        try:
            self.assertEqual(store.get("topic"), "real topic")
            self.assertEqual(store.rows("papers"), [])
        finally:
            store.close()


class RecoveryTests(unittest.TestCase):
    def test_budget_resume_keeps_cohort_when_internal_evidence_grows(self):
        with tempfile.TemporaryDirectory() as temp:
            store = Store(Path(temp))
            try:
                store.set("topic", DEMO_TOPIC)
                import_papers(store, DEMO_PAPERS)
                cfg = dict(DEFAULTS, backend="demo", auto_search=False, max_calls=7, max_seconds=120)
                with self.assertRaises(BudgetExhausted):
                    Controller(store, DemoBackend(), cfg).run()
                original_ids = [c["id"] for c in store.rows("candidates")]
                # Simulate retrieval performed inside the controller, not an explicit replan.
                store.put("papers", {"id": "internal-new", "title": "Synthetic added evidence", "content_kind": "notes", "text": "This is synthetic material only.\nAn additional diagnostic can be tested under matched computation budgets."})
                Controller(store, DemoBackend(), dict(cfg, max_calls=40)).run()
                self.assertEqual(original_ids, [c["id"] for c in store.rows("candidates")])
                self.assertEqual(store.get("status"), "completed")
            finally:
                store.close()

    def test_failed_discovery_has_bounded_retry(self):
        with tempfile.TemporaryDirectory() as temp:
            store = Store(Path(temp))
            try:
                cfg = dict(DEFAULTS, backend="api", auto_search=True, max_seconds=60)
                controller = Controller(store, DemoBackend(), cfg)
                with patch("research_agent.literature.discover", side_effect=[OSError("temporary"), [dict(DEMO_PAPERS[0])]]) as lookup:
                    self.assertFalse(controller.search_once("query", "test"))
                    self.assertTrue(controller.search_once("query", "retry"))
                    self.assertFalse(controller.search_once("query", "cached"))
                    self.assertEqual(lookup.call_count, 2)
            finally:
                store.close()

    def test_section_selection_reaches_results_and_uses_original_offsets(self):
        text = "Introduction\n" + "a " * 2000 + "\nMethods\n" + "b " * 2000 + "\nResults\nThe signal fails when evaluation conditions change.\n" + "c " * 2000
        excerpt = select_excerpt(text, 1800)
        quote = "The signal fails when evaluation conditions change."
        self.assertIn(quote, excerpt)
        paper = {"id": "p", "text": text, "content_kind": "full_text"}
        observation = {"statement": "Conditional failure", "quote": quote, "kind": "reported_result", "conditions": "evaluation changed", "source_section": "Results"}
        evidence = make_evidence(paper, [observation], excerpt)[0]
        self.assertEqual(evidence["start"], text.index(quote))
        self.assertEqual(evidence["reading_coverage"], "partial")


if __name__ == "__main__":
    unittest.main()
