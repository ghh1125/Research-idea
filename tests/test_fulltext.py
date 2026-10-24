from __future__ import annotations

import copy
import hashlib
import io
import json
import shutil
from pathlib import Path
import sys
import tempfile
import time
import unittest
from unittest.mock import Mock, patch
from urllib.error import HTTPError
from urllib.request import Request
from urllib.parse import parse_qs, urlparse

from research_idea import fulltext


PDF_URL = "https://aclanthology.org/2024.acl-long.1.pdf"
PDF_BYTES = b"%PDF-1.7\nsynthetic test fixture; not a real scientific paper\n%%EOF\n"


class FakeResponse(io.BytesIO):
    def __init__(self, payload, url=PDF_URL, headers=None):
        super().__init__(payload)
        self.url = url
        self.headers = headers or {}
        self.status = 200

    def geturl(self):
        return self.url


class FullTextTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.paper = {"id": "stable-paper-id", "title": "A supplied paper",
                      "url": PDF_URL, "text": "Existing abstract text.",
                      "abstract": "Existing abstract text.", "content_kind": "abstract"}

    def tearDown(self):
        self.tmp.cleanup()

    def download(self, url, target, timeout_s):
        Path(target).write_bytes(PDF_BYTES)
        return {"final_url": url, "pdf_sha256": hashlib.sha256(PDF_BYTES).hexdigest()}

    def assert_preserved_failure(self, original, result):
        for field in ("id", "text", "content_kind"):
            self.assertEqual(result.get(field), original.get(field))
        self.assertIsNot(result, original)
        self.assertIn(result["full_text_retrieval"]["status"], {"failed", "unavailable"})
        self.assertTrue(result["full_text_error"].strip())

    def test_acl_landing_page_and_doi_resolve_to_pdf(self):
        for record in [{"url": "https://aclanthology.org/2024.acl-long.1/"},
                       {"doi": "10.18653/v1/2024.acl-long.1"},
                       {"doi": "https://doi.org/10.18653/v1/2024.acl-long.1"}]:
            with self.subTest(record=record):
                self.assertIn(PDF_URL, fulltext.candidate_pdf_urls(record))

    def test_openreview_forum_preserves_paper_identifier(self):
        candidates = fulltext.candidate_pdf_urls({"url": "https://openreview.net/forum?id=AbC_123-xyz"})
        self.assertTrue(any(urlparse(url).path == "/pdf" and
                            parse_qs(urlparse(url).query).get("id") == ["AbC_123-xyz"]
                            for url in candidates))

    def test_database_and_acm_public_pdf_locations_are_retrievable(self):
        for url in ['https://www.vldb.org/pvldb/vol19/p1-example.pdf',
                    'https://dl.acm.org/doi/pdf/10.1145/1234567.1234568',
                    'https://ieeexplore.ieee.org/iel7/123/456/example.pdf']:
            with self.subTest(url=url):
                self.assertEqual(fulltext.candidate_pdf_urls({'pdf_url': url}), [url])
        self.assertEqual(fulltext.candidate_pdf_urls({'pdf_url': 'https://dl.acm.org/doi/epdf/10.1145/1234567.1234568'}),
                         ['https://dl.acm.org/doi/pdf/10.1145/1234567.1234568'])

    def test_arxiv_identifiers_preserve_version(self):
        for record in [{"url": "https://arxiv.org/abs/2401.01234v2"},
                       {"url": "https://arxiv.org/pdf/2401.01234v2.pdf"},
                       {"arxiv_id": "2401.01234v2"}]:
            with self.subTest(record=record):
                candidates = fulltext.candidate_pdf_urls(record)
                self.assertTrue(any(urlparse(url).hostname == "arxiv.org" and
                                    urlparse(url).path.rstrip("/").removesuffix(".pdf") == "/pdf/2401.01234v2"
                                    for url in candidates))

    def test_arxiv_metadata_version_pins_unversioned_landing_page(self):
        paper = {"url": "https://arxiv.org/abs/2401.01234",
                 "arxiv_id": "2401.01234", "version": "v2"}
        self.assertEqual(fulltext.candidate_pdf_urls(paper),
                         ["https://arxiv.org/pdf/2401.01234v2"])

    def test_pdf_candidates_are_deduplicated_and_unknown_hosts_are_not_guessed(self):
        record = {"url": PDF_URL, "pdf_url": PDF_URL,
                  "locations": [{"pdf_url": PDF_URL}]}
        candidates = fulltext.candidate_pdf_urls(record)
        self.assertEqual(candidates.count(PDF_URL), 1)
        self.assertEqual(fulltext.candidate_pdf_urls({"url": "https://example.org/paper/123"}), [])

    def test_url_policy_accepts_official_pdf_hosts(self):
        urls = [PDF_URL, "https://openreview.net/pdf?id=AbC123",
                "https://arxiv.org/pdf/2401.01234", "https://export.arxiv.org/pdf/2401.01234",
                "https://proceedings.mlr.press/v235/example24a/example24a.pdf",
                "https://proceedings.neurips.cc/paper_files/paper/2024/file/example-Paper-Conference.pdf",
                "https://ojs.aaai.org/index.php/AAAI/article/download/123/456",
                "https://www.ijcai.org/proceedings/2024/0010.pdf",
                "https://openaccess.thecvf.com/content/CVPR2024/papers/example.pdf"]
        for url in urls:
            with self.subTest(url=url):
                self.assertEqual(fulltext.validate_pdf_url(url), url)

    def test_url_policy_rejects_untrusted_authorities_and_schemes(self):
        urls = ["http://arxiv.org/pdf/2401.01234", "file:///tmp/paper.pdf",
                "https://127.0.0.1/paper.pdf", "https://[::1]/paper.pdf",
                "https://arxiv.org.attacker.example/paper.pdf", "https://evil-arxiv.org/paper.pdf",
                "https://user:password@arxiv.org/pdf/2401.01234",
                "https://arxiv.org:8443/pdf/2401.01234", "https://example.org/paper.pdf"]
        for url in urls:
            with self.subTest(url=url), self.assertRaises(ValueError):
                fulltext.validate_pdf_url(url)

    def test_success_preserves_identity_and_records_content_provenance(self):
        original = copy.deepcopy(self.paper)
        text = "Extracted first page.\fExtracted second page."
        with patch.object(fulltext, "_download_in_process", side_effect=self.download) as download, \
             patch.object(fulltext, "_extract_pdf", return_value=text):
            result = fulltext.fetch_full_text(self.paper, destination=self.root, timeout_s=8)
        self.assertEqual(self.paper, original)
        self.assertEqual(result["id"], original["id"])
        self.assertEqual(result["content_kind"], "full_text")
        self.assertEqual(result["text"], text)
        self.assertEqual(result["full_text_url"], PDF_URL)
        self.assertEqual(result["pdf_sha256"], hashlib.sha256(PDF_BYTES).hexdigest())
        self.assertEqual(result["content_sha256"], hashlib.sha256(text.encode()).hexdigest())
        self.assertEqual(download.call_count, 1)

    def test_no_official_pdf_candidate_retains_abstract_without_network(self):
        paper = dict(self.paper, url="https://example.org/article")
        original = copy.deepcopy(paper)
        with patch.object(fulltext, "_download_in_process") as download, \
             patch.object(fulltext, "_extract_pdf") as extract:
            result = fulltext.fetch_full_text(paper)
        self.assertEqual(paper, original)
        self.assert_preserved_failure(original, result)
        download.assert_not_called()
        extract.assert_not_called()

    def test_download_failure_is_sanitized_and_keeps_original_content(self):
        original = copy.deepcopy(self.paper)
        with patch.object(fulltext, "_download_in_process", side_effect=OSError("secret-token https://private.example/?key=secret-token")), \
             patch.object(fulltext, "_extract_pdf") as extract:
            result = fulltext.fetch_full_text(self.paper, destination=self.root)
        self.assertEqual(self.paper, original)
        self.assert_preserved_failure(original, result)
        self.assertNotIn("secret-token", str(result["full_text_error"]))
        self.assertNotIn("private.example", str(result["full_text_retrieval"]))
        extract.assert_not_called()

    def test_empty_extraction_does_not_promote_abstract_to_full_text(self):
        for extracted in ("", " \n\f\t"):
            with self.subTest(extracted=extracted), \
                 patch.object(fulltext, "_download_in_process", side_effect=self.download), \
                 patch.object(fulltext, "_extract_pdf", return_value=extracted):
                result = fulltext.fetch_full_text(self.paper, destination=self.root)
            self.assert_preserved_failure(self.paper, result)

    def test_extraction_failure_keeps_original_content_and_sanitizes_details(self):
        with patch.object(fulltext, "_download_in_process", side_effect=self.download), \
             patch.object(fulltext, "_extract_pdf", side_effect=OSError("secret-token in converter stderr")):
            result = fulltext.fetch_full_text(self.paper, destination=self.root)
        self.assert_preserved_failure(self.paper, result)
        self.assertNotIn("secret-token", str(result["full_text_error"]))

    def test_later_official_candidate_can_succeed_after_failed_download(self):
        alternate = "https://arxiv.org/pdf/2401.01234"
        def download(url, target, timeout_s):
            if url == PDF_URL:
                raise fulltext.FullTextError("first source unavailable")
            return self.download(url, target, timeout_s)
        with patch.object(fulltext, "candidate_pdf_urls", return_value=[PDF_URL, alternate]), \
             patch.object(fulltext, "_download_in_process", side_effect=download) as attempted, \
             patch.object(fulltext, "_extract_pdf", return_value="Actual extracted text"):
            result = fulltext.fetch_full_text(self.paper, destination=self.root)
        self.assertEqual(attempted.call_count, 2)
        self.assertEqual(result["content_kind"], "full_text")
        self.assertEqual(result["full_text_url"], alternate)

    def test_download_uses_get_and_hashes_actual_pdf_bytes(self):
        final_url = "https://arxiv.org/pdf/2401.01234"
        opener = Mock()
        opener.open.return_value = FakeResponse(PDF_BYTES, url=final_url)
        target = self.root / "paper.pdf"
        with patch.object(fulltext, "build_opener", return_value=opener):
            result = fulltext._download_pdf(PDF_URL, target, 4)
        request = opener.open.call_args.args[0]
        self.assertEqual(request.get_method(), "GET")
        self.assertIsNone(request.data)
        self.assertIsNone(request.get_header("Authorization"))
        self.assertEqual(target.read_bytes(), PDF_BYTES)
        self.assertEqual(result["final_url"], final_url)
        self.assertEqual(result["pdf_sha256"], hashlib.sha256(PDF_BYTES).hexdigest())

    def test_html_response_cannot_be_accepted_as_pdf(self):
        opener = Mock()
        opener.open.return_value = FakeResponse(b"<!doctype html><title>Access denied</title>",
                                                headers={"Content-Type": "application/pdf"})
        with patch.object(fulltext, "build_opener", return_value=opener), \
             self.assertRaises(fulltext.FullTextError):
            fulltext._download_pdf(PDF_URL, self.root / "not-a-pdf.pdf", 4)

    def test_download_size_is_bounded_with_and_without_content_length(self):
        self.assertEqual(fulltext.MAX_PDF_BYTES, 32 * 1024 * 1024)
        for headers in ({"Content-Length": "100000"}, {}):
            opener = Mock()
            opener.open.return_value = FakeResponse(b"%PDF-" + b"x" * 64, headers=headers)
            with self.subTest(headers=headers), \
                 patch.object(fulltext, "MAX_PDF_BYTES", 32), \
                 patch.object(fulltext, "build_opener", return_value=opener), \
                 self.assertRaises(fulltext.FullTextError):
                fulltext._download_pdf(PDF_URL, self.root / "oversized.pdf", 4)

    def test_http_error_details_are_not_exposed(self):
        opener = Mock()
        opener.open.side_effect = HTTPError(PDF_URL + "?key=secret-token", 403,
                                           "secret-token", {}, None)
        with patch.object(fulltext, "build_opener", return_value=opener), \
             self.assertRaises(fulltext.FullTextError) as caught:
            fulltext._download_pdf(PDF_URL, self.root / "paper.pdf", 4)
        self.assertIn("403", str(caught.exception))
        self.assertNotIn("secret-token", str(caught.exception))

    def test_declared_content_length_cannot_accept_a_truncated_pdf(self):
        opener = Mock()
        opener.open.return_value = FakeResponse(
            PDF_BYTES, headers={"Content-Length": str(len(PDF_BYTES) + 100)})
        with patch.object(fulltext, "build_opener", return_value=opener), \
             self.assertRaisesRegex(fulltext.FullTextError, "incomplete"):
            fulltext._download_pdf(PDF_URL, self.root / "truncated.pdf", 4)

    def test_download_worker_is_isolated_and_receives_json_over_stdin(self):
        target = self.root / "target with spaces.pdf"
        envelope = {"status": "completed", "final_url": PDF_URL,
                    "pdf_sha256": hashlib.sha256(PDF_BYTES).hexdigest()}
        with patch("research_idea.backends.common.run_cli", return_value=json.dumps(envelope)) as runner:
            result = fulltext._download_in_process(PDF_URL, target, 2.5)
        argv, prompt, cwd, timeout = runner.call_args.args
        self.assertEqual(argv[0], sys.executable)
        self.assertIn("-I", argv)
        self.assertEqual(argv[-1], "--download-worker")
        self.assertNotIn(PDF_URL, argv)
        self.assertEqual(json.loads(prompt)["url"], PDF_URL)
        self.assertEqual(json.loads(prompt)["target"], str(target.resolve()))
        self.assertEqual(cwd, target.parent)
        self.assertEqual(timeout, 2.5)
        self.assertEqual(result["final_url"], PDF_URL)

    def test_download_worker_timeout_is_sanitized(self):
        from research_idea.backend_types import BackendError
        with patch("research_idea.backends.common.run_cli", side_effect=BackendError("secret-token timeout")), \
             self.assertRaises(fulltext.FullTextError) as caught:
            fulltext._download_in_process(PDF_URL, self.root / "paper.pdf", 0.1)
        self.assertIn("timeout", str(caught.exception))
        self.assertNotIn("secret-token", str(caught.exception))

    def test_fetch_deadline_covers_download_and_prevents_late_extraction(self):
        def delayed_download(url, target, timeout_s):
            time.sleep(0.03)
            return self.download(url, target, timeout_s)
        with patch.object(fulltext, "_download_in_process", side_effect=delayed_download), \
             patch.object(fulltext, "_extract_pdf") as extract:
            result = fulltext.fetch_full_text(self.paper, destination=self.root, timeout_s=0.01)
        self.assert_preserved_failure(self.paper, result)
        self.assertIn("timeout", result["full_text_error"])
        extract.assert_not_called()

    def test_redirect_target_is_validated_before_following(self):
        redirect = fulltext._AllowedRedirect()
        request = Request(PDF_URL)
        for target in ("https://attacker.example/paper.pdf", "http://arxiv.org/pdf/2401.01234",
                       "https://arxiv.org.attacker.example/paper.pdf", "https://127.0.0.1/paper.pdf"):
            with self.subTest(target=target), self.assertRaises((ValueError, fulltext.FullTextError)):
                redirect.redirect_request(request, None, 302, "Found", {}, target)
        allowed = "https://arxiv.org/pdf/2401.01234"
        follow = redirect.redirect_request(request, None, 302, "Found", {}, allowed)
        self.assertEqual(follow.full_url, allowed)

    def test_pdftotext_uses_argv_and_preserves_page_boundaries(self):
        pdf, txt = self.root / "name; echo.pdf", self.root / "output text.txt"
        pdf.write_bytes(PDF_BYTES)
        extracted = "Page one.\fPage two."
        def convert(argv, prompt, cwd, timeout_s):
            self.assertIsInstance(argv, list)
            self.assertIn("pdftotext", Path(argv[0]).name)
            self.assertEqual(argv[-2:], [str(pdf), str(txt)])
            self.assertEqual(prompt, "")
            self.assertGreater(timeout_s, 0)
            self.assertLessEqual(timeout_s, 3)
            txt.write_text(extracted, encoding="utf-8")
            return ""
        with patch("research_idea.backends.common.run_cli", side_effect=convert) as converter, \
             patch("shutil.which", return_value="/usr/bin/pdftotext"):
            result = fulltext._extract_pdf(pdf, txt, 3)
        self.assertEqual(result, extracted)
        self.assertEqual(converter.call_count, 1)

    @unittest.skipUnless(shutil.which("pdftotext"), "Poppler is needed for the two-column regression")
    def test_two_column_paragraphs_remain_contiguous_for_quote_verification(self):
        from research_idea.controller import locate_quote
        from research_idea.literature import read_source
        stream = b'''BT /F1 11 Tf
1 0 0 1 40 720 Tm (A rule requires signal A.) Tj
1 0 0 1 40 704 Tm (Feedback identifies this rule.) Tj
1 0 0 1 340 720 Tm (Unrelated appendix sentence.) Tj
1 0 0 1 340 704 Tm (Extra text from another column.) Tj ET'''
        objects = [
            b'<< /Type /Catalog /Pages 2 0 R >>',
            b'<< /Type /Pages /Kids [3 0 R] /Count 1 >>',
            b'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] '
            b'/Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>',
            b'<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>',
            b'<< /Length ' + str(len(stream)).encode() + b' >>\nstream\n' + stream + b'\nendstream',
        ]
        data = bytearray(b'%PDF-1.4\n')
        offsets = [0]
        for index, obj in enumerate(objects, 1):
            offsets.append(len(data))
            data += f'{index} 0 obj\n'.encode() + obj + b'\nendobj\n'
        xref = len(data)
        data += b'xref\n0 6\n0000000000 65535 f \n'
        for offset in offsets[1:]:
            data += f'{offset:010d} 00000 n \n'.encode()
        data += f'trailer\n<< /Size 6 /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n'.encode()
        pdf, txt = self.root / 'two-columns.pdf', self.root / 'two-columns.txt'
        pdf.write_bytes(data)
        quote = 'A rule requires signal A. Feedback identifies this rule.'
        for text in [read_source(pdf)["text"], fulltext._extract_pdf(pdf, txt, 5)]:
            with self.subTest(text=text):
                start, end = locate_quote(text, quote)
                self.assertNotIn('appendix', text[start:end])
                self.assertIn('\f', text)

    def test_converter_failure_cannot_return_a_partial_text_file(self):
        from research_idea.backend_types import BackendError
        pdf, txt = self.root / "paper.pdf", self.root / "paper.txt"
        pdf.write_bytes(PDF_BYTES)
        txt.write_text("partial text that must not be accepted", encoding="utf-8")
        with patch("research_idea.backends.common.run_cli", side_effect=BackendError("secret-token task timeout")), \
             patch("shutil.which", return_value="/usr/bin/pdftotext"), \
             self.assertRaises(fulltext.FullTextError) as caught:
            fulltext._extract_pdf(pdf, txt, 0.1)
        self.assertNotIn("secret-token", str(caught.exception))

    def test_converter_success_without_output_cannot_reuse_stale_text(self):
        pdf, txt = self.root / "paper.pdf", self.root / "paper.txt"
        pdf.write_bytes(PDF_BYTES)
        txt.write_text("stale text from an earlier attempt", encoding="utf-8")
        with patch("research_idea.backends.common.run_cli", return_value=""), \
             patch("shutil.which", return_value="/usr/bin/pdftotext"), \
             self.assertRaises(fulltext.FullTextError):
            fulltext._extract_pdf(pdf, txt, 3)
        self.assertFalse(txt.exists())


if __name__ == "__main__":
    unittest.main()
