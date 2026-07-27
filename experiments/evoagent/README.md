# EvoAgent reproduction

This experiment reproduces the official EvoAgent inference method on the same
SPP tasks, model configuration, sample indices, datasets, and normalized metrics
used by the Roy evaluation.

## Provenance and boundaries

- Project: <https://evo-agent.github.io/>
- Code: <https://github.com/siyuyuan/evoagent>
- Pinned source: `baselines/EvoAgent` at
  `fc6d087b119df69466c2372cfcaf588c040aaba8`
- Benchmark data: the independently pinned `benchmarks/SPP` submodule
- Method parameters: temperature `0`, three evolved experts per role

The upstream code is read-only and has no declared repository license. Do not
copy, edit, commit, or redistribute its contents outside the pinned submodule.
MIA-exp reads the published prompt literals directly from that checkout and
implements only the execution adapter, tracing, selection, and common metrics.

EvoAgent is an inference-time agent evolution method, not a separately trained
model checkpoint. Each role follows the published sequence:

1. generate an initial answer;
2. create an expert description;
3. quality-check the candidate and retry discarded descriptions;
4. run the accepted expert;
5. integrate the expert answer into the current result;
6. repeat steps 2–5 for three evolved experts.

Codenames runs the sequence independently for the Spymaster and Guesser. The
adapter fixes execution defects in the published scripts without modifying the
method: ignored `--start/--end` arguments, reversed message-construction
arguments, and the N=5-only writing entrypoint. This makes the registered N=10
split and deterministic sample windows runnable.

## Prepare and validate

```bash
./scripts/prepare-evoagent.sh
make smoke-evoagent
```

Credentials remain in the ignored `.env`. Provider selection and
`DEFAULT_MODEL` use the same precedence as Roy: DeepSeek, then OpenAI.

## Comparable 10 × 4 run

```bash
./scripts/run-evoagent-suite.sh \
  --start 0 \
  --limit 10 \
  --individuals 3 \
  --output-root results/evoagent/evoagent-10x4
```

The run writes:

- `run.json`: source commits, provider/model, selection, and method parameters;
- `items.jsonl`: append-safe item status, scores, artifacts, and usage;
- `raw/<index>.json`: every prompt/response, quality decision, integration
  trajectory, execution tree, final response, and token usage;
- `summary.json`: normalized benchmark result and aggregate usage;
- `suite-summary.json`: common macro-average across the four SPP tasks.

The official code retries model failures forever. The adapter uses bounded
transport retries so a provider outage becomes an explicit failed item instead
of an unending process. This changes transport behavior, not EvoAgent's
reasoning method or quality-selection loop.
