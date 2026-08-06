# Read-only Critic Agent

## Scope

`search_harness.adapter.critic` implements the read-only Critic role under the offline Adapter boundary. One Critic run is bound to one primary Experience Set evaluation report, its source rollout JSONL and one Actor Harness snapshot. It can optionally bind a second aligned report, rollout and snapshot for comparison. It reuses the fixed `AgentLoop`, but its concrete prompt and tools are loaded from `harness_templates/adapter/critic/baseline/plugins/`.

The current Critic can inspect evidence and emit a `CriticResult`. Its failure-analysis output
stops at behavioral problem directions: repeated pattern, excluded causes, desired behavior,
success criteria and constraints. It cannot select Hook phases, author prompt wording, design
tools, modify files, submit patches, accept versions, call the retriever, intervene in Actor
rollouts or write long-term Memory.

The Critic plugin root includes a fixed `format_error_feedback` hook for Adapter reliability. It uses the existing `post_parse` phase to diagnose incomplete action tags and refine invalid parse errors. This hook is not installed in the Student baseline; an equivalent Student policy must be proposed and evaluated as an evolved mutable extension.

It also includes a fixed `turn_budget_notice` hook at `post_prompt`. At that point the `ModelInput` has been built but has not been sent to the model, so the hook appends a user reminder containing `core.step` and `core.max_steps`. On the final permitted turn it additionally requires the Critic to finish with `<final_answer>` rather than make another tool call. The transformed input is recorded through the normal `hook_applied` trace event.

## Context Boundary

The initial user message contains the selected report's `summary.json`, the bound Harness version and a compact manifest summary. When comparison evidence is bound, it also contains aggregate accuracy, problem-level transition, replicate-level transition and unmatched counts. Per-example records and complete trajectories are not inserted initially. They enter the model context only when the Critic calls a bound read-only tool.

`example_id` always addresses one logical question and returns its aggregate stability summary
and compact replicate directory. A complete trajectory requires both `example_id` and
`replicate_id`. Multiple replicates of one question are sampling evidence, not independent
cases.

The MVP only supports the `experience` split. Tool arguments contain identifiers and filters, never arbitrary filesystem paths. A Critic cannot switch to another report, rollout or Harness during a run.

The external plugin factories receive this read-only view through `PluginContext.runtime_context`. Ordinary Actor assembly leaves that optional field as `None` and is unchanged.

For each turn, the Critic prompt requires a concise plain-text analysis or intent before its single action block. This text is retained as `ParsedOutput.inband_thinking`; the following `<tool_call>` or `<final_answer>` remains the only loop-control action.

## Tools

- `list_evaluation_cases`: returns a compact problem-level page and supports score, stability,
  status and retriever-error filters.
- `get_case_evaluation(example_id)`: returns the complete question-level stability summary and
  replicate directory, but no Actor trace.
- `get_case_trajectory(example_id, replicate_id)`: returns one exact source rollout and trace.
- `get_harness_manifest`: returns the complete manifest of the bound Actor Harness.
- `get_harness_component`: returns one component's manifest entry and all UTF-8 files under its component directory.
- `list_comparison_cases`: filters and paginates aligned outcome transitions without returning question or answer text.
- `get_comparison_case`: returns paired complete evaluation records for one aligned `example_id`.
- `get_comparison_trajectory(example_id, replicate_id)`: returns paired complete rollouts plus
  replicate-local execution deltas, calculated as primary candidate minus comparison baseline.
- `get_harness_change_summary`: returns file and manifest component changes introduced by the primary candidate relative to the comparison baseline.

The distinction between case tools is intentional: evaluation explains how a case was judged, while trajectory exposes how the Actor executed it. This keeps the common inspection path small before a full trace is added to the context.

## Result And Log

The final action must contain a JSON object inside `<final_answer>` and is parsed into the deliberately small contract:

```python
CriticResult(
    analysis: str,
    problem_directions: tuple[dict[str, Any], ...],
    evidence_requests: tuple[str, ...],
    review: CriticReview | None,
)
```

`CriticResult` remains deliberately small. `problem_directions` uses dictionaries as its Python
container, but each item follows a closed six-field schema: `problem`, `observed_pattern`,
`excluded_causes`, `desired_behavior`, `success_criteria` and `constraints`. Missing fields,
unknown fields, wrong types and empty required strings are producer protocol errors. These fields
define what the next iteration should solve without prescribing how. The Coordinator validates
one direction through Worker trials; the Compiler no longer consumes Critic output directly. The
complete `AgentRun`, including model inputs, tool calls and observations, is written alongside the
parsed result.

