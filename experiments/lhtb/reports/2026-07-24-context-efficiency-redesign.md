# Roy context-efficiency redesign — 2026-07-24

## Trigger

The first complete three-task LHTB run did not establish task completion:

- all three trials ended with Harbor `AgentTimeoutError`;
- mean reward was `0.0016667` (Great Expectations `0`, LangChain `0`,
  document reconstruction `0.005`);
- 468 model calls consumed 8,394,227 input tokens and 468,276 output tokens;
- the median complete Roy phase consumed 359,648 input tokens.

This was treated as an execution-design failure, not as a reason to reduce the
model context or shorten the run.

## Structural diagnosis

The trace and prompt artifacts exposed three multiplicative causes:

1. Agent prompt templates already rendered identity, task, public context, and
   private memory, but Runtime appended those sections a second time.
2. Every team member performed an LLM delegation decision before executing its
   assigned task. `agent.delegation_decision` alone accounted for 219 calls and
   5,596,015 input tokens.
3. Every Harbor verifier continuation entered root delegation as a new task and
   rebuilt a new initial team instead of resuming the persisted open execution
   path. Unchanged verifier artifacts were also replayed in every continuation.

Across the old artifacts, 288 created actors had an average rendered prompt size
of 103,679 characters and a maximum of 177,818 characters.

## Implemented redesign

Roy core commits `ad0fbf1`, `fa78f99`, `75427af`, `b23408c`, `5cad652`,
`a166a1c`, `5a06952`, `632754e`, and `a1092ca` make execution state, rather
than context limits, the control plane:

- prompt slots are rendered once; Runtime adds only missing fallback sections;
- irrelevant zero-overlap execution-cache records are excluded;
- a verifier continuation locates the most relevant open cached correlation,
  skips root re-planning, and resumes root execution directly;
- the new path records the prior open path as its parent, preserving a
  cross-turn path chain;
- continuation and root execution prompts use one compact execution ledger
  instead of duplicating steps, actor reports, team reports, and full cache
  objects;
- only a team lead with explicit or staged recursive responsibility evaluates
  descendant delegation; bounded members execute their assigned closure
  directly;
- synthesized team evidence replaces duplicated member reports when a team
  result exists;
- mutation-task output paths are no longer mistaken for missing input evidence;
- long-horizon workspace tasks obey the configured exploratory delegation limit
  and hand control to root implementation instead of spending every delegation
  round on additional analysis teams;
- transformed repair prompts preserve the original workspace-mutation intent in
  the tool planner, so a resumed phase cannot satisfy the closure by repeatedly
  listing and reading files without mutation or verification;
- task-declared shell commands are extracted from explicit shell fences and
  executed with their real exit status; a successful Python module/script CLI is
  accepted as functional verification after mutation;
- `fs.read` supports inclusive line ranges, and a failed command traceback is
  deterministically converted into a bounded read around the reported source
  line before another model repair decision;
- an equivalent failed verification is skipped when no mutation occurred after
  it, while the same verification is allowed immediately after a newer
  successful mutation;
- inline Python/Node source writers are rejected when structured file mutation
  tools are available, avoiding shell quoting corruption without disabling
  terminal execution;
- tool planning carries a causal observation frontier: the latest result retains
  repair detail, while historical commands, errors, and outputs are compact
  summaries. The stable task head and newest feedback tail are retained instead
  of replaying the entire growing prompt and every old log on every tool round;
- deterministic inspection plans use path-scoped cache invalidation across root
  closure attempts. A cached config read survives an unrelated source edit, a
  source read is invalidated by an edit to that source, and a directory listing
  is not discarded by an in-place replacement;
- a truncated structured `fs.write` response is recovered into an executable
  bounded source chunk. The first recovered chunk overwrites the target and a
  subsequent distinct recovered chunk appends, so generated implementation work
  is no longer discarded merely because the surrounding JSON ended at the model
  output boundary;
- verification state now distinguishes attempted, failed, and passed checks
  relative to the latest mutation. A failed verifier retains its detailed causal
  frontier after a later source read, permits one targeted inspection, then
  requires a repair before another verification;
- semantically identical shell calls ignore execution-only timeout differences,
  while output contracts remain distinct. Existing source files cannot be
  destructively overwritten during a verifier-driven repair; focused replacement
  preserves already-working behavior.

The MIA-exp adapter now sends changed verifier artifacts, including Harbor's full
`pytest.log`, once. An unchanged artifact is represented by a SHA-256 fingerprint
and resolves through the persisted execution ledger. After Harbor has mounted the
official tests, each continuation also declares the available `/tests` verifier
entrypoint as a required local command. Roy can therefore repair and rerun the
real verifier inside one phase instead of waiting for another outer continuation
after every edit. Verifier entrypoints already accessible to terminal agents are
mirrored into `.roy/official-verifier/` so workspace-scoped filesystem reads can
inspect their exact assertions. The custom Harbor environment deletes trial
containers and volumes without deleting pulled benchmark images after every
probe.

The standard LHTB policy restores a 32K context window and expands the execution
envelope. A separate development config provides a multi-hour completion-oriented
run without replacing its workspace policy with Harbor's continuation countdown.
This configuration is diagnostic and is not an official-time benchmark result.

## Verification

