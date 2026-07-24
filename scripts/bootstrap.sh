#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"

git submodule sync --recursive
git submodule update --init core/Roy
git submodule update --init --depth 1 benchmarks/LHTB
git submodule update --init benchmarks/SPP

if ! command -v git-lfs >/dev/null 2>&1 && ! git lfs version >/dev/null 2>&1; then
  echo "error: Git LFS is required. Install it before bootstrapping LHTB." >&2
  exit 1
fi
git lfs install --local
git -C benchmarks/LHTB lfs install --local
if [[ "${MIA_SKIP_LHTB_LFS:-0}" != "1" ]]; then
  git -C benchmarks/LHTB lfs pull
fi

npm --prefix core/Roy ci
"$repo_root/scripts/build-roy-bundle.sh"
"$repo_root/scripts/cache-node-runtime.sh"

if [[ ! -d .venv ]]; then
  uv venv --python 3.12 .venv
fi
export UV_HTTP_TIMEOUT="${UV_HTTP_TIMEOUT:-300}"
export UV_HTTP_RETRIES="${UV_HTTP_RETRIES:-10}"
# Harbor's current LiteLLM resolution builds through maturin but omits these
# build requirements from its source distribution metadata.
uv pip install \
  --python .venv/bin/python \
  "uv-build>=0.8.4,<0.9.0" \
  maturin \
  puccinialin
uv pip install \
  --python .venv/bin/python \
  --no-build-isolation \
  -e benchmarks/LHTB/harbor
uv pip install --python .venv/bin/python -e .

"$repo_root/scripts/prepare-spp.sh"

echo "Bootstrap complete. Run: make doctor && make check"
