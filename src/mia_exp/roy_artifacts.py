"""Benchmark-neutral summaries for Roy run artifacts and execution trees."""

from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path
from typing import Any, Iterable


_ARTIFACT_NAME = re.compile(r"^(?:roy|spymaster|guesser|roy-run-\d+)\.json$")


def discover_roy_artifacts(paths: Iterable[Path]) -> list[Path]:
    """Resolve explicit artifacts and recursively discover known artifact names."""

    discovered: set[Path] = set()
    for raw_path in paths:
        path = raw_path.expanduser().resolve()
        if path.is_file():
            discovered.add(path)
            continue
        if not path.is_dir():
            raise FileNotFoundError(path)
        discovered.update(
            candidate
            for candidate in path.rglob("*.json")
            if _ARTIFACT_NAME.match(candidate.name)
        )
    if not discovered:
        raise ValueError("no Roy run artifacts found")
    return sorted(discovered)


def _read_artifact(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"expected a JSON object: {path}")
    result = payload.get("result")
    if not isinstance(result, dict):
        raise ValueError(f"missing Roy result object: {path}")
    return payload


def _actor(node: dict[str, Any]) -> dict[str, Any]:
    return {
        key: node.get(key)
        for key in (
            "id",
            "kind",
            "name",
            "role",
            "parentId",
            "generation",
            "status",
            "tokenUsage",
        )
        if node.get(key) is not None
    }


def _step(step: dict[str, Any]) -> dict[str, Any]:
    decision = step.get("decision")
    decision = decision if isinstance(decision, dict) else {}
    snapshot = step.get("treeSnapshot")
    snapshot = snapshot if isinstance(snapshot, list) else []
    step_index = step.get("index")
    new_actors = [
        _actor(node)
        for node in snapshot
        if isinstance(node, dict) and node.get("createdAtStep") == step_index
    ]
    activities = step.get("activities")
    activities = activities if isinstance(activities, list) else []
    activity_counts = Counter(
        str(activity.get("kind") or "unknown")
        for activity in activities
        if isinstance(activity, dict)
    )
    feedback = [
        {
            "actorId": activity.get("actorId"),
            "eventType": activity.get("eventType"),
            "summary": activity.get("summary"),
        }
        for activity in activities
        if isinstance(activity, dict)
        and (
            activity.get("kind") == "feedback"
            or "feedback" in str(activity.get("eventType") or "")
        )
    ]
    return {
        "id": step.get("id"),
        "index": step_index,
        "status": step.get("status"),
        "dependsOn": step.get("dependsOn") or [],
        "decision": {
            key: decision.get(key)
            for key in ("action", "reason", "agentCount")
            if decision.get(key) is not None
        },
        "actorIds": step.get("actorIds") or [],
        "teamIds": step.get("teamIds") or [],
        "newActors": new_actors,
        "activityCounts": dict(sorted(activity_counts.items())),
        "feedback": feedback,
    }


def summarize_roy_artifact(path: Path) -> dict[str, Any]:
    """Create a compact, inspectable execution summary for one Roy artifact."""

    payload = _read_artifact(path)
    result = payload["result"]
    tree = result.get("executionTree")
    tree = tree if isinstance(tree, dict) else {}
    nodes = tree.get("nodes")
    nodes = nodes if isinstance(nodes, list) else []
    steps = tree.get("steps")
    steps = steps if isinstance(steps, list) else []
    actors = [_actor(node) for node in nodes if isinstance(node, dict)]
    usage = result.get("usage")
    usage = usage if isinstance(usage, dict) else {}
    total_usage = usage.get("total")
    total_usage = total_usage if isinstance(total_usage, dict) else {}
    recursive_actors = [
        actor for actor in actors if int(actor.get("generation") or 0) >= 2
    ]
    root_agent_id = tree.get("rootAgentId") or "root"
    derived_agents = [
        actor
        for actor in actors
        if actor.get("kind") == "agent" and actor.get("id") != root_agent_id
    ]
    derived_teams = [actor for actor in actors if actor.get("kind") == "team"]
    return {
        "artifact": str(path),
        "sessionId": payload.get("sessionId"),
        "status": payload.get("status"),
        "correlationId": result.get("correlationId"),
        "decision": (result.get("decision") or {}).get("action"),
        "treeStatus": tree.get("status"),
        "rootAgentId": root_agent_id,
        "stepCount": len(steps),
        "actorCount": len(actors),
        "derivedAgentCount": len(derived_agents),
        "derivedTeamCount": len(derived_teams),
        "maxActorGeneration": max(
            (int(actor.get("generation") or 0) for actor in actors),
            default=0,
        ),
        "recursiveActorIds": [
            str(actor["id"]) for actor in recursive_actors if actor.get("id")
        ],
        "actors": actors,
        "steps": [_step(step) for step in steps if isinstance(step, dict)],
        "usage": {
            key: total_usage.get(key)
            for key in (
                "llmCalls",
                "inputTokens",
                "cachedInputTokens",
                "outputTokens",
                "totalTokens",
            )
            if total_usage.get(key) is not None
        },
    }


