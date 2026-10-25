import copy
import json
from datetime import date
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from research_idea.selection import discovery_pool, rank_metadata
from research_idea.retrieval_transport import SESSION, request_with_policy, retry_seconds
from research_idea.literature import LiteratureError, deduplicate, normalize_paper
from research_idea.proceedings import parse_index, enrich_selected
from research_idea.search_scope import config_scope, months_before, exclusion_reason, AI_VENUES
from research_idea.config import _validated_settings
from research_idea.venues import normalize_venues, supported_venues


class SelectionTests(unittest.TestCase):
    def paper(self, name, title, published):
        return normalize_paper(dict(id=name, title=title, publication_date=published))

    def test_relevance_precedes_newness_and_same_relevance_prefers_recent(self):
        records = [self.paper('new-off-topic', 'A protein discovery', '2026-10-20'),
                   self.paper('old', 'Spatial multi agent communication', '2026-01-01'),
                   self.paper('new', 'Spatial multi agent routing', '2026-09-01')]
        ranked = rank_metadata(records, ['spatial multi agent'])
        self.assertEqual([p['id'] for p in ranked], ['new', 'old', 'new-off-topic'])
        self.assertEqual(ranked[0]['selection']['matched_query'], 'spatial multi agent')

    def test_retrieved_titles_never_mark_overlap_or_novelty(self):
        rows = rank_metadata([self.paper('p', 'Existing method', '')], ['existing method'])
        self.assertNotIn('novelty', rows[0]['selection'])
        self.assertIn('metadata only', rows[0]['selection']['basis'])

    def test_discovery_pool_keeps_other_routes_when_one_has_many_new_matches(self):
        routes = [{'id': name, 'question': name, 'why_relevant': 'A separate line of inquiry.'}
                  for name in ('common', 'alternative', 'boundary')]
        queries = [{'query': name + ' model', 'route_ids': [name]} for name in ('common', 'alternative', 'boundary')]
        entries = [{'query': query['query'], 'metadata': [
            self.paper(f'{index}-{number}', query['query'], '2026-10-20' if index == 0 else '2026-01-01')
            for number in range(50 if index == 0 else 2)]}
            for index, query in enumerate(queries)]
        records = deduplicate([paper for entry in entries for paper in entry['metadata']])
        before = copy.deepcopy((records, entries))
        pool = discovery_pool(records, entries, {'research_routes': routes, 'queries': queries})
        self.assertEqual(len(pool), 40)
        self.assertEqual([paper['discovery_provenance'][0]['route_ids'] for paper in pool[:3]],
                         [['common'], ['alternative'], ['boundary']])
        self.assertEqual(sum(p['id'].startswith('1-') for p in pool), 2)
        self.assertEqual(sum(p['id'].startswith('2-') for p in pool), 2)
        self.assertTrue(all('relevance' in paper['selection'] for paper in pool))
        self.assertEqual((records, entries), before)

    def test_discovery_provenance_joins_aliases_and_keeps_all_actual_queries(self):
        first = dict(self.paper('preprint', 'Shared method', '2026-01-01'), aliases=['preprint', 'shared-doi'])
        second = dict(self.paper('conference', 'Shared method', '2026-09-01'), aliases=['conference', 'shared-doi'])
        records = deduplicate([first, second])
        entries = [{'query': 'first question', 'metadata': [first]},
                   {'query': 'second question', 'metadata': [second]}]
        plan = {'research_routes': [{'id': 'a'}, {'id': 'b'}],
                'queries': [{'query': 'first question', 'route_ids': ['a']},
                            {'query': 'second question', 'route_ids': ['b']}]}
        pool = discovery_pool(records, entries, plan)
        self.assertEqual(len(pool), 1)
        self.assertEqual(pool[0]['discovery_provenance'], [
            {'query': 'first question', 'route_ids': ['a']},
            {'query': 'second question', 'route_ids': ['b']}])

    def test_lexical_match_does_not_invent_query_or_route_provenance(self):
        paper = self.paper('p', 'beta retrieval', '2026-10-01')
        entries = [{'query': 'alpha inquiry', 'metadata': [paper]},
                   {'query': 'beta retrieval', 'metadata': []}]
        plan = {'research_routes': [{'id': 'a'}, {'id': 'b'}],
                'queries': [{'query': 'alpha inquiry', 'route_ids': ['a']},
                            {'query': 'beta retrieval', 'route_ids': ['b']}]}
        self.assertEqual(rank_metadata([paper], [entry['query'] for entry in entries])[0]['selection']['matched_query'],
                         'beta retrieval')
        pool = discovery_pool([paper], entries, plan)
        self.assertEqual(pool[0]['discovery_provenance'], [{'query': 'alpha inquiry', 'route_ids': ['a']}])

    def test_discovery_pool_handles_empty_routes_legacy_plans_and_unmapped_records(self):
        routed = self.paper('routed', 'alpha inquiry', '2026-01-01')
        unmapped = self.paper('unmapped', 'alpha inquiry', '2026-10-01')
        entries = [{'query': 'alpha inquiry', 'metadata': [routed]}]
        plan = {'research_routes': [{'id': 'empty'}, {'id': 'a'}],
                'queries': [{'query': 'no results', 'route_ids': ['empty']},
                            {'query': 'alpha inquiry', 'route_ids': ['a']}]}
        pool = discovery_pool([routed, unmapped], entries, plan, limit=2)
        self.assertEqual([p['id'] for p in pool], ['routed', 'unmapped'])
        self.assertEqual(pool[1]['discovery_provenance'], [])
        legacy = discovery_pool([routed, unmapped], entries, {'queries': [{'query': 'alpha inquiry'}]})
        self.assertEqual([p['id'] for p in legacy], ['unmapped', 'routed'])
        self.assertEqual(discovery_pool([routed], entries, plan, limit=0), [])

    def test_windows_follow_calendar_and_handle_month_ends(self):
        self.assertEqual(months_before(date(2024, 8, 31), 6), date(2024, 2, 29))
        with patch('research_idea.search_scope.date') as day:
            day.today.return_value = date(2026, 10, 23)
            # Month arithmetic uses the same date constructor.
            day.side_effect = date
            day.fromisoformat.side_effect = date.fromisoformat
            cfg = _validated_settings({})
            self.assertEqual(config_scope(cfg)['since'], '2025-10-23')
            self.assertEqual(config_scope(cfg, 'novelty')['since'], '2026-04-23')
            day.today.return_value = date(2026, 11, 23)
            self.assertEqual(config_scope(cfg)['since'], '2025-11-23')

    def test_legacy_fixed_dates_and_invalid_month_limits(self):
        cfg = _validated_settings({'search_since': '2025-01-01', 'search_until': '2026-01-01'})
        self.assertEqual(cfg['search_date_mode'], 'fixed')
        self.assertEqual(config_scope(cfg)['since'], '2025-01-01')
        for invalid in ({'novelty_months': 15}, {'strategy_months': 0}, {'strategy_months': True}, {'search_results_per_query': 101}):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                _validated_settings(invalid)

    def test_current_catalogs_and_user_selected_venues(self):
        rows = {row['code']: row for row in supported_venues()}
        self.assertEqual(rows['ICLR']['ccf_2026_ai_grade'], 'A')
        self.assertEqual(rows['IJCAI']['ccf_2026_ai_grade'], 'B')
        self.assertEqual(rows['ICLR']['core_2026_grade'], 'A*')
        self.assertEqual(rows['EMNLP']['tsinghua_2019_ai_grade'], 'A')
        self.assertIsNone(rows['COLM']['ccf_2026_ai_grade'])
        self.assertEqual(len(normalize_venues(['core-astar-2026'])), 62)
        self.assertEqual(AI_VENUES, ['NeurIPS', 'ICML', 'ICLR', 'ACL', 'EMNLP', 'NAACL', 'COLM', 'AAAI', 'IJCAI', 'AAMAS',
                                    'KDD', 'ICDM', 'ICDE', 'SIGMOD', 'VLDB', 'ACMMM', 'CVPR', 'ICCV', 'SIGIR', 'WWW'])
        self.assertEqual(normalize_venues(['ai-recommended', 'COLM']), AI_VENUES)


