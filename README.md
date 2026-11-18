# monitor-bcrp

Watches the Central Reserve Bank of Peru (BCRP) in the official gazette
*El Peruano* and sends a Telegram message and an email, with the official PDF
attached, whenever the BCRP puts a coin, medal or banknote into circulation.

Runs on GitHub Actions. No local scheduler is needed.

## How it works

1. Downloads the daily gazette PDF for the last few days.
2. Extracts the BCRP section and resolves each dispositive to its official page
   and PDF.
3. Keeps the dispositives whose official title matches the issue filter.
4. Sends the notice through Telegram (text + PDF) and Gmail (HTML + PDF).
5. Checks a filtered Google News feed for BCRP coin or medal announcements
   that never reach the gazette (medals are not legal tender, so they often
   have no dispositive in *El Peruano*).
6. Persists `state.json` so nothing is notified twice and unreadable gazette
   days are retried for up to `pending_retention_days`.

## Layout

```
bcrp_monitor/
  cli.py          CLI and logging
  config.py       env + config.local.json + settings.toml loader
  constants.py    protocol and format constants (Telegram, SMTP, PDF)
  http.py         HTTP client with retries
  source.py       El Peruano URLs and downloads
  news.py         Google News RSS feed for press announcements
  extract.py      PDF parsing
  render.py       Telegram/Gmail message rendering
  notify.py       Telegram and Gmail adapters
  state.py        state v2 (no personal data)
  i18n.py         locale loader
  pipeline.py     orchestration
config/settings.toml   source URLs, headers, patterns, defaults (non-secret)
locales/{es,en}.json   user-facing messages
tests/                 unit tests, no network
monitor.py             compatibility entry point
```

## Requirements

- Python 3.11+ (`tomllib`)
- `pypdf` (pinned in `requirements.txt`)

## Configuration

Non-secret defaults and all site-specific values live in
`config/settings.toml`:

- `[app]`: locale, UTC offset, lookback/baseline days, retries, timeouts,
  state retention, retry window for unreadable gazettes.
- `[source]`: base URL, `Accept-Language`, user agent.
- `[source.paths]`: URL templates.
- `[source.patterns]`: regexes used to parse the Spanish PDF. Keys keep the
  `_es` suffix because they match Spanish text.
- `[news]`: Google News query and the title filters that keep only BCRP coin
  or medal announcements. Set `enabled = false` to disable the press check.

Secrets are never committed. Provide them locally in `config.local.json`
(gitignored) or through environment variables. Environment variables take
precedence:

| Variable | Required | Purpose |
| --- | --- | --- |
| `TELEGRAM_BOT_TOKEN` | yes | Telegram bot token. |
| `TELEGRAM_CHAT_ID` | yes | Telegram destination chat. |
| `GMAIL_USER` | for email | Gmail sender account. |
| `GMAIL_APP_PASSWORD` | for email | Google app password. |
| `GMAIL_TO` | no | Recipient; defaults to `GMAIL_USER`. |
| `LOCALE` | no | `es` (default) or `en`. |
| `NOTIFY_WHEN_NOTHING` | no | Send a heartbeat on every run. |
| `MIN_SECONDS_BETWEEN_RUNS` | no | Anti-duplicate guard. |
| `LOOKBACK_DAYS`, `BASELINE_DAYS` | no | Processing window. |

Local `config.local.json` (see `config.example.json`):

```json
{
  "telegram": {"bot_token": "...", "chat_id": "..."},
  "gmail": {"user": "...", "app_password": "...", "to": "..."},
  "locale": "es"
}
```

## Local setup

```bash
python -m pip install -r requirements.txt
cp config.example.json config.local.json
python telegram_setup.py          # discovers the chat_id and saves it
python -m bcrp_monitor --test     # sends a test message
```

If several Telegram chats are found, `telegram_setup.py` asks for an explicit
`--chat-id`.

Useful commands:

