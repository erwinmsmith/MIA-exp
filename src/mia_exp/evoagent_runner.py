"""Reproducible EvoAgent baseline runner for the registered SPP tasks.

The upstream repository is intentionally read-only.  This module loads its
published prompt strings directly from the pinned source tree, while providing
the run selection, transport, tracing, and common scoring contract needed by
MIA-exp.
"""

from __future__ import annotations

import ast
import json
import os
import random
import re
import subprocess
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterable

from .benchmarks.contracts import ItemScore, aggregate_scores
from .benchmarks.registry import REPO_ROOT, BenchmarkSpec, get_benchmark
from .benchmarks.spp import load_instances, score_response
from .roy_runner import load_dotenv


EVOAGENT_ROOT = REPO_ROOT / "baselines" / "EvoAgent"
UPSTREAM_SPP_ROOT = EVOAGENT_ROOT / "spp"
DEFAULT_INDIVIDUALS = 3
DEFAULT_REQUEST_TIMEOUT_SECONDS = 300
DEFAULT_TRANSPORT_ATTEMPTS = 6


@dataclass(frozen=True)
class ModelConfig:
    provider: str
    model: str
    base_url: str
    api_key: str


@dataclass(frozen=True)
class Completion:
    content: str
    usage: dict[str, Any]
    duration_seconds: float
    transport_attempts: int


def _git_revision(path: Path) -> str:
    return subprocess.run(
        ["git", "-C", str(path), "rev-parse", "HEAD"],
        text=True,
        capture_output=True,
        check=True,
    ).stdout.strip()


def resolve_model_config(env_file: Path | None = None) -> ModelConfig:
    """Resolve the same provider precedence and model setting used by Roy."""

    env = {**load_dotenv(env_file or REPO_ROOT / ".env"), **os.environ}
    model = env.get("DEFAULT_MODEL", "").strip()
    if env.get("DEEPSEEK_API_KEY"):
        return ModelConfig(
            provider="deepseek",
            model=model or "deepseek-v4-flash",
            base_url=env.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
            api_key=env["DEEPSEEK_API_KEY"],
        )
    if env.get("OPENAI_API_KEY"):
        return ModelConfig(
            provider="openai",
            model=model or "gpt-4o",
            base_url=env.get("OPENAI_BASE_URL", "https://api.openai.com/v1"),
            api_key=env["OPENAI_API_KEY"],
        )
    raise RuntimeError(
        "EvoAgent SPP reproduction requires DEEPSEEK_API_KEY or OPENAI_API_KEY"
    )


