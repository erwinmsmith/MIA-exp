"""Manifest-backed benchmark discovery and data-integrity validation."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable


REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_REGISTRY = REPO_ROOT / "experiments" / "benchmarks.json"


@dataclass(frozen=True)
class BenchmarkSpec:
    id: str
    suite: str
    name: str
    adapter: str
    source_url: str
    source_commit: str
    data: dict[str, Any]
    primary_metric: dict[str, Any]

    @property
    def data_path(self) -> Path:
        relative = Path(str(self.data["path"]))
        candidate = (REPO_ROOT / relative).resolve()
        if REPO_ROOT not in candidate.parents and candidate != REPO_ROOT:
            raise ValueError(f"benchmark path escapes repository: {relative}")
        return candidate


def load_registry(
    path: Path = DEFAULT_REGISTRY,
) -> tuple[dict[str, Any], dict[str, BenchmarkSpec]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    specs: dict[str, BenchmarkSpec] = {}
    for raw in payload["benchmarks"]:
        spec = BenchmarkSpec(
            id=raw["id"],
            suite=raw["suite"],
            name=raw["name"],
            adapter=raw["adapter"],
            source_url=raw["source"]["url"],
            source_commit=raw["source"]["commit"],
            data=raw["data"],
            primary_metric=raw["primaryMetric"],
        )
        if spec.id in specs:
            raise ValueError(f"duplicate benchmark id: {spec.id}")
        specs[spec.id] = spec
    return payload, specs


def get_benchmark(benchmark_id: str) -> BenchmarkSpec:
    _, specs = load_registry()
    try:
        return specs[benchmark_id]
    except KeyError as error:
        choices = ", ".join(sorted(specs))
        raise KeyError(
            f"unknown benchmark {benchmark_id!r}; choose from: {choices}"
        ) from error


def iter_benchmarks(suite: str | None = None) -> Iterable[BenchmarkSpec]:
    _, specs = load_registry()
    for spec in specs.values():
        if suite is None or spec.suite == suite:
            yield spec


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate_data(spec: BenchmarkSpec) -> dict[str, Any]:
    """Validate one manifest entry and return a machine-readable report."""

    path = spec.data_path
    report: dict[str, Any] = {
        "benchmarkId": spec.id,
        "path": str(path.relative_to(REPO_ROOT)),
        "ok": False,
    }
    if spec.data.get("format") == "directory":
        report["ok"] = path.is_dir()
        report["kind"] = "directory"
        if not report["ok"]:
            report["error"] = "directory is missing"
        return report

    if not path.is_file():
        report["error"] = "file is missing"
        return report

    actual_sha = _sha256(path)
    actual_items = 0
    if spec.data.get("format") == "jsonl":
        with path.open(encoding="utf-8") as stream:
            for line_number, line in enumerate(stream, start=1):
                if not line.strip():
                    continue
                try:
                    json.loads(line)
                except json.JSONDecodeError as error:
                    report["error"] = f"invalid JSON on line {line_number}: {error}"
                    return report
                actual_items += 1
    else:
        report["error"] = f"unsupported data format: {spec.data.get('format')}"
        return report

    report.update(
        {
            "sha256": actual_sha,
            "expectedSha256": spec.data["sha256"],
            "items": actual_items,
            "expectedItems": spec.data["expectedItems"],
        }
    )
    report["ok"] = (
        actual_sha == spec.data["sha256"] and actual_items == spec.data["expectedItems"]
    )
    if not report["ok"]:
        report["error"] = "checksum or item count mismatch"
    return report
