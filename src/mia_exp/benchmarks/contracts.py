"""Benchmark-neutral score and aggregation contracts."""

from __future__ import annotations

from dataclasses import dataclass, field
from statistics import fmean
from typing import Any, Iterable


@dataclass(frozen=True)
class ItemScore:
    """A benchmark item score normalized through an earned/possible ratio."""

    metric: str
    earned: float
    possible: float
    parsed: bool = True
    details: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.possible <= 0:
            raise ValueError("possible must be greater than zero")
        if self.earned < 0 or self.earned > self.possible:
            raise ValueError("earned must be between zero and possible")

    @property
    def score(self) -> float:
        return self.earned / self.possible

    @property
    def exact_match(self) -> bool:
        return self.parsed and self.earned == self.possible

    def to_dict(self) -> dict[str, Any]:
        return {
            "metric": self.metric,
            "earned": self.earned,
            "possible": self.possible,
            "score": self.score,
            "exactMatch": self.exact_match,
            "parsed": self.parsed,
            "details": self.details,
        }


def aggregate_scores(scores: Iterable[ItemScore]) -> dict[str, Any]:
    """Aggregate item scores without discarding their native denominators."""

    items = list(scores)
    if not items:
        raise ValueError("at least one item score is required")
    earned = sum(item.earned for item in items)
    possible = sum(item.possible for item in items)
    return {
        "items": len(items),
        "earned": earned,
        "possible": possible,
        "score": earned / possible,
        "meanItemScore": fmean(item.score for item in items),
        "exactMatches": sum(item.exact_match for item in items),
        "exactMatchRate": fmean(float(item.exact_match) for item in items),
        "parsedItems": sum(item.parsed for item in items),
        "parseRate": fmean(float(item.parsed) for item in items),
    }


def aggregate_benchmark_summaries(
    summaries: Iterable[dict[str, Any]],
) -> dict[str, Any]:
    """Macro-average normalized benchmark summaries without pooling items."""

    items = list(summaries)
    if not items:
        raise ValueError("at least one benchmark summary is required")
    benchmark_ids = [str(item["benchmarkId"]) for item in items]
    if len(set(benchmark_ids)) != len(benchmark_ids):
        raise ValueError("each benchmark may appear only once in a suite aggregate")
    return {
        "benchmarks": len(items),
        "benchmarkIds": benchmark_ids,
        "score": fmean(float(item["score"]) for item in items),
        "exactMatchRate": fmean(float(item["exactMatchRate"]) for item in items),
        "parseRate": fmean(float(item["parseRate"]) for item in items),
        "aggregation": "macro",
    }
