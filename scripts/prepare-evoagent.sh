#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"

git submodule sync -- baselines/EvoAgent
git submodule update --init baselines/EvoAgent

expected_commit="fc6d087b119df69466c2372cfcaf588c040aaba8"
actual_commit="$(git -C baselines/EvoAgent rev-parse HEAD)"
if [[ "$actual_commit" != "$expected_commit" ]]; then
  echo "error: EvoAgent is at $actual_commit, expected $expected_commit" >&2
  exit 1
fi

echo "EvoAgent ready at $actual_commit"
