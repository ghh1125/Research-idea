"""Bounded official-source PDF acquisition; failed reads never become evidence.

The download runs in a cancellable process so a slow response body cannot evade
the total download/extraction deadline. No account credentials are consulted.
This file also serves as that worker's isolated Python entry point.
"""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
import re
import shutil
import sys
import tempfile
import time
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlencode, urlsplit, urlunsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

MAX_PDF_BYTES = 32 * 1024 * 1024
MAX_REDIRECTS = 5
MAX_CANDIDATES = 8
ALLOWED_HOSTS = frozenset({
    "aclanthology.org", "www.aclanthology.org",
    "openreview.net", "www.openreview.net",
    "arxiv.org", "www.arxiv.org", "export.arxiv.org",
    "proceedings.mlr.press", "proceedings.neurips.cc", "papers.nips.cc", "papers.neurips.cc",
    "ojs.aaai.org", "ijcai.org", "www.ijcai.org", "openaccess.thecvf.com",
    "vldb.org", "www.vldb.org", "dl.acm.org", "ieeexplore.ieee.org",
    "raw.githubusercontent.com",
})


class FullTextError(RuntimeError):
    """A sanitized acquisition failure suitable for a retrieval ledger."""


def validate_pdf_url(url: str) -> str:
    """Validate every network target, including all redirect destinations."""
    if not isinstance(url, str) or not url or len(url) > 8192 or any(ord(c) < 33 or ord(c) == 127 for c in url):
        raise ValueError("PDF URL is malformed")
    try:
        parsed = urlsplit(url)
        port = parsed.port
    except ValueError:
        raise ValueError("PDF URL is malformed") from None
    if (parsed.scheme != "https" or parsed.hostname not in ALLOWED_HOSTS
            or parsed.username is not None or parsed.password is not None
            or port not in {None, 443} or parsed.fragment):
        raise ValueError("PDF URL must use HTTPS on a supported official host without credentials or custom ports")
    if parsed.hostname == 'raw.githubusercontent.com' and (
            parsed.query or not re.fullmatch(
                r'/mlresearch/v\d+/(?:main|master|gh-pages)/(?:assets/)?[A-Za-z0-9_-]+/[A-Za-z0-9_.-]+\.pdf',
                parsed.path)):
        raise ValueError("GitHub PDF URLs must point to a PMLR mlresearch volume")
    return urlunsplit(("https", parsed.hostname, parsed.path or "/", parsed.query, ""))


def _pdf_candidate(raw) -> str | None:
    if not isinstance(raw, str):
        return None
    try:
        url = validate_pdf_url(raw.strip())
    except ValueError:
        return None
    parsed = urlsplit(url)
    host, path = parsed.hostname, parsed.path
    if host in {"aclanthology.org", "www.aclanthology.org"}:
        identifier = path.strip("/").removesuffix(".pdf")
        if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", identifier):
            return "https://aclanthology.org/" + identifier + ".pdf"
    elif host in {"openreview.net", "www.openreview.net"} and path.rstrip("/") in {"/forum", "/pdf"}:
        query = parse_qs(parsed.query)
        ids = query.get("id", [])
        if len(ids) == 1 and re.fullmatch(r"[A-Za-z0-9_-]{1,256}", ids[0]):
            params = {"id": ids[0]}
            if len(query.get("version", [])) == 1 and query["version"][0].isdigit():
                params["version"] = query["version"][0]
            return "https://openreview.net/pdf?" + urlencode(params)
    elif host in {"arxiv.org", "www.arxiv.org", "export.arxiv.org"}:
        from .literature import _arxiv
        identifier = _arxiv(url)
        if identifier:
            return "https://arxiv.org/pdf/" + identifier[0] + (identifier[1] or "")
    elif host == 'dl.acm.org' and re.fullmatch(r'/doi/(?:e?pdf)/10\.\d+/[^/]+', path):
        return url.replace('/doi/epdf/', '/doi/pdf/')
    elif path.lower().endswith(".pdf") or (host == "ojs.aaai.org" and "/article/download/" in path):
        return url
    return None


