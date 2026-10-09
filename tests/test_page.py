import unittest

from app.server import estimate_form, home


class PageTests(unittest.TestCase):
    def test_home_defaults_to_used_and_has_no_essay(self):
        html = home()
        self.assertIn('value="USED" checked', html)
        self.assertNotIn('value="LIKE_NEW" checked', html)
        for phrase in (
            "الگوی رند",
            "هر روز یک‌بار",
            "خطای میانه",
            "برآورد مدل",
            "فاصله",
        ):
            self.assertNotIn(phrase, html)

    def test_result_shows_price_without_the_method(self):
        html = estimate_form("09121796900", "USED")
        self.assertIn("تومان", html)
        self.assertIn('value="USED" checked', html)
        self.assertIn("09121796900", html)
        for phrase in (
            "خطای میانه",
            "برآورد مدل",
            "میانگین وزنی",
            "آگهی‌های هم‌رده که در قیمت",
            "فاصله",
        ):
            self.assertNotIn(phrase, html)
