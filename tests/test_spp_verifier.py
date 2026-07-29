from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from mia_exp.evoagent_runner import Completion
from mia_exp.spp_verifier import (
    load_story,
    parse_verifier_response,
    render_verifier_prompt,
    run_verifier,
)
from mia_exp.benchmarks.spp import load_instances


def _judgment(question_ids: list[str]) -> str:
    return json.dumps(
        {
            "answerAssessments": [
                {
                    "questionId": question_id,
                    "status": "supported" if index else "partial",
                    "evidence": "story evidence",
                    "reason": "semantic match",
                }
                for index, question_id in enumerate(question_ids)
            ],
            "dimensions": {
                "factualFaithfulness": 4,
                "narrativeCoherence": 5,
                "answerIntegration": 4,
                "topicConsistency": 5,
                "instructionCompliance": 5,
                "concision": 3,
            },
            "dimensionReasons": {
                "factualFaithfulness": "Facts are mostly accurate.",
                "narrativeCoherence": "The plot is causally connected.",
                "answerIntegration": "Answers are embedded in scenes.",
                "topicConsistency": "The topic shapes the story.",
                "instructionCompliance": "Only the story is returned.",
                "concision": "Some passages could be shorter.",
            },
            "confidence": 0.9,
            "qualitySummary": "Strong story with one partial answer.",
            "referenceIssues": [],
        }
    )


class FakeClient:
    class Config:
        provider = "fake"

    config = Config()

    def __init__(self, response: str) -> None:
        self.response = response

    def complete(self, _prompt: str) -> Completion:
        return Completion(
            content=self.response,
            usage={
                "inputTokens": 100,
                "outputTokens": 50,
                "totalTokens": 150,
                "cachedInputTokens": 10,
                "thinkingTokens": 20,
            },
            duration_seconds=0.2,
            transport_attempts=1,
        )


class SPPVerifierTests(unittest.TestCase):
    def test_prompt_is_blind_and_keeps_compact_reference_answers(self) -> None:
        instance = load_instances("spp.trivia-creative-writing-n5")[0]
        prompt = render_verifier_prompt(instance, "A candidate story.")
        self.assertNotIn("Roy", prompt)
        self.assertIn("<candidate_story>", prompt)
        self.assertIn("David Seville", prompt)
        self.assertIn('"Cancer"', prompt)
        self.assertLess(len(prompt), 12_000)

    def test_parses_dimensions_and_derives_weighted_score(self) -> None:
        ids = ["q1", "q2"]
        parsed = parse_verifier_response(
            f"```json\n{_judgment(ids)}\n```",
            expected_question_ids=ids,
        )
        self.assertEqual(parsed["semanticAnswerCoverage"], 0.75)
        self.assertGreater(parsed["overallScore"], 0.7)
        self.assertLessEqual(parsed["overallScore"], 1)

    def test_rejects_missing_question_assessment(self) -> None:
        with self.assertRaisesRegex(ValueError, "question IDs"):
            parse_verifier_response(
                _judgment(["q1"]),
                expected_question_ids=["q1", "q2"],
            )

    def test_loads_flat_and_roy_story_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "raw").mkdir()
            (root / "raw" / "0000.json").write_text(
                json.dumps({"finalAnswer": "flat story"}),
                encoding="utf-8",
            )
            (root / "raw" / "0001").mkdir()
            (root / "raw" / "0001" / "roy.json").write_text(
                json.dumps(
                    {
                        "result": {
                            "finalResponse": "Synthesis details\nFINAL_STORY: Roy story"
                        }
                    }
                ),
                encoding="utf-8",
            )
            self.assertEqual(load_story(root, 0)[0], "flat story")
            self.assertEqual(load_story(root, 1)[0], "Roy story")

    def test_run_records_judgment_and_verifier_usage_separately(self) -> None:
        instance = load_instances("spp.trivia-creative-writing-n5")[0]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source"
            output = root / "verifier"
            (source / "raw").mkdir(parents=True)
            (source / "raw" / "0000.json").write_text(
                json.dumps({"finalAnswer": "A complete story."}),
                encoding="utf-8",
            )
            run_verifier(
                "spp.trivia-creative-writing-n5",
                source_run=source,
                output_dir=output,
                indices=[0],
                model="fake-model",
                client=FakeClient(_judgment(instance["question_ids"])),  # type: ignore[arg-type]
            )
            item = json.loads((output / "items.jsonl").read_text())
            summary = json.loads((output / "summary.json").read_text())
            run = json.loads((output / "run.json").read_text())
        self.assertEqual(item["status"], "completed")
        self.assertEqual(item["usage"]["totalTokens"], 150)
        self.assertEqual(summary["usage"]["modelCalls"], 1)
        self.assertEqual(summary["judgeModel"], "fake-model")
        self.assertNotIn("A complete story.", json.dumps(run))

    def test_run_repairs_one_malformed_json_response(self) -> None:
        instance = load_instances("spp.trivia-creative-writing-n5")[0]

        class RepairClient(FakeClient):
            def __init__(self) -> None:
                self.responses = iter(["{not valid json", _judgment(instance["question_ids"])])

            def complete(self, _prompt: str) -> Completion:
                return Completion(
                    content=next(self.responses),
                    usage={
                        "inputTokens": 10,
                        "outputTokens": 5,
                        "totalTokens": 15,
                        "cachedInputTokens": None,
                        "thinkingTokens": None,
                    },
                    duration_seconds=0.1,
                    transport_attempts=1,
                )

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source"
            output = root / "verifier"
            (source / "raw").mkdir(parents=True)
            (source / "raw" / "0000.json").write_text(
                json.dumps({"finalAnswer": "A complete story."}),
                encoding="utf-8",
            )
            run_verifier(
                "spp.trivia-creative-writing-n5",
                source_run=source,
                output_dir=output,
                indices=[0],
                model="fake-model",
                client=RepairClient(),  # type: ignore[arg-type]
            )
            item = json.loads((output / "items.jsonl").read_text())
            raw = json.loads((output / "raw" / "0000.json").read_text())
        self.assertEqual(item["status"], "completed")
        self.assertEqual(item["usage"]["modelCalls"], 2)
        self.assertIsNotNone(raw["repair"])

    def test_resume_allows_a_subset_of_the_original_indices(self) -> None:
        instance = load_instances("spp.trivia-creative-writing-n5")[0]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source"
            output = root / "verifier"
            (source / "raw").mkdir(parents=True)
            for index in (0, 1):
                (source / "raw" / f"{index:04d}.json").write_text(
                    json.dumps({"finalAnswer": "A complete story."}),
                    encoding="utf-8",
                )
            run_verifier(
                "spp.trivia-creative-writing-n5",
                source_run=source,
                output_dir=output,
                indices=[0, 1],
                model="fake-model",
                client=FakeClient(_judgment(instance["question_ids"])),  # type: ignore[arg-type]
            )
            run_verifier(
                "spp.trivia-creative-writing-n5",
                source_run=source,
                output_dir=output,
                indices=[0],
                model="fake-model",
                client=FakeClient(_judgment(instance["question_ids"])),  # type: ignore[arg-type]
            )
            records = [
                json.loads(line)
                for line in (output / "items.jsonl").read_text().splitlines()
            ]
        self.assertEqual(len(records), 2)


if __name__ == "__main__":
    unittest.main()
