# Harness Checkpoint Store

## Purpose

`search_harness.versioning` implements the checkpoint persistence boundary needed before an Adapter starts proposing Harness changes. The internal mechanism remains named `HarnessVersionStore`; its user-facing storage root is a Harness Checkpoint Store. A candidate is not a copied plugin directory: it is an accepted immutable snapshot plus an in-memory file overlay. Only runtime validation uses a temporary directory, and only an accepted candidate is written to the store's own Git repository.

The current implementation is intentionally linear and single-process. A workspace can only be accepted when its parent is the latest accepted version.

The single-writer rule is an operational requirement, not a lock enforced by the store. Acceptance
writes the plugins tree, creates a Git commit and then appends `versions.jsonl`; iteration events are
also append-only JSONL. Normal exceptions around Git commit restore the plugins tree, but abrupt
process termination or a metadata write failure can still leave Git, the version index or a journal
tail out of sync. Back up the checkpoint store before manual repair and do not run two writers
against the same store.

## Main Objects

- `HarnessSnapshot`: an immutable mapping from plugins-root-relative POSIX paths to bytes, with a stable content digest and optional Git commit.
- `CandidateWorkspace`: a parent snapshot and mutable overlay. Reads merge the two layers; writes and deletes never alter the parent.
- `FileEdit`: one `write` or `delete` operation. `CandidateWorkspace.apply_patch()` applies a non-empty edit list transactionally and rolls back the complete overlay when any edit fails.
- `HarnessValidator`: validates fixed boundaries, manifest policy, UTF-8 Python syntax and real registry assembly. It returns a `ValidationReport` tied to the candidate revision and digest.
- `HarnessVersionStore`: initializes a dedicated Git repository, resolves accepted commits into memory, opens candidates and accepts validated changes.
- `IterationSession`: the durable evolution entrypoint. It journals patches, validation reports and terminal accept/reject decisions, and can reconstruct a pending candidate after process restart.

`CandidateWorkspace.add_extension()` is the controlled creation interface for a new hook component. It creates files under `extensions/<instance_id>/`, updates `harness.json` in the same transaction and always writes `evolution_policy: mutable`. The caller does not choose this policy.

## Validation Rules

The protection boundary comes from the parent accepted manifest, never from candidate-provided metadata.

- Files inside a parent `fixed` component directory cannot change.
- A fixed component's complete manifest entry and category cannot change or disappear.
- Existing components cannot change their `evolution_policy`.
- Every newly declared component must be `mutable`; a raw patch that introduces a new fixed component is rejected.
- Tool, prompt and extension entrypoints must remain under `tools/`, `prompts/` and `extensions/` respectively.
- One component directory belongs to one manifest component.
- All Python files must decode as UTF-8 and compile before plugin factories are imported.
- The candidate must assemble successfully through the real `registry.build_harness()` path.

Temporary staging exists because Python imports and current factories require filesystem paths. Its lifetime must cover any runtime behavior that reads files through `PluginContext.plugins_root`.

## Checkpoint Storage

The store has this layout:

```text
<checkpoint_store>/
  checkpoint.json
  .git/
  .harness-store/versions.jsonl
  .harness-store/iterations.jsonl
  plugins/
```

Only `plugins/` is committed. `checkpoint.json` records a stable store ID and initialization provenance. `versions.jsonl` maps stable IDs such as `harness_v0002` to commit hashes, parent versions, content digests, change summaries and evaluation summaries. Git automatic line-ending conversion is disabled locally so a resolved commit has the same bytes and digest as the validated workspace.

## Iteration Journal

`iterations.jsonl` is an append-only UTF-8 event journal for candidate attempts. It complements Git rather than replacing it: Git stores accepted Harness trees, while the journal stores work that may still be pending or may eventually be rejected.

One iteration begins with `started`, followed by zero or more complete `patch_applied` events. Validation adds `validation_completed`; `accepted` and `rejected` are terminal events. Every patch event contains the complete ordered `FileEdit` list, resulting workspace revision and candidate digest. This permits deterministic replay without persisting a candidate directory.

Use the managed session API whenever an attempt must survive process termination:

