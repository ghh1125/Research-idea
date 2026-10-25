"""PMLR's official GitHub distributions must not become guessed mirror URLs."""
from copy import deepcopy
import unittest
from unittest.mock import patch

from research_idea.fulltext import candidate_pdf_urls, validate_pdf_url
from research_idea.literature import fetch_full_text, LiteratureError
from research_idea.proceedings import parse_index, pmlr_landing_page, resolve_pmlr_pdf


PAGE = 'https://proceedings.mlr.press/v306/example26a.html'
PDF = 'https://raw.githubusercontent.com/mlresearch/v306/main/assets/example26a/example26a.pdf'
OLD_PDF = 'https://proceedings.mlr.press/v306/example26a/example26a.pdf'


class PmlrRetrievalTests(unittest.TestCase):
    def paper(self):
        return {'id': PAGE, 'url': PAGE, 'title': 'A synthetic paper', 'venue': 'ICML',
                'source': 'official_proceedings', 'pdf_url': OLD_PDF,
                'content_kind': 'abstract', 'text': 'The supplied abstract.', 'conference_year': 2026}

    def test_index_keeps_the_exact_official_download_link(self):
        html = ('<title>International Conference on Machine Learning</title>'
                '<div class="paper"><p class="title">A synthetic paper</p>'
                f'<a href="{PAGE}">abs</a><a href="{PDF}">Download PDF</a></div>')
        records = parse_index(html, 'https://proceedings.mlr.press/v306/', 'ICML', 2026)
        self.assertEqual(records[0]['pdf_url'], PDF)
        self.assertEqual(candidate_pdf_urls(records[0]), [PDF])
        self.assertEqual(records[0]['venue'], 'ICML')

    def test_only_pmlr_github_volume_pdfs_are_accepted(self):
        self.assertEqual(validate_pdf_url(PDF), PDF)
        for url in [PDF.replace('/mlresearch/', '/someone-else/'),
                    PDF.replace('/v306/', '/other-repository/'),
                    PDF.replace('/assets/', '/../../'),
                    PDF.replace('.pdf', '.py'), PDF + '?token=secret']:
            with self.subTest(url=url), self.assertRaises(ValueError):
                validate_pdf_url(url)

    def test_official_citation_metadata_repairs_stale_pdf_without_mutation(self):
        paper = self.paper()
        original = deepcopy(paper)
        html = f'<meta content="{PDF}" name="citation_pdf_url">'.encode()
        with patch('research_idea.literature._request_bytes', return_value=html) as request:
            repaired = resolve_pmlr_pdf(paper, timeout_s=3)
        self.assertEqual(repaired['pdf_url'], PDF)
        self.assertEqual(repaired['pdf_url_source'], PAGE)
        for key in ('id', 'title', 'venue', 'conference_year', 'text', 'content_kind'):
            self.assertEqual(repaired[key], original[key])
        self.assertEqual(paper, original)
        request.assert_called_once_with(PAGE, 3)

    def test_official_anchor_can_supply_pdf_when_citation_meta_is_absent(self):
        with patch('research_idea.literature._request_bytes',
                   return_value=f'<a href="{PDF}">Download PDF</a>'.encode()):
            self.assertEqual(resolve_pmlr_pdf(self.paper())['pdf_url'], PDF)

    def test_index_and_unrelated_pages_are_not_used_as_paper_metadata(self):
        for page in ('https://proceedings.mlr.press/v306/',
                     'https://example.org/v306/example26a.html',
                     PAGE.replace('https:', 'http:'), PAGE + '?next=other'):
            with self.subTest(page=page), patch('research_idea.literature._request_bytes') as request:
                self.assertIsNone(resolve_pmlr_pdf({'url': page}))
                request.assert_not_called()
        self.assertEqual(pmlr_landing_page({'locations': [{'landing_page_url': PAGE}]}), PAGE)
        self.assertIsNone(pmlr_landing_page({'url': 'https://[invalid', 'locations': None}))

    def test_failed_stale_url_recovers_official_pdf_before_searching_preprint(self):
        paper = self.paper()
        failed = dict(paper, full_text_error='Official PDF source returned HTTP 404')
        full = dict(paper, pdf_url=PDF, text='Actual extracted source.', content_kind='full_text')
        with patch('research_idea.fulltext.fetch_full_text', side_effect=[failed, full]) as fetch, \
             patch('research_idea.literature._request_bytes',
                   return_value=f'<meta name="citation_pdf_url" content="{PDF}">'.encode()), \
             patch('research_idea.proceedings.match_preprint') as match, \
             patch('research_idea.literature.time.monotonic', side_effect=[0, 4, 5]):
            result = fetch_full_text(paper, timeout_s=30)
        self.assertEqual(fetch.call_args_list[0].kwargs['timeout_s'], 15)
        self.assertEqual(fetch.call_args_list[1].kwargs['timeout_s'], 12.5)
        self.assertEqual(fetch.call_args_list[1].args[0]['pdf_url'], PDF)
        self.assertEqual(result['content_kind'], 'full_text')
        self.assertEqual(result['primary_full_text_error'], failed['full_text_error'])
        match.assert_not_called()

    def test_existing_working_url_does_not_read_landing_page(self):
        full = dict(self.paper(), content_kind='full_text', text='Already read source.')
        with patch('research_idea.fulltext.fetch_full_text', return_value=full), \
             patch('research_idea.literature._request_bytes') as request:
            self.assertEqual(fetch_full_text(full), full)
        request.assert_not_called()

    def test_missing_or_unreadable_metadata_preserves_primary_failure(self):
        for error in (LiteratureError('HTTP 503'), UnicodeDecodeError('utf-8', b'\xff', 0, 1, 'bad')):
            paper = dict(self.paper(), source='openalex')
            failed = dict(paper, full_text_error='Official PDF source returned HTTP 404')
            with self.subTest(error=error), \
                 patch('research_idea.fulltext.fetch_full_text', return_value=failed), \
                 patch('research_idea.proceedings.match_preprint', return_value=None), \
                 patch('research_idea.literature._request_bytes', side_effect=error):
                self.assertEqual(fetch_full_text(paper), failed)


if __name__ == '__main__':
    unittest.main()
