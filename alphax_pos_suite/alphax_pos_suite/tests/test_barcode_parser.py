"""Unit tests for the embedded/variable-measure barcode parser.

Run with:  bench --site <site> run-tests --module \
    alphax_pos_suite.alphax_pos_suite.tests.test_barcode_parser
"""
import unittest

from alphax_pos_suite.alphax_pos_suite.barcode import parser


WEIGHT_DEF = dict(
    definition_name="Weight", enabled=1, prefix="2", total_length=13,
    item_start=2, item_length=5, qty_start=7, qty_length=5, qty_divider=1000,
    use_qty_from_barcode=1, use_rate_from_barcode=0,
)

PRICE_DEF = dict(
    definition_name="Price", enabled=1, prefix="2", total_length=13,
    item_start=2, item_length=5, rate_start=7, rate_length=5, rate_divider=100,
    use_rate_from_barcode=1, use_qty_from_barcode=0,
)


class TestBarcodeParser(unittest.TestCase):
    def test_weight_barcode(self):
        # 2 00042 01500 7 -> item 42, 1500 g = 1.5 kg
        r = parser.parse("2000420150007", WEIGHT_DEF)
        self.assertIsNotNone(r)
        self.assertEqual(r.item_code, "42")
        self.assertAlmostEqual(r.qty, 1.5)
        self.assertIsNone(r.rate)

    def test_price_barcode(self):
        # 2 00099 02350 1 -> item 99, 2350 cents = 23.50
        r = parser.parse("2000990235001", PRICE_DEF)
        self.assertIsNotNone(r)
        self.assertEqual(r.item_code, "99")
        self.assertAlmostEqual(r.rate, 23.5)
        self.assertIsNone(r.qty)

    def test_wrong_prefix_no_match(self):
        self.assertIsNone(parser.parse("5000420150007", WEIGHT_DEF))

    def test_wrong_length_no_match(self):
        self.assertIsNone(parser.parse("200042015000", WEIGHT_DEF))

    def test_non_numeric_no_match(self):
        self.assertIsNone(parser.parse("20A0420150007", WEIGHT_DEF))

    def test_parse_first_returns_first_match(self):
        r = parser.parse_first("2000420150007", [PRICE_DEF, WEIGHT_DEF])
        self.assertEqual(r.definition_name, "Price")

    def test_zero_division_guard(self):
        d = dict(WEIGHT_DEF, qty_divider=0)
        r = parser.parse("2000420150007", d)
        self.assertEqual(r.qty, 1500)  # divider 0 -> treated as 1


if __name__ == "__main__":
    unittest.main()
