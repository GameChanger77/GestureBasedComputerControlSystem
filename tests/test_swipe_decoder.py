import tempfile
import unittest
from pathlib import Path

from backend.gestures.keyboard_mode.SwipeDecoder import SwipeDecoder


class SwipeDecoderTests(unittest.TestCase):
    def _make_decoder(self, words):
        with tempfile.TemporaryDirectory() as tmp:
            lexicon = Path(tmp) / "words.txt"
            lexicon.write_text("\n".join(words) + "\n", encoding="utf-8")
            decoder = SwipeDecoder(lexicon, max_words=1000)
            # Return a clone with persistent file for this test call.
            return decoder

    def test_exact_trace_prefers_exact_word(self):
        decoder = self._make_decoder(["hello", "help", "helmet", "held"])
        best, conf, candidates = decoder.decode(list("hello"), top_k=3)
        self.assertEqual(best, "hello")
        self.assertGreater(conf, 0.0)
        self.assertIn("hello", candidates)

    def test_noisy_repeated_trace_collapses(self):
        decoder = self._make_decoder(["hello", "hero", "hill"])
        best, conf, candidates = decoder.decode(list("hheeelllloo"), top_k=3)
        self.assertEqual(best, "hello")
        self.assertGreater(conf, 0.0)
        self.assertIn("hello", candidates)

    def test_short_or_invalid_trace_returns_empty(self):
        decoder = self._make_decoder(["hello", "hero"])
        best, conf, candidates = decoder.decode(["1", "!", "x"], top_k=3)
        self.assertEqual(best, "")
        self.assertEqual(conf, 0.0)
        self.assertEqual(candidates, [])

    def test_ranking_is_deterministic(self):
        decoder = self._make_decoder(["tone", "tome", "time", "tile", "tide"])
        first = decoder.decode(list("tome"), top_k=4)
        second = decoder.decode(list("tome"), top_k=4)
        self.assertEqual(first, second)

    def test_user_reported_noisy_examples(self):
        decoder = self._make_decoder(
            [
                "hi",
                "hello",
                "hui",
                "hero",
                "halo",
                "hill",
            ]
        )
        best_hi, _, _ = decoder.decode(list("hui"), top_k=5)
        best_hello, _, _ = decoder.decode(list("hgtrertyuiklo"), top_k=5)
        self.assertEqual(best_hi, "hi")
        self.assertEqual(best_hello, "hello")


if __name__ == "__main__":
    unittest.main()
