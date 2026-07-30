# Evolution Controller

## 当前状态

`search_harness.evolution.control` 是 v2 八角色的正式闭环入口。它与旧版
`search_harness.evolution.runner.EvolutionRunner` 并存；旧入口没有被删除，也
不会被新 Controller 调用。

实现模块：

| 模块 | 职责 |
| --- | --- |
| `domain.py` | WorkItem、EffectResult、事件和状态投影。 |
| `journal.py` | UTF-8 JSONL 事件日志与 effect artifact 原子写入。 |
| `policies.py` | 工作/token 预算和确定性 promotion gate。 |
| `transitions.py` | 每个 WorkKind 的局部转移与修订路由。 |
| `controller.py` | 回放、恢复、执行一个待办和提交事件。 |
| `effects.py` | 八角色、rollout/evaluation 和 Version Store 的本地实现。 |
| `cli.py` | 新建和恢复运行。 |

设计理由和协议字段见
[Evolution Controller v2 设计](../design/evolution-controller-v2.md)。

## 闭环组成

当前 Controller 使用以下八个 v2 角色：

1. Failure Analyst；
2. Hypothesis Researcher；
3. Intervention Worker；
4. Trial Reviewer；
5. Evidence Reviewer；
6. Mechanism Distiller；
7. Compiler；
8. Candidate Reviewer。

incumbent/candidate rollout 与 HotpotQA evaluation 复用现有
`LocalEvolutionBackend` 的评估实现。候选评审后，Controller 操作
`HarnessVersionStore.IterationSession` 完成 accept/reject。

Intervention Worker effect 使用专用 `InterventionRoleRuntime`：Controller
只按假设的 `fork_phase` 选择一个 inclusive prefix；`phase_plan` 中其余 phase
由同一个 Worker transcript 在该 Student 分支后续生命周期内处理。每条
executed trial 随后由独立 Trial Reviewer 读取完整轨迹；Evidence Reviewer
只聚合这些局部审阅。其他七个
Teacher 角色继续使用通用 `NativeChatTeacherRuntime`。
`continue` 新增证据时，Controller 复用已绑定当前冻结假设的 TrialReview，
只为新增 trial 启动新的局部审阅。

## 运行目录

```text
<run-dir>/
  run.json
  experience_set.jsonl
  events.jsonl
  artifacts/
    <work-id>/
      effect.json
      role.json | trial.json | mechanism.json
      report/
```

- `run.json` 冻结 checkpoint、控制配置、runtime 配置和数据集来源；
- `experience_set.jsonl` 是整个 run 固定使用的 UTF-8 Experience Set；
- `events.jsonl` 是唯一控制状态来源；
- `effect.json` 是 Controller 提交工作完成前的恢复边界；
- 角色 transcript、工具调用、trial 轨迹和评估明细保留在相应工作目录。

所有文本均以 UTF-8 读写。

## 新建运行

```powershell
& 'D:\ProgramData\miniconda3\envs\env_search_harness\python.exe' `
  -m search_harness.evolution.control run `
  --run-dir 'runs\experiments\evolution_controller_v2\example' `
  --checkpoint-store 'harness_checkpoints\search_actor' `
  --limit 20 `
  --max-generations 1 `
  --max-trials-per-hypothesis 4 `
  --max-trial-assignments 12 `
  --rollouts-per-example 1 `
  --env-file '.env'
```

未指定 `--dataset-path` 时，数据集从 `.env` 的 Dataset 配置读取。建议正式实验
使用独立 checkpoint store；Controller 通过 promotion 时会真实创建 accepted
Git version。

常用门禁：

| 参数 | 默认值 | 含义 |
| --- | ---: | --- |
| `--min-accuracy-delta` | `0.0` | candidate 相对 incumbent 的最低 accuracy 变化。 |
| `--max-total-token-ratio` | `3.0` | candidate/incumbent 总 token 最大比例。 |
| `--max-total-tokens` | 未限制 | 整个 Controller run 的 effect token 预算。 |

Candidate Reviewer 必须建议 `accept`，并且准确率和成本门禁都通过，Controller
才会执行 promotion。

## 恢复运行

```powershell
& 'D:\ProgramData\miniconda3\envs\env_search_harness\python.exe' `
  -m search_harness.evolution.control resume `
  'runs\experiments\evolution_controller_v2\example'
```

恢复默认使用 `run.json` 中冻结的 runtime 配置。只允许通过命令行覆盖
`--env-file` 和 `--no-progress`，避免无意改变实验语义。

预算耗尽或 effect 重试耗尽会写入 `run_paused`。再次执行 resume 会先写
`run_resumed`。若暂停原因是 effect 重试耗尽，显式 resume 会为最后一个失败项
再安排一次局部尝试，用于外部服务或代码已经修复的情况；再次失败仍会安全暂停。
如果原配置预算仍然阻止前进，它也会再次安全暂停。要改变冻结预算，应开始一个
新 run，而不是手工修改事件日志。

## Promotion gate

当前确定性 gate 只包含已经实际用于闭环的最小规则：

1. Candidate Reviewer recommendation 必须是 `accept`；
2. `candidate_accuracy - incumbent_accuracy` 不低于
   `min_accuracy_delta`；
3. 配置成本上限时，`candidate_total_tokens / incumbent_total_tokens`
   不高于 `max_total_token_ratio`。

Compiler validation 和 Version Store validation 都必须通过。Reviewer 不能绕过
这些规则，Controller 也不会从 Reviewer 自由文本推断额外阈值。

## 维护规则

- 新增角色结果时，先扩展对应 Pydantic 语义协议，再增加一个局部转移；
- 不让角色输出 `next_role`、版本 ID、预算或终止 run 的决定；
- Candidate Reviewer 的 `revision_target` 只选择职责层；`next_obligation`
  必须同时映射到 evidence 的下一试验义务、mechanism 的能力约束或
  implementation 的实现约束；
- 不在 Controller 主循环中加入角色专用分支；角色路由属于
  `transitions.py`；
- 大对象保存在 artifact，不复制进事件 payload；
- 新增外部副作用时必须定义“effect 已完成但事件未提交”的恢复方法；
- 未经实验需求确认，不引入通用 DAG、registry 或并行候选框架。
