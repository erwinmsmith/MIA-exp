#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root/core/Roy"

npm test
npm run check
npm run build
node dist/cli/Run.js --help
