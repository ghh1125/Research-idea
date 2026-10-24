"""Provider metadata contracts and bounded venue discovery, without network."""
import json
import io
import unittest
from datetime import date
from unittest.mock import Mock, patch
from urllib.parse import parse_qs, urlparse

from research_idea import literature as lit
from research_idea.venues import canonical_venue


def encoded(value):
    return json.dumps(value).encode()


def work(identifier="W1", source_id="S1", venue="Conference on Empirical Methods in Natural Language Processing"):
    return {"id": "https://openalex.org/" + identifier, "display_name": "A method for retrieval",
            "publication_year": 2025, "authorships": [], "abstract_inverted_index": {"retrieval": [0]},
            "primary_location": {"landing_page_url": "https://aclanthology.org/2025.emnlp-main.1/",
                                 "pdf_url": "https://aclanthology.org/2025.emnlp-main.1.pdf",
                                 "source": {"id": "https://openalex.org/" + source_id, "display_name": venue}}}


def note(identifier="abc123", year=None, accepted=True, title="Retrieval with uncertainty"):
    year = year or date.today().year
    venue = f"colmweb.org/COLM/{year}/Conference" + ("/Rejected_Submission" if not accepted else "")
    return {"id": identifier, "content": {"title": {"value": title}, "abstract": {"value": "Retrieval and language modeling."},
            "authors": {"value": ["Alice"]}, "venueid": {"value": venue}, "venue": {"value": f"COLM {year}"},
            "pdf": {"value": "/pdf/abc123.pdf"}}}


