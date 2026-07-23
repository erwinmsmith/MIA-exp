# Roy on LHTB

This directory owns the Roy-to-Harbor adapter and LHTB experiment configs. The
upstream task definitions and modified Harbor runtime remain in
`benchmarks/LHTB`.

## Readiness checks

```bash
make bootstrap
make doctor
make smoke-lhtb
```

The oracle smoke proves Docker image build, task setup, verifier execution, and the
LHTB Harbor patch without spending model tokens.

For public smoke images, the script uses an isolated anonymous Docker client
config so a stale desktop credential helper cannot block pulls. Set
`MIA_DOCKER_CONFIG=/path/to/config` to use a different Docker client config.

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
export DOCKER_DEFAULT_PLATFORM=linux/amd64
.venv/bin/harbor run -c experiments/lhtb/configs/roy_smoke.yaml
```

Artifacts are written below `jobs/<job>/<trial>/agent/`:

- `roy-run-<round>.json`: result, execution tree, events, messages, and usage;
- `roy-state-<round>/`: persisted memory, full traces, execution trees, and caches;
- `instruction-<round>.txt`: exact instruction supplied to Roy.

The concrete Harbor config and adapter remain in this outer repository.
