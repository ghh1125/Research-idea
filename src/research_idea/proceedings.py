"""Official, public conference indexes when a metadata API is unavailable.

No PDF downloads here. Venue provenance comes from a main-proceedings index;
titles select reading targets and never establish contribution overlap.
"""
from __future__ import annotations

from datetime import date, datetime
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse
import re
import time

from .selection import rank_metadata


class Node:
    def __init__(self, tag='', attrs=()):
        self.tag, self.attrs, self.children = tag, dict(attrs), []

    def text(self):
        return ''.join(child.text() if isinstance(child, Node) else child for child in self.children)

    def walk(self):
        yield self
        for child in self.children:
            if isinstance(child, Node):
                yield from child.walk()


class Document(HTMLParser):
    def __init__(self, html):
        super().__init__(convert_charrefs=True)
        self.root = Node()
        self.stack = [self.root]
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        node = Node(tag, attrs)
        self.stack[-1].children.append(node)
        if tag not in {'area', 'base', 'br', 'col', 'embed', 'hr', 'img', 'input', 'link', 'meta', 'param', 'source', 'track', 'wbr'}:
            if len(self.stack) < 100:
                self.stack.append(node)

    def handle_startendtag(self, tag, attrs):
        self.stack[-1].children.append(Node(tag, attrs))

    def handle_endtag(self, tag):
        for index in range(len(self.stack) - 1, 0, -1):
            if self.stack[index].tag == tag:
                del self.stack[index:]
                break

    def handle_data(self, data):
        self.stack[-1].children.append(data)


def parse_index(html, url, venue, year):
    from .literature import normalize_paper
    nodes = list(Document(html).root.walk())
    title = next((n.text() for n in nodes if n.tag == 'title'), '')
    month = ''
    records = []
    if venue in {'ACL', 'EMNLP', 'NAACL'}:
        series = {'ACL': 'acl-long', 'EMNLP': 'emnlp-main', 'NAACL': 'naacl-long'}[venue]
        if f'{year}.{series}' not in html:
            return []
        for i, node in enumerate(nodes[:-1]):
            if node.tag == 'dt' and node.text().strip() == 'Month:' and nodes[i + 1].tag == 'dd':
                try:
                    month = datetime.strptime(nodes[i + 1].text().strip(), '%B').strftime('%m')
                except ValueError:
                    pass
        abstracts = {n.attrs.get('id'): n.text().strip() for n in nodes if n.tag == 'div' and n.attrs.get('id', '').startswith('abstract-')}
        for node in nodes:
            if node.tag != 'a':
                continue
            href = urljoin(url, node.attrs.get('href', ''))
            match = re.fullmatch(rf'/{year}\.{series}\.(\d+)/', urlparse(href).path)
            if urlparse(href).hostname != 'aclanthology.org' or not match or node.text().strip() in {'pdf', 'bib', 'abs'}:
                continue
            number = match[1]
            if number == '0':
                continue
            records.append({'id': href, 'url': href, 'title': node.text(),
                'abstract': abstracts.get(f'abstract-{year}--{series}--{number}', ''), 'pdf_url': href.rstrip('/') + '.pdf'})
    elif venue == 'ICML':
        if 'International Conference on Machine Learning' not in title:
            return []
        for node in nodes:
            if node.tag != 'div' or 'paper' not in node.attrs.get('class', '').split():
                continue
            contents = list(node.walk())
            name = next((n.text() for n in contents if 'title' in n.attrs.get('class', '').split()), '')
            href = next((urljoin(url, n.attrs['href']) for n in contents if n.tag == 'a' and n.text().strip() == 'abs'), '')
            pdf = next((urljoin(url, n.attrs['href']) for n in contents if n.tag == 'a' and n.text().strip() == 'Download PDF'), '')
            if name and href and urlparse(href).hostname == 'proceedings.mlr.press':
                # PMLR sometimes links GitHub mirrors; its own PDF path is also
                # a public official distribution and works with the downloader.
                if urlparse(pdf).hostname == 'raw.githubusercontent.com':
                    slug = urlparse(href).path.rsplit('/', 1)[-1].removesuffix('.html')
                    pdf = urljoin(url, slug + '/' + slug + '.pdf')
                records.append({'id': href, 'url': href, 'title': name, 'pdf_url': pdf})
    elif venue == 'NeurIPS':
        if 'Main Conference' not in html and ('Creative AI' in html or 'Datasets and Benchmarks' in title):
            return []
        for node in nodes:
            href = urljoin(url, node.attrs.get('href', ''))
            if (node.tag == 'a' and node.attrs.get('title') == 'paper title'
                    and urlparse(href).hostname == 'papers.nips.cc'
                    and re.search(r'/hash/[a-f0-9]+-Abstract(?:-Conference)?\.html$', urlparse(href).path)):
                records.append({'id': href, 'url': href, 'title': node.text(),
                    'pdf_url': href.replace('/hash/', '/file/').replace('-Abstract', '-Paper').replace('.html', '.pdf')})
    elif venue == 'ICLR':
        if f'ICLR {year}' not in html and 'ICLR Papers' not in html:
            return []
        for node in nodes:
            href = urljoin(url, node.attrs.get('href', ''))
            if node.tag == 'a' and urlparse(href).hostname == 'iclr.cc' and re.fullmatch(rf'/virtual/{year}/poster/\d+', urlparse(href).path):
                name = node.text().strip()
                if name:
                    records.append({'id': href, 'url': href, 'title': name})
    elif venue == 'COLM':
        if f'COLM {year} Accepted Papers' not in html:
            return []
        for node in nodes:
            if node.tag != 'tr':
                continue
            name = next((n.text().strip() for n in node.walk() if n.tag == 'strong'), '')
            if name:
                # This official list has no per-paper links. Keep its provenance
                # and title without inventing an OpenReview ID or a PDF address.
                records.append({'title': name, 'url': url, 'abstract': ''})
    result = []
    precise = re.search(r'on (\d{2} [A-Z][a-z]+ \d{4})\.', title) if venue == 'ICML' else None
    for record in records:
        record.update(year=year, venue=venue, source='official_proceedings', content_kind='abstract',
                      venue_evidence=url, venue_name=venue, publication_date_precision='month' if month else 'year',
                      publication_period=f'{year}-{month}' if month else str(year))
        if precise:
            record['publication_date'] = datetime.strptime(precise[1], '%d %B %Y').date().isoformat()
            record['publication_date_precision'] = 'day'
        result.append(normalize_paper(record))
    return result


