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

    def test_compact_citations_merge_adjacent_sources_but_preserve_claim_links(self):
        second = dict(self.evidence, id='ev_456', page=6, line=102)
        other = dict(self.paper, id='p2', title='Another paper', url='https://example.org/another')
        third = dict(self.evidence, id='ev_789', paper_id='p2')
        citations = Citations([self.paper, other], [self.evidence, second, third])
        source = 'First claim (`ev_123`、ev_456, ev_789). Another claim ev_456.'
        compact = citations.text(source, compact=True)
        self.assertEqual(compact, 'First claim (' + citations.paper('p1') + '、' + citations.paper('p2') +
                         '). Another claim ' + citations.paper('p1') + '.')
        self.assertNotIn('第 4 页', compact)
        detailed = citations.text(source)
        self.assertIn('#page=4', detailed)
        self.assertIn('#page=6', detailed)
        self.assertEqual(citations.text('ev_missing', compact=True), '原文来源未找到')
        self.assertEqual(second['page'], 6)

    def test_cli_design_findings_and_details_name_the_paper_without_internal_ids(self):
        from research_idea.presentation import activity_summary
        from research_idea.chat_worker import outline
        from research_idea.chat import fragments
        citations = Citations([self.paper], [self.evidence])
        result = {'paper_id': 'p1', 'options': [{'question': '如何更新状态？',
            'source_technique': '从可见观察更新状态。', 'shared_structure': '两者都需要保留未决解释。',
            'source_conditions': '只使用当前观察。', 'adaptation': '把来源状态换成环境规则。',
            'why_it_helps': '将新观察与旧规则比较。', 'simpler_alternative': '每次重新推断。',
            'first_test': '比较规则改变后的第一次决策。', 'evidence_ids': ['ev_123']}], 'reading_gaps': []}
        summary = activity_summary('design_transfer', result, citations)
        detail = '\n'.join(outline(result, citations=citations))
        for text in (summary, detail):
            self.assertIn('[An agent study](https://example.org/paper)', text)
            self.assertNotIn('ev_123', text)
            self.assertNotIn('p1', text)
        styled = fragments('design', summary)
        self.assertTrue(any('bold' in style and '可借鉴的技术' in text for style, text in styled))
        self.assertNotIn('**', ''.join(text for _, text in styled))
        self.assertEqual(result['options'][0]['evidence_ids'], ['ev_123'])

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
                report, data = export_report(store, store.project)
                text = report.read_text()
                self.assertNotIn('ev_123', text)
                self.assertIn('[An agent study](https://example.org/paper)', text)
                self.assertIn(self.evidence['quote'], text)
                self.assertIn('https://arxiv.org/pdf/2501.12345v2#page=4', text)
                saved = json.loads(data.read_text())
                self.assertEqual(saved['evidence'], [self.evidence])
                self.assertEqual(saved['candidates'], [candidate])
                detail = (report.parent / 'idea_1.md').read_text()
                self.assertNotIn('ev_123', detail)
            finally:
                store.close()


if __name__ == '__main__':
    unittest.main()
