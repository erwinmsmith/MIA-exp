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
LHTB Harbor patch without spending model tokens. It fails if Harbor reports any
exception, cancelled or pending trial, missing trial result, fewer than three
tasks, or an oracle reward below `0.95`; Harbor's process exit code alone is not
considered a successful smoke.

Image preparation reads each task's declared `environment.docker_image`, pulls the
official `linux/amd64` image, requires a registry digest, and probes `/app` and
the image's `python` or `python3` interpreter. Images that declare a different
working directory are probed at that directory instead of assuming `/app`. It
rejects locally reconstructed images without a registry digest. The
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

Run the original three-task engineering set sequentially with the multi-task config:

```bash
LHTB_ROY_CONFIG="$PWD/experiments/lhtb/configs/roy_multi.yaml" \
LHTB_ROY_TASKS="langchain-version-migration,great-expectations-audit,document-table-layout-reconstruction" \
make run-lhtb-roy
```

Run the same tasks with the selected model in Harbor's standard single-agent
terminal loop. This is the direct-model control: it uses the same task images,
official verifier, timeout multiplier, and result layout, but does not use Roy's
team derivation or memory runtime.

```bash
LHTB_DIRECT_TASKS="langchain-version-migration,great-expectations-audit,document-table-layout-reconstruction" \
make run-lhtb-direct
```

`DirectLHTBAgent` reads `DEFAULT_MODEL` and the provider base URL from the
environment. The committed development config pins `deepseek-v4-flash` so the
Roy and direct runs can use the same model.

The pinned LHTB revision contains 46 tasks. `roy_all_development.yaml` is the
complete task manifest, while `roy_broad_pass5.yaml` is a deterministic
cross-domain sample of 10 tasks with five attempts each. Both use sequential
execution because individual LHTB containers can be resource intensive:

```bash
LHTB_ROY_CONFIG="$PWD/experiments/lhtb/configs/roy_broad_pass5.yaml" \
./scripts/run-lhtb-roy.sh --yes
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

`LHTB_ROY_CONFIG` selects the Harbor config. By default, the launcher derives the
image-preparation set from that config's `datasets[].task_names`; set
`LHTB_ROY_TASKS` only to override it explicitly. Raw jobs remain ignored; publish
only deliberately summarized, secret-free results.

Normalize any completed Harbor job and calculate threshold-aware sampling metrics:

```bash
mia-bench harbor-summary jobs/<job> \
  --threshold 0.95 \
  --k 1 \
  --k 5 \
  --output jobs/<job>/mia-summary.json
```

`pass@1` and `pass@5` are standard unbiased estimators computed per task and
macro-averaged. The summary also records the observed first-k outcome for every
task, raw rewards, exceptions, tokens, cost, and whether every selected LHTB task
reached reward `>= 0.95`. A requested k is explicitly `null` when any task has
fewer than k attempts. The long-term target is all 46 pinned tasks reaching the
threshold. The broad sample records five attempts per selected task so `pass@1`,
`pass@5`, and observed per-attempt outcomes can be reported without claiming a
full-suite result.

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
inside the same Roy phase. The complete readable verifier bundle is mirrored
under `.roy/official-verifier/`, including fixtures and helper files, allowing
Roy's workspace-scoped filesystem tools to inspect and execute the assertions
that are already available to terminal-based agents. If Harbor has removed its
temporary `/tests` mount for a continuation, the adapter links `/tests` to that
read-only mirror so absolute fixture paths still resolve. From the second round
onward, the adapter uploads the same checked-out verifier bundle, avoiding
dependence on Harbor's later `/tests` injection timing.

The concrete Harbor config and adapter remain in this outer repository.
