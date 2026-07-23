#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
node_version="20.20.2"
archive="node-v${node_version}-linux-x64.tar.gz"
target="$repo_root/artifacts/$archive"
checksums="$repo_root/artifacts/node-v${node_version}-SHASUMS256.txt"
base_url="https://nodejs.org/dist/v${node_version}"

mkdir -p "$repo_root/artifacts"
if [[ ! -f "$checksums" ]]; then
  curl --fail --location --retry 3 --output "$checksums" "$base_url/SHASUMS256.txt"
fi

expected="$(awk -v file="$archive" '$2 == file { print $1 }' "$checksums")"
if [[ -z "$expected" ]]; then
  echo "error: checksum for $archive not found" >&2
  exit 1
fi
if [[ -f "$target" ]]; then
  actual="$(shasum -a 256 "$target" | awk '{ print $1 }')"
  if [[ "$actual" == "$expected" ]]; then
    echo "Cached verified Node runtime: $target"
    exit 0
  fi
else
  : > "$target"
fi
curl \
  --fail \
  --location \
  --retry 5 \
  --retry-all-errors \
  --connect-timeout 15 \
  --speed-limit 1024 \
  --speed-time 30 \
  --continue-at - \
  --output "$target" \
  "$base_url/$archive"
actual="$(shasum -a 256 "$target" | awk '{ print $1 }')"
if [[ "$actual" != "$expected" ]]; then
  echo "error: checksum mismatch for $target" >&2
  exit 1
fi
echo "Cached verified Node runtime: $target"
