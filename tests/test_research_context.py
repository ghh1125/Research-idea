"""Operational context compression must preserve the scientific argument."""
from copy import deepcopy
import json
import unittest

from research_idea.research_context import compact_research_context


class ResearchContextTests(unittest.TestCase):
    def test_large_inventories_and_transport_logs_are_reduced_without_losing_evidence(self):
        evidence = {'id': 'ev_1', 'paper_id': 'p1', 'quote': 'The exact source quote with its conditions.',
                    'kind': 'reported_result', 'conditions': 'one model, equal compute', 'start': 12, 'end': 61}
        context = {'topic': 'Understand how to learn new patterns from limited data',
            'user_notes': 'Do not narrow the question to one benchmark.',
            'evidence': [evidence],
            'paper_claim_audits': [{'paper_id': 'p1', 'claims': [{'warranted_conclusion': 'Limited source conclusion'}]}],
            'paper_cards': [{'paper_id': 'p1', 'framework': [{'summary': 'Important scientific finding'}],
                'analyst_concerns': [{'concern': 'A competing explanation'}],
                'inventory': {'text_coverage': 'partial', 'characters_supplied': 12000,
                    'sections': [{'id': f'section_{i}', 'title': 'Section', 'start': i, 'end': i + 100,
                                  'text_coverage': 'unread'} for i in range(1000)],
                    'assets': [{'caption': 'Caption' * 100} for _ in range(100)]}}],
            'search_coverage': [{'query': 'reuse old data', 'status': 'completed', 'coverage': {
                'source': 'hybrid', 'gaps': ['EMNLP source could not be resolved'],
                'providers': {'openalex': {'gaps': ['HTTP 429'], 'openalex_work_queries': ['request detail' * 1000] * 20}},
                'transport': {'requests': ['long request URL' * 1000] * 20}}}]}
        saved = deepcopy(context)
        compact = compact_research_context(context)
        self.assertEqual(context, saved)  # archival data remains complete
        self.assertEqual(compact['evidence'], [evidence])
        self.assertEqual(compact['topic'], context['topic'])
        self.assertEqual(compact['user_notes'], context['user_notes'])
        self.assertEqual(compact['paper_claim_audits'], context['paper_claim_audits'])
        self.assertEqual(compact['paper_cards'][0]['framework'], context['paper_cards'][0]['framework'])
        self.assertEqual(compact['paper_cards'][0]['analyst_concerns'], context['paper_cards'][0]['analyst_concerns'])
        self.assertEqual(compact['paper_cards'][0]['inventory']['text_coverage'], 'partial')
        self.assertEqual(compact['paper_cards'][0]['inventory']['sections_count'], 1000)
        self.assertEqual(compact['paper_cards'][0]['inventory']['sections'][0],
                         {'id': 'section_0', 'title': 'Section', 'text_coverage': 'unread'})
        self.assertEqual(compact['search_coverage'][0]['coverage']['gaps'], ['EMNLP source could not be resolved'])
        self.assertIn('HTTP 429', compact['search_coverage'][0]['coverage']['providers']['openalex']['gaps'])
        self.assertLess(len(json.dumps(compact)), len(json.dumps(context)) / 10)

    def test_long_history_reports_omissions_instead_of_claiming_complete_coverage(self):
        searches = [{'query': str(i), 'coverage': {'gaps': ['gap ' + str(j) for j in range(70)]}} for i in range(100)]
        compact = compact_research_context({'search_coverage': searches})
        self.assertEqual(len(compact['search_coverage']), 12)
        self.assertEqual(compact['search_coverage'][0]['query'], '88')
        self.assertEqual(compact['context_summary']['searches_recorded'], 100)
        coverage = compact['search_coverage'][0]['coverage']
        self.assertEqual(coverage['gap_count'], 70)
        self.assertTrue(coverage['gaps_are_examples'])
        self.assertEqual(len(coverage['gaps']), 3)

    def test_reading_inventory_absent_in_older_card_is_supported(self):
        compact = compact_research_context({'paper_cards': [{'paper_id': 'p1', 'framework': []}]})
        self.assertEqual(compact['paper_cards'], [{'paper_id': 'p1', 'framework': []}])
