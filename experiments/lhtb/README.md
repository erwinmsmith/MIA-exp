# Roy on LHTB

This directory owns the Roy-to-Harbor adapter and LHTB experiment configs. The
upstream task definitions and modified Harbor runtime remain in
`benchmarks/LHTB`.

## Readiness checks

```bash
make bootstrap
make doctor
make prepare-lhtb-images
make smoke-roy-container
make smoke-lhtb
```

The oracle smoke proves Docker image build, task setup, verifier execution, and the
LHTB Harbor patch without spending model tokens.

Image preparation reads each task's declared `environment.docker_image`, pulls the
official `linux/amd64` image, requires a registry digest, and probes `/app` and
Python. It rejects locally reconstructed images without a registry digest. The
scripts use an isolated anonymous Docker client config so a stale desktop credential
helper cannot block pulls. Set
`MIA_DOCKER_CONFIG=/path/to/config` to use a different Docker client config.
Trial cleanup removes containers, volumes, and orphaned resources but retains
these pulled benchmark images, avoiding a repeated multi-hundred-megabyte pull
between repair probes.

## Roy agent run

Roy runs non-interactively through its `roy-run` CLI. The Harbor adapter launches it
inside the task environment, enables the explicitly configured benchmark terminal
policy, and stores the returned JSON result plus `.roy` execution trees and traces
with the Harbor job artifacts.

Provider credentials must be passed through the environment. Do not place API keys
in YAML.

The adapter is `mia_exp.benchmarks.lhtb:RoyLHTBAgent`. Bootstrap builds Roy into a
single JavaScript artifact and caches a checksum-verified Linux x64 Node runtime;
the adapter uploads both into each task container. Roy itself remains benchmark
agnostic.

Run the one-task sample after selecting the model in
`configs/roy_smoke.yaml`:

```bash
export OPENAI_API_KEY=...
make run-lhtb-roy
```

Run all currently checked-out LHTB tasks sequentially with the multi-task config:

```bash
LHTB_ROY_CONFIG="$PWD/experiments/lhtb/configs/roy_multi.yaml" \
LHTB_ROY_TASKS="langchain-version-migration,great-expectations-audit,document-table-layout-reconstruction" \
make run-lhtb-roy
```

For completion-oriented local debugging, use the development config. It keeps the
official task and verifier unchanged but gives Roy a multi-hour process envelope,
uses the benchmark-agnostic development workspace policy, and does not replace that
policy with Harbor's per-continuation countdown:

```bash
LHTB_ROY_CONFIG="$PWD/experiments/lhtb/configs/roy_development.yaml" \
LHTB_ROY_TASKS="langchain-version-migration,great-expectations-audit,document-table-layout-reconstruction" \
make run-lhtb-roy
```

Use `roy_multi.yaml` for comparable official-time results. The development config
is for exposing and closing implementation defects; its longer envelope is not
reported as an official benchmark result.

`LHTB_ROY_CONFIG` selects the Harbor config and `LHTB_ROY_TASKS` is the
comma-separated image-preparation set. Raw jobs remain ignored; publish only
deliberately summarized, secret-free results.

To compare Roy revisions without replacing the default bundle used by another
running benchmark, build and select a versioned artifact:

```bash
./scripts/build-roy-bundle.sh "$PWD/artifacts/roy-run-a650eee.mjs"
LHTB_ROY_BUNDLE="$PWD/artifacts/roy-run-a650eee.mjs" \
LHTB_ROY_CONFIG="$PWD/experiments/lhtb/configs/roy_multi.yaml" \
LHTB_ROY_TASKS="langchain-version-migration,great-expectations-audit,document-table-layout-reconstruction" \
./scripts/run-lhtb-roy.sh --n-concurrent 3 --yes
```

Summarized probe reports live under [`reports/`](reports/). They distinguish
runtime diagnostics from benchmark passes and do not publish raw traces or
credentials.

Artifacts are written below `jobs/<job>/<trial>/agent/`:

- `roy-run-<round>.json`: result, execution tree, events, messages, and usage;
- `roy-state-<round>/`: persisted memory, full traces, execution trees, and
  execution knowledge (step/path/agent/team/feedback) caches;
- `instruction-<round>.txt`: exact instruction supplied to Roy.

Continuation rounds carry only changed official verifier artifacts. Identical
artifacts are represented by a content fingerprint and reuse Roy's persisted
execution ledger. Roy links the new execution path to the previous open path and
continues modification, verification, and acceptance work without rebuilding the
initial team. Once Harbor has mounted `/tests`, the adapter also supplies the
task's actual local verifier entrypoint so repair and re-verification can close
inside the same Roy phase. The readable verifier entrypoint is mirrored under
`.roy/official-verifier/`, allowing Roy's workspace-scoped filesystem tools to
inspect the assertions that are already available to terminal-based agents.
From the second round onward, the adapter uploads the same read-only verifier
source from the checked-out LHTB task, avoiding dependence on Harbor's later
`/tests` injection timing.

The concrete Harbor config and adapter remain in this outer repository.
