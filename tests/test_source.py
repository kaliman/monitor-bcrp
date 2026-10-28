import unittest

from bcrp_monitor.config import load_settings
from bcrp_monitor.http import HttpClient
from bcrp_monitor.source import ElPeruano


class SourceTests(unittest.TestCase):
    def test_urls_are_built_from_settings(self):
        _, source = load_settings()
        client = HttpClient(source, timeout=1, retries=1, backoff_seconds=0)
        peruano = ElPeruano(source, client, pdf_timeout=1, max_candidates=1)
        self.assertEqual(
            peruano.url_for("gazette", day="20260618"),
            f"{source.base_url}/cuadernillo/NL/20260618",
        )
        self.assertEqual(
            peruano.url_for("dispositive", cid="2526775"),
            f"{source.base_url}/dispositivo/NL/2526775-1",
        )


if __name__ == "__main__":
    unittest.main()
