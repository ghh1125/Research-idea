"""Bounded literature discovery and local source ingestion.

All returned text is untrusted source material, never execution instructions.
Discovery supplies abstracts, not full-paper evidence. Local text/Markdown are
classified as notes unless the importing caller supplies stronger provenance.
"""
from __future__ import annotations

import hashlib
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

MAX_RESPONSE_BYTES = 8 * 1024 * 1024
MAX_SOURCE_BYTES = 32 * 1024 * 1024
ARXIV_ENDPOINT = "https://export.arxiv.org/api/query"
OPENALEX_ENDPOINT = "https://api.openalex.org/works"
_arxiv_lock = threading.Lock()
_last_arxiv_request = 0.0
_ARXIV_RE = re.compile(r"^(\d{4}\.\d{4,5}|[a-z][a-z.\-]+/\d{7})(v\d+)?$", re.I)


class LiteratureError(RuntimeError):
    """A source could not be retrieved, decoded, or normalized."""


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
        for field in ("doi", "arxiv_id", "url", "abstract", "authors", "year"):
            if not merged.get(field):
                merged[field] = next((p.get(field) for p in candidates if p.get(field)), merged.get(field))
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
        if after.scheme != "https" or after.hostname != before.hostname:
            raise LiteratureError("Literature service attempted an unexpected redirect")
        return super().redirect_request(request, fp, code, msg, headers, newurl)


def _request_bytes(url: str, timeout_s: float, headers: dict[str, str] | None = None) -> bytes:
    request = Request(url, headers={"User-Agent": "research-agent-cli/0.1", "Accept": "application/json, application/atom+xml", **(headers or {})})
    try:
        with build_opener(_SameHostRedirect()).open(request, timeout=timeout_s) as response:
            data = response.read(MAX_RESPONSE_BYTES + 1)
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


def discover(query: str, source: str = "arxiv", limit: int = 10,
             timeout_s: float = 30, api_key_env: str | None = None) -> list[dict[str, Any]]:
    """Retrieve one bounded result page. No full-text retrieval is implied.

    arXiv accepts its native query syntax; plain strings are searched with all:.
    OpenAlex uses a bearer token only when api_key_env is explicitly supplied.
    """
    if not isinstance(query, str) or not query.strip() or len(query) > 4000:
        raise LiteratureError("Query must contain 1–4000 characters")
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 100:
        raise LiteratureError("Result limit must be between 1 and 100")
    if not isinstance(timeout_s, (int, float)) or isinstance(timeout_s, bool) or not math.isfinite(timeout_s) or timeout_s <= 0:
        raise LiteratureError("Request timeout must be positive and finite")
    if source not in {"arxiv", "openalex"}:
        raise LiteratureError("Unknown source; choose arxiv or openalex")
    query = query.strip()
    if source == "arxiv":
        global _last_arxiv_request
        expression = query if re.search(r"\b(?:all|ti|au|abs|cat|id):", query) else "all:" + query
        url = ARXIV_ENDPOINT + "?" + urlencode({"search_query": expression, "start": 0, "max_results": limit, "sortBy": "relevance", "sortOrder": "descending"})
        # arXiv asks serial clients to leave >=3 seconds between requests.
        with _arxiv_lock:
            wait = 3 - (time.monotonic() - _last_arxiv_request)
            if wait > 0:
                time.sleep(wait)
            _last_arxiv_request = time.monotonic()
            data = _request_bytes(url, timeout_s)
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
                "abstract": entry.findtext("a:summary", "", ns), "source": "arxiv", "content_kind": "abstract"}))
        return deduplicate(papers)
    headers = {}
    if api_key_env:
        key = os.environ.get(api_key_env, "").strip()
        if not key:
            raise LiteratureError("The configured OpenAlex API key environment variable is empty")
        headers["Authorization"] = "Bearer " + key
    url = OPENALEX_ENDPOINT + "?" + urlencode({"search": query, "per-page": limit})
    data = _request_bytes(url, timeout_s, headers)
    try:
        payload = json.loads(data)
    except (ValueError, UnicodeError):
        raise LiteratureError("OpenAlex returned invalid JSON") from None
    if not isinstance(payload, dict) or not isinstance(payload.get("results"), list):
        raise LiteratureError("OpenAlex response does not contain a results list")
    papers = []
    for work in payload["results"][:limit]:
        if not isinstance(work, dict):
            raise LiteratureError("OpenAlex returned invalid work metadata")
        location = work.get("primary_location") or {}
        authors = [a.get("author", {}).get("display_name", "") for a in work.get("authorships", []) if isinstance(a, dict) and isinstance(a.get("author"), dict)]
        papers.append(normalize_paper({"id": work.get("id"), "title": work.get("title") or work.get("display_name"),
            "authors": authors, "year": work.get("publication_year"), "url": location.get("landing_page_url") or work.get("id") or "",
            "doi": work.get("doi"), "abstract": _abstract(work.get("abstract_inverted_index")), "source": "openalex", "content_kind": "abstract"}))
    return deduplicate(papers)


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
