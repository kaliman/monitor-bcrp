import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from bcrp_monitor.state import State, StateError


class StateTests(unittest.TestCase):
    def test_round_trip_has_no_owner(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "state.json"
            state = State(
                seen={"Circular:0013-2026": "2026-06-18T00:00:00+00:00"},
                days={"20260618": "2026-06-18T00:00:00+00:00"},
                last_run="2026-06-18T01:00:00+00:00",
            )
            state.save(path)
            payload = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(payload["version"], 2)
            self.assertNotIn("owner", payload)
            loaded = State.load(path)
            self.assertEqual(loaded.seen, state.seen)
            self.assertEqual(loaded.last_run, state.last_run)

    def test_v1_migration_drops_owner_and_normalizes_utc(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "state.json"
            path.write_text(
                json.dumps(
                    {
                        "owner": "123",
                        "seen": {},
                        "days": {"20260618": "2026-06-18T10:00:00-05:00"},
                        "last_run": "2026-06-18T10:00:00-05:00",
                    }
                ),
                encoding="utf-8",
            )
            state = State.load(path)
            self.assertEqual(state.days["20260618"], "2026-06-18T15:00:00+00:00")
            self.assertEqual(state.last_run, "2026-06-18T15:00:00+00:00")

    def test_corrupt_state_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "state.json"
            path.write_text("{not json", encoding="utf-8")
            with self.assertRaises(StateError):
                State.load(path)

    def test_prune_keeps_baseline_and_recent(self):
        state = State(
            seen={
                "old": "2020-01-01T00:00:00+00:00",
                "new": "2026-06-18T00:00:00+00:00",
            },
            days={"20200101": "baseline", "20200102": "2020-01-01T00:00:00+00:00"},
        )
        state.prune(30, now=datetime(2026, 6, 19, tzinfo=timezone.utc))
        self.assertEqual(set(state.seen), {"new"})
        self.assertEqual(set(state.days), {"20200101"})


if __name__ == "__main__":
    unittest.main()
