# MIA-exp

MIA-exp is a public experiment harness for automatically derived subagents. It
organizes reproducible experiments across multiple benchmarks and evaluates
[Roy](https://github.com/erwinmsmith/Roy) capabilities such as delegation, tool
execution, derivation trees, and trajectories.

The first supported benchmark is
[LHTB](https://github.com/zli12321/LHTB) (Long-Horizon Terminal-Bench).

## Repository boundaries

```text
MIA-exp/                 # Experiments, adapters, configs, and result processing
├── core/Roy/            # Independent submodule; benchmark-agnostic runtime only
├── benchmarks/LHTB/     # Independent upstream benchmark submodule; read-only
├── experiments/         # Benchmark adapters and experiment configurations
├── scripts/             # Bootstrap, validation, and launch scripts
├── artifacts/           # Ignored local build/runtime artifacts
└── results/             # Ignored raw and summarized experiment results
```

Experiments adapt benchmarks to Roy's public interface. Roy must not contain
benchmark-specific behavior. A missing reusable runtime capability is implemented,
tested, committed, and pushed in the Roy repository before MIA-exp updates its
submodule pointer.

Local agent-maintenance instructions are kept in an ignored `AGENTS.md` file and
are not part of the public repository.

## Setup

Prerequisites: Git, Node.js 20+, Python 3.11+, `uv`, Git LFS, and a running Docker
daemon.

```bash
git clone --recurse-submodules https://github.com/erwinmsmith/MIA-exp.git
cd MIA-exp
make bootstrap
make doctor
make check
```

`make bootstrap` also initializes missing submodules. LHTB assets use Git LFS by
default. To bootstrap only the code paths needed for local checks:

```bash
MIA_SKIP_LHTB_LFS=1 make bootstrap
```

## Model credentials

Copy the example file and fill in one supported provider locally:

```bash
cp .env.example .env
```

`.env` and all `.env.*` files except `.env.example` are ignored. Never commit API
keys. The guarded LHTB launcher loads the root `.env` automatically.

## Validation

```bash
make smoke-roy           # Roy tests, type checks, build, and one-shot CLI
make smoke-roy-container # Start the Roy bundle in a Linux amd64 container
make smoke-harbor        # Import Harbor and the Roy/LHTB adapter
make prepare-lhtb-images # Pull and validate official task images and digests
make smoke-lhtb          # Run LHTB's Docker oracle smoke without model tokens
make check               # Run local checks that do not consume model tokens
make run-lhtb-roy        # Run one live Roy/LHTB task with local credentials
```

## Experiments

Each benchmark adapter lives under `experiments/<benchmark>/`. See
[`experiments/lhtb/README.md`](experiments/lhtb/README.md) for the LHTB workflow.

The LHTB adapter builds Roy as a standalone JavaScript bundle, caches a
checksum-verified Linux x64 Node.js runtime, and uploads both into the isolated task
container. Neither the host nor benchmark image needs Roy preinstalled.

Every reported result should record:

- MIA-exp, Roy, and benchmark commit SHAs;
- model/provider and non-sensitive configuration;
- raw Harbor job output;
- Roy execution tree, events, messages, and trajectory;
- verifier reward rather than the agent's self-reported completion status.
