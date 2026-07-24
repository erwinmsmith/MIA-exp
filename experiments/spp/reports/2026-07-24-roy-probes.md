# Roy SPP capability probes — 2026-07-24

These are diagnostic single-item probes, not benchmark claims. Raw artifacts are
kept in ignored local directories under `results/spp/probes/`.

## Environment

- Provider/model: `deepseek` / `deepseek-v4-flash`
- SPP data commit: `619c8a0ff4205bfd39e33f0867647b40e1703b94`
- Initial Roy commit: `76247824ba04fa79f59cdaa8d8f71f6200906ad0`
- Repaired Roy commit: `e706501d22725832dbe2716f311ca807f50c27ed`

## Results

| Probe | Score | Parse | Roy structure | Notes |
| --- | ---: | ---: | --- | --- |
| Logic Grid item 0 | 1/1 | yes | Direct, 1 step | Correctly avoided unnecessary delegation |
| Trivia N=5 item 0 | 4/5 | yes | 1 team, 2 derived agents, 2 steps | Team and feedback/cache events were retained |
| Trivia N=10 item 0 | 6/10 | yes | Direct, 1 step | Valid run, but weak factual recall and no specialist delegation |
| Codenames item 0, initial | 0/4 | no | Spymaster only | Streaming output was truncated before `FINAL_HINT` |
| Codenames item 0, repaired | 2/4 | yes | Spymaster: 2 steps; Guesser: 3 agents, 3 steps | Two isolated sessions; output-contract repair unblocked Guesser |

The macro average of the four valid post-repair benchmark probes is `0.725`.
Because each row contains one item, this number is useful only as a harness
sanity check.

## Exposed core gap and repair

The initial Codenames Spymaster stream stopped for length but the finish reason
was not surfaced, and the incomplete prose was accepted even though the user
required a `FINAL_HINT:` line. This exposed a general runtime issue rather than a
benchmark-specific parser issue.

Roy commit `e706501` adds:

- finish-reason propagation for OpenAI-compatible and Anthropic streams;
- `llm.stream.truncated` trace events for `length`/`max_tokens`;
- detection of explicit uppercase root output markers declared by the user;
- one bounded JSON-based format repair that preserves the candidate answer;
- a dependent `finalize` step with its own execution-tree checkpoint and cache
  snapshot;
- success/failure repair events and failure feedback persistence.

The same Codenames item then produced `FINAL_HINT: screen`, launched a fresh
Guesser session, derived three Guesser-side agents (planner, critic, and
researcher), and emitted a parseable four-word answer. The Guesser prompt and
workspace contain no `Target words:` field; only the public board and Spymaster
hint cross the session boundary.

## Remaining research findings

- Trivia N=10 was solved directly despite spanning ten knowledge domains. This is
  a useful negative example for later delegation-policy tuning; it should not be
  hard-coded in the benchmark adapter.
- The N=5 team used a root synthesis fallback after one proposed member was
  rejected, but still returned a scoreable story. Future experiments should
  compare this failure mode across seeds and budgets.
- Codenames correctly derived agents on the Guesser side, but the selected hint
  recovered only two of four targets. More samples are required before changing
  generic delegation or feedback policy.
- Full benchmark runs should use repeated seeds and report score, exact-match
  rate, parse rate, tokens, wall time, derived agents/teams, and repair/fallback
  incidence together.

## Capacity and closure follow-up

The follow-up fixes are published through Roy commit
`761e9cabe56b2aa91a379c93af7e42b0775b6136` (including its prerequisite commits
`f25d2b1`, `8305f8b`, `697b663`, `71f4cbc`, and `79e6087`). They add team-capacity reservations,
post-mutation verification closure, bounded closure retries, executable-plan
preflight, direct-decision auditing for tasks with many independent obligations,
a JSON-compatible dynamic continuation prompt, recursive team-member capability
inheritance, and immediate root verification handoff after a delegated mutation.

Post-fix single-item probes:

| Probe | Score | Steps | Actual runtime structure | Capacity / closure evidence |
| --- | ---: | ---: | --- | --- |
| Trivia N=5 item 0 | 5/5 | 2 | 1 team, 2 members | 1 reservation, 1 release, 0 child/turn-capacity rejections |
| Codenames item 0 | 3/4 | 2 per Guesser | 1 team, Guesser + Critic | Both tool-free semantic members returned non-empty results; 0 capacity rejections |
| Trivia N=10 item 0 | 5/10 | 3 | 2 sequential knowledge specialists | An infeasible auto-added evidence collector was rejected before spawn; 0 capacity rejections; dynamic reassessment ran |

The N=5 planner initially proposed FactFinder, StoryWriter, and StoryReviewer.
FactFinder was preflighted out because the SPP policy deliberately exposes no web
or filesystem tool path; the remaining two members were reserved and executed
without the former `max_children_exceeded` failure. A later generic fix permits
model-internal knowledge specialists while still rejecting automatically added
actors whose task explicitly requires tool or source-file evidence.

The final N=10 run no longer fell back to a one-shot root answer: it completed two
delegation steps and a final synthesis step. Its remaining factual misses are
model-knowledge errors under the intentionally tool-free SPP policy, not empty
actors or capacity failures. One continuation response was non-JSON and therefore
fell back to synthesis within the remaining limited token budget; the earlier
provider-side HTTP 400 caused by a missing JSON cue is fixed.

These probes validate root-to-team and root-to-agent behavior. Their maximum actor
generation remains 1; second-generation runtime derivation is evaluated separately
with the long-horizon container probe rather than claimed from these SPP samples.
