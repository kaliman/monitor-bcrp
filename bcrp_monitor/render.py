"""Message rendering (Telegram HTML and Gmail HTML)."""

from __future__ import annotations

import re
from datetime import datetime
from html import escape, unescape

from .models import Hit


def fmt_day(day: str, messages: dict[str, str]) -> str:
    return datetime.strptime(day, "%Y%m%d").strftime(
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
    day: str, messages: dict[str, str], source_name: str
) -> str:
    header = messages["no_news_header"].format(
        source=escape(source_name), date=fmt_day(day, messages)
    )
    return f"{header}\n{escape(messages['no_news'])}"


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


def plain_of(text: str) -> str:
    return unescape(re.sub(r"<[^>]+>", "", text))
