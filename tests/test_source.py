import unittest

from bcrp_monitor.config import load_settings
from bcrp_monitor.http import HttpClient
from bcrp_monitor.source import ElPeruano


class FakeClient:
    def __init__(self, page: str, pdf: bytes = b"%PDF-1.4 fake"):
        self._page = page.encode("utf-8")
        self._pdf = pdf
        self.urls: list[str] = []

    def get(self, url: str, timeout: int | None = None) -> bytes:
        self.urls.append(url)
        return self._pdf if url.endswith(".pdf") else self._page


class SourceTests(unittest.TestCase):
    def _peruano(self, client: FakeClient) -> ElPeruano:
        _, source = load_settings()
        return ElPeruano(source, client, pdf_timeout=1, max_candidates=1)

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

    def test_gazette_pdf_without_edition_number(self):
        page = (
            '<meta property="og:image" content="/api/archivo/thumbnail/'
            '5KpILUHuqhbAYdaFRPjQzq/*/NL20261113_thumb.jpg"/>'
            '"/api/archivo/file/5KpILUHuqhbAYdaFRPjQzq/*/NL20261113.pdf\\"'
        )
        client = FakeClient(page)
        gazette = self._peruano(client).fetch_gazette("20261113")
        self.assertFalse(gazette.broken)
        self.assertEqual(gazette.pdf, b"%PDF-1.4 fake")
        self.assertEqual(
            client.urls[-1],
            "https://busquedas.elperuano.pe/api/archivo/file/"
            "5KpILUHuqhbAYdaFRPjQzq/*/NL20261113.pdf",
        )

    def test_gazette_falls_back_to_thumbnail_number(self):
        page = (
            "/api/archivo/thumbnail/ASSET123/*/NL20260618_19636_thumb.jpg"
        )
        client = FakeClient(page)
        gazette = self._peruano(client).fetch_gazette("20260618")
        self.assertEqual(gazette.pdf, b"%PDF-1.4 fake")
        self.assertTrue(client.urls[-1].endswith("/NL20260618_19636.pdf"))

    def test_gazette_marks_broken_page(self):
        page = (
            "/api/archivo/thumbnail/ASSET123/*/NL20261113_thumb.jpg"
        )
        client = FakeClient(page)
        gazette = self._peruano(client).fetch_gazette("20261113")
        self.assertIsNone(gazette.pdf)
        self.assertTrue(gazette.broken)


if __name__ == "__main__":
    unittest.main()
