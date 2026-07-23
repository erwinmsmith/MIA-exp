#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"
require_clean="${1:-}"

show_repo() {
  local label="$1"
  local path="$2"
  printf '\n[%s] %s\n' "$label" "$path"
  git -C "$path" status -sb
  git -C "$path" remote -v | sed -n '1,2p'
}

show_repo "experiment" .
show_repo "core" core/Roy
show_repo "benchmark" benchmarks/LHTB

if [[ "$require_clean" == "--require-clean-submodules" ]]; then
  for path in core/Roy benchmarks/LHTB; do
    if [[ -n "$(git -C "$path" status --porcelain)" ]]; then
      echo "error: dirty nested repository: $path" >&2
      exit 1
    fi
  done
fi
