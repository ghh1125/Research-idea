"""Regression cases for premature rejection and unsupported novelty claims."""
from __future__ import annotations

import copy
import unittest

from research_agent.novelty import DIMENSIONS, assess_novelty, validate_comparisons


def example(verdict="covered", source_kind="full_text"):
    evidence = [{"id": "ev-1", "paper_id": "paper-1", "source_kind": source_kind}]
    overlap = {
        "paper_id": "paper-1", "level": "core_claim", "covered_claim": "Budget allocation improves accuracy at fixed total compute.",
        "evidence_ids": ["ev-1"], "remaining_gap": "",
        "comparisons": [
            {"dimension": dimension, "prior_detail": f"Specified prior {dimension} under fixed inference budget.",
             "proposed_detail": f"Specified prior {dimension} under fixed inference budget.",
             "relation": "same", "evidence_ids": ["ev-1"]}
            for dimension in DIMENSIONS
        ],
    }
    spec = {"prior_art": {"verdict": verdict, "overlaps": [overlap]}, "novelty_claim": {
        "type": "mechanism", "claim": "A marginal-gain signal can allocate the same total inference budget more accurately.",
        "changed_variable": "Route computation by predicted marginal gain rather than answer uncertainty.",
        "observable_consequence": "At matched total tokens, accuracy exceeds uncertainty-based routing.",
        "falsifier": "The gain signal fails to predict benefit from extra computation on held-out cases.",
        "nontriviality": "The routing target predicts benefit of intervention, rather than probability of current error.",
    }}
    return spec, evidence


def differ(spec, dimension="mechanism"):
    comparison = next(c for c in spec["prior_art"]["overlaps"][0]["comparisons"] if c["dimension"] == dimension)
    comparison["relation"] = "different"
    comparison["proposed_detail"] = "Route additional samples by predicted benefit of intervention."


class NoveltyTests(unittest.TestCase):
    def test_title_or_topic_similarity_never_rejects(self):
        for level in ("title", "topic", "problem", "mechanism"):
            spec, evidence = example()
            spec["prior_art"]["overlaps"][0]["level"] = level
            with self.subTest(level=level):
                self.assertEqual(assess_novelty(spec, evidence)["status"], "uncertain")

    def test_abstract_cannot_cover_even_with_six_same_dimensions(self):
        spec, evidence = example(source_kind="abstract")
        result = assess_novelty(spec, evidence)
        self.assertEqual(result["status"], "uncertain")
        self.assertTrue(any("branch was not rejected" in warning for warning in result["warnings"]))
        self.assertEqual(sum("no full-text" in gap for gap in result["comparison_gaps"]), 6)

    def test_coverage_requires_every_dimension_grounded_not_an_overlap_citation(self):
        spec, evidence = example()
        spec["prior_art"]["overlaps"][0]["comparisons"][2]["evidence_ids"] = []
        self.assertEqual(assess_novelty(spec, evidence)["status"], "uncertain")

    def test_full_core_claim_comparison_can_support_coverage(self):
        spec, evidence = example()
        self.assertEqual(assess_novelty(spec, evidence)["status"], "covered")

    def test_legacy_or_incomplete_comparisons_remain_uncertain(self):
        for operation in (lambda overlap: overlap.pop("comparisons"), lambda overlap: overlap["comparisons"].pop()):
            spec, evidence = example()
            operation(spec["prior_art"]["overlaps"][0])
            result = assess_novelty(spec, evidence)
            self.assertEqual(result["status"], "uncertain")
            self.assertTrue(result["comparison_gaps"])

    def test_empty_or_placeholder_details_cannot_support_coverage(self):
        for detail in ("", "  ", "unknown", "TBD", "same"):
            spec, evidence = example()
            spec["prior_art"]["overlaps"][0]["comparisons"][0]["prior_detail"] = detail
            with self.subTest(detail=detail):
                self.assertEqual(assess_novelty(spec, evidence)["status"], "uncertain")

    def test_substantive_difference_is_bounded_to_corpus(self):
        spec, evidence = example("difference_supported")
        differ(spec)
        self.assertEqual(assess_novelty(spec, evidence)["status"], "difference_argued_in_supplied_corpus")

    def test_problem_or_evaluation_difference_alone_is_insufficient(self):
        for dimension in ("problem", "evaluation"):
            spec, evidence = example("difference_supported")
            differ(spec, dimension)
            self.assertEqual(assess_novelty(spec, evidence)["status"], "uncertain")

    def test_difference_requires_full_text_and_substantive_claim(self):
        spec, evidence = example("difference_supported", "abstract")
        differ(spec)
        self.assertEqual(assess_novelty(spec, evidence)["status"], "uncertain")
        evidence[0]["source_kind"] = "full_text"
        spec["novelty_claim"]["falsifier"] = ""
        self.assertEqual(assess_novelty(spec, evidence)["status"], "uncertain")

    def test_identical_descriptions_do_not_establish_a_difference(self):
        spec, evidence = example("difference_supported")
        spec["prior_art"]["overlaps"][0]["comparisons"][1]["relation"] = "different"
        self.assertEqual(assess_novelty(spec, evidence)["status"], "uncertain")

    def test_unknown_key_comparison_is_exposed_even_with_another_difference(self):
        spec, evidence = example("difference_supported")
        differ(spec)
        comparison = spec["prior_art"]["overlaps"][0]["comparisons"][2]
        comparison.update(relation="unknown", prior_detail="", proposed_detail="", evidence_ids=[])
        result = assess_novelty(spec, evidence)
        self.assertEqual(result["status"], "difference_argued_in_supplied_corpus")
        self.assertTrue(any("paper-1/information: comparison is unknown" in gap for gap in result["comparison_gaps"]))

    def test_one_difference_does_not_override_another_fully_covering_work(self):
        spec, evidence = example("difference_supported")
        covering = copy.deepcopy(spec["prior_art"]["overlaps"][0])
        differ(spec)
        spec["prior_art"]["overlaps"].append(covering)
        self.assertEqual(assess_novelty(spec, evidence)["status"], "uncertain")

    def test_each_dimension_cannot_borrow_another_papers_evidence(self):
        spec, evidence = example()
        evidence.append({"id": "ev-2", "paper_id": "paper-2", "source_kind": "full_text"})
        spec["prior_art"]["overlaps"][0]["comparisons"][1]["evidence_ids"] = ["ev-2"]
        with self.assertRaisesRegex(ValueError, "different paper"):
            assess_novelty(spec, evidence)

    def test_unknown_reference_cannot_be_silently_ignored(self):
        spec, evidence = example()
        spec["prior_art"]["overlaps"][0]["comparisons"][1]["evidence_ids"] = ["invented"]
        with self.assertRaisesRegex(ValueError, "Unknown evidence"):
            assess_novelty(spec, evidence)

    def test_missing_and_duplicate_dimensions_fail_structural_validation(self):
        for duplicate in (False, True):
            spec, _ = example()
            comparisons = spec["prior_art"]["overlaps"][0]["comparisons"]
            comparisons.pop()
            if duplicate:
                comparisons.append(copy.deepcopy(comparisons[0]))
            with self.assertRaises(ValueError):
                validate_comparisons(spec["prior_art"]["overlaps"])

    def test_no_matches_does_not_prove_novelty(self):
        spec, evidence = example("difference_supported")
        spec["prior_art"]["overlaps"] = []
        self.assertEqual(assess_novelty(spec, evidence)["status"], "uncertain")


if __name__ == "__main__":
    unittest.main()
