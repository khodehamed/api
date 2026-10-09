"""Checks against the trained rond.ir market, not a synthetic toy set."""

import unittest

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

    def test_thousand_tail_uses_thousand_comps(self):
        result = self.engine.estimate("09121112500")
        self.assertEqual(result["primary"], "هزاری از آخر")
        self.assertTrue(result["samples"])
        self.assertTrue(all(sample["primary"] == "هزاری از آخر" for sample in result["samples"]))

    def test_api_shape(self):
        result = self.engine.estimate("09122251225")
        self.assertEqual(result["primary"], "ترازویی")
        self.assertIn("price", result)
        self.assertIn("types", result)
        self.assertGreater(result["price"], 500_000_000)


if __name__ == "__main__":
    unittest.main()
