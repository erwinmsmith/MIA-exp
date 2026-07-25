from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from mia_exp.roy_artifacts import (
    discover_roy_artifacts,
    render_roy_summary_markdown,
    summarize_roy_artifacts,
)


class RoyArtifactSummaryTests(unittest.TestCase):
    def test_summarizes_steps_actor_tree_and_usage(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            artifact = root / "raw" / "0000" / "roy.json"
            artifact.parent.mkdir(parents=True)
            artifact.write_text(
                json.dumps(
                    {
                        "sessionId": "sample-1",
                        "status": "completed",
                        "result": {
                            "correlationId": "delivery-1",
                            "decision": {"action": "spawn_subagents"},
                            "usage": {
                                "total": {
                                    "llmCalls": 4,
                                    "inputTokens": 100,
                                    "cachedInputTokens": 25,
                                    "outputTokens": 30,
                                    "totalTokens": 130,
                                }
                            },
                            "executionTree": {
                                "status": "completed",
                                "rootAgentId": "root",
                                "nodes": [
                                    {
                                        "id": "root",
                                        "kind": "agent",
                                        "generation": 0,
                                    },
                                    {
                                        "id": "team_1",
                                        "kind": "team",
                                        "parentId": "root",
                                        "generation": 1,
                                    },
                                    {
                                        "id": "agent_1",
                                        "kind": "agent",
                                        "role": "coder",
                                        "parentId": "team_1",
                                        "generation": 2,
                                    },
                                ],
                                "steps": [
                                    {
                                        "id": "step-1",
                                        "index": 1,
                                        "status": "completed",
                                        "decision": {
                                            "action": "delegate",
                                            "reason": "Split inspection and repair.",
                                            "agentCount": 1,
                                        },
                                        "actorIds": ["agent_1"],
                                        "teamIds": ["team_1"],
                                        "treeSnapshot": [
                                            {
                                                "id": "root",
                                                "kind": "agent",
                                                "generation": 0,
                                                "createdAtStep": 0,
                                            },
                                            {
                                                "id": "team_1",
                                                "kind": "team",
                                                "parentId": "root",
                                                "generation": 1,
                                                "createdAtStep": 1,
                                            },
                                            {
                                                "id": "agent_1",
                                                "kind": "agent",
                                                "role": "coder",
                                                "parentId": "team_1",
                                                "generation": 2,
                                                "createdAtStep": 1,
                                            },
                                        ],
                                        "activities": [
                                            {
                                                "kind": "feedback",
                                                "actorId": "agent_1",
                                                "eventType": "agent.feedback",
                                                "summary": "Verifier still fails.",
                                            }
                                        ],
                                    }
                                ],
                            },
                        },
                    }
                ),
                encoding="utf-8",
            )

            summary = summarize_roy_artifacts([root])
            markdown = render_roy_summary_markdown(summary)
            discovered = discover_roy_artifacts([artifact])

        self.assertEqual(discovered, [artifact.resolve()])
        self.assertEqual(summary["aggregate"]["artifactCount"], 1)
        self.assertEqual(summary["aggregate"]["derivedActors"], 2)
        self.assertEqual(summary["aggregate"]["recursiveActors"], 1)
        self.assertEqual(summary["aggregate"]["maxActorGeneration"], 2)
        self.assertEqual(summary["aggregate"]["inputTokens"], 100)
        step = summary["artifacts"][0]["steps"][0]
        self.assertEqual(step["teamIds"], ["team_1"])
        self.assertEqual(
            [actor["id"] for actor in step["newActors"]],
            ["team_1", "agent_1"],
        )
        self.assertIn("Verifier still fails.", markdown)
        self.assertIn("generation 2", markdown)

    def test_rejects_directory_without_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ValueError, "no Roy run artifacts"):
                discover_roy_artifacts([Path(directory)])


if __name__ == "__main__":
    unittest.main()
