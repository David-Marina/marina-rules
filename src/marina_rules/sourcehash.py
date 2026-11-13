"""Content hashing for cited sources.

HTML pages on exchange CMSs re-render with new timestamps, nonces and asset versions while the notice
text is unchanged; a byte hash of such a page drifts for no reason. We therefore hash the *extracted
text* of HTML documents and the *bytes* of everything else (PDF, DOCX, images).

    content_sha256(body, content_type_or_url) -> (hexdigest, kind)   kind in {"text", "bytes"}

Normalisation for text: strip <script>/<style>, strip tags, unescape entities, collapse whitespace,
drop lines that look like CMS boilerplate timestamps. Deterministic across fetches and runners.
"""
from __future__ import annotations

import hashlib
import html
import re

_HTML_HINT = re.compile(rb"<\s*(!doctype\s+html|html|head|body)\b", re.I)
_TS = re.compile(r"页面生成时间\s*\d{4}-\d{2}-\d{2}\s*\d{2}:\d{2}:\d{2}")


def is_html(body: bytes, hint: str = "") -> bool:
    h = hint.lower()
    if h.endswith((".pdf", ".docx", ".doc", ".xls", ".xlsx", ".zip")) or body[:5] == b"%PDF-" or body[:2] == b"PK":
        return False
    return bool(_HTML_HINT.search(body[:4096])) or "html" in h


def html_to_text(body: bytes) -> str:
    for enc in ("utf-8", "gb18030"):
        try:
            t = body.decode(enc); break
        except UnicodeDecodeError:
            continue
    else:
        t = body.decode("utf-8", "ignore")
    t = re.sub(r"(?is)<(script|style|noscript)\b.*?</\1>", " ", t)
    t = re.sub(r"(?s)<!--.*?-->", " ", t)
    t = re.sub(r"<[^>]+>", " ", t)
    t = html.unescape(t)
    t = _TS.sub("", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t


def content_sha256(body: bytes, hint: str = "") -> tuple[str, str]:
    if is_html(body, hint):
        return hashlib.sha256(html_to_text(body).encode("utf-8")).hexdigest(), "text"
    return hashlib.sha256(body).hexdigest(), "bytes"