class TransportTests(unittest.TestCase):
    def failure(self, status, delay=1):
        exc = LiteratureError(f'HTTP {status}')
        exc.status, exc.retry_after = status, delay
        return exc

    def state(self, cache=None):
        return {'cache': cache, 'cooldowns': {}, 'cache_hits': 0, 'requests': 0, 'retries': 0, 'skipped': 0}

    def test_short_429_backoff_recovers(self):
        fetch = Mock(side_effect=[self.failure(429), b'ok'])
        with patch('research_idea.retrieval_transport.time.sleep') as sleep:
            self.assertEqual(request_with_policy(fetch, 'https://api.openalex.org/a', 20, {}, LiteratureError), b'ok')
        sleep.assert_called_once_with(1)
        self.assertEqual(fetch.call_count, 2)

    def test_exhausted_quota_is_not_retried_per_venue(self):
        state = self.state()
        token = SESSION.set(state)
        fetch = Mock(side_effect=self.failure(429, 36000))
        try:
            with patch('research_idea.retrieval_transport.time.sleep') as sleep:
                for path in ('/sources?search=ACL', '/sources?search=ICML', '/works'):
                    with self.assertRaises(LiteratureError):
                        request_with_policy(fetch, 'https://api.openalex.org' + path, 20, {}, LiteratureError)
                sleep.assert_not_called()
            self.assertEqual(fetch.call_count, 1)
            self.assertEqual(state['skipped'], 2)
        finally:
            SESSION.reset(token)

    def test_403_switches_provider_without_retries(self):
        token = SESSION.set(self.state())
        fetch = Mock(side_effect=[self.failure(403), b'official index'])
        try:
            with self.assertRaises(LiteratureError):
                request_with_policy(fetch, 'https://api2.openreview.net/notes', 10, {}, LiteratureError)
            self.assertEqual(request_with_policy(fetch, 'https://colm.cc/Conferences/2026/AcceptedPapers', 10, {}, LiteratureError), b'official index')
            self.assertEqual(fetch.call_count, 2)
        finally:
            SESSION.reset(token)

    def test_project_cache_avoids_repeated_index_requests_and_does_not_store_credentials(self):
        with tempfile.TemporaryDirectory() as tmp:
            token = SESSION.set(self.state(Path(tmp)))
            fetch = Mock(return_value=b'index')
            try:
                for _ in range(2):
                    request_with_policy(fetch, 'https://api.openalex.org/sources', 10, {'Authorization': 'secret-sentinel'}, LiteratureError)
                fetch.assert_called_once()
                self.assertNotIn('secret-sentinel', str(list(Path(tmp).iterdir())))
                self.assertEqual(SESSION.get()['cache_hits'], 1)
            finally:
                SESSION.reset(token)