```bash
python -m bcrp_monitor --dry-run          # parse, print, send nothing
python -m bcrp_monitor --probe 20260618   # inspect one day (YYYYMMDD)
python -m bcrp_monitor --backfill 20261113  # process a missed day
python -m bcrp_monitor --news --dry-run   # inspect the press feed only
python -m bcrp_monitor --test             # send a test message
python -m bcrp_monitor                    # normal run
python -m bcrp_monitor --reset-state      # ignore history, rebuild baseline
```

## GitHub Actions

`.github/workflows/monitor.yml` runs every 6 hours
(`cron: "10 1,7,13,19 * * *"`, UTC) and supports `workflow_dispatch`.
`.github/workflows/ci.yml` runs compile and unit tests on every push and pull
request.

### Secrets

**Settings → Secrets and variables → Actions → Secrets**:

| Secret | Required | Purpose |
| --- | --- | --- |
| `TELEGRAM_BOT_TOKEN` | yes | Telegram bot token. |
| `TELEGRAM_CHAT_ID` | yes | Telegram destination chat. |
| `GMAIL_USER` | for email | Gmail sender account. |
| `GMAIL_APP_PASSWORD` | for email | Google app password. |
| `GMAIL_TO` | no | Recipient; defaults to `GMAIL_USER`. |

Optional repository variable: `LOCALE` (`es` by default).

### State

`state.json` is committed on purpose: Actions runners are ephemeral and the
workflow uses it as a checkpoint between runs. It contains no personal data:

```json
{
  "version": 2,
  "seen": {"Circular:0013-2026": "2026-06-18T00:00:00+00:00"},
  "days": {"20260618": "2026-06-18T00:00:00+00:00"},
  "pending": {"20261113": "2026-11-13T20:27:00+00:00"},
  "news_seen": {"guid": "2026-11-09T14:05:00+00:00"},
  "news_last_check": "2026-11-09T14:05:00+00:00",
  "news_last_alert": "2026-11-09T14:05:00+00:00",
  "last_run": "2026-06-18T01:00:00+00:00"
}
```

- `seen`: dispositives already notified.
- `days`: days already processed.
- `pending`: days whose gazette page exists but whose PDF could not be read;
  they are retried for `pending_retention_days` and reported in the heartbeat.
- `news_seen`, `news_last_check`, `news_last_alert`: press-feed deduplication
  and alert cooldown.
- `last_run`: UTC timestamp for the cooldown guard.

A fork inherits the baseline. To start fresh, delete `state.json` or run with
`--reset-state`.

## Filter

A dispositive is notified only when its official title matches both
`source.patterns.issue_es` and `source.patterns.item_es`. There is no
restriction on denomination or topic. The regexes live in
`config/settings.toml`; the code never hardcodes site URLs, headers or
patterns.

The press feed is narrower: it only accepts titles that match
`news.title_es` (BCRP plus coin/medal/banknote) and rejects
`news.exclude_es` (civic medals, awards, exchange-rate noise). Alerts are
deduplicated by Google News id and limited to one batch every
`news.cooldown_hours`. The first run only records a baseline, so deploying a
new feed does not replay old headlines.

## Security

- No secrets, chat ids or email addresses are written to the repository or to
  logs. Config files with secrets are gitignored.
- Actions are pinned by commit SHA; dependencies are pinned by version.
- Enable GitHub secret scanning and push protection for the public repository.
- If a bot token is ever exposed, revoke it in BotFather (`/mybots` → API
  Token → Revoke current token), then update `TELEGRAM_BOT_TOKEN` in the
  repository secrets and in `config.local.json`. The old token stops working
  immediately; the chat id does not change.
- Rotate the Gmail app password from the Google account settings if needed.

## Localization

Messages live in `locales/<code>.json`. `locale` selects the file; the loader
falls back to Spanish for missing files or keys. To add a language, copy
`locales/es.json`, translate the values, and save it as `locales/<code>.json`.
Never translate the `_es` regexes: they match Spanish source text.
