"""Evidence integrity and execution-boundary regression tests."""
from __future__ import annotations

import copy
import json
from pathlib import Path
import tempfile
import unittest

from research_idea.backend_types import BackendError, BackendResult
from research_idea.config import DEFAULTS
from research_idea.controller import (
    BudgetExhausted, Controller, check_references, evidence_gate,
    locate_quote, make_evidence,
)
from research_idea.schema import SCHEMAS, validate
from research_idea.demo import demo_design_plan
from research_idea.store import Store


QUOTE = "The observed benefit depends on the available inference budget."


def valid_shape(schema):
    """Create a small fixture from the declared contract, not production code."""
    if schema["type"] == "object":
        result = {key: valid_shape(value) for key, value in schema["properties"].items()}
        if 'design_axes' in result:
            result['design_axes'] = demo_design_plan()['design_axes']
        if 'axis_ids' in result:
            result['axis_ids'] = ['relations', 'use']
        return result
    if schema["type"] == "array":
        return []
    if schema["type"] == "string":
        return schema.get("enum", ["A concrete testable statement"])[0]
    raise AssertionError(schema)


class FakeBackend:
    name = "test-backend"

    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def generate(self, task):
        self.calls.append(task)
        if not self.responses:
            raise AssertionError("Unexpected backend invocation")
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return BackendResult(output=copy.deepcopy(response), usage={"test_call": len(self.calls)})


class EvidenceIntegrityTests(unittest.TestCase):
    def paper(self, source_kind="full_text"):
        return {"id": "paper-1", "title": "Budget study", "text": "Introduction\n" + QUOTE,
                "content_kind": source_kind}

    def observation(self):
        return {"statement": "The measured benefit depends on inference budget.", "quote": QUOTE,
                "kind": "reported_result", "conditions": "The supplied experiment only.",
                "source_section": "Results"}

    def spec(self, evidence_id, paper_id="paper-1"):
        value = valid_shape(SCHEMAS["develop"])
        value['design_decisions'] = [valid_shape(SCHEMAS['develop']['properties']['design_decisions']['items'])]
        value["method"]["changes"] = ["Measure signal quality before training a controller."]
        value["motivation"]["evidence_ids"] = [evidence_id]
        value["prior_art"]["verdict"] = "covered"
        value["prior_art"]["overlaps"] = [{
            "paper_id": paper_id, "level": "core_claim", "covered_claim": "Budget changes gains.",
            "evidence_ids": [evidence_id], "remaining_gap": "No further claim established.",
            "comparisons": [{"dimension": dimension, "prior_detail": "Method conditions specify equal inference budgets.",
                "proposed_detail": "Method conditions specify equal inference budgets.", "relation": "same", "evidence_ids": [evidence_id]}
                for dimension in ("problem", "mechanism", "information", "objective", "evaluation", "claim")],
        }]
        value["feasibility"]["checks"] = [{"dimension": dimension, "status": "unverified",
            "requirement": "Check the actual implementation prerequisites.", "evidence_ids": [],
            "verification_plan": "Inspect a real sample and run the corresponding interface check.",
            "failure_action": "Keep this prerequisite unresolved before running training."}
            for dimension in ("data_access", "inference_signal", "interface", "learning_signal", "compute", "evaluation", "minimal_test")]
        return value

    def test_verbatim_quote_accepts_whitespace_and_preserves_offsets(self):
        text = "Header\nThe observed benefit\n depends on the available inference budget.\nEnd"
        start, end = locate_quote(text, QUOTE)
        self.assertEqual(" ".join(text[start:end].split()), QUOTE)
        self.assertEqual(start, len("Header\n"))

    def test_fabricated_or_stitched_quote_is_rejected(self):
        for quote in [
            "The observed benefit always improves with more training data.",
            "The observed benefit ... available inference budget.",
            "too short",
        ]:
            with self.subTest(quote=quote), self.assertRaises(ValueError):
                locate_quote(QUOTE, quote)

    def test_evidence_keeps_provenance_and_marks_quote_check_only(self):
        paper = self.paper()
        evidence = make_evidence(paper, [self.observation()], paper["text"])[0]
        self.assertEqual(evidence["paper_id"], "paper-1")
        self.assertEqual(evidence["source_kind"], "full_text")
        self.assertEqual(evidence["verification"], "quote_matched_only")
        self.assertEqual(evidence["line"], 2)
        self.assertEqual(evidence["reading_coverage"], "complete_supplied_text")
        updated = dict(paper, text=paper["text"] + "\nNew result")
        newer = make_evidence(updated, [self.observation()], paper["text"])[0]
        self.assertEqual(newer["reading_coverage"], "partial")
        self.assertNotEqual(newer["source_hash"], evidence["source_hash"])
        self.assertNotEqual(newer["id"], evidence["id"])

    def test_nested_unknown_references_are_rejected(self):
        for value in [
            {"method": {"assumptions": [{"evidence_ids": ["invented"]}]}},
            {"closest_work_ids": ["missing-paper"]},
            {"prior_art": {"overlaps": [{"paper_id": "missing-paper"}]}},
        ]:
            with self.subTest(value=value), self.assertRaises(ValueError):
                check_references(value, {"ev-1"}, {"paper-1"})

    def test_overlap_cannot_borrow_another_papers_evidence(self):
        evidence = [{"id": "ev-1", "paper_id": "paper-1", "source_kind": "full_text"}]
        spec = self.spec("ev-1", paper_id="paper-2")
        # Both IDs exist; it is the relationship that must be checked.
        check_references(spec, {"ev-1"}, {"paper-1", "paper-2"})
        with self.assertRaisesRegex(ValueError, "different paper"):
            evidence_gate(spec, evidence)

    def test_abstract_evidence_cannot_establish_core_claim_coverage(self):
        evidence = [{"id": "ev-1", "paper_id": "paper-1", "source_kind": "abstract"}]
        status, warnings = evidence_gate(self.spec("ev-1"), evidence)
        self.assertEqual(status, "uncertain")
        self.assertTrue(any("branch was not rejected" in warning for warning in warnings))

    def test_source_supported_assumption_needs_evidence(self):
        value = self.spec("ev-1")
        value["method"]["assumptions"] = [{
            "statement": "Signal can be observed at inference.", "status": "source_supported",
            "evidence_ids": [], "check": "Read method section.",
        }]
        with self.assertRaisesRegex(ValueError, "has no evidence"):
            evidence_gate(value, [{"id": "ev-1", "paper_id": "paper-1", "source_kind": "full_text"}])


class ControllerExecutionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.project = Path(self.temp.name)
        self.store = Store(self.project)
        self.store.set("topic", "Investigate inference-budget effects")
        self.config = dict(DEFAULTS, auto_search=False, max_rounds=2, max_calls=20,
                           max_seconds=60, timeout_s=20, model="test-model")

    def tearDown(self):
        self.store.close()
        self.temp.cleanup()

    def controller(self, backend, **overrides):
        return Controller(self.store, backend, dict(self.config, **overrides))

    def test_completed_task_is_reused_after_reopening_project(self):
        output = valid_shape(SCHEMAS["map"])
        backend = FakeBackend([output])
        first = self.controller(backend).task("map", {"question": "What changes?"})
        self.assertEqual(first, output)
        self.assertEqual(self.store.get("calls_used"), 1)
        self.store.close()
        self.store = Store(self.project)
        unused_backend = FakeBackend([])
        # Reusing a checked result is allowed even when the call budget is spent.
        recovered = self.controller(unused_backend, max_calls=1).task("map", {"question": "What changes?"})
        self.assertEqual(recovered, output)
        self.assertEqual(unused_backend.calls, [])
        self.assertEqual(self.store.task_summary(), {"succeeded": 1})

    def test_changed_model_or_payload_does_not_reuse_old_result(self):
        output = valid_shape(SCHEMAS["map"])
        backend = FakeBackend([output, output, output])
        self.controller(backend).task("map", {"version": 1})
        self.controller(backend, model="different-model").task("map", {"version": 1})
        self.controller(backend).task("map", {"version": 2})
        self.assertEqual(len(backend.calls), 3)
        self.assertEqual(self.store.task_summary(), {"succeeded": 3})

    def test_exhausted_call_budget_prevents_backend_invocation(self):
        backend = FakeBackend([valid_shape(SCHEMAS["map"])])
        self.store.set("calls_used", 1)
        with self.assertRaises(BudgetExhausted):
            self.controller(backend, max_calls=1).task("map", {})
        self.assertEqual(backend.calls, [])

    def test_wall_budget_prevents_backend_invocation(self):
        backend = FakeBackend([])
        controller = self.controller(backend, max_seconds=1)
        controller.started -= 2
        with self.assertRaises(BudgetExhausted):
            controller.task("map", {})
        self.assertEqual(backend.calls, [])

    def test_schema_error_has_one_repair_and_persisted_attempt_count(self):
        backend = FakeBackend([{}, {}, valid_shape(SCHEMAS["map"])])
        with self.assertRaisesRegex(BackendError, "after one repair"):
            self.controller(backend).task("map", {})
        self.assertEqual(len(backend.calls), 2)
        self.assertEqual(self.store.get("calls_used"), 2)
        row = self.store.task(backend.calls[-1].task_id)
        self.assertEqual(row["status"], "failed")
        self.assertEqual(row["attempts"], 2)
        self.assertIn('previous_output', backend.calls[1].prompt)
        self.assertTrue(any(e['kind'] == 'output_repair' for e in self.store.recent_events()))

    def test_repair_is_counted_against_call_budget(self):
        backend = FakeBackend([{}, valid_shape(SCHEMAS["map"])])
        with self.assertRaises(BudgetExhausted):
            self.controller(backend, max_calls=1).task("map", {})
        self.assertEqual(len(backend.calls), 1)
        self.assertEqual(self.store.get("calls_used"), 1)

    def test_invalid_citation_can_be_repaired_but_not_cached_as_success(self):
        bad = valid_shape(SCHEMAS["map"])
        bad["evidence_ids"] = ["invented"]
        good = copy.deepcopy(bad)
        good["evidence_ids"] = ["ev-1"]
        backend = FakeBackend([bad, good])
        checker = lambda value: check_references(value, {"ev-1"}, {"paper-1"})
        result = self.controller(backend).task("map", {}, checker)
        self.assertEqual(result["evidence_ids"], ["ev-1"])
        self.assertEqual(len(backend.calls), 2)
        row = self.store.task(backend.calls[-1].task_id)
        self.assertEqual(json.loads(row["output"])["evidence_ids"], ["ev-1"])
        self.assertEqual(row["attempts"], 2)

    def test_cached_results_are_rechecked_against_current_evidence(self):
        value = valid_shape(SCHEMAS["map"])
        value["evidence_ids"] = ["ev-1"]
        backend = FakeBackend([value])
        self.controller(backend).task("map", {}, lambda x: check_references(x, {"ev-1"}, set()))
        with self.assertRaises(ValueError):
            self.controller(FakeBackend([])).task("map", {}, lambda x: check_references(x, set(), set()))

    def test_reasoning_change_recomputes_task_but_same_setting_reuses_cache(self):
        value = valid_shape(SCHEMAS["map"])
        backend = FakeBackend([value, value, value])
        for effort in ["", "medium", "medium", "high", ""]:
            self.controller(backend, reasoning_effort=effort).task("map", {})
        self.assertEqual(len(backend.calls), 3)
        self.assertEqual(len({t.task_id for t in backend.calls}), 3)

    def test_backend_failure_is_not_retried_as_a_schema_repair(self):
        backend = FakeBackend([BackendError("provider unavailable")])
        with self.assertRaises(BackendError):
            self.controller(backend).task("map", {})
        self.assertEqual(len(backend.calls), 1)
        self.assertEqual(self.store.task_summary(), {"failed": 1})

    def test_total_deadline_during_call_is_budget_exhaustion(self):
        backend = FakeBackend([])
        controller = self.controller(backend, timeout_s=120, max_seconds=60)

        def expire(task):
            self.assertLessEqual(task.timeout_s, 60)
            controller.started -= 61
            raise BackendError("model exceeded the remaining task timeout")

        backend.generate = expire
        controller.initial_search = lambda: None
        controller.retrieve_full_texts = lambda selected_ids=None: None
        controller.read_papers = lambda selected_ids=None: None
        controller.audit_papers = lambda selected_ids=None: None
        with self.assertRaisesRegex(BudgetExhausted, "max_seconds"):
            controller.run()
        self.assertEqual(self.store.get("status"), "budget_exhausted")
        self.assertEqual(self.store.get("calls_used"), 1)
        self.assertGreaterEqual(self.store.get("elapsed_s"), 60)
        self.assertEqual(self.store.task_summary(), {"failed": 1})

    def test_single_call_timeout_keeps_backend_error_with_time_left(self):
        backend = FakeBackend([BackendError("model exceeded the 20s task timeout")])
        with self.assertRaises(BackendError):
            self.controller(backend, timeout_s=20, max_seconds=60).task("map", {})
        self.assertEqual(len(backend.calls), 1)

    def test_interrupt_marks_run_and_unfinished_task_without_resetting_usage(self):
        backend = FakeBackend([])
        backend.generate = lambda task: (_ for _ in ()).throw(KeyboardInterrupt())
        controller = self.controller(backend)
        with self.assertRaises(KeyboardInterrupt):
            controller.run()
        self.assertEqual(self.store.get('status'), 'interrupted')
        self.assertEqual(self.store.task_summary(), {'failed': 1})
        self.assertEqual(self.store.get('calls_used'), 1)
        self.assertGreater(self.store.get('elapsed_s'), 0)

    def test_interrupt_while_displaying_saved_result_keeps_successful_cache(self):
        output = valid_shape(SCHEMAS['map'])
        controller = self.controller(FakeBackend([output]))
        controller.activity = lambda *args: (_ for _ in ()).throw(KeyboardInterrupt())
        with self.assertRaises(KeyboardInterrupt):
            controller.task('map', {})
        self.assertEqual(self.store.task_summary(), {'succeeded': 1})
        resumed_backend = FakeBackend([])
        self.assertEqual(self.controller(resumed_backend).task('map', {}), output)
        self.assertEqual(resumed_backend.calls, [])
        self.assertEqual(self.store.get('calls_used'), 1)

    def test_resume_closes_stale_running_entries_before_checking_budget(self):
        self.store.begin_task('abandoned-task', 'read_section')
        self.store.set('calls_used', self.config['max_calls'])
        with self.assertRaises(BudgetExhausted):
            self.controller(FakeBackend([])).run()
        self.assertEqual(self.store.task_summary(), {'failed': 1})
        self.assertIn('Interrupted', self.store.task('abandoned-task')['error'])
        self.assertEqual(self.store.get('calls_used'), self.config['max_calls'])

    def test_parse_value_error_repairs_without_a_previous_result_object(self):
        backend = FakeBackend([ValueError('malformed structured output'), valid_shape(SCHEMAS['map'])])
        self.controller(backend).task('map', {})
        self.assertEqual(len(backend.calls), 2)
        self.assertIn('malformed structured output', backend.calls[1].prompt)
        self.assertIn('"previous_output": null', backend.calls[1].prompt)

    def test_covered_review_on_abstract_retains_candidate_untested(self):
        paper = {"id": "paper-1", "title": "Budget study", "abstract": QUOTE,
                 "content_kind": "abstract"}
        self.store.put("papers", paper)
        evidence = {"id": "ev-1", "paper_id": "paper-1", "source_kind": "abstract", "quote": QUOTE}
        self.store.replace_evidence("paper-1", [evidence])
        method = EvidenceIntegrityTests().spec("ev-1")
        review = valid_shape(SCHEMAS["review"])
        review["verdict"] = "covered"
        proposal = valid_shape(SCHEMAS["propose"]["properties"]["candidates"]["items"])
        proposal["motivation"]["evidence_ids"] = ["ev-1"]
        candidate = {"id": "idea-1", "proposal": proposal, "versions": [], "design_search_plan": demo_design_plan()}
        backend = FakeBackend([method, review])
        self.controller(backend).develop_candidate(candidate)
        saved = self.store.rows("candidates")[0]
        self.assertEqual(saved["novelty_status"], "uncertain")
        self.assertEqual(saved["research_status"], "prerequisites_unverified")
        self.assertEqual(saved["empirical_status"], "untested")
        self.assertTrue(any("retain candidate" in warning for warning in saved["warnings"]))

    def test_optimistic_review_cannot_clear_unavailable_inference_signal(self):
        self.store.put("papers", {"id": "paper-1", "title": "Budget study", "content_kind": "abstract"})
        self.store.replace_evidence("paper-1", [{"id": "ev-1", "paper_id": "paper-1", "source_kind": "abstract"}])
        method = EvidenceIntegrityTests().spec("ev-1")
        method["feasibility"]["required_signals"] = [{"name": "ground-truth answer", "needed_at": "inference",
            "availability": "unavailable", "evidence_ids": [], "acquisition_plan": "No answer oracle is available.",
            "substitute": "A proxy is only a proposal; it is not the original method."}]
        review = valid_shape(SCHEMAS["review"])
        proposal = valid_shape(SCHEMAS["propose"]["properties"]["candidates"]["items"])
        proposal["motivation"]["evidence_ids"] = ["ev-1"]
        candidate = {"id": "idea-1", "proposal": proposal, "versions": [], "design_search_plan": demo_design_plan()}
        self.controller(FakeBackend([method, review]), max_rounds=1).develop_candidate(candidate)
        self.assertEqual(candidate["feasibility_status"], "blocked")
        self.assertEqual(candidate["research_status"], "implementation_blocked")
        self.assertEqual(candidate["recommended_action"]["kind"], "resolve_prerequisite")
        self.assertEqual(candidate["empirical_status"], "untested")

    def test_incremental_motivation_requires_revision_despite_continue_verdict(self):
        self.store.put("papers", {"id": "paper-1", "title": "Budget study", "content_kind": "abstract"})
        self.store.replace_evidence("paper-1", [{"id": "ev-1", "paper_id": "paper-1", "source_kind": "abstract"}])
        method = EvidenceIntegrityTests().spec("ev-1")
        review = valid_shape(SCHEMAS["review"])
        review["motivation_assessment"]["progress"] = "incremental"
        proposal = valid_shape(SCHEMAS["propose"]["properties"]["candidates"]["items"])
        proposal["motivation"]["evidence_ids"] = ["ev-1"]
        candidate = {"id": "idea-1", "proposal": proposal, "versions": [], "design_search_plan": demo_design_plan()}
        backend = FakeBackend([method, review, method, review])
        self.controller(backend).develop_candidate(candidate)
        # The reviewer now receives the previous critique and revision record.
        # Even with that context, an unchanged method must stop the revision loop.
        self.assertEqual([t.stage for t in backend.calls], ["develop", "review", "refine", "review"])
        self.assertEqual(len(candidate["versions"]), 2)
        self.assertEqual(candidate["motivation_status"], "needs_revision")
        self.assertEqual(candidate["research_status"], "no_detectable_progress")

    def test_hypothesis_focused_reading_is_preserved_by_resume_extraction(self):
        paper = EvidenceIntegrityTests().paper()
        self.store.put("papers", paper)
        observation = EvidenceIntegrityTests().observation()
        focused = dict(observation, statement="Candidate-specific limitation of the method.")
        backend = FakeBackend([{"observations": [focused]}, {"observations": [observation]}])
        controller = self.controller(backend)
        candidate = {"proposal": {"closest_work_ids": ["paper-1"], "hypothesis": "Does budget explain the effect?"}}
        controller.focus_sources(candidate)
        focused_id = self.store.rows("evidence")[0]["id"]
        controller.extract_papers()
        self.assertIn(focused_id, {e["id"] for e in self.store.rows("evidence")})
        self.assertEqual(backend.calls[0].stage, "inspect_source")
        self.assertIn("Does budget explain the effect?", backend.calls[0].prompt)
        controller.focus_sources(candidate)
        self.assertEqual(len(backend.calls), 2)

    def test_design_search_interruption_saves_idea_before_detailed_method(self):
        self.store.put('papers', {'id': 'paper-1', 'title': 'Budget study', 'content_kind': 'abstract'})
        self.store.replace_evidence('paper-1', [{'id': 'ev-1', 'paper_id': 'paper-1', 'source_kind': 'abstract'}])
        proposal = valid_shape(SCHEMAS['propose']['properties']['candidates']['items'])
        proposal['motivation']['evidence_ids'] = ['ev-1']
        candidate = {'id': 'idea-1', 'proposal': proposal, 'versions': [], 'design_search_plan': demo_design_plan()}
        method = EvidenceIntegrityTests().spec('ev-1')
        first_backend = FakeBackend([])
        first = self.controller(first_backend, max_rounds=1)

        def interrupted_search(item):
            saved = self.store.rows('candidates')[0]
            self.assertEqual(saved['proposal'], proposal)
            self.assertNotIn('spec', saved)
            self.store.put('papers', {'id': 'paper-2', 'title': 'New comparison source'})
            raise BudgetExhausted('Design search stopped after saving a new source')

        first.search_for_candidate = interrupted_search
        with self.assertRaises(BudgetExhausted):
            first.develop_candidate(candidate)
        self.assertEqual(first_backend.calls, [])
        saved = self.store.rows('candidates')[0]
        self.assertFalse(saved.get('development_complete', False))
        resumed_backend = FakeBackend([method, valid_shape(SCHEMAS['review'])])
        resumed = self.controller(resumed_backend, max_rounds=1)
        resumed.develop_candidate(saved)
        self.assertEqual([task.stage for task in resumed_backend.calls], ['develop', 'review'])
        self.assertEqual(saved['spec'], method)
        self.assertTrue(saved['development_complete'])
        self.assertNotIn('pending_round', saved)
        self.assertEqual(self.store.get('calls_used'), 2)

    def test_design_sources_are_current_before_developing_method(self):
        self.store.put('papers', {'id': 'paper-1', 'title': 'Budget study', 'content_kind': 'abstract'})
        self.store.replace_evidence('paper-1', [{'id': 'ev-1', 'paper_id': 'paper-1', 'source_kind': 'abstract'}])
        proposal = valid_shape(SCHEMAS['propose']['properties']['candidates']['items'])
        proposal['motivation']['evidence_ids'] = ['ev-1']
        candidate = {'id': 'idea-1', 'proposal': proposal, 'versions': [], 'design_search_plan': demo_design_plan()}
        refreshed = EvidenceIntegrityTests().spec('ev-2')
        backend = FakeBackend([refreshed, valid_shape(SCHEMAS['review'])])
        controller = self.controller(backend, max_rounds=1)

        def upgrade(item):
            self.store.replace_evidence('paper-1', [{'id': 'ev-2', 'paper_id': 'paper-1', 'source_kind': 'full_text'}])

        controller.search_for_candidate = upgrade
        controller.develop_candidate(candidate)
        self.assertEqual([task.stage for task in backend.calls], ['develop', 'review'])
        self.assertIn('ev-2', backend.calls[0].prompt)
        self.assertEqual(candidate['spec']['motivation']['evidence_ids'], ['ev-2'])
        check_references(candidate['spec'], {'ev-2'}, {'paper-1'})


class SchemaBoundaryTests(unittest.TestCase):
    def test_extra_keys_and_invalid_enum_are_rejected(self):
        value = valid_shape(SCHEMAS["review"])
        value["experiment_success"] = True
        with self.assertRaises(ValueError):
            validate(value, SCHEMAS["review"])
        value.pop("experiment_success")
        value["verdict"] = "proven_novel"
        with self.assertRaises(ValueError):
            validate(value, SCHEMAS["review"])


if __name__ == "__main__":
    unittest.main()