- Roy: 41 test files, 310 tests passed.
- Roy type checking, linting, and build passed.
- Adapter: 10 LHTB adapter tests and 24 outer tests passed, including delta
  feedback, verifier mirroring, image retention, and development deadline
  behavior.
- Linux `amd64` bundled CLI container smoke passed.
- Harbor adapter import smoke passed.
- The official LHTB oracle completed all three local tasks with reward `1.0`
  (3/3), confirming that the images, task setup, reference solutions, and
  verifiers are executable.

## Live validation

An initial Great Expectations development probe with `ad0fbf1` was deliberately
terminated after 4 minutes 39 seconds when its trace exposed another structural
defect. At that point:

- nine actors had an average rendered prompt size of 13,175 tokens, compared with
  the old estimated average of 29,623 tokens (55.5% lower);
- all nine bounded members emitted the new delegation-assessment skip event;
- three root teams had nevertheless been created because two required output
  paths were misclassified as missing read evidence.

The probe is diagnostic and is not a benchmark result. `fa78f99` fixes that
newly exposed handoff defect.

A second Great Expectations probe with `fa78f99` completed its first Roy phase in
about four minutes without an agent timeout. It created one team and three actors,
then handed control to root execution after the delegated mutation:

- 45 model calls;
- 416,159 input tokens, of which 227,456 were reported as cached input;
- 31 tool calls and eight root closure attempts;
- zero new actors and zero new teams in phase two;
- one `root.task_loop.resumed` event linked phase two to phase one's open path.

This confirmed persistent resumption, but the phase-two trace repeated
`fs.list`/`fs.read` because the wrapped repair prompt had lost the original
mutation intent. It also exposed that Harbor's detailed `ImportError` was stored
in `pytest.log`, which the adapter had not included. The probe was stopped after
capturing both defects and is not a benchmark result. Core `75427af` and the
adapter change close them.

The next versioned bundle must report benchmark reward, Harbor exception status,
model-call count, input tokens, resumed-path events, actor count, and verification
phases from complete artifacts. A passing unit or oracle smoke is not reported as
a Roy benchmark pass.

A third diagnostic phase with `75427af` reduced the first phase to 39 model calls
and 362,747 input tokens, but still relied on the model to infer the task's
explicit required CLI from prose. It reached Harbor verification without timing
out, then repeated inspection in repair attempts. The task already supplied its
authoritative command in a `bash` fence; generic CLI extraction and functional
verification support were therefore added in `b23408c`. This is a reusable
terminal-agent capability rather than an LHTB-specific command.

The `b23408c` Great Expectations development run was intentionally stopped after
seven verifier phases rather than allowed to spend the remaining multi-hour
envelope. It did not raise `AgentTimeoutError`, reused the same persisted path in
every continuation, and created no new team after phase one. However, reward was
still `0.0`, and the seven Roy phases consumed 289 model calls, 2,956,552 input
tokens (2,101,248 cached input), 130,098 output tokens, and 238 tool calls. The
implementation progressed from an indentation error to a concrete Great
Expectations API compatibility failure, but it was still waiting for outer
verification between repairs and replaying large historical command outputs.

That measurement directly motivated `5cad652` and `a166a1c` plus the local
verifier handoff in the adapter. No passing claim is made for those revisions
until a fresh Roy run produces a successful official verifier artifact.

The first `a166a1c` live probe was stopped after about four minutes when root
attempts four and five still repeated deterministic workspace listing and config
reads. The within-loop causal frontier was working, but Runtime had only applied
cross-attempt caching to failed verification commands. Core `5a06952` generalizes
that cache to path-scoped inspection evidence. This probe was stopped to avoid
spending the multi-hour envelope on a known replay defect and is not a benchmark
result.

The first `5a06952` probe confirmed that all three stale deterministic plans
(`fs.list`, the unchanged config read, and the already failed CLI) were skipped
at every root closure attempt. It then exposed a different zero-progress path:
the model produced a large, correctly targeted `fs.write` plan for
`src/dq_audit/audit.py`, but the JSON response ended inside the source string.
Runtime retried parsing and eventually discarded the generated code, leaving
later root attempts with zero tool calls. The probe was stopped after about five
minutes. Core `632754e` recovers that response as bounded overwrite/append chunks
and has regression coverage for both the first and subsequent chunks.

The `632754e` Great Expectations probe ran for 22 minutes 34 seconds across six
Roy phases without `AgentTimeoutError`. It consumed 220 model calls, 1,887,461
input tokens (1,166,336 cached), and 113,023 output tokens. Average input per
model call was 8,579 tokens, down from about 10,230 in the earlier `b23408c`
probe, and the first two phases consumed 785,975 input tokens rather than
multi-million-token single-task runs.

The probe recovered and compiled a 21 KB implementation, produced six required
artifacts, ran the official `/tests/test_outputs.py` inside the Roy phase, and
temporarily reduced the verifier to one passing and ten failing tests. It was
then deliberately stopped at reward `0.0`: the old bundle treated the failed
verification as if no verification had run, lost its detailed failure after
later reads, and replaced the entire partially working source with a new
implementation. The rewrite regressed the task to a Great Expectations
`DataContext` error. Core `a1092ca` is the evidence-driven repair: it preserves
the failed verifier frontier, enforces failure → targeted inspection → focused
mutation → re-verification, canonicalizes timeout-only duplicate commands, and
rejects destructive repair overwrites of an existing file.
