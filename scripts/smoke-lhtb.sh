#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"

# Docker Desktop keeps credential helpers next to its bundled CLI. The Docker
# binary may be globally linked without linking those helpers into PATH.
docker_desktop_bin="/Applications/Docker.app/Contents/Resources/bin"
if [[ -d "$docker_desktop_bin" ]]; then
  export PATH="$docker_desktop_bin:$PATH"
fi

# LHTB's smoke images are public. Use an isolated client config so a stale or
# unavailable desktop credential helper cannot block anonymous image pulls.
if [[ -n "${MIA_DOCKER_CONFIG:-}" ]]; then
  export DOCKER_CONFIG="$MIA_DOCKER_CONFIG"
else
  export DOCKER_CONFIG="$repo_root/artifacts/docker-anonymous"
  mkdir -p "$DOCKER_CONFIG"
  cp \
    "$repo_root/experiments/lhtb/docker-public-config/config.json" \
    "$DOCKER_CONFIG/config.json"
fi

if ! docker info >/dev/null 2>&1; then
  echo "error: Docker daemon is not running" >&2
  exit 1
fi
if [[ ! -x .venv/bin/harbor ]]; then
  echo "error: Harbor is not installed; run make bootstrap" >&2
  exit 1
fi

export DOCKER_DEFAULT_PLATFORM="${DOCKER_DEFAULT_PLATFORM:-linux/amd64}"
cd benchmarks/LHTB
"$repo_root/.venv/bin/harbor" run -c configs/examples/oracle_smoke.yaml
