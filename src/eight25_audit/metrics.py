from __future__ import annotations

import re
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

from .models import CountedImageItem, HeadingCounts, ImageAltStats, LinkCounts, PageMetrics


_WORD_RE = re.compile(r"[A-Za-z0-9]+(?:['’][A-Za-z0-9]+)?")
_CTA_CLASS_RE = re.compile(r"\b(btn|button|cta|primary|btn-primary|button-primary)\b", re.I)
_CTA_TEXT_RE = re.compile(
    r"\b(contact|book|start|get\s+started|schedule|request|quote|download|subscribe|sign\s*up|join|buy|shop|demo|trial|apply|register|learn\s+more)\b",
    re.I,
)
_NOISE_LINK_TEXT_RE = re.compile(
    r"\b(home|about|privacy|terms|cookie|careers?|blog|support|help|login|log\s*in|sign\s*in)\b",
    re.I,
)


def _clean_text(text: str) -> str:
    text = re.sub(r"\s+", " ", text or " ").strip()
    return text


def _base_host(url: str) -> str:
    host = (urlparse(url).hostname or "").lower()
    return host[4:] if host.startswith("www.") else host


def _is_internal_link(base_url: str, absolute_url: str) -> bool:
    base = _base_host(base_url)
    target = _base_host(absolute_url)
    if not base or not target:
        return False
    return target == base or target.endswith("." + base)


def _first_text(*values: str) -> str:
    for value in values:
        txt = _clean_text(value)
        if txt:
            return txt
    return ""


def _is_primary_action_link(a) -> tuple[bool, str]:
    href = (a.get("href") or "").strip()
    if not href or href.startswith(("#", "mailto:", "tel:", "javascript:")):
        return False, ""

    role = (a.get("role") or "").strip().lower()
    class_attr = " ".join(a.get("class") or [])
    link_id = (a.get("id") or "").strip()
    aria_label = (a.get("aria-label") or "").strip()
    text = _first_text(a.get_text(" "), aria_label)

    attr_signal = bool(
        _CTA_CLASS_RE.search(class_attr)
        or _CTA_CLASS_RE.search(link_id)
        or role == "button"
        or a.has_attr("data-cta")
        or a.has_attr("data-action")
    )

    # Use text-based CTA fallback only when text is short enough to resemble an action label.
    text_signal = bool(text and len(text) <= 42 and _CTA_TEXT_RE.search(text) and not _NOISE_LINK_TEXT_RE.search(text))

    return (attr_signal or text_signal), text


