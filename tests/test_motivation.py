"""Research motivation is an evidence-linked argument, never a keyword score."""
from __future__ import annotations

import copy
import unittest

from research_idea.motivation import assess_motivation


EVIDENCE = [{"id": "ev-observation", "verification": "quote_matched_only"}]


def proposal():
    return {"motivation": {
        "basis": "source_observation",
        "problem_observation": "The supplied source reports an unresolved failure under a specified condition.",
        "evidence_ids": ["ev-observation"],
        "importance": "This failure prevents the target task from meeting its stated requirement.",
        "existing_approach_limit": "The current approach does not distinguish the two relevant causes.",
        "causal_explanation": "The proposed causal explanation connects the observed failure to an intervention.",
        "why_this_method": "The method targets that causal variable while retaining the original task.",
        "expected_progress": "The experiment would separate explanations with different observable predictions.",
        "simplest_alternative": "Use the existing system with a simple fixed intervention.",
        "necessity_test": "Compare the proposed and simplest interventions under the same conditions.",
    }}


def review(**overrides):
    assessment = {
        "problem_significance": "substantial", "causal_link": "plausible",
        "progress": "substantive", "reason": "The argument identifies a consequential unresolved mechanism.",
        "decisive_test": "Test the competing explanations against the simplest controlled alternative.",
    }
    assessment.update(overrides)
    return {"motivation_assessment": assessment}


class MotivationTests(unittest.TestCase):
    def test_limited_problem_requires_revision(self):
        result = assess_motivation(proposal(), review(problem_significance="limited"), EVIDENCE)
        self.assertEqual(result["status"], "needs_revision")
        self.assertEqual(result["unresolved"][0]["dimension"], "problem_significance")
        self.assertTrue(result["unresolved"][0]["decisive_test"])

    def test_unsupported_causal_link_requires_revision(self):
        result = assess_motivation(proposal(), review(causal_link="unsupported"), EVIDENCE)
        self.assertEqual(result["status"], "needs_revision")
        self.assertEqual(result["unresolved"][0]["assessment"], "unsupported")

    def test_incremental_tradeoff_requires_revision_even_when_problem_matters(self):
        result = assess_motivation(proposal(), review(progress="incremental"), EVIDENCE)
        self.assertEqual(result["status"], "needs_revision")
        self.assertEqual(result["unresolved"][0]["dimension"], "progress")

    def test_unclear_dimension_is_unresolved(self):
        for dimension in ("problem_significance", "causal_link", "progress"):
            with self.subTest(dimension=dimension):
                result = assess_motivation(proposal(), review(**{dimension: "unclear"}), EVIDENCE)
                self.assertEqual(result["status"], "motivation_unresolved")
                self.assertEqual(result["unresolved"][0]["dimension"], dimension)

    def test_revision_takes_precedence_and_unknowns_are_retained(self):
        result = assess_motivation(proposal(), review(causal_link="unclear", progress="incremental"), EVIDENCE)
        self.assertEqual(result["status"], "needs_revision")
        self.assertEqual({item["dimension"] for item in result["unresolved"]}, {"causal_link", "progress"})

    def test_positive_review_is_only_an_argument_and_does_not_mutate_inputs(self):
        idea, critique = proposal(), review()
        before = copy.deepcopy((idea, critique, EVIDENCE))
        result = assess_motivation(idea, critique, EVIDENCE)
        self.assertEqual(result["status"], "argued_not_validated")
        self.assertEqual(result["unresolved"], [])
        self.assertTrue(any("model review opinions" in warning for warning in result["warnings"]))
        self.assertEqual((idea, critique, EVIDENCE), before)

    def test_keywords_and_prose_length_do_not_decide_significance(self):
        for statement in ("A small tradeoff may expose an important mechanism.",
                          "重大创新 " * 500, "短"):
            with self.subTest(statement=statement[:30]):
                idea = proposal()
                idea["motivation"]["expected_progress"] = statement
                self.assertEqual(assess_motivation(idea, review(), EVIDENCE)["status"], "argued_not_validated")
                self.assertEqual(assess_motivation(idea, review(progress="incremental"), EVIDENCE)["status"], "needs_revision")

    def test_missing_or_empty_motivation_fields_require_repair(self):
        fields = set(proposal()["motivation"]) - {"evidence_ids", "basis"}
        for field in fields:
            for mode in ("missing", "blank", "wrong_type"):
                with self.subTest(field=field, mode=mode):
                    idea = proposal()
                    if mode == "missing":
                        del idea["motivation"][field]
                    else:
                        idea["motivation"][field] = "  " if mode == "blank" else 42
                    with self.assertRaisesRegex(ValueError, field):
                        assess_motivation(idea, review(), EVIDENCE)

    def test_missing_or_unknown_evidence_requires_repair(self):
        for refs in ([], ["invented"], "ev-observation", [None]):
            with self.subTest(refs=refs):
                idea = proposal()
                idea["motivation"]["evidence_ids"] = refs
                with self.assertRaises(ValueError):
                    assess_motivation(idea, review(), EVIDENCE)

    def test_review_needs_classifications_reason_and_decisive_test(self):
        for field in ("problem_significance", "causal_link", "progress", "reason", "decisive_test"):
            for mode in ("missing", "blank"):
                with self.subTest(field=field, mode=mode):
                    critique = review()
                    if mode == "missing":
                        del critique["motivation_assessment"][field]
                    else:
                        critique["motivation_assessment"][field] = ""
                    with self.assertRaisesRegex(ValueError, field):
                        assess_motivation(proposal(), critique, EVIDENCE)

    def test_missing_objects_require_repair(self):
        for idea, critique in (({}, review()), (proposal(), {})):
            with self.subTest(idea=idea, critique=critique), self.assertRaises(ValueError):
                assess_motivation(idea, critique, EVIDENCE)


if __name__ == "__main__":
    unittest.main()
