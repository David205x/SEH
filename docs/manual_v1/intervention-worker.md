# Standalone Intervention Worker 与 Coordinator

## 当前边界

`search_harness.adapter.intervention` 实现单方案、单案例、单分支的
Intervention MVP。它从已有 Actor rollout 的结构化上下文创建 context fork，
在指定 Hook phase 由教师 Worker 临时修改学生 Actor 的上下文或 active stage，
最后比较原轨迹与新分支并生成总结。

当前模块提供独立 Worker runtime、`run_intervention_worker` DefinedTool 和有界
Coordinator。它尚未注册为 `search_harness.adapter` 的独立 CLI 子命令，但已经作为
failure Critic 与 Compiler 之间的必经阶段接入 Evolution Runner。Worker 和 Coordinator
本身只创建临时分支与证据 artifact，不直接修改 plugins、manifest 或 Harness Checkpoint
Store；只有后续 Compiler 才能提交候选事务。

## Prefix 语义

一个 prefix 由以下四项定位：

```text
rollout_file + example_id + step + phase
```

边界是 inclusive。重建结果是 `ModelInput.messages` 形式的模型可见上下文，不是
trace event 列表。Hook 审计、parser 记录、token usage 和未进入模型输入的 native
reasoning 不会暴露给学生；如果 Hook 修改过 `stage.model_input`，保留的是最终发送给
模型的消息。

边界按 lifecycle 语义解释，而不是机械截断事件数组。例如 `post_tool` 保留当前步的
模型输出、工具调用和完整工具结果，即学生从已经看到该 observation 的位置继续。
Worker 仍可通过只读工具查看保留的完整 source trace 和当前 branch trace。

## Worker Hook Bridge

调用方提供一个从 Hook phase 到行为指导的映射。phase 只需属于当前 core 的
`HookPhase.ALL`；Intervention 模块不设置推荐时机黑名单。工具说明会提示直接修改
模型输出、parser 结果或工具结果可能造成错误归因。当前稳定工具面允许 Worker 改写
模型上下文，并在 `pre_final` 明确接受或推迟候选答案；所有 action 和 Hook
before/after 都会被完整记录。

每次 Hook 激活时，Worker 可以重复调用 `inspect_actor_context`，随后必须调用一个
terminal tool：

- `append_context_message`
- `replace_model_input`
- `defer_final_answer`
- `accept_final_answer`
- `continue_without_change`

`replace_model_input` 只接收 `system_instruction` 和可选的 `user_instruction`。工具内部
自动保留当前非 system 消息和工具证据、替换 system 消息，并按需追加 user 消息。
`defer_final_answer` 与 `accept_final_answer` 也只接收普通文本字段，内部再组装
`FinalDecision`。Worker 不需要在工具参数中手写消息数组或嵌套 JSON。

terminal tool 执行后立即结束当前 Hook 激活并把控制权还给 Actor。一个 Worker 在同一
分支的多次激活之间保留自己的消息上下文，因此可以联动多个 Hook；它不能创建新的
Worker、修改 checkpoint 或递归运行 Actor loop。

## 独立调用

真实模型默认分别从 `STUDENT_*` 和 `TEACHER_*` 加载；教师 Worker 可用
`INTERVENTION_REQUEST_TIMEOUT` 覆盖通用请求超时。也可以向 runtime 注入任意实现
`ModelClient` 的测试或实验模型：

```python
from pathlib import Path

from search_harness.adapter.intervention import (
    InterventionRunner,
    InterventionRuntimeConfig,
    RunInterventionWorkerTool,
)

runner = InterventionRunner(
    InterventionRuntimeConfig(
        env_file=Path(".env"),
        plugins_root=Path("harness_templates/actor/baseline/plugins"),
    )
)
tool = RunInterventionWorkerTool(runner)
result = tool.run(
    {
        "rollout_file": "runs/components/actor/example/rollout.jsonl",
        "example_id": "example-id",
        "fork_step": 1,
        "fork_phase": "post_tool",
        "intent": "Test whether explicit evidence-gap planning improves continuation.",
        "hook_guidance": {
            "post_tool": "Inspect evidence coverage and guide the next action.",
            "pre_final": "Check whether the candidate follows the retrieved evidence.",
        },
    }
)
```

每次调用在 `runs/components/intervention/<timestamp>/intervention.json` 保存 source
provenance、重建 prefix、Hook 修改、完整 branch run、静态答案比较、Worker trace 和
最终总结。Worker 执行及总结输入不包含 golden answer；确定性 HotpotQA evaluator 在
分支结束后独立使用 reference answer 评分。

## 独立 Coordinator

`InterventionCoordinatorRunner` 的正式链路绑定一个 Critic `problem_direction`，由
Coordinator 而不是 Critic 提出和试验具体 Hook/context 方案。可通过 `critic_log +
direction_index` 建立可审计绑定；独立测试也可直接传入 problem direction。会话可以将
一次运行绑定到 `rollout_file + example_id`，也可以绑定 evaluation report 作为失败样本池。report 模式
从 `per_example.jsonl` 选择 stable failure 和 unstable 案例，并可从 `summary.json.source_file`
自动解析源 rollout。`unresolved` 和仅静态 exact match 未通过但 Teacher 判为正确的案例
不会进入失败池。

Coordinator 只能通过以下固定工具观察、选择和试验：

