"""Message rendering (Telegram HTML and Gmail HTML)."""

from __future__ import annotations

import re
from datetime import datetime
from html import escape, unescape

from .constants import DAY_FORMAT
from .models import Hit
from .news import NewsItem


def fmt_day(day: str, messages: dict[str, str]) -> str:
    return datetime.strptime(day, DAY_FORMAT).strftime(
        messages.get("date_format", "%d/%m/%Y")
    )


def render_hit(day: str, hit: Hit, messages: dict[str, str]) -> str:
    lines = [
        messages["hit_header"].format(
            kind=escape(hit.kind), number=escape(hit.number)
        ),
        escape(messages["gazette_line"].format(date=fmt_day(day, messages))),
    ]
    if hit.title:
        lines.append(escape(hit.title))

    extras = [escape(value) for value in (hit.denomination, hit.alloy, hit.mintage) if value]
    if hit.effective:
        extras.append(
            escape(messages["since"].format(date=hit.effective))
        )
    if extras:
        lines.append(" · ".join(extras))
    if hit.url:
        lines.append(escape(hit.url, quote=True))
    return "\n".join(lines)


def render_no_news(
    day: str,
    messages: dict[str, str],
    source_name: str,
    pending_days: list[str] | None = None,
) -> str:
    header = messages["no_news_header"].format(
        source=escape(source_name), date=fmt_day(day, messages)
    )
    lines = [header, escape(messages["no_news"])]
    if pending_days:
        dates = ", ".join(fmt_day(value, messages) for value in sorted(pending_days))
        lines.append(escape(messages["pending_line"].format(dates=dates)))
    return "\n".join(lines)


def render_news(
    items: list[NewsItem], messages: dict[str, str], source_name: str
) -> str:
    lines = [
        messages["news_header"].format(source=escape(source_name)),
    ]
    for item in items:
        if item.outlet:
            line = messages["news_outlet"].format(
                title=escape(item.title), outlet=escape(item.outlet)
            )
        else:
            line = messages["news_item"].format(title=escape(item.title))
        lines.append(line)
        lines.append(escape(item.link, quote=True))
    lines.append(escape(messages["news_hint"]))
    return "\n".join(lines)


def hit_subject(hit: Hit, messages: dict[str, str], source_name: str) -> str:
    return messages["subject_hit"].format(
        source=source_name, kind=hit.kind, number=hit.number
    )


def hit_caption(hit: Hit, messages: dict[str, str], source_name: str) -> str:
    return messages["hit_caption"].format(
        source=source_name, kind=hit.kind, number=hit.number
    )


def no_news_subject(
    day: str, messages: dict[str, str], source_name: str
) -> str:
    return messages["subject_no_news"].format(
        source=source_name, date=fmt_day(day, messages)
    )


def pending_subject(
    day: str, messages: dict[str, str], source_name: str
) -> str:
    return messages["subject_pending"].format(
        source=source_name, date=fmt_day(day, messages)
    )


def plain_of(text: str) -> str:
    return unescape(re.sub(r"<[^>]+>", "", text))
