from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from mia_exp.evoagent_runner import (
    Completion,
    ModelConfig,
    load_official_prompts,
    render_official_initial_prompt,
    run_evoagent_benchmark,
    run_evoagent_item,
    run_direct_item,
)
from mia_exp.benchmarks.spp import load_instances


class FakeClient:
    def __init__(self, responses: list[str]) -> None:
        self.responses = iter(responses)

    def complete(self, _prompt: str) -> Completion:
        return Completion(
            content=next(self.responses),
            usage={
                "provider": "fake",
                "model": "fake-model",
                "inputTokens": 10,
                "outputTokens": 2,
                "totalTokens": 12,
                "cachedInputTokens": None,
                "thinkingTokens": None,
                "reported": True,
                "raw": {},
            },
            duration_seconds=0.1,
            transport_attempts=1,
        )


class EvoAgentRunnerTests(unittest.TestCase):
    def test_loads_prompts_from_the_pinned_upstream_source(self) -> None:
        prompts = load_official_prompts("spp.logic-grid-puzzle")
        self.assertIn("create and collaborate with multiple experts", prompts["INSTRUCTION_META"])
        self.assertIn("Retain", prompts["INSTRUCTION_CHECK"])

    def test_n10_uses_all_ten_questions_in_official_initial_format(self) -> None:
        instance = load_instances("spp.trivia-creative-writing-n10")[0]
        prompt = render_official_initial_prompt(
            "spp.trivia-creative-writing-n10", instance
        )
        self.assertIn("following 10 questions", prompt)
        for question in instance["questions"]:
            self.assertIn(question, prompt)

    def test_logic_initial_prompt_matches_evoagent_vendored_dataset(self) -> None:
        current = load_instances("spp.logic-grid-puzzle")[0]
        upstream_path = (
            Path(__file__).parents[1]
            / "baselines"
            / "EvoAgent"
            / "spp"
            / "data"
            / "logic_grid_puzzle"
            / "logic_grid_puzzle_200.jsonl"
        )
        upstream = json.loads(upstream_path.read_text().splitlines()[0])
        self.assertEqual(
            render_official_initial_prompt("spp.logic-grid-puzzle", current),
            upstream["inputs"],
        )

    def test_evolves_three_experts_and_records_every_phase(self) -> None:
        instance = load_instances("spp.logic-grid-puzzle")[0]
        responses = ["initial"]
        for generation in range(3):
            responses.extend(
                [
                    f"You are expert {generation}.",
                    "Reason: unique and useful. Retain",
                    f"expert answer {generation}",
                    f"integrated {generation}\nFinal Answer: choice: 2",
                ]
            )
        result = run_evoagent_item(
            "spp.logic-grid-puzzle",
            instance,
            item_index=0,
            client=FakeClient(responses),  # type: ignore[arg-type]
            individuals=3,
        )
        self.assertEqual(result["score"].score, 1)
        self.assertEqual(result["usage"]["modelCalls"], 13)
        self.assertEqual(
            [call["phase"] for call in result["calls"]].count("quality_selection"),
            3,
        )
        self.assertEqual(len(result["executionTree"]["paths"]), 3)

    def test_discarded_descriptions_are_regenerated(self) -> None:
        instance = load_instances("spp.logic-grid-puzzle")[0]
        client = FakeClient(
            [
                "initial",
                "duplicate",
                "Discard",
                "unique",
                "Retain",
                "expert answer",
                "Final Answer: choice: 2",
            ]
        )
        result = run_evoagent_item(
            "spp.logic-grid-puzzle",
            instance,
            item_index=0,
            client=client,  # type: ignore[arg-type]
            individuals=1,
        )
        checks = result["trajectories"][0]["steps"][0]["qualityChecks"]
        self.assertEqual(len(checks), 2)
        self.assertTrue(checks[0]["discarded"])
        self.assertFalse(checks[1]["discarded"])

    def test_multiline_logic_final_answer_is_scored(self) -> None:
        instance = load_instances("spp.logic-grid-puzzle")[5]
        result = run_direct_item(
            "spp.logic-grid-puzzle",
            instance,
            item_index=5,
            client=FakeClient(["Reasoning\n### Final Answer\n\nchoice: 3"]),  # type: ignore[arg-type]
        )
        self.assertEqual(result["score"].score, 1)
        self.assertEqual(result["usage"]["modelCalls"], 1)
        self.assertEqual(result["executionTree"]["maxGeneration"], 1)

    def test_direct_codenames_uses_only_the_two_required_roles(self) -> None:
        instance = load_instances("spp.codenames-collaborative")[9]
        result = run_direct_item(
            "spp.codenames-collaborative",
            instance,
            item_index=9,
            client=FakeClient(
                [
                    "Final Answer: drum",
                    "Final Answer: **kick**, **rope**",
                ]
            ),  # type: ignore[arg-type]
        )
        self.assertEqual(result["score"].score, 1)
        self.assertEqual(result["usage"]["modelCalls"], 2)
        self.assertEqual(
            [call["phase"] for call in result["calls"]],
            ["direct_answer", "direct_answer"],
        )

    def test_run_writes_common_score_and_raw_trace(self) -> None:
        responses = ["initial", "expert", "Retain", "sub", "Final Answer: choice: 2"]
        fake_client = FakeClient(responses)
        config = ModelConfig("fake", "fake-model", "https://example.invalid", "secret")
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "run"
            with (
                patch("mia_exp.evoagent_runner.resolve_model_config", return_value=config),
                patch("mia_exp.evoagent_runner.OpenAICompatibleClient", return_value=fake_client),
            ):
                run_evoagent_benchmark(
                    "spp.logic-grid-puzzle",
                    indices=[0],
                    output_dir=output,
                    individuals=1,
                )
            run = json.loads((output / "run.json").read_text())
            summary = json.loads((output / "summary.json").read_text())
            raw = json.loads((output / "raw" / "0000.json").read_text())
        self.assertEqual(run["method"], "evoagent")
        self.assertEqual(run["provider"], "fake")
        self.assertNotIn("secret", json.dumps(run))
        self.assertEqual(summary["score"], 1)
        self.assertEqual(raw["usage"]["modelCalls"], 5)


if __name__ == "__main__":
    unittest.main()
