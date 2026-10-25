"""Discovery receives its source cohort without prior candidate interpretations."""
from copy import deepcopy
import unittest

from research_idea.research_context import problem_discovery_context


class DiscoveryContextTests(unittest.TestCase):
    def source_context(self):
        return {
            'topic': 'The original research direction',
            'user_notes': ['User-supplied details must remain available.'],
            'constraints': {'resources': 'One device'},
            'papers': [
                {'id': 'initial', 'text': 'Full source remains unchanged.'},
                {'id': 'imported', 'text': 'User-provided source text.'},
                {'id': 'design', 'title': 'Later technical reference'},
            ],
            'evidence': [
                {'id': 'ev_source', 'paper_id': 'initial', 'extraction_stage': 'read_section',
                 'quote': 'An exact source quote.', 'conditions': 'The stated condition.'},
                {'id': 'ev_imported', 'paper_id': 'imported', 'quote': 'A manually imported quote.'},
                {'id': 'ev_focused', 'paper_id': 'initial', 'extraction_stage': 'inspect_source',
                 'quote': 'Another exact quote.', 'statement': 'Interpreted for the old candidate.'},
                {'id': 'ev_design', 'paper_id': 'design', 'extraction_stage': 'inspect_source'},
            ],
            'paper_cards': [
                {'paper_id': 'initial', 'evidence_ids': ['ev_source'],
                 'framework': [{'dimension': 'method', 'summary': 'The full method and its assumptions.'},
                               {'dimension': 'idea_relevance', 'summary': 'A proposed local fix.'}],
                 'components': [{'input': 'Available signal', 'evidence_ids': ['ev_source']}],
                 'analyst_concerns': [{'concern': 'An alternative explanation.',
                                       'discriminating_test': 'A future test.'}],
                 'opportunities': [{'idea': 'The reader-picked idea.'}]},
                {'paper_id': 'imported', 'status': 'source_limited', 'reading_gaps': ['No full paper.']},
                {'paper_id': 'design', 'evidence_ids': ['ev_design']},
            ],
            'paper_claim_audits': [
                {'paper_id': 'initial', 'claims': [{'claim_evidence_ids': ['ev_source'],
                                                  'result_evidence_ids': []}]},
                {'paper_id': 'design', 'claims': [{'claim_evidence_ids': ['ev_design']}]},
            ],
            'quote_gaps': {'g1': {'paper_id': 'initial', 'rejected': ['Unlocated quote']},
                           'g2': {'paper_id': 'design', 'rejected': ['Design quote']}},
            'retrieval_gaps': [{'paper_id': 'initial', 'status': 'partial'},
                               {'paper_id': 'design', 'status': 'failed'}],
        }

    def test_initial_cohort_retains_source_detail_and_user_input(self):
        context = self.source_context()
        original = deepcopy(context)
        view = problem_discovery_context(context, ['initial', 'imported'])
        self.assertEqual(context, original)
        for field in ('topic', 'user_notes', 'constraints'):
            self.assertEqual(view[field], original[field])
        self.assertEqual(view['papers'], original['papers'][:2])
        self.assertEqual(view['evidence'], original['evidence'][:2])
        self.assertEqual(view['paper_cards'][0]['components'], original['paper_cards'][0]['components'])
        self.assertEqual(view['paper_cards'][1], original['paper_cards'][1])
        self.assertEqual(view['paper_cards'][0]['framework'], original['paper_cards'][0]['framework'][:1])
        self.assertEqual(view['paper_cards'][0]['analyst_concerns'],
                         [{'concern': 'An alternative explanation.'}])
        self.assertNotIn('opportunities', view['paper_cards'][0])
        self.assertEqual(view['paper_claim_audits'], original['paper_claim_audits'][:1])
        self.assertEqual(view['quote_gaps'], {'g1': original['quote_gaps']['g1']})
        self.assertEqual(view['retrieval_gaps'], original['retrieval_gaps'][:1])
        view['evidence'][0]['quote'] = 'Changed only in returned view.'
        self.assertEqual(context, original)

    def test_mixed_derived_analysis_is_removed_but_neutral_quotes_survive(self):
        context = self.source_context()
        context['paper_cards'][0]['components'].append({'evidence_ids': ['ev_focused']})
        context['paper_claim_audits'][0]['claims'][0]['result_evidence_ids'] = ['ev_focused']
        original = deepcopy(context)
        view = problem_discovery_context(context, ['initial'])
        self.assertEqual(view['paper_cards'], [])
        self.assertEqual(view['paper_claim_audits'], [])
        self.assertEqual(view['evidence'], original['evidence'][:1])
        self.assertEqual(context, original)

    def test_cross_cohort_references_cannot_leave_a_partial_derived_analysis(self):
        context = self.source_context()
        context['paper_claim_audits'][0]['claims'][0]['claim_evidence_ids'].append('ev_design')
        view = problem_discovery_context(context, ['initial'])
        self.assertEqual(view['paper_claim_audits'], [])
        self.assertEqual(len(view['paper_cards']), 1)

    def test_empty_cohort_is_distinct_from_legacy_unspecified_cohort(self):
        context = self.source_context()
        empty = problem_discovery_context(context, [])
        for field in ('papers', 'evidence', 'paper_cards', 'paper_claim_audits'):
            self.assertEqual(empty[field], [])
        self.assertEqual(empty['quote_gaps'], {})
        self.assertEqual(empty['user_notes'], context['user_notes'])
        legacy = problem_discovery_context(context)
        self.assertEqual(legacy['papers'], context['papers'])
        self.assertEqual(legacy['evidence'], context['evidence'])
        self.assertEqual(legacy['quote_gaps'], context['quote_gaps'])
        self.assertNotIn('opportunities', legacy['paper_cards'][0])

    def test_list_quote_gaps_are_supported_without_losing_gap_details(self):
        context = self.source_context()
        context['quote_gaps'] = list(context['quote_gaps'].values())
        view = problem_discovery_context(context, ['initial'])
        self.assertEqual(view['quote_gaps'], context['quote_gaps'][:1])


if __name__ == '__main__':
    unittest.main()
