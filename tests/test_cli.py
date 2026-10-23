"""End-to-end offline CLI and interrupted-project recovery tests."""
from __future__ import annotations

import json
import io
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from contextlib import chdir, redirect_stdout, redirect_stderr
from unittest.mock import patch

from research_idea.cli import collect_paper_files, import_papers, main
from research_idea.config import DEFAULTS, load_config, write_config
from research_idea.controller import Controller, BudgetExhausted, select_excerpt, make_evidence
from research_idea.demo import DEMO_PAPERS, DEMO_TOPIC, DemoBackend
from research_idea.literature import LiteratureError
from research_idea.store import Store

ROOT = Path(__file__).resolve().parents[1]


class CLIIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.project = Path(self.tmp.name) / "project"

    def tearDown(self):
        self.tmp.cleanup()

    def call(self, *args):
        env = dict(os.environ, PYTHONPATH=str(ROOT / "src"))
        return subprocess.run([sys.executable, "-m", "research_idea", *map(str, args)], env=env,
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
                with patch("research_idea.literature.discover", side_effect=[OSError("temporary"), [dict(DEMO_PAPERS[0])]]) as lookup:
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


class SetupAndSkillsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.base = Path(self.tmp.name)
        self.project = self.base / "project"
        self.skills_root = self.base / "skills"
        self.first_skill = self.make_skill("test-research-a", "Trace claims to evidence.")
        self.second_skill = self.make_skill("test-research-b", "Test the causal mechanism.")

    def tearDown(self):
        self.tmp.cleanup()

    def make_skill(self, name, content):
        path = self.skills_root / name / "SKILL.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"---\nname: {name}\ndescription: Local fixture\n---\n{content}\n", encoding="utf-8")
        return path

    def call(self, *args):
        stdout, stderr = io.StringIO(), io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            result = main([str(arg) for arg in args])
        return result, stdout.getvalue(), stderr.getvalue()

    def init(self, *extra):
        code, _, error = self.call("init", "主题", "--project", self.project, *extra)
        self.assertEqual(code, 0, error)

    def test_start_setup_only_imports_sources_without_invoking_backend(self):
        papers = self.base / "papers"
        (papers / "nested").mkdir(parents=True)
        (papers / "z.txt").write_text("Synthetic paper A. A method may fail in a shifted setting.")
        (papers / "nested/a.md").write_text("Synthetic paper B. Controlled observations are needed.")
        (papers / "records.json").write_text(json.dumps({"papers": [{"title": "Synthetic C", "abstract": "Some observation"}]}))
        (papers / "settings.json").write_text('{"api_key_env": "NOT_A_PAPER"}')
        (papers / "AGENTS.md").write_text("This is an instruction file, not a paper.")
        (papers / ".hidden.txt").write_text("Not a selected source.")
        with patch("research_idea.backends.make_backend") as backend, patch.object(Controller, "run") as run:
            code, out, error = self.call("start", "研究主题", "--project", self.project,
                                         "--papers", papers, "--setup-only", "--no-search",
                                         "--codex-bin", self.base / "uninstalled-codex")
        self.assertEqual(code, 0, error)
        self.assertEqual(json.loads(out)["papers"], 3)
        self.assertFalse(json.loads(out)["model_invoked"])
        self.assertIn("--no-search", json.loads(out)["next"])
        self.assertIn("Skipping non-paper JSON", error)
        backend.assert_not_called()
        run.assert_not_called()

    def test_start_noninteractive_missing_topic_is_actionable_and_does_not_initialize(self):
        with patch("sys.stdin.isatty", return_value=False), patch("builtins.input") as prompt:
            code, _, error = self.call("start", "--project", self.project, "--setup-only")
        self.assertEqual(code, 1)
        self.assertIn("requires TOPIC", error)
        self.assertFalse((self.project / "research.sqlite3").exists())
        prompt.assert_not_called()

    def test_start_interactive_topic_and_builtin_disable(self):
        with patch("sys.stdin.isatty", return_value=True), patch("builtins.input", return_value="交互主题"):
            code, out, error = self.call("start", "--project", self.project, "--setup-only", "--no-builtin-skills")
        self.assertEqual(code, 0, error)
        self.assertEqual(json.loads(out)["topic"], "交互主题")
        self.assertFalse(load_config(self.project)["builtin_skills"])

    def test_skills_list_show_use_and_clear(self):
        self.init()
        code, out, error = self.call("skills", "list", "--project", self.project, "--root", self.skills_root)
        self.assertEqual(code, 0, error)
        self.assertIn("test-research-a", [item["name"] for item in json.loads(out)["skills"]])
        code, out, error = self.call("skills", "show", self.first_skill)
        self.assertEqual(code, 0, error)
        self.assertIn("Trace claims", json.loads(out)["content"])
        code, out, error = self.call("skills", "use", "test-research-a", "test-research-b",
                                     "--project", self.project, "--root", self.skills_root)
        self.assertEqual(code, 0, error)
        cfg = load_config(self.project)
        self.assertEqual(cfg["skill_paths"], [str(self.first_skill.resolve()), str(self.second_skill.resolve())])
        self.assertEqual(cfg["skill_roots"], [str(self.skills_root.resolve())])
        self.assertNotIn("content", json.loads(out)["selected_skills"][0])
        code, out, error = self.call("skills", "clear", "--project", self.project)
        self.assertEqual(code, 0, error)
        self.assertEqual(load_config(self.project)["skill_paths"], [])
        self.assertTrue(load_config(self.project)["builtin_skills"])
        self.assertIn("remain enabled", json.loads(out)["note"])

    def test_invalid_skill_selection_does_not_mutate_config(self):
        self.init("--skill", self.first_skill)
        before = (self.project / "research.toml").read_bytes()
        code, _, error = self.call("skills", "use", self.base / "missing.md", "--project", self.project)
        self.assertEqual(code, 1)
        self.assertIn("does not exist", error)
        self.assertEqual((self.project / "research.toml").read_bytes(), before)

    def test_builtin_and_external_combined_budget_is_validated_before_saving(self):
        self.init()
        cfg = load_config(self.project)
        cfg["skill_max_chars"] = max(len(self.first_skill.read_text()), len(self.second_skill.read_text())) + 10
        write_config(self.project, cfg)
        before = (self.project / "research.toml").read_bytes()
        with patch("research_idea.cli.builtin_skill_paths", return_value=[str(self.first_skill)]):
            for command in [("skills", "use", self.second_skill), ("init", "主题", "--skill", self.second_skill)]:
                with self.subTest(command=command):
                    code, _, error = self.call(*command, "--project", self.project)
                    self.assertEqual(code, 1)
                    self.assertIn("max_chars", error)
                    self.assertEqual((self.project / "research.toml").read_bytes(), before)

    def test_cli_skill_paths_are_relative_to_working_directory(self):
        relative = self.first_skill.relative_to(self.base)
        with chdir(self.base):
            self.init("--skill", f"./{relative}")
            self.assertEqual(load_config(self.project)["skill_paths"], [str(self.first_skill)])
            code, out, error = self.call("skills", "show", f"./{relative}", "--project", self.project)
            self.assertEqual(code, 0, error)
            self.assertEqual(json.loads(out)["path"], str(self.first_skill))
            code, _, error = self.call("skills", "use", f"./{relative}", "--project", self.project)
            self.assertEqual(code, 0, error)
        cfg = load_config(self.project)
        cfg["skill_paths"] = ["../" + str(relative)]
        write_config(self.project, cfg)
        self.init()
        self.assertEqual(load_config(self.project)["skill_paths"], ["../" + str(relative)])

    def test_omitted_flags_preserve_settings_and_explicit_arrays_replace(self):
        self.init("--codex-bin", self.base / "local codex", "--codex-profile", "research",
                  "--skill", self.first_skill, "--skill-root", self.skills_root, "--no-builtin-skills")
        self.init()
        cfg = load_config(self.project)
        self.assertEqual(cfg["codex_bin"], str(self.base / "local codex"))
        self.assertEqual(cfg["codex_profile"], "research")
        self.assertEqual(cfg["skill_paths"], [str(self.first_skill)])
        self.assertFalse(cfg["builtin_skills"])
        self.init("--skill", self.second_skill, "--skill-root", self.second_skill.parent)
        cfg = load_config(self.project)
        self.assertEqual(cfg["skill_paths"], [str(self.second_skill)])
        self.assertEqual(cfg["skill_roots"], [str(self.second_skill.parent)])

    def test_run_and_resume_apply_settings_before_backend(self):
        self.init()
        for command in ("run", "resume"):
            with self.subTest(command=command), patch("research_idea.backends.make_backend") as factory, patch.object(Controller, "run"):
                code, _, error = self.call(command, "--project", self.project, "--no-search",
                                           "--codex-bin", "/custom/codex", "--codex-profile", "r",
                                           "--skill", self.first_skill, "--no-builtin-skills")
                self.assertEqual(code, 0, error)
                cfg = factory.call_args.args[0]
                self.assertEqual(cfg["codex_bin"], "/custom/codex")
                self.assertEqual(cfg["codex_profile"], "r")
                self.assertEqual(cfg["skill_paths"], [str(self.first_skill)])
                self.assertFalse(cfg["builtin_skills"])

    def test_doctor_reports_binary_and_skill_hashes_without_backend_calls(self):
        self.init("--codex-bin", "/custom/codex", "--skill", self.first_skill)
        with patch("research_idea.cli.shutil.which", side_effect=lambda name: "/custom/codex" if name == "/custom/codex" else None), patch("research_idea.backends.make_backend") as backend:
            code, out, error = self.call("doctor", "--project", self.project)
        self.assertEqual(code, 0, error)
        result = json.loads(out)
        self.assertEqual(result["codex_resolved_path"], "/custom/codex")
        selected = {item["name"]: item for item in result["selected_skills"]}
        self.assertEqual(len(selected["test-research-a"]["sha256"]), 64)
        self.assertNotIn("content", selected["test-research-a"])
        self.assertTrue(any(item.get("origin") == "builtin" for item in selected.values()))
        self.assertIn(str(self.project / ".codex/skills"), result["discovery_roots"])
        backend.assert_not_called()
        with patch("research_idea.cli.shutil.which", return_value=None):
            code, out, _ = self.call("doctor", "--project", self.project)
        self.assertEqual(code, 1)
        self.assertIn("--codex-bin", json.loads(out)["warnings"][0])

    def test_directory_import_is_sorted_deduplicated_and_bounded(self):
        papers = self.base / "paper-batch"
        papers.mkdir()
        for name in ("z.txt", "a.txt"):
            (papers / name).write_text("Source material")
        files = collect_paper_files([papers, papers / "a.txt"])
        self.assertEqual([path.name for path, _ in files], ["a.txt", "z.txt"])
        for index in range(99):
            (papers / f"{index:03}.txt").write_text("Source material")
        with self.assertRaisesRegex(ValueError, "100 paper files"):
            collect_paper_files([papers])


class SearchCLITests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.project = Path(self.tmp.name) / "project"
        code, _, error = self.call("init", "topic", "--project", self.project)
        self.assertEqual(code, 0, error)

    def tearDown(self):
        self.tmp.cleanup()

    def call(self, *args):
        stdout, stderr = io.StringIO(), io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            result = main([str(arg) for arg in args])
        return result, stdout.getvalue(), stderr.getvalue()

    def test_venue_settings_persist_and_omitted_flags_preserve_them(self):
        code, _, error = self.call("start", "topic", "--project", self.project, "--setup-only",
                                  "--venues", "ACL", "EMNLP", "NAACL", "COLM", "--no-fetch-full-text")
        self.assertEqual(code, 0, error)
        code, _, error = self.call("init", "topic", "--project", self.project)
        self.assertEqual(code, 0, error)
        cfg = load_config(self.project)
        self.assertEqual(cfg["search_source"], "openalex")
        self.assertEqual(cfg["search_venues"], ["ACL", "EMNLP", "NAACL", "COLM"])
        self.assertFalse(cfg["fetch_full_text"])
        with patch("research_idea.backends.make_backend") as factory, patch.object(Controller, "run"):
            code, _, error = self.call("run", "--project", self.project, "--no-search", "--venues", "ICML", "--fetch-full-text")
        self.assertEqual(code, 0, error)
        self.assertEqual(factory.call_args.args[0]["search_venues"], ["ICML"])
        self.assertTrue(load_config(self.project)["fetch_full_text"])

    def test_explicit_arxiv_with_venues_is_rejected_without_search_or_config_mutation(self):
        before = (self.project / "research.toml").read_bytes()
        for args in [("search", "query"), ("init", "topic")]:
            with self.subTest(command=args[0]), patch("research_idea.cli.discover") as search:
                code, _, error = self.call(*args, "--project", self.project,
                                          "--source", "arxiv", "--venues", "ACL")
            self.assertEqual(code, 1)
            self.assertIn("requires OpenAlex", error)
            search.assert_not_called()
            self.assertEqual((self.project / "research.toml").read_bytes(), before)

    def test_manual_venues_imply_openalex_and_full_text_is_opt_in(self):
        with patch("research_idea.cli.discover", return_value=[]) as search, patch("research_idea.literature.fetch_full_text") as fetch:
            code, out, error = self.call("search", "query", "--project", self.project, "--venues", "EMNLP", "NAACL")
        self.assertEqual(code, 0, error)
        self.assertEqual(search.call_args.kwargs["source"], "openalex")
        self.assertEqual(search.call_args.kwargs["venues"], ["EMNLP", "NAACL"])
        self.assertEqual(json.loads(out)["error_count"], 0)
        fetch.assert_not_called()

    def test_manual_full_text_failure_keeps_abstract_and_other_success(self):
        papers = [{"id": "p1", "title": "First paper", "abstract": "First abstract", "content_kind": "abstract"},
                  {"id": "p2", "title": "Second paper", "abstract": "Second abstract", "content_kind": "abstract"}]
        success = dict(papers[1], text="Full source text", content_kind="full_text")
        with patch("research_idea.cli.discover", return_value=papers), patch("research_idea.literature.fetch_full_text", side_effect=[LiteratureError("PDF unavailable"), success]) as fetch:
            code, out, error = self.call("search", "query", "--project", self.project, "--full-text", "--limit", "2")
        self.assertEqual(code, 0, error)
        result = json.loads(out)
        self.assertEqual(result["full_text_fetched"], 1)
        self.assertEqual(result["full_text_errors"], 1)
        self.assertEqual(result["source_coverage"], {"full_text": 1, "abstract_only": 1})
        self.assertTrue(all(0 < call.kwargs["timeout_s"] <= 30 for call in fetch.call_args_list))
        store = Store(self.project)
        try:
            records = {paper["id"]: paper for paper in store.rows("papers")}
            self.assertEqual(records["p1"]["content_kind"], "abstract")
            self.assertEqual(records["p1"]["abstract"], "First abstract")
            self.assertEqual(records["p1"]["full_text_error"], "PDF unavailable")
            self.assertEqual(records["p2"]["content_kind"], "full_text")
            self.assertEqual(store.get("manual_search_ledger")[-1]["full_text_errors"], 1)
            self.assertEqual(store.get("manual_full_text_errors"), 1)
        finally:
            store.close()

    def test_manual_search_failure_is_persisted_and_counted(self):
        with patch("research_idea.cli.discover", side_effect=LiteratureError("Search unavailable")):
            code, _, error = self.call("search", "query", "--project", self.project)
        self.assertEqual(code, 1)
        self.assertIn("Search unavailable", error)
        store = Store(self.project)
        try:
            latest = store.get("manual_search_ledger")[-1]
            self.assertEqual(latest["status"], "failed")
            self.assertEqual(latest["error_type"], "LiteratureError")
            self.assertEqual(store.get("manual_search_errors"), 1)
            self.assertEqual(store.rows("papers"), [])
            self.assertIn("manual_search_failed", [event["kind"] for event in store.recent_events()])
        finally:
            store.close()

    def test_returned_full_text_error_and_search_coverage_are_preserved(self):
        class Results(list):
            coverage = {"gaps": ["Some venue metadata is unresolved"]}
        paper = {"id": "p1", "title": "Paper", "abstract": "Original abstract", "content_kind": "abstract"}
        returned = dict(paper, full_text_error="No accessible PDF", full_text_retrieval={"status": "unavailable"})
        with patch("research_idea.cli.discover", return_value=Results([paper])), patch("research_idea.literature.fetch_full_text", return_value=returned):
            code, out, error = self.call("search", "query", "--project", self.project, "--full-text")
        self.assertEqual(code, 0, error)
        self.assertEqual(json.loads(out)["search_coverage"], Results.coverage)
        self.assertEqual(json.loads(out)["full_text_errors"], 1)
        self.assertEqual(json.loads(out)["full_text_fetched"], 0)
        store = Store(self.project)
        try:
            self.assertEqual(store.rows("papers")[0]["full_text_retrieval"]["status"], "unavailable")
            self.assertEqual(store.get("manual_search_ledger")[-1]["coverage"], Results.coverage)
        finally:
            store.close()

    def test_empty_download_is_not_counted_as_full_text(self):
        paper = {"id": "p1", "title": "Paper", "abstract": "Original abstract", "content_kind": "abstract"}
        with patch("research_idea.cli.discover", return_value=[paper]), patch("research_idea.literature.fetch_full_text", return_value=dict(paper, content_kind="full_text", text=" ")):
            code, out, error = self.call("search", "query", "--project", self.project, "--full-text")
        self.assertEqual(code, 0, error)
        self.assertEqual(json.loads(out)["full_text_fetched"], 0)
        self.assertEqual(json.loads(out)["full_text_errors"], 1)
        store = Store(self.project)
        try:
            self.assertEqual(store.rows("papers")[0]["content_kind"], "abstract")
        finally:
            store.close()

    def test_manual_search_history_is_bounded_and_venues_command_is_local(self):
        store = Store(self.project)
        try:
            store.set("manual_search_ledger", [{"query": str(i)} for i in range(100)])
        finally:
            store.close()
        with patch("research_idea.cli.discover", return_value=[]):
            code, _, error = self.call("search", "new query", "--project", self.project)
        self.assertEqual(code, 0, error)
        store = Store(self.project)
        try:
            history = store.get("manual_search_ledger")
            self.assertEqual(len(history), 100)
            self.assertEqual(history[0]["query"], "1")
            self.assertEqual(history[-1]["query"], "new query")
        finally:
            store.close()
        with patch("research_idea.cli.discover") as search:
            code, out, error = self.call("venues")
        self.assertEqual(code, 0, error)
        self.assertTrue(json.loads(out)["venues"])
        self.assertIn("not a complete or current CCF", json.loads(out)["note"])
        search.assert_not_called()


if __name__ == "__main__":
    unittest.main()
