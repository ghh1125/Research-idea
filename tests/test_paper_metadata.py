"""Conference metadata is enriched before, not after, semantic selection."""
from copy import deepcopy
from email.message import Message
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from research_idea.backend_types import BackendResult
from research_idea.config import DEFAULTS
from research_idea.controller import Controller
from research_idea.literature import LiteratureError, normalize_paper
from research_idea.paper_metadata import _abstract, _fetch_html, enrich_screening_pool, paper_heading
from research_idea.store import Store


def conference(index=1, **fields):
    return normalize_paper({'id': f'paper-{index}', 'title': f'Language model data reuse {index}',
        'source': 'official_proceedings', 'venue': 'ICML', 'year': 2025,
        'conference_year': 2026, 'venue_evidence': 'https://proceedings.mlr.press/v306/',
        'url': f'https://proceedings.mlr.press/v306/example{index}.html',
        'pdf_url': f'https://arxiv.org/pdf/2606.1234{index}', **fields})


class PaperMetadataTests(unittest.TestCase):
    def test_supported_abstract_layouts_and_no_site_description_substitution(self):
        paper = conference()
        for html in ('<div id="abstract">Useful paper abstract.</div>',
                     '<div id="abstractText"><p>Useful paper abstract.</p></div>',
                     '<div class="acl-abstract">Useful paper abstract.</div>',
                     '<h4>Abstract</h4><p>Useful paper abstract.</p>',
                     '<meta name="citation_abstract" content="Useful paper abstract.">'):
            self.assertEqual(_abstract(html, paper), 'Useful paper abstract.')
        self.assertEqual(_abstract('<meta name="description" content="Conference homepage">', paper), '')
        html = '<meta name="citation_title" content="Language model data reuse 1"><meta name="description" content="Actual paper abstract.">'
        self.assertEqual(_abstract(html, paper), 'Actual paper abstract.')

    def test_only_missing_official_single_paper_metadata_is_requested(self):
        rows = [conference(), conference(2, abstract='Already available.'),
                conference(3, source='arxiv', venue=None),
                conference(4, venue='COLM', url='https://colm.cc/Conferences/2026/AcceptedPapers#paper-4'),
                conference(5, url='https://proceedings.mlr.press/v306/example5.pdf')]
        saved = deepcopy(rows)
        with patch('research_idea.paper_metadata._fetch_html', return_value='<div id="abstract">The new abstract.</div>') as fetch:
            enriched, audit = enrich_screening_pool(rows)
        self.assertEqual(fetch.call_count, 1)
        self.assertEqual(rows, saved)
        self.assertEqual(enriched[0]['abstract'], 'The new abstract.')
        self.assertEqual(enriched[0]['abstract_source'], rows[0]['url'])
        for key in ('id', 'url', 'pdf_url', 'venue', 'year', 'conference_year', 'venue_evidence', 'content_kind'):
            self.assertEqual(enriched[0][key], rows[0][key])
        self.assertEqual(audit['attempted'], audit['enriched'])

    def test_ranked_prefix_and_page_cap_are_respected(self):
        with patch('research_idea.paper_metadata._fetch_html', return_value='<div id="abstract">Abstract text.</div>') as fetch:
            enriched, audit = enrich_screening_pool([conference(i) for i in range(20)])
        self.assertEqual(fetch.call_count, 6)
        self.assertEqual(audit['enriched'], 6)
        self.assertTrue(enriched[5]['abstract'])
        self.assertFalse(enriched[6]['abstract'])

    def test_total_time_budget_bounds_all_pages_and_timeouts(self):
        elapsed = [0.0]
        def slow_page(url, timeout_s):
            elapsed[0] += min(2, timeout_s)
            return '<div id="abstract">Abstract text.</div>'
        with patch('research_idea.paper_metadata.time.monotonic', side_effect=lambda: elapsed[0]), \
             patch('research_idea.paper_metadata._fetch_html', side_effect=slow_page) as fetch:
            _, audit = enrich_screening_pool([conference(i) for i in range(20)], timeout_s=5)
        self.assertEqual(elapsed[0], 5)
        self.assertEqual(audit['attempted'], 3)
        self.assertEqual([call.args[1] for call in fetch.call_args_list], [4, 3, 1])

    def test_unavailable_page_leaves_title_only_and_does_not_abort_selection(self):
        with patch('research_idea.paper_metadata._fetch_html', side_effect=LiteratureError('HTTP 403')):
            enriched, audit = enrich_screening_pool([conference()])
        self.assertEqual(enriched[0]['abstract'], '')
        self.assertEqual(audit['pages'][0]['status'], 'unavailable')

    def test_pdf_response_is_rejected_before_body_read(self):
        response = MagicMock()
        response.headers = Message()
        response.headers['Content-Type'] = 'application/pdf'
        response.__enter__.return_value = response
        opener = MagicMock()
        opener.open.return_value = response
        with patch('research_idea.paper_metadata.build_opener', return_value=opener), \
             self.assertRaisesRegex(LiteratureError, 'did not return HTML'):
            _fetch_html(conference()['url'], 4)
        response.read.assert_not_called()
        response.read1.assert_not_called()

    def test_venue_and_edition_are_shown_even_when_fulltext_is_arxiv(self):
        self.assertEqual(paper_heading(conference()), 'Language model data reuse 1 · ICML 2026')
        merged = conference(source='arxiv', venue_evidence=None, conference_url='https://proceedings.mlr.press/v306/',
                            edition_basis='official_proceedings')
        self.assertEqual(paper_heading(merged), 'Language model data reuse 1 · ICML 2026')
        self.assertEqual(paper_heading(conference(source='arxiv', venue=None)),
                         'Language model data reuse 1 · arXiv 预印本')

    def test_enriched_abstract_reaches_screening_and_is_saved_for_resume(self):
        class Backend:
            name = 'test'

            def __init__(self):
                self.payloads = []

            def generate(self, task):
                if task.stage != 'screen_papers':
                    raise AssertionError('Metadata enrichment may not add model stages')
                data = json.loads(task.prompt.split('BEGIN_RESEARCH_DATA\n')[1].split('\nEND_RESEARCH_DATA')[0])
                self.payloads.append(data)
                return BackendResult({'selection_summary': 'Read the relevant conference paper.',
                    'selected': [{'paper_id': data['papers'][0]['id'], 'reason': 'Relevant abstract.',
                                  'reading_question': 'What does the method achieve?', 'route_ids': []}]})

        with tempfile.TemporaryDirectory() as folder:
            store = Store(Path(folder))
            store.set('topic', 'Language model data reuse')
            store.set('search_ledger', {'query-1': {'query': 'language model data reuse', 'metadata': [conference()]}})
            backend = Backend()
            controller = Controller(store, backend, dict(DEFAULTS, fetch_full_text=False, builtin_skills=False))
            with patch('research_idea.paper_metadata._fetch_html', return_value='<div id="abstract">An informative conference abstract.</div>') as fetch:
                controller.select_search_results(['query-1'], 1)
                # Repeat selection after simulating a cleared corpus. The ledger
                # retains the abstract, so no second page request is necessary.
                store.db.execute('DELETE FROM papers')
                store.db.commit()
                controller.select_search_results(['query-1'], 1)
            self.assertEqual(fetch.call_count, 1)
            self.assertEqual(backend.payloads[0]['papers'][0]['abstract'], 'An informative conference abstract.')
            self.assertEqual(backend.payloads[0]['papers'][0]['conference_year'], 2026)
            self.assertEqual(store.rows('papers')[0]['abstract'], 'An informative conference abstract.')
            self.assertEqual(store.get('calls_used'), 1)
            self.assertEqual(store.get('search_ledger')['query-1']['metadata'][0]['abstract_source'], conference()['url'])
            store.close()
