#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"

if [[ -f "$repo_root/.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "$repo_root/.env"
  set +a
fi

if [[ -n "${MIA_DOCKER_CONFIG:-}" ]]; then
  export DOCKER_CONFIG="$MIA_DOCKER_CONFIG"
else
  export DOCKER_CONFIG="$repo_root/artifacts/docker-anonymous"
  mkdir -p "$DOCKER_CONFIG"
  cp \
    "$repo_root/experiments/lhtb/docker-public-config/config.json" \
    "$DOCKER_CONFIG/config.json"
fi
export DOCKER_DEFAULT_PLATFORM="${DOCKER_DEFAULT_PLATFORM:-linux/amd64}"

if [[ -z "${OPENAI_API_KEY:-}${DEEPSEEK_API_KEY:-}" ]]; then
  echo "error: set an OpenAI-compatible model credential before a direct LHTB run" >&2
  exit 1
fi
if ! docker info >/dev/null 2>&1; then
  echo "error: Docker daemon is not running" >&2
  exit 1
fi

direct_config="${LHTB_DIRECT_CONFIG:-$repo_root/experiments/lhtb/configs/direct_development.yaml}"
if [[ ! -f "$direct_config" ]]; then
  echo "error: direct LHTB config does not exist: $direct_config" >&2
  exit 1
fi

lhtb_tasks=()
if [[ -n "${LHTB_DIRECT_TASKS:-}" ]]; then
  IFS=',' read -r -a lhtb_tasks <<< "$LHTB_DIRECT_TASKS"
else
  while IFS= read -r task_name; do
    lhtb_tasks+=("$task_name")
  done < <(
    "$repo_root/.venv/bin/python" - "$direct_config" <<'PY'
import sys
from pathlib import Path

import yaml

config = yaml.safe_load(Path(sys.argv[1]).read_text(encoding="utf-8")) or {}
seen = set()
for dataset in config.get("datasets", []):
    for task_name in dataset.get("task_names", []) or []:
        if task_name not in seen:
            print(task_name)
            seen.add(task_name)
PY
  )
fi
if (( ${#lhtb_tasks[@]} == 0 )); then
  echo "error: no LHTB task names found in $direct_config" >&2
  exit 1
fi
"$repo_root/scripts/prepare-lhtb-images.sh" "${lhtb_tasks[@]}"

exec "$repo_root/.venv/bin/harbor" run \
  -c "$direct_config" \
  "$@"
