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

Roy core commit `ad0fbf1` makes execution state, rather than context limits, the
control plane:

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
  result exists.

The MIA-exp adapter now sends changed verifier artifacts in full once. An
unchanged artifact is represented by a SHA-256 fingerprint and resolves through
the persisted execution ledger.

The standard LHTB policy restores a 32K context window and expands the execution
envelope. A separate development config provides a multi-hour completion-oriented
run without replacing its workspace policy with Harbor's continuation countdown.
This configuration is diagnostic and is not an official-time benchmark result.

## Verification

- Roy: 41 test files, 294 tests passed.
- Roy type checking, linting, and build passed.
- Adapter: 9 unit tests passed, including delta feedback and development deadline
  behavior.
- Linux `amd64` bundled CLI container smoke passed.
- Harbor adapter import smoke passed.
- The official LHTB oracle completed all three local tasks with reward `1.0`
  (3/3), confirming that the images, task setup, reference solutions, and
  verifiers are executable.

## Live validation

The versioned bundle `roy-run-ad0fbf1.mjs` is used for the next real LHTB
development run. Benchmark reward, Harbor exception status, model-call count,
input tokens, resumed-path events, actor count, and verification phases must all
be reported from the resulting artifacts. A passing unit or oracle smoke is not
reported as a Roy benchmark pass.
