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
request_timeout=300
transport_attempts=6
output_root="$repo_root/results/direct/suite"

usage() {
  cat <<'EOF'
Usage: run-direct-suite.sh [options]

Run a direct single-model baseline on the same SPP sample window.

Options:
  --benchmarks <ids>       Comma-separated benchmark IDs (default: all four).
  --start <index>          Zero-based first item (default: 0).
  --limit <count>          Items per benchmark (default: 10).
  --request-timeout <sec>  Timeout for one model request (default: 300).
  --transport-attempts <n> Bounded retry attempts (default: 6).
  --output-root <dir>      Suite result root.
  -h, --help               Show this help.
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
    --request-timeout)
      request_timeout="${2:?--request-timeout requires a value}"
      shift 2
      ;;
    --transport-attempts)
      transport_attempts="${2:?--transport-attempts requires a value}"
      shift 2
      ;;
    --output-root)
      output_root="${2:?--output-root requires a value}"
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

case "$start:$limit:$request_timeout:$transport_attempts" in
  *[!0-9:]*)
    echo "numeric options must be integers" >&2
    exit 2
    ;;
esac
if ((start < 0 || limit <= 0 || request_timeout <= 0 || transport_attempts <= 0)); then
  echo "start must be non-negative and all other numeric options positive" >&2
  exit 2
fi

mkdir -p "$output_root"
for benchmark in "${benchmarks[@]}"; do
  "$repo_root/scripts/run-spp-direct.sh" \
    "$benchmark" \
    --start "$start" \
    --limit "$limit" \
    --request-timeout "$request_timeout" \
    --transport-attempts "$transport_attempts" \
    --output "$output_root/$benchmark"
done

python_bin="$repo_root/.venv/bin/python"
if [[ ! -x "$python_bin" ]]; then
  python_bin="$(command -v python3)"
fi
summary_paths=()
for benchmark in "${benchmarks[@]}"; do
  summary_paths+=("$output_root/$benchmark/summary.json")
done
PYTHONPATH="$repo_root/src" "$python_bin" -m mia_exp.cli aggregate \
  "${summary_paths[@]}" >"$output_root/suite-summary.json"
cat "$output_root/suite-summary.json"
