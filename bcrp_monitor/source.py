"""El Peruano source: URL construction and document retrieval."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from html import unescape
from urllib.parse import urljoin

from .config import SourceSettings
from .constants import PDF_MAGIC
from .http import FetchError, HttpClient
from .models import Hit

log = logging.getLogger(__name__)


@dataclass
class Gazette:
    """Result of looking up one day of the gazette.

    ``pdf`` is set when the edition was downloaded. ``broken`` marks a page
    that exists but does not expose a usable PDF link: it must be retried
    later instead of being treated as "no edition".
    """

    pdf: bytes | None = None
    broken: bool = False


class ElPeruano:
    def __init__(
        self,
        source: SourceSettings,
        client: HttpClient,
        pdf_timeout: int,
        max_candidates: int,
    ) -> None:
        self._source = source
        self._client = client
        self._pdf_timeout = pdf_timeout
        self._max_candidates = max_candidates

    def url_for(self, key: str, **params: str) -> str:
        path = self._source.path(key).lstrip("/").format(**params)
        return urljoin(self._source.base_url + "/", path)

    def fetch_gazette(self, day: str) -> Gazette:
        page_url = self.url_for("gazette", day=day)
        try:
            page = self._client.get(page_url).decode("utf-8", "replace")
        except FetchError as exc:
            log.info("Gazette %s unavailable (%s)", day, type(exc).__name__)
            return Gazette()

        link_match = next(
            (
                match
                for match in self._source.pattern("gazette_pdf_link").finditer(page)
                if match.group(2).startswith(f"NL{day}")
            ),
            None,
        )
        if link_match:
            pdf_url = self.url_for(
                "gazette_file",
                asset=link_match.group(1),
                filename=link_match.group(2),
            )
        else:
            asset_match = self._source.pattern("gazette_asset").search(page)
            number_match = next(
                (
                    match
                    for match in self._source.pattern("gazette_number").finditer(page)
                    if match.group(1) == day
                ),
                None,
            )
            if not asset_match or not number_match:
                log.warning("Gazette %s has no PDF link", day)
                return Gazette(broken=True)
            pdf_url = self.url_for(
                "gazette_pdf",
                asset=asset_match.group(1),
                day=day,
                num=number_match.group(2),
            )

        try:
            data = self._client.get(pdf_url, timeout=self._pdf_timeout)
        except FetchError as exc:
            log.warning("Gazette PDF %s failed (%s)", day, type(exc).__name__)
            return Gazette(broken=True)
        if not data.startswith(PDF_MAGIC):
            log.warning("Gazette PDF %s is not a PDF", day)
            return Gazette(broken=True)
        return Gazette(pdf=data)

    def resolve(self, hit: Hit) -> None:
        for cid in hit.ids[: self._max_candidates]:
            try:
                page = self._client.get(
                    self.url_for("dispositive", cid=cid)
                ).decode("utf-8", "replace")
            except FetchError:
                continue
            if hit.number not in page:
                continue

            title_match = self._source.pattern("page_title").search(page)
            title = unescape(title_match.group(1)).strip() if title_match else ""
            if title:
                title = self._source.pattern("title_suffix_es").sub("", title).strip()

            asset_match = self._source.pattern("dispositive_asset").search(page)
            hit.slug = cid
            hit.title = title
            hit.asset = asset_match.group(1) if asset_match else None
            hit.url = self.url_for("dispositive", cid=cid)
            return

    def fetch_item_pdf(self, hit: Hit) -> bytes | None:
        if not (hit.asset and hit.slug):
            return None
        url = self.url_for("item_pdf", asset=hit.asset, cid=hit.slug)
        try:
            data = self._client.get(url, timeout=self._pdf_timeout)
        except FetchError as exc:
            log.warning(
                "PDF for %s %s failed (%s)",
                hit.kind,
                hit.number,
                type(exc).__name__,
            )
            return None
        return data if data.startswith(PDF_MAGIC) else None
