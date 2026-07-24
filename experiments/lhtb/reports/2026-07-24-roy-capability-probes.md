# Roy Capability Probes — 2026-07-24

## Scope

These probes exercised the generic Roy runtime against two LHTB tasks. Raw Harbor
jobs remain ignored. This report records only reproducible configuration, aggregate
runtime evidence, and issues that resulted in generic Roy or experiment-harness
changes.

Source baselines before the changes:

- MIA-exp: `bb7a310ce32e8862d0c68e7af7d5beb9e4fcd6b3`
- Roy: `9d02acd4c2da07009ea8a35822d92ef5829cf9ae`
- LHTB: `11c5e775a9f5a296744b7e9b9051a9d8ab88f04f`

The generic runtime fixes from these probes are published in Roy commit
`76247824ba04fa79f59cdaa8d8f71f6200906ad0`.

## Environment validation

`scripts/prepare-lhtb-images.sh` pulled and probed the official `linux/amd64`
images. Each image had `/app`, Python, and a registry digest:

| Task | Image digest |
| --- | --- |
| `langchain-version-migration` | `sha256:cf31f3848d622f3445e9644f5200bab766f0c7144467c5323d21d629185eb13c` |
| `great-expectations-audit` | `sha256:aaf6c349caf62e887b982a3f5b706bdc3300b7619ba48817e6183c2391867b01` |
| `document-table-layout-reconstruction` | `sha256:54127c0cbf0c83a421cec88e8d540abcf06d0fd4e75c09fc6e9d6a3a416a58bb` |

The Roy bundle also passed the Linux container smoke and Harbor adapter smoke.

## LangChain migration probe

Configuration:

- task: `langchain-version-migration`
- agent timeout multiplier: `0.25`
- wall time: 22 minutes 41 seconds
- result: reward `0`, `AgentTimeoutError`

Observed behavior:

- Harbor completed three verifier/resume phases while preserving the same Roy
  session and `.roy` state.
- Later turns emitted root and descendant `execution.cache.hit` events. A
  representative second turn loaded 3 steps, 3 paths, 4 actors, and 10 feedback
  records.
- Sequential teams emitted `team.member.step_cache.injected`; later members
  received prior member results and failures.
- The cache grew to 10 steps, 17 cached actors, and 35 feedback records.
- The third phase migrated `chain.py`, `models.py`, `retriever.py`, and
  `router.py` to modern LangChain APIs and updated the active environment.
- The final verifier still rejected dependency metadata. The run updated the
  primary project metadata but missed a stale parallel declaration. This exposed
  an acceptance-closure problem rather than an image or startup failure.

Resulting generic Roy changes:

- acceptance checklists are extracted from the task and supplied to root,
  descendants, teams, continuation, and execution closure;
- finalization requires evidence-aware classification of checklist items and
  attention to parallel declarations, generated metadata, configuration, call
  sites, and compatibility paths;
- a mutated long-horizon path that remains partial or unverified derives another
  sequential executor/verifier team instead of finalizing immediately.

## Great Expectations audit probe

Configuration:

- task: `great-expectations-audit`
- agent timeout multiplier: `0.12`
- agent time limit: 432 seconds
- result: reward `0`, `AgentTimeoutError`

Live trace evidence captured before Harbor removed the timed-out container:

- step 1 created a team plus three members and cached one partial path;
- step 2 created a fresh team plus three fresh members and cached a second path;
- the first path recorded `outputs` and `validation_report.json` as invalid,
  mutation as observed, and verification as missing;
- the next member made two equivalent reads, both of which were intercepted as
  `tool.path.cache_rejected` rather than reaching the filesystem;
- the second path added eight observed paths with no new failed tools;
- step-level actor collection initially leaked prior-step actor IDs into step 2;
- repeated full task text in the team cache inflated later member prompts to more
  than 100,000 characters.

Resulting generic Roy changes:

- invalid-path cache entries are invalidated for paths affected by successful
  shell mutations such as `mkdir`, `touch`, `rm`, `mv`, `cp`, and redirection;
- absolute workspace paths and relative paths share one canonical cache key;
- actor/team descendant collection is bounded by the current step start time;
- team-step memory now stores bounded task summaries and prior results instead of
  duplicating complete long-horizon task text.

## Verification

At report time:

- TypeScript type checking and ESLint passed.
- All Roy tests passed.
- The test suite covers live and persisted invalid-path rejection, invalidation
  after shell mutation, acceptance-checklist injection, recovery-team derivation,
  step-scoped actor caching, cross-turn execution knowledge, sequential team
  feedback, and existing recursive/multi-child delegation behavior.

Neither real probe passed its benchmark verifier within the deliberately reduced
agent timeout. The probes are diagnostic evidence for generic runtime behavior;
they are not benchmark success claims.

## Capacity, recursion, and execution-closure follow-up

The follow-up runtime fixes are published through Roy commit
`761e9cabe56b2aa91a379c93af7e42b0775b6136`. They add:

- atomic team-capacity reservation and release, including protection for planned
  member slots while recursive descendants are running;
- pre-spawn feasibility checks for actors whose requested evidence requires
  unavailable tools, while retaining useful tool-free knowledge roles;
- recursive delegation capability inheritance for custom team members;
- mutation-aware root handoff, bounded root execution attempts, and a closure
  marker when mutation is not followed by verification;
- JSON-safe dynamic continuation and explicit telemetry for capacity, recursive
  actors, infeasible plans, and execution closure.

The official three-item oracle smoke still passed `3/3`. The richer Roy probe used
the official `langchain-version-migration` image with a `0.12` agent timeout
multiplier:

| Evidence | Observed result |
| --- | --- |
| Capacity | 2 reservations and 2 releases; 0 child-capacity and 0 turn-capacity rejections |
| Recursive derivation | Maximum generation 2; 6 second-generation actors in the persisted first phase |
| Nested team | `Executor-2` created `Migration Team`, which ran `dep_fixer`, `answer_migrator`, and `router_migrator` |
| Feedback | Failed or ungrounded member results were included in `team_step_cache` for later members and verifiers |
| Root handoff | `root.execution.handoff.required` fired with `delegated_workspace_mutation_observed` |
| Root closure work | 3 root execution attempts with filesystem reads, writes, and shell verification |
| External retry | The LHTB verifier rejected phase 1; Harbor injected the failure and Roy began a second team/repair phase |

The real recursive path was:

```text
Roy
└── LongHorizonCheckpointTeam
    ├── ProjectExplorer
    ├── Executor-2
    │   └── Migration Team
    │       ├── dep_fixer
    │       ├── answer_migrator
    │       └── router_migrator
    └── Verifier-3
        ├── evidence researcher
        ├── critic
        └── executable tester
```

This closes the earlier evidence gap: second-generation subagents and a nested
subteam now occurred in an actual benchmark container, not only in unit tests.
The nested team also demonstrated failure propagation: incorrect assumed paths
and unexecuted tool requests were preserved as failed-member feedback rather
than silently treated as successful work.

The benchmark task itself did not pass. Phase 1 reached the verifier but left the
legacy `requirements.txt` declaration unchanged, so the dependency gate returned
reward `0`. Roy consumed that verifier feedback and started a second repair phase,
but the overall 10 minute 58 second budget ended with `AgentTimeoutError` before
the migration could pass. This is evidence that the modify–verify–feedback–retry
mechanism now runs end to end; it is not a benchmark-success claim. The remaining
task-quality and delegation-policy behavior is intentionally left as an
experimental question rather than encoded as an LHTB-specific core adaptation.
