"""CLI for the direct single-model SPP baseline."""

from __future__ import annotations

import argparse
from pathlib import Path

from .benchmarks.registry import get_benchmark
from .benchmarks.spp import load_instances
from .evoagent_runner import run_evoagent_benchmark


def main() -> int:
    parser = argparse.ArgumentParser(prog="mia-direct")
    parser.add_argument("benchmark")
    parser.add_argument("--start", type=int, default=0)
    parser.add_argument("--limit", type=int, default=1)
    parser.add_argument("--request-timeout", type=int, default=300)
    parser.add_argument("--transport-attempts", type=int, default=6)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    if args.start < 0:
        raise SystemExit("--start must be non-negative")
    if args.limit <= 0:
        raise SystemExit("--limit must be positive")
    spec = get_benchmark(args.benchmark)
    instances = load_instances(spec)
    end = min(args.start + args.limit, len(instances))
    run_root = run_evoagent_benchmark(
        spec.id,
        indices=range(args.start, end),
        output_dir=args.output,
        request_timeout_seconds=args.request_timeout,
        transport_attempts=args.transport_attempts,
        method="direct",
    )
    print(run_root)
    print((run_root / "summary.json").read_text(encoding="utf-8"), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
