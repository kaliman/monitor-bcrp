"""Google News RSS source for announcements outside El Peruano."""

from __future__ import annotations

import logging
import re
import urllib.parse
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

from .config import NewsSettings
from .http import FetchError, HttpClient

log = logging.getLogger(__name__)


@dataclass
class NewsItem:
    key: str
    title: str
    link: str
    published: datetime
    outlet: str = ""


def _text(node: ET.Element, tag: str) -> str:
    child = node.find(tag)
    if child is None or child.text is None:
        return ""
    return child.text.strip()


def _published(value: str) -> datetime | None:
    try:
        parsed = parsedate_to_datetime(value)
    except (TypeError, ValueError):
        return None
    if parsed is None:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


class GoogleNews:
    def __init__(self, news: NewsSettings, client: HttpClient) -> None:
        self._news = news
        self._client = client

    @property
    def enabled(self) -> bool:
        return self._news.enabled

    def url(self) -> str:
        query = urllib.parse.urlencode({"q": self._news.query})
        separator = "&" if self._news.params else ""
        return f"{self._news.feed_url}?{query}{separator}{self._news.params}"

    def fetch(self) -> list[NewsItem]:
        if not self.enabled:
            return []
        try:
            raw = self._client.get(self.url())
        except FetchError as exc:
            log.warning("News feed unavailable (%s)", type(exc).__name__)
            return []
        try:
            root = ET.fromstring(raw)
        except ET.ParseError as exc:
            log.warning("News feed is not valid XML (%s)", exc)
            return []

        items: dict[str, NewsItem] = {}
        for node in root.iter("item"):
            title = _text(node, "title")
            link = _text(node, "link")
            if not title or not link:
                continue
            if not self._news.title.search(title):
                continue
            if self._news.exclude.search(title):
                continue
            key = _text(node, "guid") or link
            outlet = _text(node, "source")
            if outlet:
                title = re.sub(
                    r"\s+[-–—]\s+" + re.escape(outlet) + r"\s*$",
                    "",
                    title,
                    flags=re.I,
                ).strip()
            items[key] = NewsItem(
                key=key,
                title=title,
                link=link,
                published=_published(_text(node, "pubDate"))
                or datetime.now(timezone.utc),
                outlet=outlet,
            )
        return sorted(
            items.values(), key=lambda item: item.published, reverse=True
        )
