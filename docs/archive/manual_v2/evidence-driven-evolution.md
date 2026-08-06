# 证据驱动的 Evolution 研究状态

Harness evolution 是受预算约束的证据搜索过程。正式 Controller 不只保存最终候选，
还保存每次失败分析、假设、trial、局部评审、聚合证据义务、蒸馏机制、实现结果和
候选评审，使一次 run 可以恢复并解释为何继续、修订、拒绝或晋升。

## 当前持久化边界

当前证据只在单个 Controller run 内持久化：

- `events.jsonl` 保存确定性工作状态、路由和恢复边界；
- `artifacts/<work-id>/` 保存角色输出、transcript、trial 轨迹、评估报告和副作用
  receipt；
- `effect.json` 使已完成的外部副作用可在 Controller 中断后复用；
- `experience_set.jsonl` 冻结本次 run 的问题集合；
- accepted candidate 由 Version Store 保存为新 Harness checkpoint。

已删除的 V1 `EvolutionResearchStore`、`IterationProduct` 和 Runner 研究日志不再是
当前实现。跨 run Experience Store 尚未实现，因此不同 run 之间不会自动检索或
继承研究经验。

## 证据流

```text
incumbent evaluation
→ failure direction
→ falsifiable hypothesis
→ intervention trial + independent trial review
→ aggregated evidence decision
→ mechanism specification
→ candidate implementation + conformance replay
→ paired candidate evaluation and review
→ deterministic promotion gate
```

模型角色贡献语义判断，Controller 维护稳定 ID、预算、工作状态、artifact 引用和
版本事务。角色不能直接决定 run 终止、版本 ID 或 candidate promotion。

## MechanismSpec 边界

Mechanism Distiller 产出的 `MechanismSpec` 是实现无关的行为规格。它记录：

- 目标、适用范围、已知限制与禁止行为；
- 各 Hook phase 的触发条件、决策输入、evaluator、动作和激活预算；
- 连续控制流、rollout-local 状态、fallback 与预期可观测信号；
- 支撑机制的已评审 trial 引用和无 Teacher Harness 所需能力。

Compiler 只能把该规格映射为最小 mutable plugin 变更。静态校验只证明候选可装配；
Mechanism Conformance Replay 检查实现是否忠实执行机制；完整 Experience Set 评估、
Candidate Reviewer 和确定性 promotion gate 共同决定是否接受。

## 当前限制

- 跨 run 经验检索、去重、置信度衰减和迁移边界尚未实现；
- 角色 continuation 只复用当前 run 内显式绑定的 transcript 和 artifact；
- 经验系统的最小记录协议将在独立设计阶段确定，不从已删除的 V1 store 自动继承。