def discover_proceedings(query, venues, limit, deadline, scope, coverage):
    from .literature import _request_bytes, _remaining, LiteratureError, deduplicate
    from .search_scope import exclusion_reason
    records, attempts = [], []
    end_year = int((scope['until'] or date.today().isoformat())[:4])
    start_year = int((scope['since'] or str(end_year - 1))[:4])
    # A fallback is bounded too: recent two editions per venue, not an archive crawl.
    years = list(range(end_year, max(start_year, end_year - 1) - 1, -1))
    supported = {'ACL', 'EMNLP', 'NAACL', 'ICML', 'NeurIPS', 'ICLR', 'COLM'}
    requested = [v for v in venues if v in supported]
    coverage['official_proceedings'] = attempts
    for venue in requested:
        venue_deadline = min(deadline, time.monotonic() + _remaining(deadline) / max(1, len(requested) - requested.index(venue)))
        for year in years:
            if time.monotonic() >= venue_deadline:
                break
            if venue in {'ACL', 'EMNLP', 'NAACL'}:
                series = {'ACL': 'acl-long', 'EMNLP': 'emnlp-main', 'NAACL': 'naacl-long'}[venue]
                urls = [f'https://aclanthology.org/{year}.{series}/']
            elif venue == 'ICLR':
                urls = [f'https://iclr.cc/virtual/{year}/papers.html']
            elif venue == 'COLM':
                urls = [f'https://colm.cc/Conferences/{year}/AcceptedPapers']
            elif venue == 'NeurIPS':
                urls = [f'https://papers.nips.cc/paper_files/paper/{year}/vol{year - 1987}-main-conference']
            else:
                try:
                    index = _request_bytes('https://proceedings.mlr.press/', min(10, _remaining(venue_deadline))).decode('utf-8')
                    urls = []
                    for node in Document(index).root.walk():
                        if node.tag != 'li' or not re.search(rf'Proceedings of ICML {year}\b', node.text()):
                            continue
                        for link in node.walk():
                            href = urljoin('https://proceedings.mlr.press/', link.attrs.get('href', ''))
                            if link.tag == 'a' and re.fullmatch(r'/v\d+/?', urlparse(href).path) and urlparse(href).hostname == 'proceedings.mlr.press':
                                urls.append(href.rstrip('/') + '/')
                    urls = list(dict.fromkeys(urls))[:2]
                except LiteratureError as exc:
                    coverage['gaps'].append(f'ICML official index: {exc}')
                    break
            for url in urls:
                entry = {'venue': venue, 'year': year, 'url': url}
                attempts.append(entry)
                try:
                    html = _request_bytes(url, min(15, _remaining(venue_deadline))).decode('utf-8')
                    papers = parse_index(html, url, venue, year)
                    entry.update(status='completed', indexed=len(papers))
                    eligible = [p for p in papers if exclusion_reason(p, scope, 'official_proceedings', verified_venue=True) is None]
                    records.extend(rank_metadata(eligible, [query])[:limit * 2])
                except (LiteratureError, UnicodeError) as exc:
                    entry.update(status='failed', error=str(exc))
    for venue in venues:
        if venue not in supported:
            coverage['gaps'].append(f'{venue}: no official-index fallback adapter; index coverage remains incomplete')
    # Some official volumes publish a month/year only. Preserve that precision.
    from .search_scope import exclusion_reason
    records = [p for p in records if exclusion_reason(p, scope, 'official_proceedings', verified_venue=True) is None]
    ranked = rank_metadata(deduplicate(records), [query])
    return [p for venue in requested for p in [r for r in ranked if r['venue'] == venue and r['selection']['relevance'] > 0][:limit]]


