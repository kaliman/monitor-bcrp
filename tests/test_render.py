import unittest

from bcrp_monitor.i18n import load_locale
from bcrp_monitor.models import Hit
from bcrp_monitor.render import plain_of, render_hit, render_no_news


class RenderTests(unittest.TestCase):
    def _hit(self) -> Hit:
        return Hit(
            kind="Circular",
            number="0013-2026",
            page=1,
            title="Moneda <Recuay> & cultura",
            url="https://example.test/a?b=1&c=2",
            denomination="S/ 1,00",
            alloy="Alpaca",
            mintage="10 millones",
            effective="18 de junio de 2026",
        )

    def test_spanish_hit_is_escaped(self):
        text = render_hit("20260618", self._hit(), load_locale("es"))
        self.assertIn("<b>Circular N° 0013-2026</b>", text)
        self.assertIn("El Peruano · 18/06/2026", text)
        self.assertIn("Moneda &lt;Recuay&gt; &amp; cultura", text)
        self.assertNotIn("<Recuay>", text)
        self.assertIn("desde el 18 de junio de 2026", text)

    def test_english_date_and_no_news(self):
        messages = load_locale("en")
        text = render_no_news("20260618", messages, "BCRP")
        self.assertIn("<b>BCRP · 2026-06-18</b>", text)
        self.assertIn("No news.", text)

    def test_plain_text(self):
        self.assertEqual(plain_of("<b>A</b> &amp; B"), "A & B")


if __name__ == "__main__":
    unittest.main()
