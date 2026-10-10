"""Checks against the trained rond.ir market, not a synthetic toy set."""

import unittest

from app.patterns import detect
from app.valuation import DB_PATH, MODEL_PATH, load_engine


@unittest.skipUnless(MODEL_PATH.exists() and DB_PATH.exists(), "trained market is missing")
class MarketSnapshotTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine = load_engine()

    def test_neighboring_blocks_are_not_priced_alike(self):
        block_201 = self.engine.estimate("09122013456")
        block_200 = self.engine.estimate("09122003456")
        self.assertGreater(block_200["price"], block_201["price"] * 1.4)
        self.assertTrue(all(sample["block3"] == "201" for sample in block_201["samples"]))
        self.assertTrue(all(sample["block3"] == "200" for sample in block_200["samples"]))

    def test_trailing_zeros_are_compared_with_the_same_tail(self):
        result = self.engine.estimate("09121796900")
        self.assertEqual(result["primary"], "معمولی")
        self.assertEqual(result["middle4"], "7969")
        self.assertGreaterEqual(len(result["samples"]), 3)
        for sample in result["samples"]:
            self.assertGreaterEqual(sample["trailing_zeros"], 2)
            self.assertTrue(sample["number"].startswith("0912"))

    def test_paid_pattern_sets_the_comps(self):
        result = self.engine.estimate("09121112500")
        self.assertIn("هزاری از آخر", result["types"])
        self.assertIn(result["price_pattern"], result["types"])
        self.assertNotEqual(result["price_pattern"], "معمولی")
        self.assertTrue(result["samples"])
        self.assertTrue(all(sample["primary"] == result["price_pattern"] for sample in result["samples"]))

    def test_ordinary_line_is_not_compared_with_other_models(self):
        result = self.engine.estimate("09127514568", "USED")
        self.assertEqual(result["primary"], "معمولی")
        self.assertEqual(result["price_pattern"], "معمولی")
        self.assertTrue(result["samples"])
        for sample in result["samples"]:
            self.assertEqual(sample["primary"], "معمولی")
            self.assertEqual(sample["block3"], "751")

    def test_rhyming_spoken_is_priced_with_its_own_kind(self):
        result = self.engine.estimate("09120339349", "USED")
        self.assertEqual(result["primary"], "گفتاری نزدیک")
        self.assertEqual(result["price_pattern"], "گفتاری نزدیک")
        self.assertTrue(result["samples"])
        for sample in result["samples"]:
            self.assertEqual(sample["primary"], "گفتاری نزدیک")

    def test_first_step_is_compared_only_with_its_own_class(self):
        result = self.engine.estimate("09123767753", "USED")
        self.assertEqual(result["primary"], "پله‌ای از اول")
        self.assertEqual(result["price_pattern"], "پله‌ای از اول")
        self.assertNotIn("سه پله", result["types"])
        # Ads that are also پله‌ای از آخر were pricing this near 326 million.
        # A one-factor step is the ordinary line of this block times its coefficient.
        self.assertGreater(result["price"], 180_000_000)
        self.assertLess(result["price"], 300_000_000)
        self.assertTrue(result["samples"])
        for sample in result["samples"]:
            sample_types = set(detect(sample["number"]).types)
            self.assertEqual(sample["primary"], "پله‌ای از اول")
            self.assertEqual(sample_types, {"پله‌ای از اول"})
            self.assertEqual(sample["block3"], "376")

    def test_api_shape(self):
        result = self.engine.estimate("09122251225")
        self.assertEqual(result["primary"], "ترازویی")
        self.assertIn("price", result)
        self.assertIn("types", result)
        self.assertGreater(result["price"], 500_000_000)


if __name__ == "__main__":
    unittest.main()
