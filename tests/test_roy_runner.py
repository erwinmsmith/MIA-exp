from __future__ import annotations

import tempfile
import unittest
from subprocess import CompletedProcess
from pathlib import Path
from unittest.mock import patch

from mia_exp.roy_runner import (
    RoyInvocationFailure,
    _telemetry,
    load_dotenv,
    run_roy,
)


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
                    {"type": "root.response.acceptance.audit.started"},
                    {"type": "root.response.acceptance.unmet"},
                    {"type": "root.response.acceptance.repair.completed"},
                    {"type": "llm.stream.continuation.started"},
                    {"type": "llm.stream.continuation.completed"},
                    {"type": "root.execution.time_budget.allocated"},
                    {"type": "root.execution.time_budget.exhausted"},
                    {"type": "agent.output.tool_intent.recovery.completed"},
                    {"type": "agent.output.empty.recovery.started"},
                    {"type": "agent.output.empty.recovery.completed"},
                    {"type": "agent.output.action_validation.recovery.started"},
                    {
                        "type": "tool.error",
                        "data": {"error": "Command timed out after 1000ms"},
                    },
                    {
                        "type": "tool.timeout",
                        "data": {"error": "Command timed out after 1000ms"},
                    },
                    {"type": "tool.deadline.applied"},
                    {"type": "llm.stream.retrying"},
                    {
                        "type": "llm.stream.failed",
                        "data": {"error": "Request timed out after 120000ms"},
                    },
                    {
                        "type": "agent.tool_planning.timeout",
                        "data": {"message": "Request timed out after 2000ms"},
                    },
                    {"type": "agent.tool_planning.failed"},
                    {"type": "runtime.wall_clock_limit.applied"},
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
        self.assertEqual(telemetry["responseAcceptanceAudits"], 1)
        self.assertEqual(telemetry["responseAcceptanceUnmet"], 1)
        self.assertEqual(telemetry["responseAcceptanceRepairsCompleted"], 1)
        self.assertEqual(telemetry["executionTimeBudgetAllocations"], 1)
        self.assertEqual(telemetry["executionTimeBudgetExhausted"], 1)
        self.assertEqual(telemetry["toolIntentRecoveriesCompleted"], 1)
        self.assertEqual(telemetry["emptyOutputRecoveriesStarted"], 1)
        self.assertEqual(telemetry["emptyOutputRecoveriesCompleted"], 1)
        self.assertEqual(telemetry["emptyOutputRecoveriesFailed"], 0)
        self.assertEqual(telemetry["actionValidationRecoveries"], 1)
        self.assertEqual(telemetry["toolErrors"], 1)
        self.assertEqual(telemetry["toolTimeouts"], 1)
        self.assertEqual(telemetry["llmRequestTimeouts"], 2)
        self.assertEqual(telemetry["toolPlanningFailures"], 1)
        self.assertEqual(telemetry["toolPlanningTimeouts"], 1)
        self.assertEqual(telemetry["toolDeadlineClamps"], 1)
        self.assertEqual(telemetry["externalWallClockLimits"], 1)
        self.assertEqual(telemetry["llmRetryEvents"], 1)
        self.assertEqual(telemetry["llmRecoveryEvents"], 1)
        self.assertEqual(telemetry["teamSynthesisRecoveries"], 1)
        self.assertEqual(telemetry["outputContractRepairEvents"], 2)
        self.assertEqual(telemetry["truncatedStreams"], 1)
        self.assertEqual(telemetry["streamContinuationsStarted"], 1)
        self.assertEqual(telemetry["streamContinuationsCompleted"], 1)
        self.assertEqual(telemetry["streamContinuationsFailed"], 0)

    def test_failed_process_preserves_its_diagnostic_invocation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            bundle = root / "roy-run.mjs"
            policy = root / "policy.json"
            artifact = root / "raw" / "roy.json"
            bundle.write_text("// bundle", encoding="utf-8")
            policy.write_text("{}\n", encoding="utf-8")
            artifact.parent.mkdir()
            artifact.write_text(
                """{
  "status": "failed",
  "error": {
    "message": "Connection error.",
    "retryable": true,
    "persistedState": true
  },
  "recovery": {
    "attempts": 3,
    "correlationIds": ["failed-1", "failed-2", "failed-3"]
  },
  "events": [
    {"type": "runtime.transient_turn.retrying"},
    {"type": "runtime.transient_turn.retrying"},
    {"type": "runtime.transient_turn.failed"}
  ],
  "messages": []
}
""",
                encoding="utf-8",
            )

            with patch(
                "mia_exp.roy_runner.subprocess.run",
                return_value=CompletedProcess(
                    args=["node"],
                    returncode=1,
                    stdout="",
                    stderr="roy-run: Connection error.",
                ),
            ):
                with self.assertRaises(RoyInvocationFailure) as raised:
                    run_roy(
                        "Solve the task.",
                        workspace=root / "workspace",
                        artifact_path=artifact,
                        session_id="failed-run",
                        budget=30_000,
                        timeout_seconds=10,
                        bundle_path=bundle,
                        policy_path=policy,
                    )

        invocation = raised.exception.invocation
        self.assertEqual(invocation.response, "")
        self.assertEqual(invocation.telemetry["runtimeStatus"], "failed")
        self.assertEqual(invocation.telemetry["turnRecoveryAttempts"], 3)
        self.assertEqual(invocation.telemetry["turnRetryEvents"], 2)
        self.assertEqual(invocation.telemetry["turnFailureEvents"], 1)

    def test_omits_budget_flag_when_runtime_budget_is_unlimited(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            bundle = root / "roy-run.mjs"
            policy = root / "policy.json"
            artifact = root / "raw" / "roy.json"
            bundle.write_text("// bundle", encoding="utf-8")
            policy.write_text("{}\n", encoding="utf-8")
            artifact.parent.mkdir()
            artifact.write_text(
                '{"status":"completed","result":{"finalResponse":"done"},"events":[],"messages":[]}\n',
                encoding="utf-8",
            )

            with patch(
                "mia_exp.roy_runner.subprocess.run",
                return_value=CompletedProcess(
                    args=["node"],
                    returncode=0,
                    stdout="",
                    stderr="",
                ),
            ) as run:
                invocation = run_roy(
                    "Solve the task.",
                    workspace=root / "workspace",
                    artifact_path=artifact,
                    session_id="unlimited-run",
                    timeout_seconds=10,
                    bundle_path=bundle,
                    policy_path=policy,
                )

        command = run.call_args.args[0]
        self.assertNotIn("--budget", command)
        self.assertEqual(invocation.response, "done")


if __name__ == "__main__":
    unittest.main()
