"""Non-interactive Roy execution for text benchmarks."""

from __future__ import annotations

import json
import os
import shlex
import shutil
import subprocess
import time
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .benchmarks.registry import REPO_ROOT


DEFAULT_BUNDLE = REPO_ROOT / "artifacts" / "roy-run.mjs"
DEFAULT_POLICY = REPO_ROOT / "experiments" / "spp" / "config" / "roy-workspace.json"


@dataclass(frozen=True)
class RoyInvocation:
    response: str
    artifact_path: Path
    duration_seconds: float
    telemetry: dict[str, Any]


def load_dotenv(path: Path) -> dict[str, str]:
    """Read a simple dotenv file without logging or expanding secret values."""

    values: dict[str, str] = {}
    if not path.is_file():
        return values
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].lstrip()
        key, separator, raw_value = line.partition("=")
        key = key.strip()
        if not separator or not key.replace("_", "").isalnum() or key[0].isdigit():
            continue
        try:
            parsed = shlex.split(raw_value, posix=True)
        except ValueError:
            parsed = [raw_value]
        values[key] = parsed[0] if len(parsed) == 1 else raw_value.strip()
    return values


def _telemetry(artifact: dict[str, Any]) -> dict[str, Any]:
    result = artifact.get("result", {})
    tree = result.get("executionTree") or {}
    nodes = tree.get("nodes") or []
    subagents = result.get("subagents") or []
    teams = result.get("teams") or []
    events = artifact.get("events") or []
    event_counts = Counter(
        str(event.get("type", "unknown")) for event in events if isinstance(event, dict)
    )
    feedback_events = sum(
        count for name, count in event_counts.items() if "feedback" in name
    )
    cache_events = sum(count for name, count in event_counts.items() if "cache" in name)
    delegation_events = sum(
        count
        for name, count in event_counts.items()
        if "delegat" in name or "spawn" in name or "team." in name
    )
    recursive_nodes = [
        node
        for node in nodes
        if isinstance(node, dict) and int(node.get("generation", 0)) >= 2
    ]
    spawn_rejections = [
        event
        for event in events
        if isinstance(event, dict) and event.get("type") == "spawn.policy.rejected"
    ]
    return {
        "correlationId": result.get("correlationId"),
        "decision": (result.get("decision") or {}).get("action"),
        "executionTreeStatus": tree.get("status"),
        "executionSteps": len(tree.get("steps") or []),
        "derivedAgents": len(subagents),
        "derivedAgentIds": [
            item.get("agent", {}).get("identity", {}).get("id")
            for item in subagents
            if isinstance(item, dict)
        ],
        "derivedTeams": len(teams),
        "derivedTeamIds": [
            item.get("team", {}).get("identity", {}).get("id")
            for item in teams
            if isinstance(item, dict)
        ],
        "maxActorGeneration": max(
            (
                int(node.get("generation", 0))
                for node in nodes
                if isinstance(node, dict)
            ),
            default=0,
        ),
        "recursiveDerivedActors": len(recursive_nodes),
        "recursiveDerivedActorIds": [
            node.get("id") for node in recursive_nodes if node.get("id")
        ],
        "messages": len(artifact.get("messages") or []),
        "events": len(events),
        "feedbackEvents": feedback_events,
        "cacheEvents": cache_events,
        "delegationEvents": delegation_events,
        "teamCapacityReservations": event_counts.get("team.capacity.reserved", 0),
        "teamCapacityReleases": event_counts.get("team.capacity.released", 0),
        "maxChildrenRejections": sum(
            1
            for event in spawn_rejections
            if (event.get("data") or {}).get("reason") == "max_children_exceeded"
        ),
        "maxTurnCapacityRejections": sum(
            1
            for event in spawn_rejections
            if (event.get("data") or {}).get("reason")
            == "max_total_agents_per_turn_exceeded"
        ),
        "infeasibleDelegationPlans": event_counts.get(
            "delegation.plan.infeasible", 0
        ),
        "directDecisionAudits": event_counts.get(
            "delegation.direct_decision.audit.started", 0
        ),
        "directDecisionOverrides": event_counts.get(
            "delegation.direct_decision.audit.overridden", 0
        ),
        "executionClosureAttempts": event_counts.get(
            "root.execution.attempt.completed", 0
        ),
        "executionClosureUnmet": event_counts.get(
            "root.execution.closure.unmet", 0
        ),
        "outputContractRepairEvents": sum(
            count
            for name, count in event_counts.items()
            if name.startswith("root.output_contract.repair.")
        ),
        "fallbackEvents": sum(
            count for name, count in event_counts.items() if "fallback" in name
        ),
        "truncatedStreams": event_counts.get("llm.stream.truncated", 0),
        "eventTypes": dict(sorted(event_counts.items())),
        "usage": (result.get("usage") or {}).get("total") or {},
    }


def run_roy(
    prompt: str,
    *,
    workspace: Path,
    artifact_path: Path,
    session_id: str,
    budget: int,
    timeout_seconds: int,
    bundle_path: Path = DEFAULT_BUNDLE,
    policy_path: Path = DEFAULT_POLICY,
    env_file: Path | None = None,
) -> RoyInvocation:
    """Run one isolated Roy session and retain its complete artifact."""

    if not bundle_path.is_file():
        raise FileNotFoundError(f"Roy bundle is missing: {bundle_path}")
    if not policy_path.is_file():
        raise FileNotFoundError(f"Roy workspace policy is missing: {policy_path}")
    workspace.mkdir(parents=True, exist_ok=True)
    (workspace / ".roy").mkdir(exist_ok=True)
    shutil.copyfile(policy_path, workspace / ".roy" / "config.json")
    artifact_path.parent.mkdir(parents=True, exist_ok=True)
    prompt_path = artifact_path.with_suffix(".prompt.txt")
    prompt_path.write_text(prompt, encoding="utf-8")

    child_env = os.environ.copy()
    for key, value in load_dotenv(env_file or REPO_ROOT / ".env").items():
        child_env.setdefault(key, value)
    child_env["LOG_LEVEL"] = "error"
    command = [
        "node",
        str(bundle_path),
        "--workspace",
        str(workspace),
        "--task-file",
        str(prompt_path),
        "--session-id",
        session_id,
        "--budget",
        str(budget),
        "--output",
        str(artifact_path),
    ]
    started = time.monotonic()
    execution = subprocess.run(
        command,
        cwd=REPO_ROOT,
        env=child_env,
        text=True,
        capture_output=True,
        timeout=timeout_seconds,
        check=False,
    )
    duration = time.monotonic() - started
    artifact_path.with_suffix(".stdout.txt").write_text(
        execution.stdout, encoding="utf-8"
    )
    artifact_path.with_suffix(".stderr.txt").write_text(
        execution.stderr, encoding="utf-8"
    )
    if execution.returncode != 0:
        tail = (execution.stderr or execution.stdout)[-2000:]
        raise RuntimeError(f"Roy exited with code {execution.returncode}: {tail}")
    if not artifact_path.is_file():
        raise RuntimeError("Roy completed without writing its JSON artifact")

    artifact = json.loads(artifact_path.read_text(encoding="utf-8"))
    return RoyInvocation(
        response=str(artifact["result"]["finalResponse"]),
        artifact_path=artifact_path,
        duration_seconds=duration,
        telemetry=_telemetry(artifact),
    )
