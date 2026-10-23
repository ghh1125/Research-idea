"""Practical prerequisite gates reject inaccessible signals and paper-only confidence."""
from __future__ import annotations

import copy
import unittest

from research_agent.feasibility import assess_feasibility


DIMENSIONS = ["data_access", "inference_signal", "interface", "learning_signal",
              "compute", "evaluation", "minimal_test"]
EVIDENCE = [{"id": "ev-source", "verification": "quote_matched_only"}]


def specification():
    return {"feasibility": {"checks": [{
        "dimension": dimension, "status": "source_supported",
        "requirement": f"The proposed method needs a compatible {dimension} condition.",
        "evidence_ids": ["ev-source"],
        "verification_plan": f"Check {dimension} in the actual project environment.",
        "failure_action": f"Revise the method if {dimension} cannot be satisfied.",
    } for dimension in DIMENSIONS], "required_signals": []}}


def signal(name="token logits", needed_at="inference", availability="unavailable"):
    return {"name": name, "needed_at": needed_at, "availability": availability,
            "evidence_ids": ["ev-source"] if availability == "source_supported" else [],
            "acquisition_plan": "Inspect the selected model interface before proceeding.",
            "substitute": "A surrogate is proposed but has not been validated."}


class FeasibilityTests(unittest.TestCase):
    def test_inference_ground_truth_is_blocked_despite_optimistic_review(self):
        spec = specification()
        spec["review"] = {"verdict": "continue"}
        spec["feasibility"]["required_signals"] = [signal("ground truth answer")]
        result = assess_feasibility(spec, EVIDENCE)
        self.assertEqual(result["status"], "blocked")
        self.assertEqual(result["blocking_checks"][0]["needed_at"], "inference")
        self.assertIn("substitute", result["blocking_checks"][0]["reason"])

    def test_missing_logits_gradients_or_evaluation_labels_block(self):
        for name, stage in [("token logits", "inference"),
                            ("weight gradients", "training"),
                            ("reference labels", "evaluation")]:
            with self.subTest(name=name):
                spec = specification()
                spec["feasibility"]["required_signals"] = [signal(name, stage)]
                result = assess_feasibility(spec, EVIDENCE)
                self.assertEqual(result["status"], "blocked")
                self.assertEqual(result["blocking_checks"][0]["name"], name)

    def test_gpu_estimate_and_pending_interface_remain_unverified(self):
        spec = specification()
        for check in spec["feasibility"]["checks"]:
            if check["dimension"] in {"compute", "interface"}:
                check.update(status="unverified", evidence_ids=[])
        result = assess_feasibility(spec, EVIDENCE)
        self.assertEqual(result["status"], "prerequisites_unverified")
        self.assertEqual({c["dimension"] for c in result["unverified_checks"]},
                         {"compute", "interface"})

    def test_unverified_signal_prevents_fully_specified_status(self):
        spec = specification()
        spec["feasibility"]["required_signals"] = [signal(availability="unverified")]
        result = assess_feasibility(spec, EVIDENCE)
        self.assertEqual(result["status"], "prerequisites_unverified")
        self.assertEqual(result["unverified_checks"][0]["kind"], "required_signal")

    def test_blocked_dimension_takes_precedence_but_preserves_unknowns(self):
        spec = specification()
        spec["feasibility"]["checks"][0].update(status="blocked", evidence_ids=[])
        spec["feasibility"]["checks"][1].update(status="unverified", evidence_ids=[])
        result = assess_feasibility(spec, EVIDENCE)
        self.assertEqual(result["status"], "blocked")
        self.assertEqual(len(result["blocking_checks"]), 1)
        self.assertEqual(len(result["unverified_checks"]), 1)
        self.assertTrue(result["blocking_checks"][0]["failure_action"])

    def test_all_sources_do_not_establish_execution_or_success(self):
        spec = specification()
        spec["feasibility"]["required_signals"] = [signal(availability="source_supported")]
        before = copy.deepcopy(spec)
        result = assess_feasibility(spec, EVIDENCE)
        self.assertEqual(result["status"], "specified_not_executed")
        self.assertEqual(result["blocking_checks"], [])
        self.assertEqual(result["unverified_checks"], [])
        self.assertTrue(any("no code" in w for w in result["warnings"]))
        self.assertEqual(spec, before)

    def test_missing_duplicate_or_unknown_dimensions_require_repair(self):
        for case in ("missing", "duplicate", "unknown"):
            with self.subTest(case=case):
                spec = specification()
                checks = spec["feasibility"]["checks"]
                if case == "missing":
                    checks.pop()
                elif case == "duplicate":
                    checks.append(copy.deepcopy(checks[0]))
                else:
                    checks[0]["dimension"] = "paper_score"
                with self.assertRaisesRegex(ValueError, "exactly once"):
                    assess_feasibility(spec, EVIDENCE)

    def test_source_supported_check_requires_real_reference(self):
        for refs in ([], ["invented"]):
            with self.subTest(refs=refs):
                spec = specification()
                spec["feasibility"]["checks"][0]["evidence_ids"] = refs
                with self.assertRaises(ValueError):
                    assess_feasibility(spec, EVIDENCE)

    def test_source_supported_signal_requires_real_reference(self):
        for refs in ([], ["invented"]):
            with self.subTest(refs=refs):
                spec = specification()
                item = signal(availability="source_supported")
                item["evidence_ids"] = refs
                spec["feasibility"]["required_signals"] = [item]
                with self.assertRaises(ValueError):
                    assess_feasibility(spec, EVIDENCE)

    def test_every_check_requires_verification_and_failure_actions(self):
        for status in ("source_supported", "unverified", "blocked", "not_applicable"):
            for field in ("verification_plan", "failure_action"):
                with self.subTest(status=status, field=field):
                    spec = specification()
                    check = spec["feasibility"]["checks"][0]
                    check.update(status=status)
                    check[field] = "  "
                    with self.assertRaisesRegex(ValueError, field):
                        assess_feasibility(spec, EVIDENCE)

    def test_not_applicable_requires_reason_and_keeps_verification_plan(self):
        spec = specification()
        check = spec["feasibility"]["checks"][3]
        check.update(status="not_applicable", evidence_ids=[],
                     requirement="The method only reranks frozen model outputs; it performs no training.")
        plan = check["verification_plan"]
        self.assertEqual(assess_feasibility(spec, EVIDENCE)["status"], "specified_not_executed")
        self.assertEqual(check["verification_plan"], plan)
        for reason in ("", "N/A", "not applicable", "不适用"):
            with self.subTest(reason=reason):
                check["requirement"] = reason
                with self.assertRaises(ValueError):
                    assess_feasibility(spec, EVIDENCE)


if __name__ == "__main__":
    unittest.main()