def candidate_pdf_urls(paper: dict) -> list[str]:
    """Resolve known official landing pages; do not guess arbitrary download links."""
    raw_urls = [paper.get("pdf_url"), paper.get("url")]
    locations = paper.get("locations")
    if isinstance(locations, list):
        for location in locations[:100]:
            if isinstance(location, dict):
                raw_urls.extend((location.get("pdf_url"), location.get("landing_page_url"), location.get("url")))
    for field in ("best_oa_location", "primary_location", "open_access"):
        location = paper.get(field)
        if isinstance(location, dict):
            raw_urls.extend((location.get("pdf_url"), location.get("landing_page_url"), location.get("oa_url")))
    candidates = [candidate for raw in raw_urls if (candidate := _pdf_candidate(raw))]
    doi = str(paper.get("doi") or "").strip()
    doi = re.sub(r"^(?:https?://(?:dx\.)?doi\.org/|doi:\s*)", "", doi, flags=re.I)
    acl = re.fullmatch(r"10\.18653/v1/([A-Za-z0-9][A-Za-z0-9._-]*)", doi, re.I)
    if acl:
        candidates.append("https://aclanthology.org/" + acl[1] + ".pdf")
    from .literature import _arxiv
    identifier = _arxiv(paper.get("arxiv_id")) or _arxiv(paper.get("url")) or _arxiv(paper.get("pdf_url"))
    if identifier is None and doi.lower().startswith("10.48550/arxiv."):
        identifier = _arxiv(doi[len("10.48550/arxiv."):])
    if identifier:
        version = identifier[1] or paper.get("version") or ""
        version = version if isinstance(version, str) and re.fullmatch(r"v\d+", version) else ""
        exact = "https://arxiv.org/pdf/" + identifier[0] + version
        if version:
            # An unversioned URL means "latest" and must not fetch v3 into a
            # metadata record that explicitly identifies v2. Replace every URL
            # for this arXiv ID with the pinned version, including fallbacks.
            candidates = [exact if (parsed := _arxiv(candidate)) and parsed[0] == identifier[0]
                          else candidate for candidate in candidates]
        candidates.append(exact)
    return list(dict.fromkeys(candidates))[:MAX_CANDIDATES]


class _AllowedRedirect(HTTPRedirectHandler):
    def __init__(self):
        super().__init__()
        self.hops = 0

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        self.hops += 1
        if self.hops > MAX_REDIRECTS:
            raise FullTextError("PDF redirect limit exceeded")
        try:
            checked = validate_pdf_url(newurl)
        except ValueError:
            raise FullTextError("PDF redirect left the supported official hosts") from None
        return super().redirect_request(req, fp, code, msg, headers, checked)


def _download_pdf(url: str, target: Path, timeout_s: float) -> dict:
    """Worker-side bounded streaming; the supervising process enforces total time."""
    checked = validate_pdf_url(url)
    request = Request(checked, headers={"User-Agent": "Research-idea/0.2 (paper full-text retrieval)",
                                        "Accept": "application/pdf"}, method="GET")
    # Honor the user's normal HTTPS proxy configuration; destinations and every
    # redirect remain constrained by the official-host allowlist and TLS.
    opener = build_opener(_AllowedRedirect())
    digest = hashlib.sha256()
    total = 0
    try:
        with opener.open(request, timeout=timeout_s) as response:
            final_url = validate_pdf_url(response.geturl())
            content_type = response.headers.get("Content-Type", "").lower()
            if "text/html" in content_type or "application/xhtml" in content_type:
                raise FullTextError("Official source returned HTML or a login page instead of PDF")
            length = response.headers.get("Content-Length")
            expected_size = None
            if length is not None:
                try:
                    expected_size = int(length)
                    if expected_size < 0 or expected_size > MAX_PDF_BYTES:
                        raise FullTextError("PDF exceeds the 32 MiB download limit")
                except ValueError:
                    raise FullTextError("Official source returned an invalid PDF length") from None
            with target.open("wb") as output:
                while chunk := response.read(min(65536, MAX_PDF_BYTES + 1 - total)):
                    if total == 0 and not chunk.startswith(b"%PDF-"):
                        raise FullTextError("Official source did not return PDF content")
                    total += len(chunk)
                    if total > MAX_PDF_BYTES:
                        raise FullTextError("PDF exceeds the 32 MiB download limit")
                    digest.update(chunk)
                    output.write(chunk)
            if total == 0:
                raise FullTextError("Official source returned an empty PDF")
            if expected_size is not None and total != expected_size:
                raise FullTextError("PDF download was incomplete")
    except HTTPError as exc:
        raise FullTextError(f"Official PDF source returned HTTP {exc.code}") from None
    except (URLError, TimeoutError, OSError):
        raise FullTextError("Official PDF source could not be downloaded") from None
    return {"final_url": final_url, "pdf_sha256": digest.hexdigest(), "bytes": total}


def _download_in_process(url: str, target: Path, timeout_s: float) -> dict:
    from .backends.common import run_cli
    from .backend_types import BackendError
    payload = json.dumps({"url": url, "target": str(target.resolve()), "timeout_s": timeout_s})
    try:
        raw = run_cli([sys.executable, "-I", str(Path(__file__).resolve()), "--download-worker"],
                      payload, target.parent, timeout_s)
        result = json.loads(raw)
        if not isinstance(result, dict) or result.get("status") != "completed":
            # Only worker-created fixed messages are surfaced, never a remote body.
            message = result.get("error", "PDF download failed") if isinstance(result, dict) else "PDF download failed"
            raise FullTextError(message)
        return result
    except BackendError:
        raise FullTextError("PDF download failed or exceeded the total retrieval timeout") from None
    except (ValueError, TypeError):
        raise FullTextError("PDF download worker returned an invalid result") from None


