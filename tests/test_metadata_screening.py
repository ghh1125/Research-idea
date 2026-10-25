"""Metadata screening steers reading without inventing citations or overlap."""
import json
from pathlib import Path
import tempfile
import unittest

from research_idea.backend_types import BackendResult
from research_idea.config import DEFAULTS
from research_idea.controller import Controller, OutputValidationError
from research_idea.literature import normalize_paper
from research_idea.store import Store


class SelectionBackend:
    name = 'screening-fixture'

    def __init__(self, ids):
        self.ids, self.calls = ids, []

    def generate(self, task):
        self.calls.append(task)
        if task.stage != 'screen_papers':
            raise AssertionError(task.stage)
        return BackendResult({'selection_summary': 'Prioritize changing task environments.',
            'selected': [{'paper_id': pid, 'reason': 'Studies the environment intervention.',
                          'reading_question': 'Does the environment change rules or just vocabulary?', 'reading_role': 'method', 'route_ids': []}
                         for pid in self.ids]})


class MetadataScreeningTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.temp.name))
        self.store.set('topic', 'How should environments change to help agents adapt?')
        self.records = [
            normalize_paper({'id': 'vocabulary', 'title': 'Agent vocabulary adaptation',
                'abstract': 'Compress the vocabulary to reduce inference latency.', 'publication_date': '2026-10-20'}),
            normalize_paper({'id': 'worlds', 'title': 'Procedural worlds for transfer',
                'abstract': 'Generate new task rules and assess adaptation to unseen environments.',
                'publication_date': '2026-08-01'}),
        ]
        self.store.set('search_ledger', {'s': {'query': 'agent adaptation', 'purpose': 'strategy',
            'status': 'completed', 'metadata': self.records}})
        self.cfg = dict(DEFAULTS, fetch_full_text=False, builtin_skills=False, max_papers=2)

    def tearDown(self):
        self.store.close()
        self.temp.cleanup()

    def select(self, backend, **settings):
        controller = Controller(self.store, backend, dict(self.cfg, **settings))
        controller.select_search_results(['s'], 1)
        return controller

    def test_semantic_choice_can_replace_a_newer_lexical_match(self):
        backend = SelectionBackend(['worlds'])
        self.select(backend)
        paper = self.store.rows('papers')[0]
        self.assertEqual(paper['id'], 'worlds')
        self.assertIn('environment', paper['selection']['reason'])
        self.assertIn('vocabulary', paper['selection']['reading_question'])
        self.assertEqual(self.store.rows('evidence'), [])
        self.assertNotIn('novelty_status', paper)
        audit = self.store.get('paper_selections')[-1]
        self.assertEqual(audit['selected_ids'], ['worlds'])
        self.assertEqual(len(audit['ranking']), 2)

    def test_no_relevant_choice_does_not_fill_quota_with_off_topic_work(self):
        self.select(SelectionBackend([]))
        self.assertEqual(self.store.rows('papers'), [])
        self.assertEqual(self.store.get('paper_selections')[-1]['selected_ids'], [])

    def test_invented_duplicate_or_over_quota_ids_are_repaired_once_then_rejected(self):
        for ids in [['fabricated'], ['worlds', 'worlds'], ['worlds', 'vocabulary']]:
            with self.subTest(ids=ids):
                backend = SelectionBackend(ids)
                with self.assertRaises(OutputValidationError):
                    self.select(backend)
                self.assertEqual(len(backend.calls), 2)
                self.assertEqual(self.store.rows('papers'), [])

    def test_saved_selection_survives_interruption_before_paper_insertion(self):
        backend = SelectionBackend(['worlds'])
        self.select(backend)
        with self.store.db:
            self.store.db.execute('DELETE FROM papers')
        resumed = SelectionBackend([])
        self.select(resumed, max_calls=1)
        self.assertEqual(resumed.calls, [])
        self.assertEqual(self.store.rows('papers')[0]['id'], 'worlds')

    def test_model_context_is_bounded_and_omits_full_text(self):
        records = [normalize_paper({'id': f'p{n}', 'title': 'Agent environment adaptation',
            'abstract': 'word ' * 1000, 'text': 'Full text must stay out of screening.'}) for n in range(65)]
        self.store.set('search_ledger', {'s': {'query': 'agent adaptation', 'metadata': records}})
        backend = SelectionBackend([])
        self.select(backend)
        data = json.loads(backend.calls[0].prompt.split('BEGIN_RESEARCH_DATA\n')[1].split('\nEND_RESEARCH_DATA')[0])
        self.assertEqual(len(data['papers']), 40)
        self.assertTrue(all(len(p['abstract']) <= 1800 and 'text' not in p for p in data['papers']))
        self.assertEqual(data['max_papers'], 1)


if __name__ == '__main__':
    unittest.main()
