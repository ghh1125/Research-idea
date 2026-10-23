"""Skill snapshots must affect the correct tasks and survive resumable research."""
from __future__ import annotations

import tempfile
from pathlib import Path
import unittest

from research_idea.backend_types import BackendResult
from research_idea.config import DEFAULTS
from research_idea.controller import Controller, make_evidence
from research_idea.demo import DemoBackend, DEMO_PAPERS, DEMO_TOPIC
from research_idea.local_skills import builtin_skill_paths
from research_idea.store import Store


class CaptureBackend:
    name = "capture"

    def __init__(self):
        self.prompts = []

    def generate(self, task):
        self.prompts.append(task.prompt)
        return BackendResult({"problem": "A research question", "observations": [],
            "competing_explanations": [], "unresolved_questions": [],
            "opportunity_types": [], "evidence_ids": []})


class ExtractionBackend:
    name = "extraction-fixture"

    def __init__(self, outputs):
        self.outputs = iter(outputs)
        self.stages = []

    def generate(self, task):
        self.stages.append(task.stage)
        return BackendResult({"observations": next(self.outputs)})


class SkillIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.project = Path(self.temp.name)
        self.store = Store(self.project)
        self.config = dict(DEFAULTS, builtin_skills=False, skill_paths=[], auto_search=False)

    def tearDown(self):
        self.store.close()
        self.temp.cleanup()

    def skill(self, name, body):
        directory = self.project / name
        directory.mkdir(exist_ok=True)
        path = directory / "SKILL.md"
        path.write_text(f"---\nname: {name}\ndescription: Local research guidance\n---\n{body}\n")
        return path

    def test_builtins_are_complete_and_stage_scoped(self):
        self.assertEqual(len(builtin_skill_paths()), 8)
        controller = Controller(self.store, CaptureBackend(), dict(self.config, builtin_skills=True))
        self.assertEqual(len(controller.skill_manifest), 8)
        self.assertTrue(all(item["origin"] == "builtin" for item in controller.skill_manifest))
        selected = [s["name"] for s in controller.skills if "extract" in s["stages"]]
        self.assertEqual(selected, ["research-idea-read-evidence", "research-idea-audit-claims"])
        self.assertEqual(len(self.store.get("active_skills")), 8)
        audits = [s["name"] for s in controller.skills if "audit_claims" in s["stages"]]
        self.assertEqual(audits, ["research-idea-audit-claims"])
        planners = [s["name"] for s in controller.skills if "plan_search" in s["stages"]]
        self.assertEqual(planners, ["research-idea-read-evidence"])

    def test_explicit_skill_changes_prompt_and_invalidates_its_task(self):
        path = self.skill("ccf-idea-optimizer", "Compare a causal explanation with its simplest rival.")
        config = dict(self.config, skill_paths=[str(path)])
        backend = CaptureBackend()
        Controller(self.store, backend, config).task("map", {})
        self.assertIn("simplest rival", backend.prompts[0])
        self.assertIn("NOT scientific evidence", backend.prompts[0])
        self.assertEqual(self.store.get("calls_used"), 1)
        Controller(self.store, backend, config).task("map", {})
        self.assertEqual(len(backend.prompts), 1)
        path.write_text(path.read_text() + "Check a distinct boundary condition.\n")
        Controller(self.store, backend, config).task("map", {})
        self.assertEqual(len(backend.prompts), 2)
        self.assertIn("distinct boundary", backend.prompts[-1])

    def test_irrelevant_stage_does_not_receive_or_recompute_selected_skill(self):
        path = self.skill("ccf-idea-reviewer", "REVIEW_ONLY_GUIDANCE")
        config = dict(self.config, skill_paths=[str(path)])
        backend = CaptureBackend()
        Controller(self.store, backend, config).task("map", {})
        path.write_text(path.read_text() + "REVISION_ONLY_GUIDANCE\n")
        Controller(self.store, backend, config).task("map", {})
        self.assertEqual(len(backend.prompts), 1)
        self.assertNotIn("REVIEW_ONLY_GUIDANCE", backend.prompts[0])

    def test_codex_profile_changes_task_identity(self):
        backend = CaptureBackend()
        Controller(self.store, backend, dict(self.config, codex_profile="first")).task("map", {})
        Controller(self.store, backend, dict(self.config, codex_profile="second")).task("map", {})
        self.assertEqual(len(backend.prompts), 2)

    def test_skill_change_replans_cohort_and_keeps_earlier_history(self):
        path = self.skill("ccf-idea-optimizer", "Separate the problem from the proposed intervention.")
        config = dict(self.config, backend="demo", skill_paths=[str(path)], max_calls=60)
        self.store.set("topic", DEMO_TOPIC)
        for paper in DEMO_PAPERS:
            self.store.put("papers", paper)
        Controller(self.store, DemoBackend(), config).run()
        previous = self.store.get("calls_used")
        old_key = self.store.get("cohort")["key"]
        path.write_text(path.read_text() + "Prefer a necessity test over a decorative ablation.\n")
        Controller(self.store, DemoBackend(), config).run()
        self.assertNotEqual(self.store.get("cohort")["key"], old_key)
        self.assertGreater(self.store.get("calls_used"), previous)
        self.assertTrue(any(event["kind"] == "cohort_archived" for event in self.store.recent_events(100)))
        self.assertTrue(all(c["empirical_status"] == "untested" for c in self.store.rows("candidates")))

    def source(self):
        paper = {"id": "paper-fixture", "title": "Reading fixture", "content_kind": "full_text",
                 "text": "This source describes a bounded method under controlled conditions."}
        self.store.put("papers", paper)
        observation = {"statement": "General observation.", "quote": paper["text"], "kind": "author_claim",
                       "conditions": "Fixture only", "source_section": "method"}
        candidate = {"proposal": {"closest_work_ids": [paper["id"]], "hypothesis": "Does the condition matter?"}}
        return paper, observation, candidate

    def test_new_extraction_guidance_can_remove_previous_observations(self):
        _, observation, _ = self.source()
        path = self.skill("nature-paper-card", "Initial reading procedure.")
        config = dict(self.config, skill_paths=[str(path)])
        backend = ExtractionBackend([[observation], []])
        Controller(self.store, backend, config).extract_papers()
        first = self.store.rows("evidence")[0]
        self.assertEqual(first["extraction_stage"], "extract")
        self.assertTrue(first["guidance_key"])
        path.write_text(path.read_text() + "Reject the previous unsupported interpretation.\n")
        Controller(self.store, backend, config).extract_papers()
        self.assertEqual(backend.stages, ["extract", "extract"])
        self.assertEqual(self.store.rows("evidence"), [])

    def test_resume_keeps_focused_evidence_only_for_current_stage_guidance(self):
        _, observation, candidate = self.source()
        focused = dict(observation, statement="Candidate-specific observation.")
        inspect_path = self.skill("novelty-check", "Read candidate-specific method conditions.")
        reviewer_path = self.skill("ccf-idea-reviewer", "Review the resulting proposal.")
        config = dict(self.config, skill_paths=[str(inspect_path), str(reviewer_path)])
        backend = ExtractionBackend([[focused], [observation]])
        first = Controller(self.store, backend, config)
        first.focus_sources(candidate)
        focused_record = self.store.rows("evidence")[0]
        self.assertEqual(focused_record["extraction_stage"], "inspect_source")
        self.assertTrue(focused_record["extraction_scope"])
        first.extract_papers()
        reviewer_path.write_text(reviewer_path.read_text() + "New review-only instruction.\n")
        Controller(self.store, backend, config).extract_papers()
        self.assertIn(focused_record["id"], {e["id"] for e in self.store.rows("evidence")})
        inspect_path.write_text(inspect_path.read_text() + "Correct the reading procedure.\n")
        Controller(self.store, backend, config).extract_papers()
        self.assertNotIn(focused_record["id"], {e["id"] for e in self.store.rows("evidence")})
        self.assertEqual(backend.stages, ["inspect_source", "extract"])

    def test_reextract_drops_changed_source_and_unattributed_legacy_readings(self):
        paper, observation, candidate = self.source()
        backend = ExtractionBackend([[observation], []])
        controller = Controller(self.store, backend, self.config)
        controller.focus_sources(candidate)
        paper["text"] += " The source has now changed."
        self.store.put("papers", paper)
        current = self.store.rows("evidence")
        legacy = make_evidence(paper, [dict(observation, statement="Unattributed legacy reading.")], paper["text"])
        self.store.replace_evidence(paper["id"], current + legacy)
        controller.extract_papers()
        self.assertEqual(self.store.rows("evidence"), [])

    def test_focused_refresh_replaces_outdated_interpretation_and_keeps_ordinary_evidence(self):
        _, observation, candidate = self.source()
        focused = dict(observation, statement="Candidate-specific observation.")
        path = self.skill("novelty-check", "Initial candidate reading.")
        config = dict(self.config, skill_paths=[str(path)])
        backend = ExtractionBackend([[observation], [focused], []])
        first = Controller(self.store, backend, config)
        first.extract_papers()
        first.focus_sources(candidate)
        path.write_text(path.read_text() + "Discard unsupported candidate details.\n")
        Controller(self.store, backend, config).focus_sources(candidate)
        remaining = self.store.rows("evidence")
        self.assertEqual([e["statement"] for e in remaining], [observation["statement"]])
        self.assertEqual(remaining[0]["extraction_stage"], "extract")
        self.assertEqual(backend.stages, ["extract", "inspect_source", "inspect_source"])


if __name__ == "__main__":
    unittest.main()
