"""Integration of search planning, grounded reading, and scoped claim audits."""
from __future__ import annotations

import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from research_idea.backend_types import BackendError, BackendResult
from research_idea.config import DEFAULTS
from research_idea.controller import BudgetExhausted, Controller
from research_idea.report import export_report
from research_idea.store import Store, digest


CLAIM = "Adaptive routing improves mathematical reasoning under all deployment conditions."
RESULT = "On Dataset A, Model B improves by two points at 1000 tokens per item."
QUERIES = ["language model adaptive routing", "adaptive routing feedback mechanism", "adaptive routing failure conditions"]


def paper(identifier="p1", *, abstract=False, result=RESULT):
    record = {"id": identifier, "title": "Synthetic routing study " + identifier,
              "content_kind": "abstract" if abstract else "full_text", "abstract": CLAIM}
    if not abstract:
        record["text"] = "Introduction\n" + CLAIM + "\nResults\n" + result + "\nAppendix\nPrompt controls remain unreported."
    return record


class PipelineBackend:
    """Exercises actual task schemas and evidence checks without network models."""

    name = "pipeline-fixture"

    def __init__(self, trace=None):
        self.calls = []
        self.trace = trace if trace is not None else []

    def generate(self, task):
        payload = json.loads(task.prompt.split("BEGIN_RESEARCH_DATA\n", 1)[1].split("\nEND_RESEARCH_DATA", 1)[0])
        self.calls.append((task.stage, copy.deepcopy(payload)))
        self.trace.append(("model", task.stage))
        if task.stage == "plan_search":
            queries = ["candidate routing matched budget", "candidate routing simpler controls", "candidate routing counterexamples"] if "candidate" in payload else QUERIES
            output = {"research_question": "When can observable feedback improve adaptive routing?",
                      "scope": "Inference-time routing with matched evaluation budgets.",
                      "queries": [{"query": query, "purpose": purpose, "rationale": "Find the corresponding evidence before drawing a conclusion."}
                                  for query, purpose in zip(queries, ("background", "mechanism", "counterevidence"))],
                      "assumptions": ["Resource access remains unspecified."]}
        elif task.stage in {"extract", "inspect_source", "read_section"}:
            observations = []
            for line in payload["excerpt"].splitlines():
                if line.startswith("Adaptive routing"):
                    observations.append({"statement": "Authors state a broad benefit.", "quote": line,
                        "kind": "author_claim", "conditions": "The authors discuss deployment broadly.", "source_section": "Introduction"})
                elif line.startswith("On Dataset A"):
                    observations.append({"statement": "The supplied experiment reports a bounded result.", "quote": line,
                        "kind": "reported_result", "conditions": "Dataset A; Model B; 1000 tokens per item.", "source_section": "Results Table 1"})
            output = {"observations": observations}
        elif task.stage == "paper_card":
            from research_idea.paper_reading import FACETS
            refs = [item["id"] for item in payload["evidence"]]
            output = {"paper_id": payload["paper_id"], "paper_type": "empirical",
                "framework": [{"dimension": dimension, "status": "analysis", "summary": "The supplied synthetic evidence supports only a narrow interpretation.", "evidence_ids": refs} for dimension in FACETS],
                "components": [], "experiments": [], "author_limitations": [], "analyst_concerns": [], "opportunities": [],
                "reading_gaps": ["Synthetic example; no visual inspection."], "followup_requests": []}
        elif task.stage == "audit_claims":
            claims = [item for item in payload["evidence"] if item["kind"] == "author_claim"]
            results = [item for item in payload["evidence"] if item["kind"] == "reported_result"]
            output = {"paper_id": payload["paper_id"],
                "reading_coverage": {"experiments": "read", "appendix": "partial", "notes": "Only supplied source text was available."},
                "claims": [{"claim": claims[0]["quote"], "claim_evidence_ids": [claims[0]["id"]],
                    "tested_scope": {"tasks": "Arithmetic reasoning", "data": "Dataset A", "models": "Model B",
                                     "settings": "One held-out split", "budget": "1000 tokens per item"},
                    "result_evidence_ids": [item["id"] for item in results],
                    "warranted_conclusion": results[0]["quote"] if results else "No result was supplied.",
                    "limitations": ["One dataset and model cannot establish universal improvement."],
                    "confounds": ["Prompt differences may affect the result."],
                    "missing_controls": ["Matched-prompt baseline"],
                    "support_judgment": "supported_within_tested_scope", "next_reading": ["Read additional appendix controls."]}]}
        elif task.stage == "map":
            output = {"problem": "Routing feedback may fail outside the tested setting.",
                      "observations": ["A narrow reported result does not establish the broad claim."],
                      "competing_explanations": ["Feedback validity versus prompt differences"],
                      "unresolved_questions": ["Does the mechanism survive a matched-prompt control?"],
                      "opportunity_types": ["boundary"], "evidence_ids": [item["id"] for item in payload["evidence"]]}
        elif task.stage == "propose":
            output = {"candidates": [], "no_candidate_reason": "These synthetic sources are insufficient to justify a new candidate."}
        else:
            raise AssertionError("Unexpected model stage: " + task.stage)
        return BackendResult(output, usage={"fixture": True})


class PaperPipelineTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.temp.name))
        self.store.set("topic", "大模型的自适应推理与反馈可靠性")
        self.config = dict(DEFAULTS, backend="api", builtin_skills=False, auto_search=True,
                           fetch_full_text=False, max_papers=10, max_candidates=2,
                           max_calls=50, max_seconds=120)

    def tearDown(self):
        self.store.close()
        self.temp.cleanup()

    def controller(self, fixture_backend=None, **overrides):
        return Controller(self.store, fixture_backend or PipelineBackend(), dict(self.config, **overrides))

    def audited_source(self):
        self.store.put("papers", paper())
        backend = PipelineBackend()
        controller = self.controller(backend, auto_search=False)
        controller.extract_papers()
        controller.audit_papers()
        return controller, backend

    def test_english_plan_precedes_discovery_reading_audit_and_brainstorm(self):
        trace = []
        backend = PipelineBackend(trace)

        def discover(query, **kwargs):
            trace.append(("discover", query))
            batch = len([entry for entry in trace if entry[0] == "discover"])
            return [paper(f"batch{batch}-{i}") for i in range(kwargs["limit"])]

        with patch("research_idea.literature.discover", side_effect=discover) as search:
            controller = self.controller(backend)
            controller.run()
        self.assertEqual(trace[0], ("model", "plan_search"))
        self.assertEqual([call.args[0] for call in search.call_args_list], QUERIES)
        self.assertNotIn(self.store.get("topic"), [call.args[0] for call in search.call_args_list])
        last_search = max(i for i, item in enumerate(trace) if item[0] == "discover")
        first_extract = trace.index(("model", "read_section"))
        first_audit = trace.index(("model", "audit_claims"))
        first_map = trace.index(("model", "map"))
        self.assertLess(last_search, first_extract)
        self.assertLess(first_extract, first_audit)
        self.assertLess(first_audit, first_map)
        self.assertLess(first_map, trace.index(("model", "propose")))
        self.assertEqual(len(self.store.rows("papers")), 5)
        self.assertEqual(sum(call.kwargs["limit"] for call in search.call_args_list), 60)
        map_payload = next(payload for stage, payload in backend.calls if stage == "map")
        self.assertEqual(len(map_payload["paper_claim_audits"]), 5)
        self.assertEqual(len(map_payload["paper_cards"]), 5)
        self.assertTrue(all(item["status"] == "analyzed" for item in map_payload["paper_cards"]))
        self.assertTrue(all(item["status"] == "audited" for item in map_payload["paper_claim_audits"]))

    def test_candidate_search_uses_reserved_capacity_and_a_different_plan(self):
        backend = PipelineBackend()
        batch = 0

        def discover(query, **kwargs):
            nonlocal batch
            batch += 1
            return [paper(f"batch{batch}-{index}") for index in range(kwargs["limit"])]

        controller = self.controller(backend)
        with patch("research_idea.literature.discover", side_effect=discover) as search:
            controller.initial_search()
            self.assertEqual(len(self.store.rows("papers")), 5)
            candidate = {"id": "candidate-1", "proposal": {"title": "Matched feedback routing", "closest_work_ids": ["batch1-0"]}}
            controller.search_for_candidate(candidate)
        self.assertEqual(len(self.store.rows("papers")), 7)
        self.assertEqual(search.call_args_list[-1].args[0], "candidate routing counterexamples")
        self.assertEqual(search.call_args_list[-1].kwargs["limit"], 20)
        self.assertIn("candidate", [payload for stage, payload in backend.calls if stage == "plan_search"][-1])
        self.assertEqual(set(self.store.get("search_plans")), {"initial", "candidate-1"})

    def test_no_search_and_demo_do_not_plan_or_call_discovery(self):
        for config in ({"auto_search": False}, {"backend": "demo"}):
            with self.subTest(config=config), patch("research_idea.literature.discover") as search:
                backend = PipelineBackend()
                self.controller(backend, **config).initial_search()
                self.assertEqual(backend.calls, [])
                search.assert_not_called()

    def test_cached_empty_search_resume_needs_no_new_model_or_network_calls(self):
        first = PipelineBackend()
        with patch("research_idea.literature.discover", return_value=[]) as search:
            self.controller(first).initial_search()
        self.assertEqual(len(first.calls), 1)
        self.assertEqual(search.call_count, 3)
        resumed = PipelineBackend()
        with patch("research_idea.literature.discover") as search:
            self.controller(resumed, max_calls=1).initial_search()
        self.assertEqual(resumed.calls, [])
        search.assert_not_called()
        self.assertEqual(self.store.get("calls_used"), 1)

    def test_interrupted_initial_search_resumes_remaining_queries_from_cached_plan(self):
        first = PipelineBackend()
        with patch("research_idea.literature.discover", side_effect=[[paper("first")], KeyboardInterrupt()]):
            with self.assertRaises(KeyboardInterrupt):
                self.controller(first, max_papers=6).initial_search()
        self.assertEqual(len(self.store.rows("papers")), 0)
        self.assertEqual(len(next(iter(self.store.get("search_ledger").values()))["metadata"]), 1)
        resumed = PipelineBackend()
        with patch("research_idea.literature.discover", side_effect=[[paper("second")], [paper("third")]]) as search:
            self.controller(resumed, max_papers=6).initial_search()
        self.assertEqual(resumed.calls, [])
        self.assertEqual([call.args[0] for call in search.call_args_list], QUERIES[1:])
        self.assertEqual(len(self.store.rows("papers")), 3)

    def test_planning_is_charged_to_model_budget_before_any_search(self):
        backend = PipelineBackend()
        with patch("research_idea.literature.discover") as search:
            with self.assertRaises(BudgetExhausted):
                self.controller(backend, max_calls=1).run()
        self.assertEqual([stage for stage, _ in backend.calls], ["plan_search"])
        self.assertEqual(self.store.get("calls_used"), 1)
        self.assertEqual(self.store.get("status"), "budget_exhausted")
        self.assertIn("initial", self.store.get("search_plans"))
        search.assert_not_called()

    def test_claim_audits_reach_context_and_export_with_bounded_conclusions(self):
        controller, _ = self.audited_source()
        audit = controller.context()["paper_claim_audits"][0]
        self.assertEqual(audit["status"], "audited")
        self.assertEqual(audit["source_hash"], digest(paper()["text"]))
        self.assertEqual(audit["claims"][0]["warranted_conclusion"], RESULT)
        self.assertTrue(any("not global proof" in warning for warning in audit["warnings"]))
        controller.plan_search()
        markdown, machine = export_report(self.store)
        report = json.loads(machine.read_text())
        self.assertEqual(report["paper_claim_audits"]["p1"], audit)
        self.assertIn("initial", report["search_plans"])
        self.assertIn(RESULT, markdown.read_text())
        self.assertIn(QUERIES[0], markdown.read_text())

    def test_abstract_only_audit_is_explicit_and_does_not_use_a_model(self):
        self.store.put("papers", paper(abstract=True))
        backend = PipelineBackend()
        controller = self.controller(backend, auto_search=False)
        controller.extract_papers()
        before = self.store.get("calls_used")
        controller.audit_papers()
        self.assertEqual([stage for stage, _ in backend.calls], ["extract"])
        self.assertEqual(self.store.get("calls_used"), before)
        audit = controller.context()["paper_claim_audits"][0]
        self.assertEqual(audit["status"], "insufficient_evidence")
        self.assertEqual(audit["reading_coverage"]["experiments"], "unavailable")
        self.assertEqual(audit["claims"], [])

    def test_audit_resume_is_cached_but_source_change_creates_new_tasks(self):
        _, first = self.audited_source()
        self.assertEqual([stage for stage, _ in first.calls], ["extract", "audit_claims"])
        resumed_backend = PipelineBackend()
        resumed = self.controller(resumed_backend, auto_search=False)
        resumed.extract_papers()
        resumed.audit_papers()
        self.assertEqual(resumed_backend.calls, [])
        changed = paper(result="On Dataset A, Model B gains zero points with the matched-prompt control.")
        self.store.put("papers", changed)
        resumed.extract_papers()
        resumed.audit_papers()
        self.assertEqual([stage for stage, _ in resumed_backend.calls], ["extract", "audit_claims"])
        audit = self.store.get("paper_claim_audits")["p1"]
        self.assertEqual(audit["source_hash"], digest(changed["text"]))
        self.assertIn("zero points", audit["claims"][0]["warranted_conclusion"])

    def test_stale_evidence_is_rejected_and_previous_audit_cleared(self):
        controller, backend = self.audited_source()
        self.store.put("papers", paper(result="On Dataset A, Model B gains zero points with the matched-prompt control."))
        with self.assertRaisesRegex(BackendError, "stale"):
            controller.audit_papers()
        self.assertEqual(self.store.get("paper_claim_audits"), {})
        self.assertEqual([stage for stage, _ in backend.calls].count("audit_claims"), 3)

    def test_context_does_not_expose_source_changed_audit_as_current(self):
        controller, _ = self.audited_source()
        self.store.put("papers", paper(result="On Dataset A, Model B gains zero points with the matched-prompt control."))
        self.assertFalse(any(item["paper_id"] == "p1" and item["status"] == "audited"
                             for item in controller.context()["paper_claim_audits"]))

    def test_export_does_not_present_source_changed_audit_as_current(self):
        self.audited_source()
        self.store.put("papers", paper(result="On Dataset A, Model B gains zero points with the matched-prompt control."))
        _, machine = export_report(self.store)
        audit = json.loads(machine.read_text())["paper_claim_audits"].get("p1", {})
        self.assertNotEqual(audit.get("status"), "audited")

    def test_budget_stop_retains_completed_audit_without_claiming_remaining_paper_read(self):
        self.store.put("papers", paper("p1"))
        self.store.put("papers", paper("p2"))
        controller = self.controller(auto_search=False, max_calls=3)
        controller.extract_papers()
        with self.assertRaises(BudgetExhausted):
            controller.audit_papers()
        audits = self.store.get("paper_claim_audits")
        self.assertEqual(audits["p1"]["status"], "audited")
        self.assertNotEqual(audits.get("p2", {}).get("status"), "audited")
        self.assertEqual(self.store.get("calls_used"), 3)
        markdown, machine = export_report(self.store)
        pending = json.loads(machine.read_text())["paper_claim_audits"]["p2"]
        self.assertEqual(pending["status"], "pending")
        self.assertTrue(pending["warnings"])
        self.assertIn("pending", markdown.read_text())


if __name__ == "__main__":
    unittest.main()
