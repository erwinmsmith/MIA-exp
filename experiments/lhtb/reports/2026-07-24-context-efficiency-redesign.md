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

Roy core commits `ad0fbf1`, `fa78f99`, `75427af`, and `b23408c` make execution
state, rather than context limits, the control plane:

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
  accepted as functional verification after mutation.

The MIA-exp adapter now sends changed verifier artifacts, including Harbor's full
`pytest.log`, once. An unchanged artifact is represented by a SHA-256 fingerprint
and resolves through the persisted execution ledger.

The standard LHTB policy restores a 32K context window and expands the execution
envelope. A separate development config provides a multi-hour completion-oriented
run without replacing its workspace policy with Harbor's continuation countdown.
This configuration is diagnostic and is not an official-time benchmark result.

## Verification

- Roy: 41 test files, 297 tests passed.
- Roy type checking, linting, and build passed.
- Adapter: 9 unit tests passed, including delta feedback and development deadline
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
