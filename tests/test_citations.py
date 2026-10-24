"""Readable references preserve the original source and machine evidence."""
import copy
import json
from pathlib import Path
import tempfile
import unittest

from research_idea.citations import Citations
from research_idea.report import export_report
from research_idea.store import Store


class CitationTests(unittest.TestCase):
    def setUp(self):
        self.paper = {'id': 'p1', 'title': 'An agent study', 'url': 'https://example.org/paper',
                      'full_text_url': 'https://arxiv.org/pdf/2501.12345v2',
                      'full_text_origin': {'version': 'v2'}, 'content_kind': 'notes'}
        self.evidence = {'id': 'ev_123', 'paper_id': 'p1', 'statement': 'An attributed observation.',
                         'quote': 'The original source text remains exact.', 'page': 4, 'line': 86,
                         'kind': 'author_claim', 'conditions': 'Under these conditions.',
                         'source_kind': 'notes', 'reading_coverage': 'provided_text'}

    def test_reference_has_paper_title_landing_link_and_exact_body_version(self):
        before = copy.deepcopy(self.evidence)
        citations = Citations([self.paper], [self.evidence])
        rendered = citations.text('根据 ev_123，可提出一个待检验假设。')
        self.assertIn('[An agent study](https://example.org/paper)', rendered)
        self.assertIn('https://arxiv.org/pdf/2501.12345v2#page=4', rendered)
        self.assertIn('第 86 行', rendered)
        self.assertNotIn('ev_123', rendered)
        self.assertEqual(citations.text('依据ev_123说明。'), '依据' + citations.reference('ev_123') + '说明。')
        self.assertEqual(citations.text('`ev_123`'), citations.reference('ev_123'))
        block = citations.block(self.evidence)
        self.assertIn(self.evidence['quote'], block)
        self.assertIn('实际阅读版本：arXiv v2', block)
        self.assertEqual(self.evidence, before)

    def test_local_unknown_and_unusable_urls_never_get_invented_links(self):
        citations = Citations([dict(self.paper, url='javascript:alert(1)', full_text_url='', title='Local notes')], [self.evidence])
        self.assertEqual(citations.paper('p1'), 'Local notes（本地资料）')
        self.assertNotIn('http', citations.reference('ev_123'))
        self.assertEqual(citations.text('ev_missing'), '原文来源未找到')

    def test_readable_reports_link_inline_evidence_without_changing_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = Store(Path(tmp))
            try:
                store.set('topic', 'A test research topic')
                store.put('papers', self.paper)
                store.replace_evidence('p1', [self.evidence])
                candidate = {'id': 'idea_1', 'proposal': {'title': 'A hypothesis', 'problem': 'Observed in ev_123.',
                              'closest_work_ids': ['p1']}, 'spec': {}}
                store.put('candidates', candidate)
                report, data = export_report(store)
                text = report.read_text()
                self.assertNotIn('ev_123', text)
                self.assertIn('[An agent study](https://example.org/paper)', text)
                self.assertIn(self.evidence['quote'], text)
                self.assertIn('https://arxiv.org/pdf/2501.12345v2#page=4', text)
                saved = json.loads(data.read_text())
                self.assertEqual(saved['evidence'], [self.evidence])
                self.assertEqual(saved['candidates'], [candidate])
                detail = (Path(tmp) / 'outputs/idea_1.md').read_text()
                self.assertNotIn('ev_123', detail)
            finally:
                store.close()


if __name__ == '__main__':
    unittest.main()
