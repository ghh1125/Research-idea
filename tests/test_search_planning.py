"""Initial search plans are bounded intentions, not invented literature."""
from __future__ import annotations

import copy
import unittest

from research_idea.search_planning import normalize_search_plan
from research_idea.demo import demo_design_plan


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
    def routed_plan(self, count=3):
        value = plan()
        value['research_routes'] = [
            {'id': f'route-{index}', 'question': f'Research question {index}?',
             'why_relevant': f'Connection {index} to the original goal.'}
            for index in range(count)]
        for index, query in enumerate(value['queries']):
            query['route_ids'] = [f'route-{index % count}'] if count else []
        return value

    def test_discovery_routes_allow_six_queries_and_preserve_late_route_coverage(self):
        value = self.routed_plan(4)
        value['queries'] = [dict(value['queries'][0], query=f'language model route {index}',
                                 route_ids=['route-0']) for index in range(7)]
        value['queries'].extend(dict(value['queries'][0], query=f'alternative evidence {index}',
                                     route_ids=[f'route-{index}']) for index in range(1, 4))
        result = normalize_search_plan(value)
        self.assertEqual(len(result['queries']), 6)
        self.assertEqual({route for query in result['queries'] for route in query['route_ids']},
                         {route['id'] for route in value['research_routes']})
        self.assertEqual(result['research_routes'], value['research_routes'])

    def test_shared_discovery_query_preserves_all_routes_without_mutation(self):
        value = self.routed_plan()
        value['queries'][1]['query'] = value['queries'][0]['query'].upper()
        before = copy.deepcopy(value)
        result = normalize_search_plan(value)
        self.assertEqual(len(result['queries']), 2)
        self.assertEqual(result['queries'][0]['route_ids'], ['route-0', 'route-1'])
        self.assertEqual(result['queries'][0]['purpose'], 'background')
        self.assertEqual(value, before)

    def test_discovery_does_not_require_three_routes(self):
        value = self.routed_plan(1)
        value['queries'] = value['queries'][:1]
        self.assertEqual(len(normalize_search_plan(value)['research_routes']), 1)
        value = self.routed_plan(0)
        self.assertEqual(normalize_search_plan(value)['research_routes'], [])

    def test_route_links_and_identifiers_are_structurally_validated(self):
        for change in ('duplicate', 'unknown', 'missing_query', 'empty_link', 'too_many'):
            with self.subTest(change=change):
                value = self.routed_plan()
                if change == 'duplicate':
                    value['research_routes'][1]['id'] = 'route-0'
                elif change == 'unknown':
                    value['queries'][0]['route_ids'] = ['invented']
                elif change == 'missing_query':
                    value['queries'] = value['queries'][:2]
                elif change == 'empty_link':
                    value['queries'][0]['route_ids'] = []
                else:
                    value['research_routes'].extend([
                        {'id': str(index), 'question': 'Question?', 'why_relevant': 'Relation.'}
                        for index in range(2)])
                with self.assertRaises(ValueError):
                    normalize_search_plan(value)

    def test_technical_plan_keeps_three_queries_and_no_discovery_routes(self):
        value = demo_design_plan()
        value['research_routes'] = []
        for query in value['queries']:
            query['route_ids'] = []
        value['queries'].extend([dict(value['queries'][0], query='alternative transfer principle'),
                                 dict(value['queries'][0], query='further implementation method')])
        result = normalize_search_plan(value, technical=True)
        self.assertEqual(len(result['queries']), 3)
        self.assertEqual(result['research_routes'], [])
        self.assertTrue(all(query['route_ids'] == [] for query in result['queries']))
        value['research_routes'] = self.routed_plan(1)['research_routes']
        with self.assertRaisesRegex(ValueError, 'Technical design'):
            normalize_search_plan(value, technical=True)

    def test_technical_queries_preserve_their_angles_when_deduplicated(self):
        value = demo_design_plan()
        value['queries'][1]['query'] = value['queries'][0]['query'].upper()
        result = normalize_search_plan(value, technical=True)
        self.assertEqual(len(result['queries']), 1)
        self.assertEqual(result['queries'][0]['axis_ids'], ['relations', 'use'])
        self.assertEqual(result['design_axes'], value['design_axes'])

    def test_technical_plan_requires_two_distinct_angles_and_queries_for_both(self):
        for change in ('missing_angle', 'duplicate_id', 'unknown_link', 'lost_angle'):
            with self.subTest(change=change):
                value = demo_design_plan()
                if change == 'missing_angle':
                    value['design_axes'].pop()
                elif change == 'duplicate_id':
                    value['design_axes'][1]['id'] = value['design_axes'][0]['id']
                elif change == 'unknown_link':
                    value['queries'][0]['axis_ids'] = ['invented']
                else:
                    value['queries'] = value['queries'][:1]
                with self.assertRaises(ValueError):
                    normalize_search_plan(value, technical=True)

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
        for value in (None, 1, [], "search words"):
            with self.subTest(plan=value), self.assertRaises(ValueError):
                normalize_search_plan(value)
        for field, replacement in (("research_question", 1), ("scope", None),
                                   ("queries", "search words"), ("queries", ["search words"]),
                                   ("queries", [None]), ("queries", [1]),
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
