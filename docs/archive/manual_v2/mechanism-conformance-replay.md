# Mechanism Conformance Replay

状态：已接入 Evolution Controller。

## 目的

Mechanism Conformance Replay 位于 Candidate 静态验证之后、全量 evaluation
之前。它只回答一个问题：

> Compiler 生成的 Harness 是否忠实实现了已经由 intervention 证据支持的机制？

它不是新的性能评估集，也不使用原 intervention 案例证明机制能够泛化。

## 已确认边界

- 原始 intervention trial artifact 会随 Controller work refs 保留到 Compiler
  之后，可直接定位，不需要从 `MechanismSpec.evidence_refs` 猜测文件。
- replay 优先复用 Distiller 实际读取过的 trial，不重新选择问题。
- 原始完整轨迹只提供给彼此隔离的 Conformance Review Worker。
- Compiler 只接收不含问题、答案和原始轨迹的实现修订义务。
- 同一组 replay 案例可以在 Compiler 修订间重复使用。它们是机制回归测试，
  不是泛化测试，因此不要求每轮更换。
- 只从原问题执行完整 Candidate rollout，不执行 prefix continuation。
- 每个不同 intervention example 执行 3 个 Candidate replicate。
- MVP 暂不增加新样本 canary；是否引入应由后续实验决定。

## 推荐流程

```text
Compiler
→ Version Store validation
→ Hook smoke test
→ 对原 intervention 问题执行 Candidate 完整 rollout
→ 每条 replay 由独立 Conformance Review Worker 审阅
→ 程序聚合 findings
→ pass：进入全量 evaluation
→ implementation mismatch：回到 Compiler
→ not observed / inconclusive：回到 Compiler
```

完整 rollout 从原问题开始，可以覆盖 Hook 初始化、rollout-local 状态和早期
phase。MVP 不使用相同前缀 continuation，避免绕过 Candidate Hook 在更早
phase 的初始化，也避免维护第二种 replay 语义。

`faithful` 只表示 Candidate 在该 replicate 中忠实执行了 `MechanismSpec`：

- 轨迹到达机制 phase，且触发条件可以从声明的输入判断；
- 条件满足时执行了与 phase rule 语义一致的动作；
- 状态变化、激活次数和 fallback 符合 behavioral pseudocode；
- Actor 确实收到了该动作产生的上下文或控制结果；
- 没有使用禁止能力或案例特定内容。

答案是否正确不属于 `faithful` 判定。忠实实现但效果无益的 Candidate 应通过
conformance，随后由全量 evaluation 和 Candidate Reviewer 判断效果。

## 建议协议

```python
class ConformanceFinding:
    trial_ref: str
    candidate_run_ref: str
    verdict: str
    observed_phases: list[str]
    assessment: str
    repair_obligation: str | None
```

| 字段 | 描述 |
| --- | --- |
| `trial_ref` | 标识本次判断所对应的原 intervention trial。 |
| `candidate_run_ref` | 标识 Worker 实际审阅的 Candidate replay 轨迹。 |
| `verdict` | 表示实现忠实、实现偏差、机制偏差、未观察到触发、运行错误或证据不足。 |
| `observed_phases` | 记录 Candidate Hook 在轨迹中实际进入或修改的 phase。 |
| `assessment` | 简要说明轨迹事实与 MechanismSpec 的一致或偏离之处。 |
| `repair_obligation` | 仅在需要修订时给出不含案例内容的可检验义务。 |

建议的 `verdict` 取值：

```text
faithful
implementation_mismatch
not_observed
runtime_error
inconclusive
```

程序聚合结果：

```python
class ConformanceSummary:
    decision: str
    finding_counts: dict[str, int]
    per_example: dict[str, dict]
    compiler_feedback: list[str]
    finding_refs: list[str]
```

| 字段 | 描述 |
| --- | --- |
| `decision` | 决定进入全量评估或返回 Compiler 修订实现。 |
| `finding_counts` | 汇总每类 Worker verdict 的数量。 |
| `per_example` | 记录每题 faithful 数量、verdict 计数和是否通过。 |
| `compiler_feedback` | 提供给 Compiler 的脱敏实现修订义务。 |
| `finding_refs` | 指向独立 Worker finding，供审计而不复制原轨迹。 |

## Suite 判据

- 每个不同 intervention example 固定执行 3 个 Candidate replicate。
- 每个 example 至少出现一次 `faithful`。
- 任意 replicate 出现 `runtime_error` 或 `implementation_mismatch` 时失败。
- `not_observed` 或 `inconclusive` 不触发 prefix 诊断；当该 example 没有其他
  faithful replicate 时，携带脱敏义务返回 Compiler。
- Suite 通过后才执行全量 Candidate evaluation。
