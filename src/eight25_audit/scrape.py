from __future__ import annotations

from datetime import datetime, timezone
from urllib.parse import urlparse

import httpx

from .models import FetchResult


def _detect_blocked_reason(*, status_code: int, html: str, content_type: str | None) -> str | None:
    body = (html or "").lower()
    ctype = (content_type or "").lower()

    # Common bot-protection challenge signatures.
    if "just a moment" in body and ("cloudflare" in body or "cf-chl" in body or status_code == 403):
        return "Blocked by Cloudflare challenge page"
    if "attention required" in body and "cloudflare" in body:
        return "Blocked by Cloudflare protection"
    if "cf-ray" in body and ("captcha" in body or "challenge" in body):
        return "Blocked by Cloudflare challenge/captcha"

    # Non-HTML responses should not be parsed into webpage metrics.
    if ctype and not (
        "text/html" in ctype
        or "application/xhtml+xml" in ctype
        or "application/xml" in ctype
        or "+xml" in ctype
    ):
        return f"Unsupported content type for page audit: {ctype}"

    if "enable javascript" in body and ("access denied" in body or "verify you are human" in body):
        return "Blocked by anti-bot page requiring JavaScript"

    if "access denied" in body and status_code in {401, 403}:
        return f"Access denied (HTTP {status_code})"

    if status_code >= 400 and "text/html" in ctype and not body.strip():
        return f"Request failed with HTTP {status_code} and empty HTML body"

    if status_code >= 400 and ("captcha" in body or "are you human" in body):
        return f"Blocked by anti-bot/captcha page (HTTP {status_code})"

    return None


def normalize_url(url: str) -> str:
    url = url.strip()
    if not url:
        raise ValueError("URL is required")

    parsed = urlparse(url)
    if not parsed.scheme:
        url = "https://" + url
        parsed = urlparse(url)

    if parsed.scheme not in {"http", "https"}:
        raise ValueError("Only http/https URLs are supported")

    if not parsed.netloc:
        raise ValueError("Invalid URL")

    return url


def fetch_html(url: str, *, timeout_s: float = 25.0, verify_tls: bool = True) -> FetchResult:
    requested = normalize_url(url)

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/121.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
        "Upgrade-Insecure-Requests": "1",
    }

    fetched_at = datetime.now(timezone.utc)
    try:
        with httpx.Client(
            follow_redirects=True,
            headers=headers,
            timeout=timeout_s,
            verify=verify_tls,
        ) as client:
            resp = client.get(requested)
    except httpx.HTTPError as e:
        return FetchResult(
            requested_url=requested,
            final_url=requested,
            status_code=0,
            fetched_at=fetched_at,
            content_type=None,
            html="",
            blocked_reason=f"Network/fetch error: {type(e).__name__}: {e}",
        )

    content_type = resp.headers.get("content-type")

    # Best-effort decode; httpx already decodes to text using apparent encoding.
    html = resp.text or ""
    blocked_reason = _detect_blocked_reason(status_code=resp.status_code, html=html, content_type=content_type)

    return FetchResult(
        requested_url=requested,
        final_url=str(resp.url),
        status_code=resp.status_code,
        fetched_at=fetched_at,
        content_type=content_type,
        html=html,
        blocked_reason=blocked_reason,
    )