def enrich_selected(paper, timeout_s=15):
    """Resolve body links only for selected records, never for the entire index."""
    from .literature import _request_bytes, discover, deduplicate, LiteratureError
    if paper.get('source') != 'official_proceedings' or paper.get('pdf_url'):
        return paper
    if paper.get('venue') == 'ICLR':
        html = _request_bytes(paper['url'], timeout_s).decode('utf-8')
        nodes = list(Document(html).root.walk())
        abstract = next((n.text().strip() for n in nodes if n.attrs.get('id') == 'abstractText'), '')
        link = next((n.attrs.get('href', '') for n in nodes if n.tag == 'a' and n.attrs.get('href', '').startswith('https://openreview.net/forum?id=')), '')
        if link:
            return dict(paper, abstract=abstract, pdf_url=link.replace('/forum?', '/pdf?'),
                        locations=[{'landing_page_url': link}])
    if paper.get('venue') == 'COLM':
        matched = match_preprint(paper, timeout_s)
        if matched:
            return matched
        raise LiteratureError('COLM accepted title has no exact-title preprint match in the bounded lookup')
    return paper


def match_preprint(paper, timeout_s=15):
    """Attach a public preprint only after exact normalized title matching.

    Conference metadata stays intact; the body can be an earlier arXiv version.
    Its identity and version are recorded separately for downstream comparison.
    """
    from .literature import discover
    clean = lambda value: re.sub(r'[^\w]', '', value.casefold())
    title = paper['title'].replace('"', '')
    found = discover('ti:"' + title + '"', source='arxiv', limit=3, timeout_s=timeout_s)
    for match in found:
        if clean(match['title']) != clean(paper['title']):
            continue
        authors = {clean(a) for a in paper.get('authors', [])}
        matched_authors = {clean(a) for a in match.get('authors', [])}
        if authors and matched_authors and not authors.intersection(matched_authors):
            continue
        return dict(paper, abstract=paper.get('abstract') or match.get('abstract', ''),
            pdf_url=match.get('pdf_url'), arxiv_id=match.get('arxiv_id'),
            version=match.get('version'),
            aliases=sorted(set(paper.get('aliases', [paper['id']]) + match.get('aliases', [match['id']]))),
            locations=paper.get('locations', []) + [{'landing_page_url': match['url']}],
            full_text_origin={'kind': 'arxiv_preprint', 'url': match['url'],
                'version': match.get('version'), 'publication_date': match.get('publication_date'),
                'match': 'normalized_exact_title'})
    return None