def extract_metrics(html: str, *, page_url: str) -> PageMetrics:
    soup = BeautifulSoup(html, "lxml")

    for tag_name in ["script", "style", "noscript", "template"]:
        for t in soup.find_all(tag_name):
            t.decompose()

    title = None
    if soup.title and soup.title.string:
        title = _clean_text(soup.title.string)

    meta_desc = None
    meta_desc_tag = soup.find("meta", attrs={"name": re.compile(r"^description$", re.I)})
    if meta_desc_tag and meta_desc_tag.get("content"):
        meta_desc = _clean_text(meta_desc_tag.get("content"))

    body = soup.body or soup
    total_body_text = _clean_text(body.get_text(" "))
    words = _WORD_RE.findall(total_body_text)
    total_word_count = len(words)

    h1_tags = soup.find_all("h1")
    h2_tags = soup.find_all("h2")
    h3_tags = soup.find_all("h3")
    headings = HeadingCounts(h1=len(h1_tags), h2=len(h2_tags), h3=len(h3_tags))
    heading_texts = {
        "h1": [_clean_text(h.get_text(" ")) for h in h1_tags if _clean_text(h.get_text(" "))],
        "h2": [_clean_text(h.get_text(" ")) for h in h2_tags if _clean_text(h.get_text(" "))],
        "h3": [_clean_text(h.get_text(" ")) for h in h3_tags if _clean_text(h.get_text(" "))],
    }

    # Heading samples for AI grounding
    sample_headings: list[str] = []
    for level in ("h1", "h2", "h3"):
        for h in soup.find_all(level):
            text = _clean_text(h.get_text(" "))
            if text:
                sample_headings.append(f"{level.upper()}: {text}")
            if len(sample_headings) >= 12:
                break
        if len(sample_headings) >= 12:
            break

    # Links
    internal = external = other = 0
    counted_internal_links: list[str] = []
    counted_external_links: list[str] = []
    counted_other_links: list[str] = []
    for a in soup.find_all("a"):
        href = (a.get("href") or "").strip()
        if not href or href.startswith("#"):
            other += 1
            if href:
                counted_other_links.append(href)
            continue
        if href.startswith(("mailto:", "tel:", "javascript:")):
            other += 1
            counted_other_links.append(href)
            continue

        absolute = urljoin(page_url, href)
        parsed = urlparse(absolute)
        if parsed.scheme not in {"http", "https"}:
            other += 1
            counted_other_links.append(href)
            continue

        if _is_internal_link(page_url, absolute):
            internal += 1
            counted_internal_links.append(absolute)
        else:
            external += 1
            counted_external_links.append(absolute)

    link_counts = LinkCounts(internal=internal, external=external, other=other)

    # Images + alt
    imgs = soup.find_all("img")
    total_images = len(imgs)
    missing_alt = 0
    counted_images: list[CountedImageItem] = []
    for img in imgs:
        alt = img.get("alt")
        src = (img.get("src") or "").strip() or None
        is_missing = alt is None or not str(alt).strip()
        if is_missing:
            missing_alt += 1
        counted_images.append(
            CountedImageItem(src=src, alt=(str(alt) if alt is not None else None), counted_missing_alt=is_missing)
        )

    missing_pct = round((missing_alt / total_images) * 100, 2) if total_images else 0.0
    image_stats = ImageAltStats(
        total_images=total_images,
        missing_alt=missing_alt,
        missing_alt_pct=missing_pct,
    )

    # CTA detection required by assignment: buttons plus primary action links.
    strict_cta_elements = []
    strict_cta_texts: list[str] = []
    for a in soup.find_all("a"):
        is_primaryish, text = _is_primary_action_link(a)
        if not is_primaryish:
            continue

        strict_cta_elements.append(a)
        if text:
            strict_cta_texts.append(text)

    for b in soup.find_all("button"):
        text = _first_text(b.get_text(" "), b.get("aria-label") or "")

        strict_cta_elements.append(b)
        if text:
            strict_cta_texts.append(text)

    # Include form submit/button inputs as CTAs.
    for i in soup.find_all("input"):
        i_type = (i.get("type") or "").strip().lower()
        if i_type not in {"submit", "button"}:
            continue
        text = _first_text(i.get("value") or "", i.get("aria-label") or "", i.get("name") or "")
        strict_cta_elements.append(i)
        if text:
            strict_cta_texts.append(text)

    sample_cta_texts = []
    for t in strict_cta_texts:
        if t and t not in sample_cta_texts:
            sample_cta_texts.append(t)
        if len(sample_cta_texts) >= 10:
            break

    cta_count = len(strict_cta_elements)
    counted_cta_texts = [t for t in strict_cta_texts if t]

    # Keep text sample compact for AI: first ~1400 words.
    text_sample_words = words[:1400]
    text_sample = " ".join(text_sample_words)

    return PageMetrics(
        word_count=total_word_count,
        counted_words=words,
        headings=headings,
        heading_texts=heading_texts,
        cta_count=cta_count,
        counted_cta_texts=counted_cta_texts,
        links=link_counts,
        counted_internal_links=counted_internal_links,
        counted_external_links=counted_external_links,
        counted_other_links=counted_other_links,
        images=image_stats,
        counted_images=counted_images,
        meta_title=title,
        meta_description=meta_desc,
        sample_headings=sample_headings,
        sample_cta_texts=sample_cta_texts,
        text_sample=text_sample,
    )
