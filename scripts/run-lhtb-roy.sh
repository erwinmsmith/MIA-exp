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

docker_desktop_bin="/Applications/Docker.app/Contents/Resources/bin"
if [[ -d "$docker_desktop_bin" ]]; then
  export PATH="$docker_desktop_bin:$PATH"
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

if [[ -n "${LHTB_ROY_BUNDLE:-}" ]]; then
  if [[ ! -f "$LHTB_ROY_BUNDLE" ]]; then
    echo "error: configured Roy bundle does not exist: $LHTB_ROY_BUNDLE" >&2
    exit 1
  fi
  export MIA_ROY_BUNDLE="$LHTB_ROY_BUNDLE"
else
  "$repo_root/scripts/ensure-roy-bundle.sh"
fi

if [[ -z "${OPENAI_API_KEY:-}${ANTHROPIC_API_KEY:-}${DEEPSEEK_API_KEY:-}" ]]; then
  echo "error: set a supported Roy model credential before a live LHTB run" >&2
  exit 1
fi

if ! docker info >/dev/null 2>&1; then
  echo "error: Docker daemon is not running" >&2
  exit 1
fi

IFS=',' read -r -a lhtb_tasks <<< "${LHTB_ROY_TASKS:-langchain-version-migration}"
"$repo_root/scripts/prepare-lhtb-images.sh" "${lhtb_tasks[@]}"

roy_config="${LHTB_ROY_CONFIG:-$repo_root/experiments/lhtb/configs/roy_smoke.yaml}"
if [[ ! -f "$roy_config" ]]; then
  echo "error: Roy LHTB config does not exist: $roy_config" >&2
  exit 1
fi

exec "$repo_root/.venv/bin/harbor" run \
  -c "$roy_config" \
  "$@"
