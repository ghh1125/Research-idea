"""Conference editions and preprint recency are independent search policies."""
from datetime import datetime, timezone
import time
import unittest
from unittest.mock import patch
from urllib.parse import parse_qs, urlparse

from research_idea import literature as lit
from research_idea.proceedings import discover_proceedings
from research_idea.search_scope import normalize_scope, exclusion_reason
from research_idea.selection import rank_metadata


def acl_index(year, title='Agent environments', month='July'):
    return (f'<title>{year}.acl-long</title><dl><dt>Month:</dt><dd>{month}</dd></dl>'
            f'<a href="/{year}.acl-long.1/">{title}</a>').encode()


def scope(**changes):
    return normalize_scope(**({'since': '2026-04-24', 'until': '2026-10-24',
                              'cs_only': True, 'conference_policy': 'latest'} | changes))


class ConferenceEditionTests(unittest.TestCase):
    def official_search(self, fetch, query='agents', settings=None):
        coverage = {'gaps': []}
        with patch.object(lit, '_request_bytes', side_effect=fetch) as request:
            papers = discover_proceedings(query, ['ACL'], 10, time.monotonic() + 20,
                                          settings or scope(), coverage)
        return papers, coverage, request

    def test_latest_public_edition_survives_preprint_window_and_stops_at_that_edition(self):
        def fetch(url, *_):
            if '2026.' in url:
                raise lit.LiteratureError('HTTP 404')
            return acl_index(2025)
        papers, coverage, request = self.official_search(fetch)
        self.assertEqual(len(papers), 1)
        self.assertEqual(papers[0]['conference_year'], 2025)
        self.assertEqual(papers[0]['publication_period'], '2025-07')
        self.assertEqual(coverage['conference_editions']['ACL']['year'], 2025)
        self.assertEqual(len(request.call_args_list), 2)

    def test_no_topical_hit_in_current_edition_does_not_select_previous_edition(self):
        papers, coverage, request = self.official_search(lambda *args: acl_index(2026, 'Protein structures'))
        self.assertEqual(papers, [])
        self.assertEqual(coverage['conference_editions']['ACL']['year'], 2026)
        request.assert_called_once()

    def test_http_failure_is_not_reported_as_proof_newer_edition_is_unpublished(self):
        def fetch(url, *_):
            if '2026.' in url:
                raise lit.LiteratureError('HTTP 403')
            return acl_index(2025)
        papers, coverage, _ = self.official_search(fetch)
        self.assertEqual(papers[0]['conference_year'], 2025)
        self.assertEqual(coverage['conference_editions']['ACL']['newer_unresolved'][0]['year'], 2026)

    def test_fixed_window_remains_strict_and_until_is_still_enforced(self):
        current = scope()
        papers, _, _ = self.official_search(lambda *args: acl_index(2026, month='January'))
        self.assertEqual(len(papers), 1)
        self.assertIsNotNone(exclusion_reason(papers[0], dict(current, conference_policy='window'),
                                             'official_proceedings', verified_venue=True))
        future = dict(papers[0], publication_period='2026-11')
        self.assertIsNotNone(exclusion_reason(future, current, 'official_proceedings', verified_venue=True))

    def test_latest_accepted_colm_is_detected_without_query_matches(self):
        coverage = {'gaps': [], 'filters': scope()}
        note = {'id': 'knownid', 'content': {'title': {'value': 'Protein structures'},
                'venueid': {'value': 'colmweb.org/COLM/2026/Conference'}}}
        with patch.object(lit, '_json_results', return_value=([note], {'count': 1})) as fetch:
            papers = lit._discover_colm('agents', 10, time.monotonic() + 10, coverage)
        self.assertEqual(papers, [])
        fetch.assert_called_once()
        self.assertEqual(coverage['conference_editions']['COLM']['year'], 2026)

    def test_colm_edition_published_after_cutoff_does_not_hide_previous_edition(self):
        coverage = {'gaps': [], 'filters': scope(since='2025-12-01', until='2026-02-01')}
        def fetch(url, *args, **kwargs):
            current = '2026' in parse_qs(urlparse(url).query)['content.venueid'][0]
            year, month = (2026, 8) if current else (2025, 10)
            note = {'id': str(year), 'pdate': datetime(year, month, 1, tzinfo=timezone.utc).timestamp() * 1000,
                'content': {'title': {'value': 'Agent environments'},
                    'venueid': {'value': f'colmweb.org/COLM/{year}/Conference'}}}
            return [note], {'count': 1}
        with patch.object(lit, '_json_results', side_effect=fetch):
            papers = lit._discover_colm('agent', 10, time.monotonic() + 10, coverage)
        self.assertEqual([p['conference_year'] for p in papers], [2025])
        self.assertEqual(coverage['conference_editions']['COLM']['year'], 2025)

    def test_dated_conference_source_overrides_original_preprint_year_and_excludes_other_editions(self):
        calls = []
        def sources(venues, deadline, headers, coverage):
            coverage['openalex_sources'] = {'ICCV': [
                {'id': f'S{year}', 'display_name': f'{year} International Conference on Computer Vision'}
                for year in (2025, 2026)]}
            return {'S2025': 'ICCV', 'S2026': 'ICCV'}
        def fetch(url, *args, **kwargs):
            params = parse_qs(urlparse(url).query)
            calls.append(params)
            if 'group_by' in params:
                self.assertEqual(params['group_by'], ['primary_location.source.id'])
                return [{'key': 'https://openalex.org/S2026', 'count': 1000}, {'key': 'S2025', 'count': 1000}], {}
            return [{'id': f'https://openalex.org/W{year}', 'title': 'Agent environments',
                'publication_year': 2025, 'publication_date': '2025-10-01',
                'primary_location': {'source': {'id': f'https://openalex.org/S{year}',
                    'display_name': f'{year} International Conference on Computer Vision'}}} for year in (2025, 2026)], {}
        with patch.object(lit, '_openalex_sources', side_effect=sources), patch.object(lit, '_json_results', side_effect=fetch):
            papers = lit.discover('agents', source='openalex', venues=['ICCV'], **scope())
        self.assertEqual([p['conference_year'] for p in papers], [2026])
        self.assertEqual(papers[0]['year'], 2025)
        self.assertEqual(papers[0]['edition_basis'], 'publication_source_edition')
        self.assertNotIn('publication_year:', calls[1]['filter'][0])
        self.assertNotIn('S2025', calls[1]['filter'][0])

    def test_optional_continuous_series_failure_keeps_known_dated_edition(self):
        coverage = {'gaps': [], 'openalex_sources': {'ICCV': [
            {'id': 'S2025', 'display_name': '2025 International Conference on Computer Vision'},
            {'id': 'S1', 'display_name': 'International Conference on Computer Vision'}]}}
        with patch.object(lit, '_json_results', side_effect=[
                ([{'key': 'S2025', 'count': 100}], {}), lit.LiteratureError('HTTP 429')]):
            year = lit._latest_openalex_year('ICCV', ['S2025', 'S1'], scope(),
                                             time.monotonic() + 10, {}, coverage)
        self.assertEqual(year, 2025)
        self.assertEqual(coverage['conference_editions']['ICCV']['source_ids'], ['S2025'])
        self.assertTrue(any('HTTP 429' in gap for gap in coverage['gaps']))

    def test_openalex_resolves_edition_before_search_and_keeps_biennial_previous_year(self):
        calls = []
        def query(url, *args, **kwargs):
            params = parse_qs(urlparse(url).query)
            calls.append(params)
            if 'group_by' in params:
                self.assertNotIn('search', params)
                return [{'key': '2025', 'count': 2000}, {'key': '2027', 'count': 100}], {}
            return [{'id': 'https://openalex.org/W1', 'title': 'Agent environments',
                     'publication_year': 2025, 'publication_date': '2025-10-01',
                     'primary_location': {'source': {'id': 'https://openalex.org/S1',
                         'display_name': 'International Conference on Computer Vision'}}}], {}
        with patch.object(lit, '_openalex_sources', return_value={'S1': 'ICCV'}), \
             patch.object(lit, '_json_results', side_effect=query):
            found = lit.discover('agents', source='openalex', venues=['ICCV'], **scope())
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0]['conference_year'], 2025)
        self.assertIn('publication_year:2025', calls[1]['filter'][0])
        self.assertNotIn('from_publication_date', calls[1]['filter'][0])
        self.assertIn('to_publication_date:2026-10-24', calls[1]['filter'][0])

    def test_official_current_edition_with_no_topic_results_is_not_replaced_by_api_older_hit(self):
        with patch.object(lit, '_request_bytes', return_value=acl_index(2026, 'Protein structures')), \
             patch.object(lit, '_openalex_sources') as sources:
            found = lit.discover('agents', source='openalex', venues=['ACL'], **scope())
        self.assertEqual(found, [])
        sources.assert_not_called()
        self.assertEqual(found.coverage['conference_editions']['ACL']['year'], 2026)

    def test_arxiv_does_not_inherit_conference_lower_date_exemption(self):
        feed = b'<feed xmlns="http://www.w3.org/2005/Atom"><entry><id>https://arxiv.org/abs/2501.00001</id><title>Agent environments</title><published>2025-01-01T00:00:00Z</published><category term="cs.AI"/></entry></feed>'
        with patch.object(lit, '_request_bytes', return_value=feed), patch.object(lit, '_last_arxiv_request', 0):
            found = lit.discover('agents', source='arxiv', **scope())
        self.assertEqual(found, [])
        self.assertEqual(found.coverage['excluded'][0]['reason'], 'publication date before requested window')

    def test_dedup_preserves_conference_edition_when_preprint_has_richer_content(self):
        official = {'id': 'official', 'aliases': ['arxiv:2501.00001'], 'title': 'Agent environments',
            'year': 2026, 'conference_year': 2026, 'edition_basis': 'official_proceedings',
            'source': 'official_proceedings', 'venue': 'ICML', 'venue_evidence': 'https://proceedings.mlr.press/v306/',
            'url': 'https://proceedings.mlr.press/v306/paper.html'}
        preprint = {'id': 'arxiv:2501.00001', 'title': 'Agent environments', 'year': 2025,
            'publication_date': '2025-01-01', 'source': 'arxiv', 'version': 'v3', 'abstract': 'More detail',
            'url': 'https://arxiv.org/abs/2501.00001'}
        merged = lit.deduplicate([official, preprint])[0]
        self.assertEqual(merged['venue'], 'ICML')
        self.assertEqual(merged['conference_year'], 2026)
        self.assertEqual(merged['conference_url'], official['url'])
        self.assertEqual(merged['publication_date'], '2025-01-01')
        self.assertEqual(rank_metadata([merged], ['agents'])[0]['selection']['date'], '2026-00-00')

    def test_newest_relevant_edition_precedes_older_edition_despite_preprint_dates(self):
        rows = [
            {'id': 'new-edition', 'title': 'Agent environments', 'conference_year': 2026,
             'publication_date': '2024-01-01', 'venue': 'ICML'},
            {'id': 'old-edition', 'title': 'Agent environments', 'conference_year': 2025,
             'publication_date': '2025-12-01', 'venue': 'NAACL'},
            {'id': 'unrelated', 'title': 'Protein structures', 'conference_year': 2026,
             'publication_date': '2026-10-01', 'venue': 'ICML'}]
        self.assertEqual([p['id'] for p in rank_metadata(rows, ['agent environments'])],
                         ['new-edition', 'old-edition', 'unrelated'])
