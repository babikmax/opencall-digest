import copy
import sys
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import generate as g


class DeduplicationTests(unittest.TestCase):
    def item(self, **overrides):
        value = {
            "title": "Грантовая программа фонда Ruarts",
            "org": "Фонд Ruarts",
            "deadline": "2026-08-31",
            "source": "ewert.ru",
            "source_url": "https://ewert.ru/competitions/ruarts/",
            "apply_url": "https://ewert.ru/competitions/ruarts/",
            "summary": "Короткое описание",
            "theme": "Поддержка художников",
            "first_seen": "2026-08-28",
        }
        value.update(overrides)
        return value

    def test_url_variants_are_same_event(self):
        a = self.item(source_url="https://example.org/call/?utm_source=tg")
        b = self.item(source_url="http://www.example.org/call")
        self.assertTrue(g.same_event(a, b))

    def test_ruarts_titles_are_same_event(self):
        a = self.item(title="Ежегодная грантовая программа фонда Ruarts")
        b = self.item(title="Грантовая программа фонда Ruarts",
                      source_url="https://ruarts.foundation/ru/grants/14",
                      apply_url="https://ruarts.foundation/ru/grants/14")
        self.assertTrue(g.same_event(a, b))

    def test_different_calls_are_not_merged(self):
        a = self.item(title="Грантовая программа фонда Ruarts")
        b = self.item(title="Летняя выставка молодых авторов",
                      source_url="https://example.org/summer-show",
                      apply_url="https://example.org/summer-show")
        self.assertFalse(g.same_event(a, b))

    def test_different_deadlines_are_not_merged(self):
        a = self.item()
        b = self.item(deadline="2026-09-30",
                      source_url="https://example.org/next-call",
                      apply_url="https://example.org/next-call")
        self.assertFalse(g.same_event(a, b))

    def test_merge_prefers_official_url_and_keeps_aliases(self):
        aggregator = self.item(title="Ежегодная грантовая программа фонда Ruarts")
        official = self.item(
            source="ruarts.foundation",
            source_url="https://ruarts.foundation/ru/grants/14",
            apply_url="https://ruarts.foundation/ru/grants/14",
            summary="Более подробное описание гранта и требований к заявке",
        )
        merged = g.merge_items(aggregator, official)
        self.assertEqual(merged["apply_url"], "https://ruarts.foundation/ru/grants/14")
        self.assertIn(aggregator["source_url"], merged["aliases"])
        self.assertIn(official["source_url"], merged["aliases"])
        self.assertIn("ewert.ru", merged["sources"])
        self.assertIn("ruarts.foundation", merged["sources"])

    def test_seen_contains_all_aliases_after_dedup(self):
        aggregator = self.item(title="Ежегодная грантовая программа фонда Ruarts")
        official = self.item(
            source_url="https://ruarts.foundation/ru/grants/14",
            apply_url="https://ruarts.foundation/ru/grants/14",
        )
        store = {"items": {aggregator["source_url"]: aggregator,
                           official["source_url"]: official}, "rejected": {}}
        self.assertEqual(g.deduplicate_store(store), 1)
        seen = g.all_seen_urls(store)
        self.assertIn(aggregator["source_url"], seen)
        self.assertIn(official["source_url"], seen)


if __name__ == "__main__":
    unittest.main()
