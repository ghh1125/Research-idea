"""Bounded venue-aware discovery, official PDF retrieval and local ingestion.

All returned text is untrusted source material, never execution instructions.
Discovery supplies abstracts; fetch_full_text is a separate operation. Text/Markdown are
classified as notes unless the importing caller supplies stronger provenance.
"""
from __future__ import annotations

import hashlib
from datetime import date
import json
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import threading
import time
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import unquote, urlencode, urlparse
from urllib.request import HTTPRedirectHandler, Request, build_opener
import xml.etree.ElementTree as ET

from .venues import SOURCE_QUERIES, VENUES, canonical_venue, normalize_venues, supported_venues

MAX_RESPONSE_BYTES = 8 * 1024 * 1024
MAX_SOURCE_BYTES = 32 * 1024 * 1024
ARXIV_ENDPOINT = "https://export.arxiv.org/api/query"
OPENALEX_ENDPOINT = "https://api.openalex.org/works"
OPENALEX_SOURCES_ENDPOINT = "https://api.openalex.org/sources"
OPENREVIEW_ENDPOINT = "https://api2.openreview.net/notes"
OPENREVIEW_PAGE_SIZE = 200
OPENREVIEW_MAX_PAGES = 3
_arxiv_lock = threading.Lock()
_last_arxiv_request = 0.0
_ARXIV_RE = re.compile(r"^(\d{4}\.\d{4,5}|[a-z][a-z.\-]+/\d{7})(v\d+)?$", re.I)


class LiteratureError(RuntimeError):
    """A source could not be retrieved, decoded, or normalized."""


class DiscoveryResults(list):
    """List-compatible results with coverage even when no paper was found."""

    def __init__(self, papers=(), *, coverage: dict | None = None):
        super().__init__(papers)
        self.coverage = coverage or {}


def _clean(value: Any) -> str:
    return " ".join(str(value or "").split())


def _doi(value: Any) -> str | None:
    value = unquote(str(value or "")).strip()
    value = re.sub(r"^(?:https?://(?:dx\.)?doi\.org/|doi:\s*)", "", value, flags=re.I)
    return value.lower() if re.fullmatch(r"10\.\d{4,9}/\S+", value, re.I) else None


def _arxiv(value: Any) -> tuple[str, str | None] | None:
    value = unquote(str(value or "")).strip()
    if value.startswith(("http://", "https://")):
        parsed = urlparse(value)
        if parsed.hostname not in {"arxiv.org", "www.arxiv.org", "export.arxiv.org"}:
            return None
        value = re.sub(r"^/(?:abs|pdf|html)/", "", parsed.path)
    value = re.sub(r"^arxiv:\s*", "", value, flags=re.I)
    value = re.sub(r"\.pdf$", "", value, flags=re.I)
    match = _ARXIV_RE.fullmatch(value)
    return (match[1].lower(), match[2]) if match else None


