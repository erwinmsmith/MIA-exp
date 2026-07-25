#!/usr/bin/env bash
set -uo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"
failures=0

if [[ -f "$repo_root/.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "$repo_root/.env"
  set +a
fi

ok() { printf 'ok   %s\n' "$1"; }
warn() { printf 'warn %s\n' "$1"; }
fail() { printf 'fail %s\n' "$1"; failures=$((failures + 1)); }

if git rev-parse --is-inside-work-tree >/dev/null 2>&1; then ok "MIA-exp Git repository"; else fail "MIA-exp is not a Git repository"; fi
if git -C core/Roy rev-parse --is-inside-work-tree >/dev/null 2>&1; then ok "Roy submodule"; else fail "Roy submodule is missing"; fi
if git -C benchmarks/LHTB rev-parse --is-inside-work-tree >/dev/null 2>&1; then ok "LHTB submodule"; else fail "LHTB submodule is missing"; fi
if git -C benchmarks/SPP rev-parse --is-inside-work-tree >/dev/null 2>&1; then ok "SPP submodule"; else fail "SPP submodule is missing"; fi

for command_name in node npm uv python3 docker; do
  if command -v "$command_name" >/dev/null 2>&1; then ok "$command_name available"; else fail "$command_name unavailable"; fi
done
if git lfs version >/dev/null 2>&1; then ok "Git LFS available"; else fail "Git LFS unavailable"; fi

node_major="$(node -p 'Number(process.versions.node.split(".")[0])' 2>/dev/null || printf 0)"
if (( node_major >= 20 )); then ok "Node.js >= 20"; else fail "Node.js 20+ required"; fi

if docker info >/dev/null 2>&1; then
  ok "Docker daemon running"
else
  fail "Docker daemon is not running"
fi
if docker compose version >/dev/null 2>&1; then
  ok "Docker Compose v2 available"
else
  fail "Docker Compose v2 is unavailable"
fi

if [[ -x .venv/bin/harbor ]]; then ok "LHTB Harbor installed in .venv"; else fail "Harbor missing; run make bootstrap"; fi
if [[ -d core/Roy/node_modules ]]; then ok "Roy dependencies installed"; else fail "Roy dependencies missing; run make bootstrap"; fi
roy_commit="$(git -C core/Roy rev-parse HEAD 2>/dev/null || true)"
roy_changes="$(git -C core/Roy status --porcelain --untracked-files=all -- \
  src \
  package.json \
  package-lock.json \
  tsconfig.json \
  eslint.config.js 2>/dev/null || true)"
bundle_commit=""
if [[ -f artifacts/roy-run.mjs.commit ]]; then
  IFS= read -r bundle_commit <artifacts/roy-run.mjs.commit || true
fi
if [[ -f artifacts/roy-run.mjs && -z "$roy_changes" && "$bundle_commit" == "$roy_commit" ]]; then
  ok "Roy container bundle matches core commit"
elif [[ -n "$roy_changes" ]]; then
  fail "Roy source has uncommitted changes; rebuild before running experiments"
elif [[ -f artifacts/roy-run.mjs ]]; then
  fail "Roy bundle is stale; run make bundle"
else
  fail "Roy bundle missing; run make bundle"
fi
if [[ -f artifacts/node-v20.20.2-linux-x64.tar.gz ]]; then ok "Linux Node runtime cached"; else fail "Node runtime missing; run make bootstrap"; fi
if PYTHONPATH=src .venv/bin/python -m mia_exp.cli validate --suite spp >/dev/null 2>&1; then ok "SPP datasets verified"; else fail "SPP datasets missing or corrupt; run make prepare-spp"; fi

if [[ -n "${OPENAI_API_KEY:-}${ANTHROPIC_API_KEY:-}${DEEPSEEK_API_KEY:-}" ]]; then
  ok "Roy model credential present"
else
  warn "no Roy model credential; offline/oracle smoke works, live Roy tasks do not"
fi

if (( failures > 0 )); then
  printf '\nDoctor found %d blocking issue(s).\n' "$failures" >&2
  exit 1
fi
printf '\nEnvironment is ready.\n'
