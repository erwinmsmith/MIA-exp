# MIA-exp

MIA-exp is a public experiment harness for automatically derived subagents. It
organizes reproducible experiments across multiple benchmarks and evaluates
[Roy](https://github.com/erwinmsmith/Roy) capabilities such as delegation, tool
execution, derivation trees, and trajectories.

Supported benchmark suites:

- [LHTB](https://github.com/zli12321/LHTB) for long-horizon terminal work;
- [Solo Performance Prompting](https://github.com/MikeWangWZHL/Solo-Performance-Prompting)
  for Logic Grid Puzzle, Trivia Creative Writing (N=5/N=10), and Codenames
  Collaborative.

## Repository boundaries

```text
MIA-exp/                 # Experiments, adapters, configs, and result processing
├── core/Roy/            # Independent submodule; benchmark-agnostic runtime only
├── benchmarks/LHTB/     # Independent upstream benchmark submodule; read-only
├── benchmarks/SPP/      # Independent upstream datasets submodule; read-only
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

Prerequisites: Git, Node.js 20+, Python 3.11+, `uv`, Git LFS, Docker Compose v2,
and a running Docker daemon.

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

The SPP upstream repository does not currently declare a software/data license.
MIA-exp therefore pins it as a read-only submodule instead of copying its datasets
into this repository. `make prepare-spp` downloads the pinned data and verifies the
expected item counts and SHA-256 digests.

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
make prepare-spp         # Download and checksum the four SPP data splits
make smoke-spp           # Validate data, adapters, prompts, and metrics offline
make check               # Run local checks that do not consume model tokens
make run-lhtb-roy        # Run one live Roy/LHTB task with local credentials
make run-spp-roy ARGS=... # See experiments/spp/README.md for direct commands
```

## Experiments

Each benchmark adapter lives under `experiments/<benchmark>/`. See
[`experiments/lhtb/README.md`](experiments/lhtb/README.md) and
[`experiments/spp/README.md`](experiments/spp/README.md) for their workflows.

The LHTB adapter builds Roy as a standalone JavaScript bundle, caches a
checksum-verified Linux x64 Node.js runtime, and uploads both into the isolated task
container. Neither the host nor benchmark image needs Roy preinstalled.

Every reported result should record:

- MIA-exp, Roy, and benchmark commit SHAs;
- model/provider and non-sensitive configuration;
- raw Harbor job output;
- Roy execution tree, events, messages, and trajectory;
- verifier reward rather than the agent's self-reported completion status.
- threshold-aware `pass@1`, `pass@5`, and any configured `pass@k`.

## Common score contract

Every adapter exposes an item-level score as `earned / possible` in `[0, 1]` and
retains both numeric values. Runs also report `score`, `meanItemScore`,
`exactMatchRate`, and `parseRate`. The native metric remains visible:

| Benchmark | Earned | Possible |
| --- | --- | --- |
| LHTB | Harbor verifier reward | 1 |
| Logic Grid Puzzle | Correct house answers | Puzzles |
| Trivia Creative Writing | Official answer aliases mentioned | Trivia questions |
| Codenames Collaborative | Unique target words guessed | Target words |

Cross-benchmark comparisons use a macro mean of each benchmark's normalized score,
so a larger dataset or a Trivia N=10 item cannot silently dominate another
benchmark. Raw item records remain authoritative.

Repeated trials use the standard unbiased pass@k estimator per task and then macro
average across tasks. LHTB counts a trial as passing when the official Harbor
verifier reward is at least `0.95`. A missing `pass@k` value means the run did not
contain at least `k` attempts for every task; it is never treated as zero or one.
