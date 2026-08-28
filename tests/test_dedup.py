import copy
import json
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

    def test_editorial_suffix_does_not_create_duplicate(self):
        a = self.item(
            title="«Размышления о садах и реках»",
            org="Арт-резиденция «Открытых мастерских»",
            deadline="2026-09-05",
        )
        b = self.item(
            title="Размышления о садах и реках: исследуем исламское искусство",
            org="Арт-резиденция «Открытых мастерских»",
            deadline="2026-09-05",
            source_url="https://t.me/gdeart/1783",
            apply_url="https://t.me/gdeart/1783",
        )
        self.assertTrue(g.same_event(a, b))

    def test_same_title_with_different_source_org_is_duplicate(self):
        a = self.item(title="Арт-резиденция в Зарайске 2026",
                      org="Зарайская арт-резиденция")
        b = self.item(title="Арт-резиденция в Зарайске 2026",
                      org="Ewert — каталог возможностей",
                      source_url="https://example.org/zaraysk",
                      apply_url="https://example.org/zaraysk")
        self.assertTrue(g.same_event(a, b))

    def test_rare_project_name_matches_different_editorial_titles(self):
        a = self.item(title="Опен-колл триеннале «Мифологема» в Галерее МИФ",
                      org="MYTH Gallery", deadline="2026-09-20")
        b = self.item(title="Триеннале «Мифологема»: Миф о Пути Героя",
                      org="Галерея МИФ", deadline="2026-09-20",
                      source_url="https://mythologema.org/",
                      apply_url="https://mythologema.org/")
        self.assertTrue(g.same_event(a, b))

    def test_transitive_cluster_is_fully_merged(self):
        base = dict(org="Галерея БИС АРТ", deadline="2026-08-10")
        a = self.item(title="NEXT 3.0 — набор резидентов", **base)
        b = self.item(title="NEXT 3.0 — open-call галереи БИС АРТ",
                      source_url="https://example.org/next-long",
                      apply_url="https://example.org/next-long", **base)
        bridge = self.item(title="NEXT 3.0",
                           source_url="https://example.org/next",
                           apply_url="https://example.org/next", **base)
        store = {"items": {a["source_url"]: a, b["source_url"]: b,
                           bridge["source_url"]: bridge}, "rejected": {}}
        self.assertEqual(g.deduplicate_store(store), 2)
        self.assertEqual(len(store["items"]), 1)

    def test_generic_same_title_is_not_enough(self):
        a = self.item(title="Open Call 2026", org="Галерея А")
        b = self.item(title="Open Call 2026", org="Галерея Б",
                      source_url="https://example.org/other",
                      apply_url="https://example.org/other")
        self.assertFalse(g.same_event(a, b))

    def test_exact_named_call_without_deadline_is_merged(self):
        a = self.item(title="Open Call в «Барке»", org="Бар «Барка»", deadline="")
        b = self.item(title="Open Call в Барке", org="Бар «Барка»", deadline="",
                      source_url="https://t.me/gdeart/1787",
                      apply_url="https://t.me/gdeart/1787")
        self.assertTrue(g.same_event(a, b))

    def test_same_call_with_two_stage_deadlines_is_merged(self):
        a = self.item(title="Конкурс HSE ART GALLERY «Глобальный город»",
                      org="HSE ART GALLERY", deadline="2026-07-19")
        b = self.item(title="Конкурс HSE ART GALLERY «Глобальный город»",
                      org="HSE ART GALLERY, Школа дизайна НИУ ВШЭ",
                      deadline="2026-07-01", source_url="https://example.org/hse",
                      apply_url="https://example.org/hse")
        self.assertTrue(g.same_event(a, b))

    def test_similar_monthly_residencies_are_not_merged_without_deadlines(self):
        a = self.item(title="Residency Available – October 2026",
                      org="Casa na Ilha", deadline="")
        b = self.item(title="Residency Available – November 2026",
                      org="Casa na Ilha", deadline="", source_url="https://example.org/nov",
                      apply_url="https://example.org/nov")
        self.assertFalse(g.same_event(a, b))

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

    def test_repository_archive_is_already_deduplicated(self):
        store_path = Path(__file__).resolve().parents[1] / "data" / "items.json"
        store = json.loads(store_path.read_text(encoding="utf-8"))
        before = len(store["items"])
        removed = g.deduplicate_store(store)
        self.assertEqual(removed, 0, "%d дублей осталось в архиве" % removed)
        self.assertEqual(len(store["items"]), before)


if __name__ == "__main__":
    unittest.main()
