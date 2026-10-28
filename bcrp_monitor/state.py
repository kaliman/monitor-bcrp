"""Persistent state: processed days, notified dispositives and last run."""

from __future__ import annotations

import json
import logging
import os
import tempfile
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .config import ROOT

log = logging.getLogger(__name__)

STATE_VERSION = 2
STATE_PATH = ROOT / "state.json"


class StateError(Exception):
    """Raised when state cannot be read or is not supported."""


def _to_utc(value: str) -> str:
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return value
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).isoformat(timespec="seconds")


def _normalize_map(values: dict, label: str) -> dict[str, str]:
    if not isinstance(values, dict):
        raise StateError(f"state.{label} must be an object")
    normalized: dict[str, str] = {}
    for key, value in values.items():
        if not isinstance(key, str) or not isinstance(value, str):
            raise StateError(f"state.{label} must map strings to strings")
        normalized[key] = "baseline" if value == "baseline" else _to_utc(value)
    return normalized


@dataclass
class State:
    seen: dict[str, str] = field(default_factory=dict)
    days: dict[str, str] = field(default_factory=dict)
    last_run: str | None = None

    @classmethod
    def load(cls, path: Path | None = None) -> "State":
        state_path = path or STATE_PATH
        if not state_path.exists():
            return cls()
        try:
            data = json.loads(state_path.read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError) as exc:
            raise StateError(f"Invalid {state_path.name}: {exc}") from None
        if not isinstance(data, dict):
            raise StateError(f"{state_path.name} must contain a JSON object")

        version = data.get("version")
        if version == STATE_VERSION:
            last_run = data.get("last_run")
            return cls(
                seen=_normalize_map(data.get("seen", {}), "seen"),
                days=_normalize_map(data.get("days", {}), "days"),
                last_run=_to_utc(last_run) if isinstance(last_run, str) else None,
            )
        if version is None and "owner" in data:
            log.info("Migrating state v1 to v%d", STATE_VERSION)
            last_run = data.get("last_run")
            return cls(
                seen=_normalize_map(data.get("seen", {}), "seen"),
                days=_normalize_map(data.get("days", {}), "days"),
                last_run=_to_utc(last_run) if isinstance(last_run, str) else None,
            )
        raise StateError(f"Unsupported state version: {version!r}")

    def save(self, path: Path | None = None) -> None:
        state_path = path or STATE_PATH
        payload = {
            "version": STATE_VERSION,
            "seen": self.seen,
            "days": self.days,
            "last_run": self.last_run,
        }
        state_path.parent.mkdir(parents=True, exist_ok=True)
        handle = tempfile.NamedTemporaryFile(
            "w",
            dir=state_path.parent,
            delete=False,
            encoding="utf-8",
            newline="\n",
        )
        try:
            with handle:
                json.dump(payload, handle, indent=2, ensure_ascii=False)
                handle.write("\n")
            os.replace(handle.name, state_path)
        except Exception:
            try:
                os.unlink(handle.name)
            except OSError:
                pass
            raise

    def prune(self, retention_days: int, now: datetime | None = None) -> None:
        reference = now or datetime.now(timezone.utc)
        cutoff = reference - timedelta(days=max(0, retention_days))

        def keep(value: str) -> bool:
            if value == "baseline":
                return True
            try:
                parsed = datetime.fromisoformat(value)
            except ValueError:
                return True
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed >= cutoff

        self.seen = {key: value for key, value in self.seen.items() if keep(value)}
        self.days = {key: value for key, value in self.days.items() if keep(value)}
