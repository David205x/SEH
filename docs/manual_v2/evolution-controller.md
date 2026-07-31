# Evolution Controller

## 当前状态

`search_harness.evolution.control` 是 v2 九角色的正式闭环入口。它与旧版
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
| `effects.py` | 九角色、rollout/evaluation 和 Version Store 的本地实现。 |
| `cli.py` | 新建和恢复运行。 |

设计理由和协议字段见
[Evolution Controller v2 设计](../design/evolution-controller-v2.md)。

## 主运行流程与角色激活

主路径为：

```text
评估 incumbent
→ Failure Analyst
→ Hypothesis Researcher
→ 选择 prefix
→ Intervention Worker
→ Trial Reviewer
→ Evidence Reviewer
→ Mechanism Distiller
→ Compiler
→ 导入并验证 candidate
→ 对 intervention examples 执行 Mechanism Conformance Replay
→ 评估 candidate
→ Candidate Reviewer
→ 接受、拒绝或返回指定层修订
```

其中评估、prefix 选择、候选导入验证和版本接受/拒绝是确定性 Controller
effect，不是模型角色。

| 角色 | 激活时机 | 主要去向 |
| --- | --- | --- |
| Failure Analyst | 每代 incumbent 评估完成后 | 生成失败方向，进入 Hypothesis Researcher。 |
| Hypothesis Researcher | 首次失败分析后；或 Worker 判定假设不受支持、Evidence Reviewer 要求修订/拒绝时 | 形成或修订假设，进入 prefix 选择。 |
| Intervention Worker | Controller 选出符合假设 phase 的 rollout prefix 后 | 执行 trial；assignment 不合适时重选 prefix，假设不受支持时返回 Researcher。 |
| Trial Reviewer | 每条 trial 成功执行后 | 独立审阅该 trial，再交给 Evidence Reviewer 聚合。已有审阅在追加 trial 时复用。 |
| Evidence Reviewer | 当前假设的 trial 均完成局部审阅后 | `continue` 追加 trial；`revise/reject` 返回 Researcher；`ready_to_distill` 进入 Distiller。 |
| Mechanism Distiller | Evidence Reviewer 判定证据可蒸馏后；或 Compiler/Candidate Reviewer 要求机制层修订时 | `needs_evidence` 返回 trial；`distilled` 进入 Compiler；`not_distillable` 结束本代研究。 |
| Compiler | 机制蒸馏完成后；或候选校验、Conformance Replay、Candidate Reviewer 要求实现层修订时 | 提交候选；若能力不足则返回 Distiller。 |
| Conformance Reviewer | Candidate 通过静态校验后，对每个 intervention example 的每条完整 replay 独立调用 | 程序聚合后通过则进入全量评估；不通过则携带脱敏义务返回 Compiler。 |
| Candidate Reviewer | 候选通过 conformance 并完成与 incumbent 的对照评估后 | 建议接受、拒绝，或返回 evidence/mechanism/implementation 层修订；接受仍须通过确定性 promotion gate。 |

实现上，Trial Reviewer 与 Evidence Reviewer 共用一个 `review_evidence`
WorkItem：Controller 先为尚未审阅的 trial 运行 Trial Reviewer，再运行
Evidence Reviewer。Intervention Worker 使用专用 `InterventionRoleRuntime`；
其他八个角色使用通用 `NativeChatTeacherRuntime`。

incumbent/candidate rollout 与 HotpotQA evaluation 复用现有
`LocalEvolutionBackend`。候选评审后，Controller 通过
`HarnessVersionStore.IterationSession` 完成 accept/reject；接受后若仍有
generation 预算，则以新版本重新开始 incumbent 评估。

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
| `--min-accuracy-delta` | `-0.02` | 确定性安全门禁允许的最大 accuracy 回撤；效果是否值得接受仍由 Reviewer 判断。 |
| `--max-total-token-ratio` | `3.0` | candidate/incumbent 总 token 最大比例。 |
| `--max-total-tokens` | 未限制 | 整个 Controller run 的 effect token 预算。 |
| `--candidate-error-streak-limit` | `3` | candidate 连续出现同一 runner error 时提前结束 rollout 批次。 |

Candidate promotion 使用双层 gate。确定性安全门禁必须通过，同时 Candidate
Reviewer 的效果判断必须建议 `accept`，Controller 才会执行 promotion。

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

Promotion 由两个职责不同的 gate 共同决定：

1. **确定性安全门禁**：Version Store validation 必须通过；candidate 不得包含
   `runner_error`；准确率、执行状态及已配置的成本指标必须完整；
   `candidate_accuracy - incumbent_accuracy` 不得低于
   `min_accuracy_delta`；配置成本上限时 token 比例不得超限。
2. **Reviewer 效果判断门禁**：Candidate Reviewer 综合 aggregate accuracy、
   每题稳定性、机制针对的失败子集、gain/loss 代表轨迹、Harness diff 和 token
   成本，判断机制是否值得采用。Reviewer 不执行隐式的
   `accuracy_delta >= 0` 规则，正向 aggregate delta 也不能替代机制有效性证据。

两个 gate 的结果分别写入 promotion artifact。Reviewer 不能绕过安全门禁，
Controller 也不会从 Reviewer 自由文本推断额外阈值。

Version Store 的 Hook phase contract smoke 使用一段代表性的非空历史轨迹，
用于覆盖读取 `HookContext.trace` 的分支。通过该检查后，candidate rollout
仍启用连续同类 `runner_error` 熔断；熔断后保留已生成记录并继续生成 evaluation
与 Candidate Reviewer 证据，而不是消耗整个 Experience Set。

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
