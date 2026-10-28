"""Configuration loading and validation."""

from __future__ import annotations

import json
import os
import re
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent.parent
SETTINGS_PATH = ROOT / "config" / "settings.toml"
LOCAL_CONFIG_PATH = ROOT / "config.local.json"

REQUIRED_PATHS = {"gazette", "dispositive", "item_pdf", "gazette_pdf"}
REQUIRED_PATTERNS = {
    "section_header_es",
    "dispositive_es",
    "issue_es",
    "item_es",
    "gazette_asset",
    "gazette_number",
    "dispositive_id",
    "dispositive_asset",
    "page_title",
    "title_suffix_es",
    "coin_page_es",
    "coin_denomination_es",
    "coin_alloy_es",
    "coin_mintage_es",
    "coin_effective_es",
}


class ConfigError(Exception):
    """Raised when configuration is missing or invalid."""


@dataclass(frozen=True)
class AppSettings:
    locale: str
    utc_offset_hours: int
    lookback_days: int
    baseline_days: int
    state_retention_days: int
    min_seconds_between_runs: int
    notify_when_nothing: bool
    http_timeout_seconds: int
    pdf_timeout_seconds: int
    http_retries: int
    retry_backoff_seconds: float
    max_candidates: int


@dataclass(frozen=True)
class SourceSettings:
    name: str
    base_url: str
    accept_language: str
    user_agent: str
    paths: dict[str, str]
    patterns: dict[str, re.Pattern[str]]

    def path(self, key: str) -> str:
        try:
            return self.paths[key]
        except KeyError:
            raise ConfigError(f"Missing source path: {key}") from None

    def pattern(self, key: str) -> re.Pattern[str]:
        try:
            return self.patterns[key]
        except KeyError:
            raise ConfigError(f"Missing source pattern: {key}") from None


@dataclass(frozen=True)
class Secrets:
    telegram_bot_token: str
    telegram_chat_id: str
    gmail_user: str
    gmail_app_password: str
    gmail_to: str


@dataclass(frozen=True)
class Config:
    app: AppSettings
    source: SourceSettings
    secrets: Secrets


def _read_toml(path: Path) -> dict[str, Any]:
    try:
        with path.open("rb") as fh:
            data = tomllib.load(fh)
    except FileNotFoundError:
        raise ConfigError(f"Missing settings file: {path}") from None
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"Invalid TOML in {path.name}: {exc}") from None
    if not isinstance(data, dict):
        raise ConfigError(f"{path.name} must contain a TOML table")
    return data


def _read_local(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ConfigError(f"Invalid {path.name}: {exc}") from None
    if not isinstance(data, dict):
        raise ConfigError(f"{path.name} must contain a JSON object")
    return data


def _env(name: str) -> str | None:
    value = os.environ.get(name)
    return value if value not in (None, "") else None


def _as_int(value: Any, label: str) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        raise ConfigError(f"{label} must be an integer") from None


def _as_float(value: Any, label: str) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        raise ConfigError(f"{label} must be a number") from None


def _as_bool(value: Any, label: str) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "on"}:
            return True
        if normalized in {"0", "false", "no", "off"}:
            return False
    raise ConfigError(f"{label} must be a boolean")


def _pick(
    env_name: str, local: dict[str, Any], key: str, default: Any
) -> Any:
    value = _env(env_name)
    if value is not None:
        return value
    if key in local:
        return local[key]
    return default


def _load_app(raw: dict[str, Any], local: dict[str, Any]) -> AppSettings:
    app = raw.get("app")
    if not isinstance(app, dict):
        raise ConfigError("Missing [app] section in settings.toml")

    def required(key: str) -> Any:
        if key not in app:
            raise ConfigError(f"Missing app.{key} in settings.toml")
        return app[key]

    locale = _pick("LOCALE", local, "locale", required("locale"))
    notify = _as_bool(
        _pick(
            "NOTIFY_WHEN_NOTHING",
            local,
            "notify_when_nothing",
            required("notify_when_nothing"),
        ),
        "notify_when_nothing",
    )
    min_seconds = _as_int(
        _pick(
            "MIN_SECONDS_BETWEEN_RUNS",
            local,
            "min_seconds_between_runs",
            required("min_seconds_between_runs"),
        ),
        "min_seconds_between_runs",
    )
    lookback = _as_int(
        _pick("LOOKBACK_DAYS", local, "lookback_days", required("lookback_days")),
        "lookback_days",
    )
    baseline = _as_int(
        _pick("BASELINE_DAYS", local, "baseline_days", required("baseline_days")),
        "baseline_days",
    )
    retention = _as_int(
        _pick(
            "STATE_RETENTION_DAYS",
            local,
            "state_retention_days",
            required("state_retention_days"),
        ),
        "state_retention_days",
    )

    offset = _as_int(required("utc_offset_hours"), "utc_offset_hours")
    if not -12 <= offset <= 14:
        raise ConfigError("utc_offset_hours must be between -12 and 14")

    return AppSettings(
        locale=str(locale).strip().lower(),
        utc_offset_hours=offset,
        lookback_days=lookback,
        baseline_days=baseline,
        state_retention_days=retention,
        min_seconds_between_runs=min_seconds,
        notify_when_nothing=notify,
        http_timeout_seconds=_as_int(
            required("http_timeout_seconds"), "http_timeout_seconds"
        ),
        pdf_timeout_seconds=_as_int(
            required("pdf_timeout_seconds"), "pdf_timeout_seconds"
        ),
        http_retries=_as_int(required("http_retries"), "http_retries"),
        retry_backoff_seconds=_as_float(
            required("retry_backoff_seconds"), "retry_backoff_seconds"
        ),
        max_candidates=_as_int(required("max_candidates"), "max_candidates"),
    )


