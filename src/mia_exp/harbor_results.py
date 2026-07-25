"""Benchmark-neutral Harbor result normalization and pass@k metrics."""

from __future__ import annotations

import json
import math
from collections import defaultdict
from pathlib import Path
from statistics import fmean
from typing import Any, Iterable


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"expected a JSON object: {path}")
    return payload


def _trial_reward(payload: dict[str, Any]) -> float | None:
    verifier = payload.get("verifier_result")
    if not isinstance(verifier, dict):
        return None
    rewards = verifier.get("rewards")
    if not isinstance(rewards, dict) or len(rewards) != 1:
        return None
    reward = next(iter(rewards.values()))
    if isinstance(reward, bool) or not isinstance(reward, (int, float)):
        return None
    normalized = float(reward)
    return normalized if math.isfinite(normalized) else None


def _pass_at_k(total: int, passed: int, k: int) -> float | None:
    """Return the standard unbiased pass@k estimator for one task."""

    if k <= 0:
        raise ValueError("k must be positive")
    if total < k:
        return None
    if total - passed < k:
        return 1.0
    product = 1.0
    for index in range(k):
        product *= (total - passed - index) / (total - index)
    return 1.0 - product


def summarize_harbor_job(
    job_dir: Path,
    *,
    success_threshold: float = 0.95,
    k_values: Iterable[int] = (1, 5),
) -> dict[str, Any]:
    """Normalize one Harbor job and compute threshold-aware pass@k metrics."""

    job_dir = job_dir.resolve()
    if not 0.0 <= success_threshold <= 1.0:
        raise ValueError("success_threshold must be in [0, 1]")
    requested_k = sorted(set(int(value) for value in k_values))
    if not requested_k or requested_k[0] <= 0:
        raise ValueError("k_values must contain positive integers")

    job_result_path = job_dir / "result.json"
    job_result = _read_json(job_result_path)
    trials_by_task: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for result_path in sorted(job_dir.glob("*/result.json")):
        payload = _read_json(result_path)
        task_name = str(payload.get("task_name") or result_path.parent.name)
        reward = _trial_reward(payload)
        exception = payload.get("exception_info")
        trials_by_task[task_name].append(
            {
                "trialName": str(
                    payload.get("trial_name") or result_path.parent.name
                ),
                "resultPath": str(result_path),
                "startedAt": payload.get("started_at"),
                "finishedAt": payload.get("finished_at"),
                "reward": reward,
                "passed": reward is not None and reward >= success_threshold,
                "exceptionType": (
                    str(exception.get("exception_type"))
                    if isinstance(exception, dict)
                    and exception.get("exception_type")
                    else None
                ),
            }
        )

    tasks: dict[str, dict[str, Any]] = {}
    for task_name, trials in sorted(trials_by_task.items()):
        trials.sort(
            key=lambda trial: (
                str(trial.get("startedAt") or ""),
                str(trial["trialName"]),
            )
        )
        rewards = [
            float(trial["reward"])
            for trial in trials
            if trial["reward"] is not None
        ]
        passed = sum(bool(trial["passed"]) for trial in trials)
        task_pass_at_k = {
            str(k): _pass_at_k(len(trials), passed, k) for k in requested_k
        }
        observed_pass_at_k = {
            str(k): (
                any(bool(trial["passed"]) for trial in trials[:k])
                if len(trials) >= k
                else None
            )
            for k in requested_k
        }
        tasks[task_name] = {
            "attempts": len(trials),
            "scoredAttempts": len(rewards),
            "passes": passed,
            "meanReward": fmean(rewards) if rewards else None,
            "bestReward": max(rewards) if rewards else None,
            "firstAttemptReward": trials[0]["reward"] if trials else None,
            "passAtK": task_pass_at_k,
            "observedPassAtK": observed_pass_at_k,
            "trials": trials,
        }

    stats = job_result.get("stats")
    stats = stats if isinstance(stats, dict) else {}
    aggregate_pass_at_k: dict[str, float | None] = {}
    all_tasks_observed_pass_at_k: dict[str, bool | None] = {}
    for k in requested_k:
        key = str(k)
        values = [task["passAtK"][key] for task in tasks.values()]
        aggregate_pass_at_k[key] = (
            fmean(float(value) for value in values)
            if values and all(value is not None for value in values)
            else None
        )
        observed = [task["observedPassAtK"][key] for task in tasks.values()]
        all_tasks_observed_pass_at_k[key] = (
            all(bool(value) for value in observed)
            if observed and all(value is not None for value in observed)
            else None
        )

    task_mean_rewards = [
        float(task["meanReward"])
        for task in tasks.values()
        if task["meanReward"] is not None
    ]
    best_rewards = [
        float(task["bestReward"])
        for task in tasks.values()
        if task["bestReward"] is not None
    ]
    total_trials = int(job_result.get("n_total_trials") or 0)
    completed_trials = int(stats.get("n_completed_trials") or 0)
    errored_trials = int(stats.get("n_errored_trials") or 0)
    cancelled_trials = int(stats.get("n_cancelled_trials") or 0)
    pending_trials = int(stats.get("n_pending_trials") or 0)
    recorded_trials = sum(int(task["attempts"]) for task in tasks.values())
    evals = stats.get("evals")
    return {
        "schemaVersion": 1,
        "jobDir": str(job_dir),
        "jobResult": str(job_result_path),
        "successThreshold": success_threshold,
        "requestedK": requested_k,
        "tasks": tasks,
        "aggregate": {
            "taskCount": len(tasks),
            "totalTrials": total_trials,
            "completedTrials": completed_trials,
            "erroredTrials": errored_trials,
            "cancelledTrials": cancelled_trials,
            "pendingTrials": pending_trials,
            "missingTrialResults": max(total_trials - recorded_trials, 0),
            "macroMeanReward": (
                fmean(task_mean_rewards) if task_mean_rewards else None
            ),
            "minimumBestReward": min(best_rewards) if best_rewards else None,
            "everyTaskReachedThreshold": (
                len(best_rewards) == len(tasks)
                and bool(tasks)
                and all(reward >= success_threshold for reward in best_rewards)
            ),
            "passAtK": aggregate_pass_at_k,
            "allTasksObservedPassAtK": all_tasks_observed_pass_at_k,
            "inputTokens": stats.get("n_input_tokens"),
            "cacheTokens": stats.get("n_cache_tokens"),
            "outputTokens": stats.get("n_output_tokens"),
            "costUsd": stats.get("cost_usd"),
        },
        "harborPassAtK": {
            key: value.get("pass_at_k", {})
            for key, value in (
                evals.items() if isinstance(evals, dict) else []
            )
            if isinstance(value, dict)
        },
    }


def write_harbor_summary(
    job_dir: Path,
    output: Path,
    *,
    success_threshold: float = 0.95,
    k_values: Iterable[int] = (1, 5),
) -> dict[str, Any]:
    summary = summarize_harbor_job(
        job_dir,
        success_threshold=success_threshold,
        k_values=k_values,
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(summary, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return summary
