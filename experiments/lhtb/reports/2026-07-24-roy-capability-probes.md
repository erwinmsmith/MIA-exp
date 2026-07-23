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