class OpenAICompatibleClient:
    """Small dependency-free chat client with bounded transport recovery."""

    def __init__(
        self,
        config: ModelConfig,
        *,
        timeout_seconds: int = DEFAULT_REQUEST_TIMEOUT_SECONDS,
        max_attempts: int = DEFAULT_TRANSPORT_ATTEMPTS,
    ) -> None:
        if timeout_seconds <= 0 or max_attempts <= 0:
            raise ValueError("timeout_seconds and max_attempts must be positive")
        self.config = config
        self.timeout_seconds = timeout_seconds
        self.max_attempts = max_attempts

    def complete(self, prompt: str) -> Completion:
        endpoint = f"{self.config.base_url.rstrip('/')}/chat/completions"
        body = json.dumps(
            {
                "model": self.config.model,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0,
                "stream": False,
            }
        ).encode()
        request = urllib.request.Request(
            endpoint,
            data=body,
            headers={
                "Authorization": f"Bearer {self.config.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        started = time.monotonic()
        last_error: Exception | None = None
        for attempt in range(1, self.max_attempts + 1):
            try:
                with urllib.request.urlopen(
                    request, timeout=self.timeout_seconds
                ) as response:
                    payload = json.loads(response.read().decode())
                message = payload["choices"][0]["message"]
                content = message.get("content") or message.get("reasoning_content") or ""
                if not content.strip():
                    raise RuntimeError("model returned an empty completion")
                return Completion(
                    content=content,
                    usage=_normalize_usage(payload.get("usage"), self.config),
                    duration_seconds=time.monotonic() - started,
                    transport_attempts=attempt,
                )
            except (
                TimeoutError,
                urllib.error.HTTPError,
                urllib.error.URLError,
                json.JSONDecodeError,
                KeyError,
                IndexError,
                RuntimeError,
            ) as caught:
                last_error = caught
                if attempt == self.max_attempts or not _is_retryable(caught):
                    break
                delay = min(30.0, (2 ** (attempt - 1)) + random.random())
                time.sleep(delay)
        raise RuntimeError(
            f"model request failed after {self.max_attempts} attempts: {last_error}"
        ) from last_error


def _is_retryable(error: Exception) -> bool:
    if isinstance(error, urllib.error.HTTPError):
        return error.code in {408, 409, 429} or error.code >= 500
    return True


def _usage_number(usage: dict[str, Any], *paths: tuple[str, ...]) -> int | None:
    for path in paths:
        value: Any = usage
        for key in path:
            if not isinstance(value, dict):
                value = None
                break
            value = value.get(key)
        if isinstance(value, (int, float)):
            return max(0, int(value))
    return None


def _normalize_usage(
    raw_usage: Any, config: ModelConfig
) -> dict[str, Any]:
    usage = raw_usage if isinstance(raw_usage, dict) else {}
    input_tokens = _usage_number(usage, ("prompt_tokens",), ("input_tokens",))
    output_tokens = _usage_number(
        usage, ("completion_tokens",), ("output_tokens",)
    )
    total_tokens = _usage_number(usage, ("total_tokens",))
    cached_input_tokens = _usage_number(
        usage,
        ("prompt_tokens_details", "cached_tokens"),
        ("cached_input_tokens",),
        ("cache_read_input_tokens",),
    )
    thinking_tokens = _usage_number(
        usage,
        ("completion_tokens_details", "reasoning_tokens"),
        ("reasoning_tokens",),
        ("thinking_tokens",),
    )
    return {
        "provider": config.provider,
        "model": config.model,
        "inputTokens": input_tokens,
        "outputTokens": output_tokens,
        "totalTokens": (
            total_tokens
            if total_tokens is not None
            else (input_tokens or 0) + (output_tokens or 0)
        ),
        "cachedInputTokens": cached_input_tokens,
        "thinkingTokens": thinking_tokens,
        "reported": bool(usage),
        "raw": usage,
    }


def _load_prompt_constants(path: Path) -> dict[str, str]:
    """Read literal prompt constants without importing upstream dependencies."""

    if not path.is_file():
        raise FileNotFoundError(
            f"pinned EvoAgent prompt source is missing: {path}; "
            "run scripts/prepare-evoagent.sh"
        )
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    constants: dict[str, str] = {}
    for node in tree.body:
        if not isinstance(node, ast.Assign) or not isinstance(node.value, ast.Constant):
            continue
        if not isinstance(node.value.value, str):
            continue
        for target in node.targets:
            if isinstance(target, ast.Name):
                constants[target.id] = node.value.value
    return constants


def load_official_prompts(benchmark_id: str) -> dict[str, str]:
    if benchmark_id == "spp.logic-grid-puzzle":
        constants = _load_prompt_constants(UPSTREAM_SPP_ROOT / "agent_prompt_logic.py")
        names = (
            "INSTRUCTION_META",
            "INSTRUCTION_CHECK",
            "INSTRUCTION_MULTI",
            "INSTRUCTION_REFINE",
        )
    elif benchmark_id.startswith("spp.trivia-creative-writing-"):
        constants = _load_prompt_constants(
            UPSTREAM_SPP_ROOT / "agent_prompt_writing.py"
        )
        names = (
            "INSTRUCTION_META",
            "INSTRUCTION_CHECK",
            "INSTRUCTION_MULTI",
            "INSTRUCTION_REFINE",
        )
    elif benchmark_id == "spp.codenames-collaborative":
        constants = _load_prompt_constants(UPSTREAM_SPP_ROOT / "agent_prompt_code.py")
        names = (
            "SPY_INSTRUCTION_META",
            "SPY_INSTRUCTION_MULTI",
            "SPY_INSTRUCTION_REFINE",
            "GUESS_INSTRUCTION_META",
            "GUESS_INSTRUCTION_MULTI",
            "GUESS_INSTRUCTION_REFINE",
            "INSTRUCTION_CHECK",
        )
    else:
        raise KeyError(f"unsupported EvoAgent SPP benchmark: {benchmark_id}")
    missing = [name for name in names if name not in constants]
    if missing:
        raise ValueError(f"upstream EvoAgent prompts are missing constants: {missing}")
    return {name: constants[name] for name in names}


def render_official_initial_prompt(
    benchmark_id: str,
    instance: dict[str, Any],
    *,
    role: str | None = None,
    hint: str | None = None,
) -> str:
    """Render the initial query exactly as the published EvoAgent entrypoints."""

    if benchmark_id == "spp.logic-grid-puzzle":
        # The current SPP checkout appends an answer cue that was absent from the
        # dataset vendored by EvoAgent. Removing only that cue reproduces the
        # published EvoAgent input while preserving the same puzzle and target.
        return str(instance["inputs"]).removesuffix("A:")
    if benchmark_id.startswith("spp.trivia-creative-writing-"):
        questions = "\n".join(instance["questions"])
        count = len(instance["questions"])
        return (
            f"Write a short and coherent story about {instance['topic']} that "
            f"incorporates the answers to the following {count} questions: "
            f"\n{questions}\nAnswer:"
        ).strip()
    if benchmark_id == "spp.codenames-collaborative":
        count = len(instance["target_words"])
        if role == "spymaster":
            return (
                "Try to find a single word hint that can accurately represent and "
                f'link the {count} given words: "{instance["target_words"]}". The '
                "key is to select a hint that does not cause confusion with other "
                f"words from the following word list: {instance['word_list']}.\n"
                "You need to give reasons first and then give the answer with the "
                'format: "Final Answer: <a single word from the word list>" \n'
                "Answer:\n"
            )
        if role == "guesser":
            if hint is None:
                raise ValueError("the Codenames guesser requires a hint")
            return (
                f'Try to identify the {count} words best associated with the word '
                f'"{hint}" from the following word list: {instance["word_list"]}.\n'
                "You need to give reasons first and then give the answer with the "
                f'format: "Final Answer: <a comma-separated list of {count} words '
                'from the word list>" \nAnswer:\n'
            )
        raise ValueError("Codenames requires role='spymaster' or role='guesser'")
    raise KeyError(f"unsupported EvoAgent SPP benchmark: {benchmark_id}")


class EvoAgentSession:
    def __init__(
        self,
        client: OpenAICompatibleClient,
        benchmark_id: str,
        *,
        item_index: int,
    ) -> None:
        self.client = client
        self.benchmark_id = benchmark_id
        self.item_index = item_index
        self.calls: list[dict[str, Any]] = []

    def complete(
        self,
        prompt: str,
        *,
        role: str,
        phase: str,
        generation: int | None = None,
        candidate_attempt: int | None = None,
    ) -> str:
        completion = self.client.complete(prompt)
        self.calls.append(
            {
                "callIndex": len(self.calls),
                "role": role,
                "phase": phase,
                "generation": generation,
                "candidateAttempt": candidate_attempt,
                "prompt": prompt,
                "response": completion.content,
                "usage": completion.usage,
                "durationSeconds": completion.duration_seconds,
                "transportAttempts": completion.transport_attempts,
            }
        )
        return completion.content


def _evolve(
    session: EvoAgentSession,
    *,
    question: str,
    answer: str,
    individuals: int,
    role: str,
    meta_prompt: str,
    check_prompt: str,
    multi_prompt: str,
    refine_prompt: str,
    extra_format: dict[str, Any] | None = None,
) -> tuple[str, list[dict[str, Any]]]:
    descriptions: list[str] = []
    trajectory: list[dict[str, Any]] = []
    extra = extra_format or {}
    for generation in range(individuals):
        checks: list[dict[str, Any]] = []
        for candidate_attempt in range(5):
            description_prompt = meta_prompt.format(
                question=question,
                answer=answer,
                description="\n-".join(descriptions),
                **extra,
            )
            description = session.complete(
                description_prompt,
                role=role,
                phase="expert_generation",
                generation=generation,
                candidate_attempt=candidate_attempt,
            )
            quality_prompt = check_prompt.format(
                question=question,
                description_ls="\n-".join(descriptions),
                description=description,
                **extra,
            )
            quality = session.complete(
                quality_prompt,
                role=role,
                phase="quality_selection",
                generation=generation,
                candidate_attempt=candidate_attempt,
            )
            discarded = "discard" in quality.lower()
            forced_acceptance = discarded and candidate_attempt == 4
            checks.append(
                {
                    "candidateAttempt": candidate_attempt,
                    "description": description,
                    "qualityDecision": quality,
                    "discarded": discarded,
                    "forcedAcceptance": forced_acceptance,
                }
            )
            if not discarded or forced_acceptance:
                descriptions.append(description)
                break

        expert_prompt = multi_prompt.format(
            question=question,
            description=description,
            **extra,
        )
        sub_answer = session.complete(
            expert_prompt,
            role=role,
            phase="expert_answer",
            generation=generation,
        )
        integration_prompt = refine_prompt.format(
            question=question,
            description=description,
            old_answer=answer,
            new_answer=sub_answer,
            **extra,
        )
        new_answer = session.complete(
            integration_prompt,
            role=role,
            phase="result_integration",
            generation=generation,
        )
        trajectory.append(
            {
                "generation": generation,
                "previousAnswer": answer,
                "qualityChecks": checks,
                "acceptedDescription": description,
                "expertAnswer": sub_answer,
                "integratedAnswer": new_answer,
            }
        )
        answer = new_answer
    return answer, trajectory


def _extract_final_answer(response: str) -> str:
    matches = list(
        re.finditer(r"Final\s+Answer\s*:\s*(.*)", response, flags=re.IGNORECASE)
    )
    return (matches[-1].group(1) if matches else response).strip().splitlines()[0]


def _logic_scoring_response(response: str) -> str:
    final = _extract_final_answer(response)
    final = re.sub(r"^choice\s*:\s*", "", final, flags=re.IGNORECASE)
    match = re.search(
        r"\b(first|second|third|fourth|fifth|sixth|seventh|eighth|ninth|tenth|10|[1-9])\b",
        final,
        flags=re.IGNORECASE,
    )
    return f"FINAL_ANSWER: {match.group(1)}" if match else response


def _codenames_hint(response: str) -> str:
    final = _extract_final_answer(response)
    match = re.search(r"[A-Za-z][A-Za-z'-]*", final)
    if not match:
        raise ValueError("EvoAgent did not produce a parseable Codenames hint")
    return match.group(0)


def _usage_totals(calls: list[dict[str, Any]]) -> dict[str, Any]:
    keys = (
        "inputTokens",
        "outputTokens",
        "totalTokens",
        "cachedInputTokens",
        "thinkingTokens",
    )
    totals: dict[str, Any] = {"modelCalls": len(calls)}
    for key in keys:
        values = [
            call["usage"].get(key)
            for call in calls
            if call["usage"].get(key) is not None
        ]
        totals[key] = sum(values) if values else None
    totals["transportAttempts"] = sum(call["transportAttempts"] for call in calls)
    totals["modelDurationSeconds"] = sum(call["durationSeconds"] for call in calls)
    return totals


def _execution_tree(
    trajectories: list[tuple[str, list[dict[str, Any]]]]
) -> dict[str, Any]:
    nodes: list[dict[str, Any]] = [
        {
            "id": "root",
            "kind": "evoagent",
            "parentId": None,
            "generation": 0,
            "label": "EvoAgent",
        }
    ]
    paths: list[list[str]] = []
    for role, trajectory in trajectories:
        role_id = f"role-{role}"
        nodes.append(
            {
                "id": role_id,
                "kind": "role",
                "parentId": "root",
                "generation": 1,
                "label": role,
            }
        )
        for step in trajectory:
            expert_id = f"{role}-expert-{step['generation'] + 1}"
            nodes.append(
                {
                    "id": expert_id,
                    "kind": "evolved_expert",
                    "parentId": role_id,
                    "generation": 2,
                    "label": step["acceptedDescription"],
                }
            )
            paths.append(["root", role_id, expert_id])
    return {"nodes": nodes, "paths": paths, "maxGeneration": 2 if paths else 1}


def run_evoagent_item(
    benchmark_id: str,
    instance: dict[str, Any],
    *,
    item_index: int,
    client: OpenAICompatibleClient,
    individuals: int = DEFAULT_INDIVIDUALS,
    session: EvoAgentSession | None = None,
) -> dict[str, Any]:
    if individuals <= 0:
        raise ValueError("individuals must be positive")
    prompts = load_official_prompts(benchmark_id)
    session = session or EvoAgentSession(client, benchmark_id, item_index=item_index)
    role_trajectories: list[tuple[str, list[dict[str, Any]]]] = []
    hint: str | None = None

    if benchmark_id == "spp.codenames-collaborative":
        spy_question = render_official_initial_prompt(
            benchmark_id, instance, role="spymaster"
        )
        spy_initial = session.complete(
            spy_question, role="spymaster", phase="initialization"
        )
        spy_answer, spy_trajectory = _evolve(
            session,
            question=spy_question,
            answer=spy_initial,
            individuals=individuals,
            role="spymaster",
            meta_prompt=prompts["SPY_INSTRUCTION_META"],
            check_prompt=prompts["INSTRUCTION_CHECK"],
            multi_prompt=prompts["SPY_INSTRUCTION_MULTI"],
            refine_prompt=prompts["SPY_INSTRUCTION_REFINE"],
        )
        role_trajectories.append(("spymaster", spy_trajectory))
        hint = _codenames_hint(spy_answer)
        guess_question = render_official_initial_prompt(
            benchmark_id, instance, role="guesser", hint=hint
        )
        guess_initial = session.complete(
            guess_question, role="guesser", phase="initialization"
        )
        answer, guess_trajectory = _evolve(
            session,
            question=guess_question,
            answer=guess_initial,
            individuals=individuals,
            role="guesser",
            meta_prompt=prompts["GUESS_INSTRUCTION_META"],
            check_prompt=prompts["INSTRUCTION_CHECK"],
            multi_prompt=prompts["GUESS_INSTRUCTION_MULTI"],
            refine_prompt=prompts["GUESS_INSTRUCTION_REFINE"],
            extra_format={"n": len(instance["target_words"])},
        )
        role_trajectories.append(("guesser", guess_trajectory))
        scoring_response = f"FINAL_GUESSES: {_extract_final_answer(answer)}"
    else:
        question = render_official_initial_prompt(benchmark_id, instance)
        initial = session.complete(question, role="solver", phase="initialization")
        answer, trajectory = _evolve(
            session,
            question=question,
            answer=initial,
            individuals=individuals,
            role="solver",
            meta_prompt=prompts["INSTRUCTION_META"],
            check_prompt=prompts["INSTRUCTION_CHECK"],
            multi_prompt=prompts["INSTRUCTION_MULTI"],
            refine_prompt=prompts["INSTRUCTION_REFINE"],
        )
        role_trajectories.append(("solver", trajectory))
        scoring_response = (
            _logic_scoring_response(answer)
            if benchmark_id == "spp.logic-grid-puzzle"
            else answer
        )

    score = score_response(benchmark_id, instance, scoring_response)
    return {
        "hint": hint,
        "finalAnswer": answer,
        "scoringResponse": scoring_response,
        "score": score,
        "trajectories": [
            {"role": role, "steps": trajectory}
            for role, trajectory in role_trajectories
        ],
        "executionTree": _execution_tree(role_trajectories),
        "calls": session.calls,
        "usage": _usage_totals(session.calls),
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


def _aggregate_usage(records: list[dict[str, Any]]) -> dict[str, Any]:
    keys = (
        "modelCalls",
        "inputTokens",
        "outputTokens",
        "totalTokens",
        "cachedInputTokens",
        "thinkingTokens",
        "transportAttempts",
        "modelDurationSeconds",
    )
    totals: dict[str, Any] = {}
    for key in keys:
        values = [
            record["usage"].get(key)
            for record in records
            if record.get("usage", {}).get(key) is not None
        ]
        totals[key] = sum(values) if values else None
    return totals


def run_evoagent_benchmark(
    benchmark_id: str,
    *,
    indices: Iterable[int],
    output_dir: Path | None = None,
    individuals: int = DEFAULT_INDIVIDUALS,
    request_timeout_seconds: int = DEFAULT_REQUEST_TIMEOUT_SECONDS,
    transport_attempts: int = DEFAULT_TRANSPORT_ATTEMPTS,
    env_file: Path | None = None,
) -> Path:
    """Run a deterministic SPP slice through the official EvoAgent method."""

    spec = get_benchmark(benchmark_id)
    if spec.suite != "spp":
        raise ValueError("EvoAgent reproduction currently accepts SPP benchmarks")
    instances = load_instances(spec)
    selected = list(indices)
    if not selected:
        raise ValueError("at least one item index is required")
    if len(selected) != len(set(selected)):
        raise ValueError("item indices must be unique")
    invalid = [index for index in selected if index < 0 or index >= len(instances)]
    if invalid:
        raise IndexError(f"item indices out of range: {invalid}")

    model_config = resolve_model_config(env_file)
    client = OpenAICompatibleClient(
        model_config,
        timeout_seconds=request_timeout_seconds,
        max_attempts=transport_attempts,
    )
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    run_root = (
        output_dir.resolve()
        if output_dir
        else REPO_ROOT / "results" / "evoagent" / benchmark_id / timestamp
    )
    if (run_root / "run.json").exists() or (run_root / "items.jsonl").exists():
        raise FileExistsError(
            f"run directory already contains a benchmark run: {run_root}"
        )
    run_root.mkdir(parents=True, exist_ok=True)
    records_path = run_root / "items.jsonl"
    metadata = {
        "schemaVersion": 1,
        "method": "evoagent",
        "benchmarkId": spec.id,
        "benchmarkName": spec.name,
        "source": {"url": spec.source_url, "commit": spec.source_commit},
        "methodSource": {
            "url": "https://github.com/siyuyuan/evoagent",
            "commit": _git_revision(EVOAGENT_ROOT),
        },
        "primaryMetric": spec.primary_metric,
        "indices": selected,
        "individuals": individuals,
        "temperature": 0,
        "provider": model_config.provider,
        "model": model_config.model,
        "requestTimeoutSeconds": request_timeout_seconds,
        "transportAttempts": transport_attempts,
        "miaExpCommit": _git_revision(REPO_ROOT),
        "evoAgentCommit": _git_revision(EVOAGENT_ROOT),
        "benchmarkCommit": _git_revision(REPO_ROOT / "benchmarks" / "SPP"),
        "promptSource": "pinned upstream EvoAgent Python prompt constants",
        "startedAt": datetime.now(UTC).isoformat(),
    }
    (run_root / "run.json").write_text(
        json.dumps(metadata, indent=2) + "\n", encoding="utf-8"
    )

    scores: list[ItemScore] = []
    records: list[dict[str, Any]] = []
    for index in selected:
        instance = instances[index]
        item_path = run_root / "raw" / f"{index:04d}.json"
        item_path.parent.mkdir(parents=True, exist_ok=True)
        item_session = EvoAgentSession(client, spec.id, item_index=index)
        try:
            result = run_evoagent_item(
                spec.id,
                instance,
                item_index=index,
                client=client,
                individuals=individuals,
                session=item_session,
            )
            score = result.pop("score")
            status = "completed"
            error = None
        except Exception as caught:
            score = _failed_score(
                spec, instance, f"{type(caught).__name__}: {caught}"
            )
            status = "failed"
            error = f"{type(caught).__name__}: {caught}"
            result = {
                "hint": None,
                "finalAnswer": "",
                "scoringResponse": "",
                "trajectories": [],
                "executionTree": {"nodes": [], "paths": [], "maxGeneration": 0},
                "calls": item_session.calls,
                "usage": _usage_totals(item_session.calls),
            }
        raw = {
            "schemaVersion": 1,
            "method": "evoagent",
            "benchmarkId": spec.id,
            "index": index,
            "status": status,
            "error": error,
            "score": score.to_dict(),
            **result,
            "completedAt": datetime.now(UTC).isoformat(),
        }
        item_path.write_text(json.dumps(raw, indent=2) + "\n", encoding="utf-8")
        record = {
            "schemaVersion": 1,
            "method": "evoagent",
            "benchmarkId": spec.id,
            "index": index,
            "status": status,
            "error": error,
            "score": score.to_dict(),
            "artifact": str(item_path.relative_to(run_root)),
            "usage": result["usage"],
            "completedAt": raw["completedAt"],
        }
        with records_path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(record) + "\n")
        scores.append(score)
        records.append(record)

    summary = {
        "schemaVersion": 1,
        "method": "evoagent",
        "benchmarkId": spec.id,
        "metric": spec.primary_metric["name"],
        **aggregate_scores(scores),
        "failedItems": sum(record["status"] == "failed" for record in records),
        "usage": _aggregate_usage(records),
        "completedAt": datetime.now(UTC).isoformat(),
    }
    (run_root / "summary.json").write_text(
        json.dumps(summary, indent=2) + "\n", encoding="utf-8"
    )
    return run_root