def _load_source(raw: dict[str, Any]) -> SourceSettings:
    source = raw.get("source")
    if not isinstance(source, dict):
        raise ConfigError("Missing [source] section in settings.toml")

    base_url = str(source.get("base_url") or "")
    parsed = urlparse(base_url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ConfigError("source.base_url must be an absolute http(s) URL")

    paths = source.get("paths")
    if not isinstance(paths, dict):
        raise ConfigError("Missing [source.paths] in settings.toml")
    missing_paths = REQUIRED_PATHS - set(paths)
    if missing_paths:
        raise ConfigError(
            "Missing source paths: " + ", ".join(sorted(missing_paths))
        )
    normalized_paths = {key: str(value) for key, value in paths.items()}

    raw_patterns = source.get("patterns")
    if not isinstance(raw_patterns, dict):
        raise ConfigError("Missing [source.patterns] in settings.toml")
    missing_patterns = REQUIRED_PATTERNS - set(raw_patterns)
    if missing_patterns:
        raise ConfigError(
            "Missing source patterns: " + ", ".join(sorted(missing_patterns))
        )
    patterns: dict[str, re.Pattern[str]] = {}
    for name in sorted(REQUIRED_PATTERNS):
        value = raw_patterns[name]
        if not isinstance(value, str):
            raise ConfigError(f"source.patterns.{name} must be a string")
        try:
            patterns[name] = re.compile(value, re.I)
        except re.error as exc:
            raise ConfigError(f"Invalid regex source.patterns.{name}: {exc}") from None

    return SourceSettings(
        name=str(source.get("name") or "BCRP"),
        base_url=base_url.rstrip("/"),
        accept_language=str(source.get("accept_language") or ""),
        user_agent=str(source.get("user_agent") or ""),
        paths=normalized_paths,
        patterns=patterns,
    )


def load_secrets(
    require_chat_id: bool = True, local_path: Path | None = None
) -> Secrets:
    local = _read_local(local_path or LOCAL_CONFIG_PATH)
    telegram = local.get("telegram") if isinstance(local.get("telegram"), dict) else {}
    gmail = local.get("gmail") if isinstance(local.get("gmail"), dict) else {}

    token = os.environ.get(
        "TELEGRAM_BOT_TOKEN", str((telegram or {}).get("bot_token") or "")
    )
    chat_id = os.environ.get(
        "TELEGRAM_CHAT_ID", str((telegram or {}).get("chat_id") or "")
    )
    user = os.environ.get("GMAIL_USER", str((gmail or {}).get("user") or ""))
    app_password = os.environ.get(
        "GMAIL_APP_PASSWORD", str((gmail or {}).get("app_password") or "")
    )
    recipient = os.environ.get(
        "GMAIL_TO", str((gmail or {}).get("to") or "")
    ) or user

    if require_chat_id:
        if not token.strip():
            raise ConfigError("TELEGRAM_BOT_TOKEN is required")
        if not chat_id.strip():
            raise ConfigError("TELEGRAM_CHAT_ID is required")

    return Secrets(
        telegram_bot_token=token.strip(),
        telegram_chat_id=chat_id.strip(),
        gmail_user=user.strip(),
        gmail_app_password=app_password.strip(),
        gmail_to=recipient.strip(),
    )


def load_settings(
    settings_path: Path | None = None, local_path: Path | None = None
) -> tuple[AppSettings, SourceSettings]:
    raw = _read_toml(settings_path or SETTINGS_PATH)
    local = _read_local(local_path or LOCAL_CONFIG_PATH)
    return _load_app(raw, local), _load_source(raw)


def load_config(
    require_chat_id: bool = True,
    settings_path: Path | None = None,
    local_path: Path | None = None,
) -> Config:
    app, source = load_settings(settings_path, local_path)
    secrets = load_secrets(require_chat_id, local_path)
    return Config(app=app, source=source, secrets=secrets)
