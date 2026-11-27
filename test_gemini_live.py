"""Optional live model checks using synthetic conversations only."""
import os
import unittest

from review import analyze, gemini_configured


@unittest.skipUnless(os.getenv("HANDOFF_LIVE_TEST") == "1", "Live model checks are opt-in")
class GeminiReview(unittest.TestCase):
    def test_review_examples(self):
        self.assertTrue(gemini_configured(), "Set GEMINI_MODEL and Gemini API or Vertex credentials.")
        cases = [
            ("contradiction", "Keep the deprecated alias.", "Remove the deprecated alias.", "conflict"),
            ("paraphrase", "Keep the deprecated alias.", "Continue exporting the old name.", "aligned"),
            ("omission", "Rename the function and keep the alias.", "Rename the function.", "missing"),
            ("later correction", "Remove the alias. Correction: keep it for existing clients.",
             "Keep the alias for existing clients.", "aligned"),
            ("ambiguity", "Keep the alias for the supported client.", "Keep the alias only if the client mentioned in the ticket is the supported client; its identity is unknown.",
             "unclear"),
            ("scope", "Update the comments.", "Update the comments and send a newsletter.", "off_task"),
        ]
        for name, source, handoff, expected in cases:
            with self.subTest(case=name):
                result = analyze(source, handoff)
                self.assertEqual(expected, result["status"], result["reason"])

