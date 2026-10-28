import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from bcrp_monitor.config import ConfigError, load_config, load_settings


class ConfigTests(unittest.TestCase):
    def _local(self, directory: Path, payload: dict) -> Path:
        path = directory / "config.local.json"
        path.write_text(json.dumps(payload), encoding="utf-8")
        return path

    def test_settings_load_and_url_shape(self):
        app, source = load_settings()
        self.assertEqual(source.name, "BCRP")
        self.assertTrue(source.base_url.startswith("https://"))
        self.assertIn("issue_es", source.patterns)

    def test_env_overrides_local_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            local = self._local(
                Path(tmp),
                {
                    "telegram": {"bot_token": "local", "chat_id": "111"},
                    "gmail": {},
                },
            )
            env = {
                "TELEGRAM_BOT_TOKEN": "from-env",
                "TELEGRAM_CHAT_ID": "999",
            }
            with mock.patch.dict(os.environ, env, clear=True):
                config = load_config(local_path=local)
            self.assertEqual(config.secrets.telegram_bot_token, "from-env")
            self.assertEqual(config.secrets.telegram_chat_id, "999")

    def test_missing_telegram_token_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            local = self._local(Path(tmp), {"telegram": {"chat_id": "111"}})
            with mock.patch.dict(os.environ, {}, clear=True):
                with self.assertRaises(ConfigError):
                    load_config(local_path=local)


if __name__ == "__main__":
    unittest.main()
