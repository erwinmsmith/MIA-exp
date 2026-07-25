#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"

benchmarks=(
  "spp.logic-grid-puzzle"
  "spp.trivia-creative-writing-n5"
  "spp.trivia-creative-writing-n10"
  "spp.codenames-collaborative"
)
start=0
limit=10
timeout=1800
output_root="$repo_root/results/spp/suite"
budget_args=()

usage() {
  cat <<'EOF'
Usage: run-spp-suite.sh [options]

Run the same reproducible sample window across one or more SPP benchmarks.

Options:
  --benchmarks <ids>  Comma-separated benchmark IDs (default: all four).
  --start <index>     Zero-based first item (default: 0).
  --limit <count>     Items per benchmark (default: 10).
  --timeout <seconds> Per-invocation process timeout (default: 1800).
  --output-root <dir> Suite result root.
  --budget <tokens>   Optional explicit per-invocation token cap.
  -h, --help          Show this help.

No token budget is imposed unless --budget is supplied.
EOF
}

while (($# > 0)); do
  case "$1" in
    --benchmarks)
      IFS=',' read -r -a benchmarks <<<"${2:?--benchmarks requires a value}"
      shift 2
      ;;
    --start)
      start="${2:?--start requires a value}"
      shift 2
      ;;
    --limit)
      limit="${2:?--limit requires a value}"
      shift 2
      ;;
    --timeout)
      timeout="${2:?--timeout requires a value}"
      shift 2
      ;;
    --output-root)
      output_root="${2:?--output-root requires a value}"
      shift 2
      ;;
    --budget)
      budget_args=(--budget "${2:?--budget requires a value}")
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown option: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

case "$start:$limit:$timeout" in
  *[!0-9:]*)
    echo "--start, --limit, and --timeout must be integers" >&2
    exit 2
    ;;
esac
if ((start < 0 || limit <= 0 || timeout <= 0)); then
  echo "--start must be non-negative; --limit and --timeout must be positive" >&2
  exit 2
fi

for benchmark in "${benchmarks[@]}"; do
  case "$benchmark" in
    spp.logic-grid-puzzle|spp.trivia-creative-writing-n5|spp.trivia-creative-writing-n10|spp.codenames-collaborative)
      ;;
    *)
      echo "Unsupported SPP benchmark: $benchmark" >&2
      exit 2
      ;;
  esac
done

mkdir -p "$output_root"
for benchmark in "${benchmarks[@]}"; do
  "$repo_root/scripts/run-spp-roy.sh" \
    "$benchmark" \
    --start "$start" \
    --limit "$limit" \
    --timeout "$timeout" \
    --output "$output_root/$benchmark" \
    "${budget_args[@]}"
done
