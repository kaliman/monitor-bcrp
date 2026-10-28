"""El Peruano source: URL construction and document retrieval."""

from __future__ import annotations

import logging
from html import unescape
from urllib.parse import urljoin

from .config import SourceSettings
from .http import FetchError, HttpClient
from .models import Hit

log = logging.getLogger(__name__)


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

    def fetch_gazette(self, day: str) -> bytes | None:
        page_url = self.url_for("gazette", day=day)
        try:
            page = self._client.get(page_url).decode("utf-8", "replace")
        except FetchError as exc:
            log.info("Gazette %s unavailable (%s)", day, type(exc).__name__)
            return None

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
            return None

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
            return None
        if data[:4] != b"%PDF":
            log.warning("Gazette PDF %s is not a PDF", day)
            return None
        return data

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
        return data if data[:4] == b"%PDF" else None
