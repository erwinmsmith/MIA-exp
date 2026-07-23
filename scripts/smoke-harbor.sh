#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"

if [[ ! -x .venv/bin/harbor ]]; then
  echo "error: Harbor is not installed; run make bootstrap" >&2
  exit 1
fi

.venv/bin/harbor --help >/dev/null
.venv/bin/python -c 'import harbor'
.venv/bin/python -c 'from mia_exp.benchmarks.lhtb import RoyLHTBAgent; assert RoyLHTBAgent.name() == "roy-lhtb"'
test -f benchmarks/LHTB/configs/examples/oracle_smoke.yaml
test -f artifacts/roy-run.mjs
test -f artifacts/node-v20.20.2-linux-x64.tar.gz
echo "Harbor and LHTB configuration smoke passed."