```python
session = store.start_iteration(metadata={"experiment": "teacher-v1"})
session.apply_patch(edits)
report = session.validate(env_file=Path(".env"))

# In a later process:
store = HarnessVersionStore(Path("harness_checkpoints/search_actor"))
session = store.resume_iteration(iteration_id)
accepted = session.accept(
    summary="Add result reflection hook",
    evaluation={"accuracy": 0.62},
    env_file=Path(".env"),
)
```

`IterationSession.add_extension()` converts the high-level operation into its exact resulting text-file patch before journaling. Workspace mutation and durable journal append share one transaction boundary: if the journal cannot be flushed, the in-memory mutation is rolled back.

`session.reject(reason, evaluation=...)` preserves a failed attempt without creating a Git version. `list_iterations()` derives the status, parent, patch count, candidate digest and accepted version or rejection reason from the event stream.

`open_workspace()` remains available for short-lived programmatic candidates, but direct workspaces are not resumable. A pending iteration can only be recovered when mutations were made through its `IterationSession` methods. Current journal handling is single-process and assumes one writer.

Typical API flow:

```python
from pathlib import Path
from search_harness.versioning import HarnessVersionStore

store = HarnessVersionStore(Path("harness_checkpoints/search_actor"))
baseline = store.initialize(
    Path("harness_templates/actor/baseline/plugins"),
    env_file=Path(".env"),
    checkpoint_store_id="search_actor",
)
session = store.start_iteration()
session.add_extension(instance_id="new_policy", files={"plugin.py": source})
report = session.validate(env_file=Path(".env"))
accepted = session.accept(summary="Add new policy", env_file=Path(".env"))
```

The same initialization is available through the reusable CLI:

```powershell
D:\ProgramData\miniconda3\envs\env_search_harness\python.exe `
  -m search_harness.versioning init `
  --template-root harness_templates\actor\baseline\plugins `
  --checkpoint-store harness_checkpoints\search_actor `
  --checkpoint-store-id search_actor `
  --env-file .env
```

Initialization validates the template through the real registry, creates the first
accepted version as `harness_v0001`, and records the absolute template path and digest
in `checkpoint.json`. It refuses to overwrite an initialized checkpoint store.

For rollout, call `resolve(version_id)` and keep `with store.stage(snapshot) as plugins_root:` active while building and running components that may access plugin files.

The dataset runner exposes the same staging boundary through CLI. Use
`--checkpoint-store` with either `--harness-version` or `--iteration-id`.
When an iteration is selected, the runner reconstructs it from the journal,
validates its exact current digest, and keeps the temporary plugins root alive
for the complete rollout batch. Each JSONL record includes the Harness source,
version or iteration identity, and content digest.

```powershell
# Run a pending candidate without accepting it.
D:\ProgramData\miniconda3\envs\env_search_harness\python.exe `
  -m search_harness.runners.run_dataset `
  --checkpoint-store harness_checkpoints\search_actor `
  --iteration-id <iteration_id> `
  --limit 20 `
  --model-role student `
  --output-file runs\components\actor\candidate_20\rollout.jsonl

# Run an accepted version. Omit --harness-version to select the latest one.
D:\ProgramData\miniconda3\envs\env_search_harness\python.exe `
  -m search_harness.runners.run_dataset `
  --checkpoint-store harness_checkpoints\search_actor `
  --harness-version harness_v0001 `
  --limit 20 `
  --model-role student `
  --output-file runs\components\actor\harness_v0001_20\rollout.jsonl
```

## Evolution Viewer

The read-only visualizer can expose one checkpoint store alongside component runs:

```powershell
D:\ProgramData\miniconda3\envs\env_search_harness\python.exe `
  -m search_harness.visualizer `
  --actor-runs-dir runs\components\actor `
  --evaluation-runs-dir runs\components `
  --checkpoint-store harness_checkpoints\search_actor
```

Open `http://127.0.0.1:8765/harness.html`. `Evolution` mode keeps the journal view: the left column lists iterations, the center renders ordered events, and the right column lists accepted versions and selected metadata. `Topology` mode assembles the selected accepted snapshot through the real registry and projects its prompt, tools, enabled extensions, hook execution order, lifecycle phases, state permissions and model profiles. Selecting a component or hook opens its detailed contract in the right column. Both projections are read-only, and each column scrolls independently.
