# Offline Evaluation

## Scope

`search_harness.evaluation` is outside the Actor Harness and plugin root. It reads completed Runner JSONL records and writes reports; plugins cannot alter its scoring implementation.

The first task implementation is `HotpotQAEvaluator`, but the generic `TaskEvaluator` protocol separates task-specific static checking and teacher-judge prompt construction from report generation, execution metrics, token aggregation, and report visualization.

## Two-Layer Answer Scoring

Each item receives a deterministic static decision first:

- `pass`: normalized exact match; final score is `1`;
- `needs_teacher`: the answer is non-empty but not an exact match, so semantic judging is required;
- `automatic_zero`: no usable predicted answer; final score is `0`;
- `unresolved`: no usable golden answer or a Teacher failure.

With `--teacher-judge`, only `needs_teacher` items are sent to the `TEACHER_*` model. The judge sees question, golden answer, and predicted answer only, and must return `{"score": 0}` or `{"score": 1}`. It does not receive actor traces, tool observations, or Harness configuration. API or parsing failures remain unresolved rather than being silently converted to `0`.

Teacher judging uses bounded ordered concurrency. Static decisions remain sequential and cheap;
only `needs_teacher` cases enter the worker pool. Every worker owns an independent Teacher
model client, while report items retain source order. `--judge-workers` defaults to `8`; lower
it when the provider rate limit is restrictive. The selected value is stored in
`summary.json` under `evaluation_config`.

## Run

Actor dataset rollout 支持每个逻辑问题执行 N 次独立采样：

```powershell
python -m search_harness.runners.run_dataset `
  --limit 20 `
  --rollouts-per-example 3 `
  --rollout-workers 6
```

Experience Set 仍然一题一条。Runner 将每题展开为 `r000..rNNN`，并以
`<ROLE>_SEED + replicate_index` 派生实际采样 seed。主 Actor 与 Hook 内同 profile
模型共享该 replicate seed。rollout JSONL 以 `(example_id, replicate_id)` 为唯一键，
保持数据集顺序，并在每题内部保持 replicate 顺序。

```powershell
& 'D:\ProgramData\miniconda3\envs\env_search_harness\python.exe' `
  -m search_harness.evaluation.run_evaluation `
  runs\components\actor\student_init_hard_20\rollout.jsonl `
  --output-dir runs\components\actor\student_init_hard_20\evaluation `
  --teacher-judge `
  --judge-workers 8
```

Omit `--teacher-judge` for a static-only smoke test. Non-exact non-empty answers will then remain `unresolved`.

省略 `--output-dir` 时，位于 `runs/components/actor/<run_id>/` 的 rollout 会写入同一 run 的 `evaluation/`；其他来源会创建新的 `runs/components/evaluator/<timestamp>/evaluation/`。

## Report Layout

```text
runs/components/actor/<run_id>/evaluation/
  summary.json
  summary.md
  per_example.jsonl
  per_rollout.jsonl
```

`per_rollout.jsonl` retains every static/Teacher decision and trace-derived execution metric.
`per_example.jsonl` contains one aggregate record per logical question, including replicate
directory, success rate, score standard deviation, answer consistency and
`stable_correct/stable_failure/unstable/unresolved` classification. It does not contain full
Actor traces. `summary.json` keeps rollout-level accuracy and adds stable-correct,
stable-failure, unstable, majority-correct, pass@n and mean per-example success-rate metrics.

`example_id` is the problem-level cross-run join key. `replicate_id` identifies one concrete
trajectory beneath it. Duplicate `example_id` values are expected in rollout JSONL; duplicate
`(example_id, replicate_id)` pairs fail fast. Cross-Harness trajectory comparisons require the
same composite identities and sampling seeds. If a dataset record has no ID, the loader derives
the same `question_sha256:<digest>` value from its normalized question.

`model_output` and `hook_model_output` trace metadata preserve provider `usage` when available. The evaluator sums OpenAI-style `prompt_tokens`/`completion_tokens` or Ollama-style `prompt_eval_count`/`eval_count`. `input_tokens`、`output_tokens` 与 `total_tokens` 表示整体消耗，`actor_*` 与 `hook_*` 字段分别标出主 Actor 和 Hook 内小模型的消耗；缺失 usage 时对应值保持 `null`，并由 `coverage_rate` 明确数据覆盖率。

## Visual Inspection

Start the viewer with both roots:

```powershell
& 'D:\ProgramData\miniconda3\envs\env_search_harness\python.exe' `
  -m search_harness.visualizer `
  --actor-runs-dir runs\components\actor `
  --evaluation-runs-dir runs\components
```

Open `http://127.0.0.1:8765/evaluation.html`. The page lists reports, exposes the full metrics dictionary, and shows each item’s static decision, Teacher result, score source, and execution data.