def summarize_roy_artifacts(paths: Iterable[Path]) -> dict[str, Any]:
    """Summarize one or more Roy artifacts with a common aggregate contract."""

    artifacts = [
        summarize_roy_artifact(path) for path in discover_roy_artifacts(paths)
    ]

    def total(field: str) -> int:
        return sum(int(item["usage"].get(field) or 0) for item in artifacts)

    return {
        "schemaVersion": 1,
        "artifacts": artifacts,
        "aggregate": {
            "artifactCount": len(artifacts),
            "completedArtifacts": sum(
                item["status"] == "completed" for item in artifacts
            ),
            "executionSteps": sum(item["stepCount"] for item in artifacts),
            "derivedActors": sum(
                item["derivedAgentCount"] + item["derivedTeamCount"]
                for item in artifacts
            ),
            "derivedAgents": sum(
                item["derivedAgentCount"] for item in artifacts
            ),
            "derivedTeams": sum(item["derivedTeamCount"] for item in artifacts),
            "recursiveActors": sum(
                len(item["recursiveActorIds"]) for item in artifacts
            ),
            "maxActorGeneration": max(
                (item["maxActorGeneration"] for item in artifacts),
                default=0,
            ),
            "llmCalls": total("llmCalls"),
            "inputTokens": total("inputTokens"),
            "cachedInputTokens": total("cachedInputTokens"),
            "outputTokens": total("outputTokens"),
            "totalTokens": total("totalTokens"),
        },
    }


def render_roy_summary_markdown(summary: dict[str, Any]) -> str:
    """Render the compact summary as a human-readable step and actor view."""

    aggregate = summary["aggregate"]
    lines = [
        "# Roy execution summary",
        "",
        (
            f"Artifacts: {aggregate['artifactCount']}; "
            f"steps: {aggregate['executionSteps']}; "
            f"derived agents: {aggregate['derivedAgents']}; "
            f"derived teams: {aggregate['derivedTeams']}; "
            f"recursive actors: {aggregate['recursiveActors']}; "
            f"max generation: {aggregate['maxActorGeneration']}."
        ),
        "",
        (
            f"Tokens: {aggregate['inputTokens']} input, "
            f"{aggregate['cachedInputTokens']} cached input, "
            f"{aggregate['outputTokens']} output across "
            f"{aggregate['llmCalls']} model calls."
        ),
    ]
    for artifact in summary["artifacts"]:
        lines.extend(
            [
                "",
                f"## {artifact['sessionId'] or Path(artifact['artifact']).name}",
                "",
                (
                    f"Status: `{artifact['status']}`; tree: "
                    f"`{artifact['treeStatus']}`; decision: "
                    f"`{artifact['decision']}`."
                ),
            ]
        )
        for step in artifact["steps"]:
            decision = step["decision"]
            lines.extend(
                [
                    "",
                    (
                        f"### Step {step['index']}: "
                        f"{decision.get('action', 'unknown')}"
                    ),
                    "",
                    decision.get("reason", "No decision reason recorded."),
                ]
            )
            if step["newActors"]:
                lines.extend(["", "New actors:"])
                for actor in step["newActors"]:
                    parent = actor.get("parentId") or "none"
                    lines.append(
                        f"- `{actor.get('id')}` ({actor.get('kind')}, "
                        f"{actor.get('role')}, parent `{parent}`, "
                        f"generation {actor.get('generation', 0)})"
                    )
            if step["feedback"]:
                lines.extend(["", "Feedback:"])
                for feedback in step["feedback"]:
                    lines.append(
                        f"- {feedback.get('summary') or feedback.get('eventType')}"
                    )
    return "\n".join(lines) + "\n"
