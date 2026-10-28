"""Locale loading."""

from __future__ import annotations

import json
import logging
from pathlib import Path

from .config import ConfigError, ROOT

log = logging.getLogger(__name__)

LOCALES_DIR = ROOT / "locales"
DEFAULT_LOCALE = "es"

REQUIRED_KEYS = {
    "date_format",
    "hit_header",
    "hit_caption",
    "gazette_line",
    "since",
    "no_news_header",
    "no_news",
    "subject_hit",
    "subject_no_news",
    "subject_test",
    "test_message",
}


def _read(locale: str, locales_dir: Path) -> dict[str, str] | None:
    path = locales_dir / f"{locale}.json"
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ConfigError(f"Invalid locale {path.name}: {exc}") from None
    if not isinstance(data, dict):
        raise ConfigError(f"Locale {path.name} must contain a JSON object")
    return {str(key): str(value) for key, value in data.items()}


def load_locale(locale: str, locales_dir: Path | None = None) -> dict[str, str]:
    directory = locales_dir or LOCALES_DIR
    base = _read(DEFAULT_LOCALE, directory)
    if base is None:
        raise ConfigError(f"Missing locale file: {DEFAULT_LOCALE}.json")

    name = (locale or DEFAULT_LOCALE).strip().lower()
    if name == DEFAULT_LOCALE:
        messages = base
    else:
        selected = _read(name, directory)
        if selected is None:
            log.warning(
                "Locale '%s' not found; falling back to '%s'", name, DEFAULT_LOCALE
            )
            messages = base
        else:
            messages = {**base, **selected}

    missing = REQUIRED_KEYS - set(messages)
    if missing:
        raise ConfigError(
            "Missing locale keys: " + ", ".join(sorted(missing))
        )
    return messages
