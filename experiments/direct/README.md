# Direct single-model baseline

This baseline runs the configured model directly on the same SPP tasks, dataset
commit, sample indices, temperature, and common metrics used by Roy and the
EvoAgent reproduction.

- Logic Grid and each Trivia item use one model call.
- Codenames uses one Spymaster call followed by one Guesser call because the
  benchmark intrinsically requires the hidden-information handoff.
- There is no expert generation, quality selection, delegation, feedback,
  refinement, memory, or result integration.

The initial task prompts follow the published EvoAgent SPP entrypoints so the
direct and EvoAgent variants differ only by the evolution stages.

Run the 10 × 4 baseline:

```bash
./scripts/run-direct-suite.sh \
  --start 0 \
  --limit 10 \
  --output-root results/direct/deepseek-v4-flash-10x4
```

Provider credentials and `DEFAULT_MODEL` are read from the ignored `.env`.
Every raw model call, response, score, duration, and reported token count is
retained below the selected output root.
