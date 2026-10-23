import io
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import Mock, patch
from urllib.error import HTTPError
from urllib.parse import parse_qs, urlparse

from research_idea import literature as lit


ATOM = b'''<feed xmlns="http://www.w3.org/2005/Atom" xmlns:x="http://arxiv.org/schemas/atom">
<entry><id>http://arxiv.org/abs/2409.12345v2</id><title>A\n paper</title><published>2024-09-20</published>
<author><name>Alice</name></author><summary>Abstract only.</summary><x:doi>10.1234/TEST</x:doi></entry></feed>'''


class LiteratureTests(unittest.TestCase):
    def setUp(self):
        lit._last_arxiv_request = 0

    def test_doi_and_arxiv_normalization(self):
        p = lit.normalize_paper({"title": " A  title ", "doi": "https://doi.org/10.1234/ABC", "url": "https://arxiv.org/pdf/2409.12345v2.pdf"})
        self.assertEqual(p["id"], "doi:10.1234/abc")
        self.assertEqual(p["version"], "v2")
        self.assertIn("arxiv:2409.12345", p["aliases"])

    def test_old_arxiv_and_year(self):
        p = lit.normalize_paper({"id": "arXiv:hep-th/9901001v3", "title": "T", "year": "1999", "authors": "Author"})
        self.assertEqual(p["id"], "arxiv:hep-th/9901001")
        self.assertEqual(p["year"], 1999)
        self.assertEqual(p["authors"], ["Author"])

    def test_arxiv_doi_matches_preprint(self):
        papers = lit.deduplicate([{"title": "T", "id": "arxiv:2409.12345v2"},
                                  {"title": "T", "doi": "https://doi.org/10.48550/arXiv.2409.12345"}])
        self.assertEqual(len(papers), 1)

    def test_no_invented_full_text(self):
        self.assertEqual(lit.normalize_paper({"title": "T", "abstract": "A"})["content_kind"], "abstract")
        self.assertEqual(lit.normalize_paper({"title": "T", "text": "Some notes"})["content_kind"], "notes")

    def test_transitive_dedup_keeps_full_text_and_metadata(self):
        papers = [{"title": "T", "id": "arxiv:2409.12345v1", "text": "Full content", "content_kind": "full_text"},
                  {"title": "T", "doi": "10.1234/xyz", "source": "openalex"},
                  {"title": "T", "doi": "10.1234/XYZ", "url": "https://arxiv.org/abs/2409.12345v2", "source": "arxiv"}]
        merged = lit.deduplicate(papers)
        self.assertEqual(len(merged), 1)
        self.assertEqual(merged[0]["text"], "Full content")
        self.assertEqual(merged[0]["version"], "v1")
        self.assertEqual(merged[0]["versions"], ["v1", "v2"])
        self.assertEqual(merged[0]["id"], "doi:10.1234/xyz")

    def test_same_title_different_identifiers_not_merged(self):
        self.assertEqual(len(lit.deduplicate([{"id": "a", "title": "Same"}, {"id": "b", "title": "Same"}])), 2)

    def test_arxiv_query_encoding_and_abstract(self):
        with patch.object(lit, "_request_bytes", return_value=ATOM) as request:
            papers = lit.discover("RAG & uncertainty")
        query = parse_qs(urlparse(request.call_args.args[0]).query)
        self.assertEqual(query["search_query"], ["all:RAG & uncertainty"])
        self.assertEqual(papers[0]["title"], "A paper")
        self.assertEqual(papers[0]["content_kind"], "abstract")
        self.assertNotIn("text", papers[0])

    def test_arxiv_error_and_entity_rejected(self):
        for data in [b"not xml", b"<!DOCTYPE foo><feed/>", b'<feed xmlns="http://www.w3.org/2005/Atom"><entry><id>http://arxiv.org/api/errors#1</id></entry></feed>']:
            lit._last_arxiv_request = 0
            with patch.object(lit, "_request_bytes", return_value=data), self.assertRaises(lit.LiteratureError):
                lit.discover("x")

    def test_openalex_ordered_abstract_and_header_secret(self):
        payload = {"results": [{"id": "https://openalex.org/W123", "title": "A paper", "publication_year": 2024,
                   "doi": "https://doi.org/10.1234/X", "primary_location": None,
                   "authorships": [{"author": {"display_name": "Alice"}}],
                   "abstract_inverted_index": {"second": [1], "first": [0], "last": [2]}}]}
        with patch.dict(os.environ, {"TEST_LIT_KEY": "private-secret"}), patch.object(lit, "_request_bytes", return_value=json.dumps(payload).encode()) as request:
            papers = lit.discover("test", "openalex", api_key_env="TEST_LIT_KEY")
        self.assertEqual(papers[0]["abstract"], "first second last")
        self.assertNotIn("private-secret", request.call_args.args[0])
        self.assertEqual(request.call_args.args[2]["Authorization"], "Bearer private-secret")

    def test_missing_key_is_explicit(self):
        with patch.dict(os.environ, {}, clear=True), self.assertRaises(lit.LiteratureError):
            lit.discover("x", "openalex", api_key_env="MISSING")

    def test_response_size_and_http_errors_are_safe(self):
        response = io.BytesIO(b"123456")
        opener = Mock()
        opener.open.return_value = response
        with patch.object(lit, "MAX_RESPONSE_BYTES", 5), patch.object(lit, "build_opener", return_value=opener), self.assertRaises(lit.LiteratureError):
            lit._request_bytes("https://example.test", 1)
        error = HTTPError("https://example.test?api_key=secret", 403, "secret", {}, None)
        opener.open.side_effect = error
        with patch.object(lit, "build_opener", return_value=opener), self.assertRaises(lit.LiteratureError) as caught:
            lit._request_bytes("https://example.test", 1)
        self.assertNotIn("secret", str(caught.exception))

    def test_redirect_does_not_forward_token_to_another_host(self):
        request = lit.Request("https://api.openalex.org/works", headers={"Authorization": "Bearer secret"})
        with self.assertRaises(lit.LiteratureError):
            lit._SameHostRedirect().redirect_request(request, None, 302, "Found", {}, "https://other.test/works")

    def test_local_text_stable_identity_and_honest_kind(self):
        with tempfile.TemporaryDirectory() as temp:
            first, second = Path(temp)/"a.md", Path(temp)/"b.md"
            first.write_text("# Notes\nEvidence", encoding="utf-8")
            second.write_bytes(first.read_bytes())
            a, b = lit.read_source(first), lit.read_source(second)
        self.assertEqual(a["id"], b["id"])
        self.assertEqual(a["content_kind"], "notes")
        self.assertIn("Evidence", a["text"])

    def test_unsupported_empty_and_non_utf8(self):
        with tempfile.TemporaryDirectory() as temp:
            p = Path(temp)/"x.txt"
            for content in [b"", b"\xff"]:
                p.write_bytes(content)
                with self.assertRaises(lit.LiteratureError):
                    lit.read_source(p)
            with self.assertRaises(lit.LiteratureError):
                lit.read_source(Path(temp)/"absent.md")

    def test_pdf_extraction_has_no_shell_and_preserves_pages(self):
        with tempfile.TemporaryDirectory() as temp:
            p = Path(temp)/"strange name; echo.pdf"
            p.write_bytes(b"%PDF dummy")
            def extract(argv, **kwargs):
                self.assertEqual(argv[-2], str(p))
                self.assertNotIn("shell", kwargs)
                Path(argv[-1]).write_text("Page 1\fPage 2", encoding="utf-8")
                return subprocess.CompletedProcess(argv, 0)
            with patch.object(lit.shutil, "which", return_value="/usr/bin/pdftotext"), patch.object(lit.subprocess, "run", side_effect=extract):
                paper = lit.read_source(p)
            self.assertEqual(paper["content_kind"], "full_text")
            self.assertIn("\f", paper["text"])

    def test_pdf_missing_dependency(self):
        with tempfile.TemporaryDirectory() as temp:
            p = Path(temp)/"x.pdf"
            p.write_bytes(b"%PDF")
            with patch.object(lit.shutil, "which", return_value=None), self.assertRaises(lit.LiteratureError):
                lit.read_source(p)

    def test_invalid_limits(self):
        for kwargs in [{"limit": 0}, {"limit": True}, {"timeout_s": float("nan")}, {"source": "unknown"}]:
            with self.assertRaises(lit.LiteratureError):
                lit.discover("x", **kwargs)


if __name__ == "__main__":
    unittest.main()
