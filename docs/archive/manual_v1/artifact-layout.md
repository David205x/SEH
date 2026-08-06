# Artifact Layout

项目根目录按“初始化定义、可恢复参数、运行产物”划分边界；运行产物再分为独立组件调试和完整实验。新代码不得重新引入按文件类型分散的 `traces/`、`reports/`、`adapter_logs/` 或 `compiler_logs/` 根目录。

```text
harness_templates/
  actor/baseline/plugins/
  adapter/critic/baseline/plugins/
  adapter/compiler/baseline/plugins/
  adapter/intervention_coordinator/baseline/plugins/
  experiments/

harness_checkpoints/
  <checkpoint_store_id>/
    checkpoint.json
    .git/
    .harness-store/
    plugins/

runs/components/
  actor/<run_id>/
    rollout.jsonl
    evaluation/
  evaluator/<run_id>/evaluation/
  critic/<run_id>/critic.json
  compiler/<run_id>/compiler.json
  intervention/<run_id>/intervention.json
  intervention_coordinator/<run_id>/coordinator.json
  probes/<run_id>/result.json

runs/experiments/
  evolution/<run_id>/
    run.json
    events.jsonl
    experience_set.jsonl
    evolution.log
    iterations/<iteration_number>/
```

## Harness Templates

`harness_templates/` 是可编辑的初始化模板和直接运行模板，不携带进化历史。Actor、Critic 和 Compiler 的 baseline 分属不同角色路径。模板可直接传给 `--plugins-root`，也可用于初始化一个新的 checkpoint store。

模板不是 checkpoint。修改模板不会改变已经初始化的 checkpoint store，也不会形成一次进化记录。

## Harness Checkpoints

`harness_checkpoints/<checkpoint_store_id>/` 保存一条 Harness 的可恢复进化链，地位类似训练系统中的模型 checkpoint。内部仍由 `HarnessVersionStore` 实现：Git 保存 accepted plugin tree，iteration journal 保存 pending 或 rejected 尝试。

`checkpoint.json` 提供稳定的 `checkpoint_store_id`、初始化模板及其 digest。rollout 记录
store ID、绝对路径、version/iteration ID 与 Harness content digest；Critic 会校验这些
Harness provenance。当前 evaluation report 只记录 source rollout 路径和共享 provenance，
尚未记录 source rollout 文件 digest，因此生成报告后不应覆盖原 rollout 文件。

## Component Runs

`runs/components/` 只存放单个组件的调试执行。每次执行拥有独立 `<run_id>`，相关文件聚合在同一目录，而不是按 artifact 类型散落。

- Actor rollout 与其 evaluation 放在同一个 Actor run 下。
- 只有 evaluation、没有本项目 Actor rollout 的输入放在 `evaluator/`。
- Critic、Compiler 与 probe 各自拥有独立 run 目录。
- 独立 Intervention Worker 与 Coordinator 分别写入 `intervention/` 和
  `intervention_coordinator/`；Evolution 内调用则写入对应 iteration 子目录。

默认 `<run_id>` 使用 UTC 时间戳；可通过显式输出路径赋予有意义的实验名称。

`runs/` 和本地 `.env` 都是运行期内容，不应作为框架源码提交。若需要保留可复现实验样例，
应先脱敏并缩减为专门 fixture，而不是直接提交完整运行目录。

## Experiment Runs

`runs/experiments/` 保存完整闭环实验。一次 Evolution run 必须包含自己的配置、Experience Set、事件日志、可读日志和每轮全部中间产物。它引用 checkpoint store，但不复制其 accepted Git 历史。

因此两者职责不同：`runs/experiments/` 类似训练日志，回答“这次实验如何执行”；`harness_checkpoints/` 类似模型参数，回答“当前可恢复 Harness 是什么”。

可视化服务的 `/experiment.html` 直接读取 `runs/experiments/`。它按 run 和 iteration 聚合 Runner event，并可在同页逐条读取 incumbent/candidate Actor rollout、evaluation、failure Critic、Compiler、candidate review 与 decision。读取边界始终限制在选中的 experiment run 内。
