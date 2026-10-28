import unittest

from bcrp_monitor.config import load_settings
from bcrp_monitor.extract import mark_relevant, parse_pages


class ExtractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = load_settings()[1]

    def test_dispositive_and_coin_details(self):
        page = (
            "BANCO CENTRAL DE RESERVA DEL PERÚ "
            "CIRCULAR N° 0013-2026-BCRP "
            "Ponen en circulación la quinta moneda de la Serie Numismática "
            "Denominación: S/ 1,00 Aleación: Alpaca Peso fino: 1,0 "
            "Emisión máxima: 10 millones de unidades En el marco "
            "a partir del 18 de junio de 2026 2526775-1"
        )
        hits = parse_pages([page], self.source)
        self.assertEqual(len(hits), 1)
        hit = hits[0]
        self.assertEqual(hit.kind, "Circular")
        self.assertEqual(hit.number, "0013-2026")
        self.assertEqual(hit.ids, ["2526775"])
        self.assertEqual(hit.denomination, "S/ 1,00")
        self.assertEqual(hit.alloy, "Alpaca")
        self.assertEqual(hit.mintage, "10 millones de unidades")
        self.assertEqual(hit.effective, "18 de junio de 2026")

    def test_index_entry_is_replaced_by_body_entry(self):
        index_page = (
            "BANCO CENTRAL DE RESERVA "
            "Circular N° 0013-2026-BCRP Ponen en circulación una moneda 35"
        )
        filler = "NORMAS LEGALES"
        body_page = (
            "BANCO CENTRAL DE RESERVA DEL PERÚ "
            "CIRCULAR N° 0013-2026-BCRP "
            "Ponen en circulación una moneda 2526775-1"
        )
        hits = parse_pages([index_page, filler, body_page], self.source)
        self.assertEqual(len(hits), 1)
        self.assertEqual(hits[0].ids, ["2526775"])
        self.assertEqual(hits[0].page, 3)

    def test_filter_requires_issue_and_item(self):
        page = (
            "BANCO CENTRAL DE RESERVA DEL PERÚ "
            "CIRCULAR N° 0024-2026-BCRP "
            "Relación de bancos 2526775-1"
        )
        hit = parse_pages([page], self.source)[0]
        hit.title = "Relación de bancos que operan con el BCRP"
        mark_relevant([hit], self.source)
        self.assertFalse(hit.relevant)

        hit.title = "Ponen en circulación una nueva moneda de S/ 1"
        mark_relevant([hit], self.source)
        self.assertTrue(hit.relevant)


if __name__ == "__main__":
    unittest.main()
