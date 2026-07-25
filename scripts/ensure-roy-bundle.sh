#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
output_path="${1:-$repo_root/artifacts/roy-run.mjs}"
stamp_path="${output_path}.commit"
roy_commit="$(git -C "$repo_root/core/Roy" rev-parse HEAD)"
roy_changes="$(git -C "$repo_root/core/Roy" status --porcelain --untracked-files=all -- \
  src \
  package.json \
  package-lock.json \
  tsconfig.json \
  eslint.config.js)"
built_commit=""
if [[ -f "$stamp_path" ]]; then
  IFS= read -r built_commit <"$stamp_path" || true
fi

if [[ -f "$output_path" && -z "$roy_changes" && "$built_commit" == "$roy_commit" ]]; then
  exit 0
fi

if [[ -n "$roy_changes" ]]; then
  echo "Roy source has uncommitted changes; rebuilding bundle from the working tree." >&2
elif [[ -f "$output_path" ]]; then
  echo "Roy bundle is stale (${built_commit:-unknown} != $roy_commit); rebuilding." >&2
else
  echo "Roy bundle is missing; building it for $roy_commit." >&2
fi
"$repo_root/scripts/build-roy-bundle.sh" "$output_path"
