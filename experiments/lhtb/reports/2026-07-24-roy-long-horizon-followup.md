# Roy long-horizon follow-up — 2026-07-24

## Scope

The checked-out LHTB revision contains three unique tasks, so a 10-unique-sample
run is not possible for this benchmark. This follow-up runs all three tasks and
uses additional Great Expectations probes to isolate runtime failures. Raw jobs
and complete traces remain ignored.

- LHTB: `11c5e775a9f5a296744b7e9b9051a9d8ab88f04f`
- Provider/model: `deepseek` / `deepseek-v4-flash`
- Images: official pinned `linux/amd64` digests recorded in the capability report

## Completed diagnostic batch

Job `lhtb-roy-full-6f7ae87-20260724` ran all three tasks concurrently with Roy
`6f7ae87`. Harbor completed the 90-minute job with this official result:

| Task | Reward | Terminal state |
| --- | ---: | --- |
| Great Expectations audit | 0.000 | `AgentTimeoutError` |
| Document table reconstruction | 0.005 | `AgentTimeoutError` |
| LangChain migration | 0.000 | `AgentTimeoutError` |

The mean reward was `0.00167`. The batch consumed 8,394,227 input tokens,
1,674,240 cached tokens, and 468,276 output tokens. It proved that images,
credentials, the Roy bundle, filesystem tools, shell execution, persistence,
verifier feedback, and continuation rounds all started successfully. It did not
prove benchmark completion.

The failures were not caused by absent filesystem or shell tools. The dominant
problems were:

- delegated mutations were initially omitted from root closure evidence;
- repeated full-context phases consumed the Harbor timeout;
- some actors wrote or inspected non-authoritative parallel paths;
- a pip warning URL was mistaken for requested web evidence;
- mutation planners embedded entire source files in JSON or fragile
  `python -c` shell writers;
- modification, verification, feedback, and repair occurred, but official
  acceptance gates remained unmet.

## Full-time follow-up in progress

Job `lhtb-roy-long-closure-a650eee-20260724` uses Roy `a650eee` and runs all
three tasks concurrently. At the time of this report, every task had completed
at least one official verifier phase and resumed from concrete verifier
feedback. Five complete Roy artifacts showed:

- 211 model calls;
- 2,344,387 input tokens and 139,132 output tokens;
- 5 explicit `root.execution.closure.unmet` results rather than false success;
- 8 tool-planning parse failures;
- 1 bounded tool timeout;
- 0 model-request timeouts;
- 2 externally propagated wall-clock limits.

The latest observed official gates were still failing: LangChain rejected stale
dependency metadata, Document reconstruction had reward 0, and Great
Expectations had reward 0. This remains an in-progress diagnostic job and is not
reported as a pass.

## Generic repairs published from the live evidence

Roy commits through `a2989e4f2a49cc062c418e42b5bc8cdd1721bb24` add:

- delegated tool-call collection in root execution and global acceptance;
- timestamped, deduplicated mutation and verification evidence;
- an external wall-clock deadline and bounded planning/tool deadlines;
- explicit model, planning, and tool timeout telemetry;
- prompt compaction for long tool-planning tasks;
- authoritative source-root guidance and suppression of incidental log URLs;
- retry of truncated mutation-plan JSON with a larger bounded second response;
- bounded `fs.write` chunking guidance and protection against fragile shell
  file writers;
- runtime rejection and trace telemetry when a plan tries to create a top-level
  package parallel to an observed `src/`, `lib/`, or `packages/` source root.

The outer harness now supports versioned Roy bundles, secret-safe credential
upload, verifier-artifact feedback, and concurrent LHTB execution. Policy
version 14 reduces the session window from 30 to 20 turns, caps active context at
16K tokens, and includes subagent reports as summaries. Full traces, trees,
paths, actors, teams, feedback, and execution caches remain persisted for
inspection.

## Latest authoritative-path probe

A final short Great Expectations probe used the complete `a2989e4` runtime and
policy version 14. It ended after 7 minutes 33 seconds with reward 0 and the
expected reduced-budget `AgentTimeoutError`. Its first phase:

- wrote `src/dq_audit/cleaning.py` under the observed authoritative source root;
- did not create the parallel `/app/dq_audit` package seen in the preceding
  `3073e33` probe;
- recorded 0 tool-planning failures, 0 tool timeouts, and 0 model timeouts;
- made 26 model calls with 250,427 input and 25,731 output tokens;
- returned explicit execution-closure failure and official reward 0 because the
  complete audit pipeline and required artifacts were still absent.

This validates the path and planning recovery behavior in a real container, but
it also shows that a seven-minute diagnostic window is insufficient for the
full Great Expectations implementation.

## Verification

- Roy: 41 test files, 293 tests passed.
- TypeScript, ESLint, and the production build passed.
- Outer Python: 21 tests passed.
- Harbor adapter smoke passed.
- The latest standalone bundle passed in the official Linux amd64 Node
  container (`v20.20.2`).

No LHTB pass is claimed yet. The key remaining issue is solution quality under
the official gates, especially complete implementation of Great Expectations
and document reconstruction and removal of every stale LangChain dependency
declaration.
