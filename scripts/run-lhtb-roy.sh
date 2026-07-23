#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"

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

if [[ -z "${OPENAI_API_KEY:-}${ANTHROPIC_API_KEY:-}${DEEPSEEK_API_KEY:-}" ]]; then
  echo "error: set a supported Roy model credential before a live LHTB run" >&2
  exit 1
fi

exec "$repo_root/.venv/bin/harbor" run \
  -c "$repo_root/experiments/lhtb/configs/roy_smoke.yaml" \
  "$@"
