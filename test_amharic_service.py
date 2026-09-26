#!/usr/bin/env python3
"""
Tests for services.amharic_service.

Run from the project root:

    build_env/Scripts/python.exe test_amharic_service.py -v
"""

import json
import os
import tempfile
import unittest

from services.amharic_service import (
    AmharicService,
    normalize_key,
    to_amharic,
    to_amharic_phonetic,
)

AMHARIC_RANGE = (0x1200, 0x137F)


def is_amharic(text: str) -> bool:
    return all(AMHARIC_RANGE[0] <= ord(ch) <= AMHARIC_RANGE[1]
               for ch in text if ch.strip())


class SeedDictionaryTests(unittest.TestCase):
    """The names the shop actually complained about."""

    def test_titanic(self):
        self.assertEqual(to_amharic("titanic"), "ቲታኒክ")
        self.assertEqual(to_amharic("TITANIC"), "ቲታኒክ")

    def test_storage(self):
        self.assertEqual(to_amharic("storage"), "ስቶራጅ")
        self.assertEqual(to_amharic("STORAGE"), "ስቶራጅ")

    def test_romanized_amharic_is_kept(self):
        self.assertEqual(to_amharic("NIMA SHENKURT"), "ኒማ ሽንኩርት")
        self.assertEqual(to_amharic("kuter 27"), "ቁተር 27")

    def test_codes_are_not_translated(self):
        self.assertEqual(to_amharic("PA 180"), "PA 180")
        self.assertEqual(to_amharic("ZB 2145"), "ZB 2145")
        self.assertEqual(to_amharic("M3 COFFEE"), "M3 ኮፌ")

    def test_seed_has_no_empty_values(self):
        service = AmharicService()
        self.assertTrue(service._seed_entries)
        for key, value in service._seed_entries.items():
            self.assertTrue(value.strip(), f"empty Amharic value for {key}")


class RuleTests(unittest.TestCase):
    """Words that are not in the seed still have to come out sensible."""

    def test_soft_c_is_s(self):
        self.assertTrue(is_amharic(to_amharic("plastic")))

    def test_ck_is_k(self):
        self.assertEqual(to_amharic("plastic"), "ፕላስቲክ")

    def test_english_g_is_soft(self):
        # "manager" is not in the seed dictionary on purpose.
        service = AmharicService()
        self.assertFalse(service.has_seed("manager"))
        self.assertEqual(to_amharic("manager"), "ማናጀር")

    def test_unknown_romanized_word_still_converts(self):
        result = to_amharic("zemene")
        self.assertTrue(is_amharic(result), result)
        self.assertTrue(result.strip())


