"""Command-line interface for benchmark discovery, validation, and Roy runs."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .benchmarks.contracts import aggregate_benchmark_summaries
from .benchmarks.registry import get_benchmark, iter_benchmarks, validate_data
from .benchmarks.spp import load_instances, render_prompt, score_response
from .spp_runner import run_benchmark


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="mia-bench")
    commands = parser.add_subparsers(dest="command", required=True)

    list_command = commands.add_parser("list", help="list registered benchmarks")
    list_command.add_argument("--suite")

    validate = commands.add_parser("validate", help="validate benchmark data")
    validate.add_argument("--suite")
    validate.add_argument("--benchmark")

    render = commands.add_parser("render", help="render one SPP task prompt")
    render.add_argument("benchmark")
    render.add_argument("--index", type=int, default=0)
    render.add_argument("--stage", choices=["spymaster", "guesser"])
    render.add_argument("--hint")

    score = commands.add_parser("score", help="score a saved model response")
    score.add_argument("benchmark")
    score.add_argument("--index", type=int, default=0)
    score.add_argument("--response-file", type=Path, required=True)

    aggregate = commands.add_parser(
        "aggregate",
        help="macro-average one summary per benchmark",
    )
    aggregate.add_argument("summaries", type=Path, nargs="+")

    run = commands.add_parser("run", help="run selected SPP items with Roy")
    run.add_argument("benchmark")
    run.add_argument("--start", type=int, default=0)
    run.add_argument("--limit", type=int, default=1)
    run.add_argument("--budget", type=int, default=30000)
    run.add_argument("--timeout", type=int, default=1200)
    run.add_argument("--output", type=Path)
    return parser


def main() -> int:
    args = _parser().parse_args()
    if args.command == "list":
        rows = [
            {
                "id": spec.id,
                "suite": spec.suite,
                "name": spec.name,
                "metric": spec.primary_metric["name"],
            }
            for spec in iter_benchmarks(args.suite)
        ]
        print(json.dumps(rows, indent=2))
        return 0

    if args.command == "validate":
        specs = (
            [get_benchmark(args.benchmark)]
            if args.benchmark
            else list(iter_benchmarks(args.suite))
        )
        reports = [validate_data(spec) for spec in specs]
        print(json.dumps(reports, indent=2))
        return 0 if all(report["ok"] for report in reports) else 1

    if args.command == "aggregate":
        summaries = [
            json.loads(path.read_text(encoding="utf-8")) for path in args.summaries
        ]
        print(json.dumps(aggregate_benchmark_summaries(summaries), indent=2))
        return 0

    spec = get_benchmark(args.benchmark)
    instances = load_instances(spec)

    if args.command == "render":
        if args.index < 0 or args.index >= len(instances):
            raise SystemExit(f"index must be in [0, {len(instances) - 1}]")
        instance = instances[args.index]
        print(
            render_prompt(
                spec.id,
                instance,
                stage=args.stage,
                hint=args.hint,
            )
        )
        return 0

    if args.command == "score":
        if args.index < 0 or args.index >= len(instances):
            raise SystemExit(f"index must be in [0, {len(instances) - 1}]")
        instance = instances[args.index]
        response = args.response_file.read_text(encoding="utf-8")
        print(
            json.dumps(score_response(spec.id, instance, response).to_dict(), indent=2)
        )
        return 0

    if args.command == "run":
        if args.limit <= 0:
            raise SystemExit("--limit must be positive")
        end = min(args.start + args.limit, len(instances))
        run_root = run_benchmark(
            spec.id,
            indices=range(args.start, end),
            output_dir=args.output,
            budget=args.budget,
            timeout_seconds=args.timeout,
        )
        print(run_root)
        print((run_root / "summary.json").read_text(encoding="utf-8"), end="")
        return 0

    raise AssertionError("unreachable")


if __name__ == "__main__":
    raise SystemExit(main())
