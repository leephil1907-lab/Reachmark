import sqlite3
import unittest
from unittest.mock import patch

from web.global_discovery import (
    CATEGORY_VARIANTS, category_queries, dedupe, grid_points, is_chain, rank
)


class GlobalDiscoveryTests(unittest.TestCase):
    def test_category_variants_expand_known_category(self):
        queries = category_queries("Restaurant")
        self.assertIn("Restaurant", queries)
        self.assertIn("cafe", queries)
        self.assertIn("fast food", queries)

    def test_dedupe_merges_same_business_within_100m(self):
        rows = [
            {"source_key": "a", "name": "Acme Cafe", "latitude": 6.5244, "longitude": 3.3792,
             "phone": "+234 800 111 2222", "website": ""},
            {"source_key": "b", "name": "Acme Café", "latitude": 6.52445, "longitude": 3.37925,
             "phone": "", "website": "https://acme.example"},
        ]
        merged = dedupe(rows)
        self.assertEqual(len(merged), 1)
        self.assertEqual(merged[0]["website"], "https://acme.example")

    def test_chain_filter_and_opportunity_ranking(self):
        rows = [
            {"source_key": "1", "name": "Independent Clinic", "latitude": 6.5, "longitude": 3.3,
             "phone": "+2348000000000", "source_tags": {"rating": 4.8, "review_count": 80}},
            {"source_key": "2", "name": "McDonald's Ikeja", "latitude": 6.5, "longitude": 3.3,
             "phone": "+2348111111111", "source_tags": {"rating": 4.5, "review_count": 300}},
            {"source_key": "3", "name": "Tiny Clinic", "latitude": 6.5, "longitude": 3.3,
             "source_tags": {"rating": 5.0, "review_count": 2}},
        ]
        self.assertTrue(is_chain(rows[1]))
        ranked = rank(rows, {"1": {"tier": "NO_SITE"}})
        self.assertEqual([r["name"] for r in ranked], ["Independent Clinic"])

    def test_grid_points_are_deterministic_and_centered(self):
        points = list(grid_points(6.5244, 3.3792, ring=1, cell_km=3))
        self.assertEqual(len(points), 9)
        self.assertIn((6.5244, 3.3792), points)

    def test_google_and_foursquare_are_optional(self):
        self.assertIn("restaurant", CATEGORY_VARIANTS["restaurant"])
        with patch.dict("os.environ", {"GOOGLE_PLACES_API_KEY": "", "FOURSQUARE_API_KEY": ""}, clear=False):
            from web.global_discovery import google_search, foursquare_search
            self.assertEqual(google_search("restaurant", 6.5, 3.3)[1], "not configured")
            self.assertEqual(foursquare_search("restaurant", 6.5, 3.3)[1], "not configured")


if __name__ == "__main__":
    unittest.main()
