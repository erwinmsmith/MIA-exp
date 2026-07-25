# Roy SPP 10-sample follow-up

## Run identity

- Host: `ali-root`
- Raw run: `/root/codespace/MIA-exp/results/validation/0a0a0ec-spp-10x4`
- MIA-exp commit recorded by the run: `c5796b88b7e793c2b3a8426c778ce21480dfdd7e`
- Roy bundle/source commit: `0a0a0ecc8090d478820751b30cf8fb34121815b6`
- SPP commit: `619c8a0ff4205bfd39e33f0867647b40e1703b94`
- Provider/model: `deepseek` / `deepseek-v4-flash`
- Selection: official indices `0..9` for each of the four registered tasks
- Per-invocation process timeout: 1,800 seconds
- Budget mode: runtime unlimited

Raw item records, model artifacts, execution trees, traces, and caches remain in
the ignored run directory. The derived `suite-summary.json`, `roy-summary.json`,
and `roy-summary.md` files are stored beside them.

## Scores

| Benchmark | Earned / possible | Normalized score | Exact matches | Parse rate | Failed items |
| --- | ---: | ---: | ---: | ---: | ---: |
| Logic Grid Puzzle | 10 / 10 | 1.0000 | 10 / 10 | 1.00 | 0 |
| Trivia Creative Writing N=5 | 44 / 50 | 0.8800 | 6 / 10 | 1.00 | 0 |
| Trivia Creative Writing N=10 | 73 / 100 | 0.7300 | 1 / 10 | 1.00 | 0 |
| Codenames Collaborative | 14 / 22 | 0.6364 | 4 / 10 | 1.00 | 0 |

The macro-normalized score is **0.8116**, macro exact-match rate is **0.525**,
and macro parse rate is **1.000**.

Compared with the previous 10-sample run (`238a07b`), Logic stayed at 1.00,
Trivia N=5 increased from 0.86 to 0.88, Trivia N=10 decreased from 0.83 to
0.73, and Codenames increased from 0.5909 to 0.6364. The macro score decreased
from 0.8202 to 0.8116. The Trivia N=10 regression is genuine run-to-run
variance and remains an open derivation-policy research target.

## Runtime behavior

The run completed all 40 benchmark items through 50 isolated Roy invocations:

- 407 model calls;
- 1,739,554 input tokens, including 182,016 cached input tokens;
- 630,288 output tokens;
- 2,369,842 total tokens;
- 6,607 seconds of summed invocation wall time, with a 526-second maximum;
- 109 execution steps;
- 93 derived agents and 16 derived teams in the persisted artifacts;
- 10 tool errors, zero tool timeouts, zero model-request timeouts, zero turn
  failures, and zero `max_children_exceeded` rejections.

This is 4.4% fewer total tokens and 6.7% fewer input tokens than the prior
10-sample run (2,480,076 total and 1,864,399 input tokens), while retaining a
100% item completion and parse rate.

## Real recursive derivation

Unlike the earlier benchmark probes, this run contains a real second-generation
derivation. Logic Grid item 1 (`raw/0001/roy.json`) formed this hierarchy:

```text
root
└── team_001 LongHorizonCheckpointTeam
    ├── agent_researcher_001 EvidenceSteward-1
    │   ├── agent_tester_002 Tester-1
    │   └── agent_summarizer_003 Summarizer-3
    └── agent_tester_004 CheckpointVerifier-2
```

The two descendants below `EvidenceSteward-1` are generation 2. Across the
suite, the maximum observed generation was 2 and the recursive-derived-actor
count was 2. This establishes real benchmark evidence for
`root -> subteam -> subagent -> subagent`, not only unit-test support.

## Interpretation

The run confirms that the SPP harness is operational across all four datasets
without timeout failures and that team capacity is aligned with actual spawning.
It also shows that more derivation is not automatically better: Trivia N=10
remains unstable even though the system completes the workload. Future
derivation-policy experiments should treat this run as a fixed baseline rather
than changing Roy with SPP-specific behavior.
