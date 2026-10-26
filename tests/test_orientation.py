"""Early discussion reads real source spans without a full-paper audit pipeline."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from research_idea.backend_types import BackendResult
from research_idea.config import DEFAULTS
from research_idea.controller import Controller, make_evidence
from research_idea.orientation import orientation_excerpt
from research_idea.paper_reading import inventory
from research_idea.store import Store


def paper(pid='p1'):
    return {'id': pid, 'title': 'A general research direction', 'content_kind': 'full_text',
            'text': 'Abstract\nA short overview.\n1 I NTRODUCTION\n'
                    + 'A broad research goal motivates several established approaches.\n' * 20
                    + '2 M ETHODOLOGY\n' + 'Implementation detail.\n' * 400
                    + '3 Related Work\n' + 'Several families of approaches make different progress.\n' * 20
                    + '4 Conclusion\nAn important goal remains open under changing conditions.\n'
                    + 'References\nA bibliographic entry.\n'}


class OrientationTests(unittest.TestCase):
    def test_reads_background_related_work_and_conclusion_with_original_offsets(self):
        source = paper()
        view = orientation_excerpt(source, 900)
        self.assertLessEqual(len(view['excerpt']), 900)
        for phrase in ('A broad research goal', 'Several families', 'An important goal'):
            self.assertIn(phrase, view['excerpt'])
        self.assertNotIn('Implementation detail', view['excerpt'])
        self.assertNotIn('bibliographic entry', view['excerpt'])
        for span in view['spans']:
            self.assertIn(source['text'][span['start']:span['end']], view['excerpt'])
        quote = 'Several families of approaches make different progress.'
        evidence = make_evidence(source, [{'statement': 'An overview of approaches.', 'quote': quote,
            'kind': 'author_claim', 'conditions': 'The source overview.', 'source_section': 'Related Work'}],
            view['excerpt'], source_spans=view['spans'])
        self.assertEqual(source['text'][evidence[0]['start']:evidence[0]['end']], quote)

    def test_pdf_noise_is_not_a_section_and_small_caps_still_work(self):
        source = paper()
        source['text'] += '\n2020). However the result varies.\nmodel to capture dependencies\n1.2 9.4\nx = y + z\n'
        sections = inventory(source)['sections']
        titles = [s['title'] for s in sections]
        self.assertFalse(any(t.startswith(('2020)', 'model to', '1.2 9.4', 'x =')) for t in titles))
        self.assertIn('method', [s['family'] for s in sections])
        self.assertEqual(sum(s['family'] == 'references' for s in sections), 1)

    def test_one_read_per_source_cached_and_available_to_ideation(self):
        class Reader:
            name = 'test-reader'
            calls = []

            def generate(self, task):
                data = json.loads(task.prompt.split('BEGIN_RESEARCH_DATA\n')[1].split('\nEND_RESEARCH_DATA')[0])
                self.calls.append((task.stage, data['purpose']))
                return BackendResult({'observations': [{'statement': 'The source introduces a broad need.',
                    'quote': 'A broad research goal motivates several established approaches.',
                    'kind': 'author_claim', 'conditions': 'Introduction only.', 'source_section': 'Introduction'}]})

        with tempfile.TemporaryDirectory() as temp:
            store = Store(Path(temp))
            self.addCleanup(store.close)
            store.set('topic', 'A broad research direction')
            for pid in ('p1', 'p2'):
                store.put('papers', paper(pid))
            backend = Reader()
            controller = Controller(store, backend, dict(DEFAULTS, backend='codex', auto_search=False,
                builtin_skills=False, source_chars=900, max_seconds=60))
            controller.orient_papers(['p1', 'p2'])
            self.assertEqual(backend.calls, [('inspect_source', 'background_orientation')] * 2)
            self.assertFalse(store.get('paper_cards'))
            self.assertFalse(store.get('paper_claim_audits'))
            self.assertEqual(len(controller.ideation_context()['evidence']), 2)
            controller.orient_papers(['p1', 'p2'])
            self.assertEqual(len(backend.calls), 2)
            self.assertEqual(len(store.rows('evidence')), 2)

    def test_explicit_problem_source_is_not_blocked_by_initial_paper_cap(self):
        with tempfile.TemporaryDirectory() as temp:
            store = Store(Path(temp))
            self.addCleanup(store.close)
            store.set('topic', 'A broad need')
            for pid in ('initial', 'neighbor'):
                store.put('papers', {'id': pid, 'title': pid, 'abstract': 'A source abstract', 'content_kind': 'abstract'})
            controller = Controller(store, object(), dict(DEFAULTS, backend='codex', auto_search=True,
                                                          builtin_skills=False, max_papers=1))
            with patch.object(controller, 'reading_papers', return_value=[]), \
                 patch('research_idea.literature.fetch_full_text', return_value=paper('neighbor')) as fetch:
                controller.retrieve_full_texts(['neighbor'])
            self.assertEqual(fetch.call_count, 1)
            self.assertEqual(fetch.call_args.args[0]['id'], 'neighbor')


if __name__ == '__main__':
    unittest.main()
