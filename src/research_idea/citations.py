"""Resolve internal evidence keys into readable paper links at display time."""
from __future__ import annotations

import re
from urllib.parse import quote, urlsplit, urlunsplit

EVIDENCE_ID = re.compile(r'(?<![A-Za-z0-9_])ev_[A-Za-z0-9_]+(?![A-Za-z0-9_])')
EVIDENCE_GROUP = re.compile(EVIDENCE_ID.pattern + r'(?:[ \t]*[、,，;；][ \t]*' + EVIDENCE_ID.pattern + r')*')
KINDS = {'reported_result': '论文报告的实验结果', 'author_claim': '作者主张',
         'author_limitation': '作者说明的局限', 'method_detail': '方法细节'}


def web_url(value):
    if not isinstance(value, str) or any(ord(c) < 32 for c in value):
        return ''
    try:
        parsed = urlsplit(value)
        if parsed.scheme not in {'http', 'https'} or not parsed.hostname or parsed.username or parsed.password:
            return ''
    except ValueError:
        return ''
    return quote(value, safe=':/?#&=%+@,;~!$*\'_-')


def label(value):
    text = ' '.join(str(value).split())
    return text.replace('\\', '\\\\').replace('[', '\\[').replace(']', '\\]').replace('|', '\\|').replace('<', '&lt;').replace('>', '&gt;')


class Citations:
    def __init__(self, papers=(), evidence=()):
        self.papers = {p['id']: p for p in papers}
        self.evidence = {e['id']: e for e in evidence}

    @classmethod
    def from_store(cls, store):
        return cls(store.rows('papers'), store.rows('evidence'))

    def paper(self, paper_id):
        paper = self.papers.get(paper_id, {})
        title = label(paper.get('title') or '论文来源')
        url = web_url(paper.get('url')) or web_url(paper.get('full_text_url')) or web_url(paper.get('pdf_url'))
        if not url and paper.get('doi'):
            doi = re.sub(r'^(?:https?://(?:dx\.)?doi\.org/|doi:)', '', str(paper['doi']), flags=re.I)
            if re.fullmatch(r'10\.\d{4,9}/\S+', doi):
                url = web_url('https://doi.org/' + doi)
        return f'[{title}]({url})' if url else title + '（本地资料）'

    def location(self, evidence):
        paper = self.papers.get(evidence.get('paper_id'), {})
        page, line = evidence.get('page'), evidence.get('line')
        parts = []
        if isinstance(page, int) and page > 0:
            text = f'第 {page} 页'
            # Link the PDF actually read, including its pinned preprint version.
            url = web_url(paper.get('full_text_url'))
            if url:
                parsed = urlsplit(url)
                url = urlunsplit(parsed._replace(fragment=f'page={page}'))
                text = f'[{text}]({url})'
            parts.append(text)
        if isinstance(line, int) and line > 0:
            parts.append(f'第 {line} 行')
        if not parts:
            parts.append('原文摘录')
        return ' · '.join(parts)

    def reference(self, evidence_id):
        evidence = self.evidence.get(evidence_id)
        if evidence is None:
            return '原文来源未找到'
        return self.paper(evidence['paper_id']) + ' · ' + self.location(evidence)

    def text(self, text, *, compact=False):
        # Models sometimes format keys as inline code; remove that wrapper so
        # the resulting paper link remains clickable in Markdown reports.
        text = re.sub(r'`(' + EVIDENCE_ID.pattern + r')`', r'\1', str(text))
        if compact:
            def papers_for_group(match):
                papers = {}
                for evidence_id in EVIDENCE_ID.findall(match[0]):
                    evidence = self.evidence.get(evidence_id)
                    paper_id = evidence.get('paper_id') if evidence else None
                    papers.setdefault(paper_id, self.paper(paper_id) if evidence else '原文来源未找到')
                return '、'.join(papers.values())
            return EVIDENCE_GROUP.sub(papers_for_group, text)
        return EVIDENCE_ID.sub(lambda match: self.reference(match[0]), text)

    def block(self, evidence, *, markdown=False):
        lines = [self.paper(evidence['paper_id']), '', '支持的判断：' + evidence.get('statement', ''), '',
                 '原文位置：' + self.location(evidence)]
        paper = self.papers.get(evidence['paper_id'], {})
        origin = paper.get('full_text_origin') or {}
        if origin.get('version'):
            lines.append('实际阅读版本：arXiv ' + origin['version'])
        excerpt = evidence.get('quote', '')
        lines.extend(['', '> ' + excerpt.replace('\n', '\n> ') if markdown else '原文：' + excerpt])
        if evidence.get('conditions'):
            lines.extend(['', '成立条件：' + evidence['conditions']])
        if evidence.get('kind') in KINDS:
            lines.extend(['', '依据类型：' + KINDS[evidence['kind']]])
        return '\n'.join(lines)
