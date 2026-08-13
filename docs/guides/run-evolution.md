# 运行 Evolution Experiment

## 1. 初始化 Version Store

只需对一个新 Store 执行一次：

```powershell
python -m search_harness version-store init `
  --template-root harness_templates/student/baseline `
  --version-store harness_checkpoints/search_student `
  --env-file .env `
  --summary "Initialize Student template"
```

该命令校验模板并创建 `harness_v0001`。如果目录已初始化，不要再次 init。

## 2. 启动一个有界 Run

```powershell
python -m search_harness evolve start `
  --run-dir runs/evolution/example_run `
  --version-store harness_checkpoints/search_student `
  --dataset-path path\to\supported.jsonl `
  --limit 20 `
  --env-file .env
```

启动前在 `config/runtime.yaml` 的 `evolution.control` 与 `evolution.effects` 中设置
Generation、Trial、重试、并发和重复 Rollout 等超参数。创建 Run 时这些值会冻结到
`run.json`。首次工程验证建议先用小 `--limit` 和一代预算确认协议与服务稳定；真实
效果实验再增加样本和预算，不要改 Teacher prompt 或产物来强制推进。

`trial_batch_size` 控制一次 Evidence Review 前最多处理多少个 Trial Assignment，
必须为正数且不大于 `max_trials_per_hypothesis`。实际批次还会受剩余 Trial 与
Assignment 预算限制。批次中的 Intervention Trial 由 `rollout_workers` 限制并发，
随后各 Trial Reviewer 由 `judge_workers` 限制并发；两层均按原始输入顺序聚合，
批次完成前不会提前触发 Evidence Reviewer。

## 3. 观察与恢复

Run 目录中的 `run.json`、`experience_set.jsonl`、`events.jsonl` 和 `artifacts/` 必须整体保留。进程中断后运行：

```powershell
python -m search_harness evolve resume runs/evolution/example_run --env-file .env
```

## 复用已有 Incumbent Evaluation

当多个未完成的实验使用相同 Accepted Template Version 与 Evolution Set 时，可以从
一个已有 Run 的完整 Incumbent Evaluation 创建新的标准 Run，避免重复执行基线
rollout 与判分：

```powershell
python -m experiments.clone_run_from_incumbent `
  runs/evolution/source_run `
  runs/evolution/new_debug_run
python -m search_harness evolve resume `
  --env-file .env `
  runs/evolution/new_debug_run
```

脚本只接受 schema v2 Run，并要求源基线仍是对应 Template Version Store 的最新
Accepted Version。它以完整 Work 为单位复制 Evolution Set 与 Incumbent Evaluation
目录，并在新 Run 的 `version_store/` 中复制 Accepted Version 历史和当前模板。新
Version Store 使用独立身份，且不继承未接受的 Candidate Attempt；后续 Candidate
修改、拒绝与晋升不会影响源 Run。脚本生成新的 Run/Work 身份，然后通过正式
Controller transition 排队 `analyze_failure`，不会复制 Failure Analyst 及其下游
产物。原 evaluation 的 token 指标保留在 artifact 和复用 provenance 中，但因新
Run 没有重新调用模型，其 Control 预算记账为 0。目标目录必须不存在，源 Run 不会
被修改。

Controller 会重建 agenda，复用完整 effect artifact，并从未完成的工作继续。不要手动删除单个失败 work artifact 或拼接多个 Run。

## 调试研究链路

要只调试 Failure Analyst 到 Mechanism Distiller 之前的正式路由，先按上节创建复用
Incumbent Evaluation 的独立 Run，再执行：

```powershell
python -m experiments.run_research_slice `
  --run-dir runs/evolution/research_debug `
  --stop-before distill_mechanism `
  --env-file .env
```

该入口仍由正式 Evolution Controller 执行 Failure Analyst、Hypothesis Researcher、
Trial Selection、Intervention Executor、Trial Reviewer 与 Evidence Reviewer。只有当正式
transition 已排队 `distill_mechanism` 时才返回；该 WorkItem 保持 queued，Journal 不写入
人工 `run_paused` 或伪造的完成事件。检查完研究产物后，可直接使用普通 `evolve resume`
继续完整 Run。

若需要把 Mechanism Distiller 也纳入调试、但不执行 Mechanism Compiler，改用
`--stop-before compile_candidate`。Distiller 返回 `needs_evidence` 时仍会按正式路由回到
Trial Selection，只有真正排队 Compiler 后入口才停止。

## 4. 解释终态

`completed` 可能表示候选已接受，也可能表示证据不可蒸馏、预算耗尽或候选被拒。以 CLI reason、最后的 ControlEvent、Candidate Attempt 状态和 Version Store 最新版本共同判断；不能只看进程退出成功。
