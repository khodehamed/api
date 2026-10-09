import unittest

from app.patterns import detect
from app.valuation import build_engine


def _row(number, price, status="LIKE_NEW"):
    return {"number": number, "price": price, "status": status}


def _ordinary(block: str, count: int, base_price: int, status: str = "LIKE_NEW") -> list[dict]:
    rows = []
    cursor = 0
    while len(rows) < count:
        tail = (
            f"{(cursor * 7 + 2) % 10}"
            f"{(cursor * 3 + 8) % 10}"
            f"{(cursor * 9 + 4) % 10}"
            f"{(cursor * 5 + 6) % 10}"
        )
        cursor += 1
        number = "0912" + block + tail
        analysis = detect(number)
        if analysis is None or analysis.primary != "معمولی" or analysis.trailing_zeros:
            continue
        rows.append(_row(number, base_price + len(rows) * 250_000, status))
    return rows


class ValuationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        rows = []
        rows.extend(_ordinary("200", 25, 80_000_000))
        rows.extend(_ordinary("201", 25, 150_000_000))
        rows.extend(_ordinary("320", 15, 70_000_000))
        zeros = [
            ("09121796100", 390_000_000),
            ("09121796200", 410_000_000),
            ("09121796300", 405_000_000),
            ("09121796400", 420_000_000),
            ("09121796500", 415_000_000),
            ("09121796800", 430_000_000),
            ("09121797000", 440_000_000),
            ("09121798000", 460_000_000),
        ]
        for number, price in zeros:
            rows.append(_row(number, price))
        for number, price in (
            ("09122251225", 2_500_000_000),
            ("09123341334", 2_200_000_000),
            ("09124451445", 1_800_000_000),
            ("09125561556", 1_600_000_000),
            ("09126671667", 1_900_000_000),
        ):
            rows.append(_row(number, price))
        rows.append(_row("09121111111", 9_000_000_000))
        rows.append(_row("09122222222", 4_000_000_000))
        rows.append(_row("09123333333", 3_000_000_000))
        cls.engine = build_engine(rows)
        cls.block_200 = rows[0]["number"]
        cls.block_201 = next(row["number"] for row in rows if row["number"][4:7] == "201")

    def test_same_pattern_not_cross_block(self):
        left = self.engine.estimate("09122017384")
        right = self.engine.estimate("09122007384")
        self.assertEqual(detect("09122017384").primary, "معمولی")
        self.assertEqual(detect("09122007384").primary, "معمولی")
        self.assertGreater(left["price"], right["price"] * 1.25)
        self.assertTrue(all(sample["block3"] == "201" for sample in left["samples"][:4]))
        self.assertTrue(all(sample["block3"] == "200" for sample in right["samples"][:4]))

    def test_trailing_zero_number_stays_with_its_kind(self):
        result = self.engine.estimate("09121796900")
        self.assertEqual(result["middle4"], "7969")
        self.assertEqual(result["trailing_zeros"], 2)
        self.assertEqual(result["primary"], "معمولی")
        self.assertGreater(result["price"], 300_000_000)
        self.assertLess(result["price"], 700_000_000)
        for sample in result["samples"][:5]:
            self.assertGreaterEqual(sample["trailing_zeros"], 2)
            self.assertEqual(sample["block3"], "179")

    def test_scale_is_not_priced_like_ordinary(self):
        scale = self.engine.estimate("09122881288")
        ordinary = self.engine.estimate("09122017384")
        self.assertEqual(scale["primary"], "ترازویی")
        self.assertGreater(scale["price"], ordinary["price"] * 3)

    def test_exact_listing_anchors_the_price(self):
        result = self.engine.estimate("09121796100")
        self.assertEqual(result["source"], "آگهی همین شماره")
        self.assertGreater(result["price"], 300_000_000)

    def test_used_quote_stays_with_used_neighbors(self):
        block = _ordinary("186", 10, 420_000_000, "USED")
        rows = list(block[:8])
        rows.append(_row(block[8]["number"], 2_200_000_000, "LIKE_NEW"))
        rows.extend(_ordinary("320", 20, 80_000_000))
        rows.extend(_ordinary("410", 20, 90_000_000))
        rows.extend(_ordinary("510", 15, 100_000_000))
        engine = build_engine(rows)
        result = engine.estimate(block[9]["number"], "USED")
        self.assertLess(result["price"], 900_000_000)
        self.assertGreater(result["price"], 300_000_000)
        self.assertTrue(result["samples"])
        self.assertTrue(all(sample["status"] == "USED" for sample in result["samples"]))
        self.assertTrue(all(sample["block3"] == "186" for sample in result["samples"]))

    def test_ordinary_label_when_no_rond_class(self):
        result = self.engine.estimate("09122017384")
        self.assertEqual(result["primary"], "معمولی")
        self.assertEqual(result["types"], ["معمولی"])


if __name__ == "__main__":
    unittest.main()
