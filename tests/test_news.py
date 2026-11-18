import unittest

from bcrp_monitor.config import load_news_settings
from bcrp_monitor.news import GoogleNews

RSS = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel>
  <item>
    <title>BCRP lanza medallas conmemorativas del papa León XIV - RPP Noticias</title>
    <link>https://news.google.com/rss/articles/one</link>
    <guid>guid-one</guid>
    <pubDate>Mon, 09 Nov 2026 14:00:57 GMT</pubDate>
    <source url="https://rpp.pe">RPP Noticias</source>
  </item>
  <item>
    <title>Condecoran con la Medalla Cívica a funcionarios - El Peruano</title>
    <link>https://news.google.com/rss/articles/two</link>
    <guid>guid-two</guid>
    <pubDate>Mon, 09 Nov 2026 15:00:00 GMT</pubDate>
    <source url="https://elperuano.pe">El Peruano</source>
  </item>
  <item>
    <title>Precio del dólar hoy en Perú - Infobae</title>
    <link>https://news.google.com/rss/articles/three</link>
    <guid>guid-three</guid>
    <pubDate>Mon, 09 Nov 2026 16:00:00 GMT</pubDate>
    <source url="https://infobae.com">Infobae</source>
  </item>
  <item>
    <title>BCRP lanza medallas conmemorativas del papa León XIV - RPP Noticias</title>
    <link>https://news.google.com/rss/articles/one</link>
    <guid>guid-one</guid>
    <pubDate>Mon, 09 Nov 2026 14:00:57 GMT</pubDate>
    <source url="https://rpp.pe">RPP Noticias</source>
  </item>
  <item>
    <title>BCRP emite nueva moneda de S/ 1 - Gestión</title>
    <link>https://news.google.com/rss/articles/four</link>
    <guid>guid-four</guid>
    <pubDate>Tue, 10 Nov 2026 12:00:00 GMT</pubDate>
    <source url="https://gestion.pe">Gestión</source>
  </item>
</channel></rss>
"""


class FakeClient:
    def __init__(self, payload: bytes):
        self._payload = payload
        self.urls: list[str] = []

    def get(self, url: str, timeout: int | None = None) -> bytes:
        self.urls.append(url)
        return self._payload


class NewsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.settings = load_news_settings()

    def test_filters_out_noise_and_deduplicates(self):
        client = FakeClient(RSS.encode("utf-8"))
        items = GoogleNews(self.settings, client).fetch()
        self.assertEqual(len(items), 2)
        self.assertEqual(
            [item.title for item in items],
            [
                "BCRP emite nueva moneda de S/ 1",
                "BCRP lanza medallas conmemorativas del papa León XIV",
            ],
        )
        self.assertEqual(items[1].outlet, "RPP Noticias")

    def test_url_encodes_query_and_params(self):
        news = GoogleNews(self.settings, FakeClient(b""))
        url = news.url()
        self.assertTrue(url.startswith("https://news.google.com/rss/search?q="))
        self.assertIn("hl=es-419", url)
        self.assertIn("when%3A7d", url)

    def test_invalid_xml_returns_empty(self):
        items = GoogleNews(self.settings, FakeClient(b"<not-xml")).fetch()
        self.assertEqual(items, [])


if __name__ == "__main__":
    unittest.main()
