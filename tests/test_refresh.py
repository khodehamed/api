import unittest

from app.refresh import MIN_PRICED, accept_new_snapshot, freshness_line, rows_from_pages


def _page(number: int, items: list[dict]) -> dict:
    return {"page": number, "items": items}


class RefreshTests(unittest.TestCase):
    def test_first_copy_of_a_number_wins(self):
        pages = [
            _page(1, [{"num": "09121111111", "price": 2, "status": "USED"}]),
            _page(
                0,
                [
                    {"num": "09121111111", "price": 9, "status": "LIKE_NEW"},
                    {"num": "09122000000", "price": 8, "status": "LIKE_NEW"},
                ],
            ),
        ]
        rows = rows_from_pages(pages)
        self.assertEqual(
            rows,
            [
                {"number": "09121111111", "price": 9, "status": "LIKE_NEW"},
                {"number": "09122000000", "price": 8, "status": "LIKE_NEW"},
            ],
        )

    def test_small_or_shrunken_snapshot_is_refused(self):
        with self.assertRaises(RuntimeError):
            accept_new_snapshot(MIN_PRICED - 1, None)
        with self.assertRaises(RuntimeError):
            accept_new_snapshot(20_000, 40_000)
        accept_new_snapshot(30_000, 40_000)
        accept_new_snapshot(MIN_PRICED, None)

    def test_freshness_line_names_the_daily_update(self):
        self.assertIn("هر روز یک‌بار", freshness_line(None))
        text = freshness_line("2026-10-10T03:30:00+03:30")
        self.assertIn("2026-10-10 03:30", text)
        self.assertIn("تهران", text)