def normalize_paper(record: dict[str, Any]) -> dict[str, Any]:
    """Normalize metadata without upgrading an abstract into full-text evidence.

    Unknown caller-supplied IDs are retained (useful for local fixture citations).
    Canonical identifiers and ``aliases`` permit cross-provider deduplication.
    """
    if not isinstance(record, dict):
        raise LiteratureError("Paper metadata must be an object")
    title = _clean(record.get("title") or record.get("display_name"))
    if not title:
        raise LiteratureError("Paper metadata requires a non-empty title")
    doi = _doi(record.get("doi"))
    arxiv_doi = doi.removeprefix("10.48550/arxiv.") if doi and doi.startswith("10.48550/arxiv.") else None
    arxiv = next((a for value in (record.get("arxiv_id"), record.get("id"), record.get("url"), arxiv_doi)
                  if (a := _arxiv(value))), None)
    raw_id = _clean(record.get("id"))
    if not doi:
        doi = _doi(raw_id)
    aliases = {str(a) for a in record.get("aliases", []) if isinstance(a, str)}
    if raw_id:
        aliases.add(raw_id)
    if doi:
        aliases.add("doi:" + doi)
    if arxiv:
        aliases.add("arxiv:" + arxiv[0])
    if doi:
        paper_id = "doi:" + doi
    elif arxiv:
        paper_id = "arxiv:" + arxiv[0]
    elif raw_id:
        paper_id = raw_id
    else:
        digest = hashlib.sha256((title + "\n" + str(record.get("text") or record.get("abstract") or "")).encode()).hexdigest()[:20]
        paper_id = "local:" + digest
    authors = record.get("authors", []) or []
    if isinstance(authors, str):
        authors = [authors]
    if not isinstance(authors, list):
        raise LiteratureError("Paper authors must be a list or string")
    authors = [_clean(a.get("name") or a.get("display_name")) if isinstance(a, dict)
               else _clean(a) for a in authors]
    year = record.get("year", record.get("publication_year"))
    try:
        year = int(year) if year is not None and not isinstance(year, bool) else None
    except (TypeError, ValueError):
        year = None
    if year is not None and not 1000 <= year <= 9999:
        year = None
    kind = record.get("content_kind") or ("notes" if record.get("text") else "abstract")
    if kind not in {"full_text", "abstract", "notes"}:
        raise LiteratureError("content_kind must be full_text, abstract, or notes")
    result = dict(record)
    result.update({"id": paper_id, "title": title, "authors": [a for a in authors if a],
                   "year": year, "url": str(record.get("url") or ""), "doi": doi,
                   "abstract": _clean(record.get("abstract")), "source": str(record.get("source") or "local"),
                   "version": record.get("version") or (arxiv[1] if arxiv else None),
                   "aliases": sorted(aliases | {paper_id}), "content_kind": kind})
    if arxiv:
        result["arxiv_id"] = arxiv[0]
    return result


