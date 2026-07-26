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

if ! docker info >/dev/null 2>&1; then
  echo "error: Docker daemon is not running" >&2
  exit 1
fi

pull_attempts="${LHTB_PULL_ATTEMPTS:-10}"
if [[ ! "$pull_attempts" =~ ^[1-9][0-9]*$ ]]; then
  echo "error: LHTB_PULL_ATTEMPTS must be a positive integer" >&2
  exit 1
fi

resolve_image() {
  local task_name="$1"
  local task_file="$repo_root/benchmarks/LHTB/tasks/$task_name/task.toml"
  if [[ ! -f "$task_file" ]]; then
    echo "error: unknown LHTB task: $task_name" >&2
    return 1
  fi
  sed -n 's/^[[:space:]]*docker_image[[:space:]]*=[[:space:]]*"\([^"]*\)".*/\1/p' "$task_file" | head -1
}

prepare_image() {
  local task_name="$1"
  local image
  image="$(resolve_image "$task_name")"
  if [[ -z "$image" ]]; then
    echo "error: task $task_name does not declare environment.docker_image" >&2
    return 1
  fi

  local image_ready=0
  if [[ "${MIA_FORCE_PULL:-0}" != "1" ]] && docker image inspect "$image" >/dev/null 2>&1; then
    image_ready=1
  fi
  if [[ "$image_ready" != "1" ]]; then
    for ((attempt = 1; attempt <= pull_attempts; attempt += 1)); do
      if docker pull --platform "$DOCKER_DEFAULT_PLATFORM" "$image"; then
        image_ready=1
        break
      fi
      echo "warning: image pull attempt $attempt/$pull_attempts failed for $image" >&2
    done
  fi
  if [[ "$image_ready" != "1" ]]; then
    echo "error: could not pull $image after $pull_attempts attempts" >&2
    return 1
  fi

  local architecture
  local operating_system
  local repo_digests
  local working_dir
  architecture="$(docker image inspect "$image" --format '{{.Architecture}}')"
  operating_system="$(docker image inspect "$image" --format '{{.Os}}')"
  repo_digests="$(docker image inspect "$image" --format '{{join .RepoDigests ","}}')"
  working_dir="$(docker image inspect "$image" --format '{{.Config.WorkingDir}}')"
  working_dir="${working_dir:-/app}"
  if [[ "$operating_system/$architecture" != "linux/amd64" ]]; then
    echo "error: $image resolved to $operating_system/$architecture, expected linux/amd64" >&2
    return 1
  fi
  if [[ -z "$repo_digests" ]]; then
    echo "error: $image has no registry digest; refuse a locally reconstructed image" >&2
    return 1
  fi

  docker run --rm --platform "$DOCKER_DEFAULT_PLATFORM" \
    --env "MIA_LHTB_PROBE_WORKDIR=$working_dir" \
    --entrypoint /bin/sh "$image" -lc \
    'set -eu
     test -d "$MIA_LHTB_PROBE_WORKDIR"
     if command -v python >/dev/null 2>&1; then
       python --version >/dev/null
     else
       command -v python3 >/dev/null
       python3 --version >/dev/null
     fi'

  printf 'ok   %s\n' "$task_name"
  printf '     image:  %s\n' "$image"
  printf '     digest: %s\n' "$repo_digests"
  printf '     target: %s/%s\n' "$operating_system" "$architecture"
  printf '     workdir: %s\n' "$working_dir"
}

if (( $# > 0 )); then
  for task_name in "$@"; do
    prepare_image "$task_name"
  done
else
  while IFS= read -r task_dir; do
    prepare_image "$(basename "$task_dir")"
  done < <(find "$repo_root/benchmarks/LHTB/tasks" -mindepth 1 -maxdepth 1 -type d | sort)
fi
