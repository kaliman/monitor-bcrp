"""PDF text extraction and dispositive parsing."""

from __future__ import annotations

import io
import logging
import re

from pypdf import PdfReader

from .config import SourceSettings
from .models import Hit

log = logging.getLogger(__name__)


def pages_of(pdf: bytes) -> list[str]:
    reader = PdfReader(io.BytesIO(pdf))
    pages: list[str] = []
    for page in reader.pages:
        try:
            pages.append(re.sub(r"\s+", " ", page.extract_text() or ""))
        except Exception:
            pages.append("")
    log.info("PDF has %d pages", len(pages))
    return pages


def _grab(block: str, pattern: re.Pattern[str]) -> str:
    match = pattern.search(block)
    if not match:
        return ""
    return re.sub(r"\s+", " ", match.group(1)).strip(" .;")


def _coin_details(pages: list[str], source: SourceSettings) -> dict[str, dict]:
    details: dict[str, dict] = {}
    page_pattern = source.pattern("coin_page_es")
    for index, text in enumerate(pages):
        for match in page_pattern.finditer(text):
            block = text + " " + (pages[index + 1] if index + 1 < len(pages) else "")
            body = block[match.start():]
            denomination = _grab(body, source.pattern("coin_denomination_es"))
            if not denomination:
                continue
            details[match.group(1)] = {
                "denomination": denomination,
                "alloy": _grab(body, source.pattern("coin_alloy_es")),
                "mintage": _grab(body, source.pattern("coin_mintage_es")),
                "effective": _grab(body, source.pattern("coin_effective_es")),
            }
    return details


def parse_pages(pages: list[str], source: SourceSettings) -> list[Hit]:
    details = _coin_details(pages, source)
    dispositive_pattern = source.pattern("dispositive_es")
    id_pattern = source.pattern("dispositive_id")
    header_pattern = source.pattern("section_header_es")

    hits: dict[tuple[str, str], Hit] = {}
    for index, text in enumerate(pages):
        if not header_pattern.search(text):
            continue
        for match in dispositive_pattern.finditer(text):
            kind = re.sub(r"\s+", " ", match.group(1)).title()
            number = match.group(2)
            dedupe_key = (kind.split()[0], number)
            block = text + " " + (pages[index + 1] if index + 1 < len(pages) else "")
            ids = id_pattern.findall(block[match.start():])
            hit = Hit(
                kind=kind,
                number=number,
                page=index + 1,
                ids=ids,
            )
            if kind.lower().startswith("circular"):
                hit.denomination = details.get(number, {}).get("denomination", "")
                hit.alloy = details.get(number, {}).get("alloy", "")
                hit.mintage = details.get(number, {}).get("mintage", "")
                hit.effective = details.get(number, {}).get("effective", "")
            existing = hits.get(dedupe_key)
            if existing is None or len(hit.ids) > len(existing.ids):
                hits[dedupe_key] = hit
    return list(hits.values())


def parse_pdf(pdf: bytes, source: SourceSettings) -> list[Hit]:
    return parse_pages(pages_of(pdf), source)


def mark_relevant(hits: list[Hit], source: SourceSettings) -> None:
    issue = source.pattern("issue_es")
    item = source.pattern("item_es")
    for hit in hits:
        hit.relevant = bool(issue.search(hit.title) and item.search(hit.title))
