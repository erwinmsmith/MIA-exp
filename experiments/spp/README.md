# Solo Performance Prompting benchmarks

This adapter runs Roy on the official datasets released with
[Solo Performance Prompting](https://github.com/MikeWangWZHL/Solo-Performance-Prompting):

| Registry ID | Items | Native score |
| --- | ---: | --- |
| `spp.logic-grid-puzzle` | 200 | Correct house number / 1 |
| `spp.trivia-creative-writing-n5` | 100 | Mentioned answer aliases / 5 |
| `spp.trivia-creative-writing-n10` | 100 | Mentioned answer aliases / 10 |
| `spp.codenames-collaborative` | 50 | Target words guessed / target words |

The upstream repository has no declared license as of the pinned commit. It is
kept as a read-only submodule; MIA-exp contains only adapters, configuration,
integrity metadata, and ignored local results.

## Prepare and validate

```bash
make prepare-spp
make smoke-spp
PYTHONPATH=src .venv/bin/python -m mia_exp.cli list --suite spp
```

`prepare-spp` checks all four official files against the item counts and SHA-256
digests recorded in `experiments/benchmarks.json`.

## Inspect prompts and score saved responses

```bash
PYTHONPATH=src .venv/bin/python -m mia_exp.cli render \
  spp.logic-grid-puzzle --index 0

PYTHONPATH=src .venv/bin/python -m mia_exp.cli score \
  spp.logic-grid-puzzle --index 0 --response-file /path/to/response.txt
```

## Run Roy

Run one item first:

```bash
./scripts/run-spp-roy.sh spp.logic-grid-puzzle \
  --start 0 --limit 1 --timeout 1200
```

Then expand the same command to a complete split by changing `--limit`. A unique
ignored directory is created under `results/spp/<benchmark>/<timestamp>/` unless
`--output` is supplied.

SPP runs leave Roy's token market unlimited by default. This preserves complete
reasoning, synthesis, continuation, and acceptance-repair cycles while still
recording actual provider usage. Pass `--budget N` only for an intentional
budget-ablation experiment; the selected mode and value are recorded in
`run.json`.

An output directory that already contains `run.json` or `items.jsonl` is rejected
to prevent records from separate runs or commits being mixed accidentally.

Each run retains:

- `run.json`: commits, model/provider identity, selection, and run limits;
- `items.jsonl`: common scores, parse status, failures, and artifact references;
- `summary.json`: normalized score, mean item score, exact-match rate, and parse
  rate;
- `raw/<index>/`: Roy prompts, complete JSON artifacts, stdout/stderr, `.roy`
  execution trees, caches, memory, and traces.

The Codenames adapter uses two isolated Roy sessions. The Spymaster sees target
words and emits one hint. A fresh Guesser workspace receives only that hint and
the board. This preserves the original collaboration boundary and prevents target
leakage through Roy memory or execution cache.

The workspace policy enables automatic recursive delegation, formal teams, ToM,
feedback traces, and persistent execution caches. Filesystem, shell, and mutation
tools remain denied because third-party dataset text is treated as untrusted input.
Trivia tasks may use Roy's public-network-safe `web.search` and `web.fetch` tools;
only those two read-only tools are auto-approved. This lets factual answers be
grounded before story synthesis without exposing the host workspace or shell.

## Result interpretation

The adapter preserves the paper's automatic semantics:

- Logic Grid requires a machine-readable final house number.
- Trivia uses case-insensitive substring matching against every official TriviaQA
  alias, matching the upstream evaluator.
- Codenames uses target-word recall, matching the upstream evaluator. Distractor
  guesses are recorded but do not change the paper-comparable primary score.

Use normalized benchmark scores for comparisons. For a suite-level number, average
the four benchmark summary scores rather than pooling their raw denominators.

```bash
PYTHONPATH=src .venv/bin/python -m mia_exp.cli aggregate \
  results/spp/*/*/summary.json
```
