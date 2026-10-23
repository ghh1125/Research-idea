"""Hard literature filters must survive provider errors and source mixing."""
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
from urllib.parse import parse_qs, urlparse

from research_idea import literature as lit
from research_idea.config import DEFAULTS
from research_idea.controller import Controller
from research_idea.search_scope import normalize_scope
from research_idea.store import Store


SCOPE = dict(since="2025-01-01", until="2026-10-23", cs_only=True, arxiv_categories=["cs.*"])


def atom(entries):
    body = []
    for index, (published, categories) in enumerate(entries):
        body.append(f'''<entry><id>https://arxiv.org/abs/2601.{index:05d}</id>
          <title>Agent environments {index}</title><summary>Environment design</summary>
          <published>{published}T00:00:00Z</published><updated>2026-10-20T00:00:00Z</updated>
          {''.join(f'<category term="{c}"/>' for c in categories)}</entry>''')
    return ('<feed xmlns="http://www.w3.org/2005/Atom">' + ''.join(body) + '</feed>').encode()


def work(identifier="1", published="2026-05-01", field="17", source=None):
    return {"id": "https://openalex.org/W" + identifier, "title": "Agent environments " + identifier,
            "publication_year": int(published[:4]), "publication_date": published,
            "primary_topic": {"field": {"id": "https://openalex.org/fields/" + field}},
            "primary_location": {"source": source}, "authorships": []}