## Run

Analyze an ordinary Actor plugins directory with the configured `TEACHER_*` model:

```powershell
& 'D:\ProgramData\miniconda3\envs\env_search_harness\python.exe' `
  -m search_harness.adapter critic `
  runs\components\actor\student_raw_100\evaluation `
  --actor-plugins-root harness_templates\actor\baseline\plugins
```

The rollout path defaults to the report's `summary.json.source_file`; use `--rollout-file` when that recorded path is no longer valid. To inspect an accepted Version Store snapshot instead:

```powershell
& 'D:\ProgramData\miniconda3\envs\env_search_harness\python.exe' `
  -m search_harness.adapter critic `
  runs\components\actor\student_raw_100\evaluation `
  --checkpoint-store harness_checkpoints\search_actor `
  --harness-version harness_v0002
```

Omit `--harness-version` to bind the latest accepted version. Logs default to `runs/components/critic/<timestamp>/critic.json`; `--output-file` selects an explicit path.

For a minimal review of a pending Compiler candidate, bind the candidate as the
primary Harness and its accepted parent as the comparison Harness:

```powershell
& 'D:\ProgramData\miniconda3\envs\env_search_harness\python.exe' `
  -m search_harness.adapter critic `
  runs\components\actor\candidate_84f16d34_100\evaluation `
  --checkpoint-store harness_checkpoints\search_actor `
  --iteration-id iteration_20260715T141520385026Z_84f16d34 `
  --compare-report-dir runs\components\actor\student_raw_100\evaluation `
  --compare-harness-version harness_v0001 `
  --task "Review whether the pending candidate improved over its parent. Treat primary as the candidate and comparison as the parent. First inspect the Harness change summary and aggregate score transitions. Then inspect representative primary-only-correct and comparison-only-correct trajectories. Judge the change as effective, harmful, or inconclusive before proposing further modifications."
```

The runner provenance in every primary rollout must match the selected
iteration ID and candidate digest. For accepted primary or comparison evidence,
every rollout must instead match the selected Version Store root, accepted
version ID and content digest. The Critic fails before model inference if rollout Harness
provenance is wrong, or if comparison identities and present replicate seed values differ. The
current report and rollout are loaded independently: no rollout file digest in the report proves
that its metrics came from those exact trajectory bytes. Two missing seed values also currently
compare equal, so callers must preserve complete rollout provenance. When
`--compare-harness-version` is omitted in iteration mode, the iteration's
parent version is selected automatically. The log records the iteration ID,
parent version, digest and revision. Review decisions are structured as
`CriticReview(decision="accept"|"reject", reason=...)`. A standalone Critic invocation remains
read-only and does not write the iteration journal; when invoked by Evolution Runner, the Runner
persists the structured review and uses it as the semantic accept/reject decision.

To compare two reports produced from versions in the same Version Store:

```powershell
& 'D:\ProgramData\miniconda3\envs\env_search_harness\python.exe' `
  -m search_harness.adapter critic `
  runs\components\actor\baseline\evaluation `
  --checkpoint-store harness_checkpoints\search_actor `
  --harness-version harness_v0001 `
  --compare-report-dir runs\components\actor\candidate\evaluation `
  --compare-harness-version harness_v0002
```

For ordinary directories, use `--compare-actor-plugins-root`. Both reports are joined only by `example_id`; ordering does not participate in alignment.

`CRITIC_REQUEST_TIMEOUT` controls only Critic model calls and overrides the selected model role's `*_REQUEST_TIMEOUT` or common `REQUEST_TIMEOUT`. Set it in `.env`; the current local value is `120` seconds. It does not affect Actor rollouts or the offline Teacher Judge.

## Visualize

The local visualizer exposes `/critic.html` for Critic logs. It lists run directories from `runs/components/critic/` by default, renders successful `CriticResult` artifacts and failed runs, and shows the complete AgentLoop event timeline including model-input snapshots, tool calls, observations, separately labeled native/in-band thinking and all Hook events. `Expand roles` controls default block expansion; it does not remove events from the timeline.

```powershell
& 'D:\ProgramData\miniconda3\envs\env_search_harness\python.exe' `
  -m search_harness.visualizer `
  --critic-runs-dir runs\components\critic
```

Open `http://127.0.0.1:8765/critic.html`. The viewer is read-only; it accepts only Critic-shaped JSON logs within the configured directory.