def deduplicate(papers: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Merge matching DOI/arXiv/explicit IDs; preserve versions and provenance.

    Similar titles alone do not establish identity. Prefer fuller content, then
    a newer arXiv version; never replace full text with an abstract.
    """
    groups: list[dict[str, Any]] = []
    rank = {"abstract": 0, "notes": 1, "full_text": 2}
    for source in papers:
        paper = normalize_paper(source)
        aliases = set(paper["aliases"])
        matches = [i for i, known in enumerate(groups) if aliases.intersection(known["aliases"])]
        candidates = [paper] + [groups[i] for i in matches]
        def priority(p: dict[str, Any]) -> tuple[int, int, int]:
            v = re.fullmatch(r"v(\d+)", str(p.get("version") or ""))
            return rank[p["content_kind"]], int(v[1]) if v else 0, len(p.get("text") or p.get("abstract") or "")
        merged = dict(max(candidates, key=priority))
        merged["aliases"] = sorted({a for p in candidates for a in p["aliases"]})
        merged["sources"] = sorted({s for p in candidates for s in (p.get("sources") or [p["source"]])})
        merged["versions"] = sorted({v for p in candidates for v in (p.get("versions") or [p.get("version")]) if v})
        for field in ("doi", "arxiv_id", "url", "abstract", "authors", "year", "venue", "venue_name", "venue_id", "pdf_url"):
            if not merged.get(field):
                merged[field] = next((p.get(field) for p in candidates if p.get(field)), merged.get(field))
        locations = [location for p in candidates for location in p.get("locations", []) if isinstance(location, dict)]
        if locations:
            merged["locations"] = list({json.dumps(location, sort_keys=True): location for location in locations}.values())
        # Canonical identity may have become available through another source.
        merged = normalize_paper(merged)
        if matches:
            first = matches[0]
            groups[first] = merged
            for i in reversed(matches[1:]):
                groups.pop(i)
        else:
            groups.append(merged)
    return groups


class _SameHostRedirect(HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, newurl):
        before, after = urlparse(request.full_url), urlparse(newurl)
        try:
            port = after.port
        except ValueError:
            raise LiteratureError("Literature service attempted an invalid redirect") from None
        if (after.scheme != "https" or after.hostname != before.hostname
                or port not in {None, 443} or after.username or after.password):
            raise LiteratureError("Literature service attempted an unexpected redirect")
        return super().redirect_request(request, fp, code, msg, headers, newurl)


def _request_bytes(url: str, timeout_s: float, headers: dict[str, str] | None = None) -> bytes:
    request = Request(url, headers={"User-Agent": "research-idea/0.1", "Accept": "application/json, application/atom+xml", **(headers or {})})
    deadline = time.monotonic() + timeout_s
    try:
        with build_opener(_SameHostRedirect()).open(request, timeout=timeout_s) as response:
            pieces, size = [], 0
            # read1 avoids waiting for a full large read while a server drips bytes.
            read = getattr(response, "read1", response.read)
            while size <= MAX_RESPONSE_BYTES:
                remaining = _remaining(deadline)
                sock = getattr(getattr(getattr(response, "fp", None), "raw", None), "_sock", None)
                if sock is not None:
                    sock.settimeout(remaining)
                piece = read(min(65536, MAX_RESPONSE_BYTES + 1 - size))
                _remaining(deadline)
                if not piece:
                    break
                pieces.append(piece)
                size += len(piece)
            data = b"".join(pieces)
    except HTTPError as exc:
        # Do not echo URLs, bodies, headers, or API credentials in error strings.
        hint = " Check API authentication or provider quota." if exc.code in {401, 403, 429} else ""
        raise LiteratureError(f"Literature service returned HTTP {exc.code}.{hint}") from None
    except (URLError, TimeoutError, OSError):
        raise LiteratureError("Literature service could not be reached within the request limits") from None
    if len(data) > MAX_RESPONSE_BYTES:
        raise LiteratureError("Literature response exceeds the download size limit")
    return data


def _abstract(index: Any) -> str:
    if not isinstance(index, dict):
        return ""
    positions: dict[int, str] = {}
    for word, indexes in index.items():
        if not isinstance(word, str) or not isinstance(indexes, list):
            continue
        for i in indexes:
            if isinstance(i, int) and not isinstance(i, bool) and 0 <= i < 100_000:
                positions[i] = word
    return " ".join(positions[i] for i in sorted(positions))


def _remaining(deadline: float) -> float:
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise LiteratureError("Literature retrieval time budget exhausted")
    return remaining


def _json_results(url: str, deadline: float, headers: dict | None = None,
                  field: str = "results") -> tuple[list, dict]:
    data = _request_bytes(url, _remaining(deadline), headers)
    try:
        payload = json.loads(data)
    except (ValueError, UnicodeError):
        raise LiteratureError("Literature service returned invalid JSON") from None
    if not isinstance(payload, dict) or not isinstance(payload.get(field), list):
        raise LiteratureError(f"Literature response does not contain a {field} list")
    return payload[field], payload


def _source_id(value: Any) -> str | None:
    match = re.fullmatch(r"(?:https://openalex.org/)?(S\d+)", str(value or ""), re.I)
    return match[1].upper() if match else None


def _openalex_sources(venues: list[str], deadline: float, headers: dict,
                      coverage: dict) -> dict[str, str]:
    """Resolve sources using exact normalized publication-series metadata."""
    resolved: dict[str, str] = {}
    coverage["openalex_sources"] = {}
    coverage["openalex_source_queries"] = []
    for venue in venues:
        try:
            rows = []
            for query in SOURCE_QUERIES.get(venue, (VENUES[venue][0],)):
                coverage["openalex_source_queries"].append({"venue": venue, "query": query, "per_page": 100})
                try:
                    page, payload = _json_results(OPENALEX_SOURCES_ENDPOINT + "?" + urlencode(
                        {"search": query, "per-page": 100}), deadline, headers)
                    rows.extend(page[:100])
                    meta = payload.get("meta") if isinstance(payload.get("meta"), dict) else {}
                    count = meta.get("count", 0)
                    if isinstance(count, int) and count > 100:
                        coverage["gaps"].append(f"{venue}: source resolution examined only the first 100 matches for a source query")
                except LiteratureError as exc:
                    coverage["gaps"].append(f"{venue}: {exc}")
            matches = []
            seen_names: dict[str, set[str]] = {}
            for row in rows:
                if not isinstance(row, dict):
                    continue
                sid, name = _source_id(row.get("id")), _clean(row.get("display_name"))
                if sid and canonical_venue(name) == venue:
                    matches.append({"id": sid, "display_name": name})
                    seen_names.setdefault(name.casefold(), set()).add(sid)
            ambiguous = {name for name, ids in seen_names.items() if len(ids) > 1}
            if ambiguous:
                coverage["gaps"].append(f"{venue}: duplicate source names with different OpenAlex IDs were excluded")
            matches = list({m["id"]: m for m in matches if m["display_name"].casefold() not in ambiguous}.values())
            # OpenAlex permits at most 100 values in one OR filter.
            available = max(0, 100 - len(resolved))
            if len(matches) > available:
                coverage["gaps"].append(f"{venue}: source-ID filter limit reached; some publication sources were not searched")
            matches = matches[:available]
            coverage["openalex_sources"][venue] = matches
            resolved.update({m["id"]: venue for m in matches})
            if not matches:
                coverage["gaps"].append(f"{venue}: no unambiguous matching OpenAlex publication source found; no unfiltered fallback")
        except LiteratureError as exc:
            coverage["openalex_sources"][venue] = []
            coverage["gaps"].append(f"{venue}: {exc}")
    return resolved


def _openalex_paper(work: dict) -> dict:
    location = work.get("primary_location") if isinstance(work.get("primary_location"), dict) else {}
    source = location.get("source") if isinstance(location.get("source"), dict) else {}
    locations = [x for x in [location, work.get("best_oa_location"), *(work.get("locations") or [])] if isinstance(x, dict)]
    # Preserve source names, IDs and URLs; do not treat provider metadata as instructions.
    locations = [{key: loc.get(key) for key in ("landing_page_url", "pdf_url", "is_oa", "version", "source") if loc.get(key) is not None} for loc in locations]
    authors = [a.get("author", {}).get("display_name", "") for a in work.get("authorships", [])
               if isinstance(a, dict) and isinstance(a.get("author"), dict)]
    return normalize_paper({"id": work.get("id"), "title": work.get("title") or work.get("display_name"),
        "authors": authors, "year": work.get("publication_year"),
        "url": location.get("landing_page_url") or work.get("id") or "", "doi": work.get("doi"),
        "abstract": _abstract(work.get("abstract_inverted_index")), "source": "openalex", "content_kind": "abstract",
        "venue": canonical_venue(source.get("display_name", "")), "venue_name": source.get("display_name"),
        "venue_id": _source_id(source.get("id")), "venue_evidence": "primary_location.source" if source else None,
        "locations": locations, "pdf_url": next((l["pdf_url"] for l in locations if l.get("pdf_url")), None)})


def _openreview_value(content: dict, name: str, default=None):
    value = content.get(name, default)
    return value.get("value", default) if isinstance(value, dict) else value


def _query_score(query: str, title: str, abstract: str) -> int:
    """Bounded lexical ranking of accepted COLM metadata, not semantic search."""
    stop = {"a", "an", "the", "and", "or", "of", "in", "on", "to", "for", "with", "by", "from"}
    terms = {word for word in re.findall(r"\w+", query.casefold()) if word not in stop}
    title_words, abstract_words = set(re.findall(r"\w+", title.casefold())), set(re.findall(r"\w+", abstract.casefold()))
    return sum(3 * (term in title_words) + (term in abstract_words) for term in terms)


def _discover_colm(query: str, limit: int, deadline: float, coverage: dict) -> list[dict]:
    years = list(range(date.today().year, max(2023, date.today().year - 3), -1))
    info = {"years": years, "page_size": OPENREVIEW_PAGE_SIZE, "max_pages_per_year": OPENREVIEW_MAX_PAGES,
            "ranking": "lexical token overlap in title and abstract", "years_scanned": []}
    coverage["openreview_colm"] = info
    candidates = []
    for year in years:
        venue_id = f"colmweb.org/COLM/{year}/Conference"
        status = {"year": year, "venue_id": venue_id, "pages": 0, "scanned": 0, "truncated": False}
        info["years_scanned"].append(status)
        try:
            for page in range(OPENREVIEW_MAX_PAGES):
                notes, payload = _json_results(OPENREVIEW_ENDPOINT + "?" + urlencode({
                    "content.venueid": venue_id, "limit": OPENREVIEW_PAGE_SIZE,
                    "offset": page * OPENREVIEW_PAGE_SIZE, "sort": "number:asc"}), deadline, field="notes")
                status["pages"] += 1
                status["scanned"] += len(notes)
                for note in notes:
                    if not isinstance(note, dict) or not isinstance(note.get("content"), dict):
                        continue
                    content = note["content"]
                    # Recheck accepted venue metadata; do not include submissions/reviews/rejections.
                    if _openreview_value(content, "venueid") != venue_id or note.get("replyto") or note.get("ddate"):
                        continue
                    identifier = str(note.get("id") or "")
                    if not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", identifier):
                        continue
                    title, abstract = _clean(_openreview_value(content, "title")), _clean(_openreview_value(content, "abstract"))
                    score = _query_score(query, title, abstract)
                    if not title or not score:
                        continue
                    paper = normalize_paper({"id": "openreview:" + identifier, "title": title,
                        "abstract": abstract, "authors": _openreview_value(content, "authors", []), "year": year,
                        "url": "https://openreview.net/forum?" + urlencode({"id": identifier}),
                        "pdf_url": "https://openreview.net/pdf?" + urlencode({"id": identifier}) if _openreview_value(content, "pdf") else None,
                        "doi": _openreview_value(content, "doi"), "source": "openreview", "content_kind": "abstract",
                        "venue": "COLM", "venue_name": _openreview_value(content, "venue", f"COLM {year}"),
                        "venue_id": venue_id, "venue_evidence": "accepted content.venueid", "retrieval_relevance": score})
                    candidates.append(paper)
                count = payload.get("count")
                if len(notes) < OPENREVIEW_PAGE_SIZE or (isinstance(count, int) and status["scanned"] >= count):
                    break
            else:
                status["truncated"] = True
                coverage["gaps"].append(f"COLM {year}: accepted-paper scan reached its page limit")
        except LiteratureError as exc:
            status["error"] = str(exc)
            coverage["gaps"].append(f"COLM {year}: {exc}")
    return sorted(candidates, key=lambda p: (p["retrieval_relevance"], p["year"]), reverse=True)[:limit]


def _interleave(pools: list[list[dict]], limit: int) -> list[dict]:
    selected = []
    for offset in range(max((len(pool) for pool in pools), default=0)):
        for pool in pools:
            if offset < len(pool):
                selected.append(pool[offset])
        if len(selected) >= limit:
            break
    return deduplicate(selected)[:limit]


def discover(query: str, source: str = "arxiv", limit: int = 10,
             timeout_s: float = 30, api_key_env: str | None = None,
             venues: list[str] | None = None) -> DiscoveryResults:
    """Retrieve bounded metadata pages. No full-text retrieval is implied.

    arXiv accepts its native query syntax; plain strings are searched with all:.
    OpenAlex uses a bearer token only when api_key_env is explicitly supplied.
    Venue scopes use one source-resolution page per known name (two for NAACL's
    rename) and one work page per venue; COLM uses public accepted-note scans.
    Coverage metadata reports unresolved venues, errors and pagination limits.
    """
    if not isinstance(query, str) or not query.strip() or len(query) > 4000:
        raise LiteratureError("Query must contain 1–4000 characters")
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 100:
        raise LiteratureError("Result limit must be between 1 and 100")
    if not isinstance(timeout_s, (int, float)) or isinstance(timeout_s, bool) or not math.isfinite(timeout_s) or timeout_s <= 0:
        raise LiteratureError("Request timeout must be positive and finite")
    if source not in {"arxiv", "openalex"}:
        raise LiteratureError("Unknown source; choose arxiv or openalex")
    try:
        venues = normalize_venues(venues)
    except ValueError as exc:
        raise LiteratureError(str(exc)) from None
    if source == "arxiv" and venues:
        raise LiteratureError("arXiv does not provide reliable accepted-venue filters; choose openalex with venues")
    deadline = time.monotonic() + timeout_s
    coverage = {"requested_venues": venues, "source": source, "gaps": [],
                "scope": "bounded metadata retrieval; not exhaustive literature or novelty coverage"}
    query = query.strip()
    if source == "arxiv":
        global _last_arxiv_request
        expression = query if re.search(r"\b(?:all|ti|au|abs|cat|id):", query) else "all:" + query
        url = ARXIV_ENDPOINT + "?" + urlencode({"search_query": expression, "start": 0, "max_results": limit, "sortBy": "relevance", "sortOrder": "descending"})
        # arXiv asks serial clients to leave >=3 seconds between requests.
        with _arxiv_lock:
            wait = 3 - (time.monotonic() - _last_arxiv_request)
            if wait > 0:
                if wait >= _remaining(deadline):
                    raise LiteratureError("arXiv courtesy delay exceeds the remaining retrieval budget")
                time.sleep(wait)
            _last_arxiv_request = time.monotonic()
            data = _request_bytes(url, _remaining(deadline))
        if b"<!DOCTYPE" in data.upper() or b"<!ENTITY" in data.upper():
            raise LiteratureError("Unexpected XML declarations in literature response")
        try:
            root = ET.fromstring(data)
        except ET.ParseError:
            raise LiteratureError("arXiv returned invalid Atom XML") from None
        ns = {"a": "http://www.w3.org/2005/Atom", "x": "http://arxiv.org/schemas/atom"}
        if root.tag != "{http://www.w3.org/2005/Atom}feed":
            raise LiteratureError("arXiv response is not an Atom feed")
        papers = []
        for entry in root.findall("a:entry", ns)[:limit]:
            identifier = entry.findtext("a:id", "", ns)
            if "/api/errors" in identifier:
                raise LiteratureError("arXiv rejected the search query")
            published = entry.findtext("a:published", "", ns)
            papers.append(normalize_paper({"id": identifier, "title": entry.findtext("a:title", "", ns),
                "authors": [a.findtext("a:name", "", ns) for a in entry.findall("a:author", ns)],
                "year": published[:4], "url": identifier, "doi": entry.findtext("x:doi", "", ns),
                "abstract": entry.findtext("a:summary", "", ns), "source": "arxiv", "content_kind": "abstract",
                "journal_ref": entry.findtext("x:journal_ref", "", ns), "venue": None,
                "pdf_url": next((link.get("href") for link in entry.findall("a:link", ns)
                                  if link.get("type") == "application/pdf"), None)}))
        return DiscoveryResults(deduplicate(papers), coverage=coverage)
    headers = {}
    if api_key_env and (not venues or any(venue != "COLM" for venue in venues)):
        key = os.environ.get(api_key_env, "").strip()
        if not key:
            raise LiteratureError("The configured OpenAlex API key environment variable is empty")
        headers["Authorization"] = "Bearer " + key
    pools = {venue: [] for venue in venues}
    # Reserve half the total time for each provider when both were requested.
    other_venues = [venue for venue in venues if venue != "COLM"]
    alex_deadline = time.monotonic() + _remaining(deadline) / 2 if "COLM" in venues and other_venues else deadline
    resolved = _openalex_sources(other_venues, alex_deadline, headers, coverage) if other_venues else {}
    # Fetch a bounded page per requested venue: a prolific venue must not crowd
    # another out before the final round-robin selection.
    requests = [(None, {"search": query, "per-page": limit})] if not venues else [
        (venue, {"search": query, "per-page": limit,
                 "filter": "primary_location.source.id:" + "|".join(sid for sid, name in resolved.items() if name == venue)})
        for venue in other_venues if venue in resolved.values()]
    papers = []
    coverage["openalex_work_queries"] = []
    for requested_venue, params in requests:
        coverage["openalex_work_queries"].append({"venue": requested_venue, "per_page": limit, "pages": 1})
        try:
            works, _ = _json_results(OPENALEX_ENDPOINT + "?" + urlencode(params), alex_deadline, headers)
            for work in works[:int(params["per-page"])]:
                try:
                    if not isinstance(work, dict):
                        raise LiteratureError("OpenAlex returned invalid work metadata")
                    paper = _openalex_paper(work)
                    if venues:
                        matched = resolved.get(paper.get("venue_id"))
                        if not matched or matched != requested_venue:
                            coverage["gaps"].append("OpenAlex returned a work outside the requested source-ID filter; excluded")
                            continue
                        paper["venue"] = matched
                        pools[matched].append(paper)
                    else:
                        papers.append(paper)
                except (LiteratureError, TypeError, AttributeError):
                    coverage["gaps"].append("An invalid OpenAlex paper record was skipped")
        except LiteratureError as exc:
            if not venues:
                raise
            coverage["gaps"].append(f"OpenAlex works {requested_venue}: {exc}")
    if "COLM" in venues:
        pools["COLM"] = _discover_colm(query, limit, deadline, coverage)
    if venues:
        papers = _interleave(list(pools.values()), limit)
        coverage["matched_counts"] = {venue: len(pool) for venue, pool in pools.items()}
        coverage["selected_counts"] = {venue: sum(p.get("venue") == venue for p in papers) for venue in venues}
        if limit < sum(bool(pool) for pool in pools.values()):
            coverage["gaps"].append("Result limit is smaller than the number of matched venues; not every venue is represented")
        coverage["gaps"].extend(f"{venue}: no matching papers in the bounded retrieved metadata" for venue, pool in pools.items() if not pool)
    for paper in papers:
        paper["search_coverage"] = coverage
    return DiscoveryResults(deduplicate(papers)[:limit], coverage=coverage)


def fetch_full_text(paper: dict, destination: Path | None = None,
                    timeout_s: float = 30) -> dict:
    """Fetch a bounded trusted-host PDF; failures preserve the original evidence.

    Returns ``full_text_retrieval`` status and a safe ``full_text_error`` on
    failure. Only successful nonempty PDF text extraction upgrades content_kind.
    """
    from .fulltext import fetch_full_text as fetch
    return fetch(paper, destination=destination, timeout_s=timeout_s)


def read_source(path: Path, title: str | None = None) -> dict[str, Any]:
    """Read a local UTF-8 .txt/.md or text-bearing PDF without executing it."""
    path = Path(path).expanduser().resolve()
    if not path.is_file():
        raise LiteratureError(f"Source file does not exist: {path}")
    if path.suffix.lower() not in {".txt", ".md", ".pdf"}:
        raise LiteratureError("Supported local source formats: .txt, .md, .pdf")
    try:
        raw = path.read_bytes() if path.stat().st_size <= MAX_SOURCE_BYTES else None
    except OSError:
        raise LiteratureError("Source file cannot be read") from None
    if raw is None:
        raise LiteratureError("Source exceeds the 32 MiB local file limit")
    if path.suffix.lower() == ".pdf":
        executable = shutil.which("pdftotext")
        if not executable:
            raise LiteratureError("PDF import requires Poppler pdftotext; install it or import extracted text")
        with tempfile.TemporaryDirectory(prefix="research-pdf-") as temporary:
            output = Path(temporary) / "paper.txt"
            try:
                result = subprocess.run([executable, "-layout", "-enc", "UTF-8", str(path), str(output)],
                                        stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, timeout=45, check=False)
            except subprocess.TimeoutExpired:
                raise LiteratureError("PDF extraction exceeded 45 seconds") from None
            except OSError:
                raise LiteratureError("PDF extractor could not be started") from None
            if result.returncode or not output.is_file():
                raise LiteratureError("PDF extraction failed; encrypted or damaged PDFs may require manual extraction")
            if output.stat().st_size > MAX_SOURCE_BYTES:
                raise LiteratureError("Extracted PDF text exceeds the size limit")
            text = output.read_text(encoding="utf-8")
        kind = "full_text"
    else:
        try:
            text = raw.decode("utf-8-sig")
        except UnicodeError:
            raise LiteratureError("Text sources must use UTF-8 encoding") from None
        kind = "notes"
    if not text.strip():
        raise LiteratureError("No text was extracted; scanned PDFs require OCR before import")
    digest = hashlib.sha256(raw).hexdigest()[:20]
    return normalize_paper({"id": "local:" + digest, "title": title or path.stem,
                            "text": text, "content_kind": kind, "path": str(path),
                            "source": "local", "content_sha256": hashlib.sha256(raw).hexdigest()})
