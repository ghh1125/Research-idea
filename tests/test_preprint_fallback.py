"""Conference download failures may use a matched public preprint, within time."""
import unittest
from unittest.mock import patch

from research_idea.literature import fetch_full_text, normalize_paper, LiteratureError
from research_idea.proceedings import match_preprint


class PreprintFallbackTests(unittest.TestCase):
    def setUp(self):
        self.paper = normalize_paper({'id': 'conference', 'title': 'Changing Worlds: Agent Transfer',
            'authors': ['A. Researcher'], 'source': 'official_proceedings', 'venue': 'ACL',
            'year': 2026, 'url': 'https://aclanthology.org/2026.acl-long.1/'})
        self.preprint = normalize_paper({'id': 'arxiv:2601.12345v2',
            'title': 'Changing Worlds — Agent Transfer', 'authors': ['A. Researcher'],
            'publication_date': '2026-01-20', 'url': 'https://arxiv.org/abs/2601.12345v2',
            'pdf_url': 'https://arxiv.org/pdf/2601.12345v2', 'abstract': 'A synthetic abstract.'})

    def test_title_match_preserves_conference_metadata_and_records_preprint_version(self):
        with patch('research_idea.literature.discover', return_value=[self.preprint]):
            matched = match_preprint(self.paper)
        self.assertEqual(matched['id'], self.paper['id'])
        self.assertEqual(matched['venue'], 'ACL')
        self.assertEqual(matched['url'], self.paper['url'])
        self.assertEqual(matched['full_text_origin']['version'], 'v2')
        self.assertEqual(matched['full_text_origin']['url'], self.preprint['url'])
        self.assertIn('arxiv:2601.12345', matched['aliases'])

    def test_similar_titles_or_disjoint_authors_are_not_attached(self):
        for modified in ({'title': 'Changing Worlds: Another Agent Transfer'},
                         {'authors': ['Different Author']}):
            with self.subTest(modified=modified), patch('research_idea.literature.discover', return_value=[dict(self.preprint, **modified)]):
                self.assertIsNone(match_preprint(self.paper))

    def test_failed_primary_download_recovers_within_one_total_deadline(self):
        failed = dict(self.paper, full_text_error='HTTP 403')
        alternate = dict(self.paper, pdf_url=self.preprint['pdf_url'], full_text_origin={'version': 'v2'})
        full = dict(alternate, content_kind='full_text', text='Actual extracted text.')
        with patch('research_idea.fulltext.fetch_full_text', side_effect=[failed, full]) as download, \
             patch('research_idea.proceedings.match_preprint', return_value=alternate) as match, \
             patch('research_idea.literature.time.monotonic', side_effect=[0, 5, 8]):
            result = fetch_full_text(self.paper, timeout_s=30)
        self.assertEqual(download.call_args_list[0].kwargs['timeout_s'], 15)
        self.assertEqual(download.call_args_list[1].kwargs['timeout_s'], 22)
        self.assertEqual(match.call_args.kwargs['timeout_s'], 10)
        self.assertEqual(result['content_kind'], 'full_text')
        self.assertEqual(result['primary_full_text_error'], 'HTTP 403')

    def test_success_and_existing_preprint_do_not_search_again(self):
        for source in (self.paper, dict(self.paper, arxiv_id='2601.12345')):
            full = dict(source, content_kind='full_text', text='Verified text.')
            with patch('research_idea.fulltext.fetch_full_text', return_value=full), \
                 patch('research_idea.proceedings.match_preprint') as match:
                self.assertEqual(fetch_full_text(source), full)
            match.assert_not_called()

    def test_failed_preprint_lookup_preserves_primary_error(self):
        failed = dict(self.paper, full_text_error='HTTP 403')
        with patch('research_idea.fulltext.fetch_full_text', return_value=failed), \
             patch('research_idea.proceedings.match_preprint', side_effect=LiteratureError('HTTP 429')):
            self.assertEqual(fetch_full_text(self.paper), failed)

    def test_openalex_and_other_metadata_sources_use_the_full_title_fallback(self):
        for metadata in ({'source': 'openalex'}, {'source': 'local', 'venue': None}):
            paper = dict(self.paper, **metadata)
            failed = dict(paper, full_text_error='HTTP 404')
            full = dict(paper, content_kind='full_text', text='Actual public preprint text.')
            with self.subTest(metadata=metadata), \
                 patch('research_idea.fulltext.fetch_full_text', side_effect=[failed, full]), \
                 patch('research_idea.literature.discover', return_value=[self.preprint]) as search:
                result = fetch_full_text(paper)
            self.assertEqual(search.call_args.args[0], 'ti:"Changing Worlds: Agent Transfer"')
            self.assertEqual(search.call_args.kwargs['source'], 'arxiv')
            self.assertEqual(result['id'], paper['id'])
            self.assertEqual(result.get('venue'), paper.get('venue'))
            self.assertEqual(result['content_kind'], 'full_text')

    def test_empty_title_lookup_preserves_primary_error(self):
        failed = dict(self.paper, full_text_error='Official PDF returned HTTP 404')
        with patch('research_idea.fulltext.fetch_full_text', return_value=failed) as fetch, \
             patch('research_idea.literature.discover', return_value=[]):
            self.assertEqual(fetch_full_text(self.paper), failed)
        fetch.assert_called_once()

    def test_similar_title_is_not_downloaded_after_primary_failure(self):
        failed = dict(self.paper, full_text_error='Official PDF returned HTTP 404')
        other = dict(self.preprint, title='Changing Worlds: Unrelated Study')
        with patch('research_idea.fulltext.fetch_full_text', return_value=failed) as fetch, \
             patch('research_idea.literature.discover', return_value=[other]):
            self.assertEqual(fetch_full_text(self.paper), failed)
        fetch.assert_called_once()

    def test_matched_preprint_download_failure_preserves_primary_error(self):
        failed = dict(self.paper, full_text_error='Official PDF returned HTTP 404')
        unavailable = dict(self.preprint, full_text_error='Preprint download timed out')
        with patch('research_idea.fulltext.fetch_full_text', side_effect=[failed, unavailable]), \
             patch('research_idea.literature.discover', return_value=[self.preprint]):
            self.assertEqual(fetch_full_text(self.paper), failed)

    def test_arxiv_source_url_does_not_trigger_identical_title_lookup(self):
        paper = {'title': 'A preprint', 'url': 'https://arxiv.org/abs/2601.12345'}
        failed = dict(paper, full_text_error='arXiv is temporarily unavailable')
        with patch('research_idea.fulltext.fetch_full_text', return_value=failed), \
             patch('research_idea.proceedings.match_preprint') as match:
            self.assertEqual(fetch_full_text(paper), failed)
        match.assert_not_called()


if __name__ == '__main__':
    unittest.main()
