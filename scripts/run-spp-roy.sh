#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"

if [[ -n "${MIA_ROY_BUNDLE:-}" ]]; then
  if [[ ! -f "$MIA_ROY_BUNDLE" ]]; then
    echo "error: configured Roy bundle does not exist: $MIA_ROY_BUNDLE" >&2
    exit 1
  fi
else
  "$repo_root/scripts/ensure-roy-bundle.sh"
fi

python_bin="$repo_root/.venv/bin/python"
if [[ ! -x "$python_bin" ]]; then
  python_bin="$(command -v python3)"
fi

PYTHONPATH="$repo_root/src" "$python_bin" -m mia_exp.cli run "$@"