class CorrectionTests(unittest.TestCase):
    """A saved correction always wins — including over the seed dictionary."""

    def setUp(self):
        self.service = AmharicService()
        self.original_path = self.service._overrides_path
        self.original_entries = dict(self.service._entries)
        handle, self.temp_path = tempfile.mkstemp(suffix=".json")
        os.close(handle)
        os.remove(self.temp_path)
        self.service._overrides_path = self.temp_path
        self.service._entries = {}

    def tearDown(self):
        self.service._overrides_path = self.original_path
        self.service._entries = self.original_entries
        if os.path.exists(self.temp_path):
            os.remove(self.temp_path)

    def test_override_wins_and_reset_restores_automatic(self):
        self.assertEqual(self.service.to_amharic("TITANIC"), "ቲታኒክ")

        self.service.set_override("TITANIC", "ታይታኒክ")
        self.assertTrue(self.service.is_custom("TITANIC"))
        self.assertEqual(self.service.to_amharic("TITANIC"), "ታይታኒክ")
        self.assertEqual(self.service.describe("TITANIC"), ("ታይታኒክ", "custom"))

        self.service.remove_override("TITANIC")
        self.assertEqual(self.service.to_amharic("TITANIC"), "ቲታኒክ")
        self.assertEqual(self.service.describe("TITANIC"), ("ቲታኒክ", "seed"))

    def test_word_level_correction_applies_everywhere(self):
        self.service.set_override("TERA", "ተራ")
        self.assertEqual(self.service.to_amharic("tsehay mesob tera"),
                         "ጸሐይ መሶብ ተራ")

    def test_corrections_are_written_to_disk(self):
        self.service.set_override("TITANIC", "ታይታኒክ")
        with open(self.temp_path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
        self.assertEqual(data["entries"][normalize_key("TITANIC")], "ታይታኒክ")

    def test_sounds_like_box(self):
        self.assertEqual(self.service.to_amharic_phonetic("storaj"), "ስቶራጅ")
        self.assertEqual(self.service.to_amharic_phonetic("kuter 27"), "ቁተር 27")

    def test_suggestions_offer_the_alternatives(self):
        # A seeded name offers the checked spelling plus what was sent before.
        suggestions = dict((source, value) for source, value in self.service.suggest("storage"))
        self.assertEqual(suggestions.get("seed"), "ስቶራጅ")
        self.assertEqual(suggestions.get("old"), "ስቶራገ")
        # A name that is not in the dictionary still gets its automatic value.
        sources = {source for source, _value in self.service.suggest("manager")}
        self.assertIn("rules", sources)


class FreshInstallTests(unittest.TestCase):
    """A brand-new PC has no database and no corrections file."""

    def setUp(self):
        self.service = AmharicService()
        self.original_path = self.service._overrides_path
        self.original_entries = dict(self.service._entries)
        self.original_seed = dict(self.service._seed_entries)
        self.original_english = set(self.service._seed_english)
        handle, self.missing_path = tempfile.mkstemp(suffix=".json")
        os.close(handle)
        os.remove(self.missing_path)
        self.service._overrides_path = self.missing_path
        self.service._entries = {}

    def tearDown(self):
        self.service._overrides_path = self.original_path
        self.service._entries = self.original_entries
        self.service._seed_entries = self.original_seed
        self.service._seed_english = self.original_english
        if os.path.exists(self.missing_path):
            os.remove(self.missing_path)

    def test_shipped_dictionary_is_present(self):
        self.assertGreater(len(self.service._seed_entries), 500)

    def test_missing_corrections_file_changes_nothing(self):
        self.assertEqual(self.service.stats()["corrections"], 0)
        self.assertEqual(self.service.to_amharic("TITANIC"), "ቲታኒክ")
        self.assertEqual(self.service.to_amharic("PA 180"), "PA 180")
        # Nothing is written until the user actually saves a fix.
        self.assertFalse(os.path.exists(self.missing_path))

    def test_a_new_name_still_gets_a_sane_conversion(self):
        result = self.service.to_amharic("SOME NEW SHOP 42")
        self.assertTrue(result.strip())
        self.assertIn("42", result)

    def test_rules_alone_still_fix_the_reported_words(self):
        # Even without the seed (e.g. a rebuild that forgot the data file),
        # the English rules keep working.
        self.service._seed_entries = {}
        self.service._seed_english = set()
        self.assertEqual(self.service.to_amharic("titanic"), "ቲታኒክ")
        self.assertEqual(self.service.to_amharic("storage"), "ስቶራጅ")


class SafetyTests(unittest.TestCase):
    """Notifications must never break because of a conversion."""

    def test_empty_and_none_are_returned_unchanged(self):
        for value in (None, "", "   ", "\n\t"):
            self.assertEqual(to_amharic(value), value)

    def test_junk_never_raises(self):
        for value in ("🙂🙂", "???", "123", "a" * 500, "ጤና ይስጥልኝ",
                      "////", "M/CHA", "b/dar"):
            result = to_amharic(value)
            self.assertIsNotNone(result)

    def test_mixed_name_keeps_digits_and_separators(self):
        result = to_amharic("030 merab b/dar 84523")
        self.assertIn("84523", result)
        self.assertIn("/", result)
        self.assertTrue(is_amharic(result.replace("84523", "").replace("/", "").replace("030", "")),
                        result)


if __name__ == "__main__":
    unittest.main()
