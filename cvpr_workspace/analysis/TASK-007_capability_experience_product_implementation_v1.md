# TASK-007 Capability Experience Product 实施报告 v1

## 范围

本次仅重构 Capability Experience Product。Direction Experience、经验合并、Settlement、持久化 Store 和 Researcher 消费不在本次实现范围内。

## 最终协议

Summarizer 只提交语义判断：

```text
CapabilityExperienceProposal
- observed_limitation: str
- evidence_refs: list[int]
```

程序将 Proposal 与确定性来源信息组装为最终产品：

```text
CapabilityExperienceProductItem
- decision_scope: str
- observed_limitation: str
- evidence_summary: str
- evidence_refs: list[str]
```

其中：

- `decision_scope` 由 Source Adapter 从来源 Artifact 的冻结 predicate 原样提取，不进行重新组织，也不要求 Summarizer 复述；
- `observed_limitation` 是 Summarizer 唯一生成的经验语义，描述 Student 在哪些可观察边界上表现不可靠；
- `evidence_summary` 由程序根据 Observation 机械生成；
- `evidence_refs` 由局部 Observation 序号解析成稳定 Artifact 引用。

旧字段 `tested_decision`、`evaluated_behavior`、`conditions`、`reliance_boundary` 和 `capability_area` 均未保留兼容。

## 核心实现

1. Capability Summarizer 升级为 `capability_summarizer@2`，输出 `capability_experience_proposal@1`。
2. Hook Feasibility Adapter 改为按真实 prefix case 生成 Observation，并在默认视图中直接提供 decisive observation 和各 thinking 条件下的重复决策。
3. Conformance Adapter 改为按直接 mismatch 生成 Observation；可结合 Mechanism Artifact 展开实际 predicate 和 model-visible inputs。
4. Controller 在角色输出后确定性物化 `capability_experience.json`，运行事件携带最终 Product 而不是模型 Proposal。
5. Prompt 只要求抽取可复用的语义能力边界，禁止混入计数、模式标签、实现建议和研究策略。

## 真实 API 验证

### Hook Feasibility 来源

Artifact：`runs/experiments/20260826_capability_product_v3`

- 3/3 完成；
- 总 token：16,220；
- 三次均识别出同一边界：Student 不能可靠排除单实体问题以及 query 已覆盖双方实体的近邻负例；
- 三次输出均未再把 thinking 模式、标签计数或策略建议写入 `observed_limitation`。

### Conformance 来源

Artifact：`runs/experiments/20260826_capability_product_conformance_v2`

- 3/3 完成；
- 总 token：15,121；
- 三次均形成两项一致的能力边界：不能可靠识别 query 已包含第二实体，以及不能可靠识别第二实体已有返回证据；
- Decision Scope 已包含真实 negative rule 或完整 predicate 与 model-visible inputs，不要求消费者理解内部字段路径。

两组最终验证合计 6/6 完成，总 token 31,341。此前探索运行仅用于发现 Prompt 会混入计数和 thinking 条件的问题，不作为最终验收结果。

## 自动验证

- `python -m unittest discover -s tests/evolution -t .`：240/240 通过；
- `python -m compileall -q search_harness experiments`：通过；
- `git diff --check`：通过，仅报告工作区既有的 CRLF 提示。

## 当前边界

当前实现已经生成可独立阅读的 Capability Experience Product，但尚未实现经验合并、Settlement、长期存储或 Researcher 消费 A/B。上述能力不应由本次 API 成功率推断为已经完成。

## 2026-08-26 表述收口

- `decision_scope` 从 Adapter 重新组句改为逐字复制来源 Artifact 的冻结 predicate；
- `observed_limitation` 固定为“对象 + 不稳定语义能力 + 明确输入类别”，不再复述 predicate 或使用审查术语；
- `evidence_summary` 改为聚合程序专用的结构化 expected/observed decisions，不再逐条重复 Observation metadata；
- `runs/experiments/20260826_capability_product_v5` 真实 API 验证 3/3 得到完全一致的最终产品表述，总 token 14,954。
- `runs/experiments/20260826_capability_product_conformance_v3` 真实 API 验证 3/3 完成；每次均形成相同的两项语义边界，表述保持“明确不应触发的输入 + 具体类别”，总 token 15,510。
- 最终 evolution 回归测试 240/240 通过，`compileall` 与 `git diff --check` 通过。
