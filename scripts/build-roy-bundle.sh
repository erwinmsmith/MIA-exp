#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
esbuild="$repo_root/core/Roy/node_modules/.bin/esbuild"
output_path="${1:-$repo_root/artifacts/roy-run.mjs}"
if [[ ! -x "$esbuild" ]]; then
  echo "error: esbuild missing; install Roy dependencies first" >&2
  exit 1
fi

mkdir -p "$(dirname "$output_path")"
"$esbuild" "$repo_root/core/Roy/src/cli/Run.ts" \
  --bundle \
  --platform=node \
  --format=esm \
  --target=node20 \
  --banner:js="import { createRequire as __miaCreateRequire } from 'node:module'; const require = __miaCreateRequire(import.meta.url);" \
  --outfile="$output_path"
