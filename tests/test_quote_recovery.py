"""Realistic PDF typography, semantic rejection, and bounded partial recovery."""
import copy
from pathlib import Path
import tempfile
import unittest

from research_idea.backend_types import BackendResult
from research_idea.config import DEFAULTS
from research_idea.controller import Controller, locate_quote, make_evidence
from research_idea.evidence_matching import current_quote_gaps
from research_idea.store import Store


def observation(quote):
    return {'quote': quote, 'statement': 'A narrow observation.', 'kind': 'author_claim',
            'conditions': 'Only the supplied setting.', 'source_section': 'Methods'}


class QuoteRecoveryTests(unittest.TestCase):
    def test_typography_aligns_to_untouched_source(self):
        cases = [
            ('The efﬁcient multi-\nagent system uses “local” memory.', 'The efficient multiagent system uses "local" memory.'),
            ('The high-\nlevel policy uses local observations.', 'The high-level policy uses local observations.'),
            ('The classi\ufb01cation result is not significant.', 'The classification result is not significant.'),
            ('The soft\u00adhyphen changes only the rendering.', 'The softhyphen changes only the rendering.'),
        ]
        for source, quote in cases:
            with self.subTest(source=source):
                text = 'HEADER\n' + source + '\nFOOTER'
                start, end = locate_quote(text, quote)
                self.assertEqual(text[start:end], source)
                evidence = make_evidence({'id': 'p', 'text': text, 'content_kind': 'full_text'}, [observation(quote)], source)[0]
                self.assertEqual(evidence['quote'], source)
                self.assertEqual(evidence['start'], start)
                self.assertEqual(evidence['submitted_quote'], quote)

    def test_semantic_changes_stitching_and_outside_excerpt_are_rejected(self):
        source = 'The measured accuracy does not improve by 15 percent. A separate paragraph discusses cost.'
        for quote in ['The measured accuracy does improve by 15 percent.',
                      'The measured accuracy does not improve by 50 percent.',
                      'The measured accuracy ... discusses cost.',
                      'The measured accuracy discusses cost.']:
            with self.subTest(quote=quote), self.assertRaises(ValueError):
                locate_quote(source, quote)
        with self.assertRaises(ValueError):
            make_evidence({'id': 'p', 'text': source}, [observation(source[:53])], 'An unrelated supplied section.')

    def test_repair_is_informed_then_invalid_observation_is_isolated_and_cached(self):
        with tempfile.TemporaryDirectory() as directory:
            store = Store(Path(directory))
            quote = 'The policy observes only locally available information.'
            paper = {'id': 'p', 'title': 'Source', 'text': quote, 'content_kind': 'full_text'}
            store.put('papers', paper)
            good, bad = observation(quote), observation('The policy observes all unavailable global information.')
            class Backend:
                name = 'fixture'
                calls = []
                def generate(self, task):
                    self.calls.append(task)
                    return BackendResult(copy.deepcopy({'observations': [good, bad]}))
            backend = Backend()
            controller = Controller(store, backend, dict(DEFAULTS, builtin_skills=False))
            payload = {'paper_id': 'p', 'excerpt': quote}
            checker = lambda result: make_evidence(paper, result['observations'], quote)
            result = controller.task('read_section', payload, checker)
            self.assertEqual(result['observations'], [good])
            self.assertEqual(len(backend.calls), 2)
            self.assertIn('previous_output', backend.calls[1].prompt)
            self.assertIn('nearby_source', backend.calls[1].prompt)
            self.assertEqual(len(current_quote_gaps(store)), 1)
            self.assertEqual(len(next(iter(current_quote_gaps(store).values()))['rejected']), 1)
            self.assertEqual(controller.task('read_section', payload, checker), result)
            self.assertEqual(len(backend.calls), 2)
            store.put('papers', dict(paper, text='Source has changed.'))
            self.assertEqual(current_quote_gaps(store), {})
            store.close()

    def test_real_builtins_reach_stage_prompt_with_operational_evidence_rules(self):
        with tempfile.TemporaryDirectory() as directory:
            store = Store(Path(directory))
            class Backend:
                name = 'fixture'
                calls = []
                def generate(self, task):
                    self.calls.append(task)
                    return BackendResult({'observations': []})
            backend = Backend()
            controller = Controller(store, backend, dict(DEFAULTS))
            controller.task('read_section', {'paper_id': 'p', 'excerpt': 'No relevant evidence.'})
            prompt = backend.calls[0].prompt
            self.assertIn('research-idea-read-evidence', prompt)
            self.assertIn('research-idea-analyze-paper', prompt)
            self.assertIn('Preserve negation, numbers and qualifications', prompt)
            self.assertIn('proposed mechanism', prompt)
            store.close()
