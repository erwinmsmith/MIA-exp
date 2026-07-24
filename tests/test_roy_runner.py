from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from mia_exp.roy_runner import _telemetry, load_dotenv


class DotenvTests(unittest.TestCase):
    def test_loads_values_without_expanding_or_logging_them(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / ".env"
            path.write_text(
                "# comment\n"
                "PLAIN=value\n"
                "QUOTED='value with spaces'\n"
                'export TOKEN="secret-value"\n',
                encoding="utf-8",
            )

            values = load_dotenv(path)

        self.assertEqual(values["PLAIN"], "value")
        self.assertEqual(values["QUOTED"], "value with spaces")
        self.assertEqual(values["TOKEN"], "secret-value")

    def test_telemetry_summarizes_tree_cache_and_repair_signals(self) -> None:
        telemetry = _telemetry(
            {
                "result": {
                    "correlationId": "correlation",
                    "decision": {"action": "spawn_subagents"},
                    "executionTree": {
                        "status": "completed",
                        "steps": [{}, {}],
                        "nodes": [{"generation": 0}, {"generation": 2}],
                    },
                    "subagents": [
                        {"agent": {"identity": {"id": "agent_1"}}},
                    ],
                    "teams": [{"team": {"identity": {"id": "team_1"}}}],
                    "usage": {"total": {"totalTokens": 42}},
                },
                "events": [
                    {"type": "execution.cache.snapshot.recorded"},
                    {"type": "root.output_contract.repair.started"},
                    {"type": "root.output_contract.repair.completed"},
                    {"type": "llm.stream.truncated"},
                ],
                "messages": [{}, {}],
            }
        )

        self.assertEqual(telemetry["derivedAgentIds"], ["agent_1"])
        self.assertEqual(telemetry["derivedTeamIds"], ["team_1"])
        self.assertEqual(telemetry["maxActorGeneration"], 2)
        self.assertEqual(telemetry["outputContractRepairEvents"], 2)
        self.assertEqual(telemetry["truncatedStreams"], 1)


if __name__ == "__main__":
    unittest.main()