def _extract_pdf(pdf: Path, txt: Path, timeout_s: float) -> str:
    from .backends.common import run_cli
    from .backend_types import BackendError
    executable = shutil.which("pdftotext")
    if not executable:
        raise FullTextError("PDF extraction requires Poppler pdftotext; the abstract was preserved")
    try:
        # A failed earlier candidate must not leave reusable extraction output.
        txt.unlink(missing_ok=True)
        # Reading order keeps two-column paragraphs contiguous. Physical layout
        # interleaves unrelated columns and breaks grounded quote matching.
        run_cli([executable, "-enc", "UTF-8", str(pdf), str(txt)], "", pdf.parent, timeout_s)
        if not txt.is_file() or txt.stat().st_size > MAX_PDF_BYTES:
            raise FullTextError("PDF extraction produced no bounded text file")
        text = txt.read_text(encoding="utf-8")
    except BackendError:
        raise FullTextError("PDF extraction failed or exceeded the total retrieval timeout") from None
    except (OSError, UnicodeError):
        raise FullTextError("PDF text output could not be read as UTF-8") from None
    if not text.strip():
        raise FullTextError("PDF contains no extractable text; scanned documents require OCR")
    return text


def fetch_full_text(paper: dict, destination: Path | None = None, timeout_s: float = 30) -> dict:
    """Upgrade a copy only after a real PDF yields nonempty text, within one deadline."""
    if not isinstance(paper, dict):
        raise ValueError("Paper metadata must be an object")
    result = dict(paper)
    if paper.get("content_kind") == "full_text" and str(paper.get("text") or "").strip():
        return result
    if isinstance(timeout_s, bool) or not isinstance(timeout_s, (float, int)) or not math.isfinite(timeout_s) or timeout_s <= 0:
        raise ValueError("timeout_s must be a positive finite number")
    deadline = time.monotonic() + timeout_s
    urls = candidate_pdf_urls(paper)
    if not urls:
        result.update(full_text_error="No supported official PDF URL was found in the supplied metadata",
                      full_text_retrieval={"status": "unavailable", "attempts": 0})
        return result
    error = "No official PDF could be read"
    attempts = 0
    with tempfile.TemporaryDirectory(prefix="research-fulltext-") as temporary:
        pdf, txt = Path(temporary) / "source.pdf", Path(temporary) / "source.txt"
        for url in urls:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                error = "Full-text retrieval exceeded its total timeout"
                break
            attempts += 1
            try:
                downloaded = _download_in_process(url, pdf, remaining)
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise FullTextError("Full-text retrieval exceeded its total timeout")
                text = _extract_pdf(pdf, txt, remaining)
                if not text.strip():
                    raise FullTextError("PDF contains no extractable text; scanned documents require OCR")
                if not pdf.is_file() or pdf.stat().st_size > MAX_PDF_BYTES:
                    raise FullTextError("Downloaded PDF failed the local size check")
                raw = pdf.read_bytes()
                if not raw.startswith(b"%PDF-"):
                    raise FullTextError("Downloaded file is not a PDF")
                final_url = validate_pdf_url(downloaded.get("final_url", url))
                pdf_hash = hashlib.sha256(raw).hexdigest()
                content_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
                paths = {}
                if destination is not None:
                    target = Path(destination).expanduser().resolve()
                    target.mkdir(parents=True, exist_ok=True)
                    saved_pdf, saved_txt = target / (pdf_hash + ".pdf"), target / (pdf_hash + ".txt")
                    shutil.copyfile(pdf, saved_pdf)
                    saved_txt.write_text(text, encoding="utf-8")
                    paths = {"pdf_path": str(saved_pdf), "text_path": str(saved_txt)}
                if time.monotonic() >= deadline:
                    raise FullTextError("Full-text retrieval exceeded its total timeout")
                result.update(text=text, content_kind="full_text", full_text_url=final_url,
                              pdf_sha256=pdf_hash, content_sha256=content_hash,
                              full_text_retrieval={"status": "completed", "attempts": attempts,
                                                   "method": "official_pdf_pdftotext", "text_order": "reading_order",
                                                   "bytes": len(raw)}, **paths)
                result.pop("full_text_error", None)
                return result
            except FullTextError as exc:
                error = str(exc)
            except (OSError, ValueError, TypeError):
                error = "Full-text retrieval or local storage failed"
    result.update(full_text_error=error, full_text_retrieval={"status": "failed", "attempts": attempts})
    return result


def _worker_main():
    try:
        payload = json.loads(sys.stdin.buffer.read(32768))
        result = _download_pdf(payload["url"], Path(payload["target"]), float(payload["timeout_s"]))
        result["status"] = "completed"
    except FullTextError as exc:
        result = {"status": "failed", "error": str(exc)}
    except Exception:
        result = {"status": "failed", "error": "PDF download worker failed"}
    sys.stdout.write(json.dumps(result, ensure_ascii=False) + "\n")


if __name__ == "__main__" and sys.argv[1:] == ["--download-worker"]:
    _worker_main()
