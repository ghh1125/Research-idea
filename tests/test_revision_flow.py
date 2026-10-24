"""Revision traces preserve anchors and stop only exact evidence-free repetition."""
from __future__ import annotations

import copy
import json
from pathlib import Path
import tempfile
import unittest

from research_idea.backend_types import BackendResult
from research_idea.config import DEFAULTS
from research_idea.controller import Controller
from research_idea.schema import SCHEMAS
from research_idea.store import Store


def shape(schema):
    if schema["type"] == "object":
        return {key: shape(value) for key, value in schema["properties"].items()}
    if schema["type"] == "array":
        return []
    return schema.get("enum", ["A concrete testable statement"])[0]


def method_spec():
    spec = shape(SCHEMAS["develop"])
    spec['design_decisions'] = [shape(SCHEMAS['develop']['properties']['design_decisions']['items'])]
    spec["method"]["changes"] = ["Compare observable routing signals at a fixed inference budget."]
    spec["motivation"]["evidence_ids"] = ["ev-1"]
    spec["feasibility"]["checks"] = [
        {"dimension": dimension, "status": "unverified", "requirement": "Verify the stated interface and input.",
         "evidence_ids": [], "verification_plan": "Inspect the source method and actual input contract.",
         "failure_action": "Retain the unresolved prerequisite."}
        for dimension in ("data_access", "inference_signal", "interface", "learning_signal", "compute", "evaluation", "minimal_test")
    ]
    return spec


def review_spec(action="revise"):
    review = shape(SCHEMAS["review"])
    review.update(verdict="refine", issues=[{"severity": "important", "issue": "The routing signal may only predict current errors.",
        "evidence_ids": ["ev-1"], "action": "Specify a comparison against predicted benefit of extra inference."}],
        unresolved_questions=["Does the signal predict benefit rather than current error?"],
        revision_instructions="Specify the competing routing signals and preserve the original hypothesis.")
    review["next_action"]["kind"] = action
    return review


class ScriptedBackend:
    name = "revision-test"

    def __init__(self, method, review):
        self.method = method
        self.review = review
        self.calls = []

    def generate(self, task):
        payload = json.loads(task.prompt.split("BEGIN_RESEARCH_DATA\n", 1)[1].split("\nEND_RESEARCH_DATA", 1)[0])
        self.calls.append((task.stage, payload))
        output = self.method(payload) if task.stage in {"develop", "refine"} else self.review(payload)
        if task.stage == 'refine':
            output['review_responses'] = [{'issue': item['issue'], 'decision': 'test',
                'change': 'Compare the routing signals in the first test.',
                'reason': 'Separate current error from marginal benefit.', 'evidence_ids': ['ev-1']}
                for item in payload['review']['issues']]
        return BackendResult(output=copy.deepcopy(output), usage={})


class RevisionFlowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.temp.name))
        self.store.set("topic", "Study allocation of inference budget")
        self.store.put("papers", {"id": "paper-1", "title": "Budget study", "content_kind": "abstract"})
        self.first_evidence = {"id": "ev-1", "paper_id": "paper-1", "source_kind": "abstract"}
        self.store.replace_evidence("paper-1", [self.first_evidence])
        self.config = dict(DEFAULTS, auto_search=False, builtin_skills=False,
                           max_rounds=5, max_calls=30, max_seconds=60, timeout_s=20, model="test-model")
        proposal = shape(SCHEMAS["propose"]["properties"]["candidates"]["items"])
        proposal.update(problem="Some questions need more inference than others.",
                        hypothesis="Observable signals can identify marginal benefit of extra inference.",
                        prediction="Matched-budget routing will change accuracy on held-out questions.")
        proposal["motivation"]["evidence_ids"] = ["ev-1"]
        self.candidate = {"id": "idea-1", "proposal": proposal, "versions": []}

    def tearDown(self):
        self.store.close()
        self.temp.cleanup()

    def controller(self, backend, **options):
        return Controller(self.store, backend, dict(self.config, **options))

    def test_unchanged_revision_stops_without_using_remaining_rounds(self):
        backend = ScriptedBackend(lambda _: method_spec(), lambda _: review_spec())
        self.controller(backend).develop_candidate(self.candidate)
        self.assertEqual([stage for stage, _ in backend.calls], ["develop", "review", "refine", "review"])
        self.assertEqual(len(self.candidate["versions"]), 2)
        self.assertEqual(self.candidate["research_status"], "no_detectable_progress")
        self.assertEqual(self.candidate["empirical_status"], "untested")
        self.assertEqual(self.candidate["recommended_action"]["kind"], method_spec()['next_action']['kind'])
        self.assertEqual(self.candidate["recommended_action"]["description"], method_spec()['next_action']['description'])
        self.assertIn("routing signal", self.candidate["recommended_action"]["decision_impact"])
        saved = self.store.rows("candidates")[0]
        record = saved["versions"][-1]["revision_record"]
        self.assertEqual(record["changed_fields"], [])
        self.assertEqual(record["progress_check"]["outcome"], "no_detectable_progress")
        self.assertIn("does not establish", record["progress_check"]["limitation"])
        self.assertEqual(record["previous_objections"], review_spec()["issues"])
        self.assertEqual(record["pending_concerns"]["issues"], review_spec()["issues"])
        self.assertEqual(record["previous_revision_instructions"], review_spec()["revision_instructions"])
        before = len(backend.calls)
        self.controller(backend).develop_candidate(self.candidate)
        self.assertEqual(len(backend.calls), before)

    def test_positive_review_still_delivers_its_specific_revision_to_designer(self):
        reviews = []
        def review(payload):
            reviews.append(payload)
            result = review_spec()
            result['verdict'] = 'continue'
            result['issues'][0]['severity'] = 'minor'
            if len(reviews) > 1:
                result.update(issues=[], revision_instructions='')
                result['next_action']['kind'] = 'stop'
            return result
        def method(payload):
            spec = method_spec()
            spec['method']['changes'] = [f"Explain marginal benefit in revision {payload['round']}."]
            return spec
        backend = ScriptedBackend(method, review)
        self.controller(backend).develop_candidate(self.candidate)
        self.assertEqual([stage for stage, _ in backend.calls], ['develop', 'review', 'refine', 'review'])
        refine_payload = next(payload for stage, payload in backend.calls if stage == 'refine')
        self.assertEqual(refine_payload['review']['verdict'], 'continue')
        self.assertEqual(refine_payload['review']['issues'][0]['severity'], 'minor')
        self.assertTrue(self.candidate['spec']['review_responses'])

    def test_completed_older_run_resumes_pending_revision_within_existing_limit(self):
        def approved_review(_):
            result = review_spec('stop')
            result.update(verdict='continue', issues=[], revision_instructions='')
            return result
        backend = ScriptedBackend(lambda _: method_spec(), approved_review)
        controller = self.controller(backend, max_rounds=2)
        controller.develop_candidate(self.candidate)
        self.assertEqual(len(self.candidate['versions']), 1)
        # Reproduce a saved result from the old controller, which ignored this action.
        pending = review_spec()
        pending['verdict'] = 'continue'
        self.candidate['versions'][0]['review'] = pending
        self.candidate['review'] = pending
        self.store.put('candidates', self.candidate)
        before = len(backend.calls)
        controller.develop_candidate(self.candidate)
        self.assertEqual([stage for stage, _ in backend.calls[before:]], ['refine', 'review'])
        self.assertEqual(len(self.candidate['versions']), 2)
        # A leftover request at the configured limit cannot restart the run.
        self.candidate['versions'][-1]['review'] = pending
        before = len(backend.calls)
        controller.develop_candidate(self.candidate)
        self.assertEqual(len(backend.calls), before)

    def test_changed_action_alone_does_not_count_as_substantive_progress(self):
        def output(payload):
            spec = method_spec()
            spec["next_action"]["description"] = f"Reword the next step in round {payload['round']}."
            return spec
        backend = ScriptedBackend(output, lambda _: review_spec())
        self.controller(backend).develop_candidate(self.candidate)
        self.assertEqual(len(self.candidate["versions"]), 2)
        self.assertEqual(self.candidate["research_status"], "no_detectable_progress")

    def test_changed_method_continues_and_records_field_delta(self):
        def output(payload):
            spec = method_spec()
            spec["method"]["changes"].append(f"Add predeclared control number {payload['round']}.")
            return spec
        backend = ScriptedBackend(output, lambda _: review_spec())
        self.controller(backend, max_rounds=3).develop_candidate(self.candidate)
        self.assertEqual(len(self.candidate["versions"]), 3)
        self.assertEqual(self.candidate["research_status"], "round_limit_reached")
        second = self.candidate["versions"][1]["revision_record"]
        self.assertEqual(second["progress_check"]["outcome"], "changed")
        self.assertEqual(second["changed_fields"][0]["field"], "method.changes")
        self.assertIn("control number 1", second["changed_fields"][0]["previous"][-1])
        self.assertIn("control number 2", second["changed_fields"][0]["current"][-1])
        self.assertEqual(second["pending_concerns"]["issues"], review_spec()["issues"])

    def test_new_evidence_allows_same_method_to_be_reconsidered(self):
        backend = ScriptedBackend(lambda _: method_spec(), lambda _: review_spec("search"))
        controller = self.controller(backend, max_rounds=3)
        searches = []
        def search(query, reason, **kwargs):
            searches.append(query)
            if len(searches) != 1:
                return False
            self.store.replace_evidence("paper-1", [self.first_evidence,
                {"id": "ev-2", "paper_id": "paper-1", "source_kind": "abstract"}])
            return True
        controller.search_once = search
        controller.read_papers = lambda: None
        controller.develop_candidate(self.candidate)
        self.assertEqual(len(self.candidate["versions"]), 3)
        second = self.candidate["versions"][1]["revision_record"]
        self.assertEqual(second["new_evidence_ids"], ["ev-2"])
        self.assertEqual(second["changed_fields"], [])
        self.assertEqual(second["progress_check"]["outcome"], "changed")

    def test_late_search_breaks_an_otherwise_exact_repeat(self):
        backend = ScriptedBackend(lambda _: method_spec(), lambda _: review_spec("search"))
        controller = self.controller(backend, max_rounds=3)
        searches = []
        def search(query, reason, **kwargs):
            searches.append(query)
            if len(searches) != 2:
                return False
            self.store.replace_evidence("paper-1", [self.first_evidence,
                {"id": "ev-2", "paper_id": "paper-1", "source_kind": "abstract"}])
            return True
        controller.search_once = search
        controller.read_papers = lambda: None
        controller.develop_candidate(self.candidate)
        self.assertEqual(len(self.candidate["versions"]), 3)
        second = self.candidate["versions"][1]["revision_record"]
        self.assertEqual(second["new_evidence_ids_after_action"], ["ev-2"])
        self.assertEqual(second["progress_check"]["outcome"], "evidence_changed_after_action")
        self.assertNotEqual(self.candidate["research_status"], "no_detectable_progress")

    def test_original_anchor_is_independent_of_revision_text_and_snapshot_mutation(self):
        expected = {key: self.candidate["proposal"][key] for key in ("problem", "hypothesis", "prediction")}
        def output(payload):
            spec = method_spec()
            spec["motivation"]["problem_observation"] = f"Revised explanation in round {payload['round']}."
            return spec
        backend = ScriptedBackend(output, lambda _: review_spec())
        self.controller(backend, max_rounds=3).develop_candidate(self.candidate)
        self.assertEqual(self.candidate["original_anchor"], expected)
        for version in self.candidate["versions"]:
            self.assertEqual(version["revision_record"]["original_anchor"], expected)
        for _, payload in backend.calls:
            self.assertEqual({key: payload["candidate"][key] for key in expected}, expected)
        self.candidate["versions"][-1]["revision_record"]["original_anchor"]["hypothesis"] = "Mutated caller copy"
        self.assertEqual(self.candidate["versions"][0]["revision_record"]["original_anchor"], expected)
        self.assertEqual(self.candidate["original_anchor"], expected)

    def test_same_spec_with_continue_review_is_not_a_stall(self):
        calls = []
        def output(payload):
            spec = method_spec()
            if payload["round"] == 2:
                spec["next_action"]["description"] = "Inspect the source for the next diagnostic."
            return spec
        def review(payload):
            calls.append(payload)
            result = review_spec()
            if len(calls) == 2:
                result.update(verdict="continue", issues=[], revision_instructions="")
            return result
        backend = ScriptedBackend(output, review)
        self.controller(backend).develop_candidate(self.candidate)
        self.assertEqual(len(self.candidate["versions"]), 2)
        self.assertNotEqual(self.candidate["research_status"], "no_detectable_progress")


if __name__ == "__main__":
    unittest.main()
