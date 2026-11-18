"""Monitor orchestration."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from .config import Config
from .constants import BASELINE_MARKER, DAY_FORMAT
from .extract import mark_relevant, parse_pdf
from .http import HttpClient
from .i18n import load_locale
from .models import Hit
from .news import GoogleNews
from .notify import Gmail, Telegram
from .render import (
    hit_caption,
    hit_subject,
    no_news_subject,
    pending_subject,
    plain_of,
    render_hit,
    render_news,
    render_no_news,
)
from .source import ElPeruano
from .state import STATE_PATH, State
from pathlib import Path

log = logging.getLogger(__name__)


def _tz(config: Config):
    return timezone(timedelta(hours=config.app.utc_offset_hours))


def local_now(config: Config) -> datetime:
    return datetime.now(_tz(config))


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: datetime) -> str:
    return value.isoformat(timespec="seconds")


def local_day(config: Config) -> str:
    return local_now(config).strftime(DAY_FORMAT)


def _build_source(config: Config) -> ElPeruano:
    client = HttpClient(
        config.source,
        timeout=config.app.http_timeout_seconds,
        retries=config.app.http_retries,
        backoff_seconds=config.app.retry_backoff_seconds,
    )
    return ElPeruano(
        config.source,
        client,
        pdf_timeout=config.app.pdf_timeout_seconds,
        max_candidates=config.app.max_candidates,
    )


def _build_news(config: Config) -> GoogleNews:
    client = HttpClient(
        config.source,
        timeout=config.app.http_timeout_seconds,
        retries=config.app.http_retries,
        backoff_seconds=config.app.retry_backoff_seconds,
    )
    return GoogleNews(config.news, client)


def _notifiers(config: Config) -> tuple[Telegram, Gmail]:
    telegram = Telegram(
        config.secrets,
        timeout=config.app.http_timeout_seconds,
        pdf_timeout=config.app.pdf_timeout_seconds,
    )
    gmail = Gmail(config.secrets, timeout=config.app.http_timeout_seconds)
    return telegram, gmail


def _deliver(
    config: Config,
    messages: dict[str, str],
    source: ElPeruano,
    telegram: Telegram,
    gmail: Gmail,
    day: str,
    hits: list[Hit],
    dry: bool,
) -> list[Hit]:
    delivered: list[Hit] = []
    for hit in hits:
        text = render_hit(day, hit, messages)
        filename = f"{hit.kind.replace(' ', '-').lower()}-{hit.number}.pdf"
        pdf = source.fetch_item_pdf(hit)
        if dry:
            log.info(
                "DRY-RUN\n%s\n[pdf: %s]",
                plain_of(text),
                len(pdf) if pdf else "none",
            )
            delivered.append(hit)
            continue

        sent = telegram.send_text(text)
        if pdf:
            sent = (
                telegram.send_pdf(
                    pdf, filename, hit_caption(hit, messages, config.source.name)
                )
                or sent
            )
        sent = (
            gmail.send(
                hit_subject(hit, messages, config.source.name),
                text.replace("\n", "<br>"),
                pdf,
                filename,
            )
            or sent
        )
        if sent:
            delivered.append(hit)
        else:
            log.error("Notification failed for %s %s", hit.kind, hit.number)
    return delivered


def _heartbeat(
    config: Config,
    messages: dict[str, str],
    telegram: Telegram,
    gmail: Gmail,
    now: datetime,
    dry: bool,
    pending_days: list[str] | None = None,
) -> None:
    day = now.strftime(DAY_FORMAT)
    text = render_no_news(day, messages, config.source.name, pending_days)
    subject = (
        pending_subject(day, messages, config.source.name)
        if pending_days
        else no_news_subject(day, messages, config.source.name)
    )
    if dry:
        log.info("DRY-RUN\n%s", plain_of(text))
        return
    telegram.send_text(text)
    gmail.send(subject, text.replace("\n", "<br>"))


def _parse_cooldown(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _news_alert(
    config: Config,
    messages: dict[str, str],
    news: GoogleNews,
    state: State,
    telegram: Telegram,
    gmail: Gmail,
    now: datetime,
    dry: bool,
    force: bool = False,
) -> bool:
    items = news.fetch()
    if not items:
        return False

    stamp = _iso(now)
    fresh = [item for item in items if item.key not in state.news_seen]
    if state.news_last_check is None and not force:
        for item in fresh:
            state.news_seen[item.key] = stamp
        state.news_last_check = stamp
        log.info("News baseline established (%d headline(s)).", len(fresh))
        return False

    state.news_last_check = stamp
    if not fresh:
        return False

    last_alert = _parse_cooldown(state.news_last_alert)
    if last_alert and not force:
        elapsed = (now - last_alert).total_seconds()
        if elapsed < config.news.cooldown_hours * 3600:
            log.info(
                "News alert on cooldown; %d headline(s) held.", len(fresh)
            )
            return False

    shown = fresh[: config.news.max_items]
    text = render_news(shown, messages, config.source.name)
    subject = messages["subject_news"].format(source=config.source.name)
    if dry:
        log.info("DRY-RUN\n%s", plain_of(text))
        return True

    sent = telegram.send_text(text)
    sent = gmail.send(subject, text.replace("\n", "<br>")) or sent
    if sent:
        for item in fresh:
            state.news_seen[item.key] = stamp
        state.news_last_alert = stamp
        log.info("News: %d headline(s) notified.", len(shown))
    else:
        log.error("News notification failed")
    return sent


def run_monitor(
    config: Config,
    dry: bool = False,
    reset_state: bool = False,
    state_path: Path | None = None,
) -> int:
    messages = load_locale(config.app.locale)
    state = State() if reset_state else State.load(state_path or STATE_PATH)
    now_local = local_now(config)
    now_utc = utc_now()

    first_run = not state.days and not state.seen and not state.last_run
    if first_run:
        for back in range(1, config.app.baseline_days + 1):
            state.days[(now_local - timedelta(days=back)).strftime(DAY_FORMAT)] = (
                BASELINE_MARKER
            )
        log.info("First run: baseline established.")

    if state.last_run and not dry:
        try:
            last = datetime.fromisoformat(state.last_run)
            if last.tzinfo is None:
                last = last.replace(tzinfo=timezone.utc)
            gap = (now_utc - last.astimezone(timezone.utc)).total_seconds()
            if gap < config.app.min_seconds_between_runs:
                log.info(
                    "Last run %d s ago (min %d); skipping.",
                    gap,
                    config.app.min_seconds_between_runs,
                )
                return 0
        except ValueError:
            pass

    window = {
        (now_local - timedelta(days=back)).strftime(DAY_FORMAT)
        for back in range(config.app.lookback_days)
    }
    pending = sorted((window | set(state.pending)) - set(state.days))
    today = now_local.strftime(DAY_FORMAT)

    source = _build_source(config)
    news = _build_news(config)
    telegram, gmail = _notifiers(config)
    alerted = False
    broken: list[str] = []

    for day in pending:
        gazette = source.fetch_gazette(day)
        if not gazette.pdf:
            if gazette.broken:
                state.pending.setdefault(day, _iso(now_utc))
                if day < today:
                    broken.append(day)
            continue
        state.pending.pop(day, None)
        pdf = gazette.pdf
        hits = parse_pdf(pdf, config.source)
        for hit in hits:
            source.resolve(hit)
        mark_relevant(hits, config.source)
        relevant = [
            hit for hit in hits if hit.relevant and hit.key not in state.seen
        ]
        if relevant:
            delivered = _deliver(
                config, messages, source, telegram, gmail, day, relevant, dry
            )
            stamp = _iso(now_utc)
            for hit in delivered:
                state.seen[hit.key] = stamp
            alerted = alerted or bool(delivered)
            if len(delivered) < len(relevant):
                log.warning(
                    "Some notifications failed; the day will be retried."
                )
                continue
        state.days[day] = _iso(now_utc)

    news_alerted = _news_alert(
        config, messages, news, state, telegram, gmail, now_utc, dry
    )

    if (
        not alerted
        and not news_alerted
        and config.app.notify_when_nothing
    ):
        _heartbeat(
            config, messages, telegram, gmail, now_local, dry, broken
        )

    if not dry:
        state.last_run = _iso(now_utc)
        state.prune(
            config.app.state_retention_days,
            pending_retention_days=config.app.pending_retention_days,
        )
        state.save(state_path or STATE_PATH)

    if not pending:
        log.info("No new days; notified anyway.")
    return 0


def probe(config: Config, day: str, dry: bool = False) -> int:
    messages = load_locale(config.app.locale)
    source = _build_source(config)
    gazette = source.fetch_gazette(day)
    if not gazette.pdf:
        log.error("Could not download the gazette for %s", day)
        return 1

    hits = parse_pdf(gazette.pdf, config.source)
    for hit in hits:
        source.resolve(hit)
    mark_relevant(hits, config.source)
    log.info("BCRP dispositives found: %d", len(hits))
    for hit in hits:
        mark = "COIN" if hit.relevant else " -- "
        print(f"[{mark}] {hit.kind} {hit.number} | {hit.title[:95]}")
    picked = [hit for hit in hits if hit.relevant]
    log.info("Matching the filter: %d", len(picked))
    if not hits:
        return 1

    telegram, gmail = _notifiers(config)
    _deliver(config, messages, source, telegram, gmail, day, picked, dry)
    return 0


def backfill(
    config: Config,
    days: list[str],
    dry: bool = False,
    state_path: Path | None = None,
) -> int:
    """Process specific days that were skipped by the regular window."""
    messages = load_locale(config.app.locale)
    state = State.load(state_path or STATE_PATH)
    source = _build_source(config)
    telegram, gmail = _notifiers(config)
    now_utc = utc_now()
    failures = 0

    for day in sorted(set(days)):
        gazette = source.fetch_gazette(day)
        if not gazette.pdf:
            log.error("Could not download the gazette for %s", day)
            failures += 1
            continue
        hits = parse_pdf(gazette.pdf, config.source)
        for hit in hits:
            source.resolve(hit)
        mark_relevant(hits, config.source)
        relevant = [
            hit for hit in hits if hit.relevant and hit.key not in state.seen
        ]
        if relevant:
            delivered = _deliver(
                config, messages, source, telegram, gmail, day, relevant, dry
            )
            stamp = _iso(now_utc)
            for hit in delivered:
                state.seen[hit.key] = stamp
            if len(delivered) < len(relevant):
                failures += 1
                log.warning(
                    "Some notifications failed for %s; not marking it.", day
                )
                continue
        state.days[day] = _iso(now_utc)
        state.pending.pop(day, None)
        log.info("Backfill: day %s processed.", day)

    if not dry:
        state.last_run = _iso(now_utc)
        state.save(state_path or STATE_PATH)
    return 1 if failures else 0


def check_news(config: Config, dry: bool = False) -> int:
    messages = load_locale(config.app.locale)
    state = State.load()
    news = _build_news(config)
    telegram, gmail = _notifiers(config)
    now = utc_now()
    _news_alert(
        config, messages, news, state, telegram, gmail, now, dry, force=True
    )
    if not dry:
        state.save()
    return 0


def send_test(config: Config, dry: bool = False) -> int:
    messages = load_locale(config.app.locale)
    text = messages["test_message"].format(source=config.source.name)
    if dry:
        log.info("DRY-RUN\n%s", plain_of(text))
        return 0
    telegram, gmail = _notifiers(config)
    telegram.send_text(text)
    gmail.send(
        messages["subject_test"].format(source=config.source.name),
        text.replace("\n", "<br>"),
    )
    return 0