class ScopeTests(unittest.TestCase):
    def test_invalid_filters_fail_before_network(self):
        for scope in [dict(since="2025"), dict(until="2025-02-30"),
                      dict(since="2026-01-01", until="2025-01-01"), dict(cs_only=1),
                      dict(arxiv_categories="cs.*"), dict(arxiv_categories=["cs.* OR cat:math.*"])]:
            with self.subTest(scope=scope), patch.object(lit, "_request_bytes") as request:
                with self.assertRaises(ValueError):
                    normalize_scope(**scope)
                request.assert_not_called()

    def test_arxiv_scope_is_in_query_and_rechecked_against_original_date_and_categories(self):
        feed = atom([("2026-05-01", ["cs.AI"]), ("2020-05-01", ["cs.LG"]),
                     ("2026-05-01", ["math.AG"]), ("2027-05-01", ["cs.CL"]),
                     ("2026-05-01", []), ("2026-05-01", ["math.OC", "cs.LG"])])
        with patch.object(lit, "_request_bytes", return_value=feed) as request, \
             patch.object(lit, "_last_arxiv_request", 0):
            found = lit.discover('all:agents OR all:environment', limit=10, **SCOPE)
        expression = parse_qs(urlparse(request.call_args.args[0]).query)["search_query"][0]
        self.assertTrue(expression.startswith('(all:agents OR all:environment) AND'))
        self.assertIn('cat:cs.*', expression)
        self.assertIn('submittedDate:[202501010000 TO 202610232359]', expression)
        self.assertEqual([p["id"] for p in found], ['arxiv:2601.00000', 'arxiv:2601.00005'])
        self.assertEqual(len(found.coverage["excluded"]), 4)
        self.assertEqual(found[0]["publication_date"], "2026-05-01")

    def test_specific_arxiv_categories_are_enforced_on_cross_lists(self):
        feed = atom([("2026-05-01", ["cs.AI"]), ("2026-05-01", ["cs.CL", "cs.AI"])])
        with patch.object(lit, "_request_bytes", return_value=feed), patch.object(lit, "_last_arxiv_request", 0):
            found = lit.discover('agents', **dict(SCOPE, arxiv_categories=["cs.CL"]))
        self.assertEqual(len(found), 1)
        self.assertIn('cs.CL', found[0]["categories"])

    def test_openalex_cs_and_date_filters_are_transmitted_and_rechecked(self):
        works = [work(), work("2", "2020-01-01"), work("3", field="26"),
                 dict(work("4"), publication_date=None)]
        with patch.object(lit, "_json_results", return_value=(works, {})) as request:
            found = lit.discover('agents', source='openalex', **SCOPE)
        filters = parse_qs(urlparse(request.call_args.args[0]).query)["filter"][0]
        self.assertIn('topics.field.id:17', filters)
        self.assertIn('from_publication_date:2025-01-01', filters)
        self.assertIn('to_publication_date:2026-10-23', filters)
        self.assertEqual(len(found), 1)
        self.assertEqual(len(found.coverage["excluded"]), 3)

    def test_verified_ai_venue_does_not_require_inferred_cs_field(self):
        source = {"id": "https://openalex.org/S1", "display_name": "Neural Information Processing Systems"}
        works = [work(field="26", source=source)]
        with patch.object(lit, "_openalex_sources", return_value={"S1": "NeurIPS"}), \
             patch.object(lit, "_json_results", return_value=(works, {})):
            found = lit.discover('agents', source='openalex', venues=['NeurIPS'], **SCOPE)
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0]["venue"], "NeurIPS")

    def test_hybrid_preserves_filters_and_prefers_verified_conferences(self):
        original = lit.discover
        calls = []
        def provider(query, **options):
            calls.append(options)
            conference = options["source"] == "openalex"
            papers = [{"id": f'{options["source"]}-{i}', "title": f'Paper {i}',
                       "venue": "ICML" if conference else None} for i in range(options["limit"])]
            return lit.DiscoveryResults(papers, coverage={"gaps": []})
        with patch.object(lit, "discover", side_effect=provider):
            found = original('agent environments', source='hybrid', venues=['ICML'], limit=6, **SCOPE)
        self.assertEqual([c["source"] for c in calls], ['openalex', 'arxiv'])
        self.assertEqual([c["limit"] for c in calls], [4, 2])
        for call in calls:
            for key, value in SCOPE.items():
                self.assertEqual(call[key], value)
        self.assertEqual(found.coverage["selected_counts"], {"conference": 4, "arxiv_preprint": 2})
        calls.clear()
        with patch.object(lit, "discover", side_effect=provider):
            small = original('agent environments', source='hybrid', venues=['ICML'], limit=2, **SCOPE)
        self.assertEqual([c["source"] for c in calls], ['openalex'])
        self.assertEqual(small.coverage["selected_counts"], {"conference": 2, "arxiv_preprint": 0})

    def test_hybrid_fallback_keeps_scope_and_marks_conference_failure(self):
        original = lit.discover
        calls = []
        def provider(query, **options):
            calls.append(options)
            if options["source"] == "openalex":
                raise lit.LiteratureError('index unavailable')
            return lit.DiscoveryResults([], coverage={"gaps": []})
        with patch.object(lit, "discover", side_effect=provider):
            found = original('agents', source='hybrid', limit=3, **SCOPE)
        self.assertEqual(calls[1]["since"], SCOPE["since"])
        self.assertTrue(calls[1]["cs_only"])
        self.assertIn('openalex: index unavailable', found.coverage["gaps"])

    def test_scope_changes_invalidate_discovery_cache(self):
        with tempfile.TemporaryDirectory() as directory:
            store = Store(Path(directory))
            try:
                controller = Controller(store, None, dict(DEFAULTS, fetch_full_text=False))
                with patch.object(lit, "discover", return_value=[]) as search:
                    controller.search_once('agents', 'test')
                    controller.search_once('agents', 'cached')
                    controller.config['search_since'] = '2024-01-01'
                    controller.search_once('agents', 'changed time window')
                    controller.config['arxiv_categories'] = ['cs.CL']
                    controller.search_once('agents', 'changed category')
                self.assertEqual(search.call_count, 3)
            finally:
                store.close()

    def test_readonly_store_has_stable_wal_snapshot_and_cannot_write(self):
        with tempfile.TemporaryDirectory() as directory:
            writer = Store(Path(directory))
            writer.set('status', 'running')
            reader = Store(Path(directory), readonly=True)
            try:
                self.assertEqual(reader.get('status'), 'running')
                writer.set('status', 'completed')
                self.assertEqual(reader.get('status'), 'running')
                with self.assertRaises(sqlite3.OperationalError):
                    reader.set('status', 'corrupted')
                self.assertEqual(writer.get('status'), 'completed')
            finally:
                reader.close()
                writer.close()
