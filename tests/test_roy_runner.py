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
                        "nodes": [
                            {"id": "root", "generation": 0},
                            {"id": "agent_2", "generation": 2},
                        ],
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
                    {"type": "team.capacity.reserved"},
                    {"type": "delegation.direct_decision.audit.started"},
                    {"type": "delegation.direct_decision.audit.overridden"},
                    {"type": "root.execution.attempt.completed"},
                    {"type": "root.execution.closure.unmet"},
                    {"type": "root.acceptance.audit.completed"},
                    {"type": "root.acceptance.audit.unmet"},
                    {"type": "root.execution.time_budget.allocated"},
                    {"type": "root.execution.time_budget.exhausted"},
                    {"type": "agent.output.tool_intent.recovery.completed"},
                    {
                        "type": "tool.error",
                        "data": {"error": "Command timed out after 1000ms"},
                    },
                    {"type": "llm.stream.retrying"},
                    {
                        "type": "llm.stream.failed",
                        "data": {"error": "Request timed out after 120000ms"},
                    },
                    {"type": "llm.json.recovered"},
                    {"type": "team.synthesis.recovered"},
                    {
                        "type": "spawn.policy.rejected",
                        "data": {"reason": "max_children_exceeded"},
                    },
                ],
                "messages": [{}, {}],
            }
        )

        self.assertEqual(telemetry["derivedAgentIds"], ["agent_1"])
        self.assertEqual(telemetry["derivedTeamIds"], ["team_1"])
        self.assertEqual(telemetry["maxActorGeneration"], 2)
        self.assertEqual(telemetry["recursiveDerivedActorIds"], ["agent_2"])
        self.assertEqual(telemetry["teamCapacityReservations"], 1)
        self.assertEqual(telemetry["maxChildrenRejections"], 1)
        self.assertEqual(telemetry["directDecisionOverrides"], 1)
        self.assertEqual(telemetry["executionClosureAttempts"], 1)
        self.assertEqual(telemetry["executionClosureUnmet"], 1)
        self.assertEqual(telemetry["acceptanceAuditsCompleted"], 1)
        self.assertEqual(telemetry["acceptanceAuditsUnmet"], 1)
        self.assertEqual(telemetry["executionTimeBudgetAllocations"], 1)
        self.assertEqual(telemetry["executionTimeBudgetExhausted"], 1)
        self.assertEqual(telemetry["toolIntentRecoveriesCompleted"], 1)
        self.assertEqual(telemetry["toolErrors"], 1)
        self.assertEqual(telemetry["toolTimeouts"], 1)
        self.assertEqual(telemetry["llmRequestTimeouts"], 1)
        self.assertEqual(telemetry["llmRetryEvents"], 1)
        self.assertEqual(telemetry["llmRecoveryEvents"], 1)
        self.assertEqual(telemetry["teamSynthesisRecoveries"], 1)
        self.assertEqual(telemetry["outputContractRepairEvents"], 2)
        self.assertEqual(telemetry["truncatedStreams"], 1)


if __name__ == "__main__":
    unittest.main()
