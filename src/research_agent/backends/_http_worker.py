"""One cancellable HTTP attempt; parent owns the wall-clock deadline.

This file is executed directly in a child Python process. Credentials enter only
through stdin, never argv or a temporary file. Error bodies are not returned.
"""
from __future__ import annotations

import base64
import json
import sys
import urllib.error
import urllib.request

MAX_RESPONSE_BYTES = 16 * 1024 * 1024


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def request_once(spec: dict) -> dict:
    request = urllib.request.Request(
        spec["url"], data=json.dumps(spec["body"], ensure_ascii=False).encode("utf-8"),
        headers=spec["headers"], method="POST",
    )
    try:
        with urllib.request.build_opener(NoRedirect).open(request, timeout=spec["timeout_s"]) as response:
            payload = response.read(MAX_RESPONSE_BYTES + 1)
        if len(payload) > MAX_RESPONSE_BYTES:
            return {"kind": "oversize"}
        return {"kind": "response", "body_base64": base64.b64encode(payload).decode("ascii")}
    except urllib.error.HTTPError as exc:
        status = exc.code
        exc.close()
        return {"kind": "http_error", "status": status}
    except (urllib.error.URLError, TimeoutError, OSError):
        return {"kind": "connection_error"}


def main() -> None:
    try:
        result = request_once(json.load(sys.stdin))
    except Exception:
        # Do not print tracebacks: a transport implementation can put headers,
        # URLs, or response bodies into an exception string.
        result = {"kind": "worker_error"}
    print(json.dumps(result))


if __name__ == "__main__":
    main()
