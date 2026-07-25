from __future__ import annotations

import json
import unittest
from pathlib import Path

from mia_exp.benchmarks.spp import (
    load_instances,
    parse_hint,
    render_prompt,
    score_response,
)


class SPPAdapterTests(unittest.TestCase):
    def test_logic_grid_uses_strict_final_answer_marker(self) -> None:
        instance = load_instances("spp.logic-grid-puzzle")[0]

        correct = score_response(
            "spp.logic-grid-puzzle",
            instance,
            "Reasoning may mention 1, 3 and 4.\nFINAL_ANSWER: 2",
        )
        unparsed = score_response(
            "spp.logic-grid-puzzle",
            instance,
            "I considered house 2, but omitted the required result marker.",
        )

        self.assertEqual(correct.score, 1.0)
        self.assertTrue(correct.exact_match)
        self.assertFalse(unparsed.parsed)

    def test_trivia_matches_the_official_alias_recall_semantics(self) -> None:
        instance = load_instances("spp.trivia-creative-writing-n5")[0]
        story = ". ".join(aliases[0] for aliases in instance["answers"])

        score = score_response(
            "spp.trivia-creative-writing-n5",
            instance,
            f"FINAL_STORY:\n{story}",
        )

        self.assertEqual(score.earned, 5)
        self.assertEqual(score.possible, 5)
        self.assertTrue(score.exact_match)

    def test_trivia_requires_public_web_grounding_without_answer_leakage(self) -> None:
        instance = load_instances("spp.trivia-creative-writing-n5")[0]
        prompt = render_prompt("spp.trivia-creative-writing-n5", instance)

        self.assertIn("web.search and web.fetch", prompt)
        self.assertFalse(any(alias in prompt for aliases in instance["answers"] for alias in aliases))

        policy_path = Path(__file__).parents[1] / "experiments" / "spp" / "config" / "roy-workspace.json"
        policy = json.loads(policy_path.read_text(encoding="utf-8"))
        self.assertEqual(policy["tools"]["approval"]["readOnly"], "deny")
        self.assertEqual(
            policy["tools"]["approval"]["overrides"],
            {"web.search": "auto", "web.fetch": "auto"},
        )
        self.assertTrue(policy["tools"]["web"]["enabled"])
        self.assertTrue(policy["tools"]["executionLoop"]["enabled"])

    def test_codenames_keeps_spymaster_targets_out_of_guesser_prompt(self) -> None:
        instance = load_instances("spp.codenames-collaborative")[0]
        prompt = render_prompt(
            "spp.codenames-collaborative",
            instance,
            stage="guesser",
            hint="cinema",
        )

        self.assertIn("Hint: cinema", prompt)
        self.assertNotIn("Target words:", prompt)
        self.assertNotIn(", ".join(instance["target_words"]), prompt)

    def test_codenames_uses_official_target_recall(self) -> None:
        instance = load_instances("spp.codenames-collaborative")[0]
        score = score_response(
            "spp.codenames-collaborative",
            instance,
            "FINAL_GUESSES: director, popcorn, fog, whistle",
        )

        self.assertEqual(score.earned, 2)
        self.assertEqual(score.possible, 4)
        self.assertEqual(score.score, 0.5)
        self.assertEqual(score.details["distractorGuesses"], ["fog", "whistle"])

    def test_hint_parser_rejects_unstructured_spymaster_output(self) -> None:
        self.assertEqual(parse_hint("FINAL_HINT: Cinema"), "cinema")
        self.assertIsNone(parse_hint("Maybe cinema would work."))


if __name__ == "__main__":
    unittest.main()
