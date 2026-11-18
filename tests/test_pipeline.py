import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

from bcrp_monitor.config import (
    Config,
    Secrets,
    load_news_settings,
    load_settings,
)
from bcrp_monitor.pipeline import run_monitor
from bcrp_monitor.source import Gazette
from bcrp_monitor.state import State


class FakeSource:
    def __init__(self, results):
        self._results = results
        self.days: list[str] = []

    def fetch_gazette(self, day: str) -> Gazette:
        self.days.append(day)
        return self._results.get(day, Gazette())


class FakeNews:
    def fetch(self):
        return []


class FakeNotifier:
    def send_text(self, text: str) -> bool:
        return True

    def send(self, *args, **kwargs) -> bool:
        return True


def _config() -> Config:
    app, source = load_settings()
    return Config(
        app=app,
        source=source,
        news=load_news_settings(),
        secrets=Secrets("token", "chat", "", "", ""),
    )


class PendingDayTests(unittest.TestCase):
    def test_broken_day_is_persisted_and_reported(self):
        now_local = datetime(2026, 11, 17, 8, 0, tzinfo=timezone(timedelta(hours=-5)))
        now_utc = datetime(2026, 11, 17, 13, 0, tzinfo=timezone.utc)
        source = FakeSource(
            {
                "20261115": Gazette(broken=True),
                "20261114": Gazette(broken=True),
            }
        )
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "state.json"
            State(
                days={
                    "20261117": now_utc.isoformat(),
                    "20261116": now_utc.isoformat(),
                },
                last_run=(now_utc - timedelta(hours=10)).isoformat(),
            ).save(path)
            with (
                mock.patch("bcrp_monitor.pipeline.local_now", return_value=now_local),
                mock.patch("bcrp_monitor.pipeline.utc_now", return_value=now_utc),
                mock.patch(
                    "bcrp_monitor.pipeline._build_source", return_value=source
                ),
                mock.patch(
                    "bcrp_monitor.pipeline._build_news", return_value=FakeNews()
                ),
                mock.patch(
                    "bcrp_monitor.pipeline._notifiers",
                    return_value=(FakeNotifier(), FakeNotifier()),
                ),
                mock.patch("bcrp_monitor.pipeline._heartbeat") as heartbeat,
            ):
                self.assertEqual(run_monitor(_config(), state_path=path), 0)

            state = State.load(path)
            self.assertEqual(set(state.pending), {"20261114", "20261115"})
            self.assertEqual(
                heartbeat.call_args.args[6], ["20261114", "20261115"]
            )

    def test_readable_pending_day_is_cleared(self):
        now_local = datetime(2026, 11, 17, 8, 0, tzinfo=timezone(timedelta(hours=-5)))
        now_utc = datetime(2026, 11, 17, 13, 0, tzinfo=timezone.utc)
        source = FakeSource({"20261113": Gazette(pdf=b"%PDF-1.4 fake")})
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "state.json"
            State(
                days={
                    "20261117": now_utc.isoformat(),
                    "20261116": now_utc.isoformat(),
                    "20261115": now_utc.isoformat(),
                    "20261114": now_utc.isoformat(),
                },
                pending={"20261113": (now_utc - timedelta(days=2)).isoformat()},
                last_run=(now_utc - timedelta(hours=10)).isoformat(),
            ).save(path)
            with (
                mock.patch("bcrp_monitor.pipeline.local_now", return_value=now_local),
                mock.patch("bcrp_monitor.pipeline.utc_now", return_value=now_utc),
                mock.patch(
                    "bcrp_monitor.pipeline._build_source", return_value=source
                ),
                mock.patch(
                    "bcrp_monitor.pipeline._build_news", return_value=FakeNews()
                ),
                mock.patch(
                    "bcrp_monitor.pipeline._notifiers",
                    return_value=(FakeNotifier(), FakeNotifier()),
                ),
                mock.patch("bcrp_monitor.pipeline.parse_pdf", return_value=[]),
                mock.patch("bcrp_monitor.pipeline._heartbeat"),
            ):
                self.assertEqual(run_monitor(_config(), state_path=path), 0)

            state = State.load(path)
            self.assertNotIn("20261113", state.pending)
            self.assertIn("20261113", state.days)


if __name__ == "__main__":
    unittest.main()