class VenueRetrievalTests(unittest.TestCase):
    def test_explicit_aliases_and_dated_ccf_subset(self):
        self.assertEqual(lit.normalize_venues(["emnlp", "NAACL-HLT", "Conference on Language Modeling", "EMNLP"]),
                         ["EMNLP", "NAACL", "COLM"])
        self.assertEqual(len(lit.normalize_venues(["ccf-a-ai-2022"])), 7)
        self.assertNotIn("ICLR", lit.normalize_venues(["ccf-a-ai-2022"]))
        self.assertNotIn("COLM", lit.normalize_venues(["ccf-a-ai-2022"]))
        with self.assertRaises(ValueError):
            lit.normalize_venues(["CCF-A"])

    def test_main_proceedings_are_distinct_from_findings_workshops_and_industry(self):
        self.assertEqual(canonical_venue("Proceedings of the 2025 Conference on Empirical Methods in Natural Language Processing"), "EMNLP")
        self.assertEqual(canonical_venue("Proceedings of the 2025 Conference of the Nations of the Americas Chapter of the Association for Computational Linguistics: Human Language Technologies (Volume 1: Long Papers)"), "NAACL")
        self.assertEqual(canonical_venue("Proceedings of the 63rd Annual Meeting of the Association for Computational Linguistics (Volume 2: Short Papers)"), "ACL")
        self.assertEqual(canonical_venue("Second Conference on Language Modeling"), "COLM")
        for name in ["Findings of the Association for Computational Linguistics: EMNLP 2025",
                     "EMNLP 2025 Industry Track", "Workshop on Empirical Methods in Natural Language Processing",
                     "Transactions of the Association for Computational Linguistics"]:
            self.assertIsNone(canonical_venue(name))

    def test_extended_venues_accept_real_series_and_user_aliases(self):
        self.assertEqual(lit.normalize_venues(['kdd', 'icdm', 'icde', 'sigmod', 'vldb', 'acm mm', 'cvpr', 'iccv', 'sigir', 'www']),
                         ['KDD', 'ICDM', 'ICDE', 'SIGMOD', 'VLDB', 'ACMMM', 'CVPR', 'ICCV', 'SIGIR', 'WWW'])
        for name, expected in [
            ('Proceedings of the 32nd ACM SIGKDD Conference on Knowledge Discovery and Data Mining', 'KDD'),
            ('2026 IEEE International Conference on Data Mining', 'ICDM'),
            ('2026 IEEE 42nd International Conference on Data Engineering', 'ICDE'),
            ('Proceedings of the 2026 International Conference on Management of Data', 'SIGMOD'),
            ('Proceedings of the VLDB Endowment', 'VLDB'),
            ('Proceedings of the 34th ACM International Conference on Multimedia', 'ACMMM'),
            ('Proceedings of the 49th International ACM SIGIR Conference on Research and Development in Information Retrieval', 'SIGIR'),
            ('Proceedings of the ACM Web Conference 2026', 'WWW'),
        ]:
            with self.subTest(name=name):
                self.assertEqual(canonical_venue(name), expected)
        self.assertIsNone(canonical_venue('Companion Proceedings of the ACM Web Conference 2026'))
        self.assertIsNone(canonical_venue('The VLDB Journal'))

    def test_sigmod_lookup_includes_pacmmod_but_retains_its_series_identity(self):
        queries = []
        name = 'Proceedings of the ACM on Management of Data'
        def request(url, *_args):
            params = parse_qs(urlparse(url).query)
            if urlparse(url).path == '/sources':
                queries.append(params['search'][0])
                return encoded({'results': [{'id': 'S42', 'display_name': name}] if params['search'][0] == name else []})
            return encoded({'results': [work('W42', 'S42', name)]})
        with patch.object(lit, '_request_bytes', side_effect=request):
            results = lit.discover('retrieval', 'openalex', venues=['SIGMOD'])
        self.assertIn(name, queries)
        self.assertEqual(results[0]['venue'], 'PACMMOD')
        self.assertEqual(results[0]['requested_venue'], 'SIGMOD')
        self.assertEqual(results.coverage['selected_counts']['SIGMOD'], 1)
        self.assertEqual(results[0]['venue_name'], name)

    def test_last_requested_venue_can_win_a_small_result_limit_by_relevance(self):
        def request(url, *_args):
            params = parse_qs(urlparse(url).query)
            if urlparse(url).path == '/sources':
                return encoded({'results': [{'id': 'S1', 'display_name': 'EMNLP'}, {'id': 'S2', 'display_name': 'ACM Web Conference'}]})
            sid = params['filter'][0].split(':')[1]
            record = work('W' + sid, sid, 'EMNLP' if sid == 'S1' else 'ACM Web Conference')
            record['display_name'] = 'Grammatical parsing' if sid == 'S1' else 'Retrieval for language agents'
            record['abstract_inverted_index'] = {}
            return encoded({'results': [record]})
        with patch.object(lit, '_request_bytes', side_effect=request):
            results = lit.discover('retrieval language agents', 'openalex', limit=1, venues=['EMNLP', 'WWW'])
        self.assertEqual(results[0]['venue'], 'WWW')

    def test_arxiv_cannot_claim_accepted_venue_filtering(self):
        with patch.object(lit, "_request_bytes") as request, self.assertRaisesRegex(lit.LiteratureError, "choose openalex"):
            lit.discover("retrieval", venues=["EMNLP"])
        request.assert_not_called()

    def test_arxiv_courtesy_delay_respects_remaining_budget(self):
        with patch.object(lit, "_last_arxiv_request", 10), patch.object(lit.time, "monotonic", return_value=10), \
             patch.object(lit.time, "sleep") as sleep, self.assertRaisesRegex(lit.LiteratureError, "courtesy delay"):
            lit.discover("retrieval", timeout_s=1)
        sleep.assert_not_called()

    def test_metadata_read_checks_total_deadline(self):
        opener = Mock()
        opener.open.return_value = io.BytesIO(b"data")
        with patch.object(lit, "build_opener", return_value=opener), \
             patch.object(lit.time, "monotonic", side_effect=[0, 0, 0, 0, 2]), \
             self.assertRaisesRegex(lit.LiteratureError, "budget exhausted"):
            lit._request_bytes("https://api.openalex.org/works", 1)

    def test_metadata_redirect_rejects_other_port_or_userinfo(self):
        request = lit.Request("https://api.openalex.org/works")
        for target in ["https://api.openalex.org:8443/works", "https://name@api.openalex.org/works", "https://api.openalex.org:invalid/works"]:
            with self.assertRaises(lit.LiteratureError):
                lit._SameHostRedirect().redirect_request(request, None, 302, "Found", {}, target)

    def test_real_source_filter_used_and_metadata_retained(self):
        calls = []
        def request(url, *_args):
            calls.append(url)
            if urlparse(url).path == "/sources":
                return encoded({"results": [{"id": "https://openalex.org/S1", "display_name": "Conference on Empirical Methods in Natural Language Processing"},
                                             {"id": "https://openalex.org/S2", "display_name": "Findings of EMNLP"}]})
            return encoded({"results": [work(), work("W2", "S999")]})
        with patch.object(lit, "_request_bytes", side_effect=request):
            results = lit.discover("retrieval", "openalex", venues=["EMNLP"])
        self.assertEqual(parse_qs(urlparse(calls[-1]).query)["filter"], ["primary_location.source.id:S1"])
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["venue"], "EMNLP")
        self.assertEqual(results[0]["venue_id"], "S1")
        self.assertIn("locations", results[0])
        self.assertEqual(results[0]["content_kind"], "abstract")
        self.assertTrue(results[0]["pdf_url"].endswith(".pdf"))
        self.assertTrue(any("outside" in gap for gap in results.coverage["gaps"]))

    def test_naacl_lookup_searches_both_current_and_historical_names(self):
        queries = []
        current_name = "Conference of the Nations of the Americas Chapter of the Association for Computational Linguistics: Human Language Technologies"
        def request(url, *_args):
            query = parse_qs(urlparse(url).query)
            if urlparse(url).path == "/sources":
                queries.append(query["search"][0])
                return encoded({"results": [{"id": "S42", "display_name": current_name}] if "Nations" in query["search"][0] else []})
            return encoded({"results": [work("W42", "S42", current_name)]})
        with patch.object(lit, "_request_bytes", side_effect=request):
            results = lit.discover("retrieval", "openalex", venues=["NAACL"])
        self.assertTrue(any("Nations" in q for q in queries))
        self.assertTrue(any("North American" in q for q in queries))
        self.assertEqual(results[0]["venue"], "NAACL")

    def test_unresolved_and_ambiguous_sources_never_broaden_search(self):
        for sources in [[], [{"id": "S1", "display_name": "EMNLP"}, {"id": "S2", "display_name": "EMNLP"}]]:
            with patch.object(lit, "_request_bytes", return_value=encoded({"results": sources})) as request:
                results = lit.discover("retrieval", "openalex", venues=["EMNLP"])
            self.assertFalse(results)
            self.assertEqual(request.call_count, 1)
            self.assertTrue(results.coverage["gaps"])

    def test_query_title_cannot_supply_venue_evidence(self):
        fake = work(venue="Unknown journal")
        fake["display_name"] = "An EMNLP NAACL COLM accepted paper"
        with patch.object(lit, "_request_bytes", return_value=encoded({"results": [fake]})):
            results = lit.discover("EMNLP", "openalex")
        self.assertIsNone(results[0]["venue"])
        self.assertEqual(results[0]["venue_name"], "Unknown journal")

    def test_colm_queries_accepted_venue_and_rechecks_results(self):
        urls = []
        def request(url, *_args):
            urls.append(url)
            year = int(parse_qs(urlparse(url).query)["content.venueid"][0].split("/")[2])
            return encoded({"notes": [note(str(year), year), note("rejected", year, accepted=False)]})
        with patch.object(lit, "_request_bytes", side_effect=request):
            results = lit.discover("retrieval", "openalex", venues=["COLM"])
        self.assertTrue(results)
        self.assertTrue(all(p["venue"] == "COLM" and p["source"] == "openreview" for p in results))
        self.assertTrue(all("rejected" not in p["id"] for p in results))
        self.assertTrue(all(urlparse(url).hostname == "api2.openreview.net" for url in urls))
        self.assertTrue(all(parse_qs(urlparse(url).query)["content.venueid"][0].endswith("/Conference") for url in urls))
        self.assertIn("lexical", results.coverage["openreview_colm"]["ranking"])
        self.assertIn("https://openreview.net/pdf?id=", results[0]["pdf_url"])

    def test_colm_scan_cap_and_empty_results_have_coverage(self):
        with patch.object(lit, "OPENREVIEW_PAGE_SIZE", 1), patch.object(lit, "OPENREVIEW_MAX_PAGES", 1), \
             patch.object(lit, "_request_bytes", return_value=encoded({"notes": [note()], "count": 5})) as request:
            results = lit.discover("unmatchable", "openalex", venues=["COLM"])
        self.assertEqual(results, [])
        self.assertLessEqual(request.call_count, 3)
        self.assertTrue(any("page limit" in gap for gap in results.coverage["gaps"]))

    def test_provider_failure_preserves_other_venue_results_and_error(self):
        def request(url, *_args):
            if urlparse(url).hostname == "api.openalex.org":
                raise lit.LiteratureError("Literature service returned HTTP 503.")
            year = int(parse_qs(urlparse(url).query)["content.venueid"][0].split("/")[2])
            return encoded({"notes": [note(str(year), year)]})
        with patch.object(lit, "_request_bytes", side_effect=request), \
             patch('research_idea.proceedings.discover_proceedings', return_value=[]):
            results = lit.discover("retrieval", "openalex", venues=["EMNLP", "COLM"])
        self.assertTrue(results)
        self.assertTrue(all(p["venue"] == "COLM" for p in results))
        self.assertTrue(any("503" in gap for gap in results.coverage["gaps"]))

    def test_each_venue_gets_filtered_query_and_results_interleave(self):
        filters = []
        def request(url, *_args):
            query = parse_qs(urlparse(url).query)
            if urlparse(url).hostname == "api2.openreview.net":
                year = int(query["content.venueid"][0].split("/")[2])
                return encoded({"notes": [note(str(year), year)]})
            if urlparse(url).path == "/sources":
                venue = "EMNLP" if "Empirical" in query["search"][0] else "NAACL"
                return encoded({"results": [{"id": "S1" if venue == "EMNLP" else "S2", "display_name": venue}]})
            filters.append(query["filter"][0])
            sid = query["filter"][0].split(":")[1]
            return encoded({"results": [work("W" + sid + str(i), sid, "EMNLP" if sid == "S1" else "NAACL") for i in range(3)]})
        with patch.object(lit, "_request_bytes", side_effect=request):
            results = lit.discover("retrieval", "openalex", limit=3, venues=["EMNLP", "NAACL", "COLM"])
        self.assertCountEqual([p["venue"] for p in results], ["EMNLP", "NAACL", "COLM"])
        self.assertEqual(set(filters), {"primary_location.source.id:S1", "primary_location.source.id:S2"})

    def test_invalid_provider_record_does_not_drop_valid_records(self):
        with patch.object(lit, "_request_bytes", return_value=encoded({"results": [None, {"title": ""}, work()]})):
            results = lit.discover("retrieval", "openalex")
        self.assertEqual(len(results), 1)
        self.assertEqual(len(results.coverage["gaps"]), 2)

    def test_dedup_preserves_pdf_locations_and_venue(self):
        results = lit.deduplicate([{"id": "x", "title": "T", "text": "Full text", "content_kind": "full_text"},
                                   {"id": "x", "title": "T", "venue": "EMNLP", "pdf_url": "https://aclanthology.org/2025.emnlp-main.1.pdf",
                                    "locations": [{"pdf_url": "https://arxiv.org/pdf/2401.12345"}]}])
        self.assertEqual(results[0]["venue"], "EMNLP")
        self.assertEqual(len(results[0]["locations"]), 1)
        self.assertEqual(results[0]["content_kind"], "full_text")


if __name__ == "__main__":
    unittest.main()