- `list_failed_cases(page=1, page_size=20)`：分页读取失败样本，返回总条数与总页数；
- `select_failed_case(example_id)`：返回指定逻辑问题的稳定性概要和 replicate 目录；
- `sample_failed_case(seed)`：以局部确定性 RNG 随机选择案例，相同 pool 与 seed 可复现；
- `inspect_intervention_case(example_id, replicate_id, detail="summary")`：读取一条明确
  replicate 的精简时间线；仅在必要时读取完整源 Actor run；
- `run_worker_trial(example_id, replicate_id, ...)`：在一条明确 trajectory 上创建独立分支。

`inspect_intervention_case` 的 `prefix_timeline` 按实际 trace 顺序列出可重建的模型上下文
边界，并为当前 replicate 从 1 开始编号。每项同时包含状态摘要和底层 `step`、`phase`、
`event_index`，但 Coordinator 调用 `run_worker_trial` 时只提交 `prefix_id`。工具内部将
序号解析为精确边界；切换案例或 replicate 后序号重新生成，不能跨轨迹复用。trial 账本同时保存
请求的 `prefix_id` 和 `resolved_boundary`，保证审计与复现。

当前目录仅收录 `post_prompt`、`post_model`、`post_parse`、`pre_tool`、`post_tool` 和
`pre_final` 中实际存在的事件。`pre_prompt` 与 `on_error` 仍可注册 Hook，但没有稳定的
模型上下文重建契约，因此不作为可选 prefix。`run_worker_trial` 使用平行的
`hook_phases: list[str]` 与
`hook_instructions: list[str]`，工具内部校验数量、phase 和重复项，再组装 Worker 所需的
`hook_guidance`。每次调用都创建独立 Worker，不会继承上一个 trial 的私有消息历史；
trial 会记录 `example_id + replicate_id`，因此同一 Coordinator 会话可以在多个失败案例上
测试方案。Coordinator 只通过返回的 comparison、Worker summary、action 和 artifact
路径比较方案。
返回给 Coordinator 的 action 会移除完整 model-input before/after，只保留
scope、phase、action kind、简短 payload 与 reason；完整审计仍在 Worker artifact 中。

Coordinator 受 `max_trials` 和自身 `max_steps` 双重限制，最终结果只有
`analysis`、`verdict`、`selected_trial_id` 和 `recommendation`。verdict 为
`supported/rejected/inconclusive`；supported 必须引用本次账本中真实存在且完成的 trial。
Coordinator 看不到 golden answer。Evolution 模式会对静态 `needs_teacher` 分支调用独立
Teacher Judge，只向 Coordinator 暴露最终 0/1 与错误状态。一次成功只支持案例级机制
发现，不代表可以直接固化。
绑定失败池时，默认策略先用一个案例发现机制，再在至少两个不同且相关的失败案例上
复验同一机制；不足三个案例的证据只能作为待继续验证的候选。默认运行预算为 10 个
Worker trial 和 40 个 Coordinator step。

Coordinator 的 `recommendation` 是交给 Compiler 的证据接口。`supported` 结论必须说明
Hook phase 与触发条件、读取的通用状态、确定性规则或 Hook-model prompt/profile/schema、
上下文修改、跨阶段状态、fallback、重置与终止条件；不能把案例实体、答案或手写下一跳
query 固化为 Harness。固定的 `compilation_readiness_guard` 在 `PRE_FINAL` 校验可确定边界：
格式不符合 Coordinator JSON schema 时先 defer 并给模型精确反馈；失败池模式至少要有两个
不同案例的正向结果，且至少两个不同案例必须原样复用同一组非空通用 Hook guidance；若每个
案例依赖不同的手写指导，只能视为 case-level 发现。若本次会话由 Compiler clarification 触发，
还必须新增至少一个直接针对反馈的正向 trial，否则只能继续试验或返回 `inconclusive`。

修订调用通过 `previous_intervention_log + compiler_feedback` 继承旧账本。旧 trial 只读保留，
本次 `max_trials` 是额外预算，新 trial ID 从旧账本末尾继续编号。完整 artifact 的
`revision_source` 记录上一日志、Compiler 反馈、继承与新增 trial 数，Compiler 读取合并后的
完整账本。

```python
from pathlib import Path

from search_harness.adapter.intervention import (
    InterventionCoordinatorConfig,
    InterventionCoordinatorRunner,
)

runner = InterventionCoordinatorRunner(
    InterventionCoordinatorConfig(max_trials=10, max_steps=40)
)
artifact = runner.run(
    rollout_file=Path("runs/components/actor/example/rollout.jsonl"),
    example_id="example-id",
)
```

失败池模式无需预先指定案例；如果 evaluation `summary.json` 已记录 source rollout，也可
省略 `rollout_file`：

```python
artifact = runner.run(
    report_dir=Path(
        "runs/components/actor/candidate_84f16d34_100/evaluation"
    )
)
```

Coordinator plugins 位于
`harness_templates/adapter/intervention_coordinator/baseline/plugins/`，完整日志写入
`runs/components/intervention_coordinator/<timestamp>/coordinator.json`。日志包含
Coordinator core trace、结果和 trial ledger；每个 trial 的完整 Worker 轨迹仍由对应
`intervention.json` 独立保存。即使 Coordinator 达到步数上限或结果解析失败，也会先保存
`run`、trial ledger 与 `result_error`，再向调用方抛错。
