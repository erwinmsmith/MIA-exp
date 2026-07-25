"""Reproducible Roy runner for the SPP benchmark suite."""

from __future__ import annotations

import json
import os
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterable

from .benchmarks.contracts import ItemScore, aggregate_scores
from .benchmarks.registry import REPO_ROOT, BenchmarkSpec, get_benchmark
from .benchmarks.spp import (
    load_instances,
    parse_hint,
    render_prompt,
    score_response,
)
from .roy_runner import RoyInvocation, RoyInvocationFailure, load_dotenv, run_roy


def _git_revision(path: Path) -> str:
    return subprocess.run(
        ["git", "-C", str(path), "rev-parse", "HEAD"],
        text=True,
        capture_output=True,
        check=True,
    ).stdout.strip()


def _runtime_identity() -> dict[str, Any]:
    env = {**load_dotenv(REPO_ROOT / ".env"), **os.environ}
    if env.get("DEEPSEEK_API_KEY"):
        provider = "deepseek"
    elif env.get("OPENAI_API_KEY"):
        provider = "openai"
    elif env.get("ANTHROPIC_API_KEY"):
        provider = "anthropic"
    else:
        provider = None
    return {
        "provider": provider,
        "model": env.get("DEFAULT_MODEL"),
        "miaExpCommit": _git_revision(REPO_ROOT),
        "royCommit": _git_revision(REPO_ROOT / "core" / "Roy"),
        "benchmarkCommit": _git_revision(REPO_ROOT / "benchmarks" / "SPP"),
    }


def _invocation_record(invocation: RoyInvocation, run_root: Path) -> dict[str, Any]:
    return {
        "artifact": str(invocation.artifact_path.relative_to(run_root)),
        "durationSeconds": invocation.duration_seconds,
        "telemetry": invocation.telemetry,
    }


def _failed_score(
    spec: BenchmarkSpec, instance: dict[str, Any], error: str
) -> ItemScore:
    score = score_response(spec.id, instance, "")
    return ItemScore(
        metric=score.metric,
        earned=0,
        possible=score.possible,
        parsed=False,
        details={"runnerError": error},
    )


def run_benchmark(
    benchmark_id: str,
    *,
    indices: Iterable[int],
    output_dir: Path | None = None,
    budget: int = 30000,
    timeout_seconds: int = 1200,
) -> Path:
    """Run selected items and write append-safe raw records plus a summary."""

    spec = get_benchmark(benchmark_id)
    if spec.suite != "spp":
        raise ValueError("run_benchmark currently accepts SPP benchmarks only")
    instances = load_instances(spec)
    selected = list(indices)
    if not selected:
        raise ValueError("at least one item index is required")
    if len(set(selected)) != len(selected):
        raise ValueError("item indices must be unique")
    invalid = [index for index in selected if index < 0 or index >= len(instances)]
    if invalid:
        raise IndexError(f"item indices out of range: {invalid}")

    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    run_root = (
        output_dir.resolve()
        if output_dir
        else REPO_ROOT / "results" / "spp" / benchmark_id / timestamp
    )
    if (run_root / "run.json").exists() or (run_root / "items.jsonl").exists():
        raise FileExistsError(
            f"run directory already contains a benchmark run: {run_root}"
        )
    run_root.mkdir(parents=True, exist_ok=True)
    records_path = run_root / "items.jsonl"
    identity = _runtime_identity()
    metadata = {
        "schemaVersion": 1,
        "benchmarkId": spec.id,
        "benchmarkName": spec.name,
        "source": {"url": spec.source_url, "commit": spec.source_commit},
        "primaryMetric": spec.primary_metric,
        "budgetPerRoyInvocation": budget,
        "timeoutSeconds": timeout_seconds,
        "indices": selected,
        **identity,
        "startedAt": datetime.now(UTC).isoformat(),
    }
    (run_root / "run.json").write_text(
        json.dumps(metadata, indent=2) + "\n", encoding="utf-8"
    )

    completed_scores: list[ItemScore] = []
    for index in selected:
        instance = instances[index]
        item_dir = run_root / "raw" / f"{index:04d}"
        invocations: dict[str, Any] = {}
        response = ""
        error: str | None = None
        hint: str | None = None
        active_invocation_role = "solver"
        try:
            if spec.id == "spp.codenames-collaborative":
                active_invocation_role = "spymaster"
                spymaster = run_roy(
                    render_prompt(spec.id, instance, stage="spymaster"),
                    workspace=item_dir / "spymaster-workspace",
                    artifact_path=item_dir / "spymaster.json",
                    session_id=f"{timestamp}-{index}-spymaster",
                    budget=budget,
                    timeout_seconds=timeout_seconds,
                )
                invocations["spymaster"] = _invocation_record(spymaster, run_root)
                hint = parse_hint(spymaster.response)
                if not hint:
                    raise ValueError("Roy did not emit a parseable FINAL_HINT")
                active_invocation_role = "guesser"
                guesser = run_roy(
                    render_prompt(spec.id, instance, stage="guesser", hint=hint),
                    workspace=item_dir / "guesser-workspace",
                    artifact_path=item_dir / "guesser.json",
                    session_id=f"{timestamp}-{index}-guesser",
                    budget=budget,
                    timeout_seconds=timeout_seconds,
                )
                invocations["guesser"] = _invocation_record(guesser, run_root)
                response = guesser.response
            else:
                invocation = run_roy(
                    render_prompt(spec.id, instance),
                    workspace=item_dir / "workspace",
                    artifact_path=item_dir / "roy.json",
                    session_id=f"{timestamp}-{index}",
                    budget=budget,
                    timeout_seconds=timeout_seconds,
                )
                invocations["solver"] = _invocation_record(invocation, run_root)
                response = invocation.response
            score = score_response(spec.id, instance, response)
            status = "completed"
        except Exception as caught:  # Keep a scoreable record for failed trials.
            if isinstance(caught, RoyInvocationFailure):
                invocations[active_invocation_role] = _invocation_record(
                    caught.invocation,
                    run_root,
                )
            error = f"{type(caught).__name__}: {caught}"
            score = _failed_score(spec, instance, error)
            status = "failed"

        completed_scores.append(score)
        record = {
            "schemaVersion": 1,
            "benchmarkId": spec.id,
            "index": index,
            "status": status,
            "hint": hint,
            "score": score.to_dict(),
            "invocations": invocations,
            "error": error,
            "completedAt": datetime.now(UTC).isoformat(),
        }
        with records_path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(record) + "\n")

    summary = {
        "schemaVersion": 1,
        "benchmarkId": spec.id,
        "metric": spec.primary_metric["name"],
        **aggregate_scores(completed_scores),
        "failedItems": sum(not item.parsed for item in completed_scores),
        "completedAt": datetime.now(UTC).isoformat(),
    }
    (run_root / "summary.json").write_text(
        json.dumps(summary, indent=2) + "\n", encoding="utf-8"
    )
    return run_root
