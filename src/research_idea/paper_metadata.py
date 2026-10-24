"""Bounded abstract enrichment before selecting papers for full-text reading."""
from __future__ import annotations

from copy import deepcopy
import re
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, build_opener

from .literature import LiteratureError, _SameHostRedirect, _remaining
from .proceedings import Document

MAX_PAGES = 6
TOTAL_SECONDS = 12
PAGE_SECONDS = 4
MAX_HTML_BYTES = 1024 * 1024


def venue_label(paper):
    """Conference identity is independent of where a PDF is hosted."""
    venue = paper.get('venue')
    verified = (paper.get('source') in {'official_proceedings', 'openreview'}
                or paper.get('venue_evidence') or paper.get('venue_id')
                or (paper.get('conference_url') and paper.get('edition_basis')))
    if venue and verified:
        year = paper.get('conference_year') or paper.get('year')
        return f"{venue} {year}" if year else str(venue)
    return 'arXiv 预印本' if paper.get('source') == 'arxiv' and not venue else ''


def paper_heading(paper):
    label = venue_label(paper)
    if not label:
        label = paper.get('publication_date') or paper.get('year') or ''
    return paper.get('title', '') + (f' · {label}' if label else '')


def _landing_page(paper):
    if paper.get('source') != 'official_proceedings' or paper.get('abstract'):
        return None
    url = paper.get('url', '')
    parsed = urlparse(url)
    if (parsed.scheme != 'https' or parsed.username or parsed.password
            or parsed.port not in {None, 443} or parsed.fragment):
        return None
    # These are single-paper HTML pages, never index pages or PDF links.
    patterns = {
        'proceedings.mlr.press': r'/v\d+/[^/]+\.html',
        'iclr.cc': r'/virtual/\d{4}/poster/\d+/?',
        'aclanthology.org': r'/\d{4}\.[a-z-]+\.\d+/?',
        'papers.nips.cc': r'/paper_files/paper/\d{4}/hash/[^/]+-Abstract[^/]*\.html',
    }
    pattern = patterns.get(parsed.hostname)
    return url if pattern and re.fullmatch(pattern, parsed.path) else None


def _fetch_html(url, timeout_s):
    """Read a small HTML response; reject a PDF before reading its body."""
    deadline = time.monotonic() + timeout_s
    request = Request(url, headers={'User-Agent': 'research-idea/0.3', 'Accept': 'text/html,application/xhtml+xml'})
    try:
        with build_opener(_SameHostRedirect()).open(request, timeout=timeout_s) as response:
            mime = response.headers.get_content_type()
            if mime not in {'text/html', 'application/xhtml+xml'}:
                raise LiteratureError('Paper landing page did not return HTML')
            pieces, size = [], 0
            read = getattr(response, 'read1', response.read)
            while size <= MAX_HTML_BYTES:
                remaining = _remaining(deadline)
                sock = getattr(getattr(getattr(response, 'fp', None), 'raw', None), '_sock', None)
                if sock is not None:
                    sock.settimeout(remaining)
                piece = read(min(32768, MAX_HTML_BYTES + 1 - size))
                _remaining(deadline)
                if not piece:
                    break
                size += len(piece)
                pieces.append(piece)
            if size > MAX_HTML_BYTES:
                raise LiteratureError('Paper landing page exceeds the metadata size limit')
            encoding = response.headers.get_content_charset() or 'utf-8'
            return b''.join(pieces).decode(encoding, errors='replace')
    except HTTPError as exc:
        status = exc.code
        exc.close()
        raise LiteratureError(f'Paper landing page returned HTTP {status}') from None
    except (URLError, TimeoutError, OSError, LookupError):
        raise LiteratureError('Paper landing page could not be read within its time budget') from None


def _abstract(html, paper):
    nodes = list(Document(html).root.walk())
    text = ''
    for node in nodes:
        classes = node.attrs.get('class', '').split()
        if node.attrs.get('id') in {'abstract', 'abstractText'} or 'acl-abstract' in classes:
            text = node.text()
            if text.strip():
                break
    if not text:
        for parent in nodes:
            children = [child for child in parent.children if hasattr(child, 'tag')]
            for index, child in enumerate(children[:-1]):
                if (child.tag in {'h2', 'h3', 'h4'} and child.text().strip().lower() == 'abstract'
                        and children[index + 1].tag in {'p', 'div'}):
                    text = children[index + 1].text()
                    break
            if text:
                break
    metadata = {str(n.attrs.get('name') or n.attrs.get('property') or '').lower(): n.attrs.get('content') or ''
                for n in nodes if n.tag == 'meta'}
    if not text:
        text = metadata.get('citation_abstract', '') or metadata.get('dc.description', '')
    if not text:
        # Generic site descriptions are not paper abstracts. Use them only when
        # the same page identifies this exact paper in its title metadata.
        clean = lambda value: re.sub(r'[^\w]', '', value.casefold())
        titles = [metadata.get('citation_title', ''), metadata.get('og:title', '')]
        if clean(paper['title']) in {clean(title) for title in titles if title}:
            text = metadata.get('description', '') or metadata.get('og:description', '')
    text = re.sub(r'^\s*Abstract\s*[:\n]?\s*', '', text, flags=re.I)
    return ' '.join(text.split())[:12000]


def enrich_screening_pool(papers, *, max_pages=MAX_PAGES, timeout_s=TOTAL_SECONDS):
    """Enrich the ranked prefix without changing identities or downloading PDFs.

    The caller decides the candidate pool. Missing pages simply leave their
    records title-only; a venue is never given a mandatory reading quota.
    """
    result = deepcopy(papers)
    audit = {'attempted': 0, 'enriched': 0, 'pages': [], 'max_pages': max_pages,
             'timeout_s': timeout_s}
    deadline = time.monotonic() + max(0, timeout_s)
    for paper in result:
        if audit['attempted'] >= max_pages or time.monotonic() >= deadline:
            break
        try:
            url = _landing_page(paper)
        except ValueError:
            url = None
        if not url:
            continue
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        audit['attempted'] += 1
        attempt = {'paper_id': paper['id'], 'url': url}
        audit['pages'].append(attempt)
        try:
            abstract = _abstract(_fetch_html(url, min(PAGE_SECONDS, remaining)), paper)
            if abstract:
                paper.update(abstract=abstract, abstract_source=url)
                attempt['status'] = 'enriched'
                audit['enriched'] += 1
            else:
                attempt['status'] = 'no_abstract'
        except LiteratureError:
            attempt['status'] = 'unavailable'
    return result, audit
