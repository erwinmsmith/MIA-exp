from __future__ import annotations

import unittest

from mia_exp.benchmarks.contracts import (
    ItemScore,
    aggregate_benchmark_summaries,
    aggregate_scores,
)


class ItemScoreTests(unittest.TestCase):
    def test_common_score_and_aggregate_contract(self) -> None:
        scores = [
            ItemScore(metric="answer_recall", earned=1, possible=1),
            ItemScore(
                metric="answer_recall",
                earned=3,
                possible=5,
                parsed=True,
            ),
            ItemScore(
                metric="target_word_recall",
                earned=0,
                possible=4,
                parsed=False,
            ),
        ]

        aggregate = aggregate_scores(scores)

        self.assertAlmostEqual(aggregate["score"], 4 / 10)
        self.assertAlmostEqual(aggregate["meanItemScore"], (1 + 0.6 + 0) / 3)
        self.assertEqual(aggregate["exactMatches"], 1)
        self.assertEqual(aggregate["parsedItems"], 2)

    def test_invalid_denominator_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            ItemScore(metric="invalid", earned=0, possible=0)

    def test_cross_benchmark_score_is_a_macro_average(self) -> None:
        aggregate = aggregate_benchmark_summaries(
            [
                {
                    "benchmarkId": "small",
                    "score": 1.0,
                    "exactMatchRate": 1.0,
                    "parseRate": 1.0,
                    "items": 1,
                },
                {
                    "benchmarkId": "large",
                    "score": 0.0,
                    "exactMatchRate": 0.0,
                    "parseRate": 1.0,
                    "items": 1000,
                },
            ]
        )

        self.assertEqual(aggregate["score"], 0.5)
        self.assertEqual(aggregate["aggregation"], "macro")


if __name__ == "__main__":
    unittest.main()
