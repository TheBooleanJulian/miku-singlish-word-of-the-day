"""Word bank integrity + Wiktionary parser checks. Run: python -m unittest discover tests"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from singlish_words import CURATED_WORDS, SINGLISH_WORDS, normalise_word  # noqa: E402
from scripts.import_wiktionary import extract_entry, _is_bare_alt  # noqa: E402

REQUIRED = ("word", "type", "pronunciation", "meaning")


class WordBankTests(unittest.TestCase):
    def test_required_fields_present_and_non_empty(self):
        for e in SINGLISH_WORDS:
            for key in REQUIRED:
                self.assertIsInstance(e.get(key), str, f"{e.get('word')!r} missing {key}")
                self.assertTrue(e[key].strip(), f"{e['word']!r} has empty {key}")

    def test_imported_entries_do_not_duplicate_each_other_or_curated(self):
        imported = SINGLISH_WORDS[len(CURATED_WORDS):]
        curated_keys = {normalise_word(w["word"]) for w in CURATED_WORDS}
        keys = [normalise_word(w["word"]) for w in imported]
        self.assertEqual(len(keys), len(set(keys)))
        self.assertFalse(curated_keys & set(keys))

    def test_imported_entries_are_attributed_and_markdown_safe(self):
        for e in SINGLISH_WORDS[len(CURATED_WORDS):]:
            self.assertTrue(e["source"].startswith("https://en.wiktionary.org/wiki/"), e["word"])
            self.assertNotIn("_", e["source"], e["word"])
            for key in REQUIRED:
                for ch in "*_`[]":
                    self.assertNotIn(ch, e[key], f"{e['word']!r} {key} contains {ch!r}")
            # Photo captions are capped at 1024 chars by Telegram.
            self.assertLessEqual(len(e["meaning"]), 300, e["word"])

    def test_curated_list_has_no_duplicate_spellings(self):
        keys = [normalise_word(w["word"]) for w in CURATED_WORDS]
        self.assertEqual(len(keys), len(set(keys)))

    def test_normalise_word_collapses_spacing_and_hyphens(self):
        self.assertEqual(normalise_word("Wah-Lau"), normalise_word("wah lau"))


SAMPLE = """<html><body><section><h2 id="English">English</h2>
<section><h3 id="Pronunciation">Pronunciation</h3>
<ul><li>(Singapore) IPA: <span class="IPA">/ʃi.ɔk/</span></li></ul></section>
<section><h3 id="Adjective">Adjective</h3>
<p><span class="headword-line"><strong>shiok</strong></span></p>
<ol>
<li><span class="usage-label-sense">(Singapore, colloquial)</span> Very <a>pleasurable</a>.
<dl><dd>example sentence that should be ignored</dd></dl></li>
<li>A sense used everywhere, not regional.</li>
<li><span class="usage-label-sense">(Singlish, vulgar)</span> A rude sense.</li>
</ol></section></section>
<section><h2 id="Malay">Malay</h2><section><h3 id="Noun">Noun</h3>
<ol><li><span class="usage-label-sense">(Singapore)</span> Not English.</li></ol></section></section>
</body></html>"""


class ParserTests(unittest.TestCase):
    def test_extracts_only_singapore_senses_from_english_section(self):
        e = extract_entry("shiok", SAMPLE)
        self.assertEqual(e["type"], "adjective")
        self.assertEqual(e["pronunciation"], "ʃi.ɔk")
        self.assertEqual(e["meaning"], "1. Very pleasurable. 2. A rude sense.")
        self.assertTrue(e["nsfw"])
        self.assertNotIn("example", e["meaning"])
        self.assertNotIn("Not English", e["meaning"])

    def test_bare_alternative_spelling_detection(self):
        self.assertTrue(_is_bare_alt({"meaning": "Alternative spelling of agak-agak."}))
        self.assertTrue(_is_bare_alt({"meaning": "1. Alternative form of x. 2. Alternative spelling of y."}))
        self.assertFalse(_is_bare_alt({"meaning": "Alternative spelling of 'kiasu'. Fear of losing out."}))
        self.assertFalse(_is_bare_alt({"meaning": "1. A jelly. 2. Alternative spelling of agak-agak."}))


if __name__ == "__main__":
    unittest.main()
