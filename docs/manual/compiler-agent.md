# Standalone Compiler Agent

## Scope

`search_harness.adapter.compiler` implements the Compiler role under the offline Adapter
boundary. It consumes one Coordinator artifact whose verdict is `supported`, binds the latest
accepted Harness snapshot, and asks an external Compiler plugin Harness to produce one complete
file transaction. Before a model call, it follows `direction_source` back to the Critic log and
requires that log's accepted Harness version and content digest to equal the selected parent.

The Compiler does not independently browse evaluation cases or Actor trajectories. Its evidence
boundary contains the Critic problem direction, Coordinator analysis and recommendation, the
selected completed trial and the compact cross-case trial ledger. It rejects `rejected` or
`inconclusive` Coordinator results. The Compiler translates the tested behavior into a general
plugin implementation; it must not persist case-specific entities from Worker instructions.

## Patch Boundary

The final artifact is either:

- a non-empty tuple of `FileEdit` write/delete operations plus a summary; or
- no edits and a concrete clarification request.

Paths are UTF-8, POSIX-style and relative to the Actor plugins root. A transaction may modify mutable components or create and register new tools, extensions and prompt implementations. Every model-created component must be declared `mutable`; parent fixed components remain protected by `HarnessValidator`.

The host applies all edits atomically through `IterationSession.apply_patch()` and immediately records a validation report. It does not run Actor rollouts, evaluate task performance, accept the candidate, reject it, or commit a new Git version. A compiled candidate therefore remains a resumable pending iteration.

## Tools

The fixed Compiler baseline at `harness_templates/adapter/compiler/baseline/plugins/` exposes only parent-Harness inspection:

- `list_harness_files` lists file paths and sizes;
- `read_harness_file` reads one complete UTF-8 file;
- `get_harness_component` reads one manifest declaration and its component directory.
- `get_hook_authoring_guide` returns focused implementation, lifecycle, state-access,
  model-inference, final-decision and manifest authoring contracts.

Before creating or modifying a Hook, the Compiler must read the `implementation` topic, which
defines legal core imports, the exact `BaseHook` constructor contract, `build()` factory shape and
persistent `StateRef` skeleton. A model-driven Hook must additionally use the framework's
`context.call_model(...)` interface, declare its allowed `model_profiles`, keep prompts in its
extension component, parse the response explicitly and provide deterministic fallback behavior.
A Hook that enforces completion must read `final_decision`, use `PRE_FINAL` with
`FinalDecision.defer(feedback)`, and declare its state-machine completion condition.

The model cannot mutate the workspace incrementally through these tools. It returns the whole transaction in `<final_answer>`, avoiding partial model-side state and preserving one journaled patch boundary.

## Run

```powershell
& 'D:\ProgramData\miniconda3\envs\env_search_harness\python.exe' `
  -m search_harness.adapter compiler `
  runs\components\intervention_coordinator\<run_id>\coordinator.json `
  --checkpoint-store harness_checkpoints\search_actor
```

The checkpoint store must already be initialized. `--harness-version` may name the latest
accepted version explicitly; linear-history rules reject an older writable parent. Logs default
to `runs/components/compiler/<timestamp>/compiler.json` and contain the Intervention and Critic
artifact paths, direction index, parent provenance, complete `AgentRun`, parsed transaction,
validation result and iteration ID.

`COMPILER_REQUEST_TIMEOUT` controls only Compiler model calls. It falls back to the selected model role timeout when absent.

## Visual Inspection

Compiler logs retain the complete `AgentRun`, including each structured model input, provider-native reasoning metadata, parsed in-band thinking, action blocks, tool interactions and Hook events. Start the shared viewer with the Compiler log root:

```powershell
& 'D:\ProgramData\miniconda3\envs\env_search_harness\python.exe' `
  -m search_harness.visualizer `
  --actor-runs-dir runs\components\actor `
  --evaluation-runs-dir runs\components `
  --critic-runs-dir runs\components\critic `
  --compiler-runs-dir runs\components\compiler `
  --checkpoint-store harness_checkpoints\search_actor
```

Open `http://127.0.0.1:8765/compiler.html`. The left column lists Compiler logs, the center shows the parsed transaction, validation report and complete execution timeline, and the right column shows steps plus parent-version and iteration details. Native thinking and in-band thinking are rendered as separate roles; Hook events are always present and can be collapsed through `Expand roles`.
