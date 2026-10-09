import unittest

from app.patterns import detect


class PatternTests(unittest.TestCase):
    def types(self, number):
        analysis = detect(number)
        self.assertIsNotNone(analysis)
        return analysis

    def test_ordinary_with_trailing_zeros_and_middle_block(self):
        # The number the previous estimator compared with unrelated lines.
        analysis = self.types("09121796900")
        self.assertEqual(analysis.core, "1796900")
        self.assertEqual(analysis.middle4, "7969")
        self.assertEqual(analysis.trailing_zeros, 2)
        self.assertNotIn("هزاری از آخر", analysis.types)
        self.assertEqual(analysis.primary, "معمولی")

    def test_scale(self):
        analysis = self.types("09122251225")
        self.assertIn("ترازویی", analysis.types)
        self.assertEqual(analysis.primary, "ترازویی")

    def test_mirror(self):
        analysis = self.types("09121234321")
        self.assertIn("آینه‌ای", analysis.types)
        self.assertNotIn("ترازویی", analysis.types)

    def test_contiguous_mirror(self):
        analysis = self.types("09120009559")
        self.assertIn("آینه‌ای", analysis.types)

    def test_all_same(self):
        analysis = self.types("09121111111")
        self.assertEqual(analysis.primary, "هفت رقم یکی")

    def test_million_and_trailing(self):
        analysis = self.types("09129000000")
        self.assertIn("میلیونی", analysis.types)
        self.assertEqual(analysis.trailing_zeros, 6)

    def test_hezar_from_end(self):
        analysis = self.types("09121112500")
        self.assertIn("هزاری از آخر", analysis.types)

    def test_hezar_from_start(self):
        analysis = self.types("09122500111")
        self.assertIn("هزاری از اول", analysis.types)

    def test_ten_thousand_from_end(self):
        self.assertIsNone(detect("0912150000"))
        analysis = self.types("09121250000")
        self.assertIn("ده هزاری از آخر", analysis.types)

    def test_step_from_start_same_tens(self):
        analysis = self.types("09124348111")
        self.assertIn("پله‌ای از اول", analysis.types)

    def test_step_same_units(self):
        analysis = self.types("09125686111")
        self.assertIn("پله‌ای از اول", analysis.types)

    def test_not_a_step_when_both_digits_change(self):
        analysis = self.types("09124352111")
        self.assertNotIn("پله‌ای از اول", analysis.types)
        analysis = self.types("09125467111")
        self.assertNotIn("پله‌ای از اول", analysis.types)

    def test_three_steps(self):
        analysis = self.types("09129594931")
        self.assertIn("سه پله", analysis.types)
        self.assertEqual(analysis.primary, "سه پله")

    def test_triple_digit_step(self):
        analysis = self.types("09122187180")
        self.assertIn("پله‌ای از اول", analysis.types)
        analysis = self.types("09122822831")
        self.assertIn("پله‌ای از اول", analysis.types)

    def test_spoken_pair(self):
        analysis = self.types("09124004001")
        self.assertIn("گفتاری", analysis.types)

    def test_double_pairs(self):
        analysis = self.types("09124545111")
        self.assertIn("جفت جفت از اول", analysis.types)
        analysis = self.types("09121114545")
        self.assertIn("جفت جفت از آخر", analysis.types)

    def test_triple_pair(self):
        analysis = self.types("09121818181")
        self.assertIn("سه جفت از اول", analysis.types)

    def test_sequential(self):
        analysis = self.types("09121234567")
        self.assertIn("ترتیبی از اول", analysis.types)
        self.assertIn("ترتیبی از آخر", analysis.types)
        analysis = self.types("09129876000")
        self.assertIn("ترتیبی از اول", analysis.types)
        self.assertEqual(analysis.sequential_reversed, 1)

    def test_birth_year(self):
        analysis = self.types("09121375111")
        self.assertIn("تاریخ تولدی", analysis.types)
        analysis = self.types("09120001375")
        self.assertIn("تاریخ تولدی", analysis.types)

    def test_low_code_only_for_0912_code_1(self):
        self.assertIn("کد پایین", self.types("09121131234").types)
        self.assertNotIn("کد پایین", self.types("09125131234").types)

    def test_decimal_and_hundred(self):
        self.assertIn("ده دهی از اول", self.types("09122030111").types)
        self.assertIn("ده دهی از آخر", self.types("09121118090").types)
        self.assertIn("صد صدی", self.types("09122003001").types)

    def test_letters(self):
        analysis = self.types("09126642623")
        self.assertIn("حروفی", analysis.types)
        self.assertEqual(analysis.word, "Mohamad")

    def test_two_digits_only(self):
        analysis = self.types("09129922229")
        self.assertIn("متشکل از دو رقم", analysis.types)

    def test_prefix_repeat(self):
        analysis = self.types("09120935111")
        self.assertIn("تکرار پیش شماره", analysis.types)

    def test_persian_digits(self):
        analysis = detect("۰۹۱۲۲۲۵۱۲۲۵")
        self.assertEqual(analysis.number, "09122251225")
        self.assertIn("ترازویی", analysis.types)

    def test_blocks_differ_between_neighbors(self):
        a = self.types("09122013456")
        b = self.types("09122003456")
        self.assertEqual(a.block3, "201")
        self.assertEqual(b.block3, "200")
        self.assertNotEqual(a.block3, b.block3)


if __name__ == "__main__":
    unittest.main()
