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

if ! docker info >/dev/null 2>&1; then
  echo "error: Docker daemon is not running" >&2
  exit 1
fi
test -f artifacts/roy-run.mjs
test -f artifacts/node-v20.20.2-linux-x64.tar.gz

docker run \
  --rm \
  --platform linux/amd64 \
  --volume "$repo_root/artifacts:/artifacts:ro" \
  debian:bookworm-slim \
  sh -ceu '
    mkdir -p /opt/node
    tar -xzf /artifacts/node-v20.20.2-linux-x64.tar.gz \
      -C /opt/node \
      --strip-components=1
    /opt/node/bin/node /artifacts/roy-run.mjs --help >/tmp/roy-help 2>&1
    grep -q "Run one Roy task non-interactively" /tmp/roy-help
    /opt/node/bin/node --version
  '

echo "Roy Linux container smoke passed."
