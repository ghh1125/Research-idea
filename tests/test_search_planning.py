"""Initial search plans are bounded intentions, not invented literature."""
from __future__ import annotations

import copy
import unittest

from research_idea.search_planning import normalize_search_plan


def plan():
    return {
        "research_question": "How does adaptation affect reasoning under distribution shift?",
        "scope": "LLM inference-time adaptation with observable inference signals.",
        "queries": [
            {"query": "language model test time adaptation distribution shift", "purpose": "background",
             "rationale": "Find the relevant task settings and existing adaptation methods."},
            {"query": "language model adaptation feedback reliability mechanism", "purpose": "mechanism",
             "rationale": "Find explanations connecting available feedback and adaptation behavior."},
            {"query": "test time adaptation negative results language models", "purpose": "counterevidence",
             "rationale": "Find conditions where adaptation does not help."},
        ],
        "assumptions": ["Access to model weights and logits is not established."],
    }


class SearchPlanningTests(unittest.TestCase):
    def test_normalizes_whitespace_without_mutating_input(self):
        value = plan()
        value["research_question"] = "  How does\n adaptation work? "
        value["queries"][0]["query"] = "  language\tmodel\n adaptation  "
        value["queries"][0]["rationale"] = " Find\n background. "
        value["assumptions"] = ["  Access is\tunknown. "]
        before = copy.deepcopy(value)
        result = normalize_search_plan(value)
        self.assertEqual(result["research_question"], "How does adaptation work?")
        self.assertEqual(result["queries"][0]["query"], "language model adaptation")
        self.assertEqual(result["queries"][0]["rationale"], "Find background.")
        self.assertEqual(result["assumptions"], ["Access is unknown."])
        self.assertEqual(value, before)

    def test_deduplicates_before_capping_and_preserves_first_purpose(self):
        value = plan()
        first = value["queries"][0]
        value["queries"].insert(1, dict(first, query=first["query"].upper(), purpose="mechanism"))
        value["queries"].append({"query": "language model calibration", "purpose": "background", "rationale": "A fourth direction."})
        result = normalize_search_plan(value)
        self.assertEqual(len(result["queries"]), 3)
        self.assertEqual(result["queries"][0]["purpose"], "background")
        self.assertEqual(result["queries"][-1]["purpose"], "counterevidence")
        self.assertNotIn("language model calibration", [item["query"] for item in result["queries"]])

    def test_one_query_and_no_assumptions_are_allowed(self):
        value = plan()
        value["queries"] = value["queries"][:1]
        value["assumptions"] = []
        self.assertEqual(len(normalize_search_plan(value)["queries"]), 1)

    def test_mixed_script_names_and_accented_latin_are_allowed(self):
        for query in ("Qwen 中文模型 inference-time adaptation", "Müller model calibration", "évaluation"):
            with self.subTest(query=query):
                value = plan()
                value["research_question"] = "大模型在分布偏移下如何调整？"
                value["queries"][0]["query"] = query
                self.assertEqual(normalize_search_plan(value)["queries"][0]["query"], query)

    def test_entirely_untranslated_query_requires_repair(self):
        value = plan()
        value["queries"][0]["query"] = "大模型测试时适应分布偏移"
        with self.assertRaisesRegex(ValueError, "English academic keywords"):
            normalize_search_plan(value)

    def test_empty_plan_components_require_repair(self):
        for field in ("research_question", "scope", "queries"):
            with self.subTest(field=field):
                value = plan()
                value[field] = [] if field == "queries" else " \n "
                with self.assertRaises(ValueError):
                    normalize_search_plan(value)
        for field in ("query", "purpose", "rationale"):
            with self.subTest(field=field):
                value = plan()
                value["queries"][0][field] = " "
                with self.assertRaisesRegex(ValueError, field):
                    normalize_search_plan(value)

    def test_invalid_types_and_purposes_require_repair(self):
        for field, replacement in (("research_question", 1), ("scope", None),
                                   ("queries", "search words"), ("queries", ["search words"]),
                                   ("assumptions", "one assumption"), ("assumptions", [None])):
            with self.subTest(field=field, replacement=replacement):
                value = plan()
                value[field] = replacement
                with self.assertRaises(ValueError):
                    normalize_search_plan(value)
        value = plan()
        value["queries"][0]["purpose"] = "prove_my_idea"
        with self.assertRaisesRegex(ValueError, "purpose"):
            normalize_search_plan(value)

    def test_extra_paper_metadata_and_missing_fields_are_rejected(self):
        value = plan()
        value["papers"] = [{"title": "An invented title", "doi": "10.fake/example"}]
        with self.assertRaisesRegex(ValueError, "unexpected"):
            normalize_search_plan(value)
        value = plan()
        value["queries"][0]["paper_id"] = "invented"
        with self.assertRaisesRegex(ValueError, "unexpected"):
            normalize_search_plan(value)
        for field in ("research_question", "scope", "queries", "assumptions"):
            with self.subTest(field=field):
                value = plan()
                del value[field]
                with self.assertRaisesRegex(ValueError, "missing"):
                    normalize_search_plan(value)

    def test_length_and_input_bounds_require_repair(self):
        for query in ("a" * 301, "word " * 41, "model\x00adaptation"):
            with self.subTest(query=query[:30]):
                value = plan()
                value["queries"][0]["query"] = query
                with self.assertRaises(ValueError):
                    normalize_search_plan(value)
        value = plan()
        value["queries"] = [value["queries"][0]] * 201
        with self.assertRaises(ValueError):
            normalize_search_plan(value)

    def test_invalid_fourth_query_cannot_hide_after_truncation(self):
        value = plan()
        value["queries"].append({"query": " ", "purpose": "background", "rationale": "Invalid trailing item."})
        with self.assertRaisesRegex(ValueError, r"queries\[3\]"):
            normalize_search_plan(value)


if __name__ == "__main__":
    unittest.main()
