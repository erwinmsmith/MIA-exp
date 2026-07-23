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

if [[ -z "${OPENAI_API_KEY:-}${ANTHROPIC_API_KEY:-}${DEEPSEEK_API_KEY:-}" ]]; then
  echo "error: set a supported Roy model credential before a live LHTB run" >&2
  exit 1
fi

if ! docker info >/dev/null 2>&1; then
  echo "error: Docker daemon is not running" >&2
  exit 1
fi

lhtb_image="${LHTB_ROY_IMAGE:-zli12321/lhtb-langchain-version-migration:20260615}"
if ! docker image inspect "$lhtb_image" >/dev/null 2>&1; then
  pull_attempts="${LHTB_PULL_ATTEMPTS:-10}"
  if [[ ! "$pull_attempts" =~ ^[1-9][0-9]*$ ]]; then
    echo "error: LHTB_PULL_ATTEMPTS must be a positive integer" >&2
    exit 1
  fi
  image_ready=0
  for ((attempt = 1; attempt <= pull_attempts; attempt += 1)); do
    if docker pull --platform "$DOCKER_DEFAULT_PLATFORM" "$lhtb_image"; then
      image_ready=1
      break
    fi
    echo "warning: image pull attempt $attempt/$pull_attempts failed for $lhtb_image" >&2
  done
  if [[ "$image_ready" != "1" ]]; then
    echo "error: could not pull $lhtb_image after $pull_attempts attempts" >&2
    exit 1
  fi
fi

exec "$repo_root/.venv/bin/harbor" run \
  -c "$repo_root/experiments/lhtb/configs/roy_smoke.yaml" \
  "$@"