class ProceedingsTests(unittest.TestCase):
    def test_acl_main_titles_abstracts_and_month_precision(self):
        html = '''<title>2026.acl-long</title><dl><dt>Month:</dt><dd>July</dd></dl>
        <a href=/2026.acl-long.1/>Agent <span>Memory</span></a>
        <div id=abstract-2026--acl-long--1><div>Reported abstract.</div></div>
        <a href=/2026.findings-acl.1/>Wrong track</a>'''
        rows = parse_index(html, 'https://aclanthology.org/2026.acl-long/', 'ACL', 2026)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['abstract'], 'Reported abstract.')
        self.assertNotIn('publication_date', rows[0])
        self.assertEqual(rows[0]['publication_period'], '2026-07')
        scope = {'since': '2026-04-23', 'until': '2026-10-23', 'cs_only': True, 'arxiv_categories': []}
        self.assertIsNone(exclusion_reason(rows[0], scope, 'official_proceedings', verified_venue=True))
        self.assertIsNotNone(exclusion_reason(rows[0], dict(scope, since='2026-08-01'), 'official_proceedings', verified_venue=True))

    def test_neurips_main_excludes_creative_track(self):
        html = '''<title>Main Conference</title><a title="paper title" href="/paper_files/paper/2025/hash/abcdef-Abstract-Conference.html">Agent</a>
        <a title="paper title" href="/paper_files/paper/2025/hash/fedcba-Abstract-Creative_AI_Track.html">Other</a>'''
        rows = parse_index(html, 'https://papers.nips.cc/paper_files/paper/2025/vol38-main-conference', 'NeurIPS', 2025)
        self.assertEqual(len(rows), 1)
        self.assertTrue(rows[0]['pdf_url'].endswith('-Paper-Conference.pdf'))

    def test_colm_title_only_index_is_not_fulltext_and_papers_keep_distinct_ids(self):
        html = '<title>COLM 2026 Accepted Papers</title><tr><td><strong>First agent</strong></td></tr><tr><td><strong>Second agent</strong></td></tr>'
        rows = parse_index(html, 'https://colm.cc/Conferences/2026/AcceptedPapers', 'COLM', 2026)
        self.assertEqual(len({p['id'] for p in rows}), 2)
        self.assertTrue(all(not p['abstract'] and p['content_kind'] == 'abstract' for p in rows))

    def test_iclr_selected_link_resolves_only_actual_openreview_link(self):
        html = '<div id="abstractText">Actual abstract.</div><a href="https://openreview.net/forum?id=actual-id">OpenReview</a>'
        paper = normalize_paper({'id': 'p', 'title': 'Title', 'source': 'official_proceedings', 'venue': 'ICLR', 'url': 'https://iclr.cc/virtual/2026/poster/1'})
        with patch('research_idea.literature._request_bytes', return_value=html.encode()):
            enriched = enrich_selected(paper)
        self.assertEqual(enriched['pdf_url'], 'https://openreview.net/pdf?id=actual-id')
        self.assertEqual(enriched['abstract'], 'Actual abstract.')
