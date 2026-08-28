# TASK-007 Capability Experience Product 最小协议实施计划 v19

> 实施状态：用户已批准执行。本轮只修改 Capability，不修改 Direction、Settlement、Researcher consumer 或正式 Evolution 路由。

## 当前状态

- 当前 `capability_summarizer@1` 输出 `evaluated_behavior`、`observed_limitation`、`conditions` 和局部 Observation refs；真实 API 结果容易退化为三值标签与阶段摘要。
- Hook Feasibility Artifact 已保存冻结 decision contract、逐 case `decisive_observation`、expected label、thinking mode、repetition 和 raw output，但当前 Packet 默认视图只聚合 case ID/label，把决定性语义放在未读取的 Detail 中。
- 当前 Capability side work 只保存 Role Artifact，尚无程序组装的 Capability Experience Product Artifact。
- Direction 实现和协议不进入本轮修改。
- 用户已确认最小产品：Summarizer 只生成 `observed_limitation + evidence_refs`；程序提供 `decision_scope`、`evidence_summary` 和稳定 Evidence refs；不保留旧字段兼容。

## 任务意图

本任务把 Capability 输出从“模型复述被测试操作与运行条件”改成“模型只归纳具体语义限制，程序补齐稳定判定范围和证据概况”，使产物能够直接说明 Student/Hook model 不能稳定完成什么语义区分，同时不替 Hypothesis Researcher 选择解决方案。

本任务服务 Goal H3：

> “将已结算轨迹中的 typed verification verdict 与终态转为有 provenance、严格 consumer/scope、可失效和可复查的 role-scoped experience，能够减少跨 attempt/generation 的能力越界、同角色错误复发和方向重走，并提高单位总预算的 useful Candidate yield，同时控制 false pruning 与 held-out utility。”

本轮只建立 Capability Product 的开发期协议与 Artifact，不验证 H3 consumer 效果。

相关 H1/H2 语义保持不变：

> H1：“在持久化 Candidate 物化前，冻结真实 Student Prefix 上的 matched no-op 与不可部署 soft intervention 证据能够预测 downstream Candidate effect，并在预算匹配下提高 useful Candidate yield、减少无效完整评估。”

> H2A：“对 Student-owned recognition、decision、adherence、fallback 与 parse responsibility 的独立 probe 能够预测未参与 probe 的真实 Prefix 上的 shadow/in-loop realizability。”

> H2B：“基于逐职责 realizability 证据在 reject、simplify、deterministic lowering 与 ownership reassignment 之间进行 adaptive routing，相对固定 ownership 策略能够提高可实现且有用的 Candidate 产出并减少浪费。”

## 实施思路

Capability Source Adapter 把一个直接模型行为来源拆成带稳定 Decision Scope 的语义 Observation。Hook Feasibility 每个 mismatch/flip case 成为独立 Observation，默认视图直接包含 `decisive_observation` 原文和逐 condition raw labels；Conformance 直接 mismatch 同样保留 decisive input。

Summarizer 不再生成被测任务名称、Capability 分类、条件摘要或研究建议，只提交一条或多条 `observed_limitation` 并选择直接支持它们的 Observation refs。程序要求同一 Proposal 引用的 Observation 共享一个 Decision Scope，然后确定性组装最终产品：

```python
class CapabilityExperienceProductItem:
    decision_scope: str
    observed_limitation: str
    evidence_summary: str
    evidence_refs: list[str]
```

- `decision_scope`：Source Adapter 从冻结 phase、decision inputs、predicate 和 label rules 组装的自足判定范围。
- `observed_limitation`：Summarizer 归纳的具体语义误判或不稳定边界。
- `evidence_summary`：程序根据被引用 Observation 的 conditions、Evidence Structure 和实际结果形成的机械概况。
- `evidence_refs`：程序把局部 Observation refs 解析成来源 Artifact/Case 的稳定引用。

最终 side work 同时保存原始 Role Artifact 和程序组装的 `capability_experience.json`；Effect outcome 使用最终 Product，不再把模型 Proposal 伪装成完成的 Experience。

## 计划实现

### Contract 与 Role

- 修改 `search_harness/evolution/research/roles/contracts.py`：
  - 增加 Capability 专用 Observation 的 `decision_scope`；
  - 删除 `CapabilityDraft`/`CapabilitySummary`；
  - 增加只含 `observed_limitation`、`evidence_refs` 的 Proposal/Summary；
  - 增加程序组装的 Capability Experience Product 类型；
  - 将角色更新为 `capability_summarizer@2`、`capability_experience_proposal@1`。
- 更新 `harness_templates/teacher/capability_summarizer/` 的 Manifest 与 Prompt，删除 `evaluated_behavior`、模型输出 `conditions` 和旧 Draft 表述。
- 更新 Role execution/resource validation 的类型分支，不保留旧 Capability contract 解析。

### Packet 与 Product Assembly

- 修改 `search_harness/evolution/research/experience_summary.py`：
  - Hook Feasibility 按 case 生成语义 Observation；
  - 默认视图直接包含 Artifact 的 decisive observation 与 repeated raw decisions；
  - 从冻结 contract 确定性生成 self-contained Decision Scope；
  - Conformance mismatch 提供对应 Decision Scope 与 decisive input；
  - 校验一条 Proposal 的 refs 只能绑定一个 Decision Scope；
  - 生成机械 Evidence Summary 与稳定来源 refs；
  - 增加 `materialize_capability_experience_product()`。
- 修改 `research_role_effects.py`：写入 `role.json` 与 `capability_experience.json`，Effect refs 改为 `capability_summarizer_artifact` 和 `capability_experience_artifact`。

### 文档与术语

- 更新 `CONTEXT.md` 中 Student Capability Experience Draft 与 Evaluated Behavior 定义，使用程序提供的 Decision Scope 和模型生成的 Observed Limitation。
- 更新 `docs/architecture/evolution.md`、`docs/reference/role-contracts.md`、`docs/reference/artifact-schemas.md`、`docs/design/experience-summarizer-redesign.md` 和 v2 产品草案的 Capability 部分。
- 历史 API 译注与实施报告保持历史事实，不改写其旧输出。

### 验证

- 更新 Capability contract、Source Adapter、Product assembly、Role loader/execution 与 Controller effect 的定向测试。
- 修复两项已经确认的 Hook Feasibility v16 测试回归，使受影响 Evolution 测试恢复通过。
- 使用 `20260815_qwen3-8b_hook_feasibility` 的真实 Probe Artifact 运行 Capability Summarizer 三次；检查是否产出具体实体结构/Query 覆盖语义，而非“三值负例误判”摘要。
- 验证每次都写入程序组装的 Product，Decision Scope 和 Evidence Summary 不由模型生成。
- 运行受影响测试、`tests/evolution` rooted discover；最后记录全量 discover 中已排除 Visualizer 遗留错误。

## 盘点结果

- 当前 Hook Adapter 在一个 phase 下把所有 case 聚合为单一 Observation，默认 `expected/observed` 只包含 case ID、label 和匹配计数；`decisive_observation` 仅存在 Detail，因此模型没有足够默认语义生成可用 Capability。
- 当前 `CapabilitySummarizerInput` 与 Direction input 通过继承共享结构；Capability 增加 Decision Scope 后应拆开输入类型，避免把 Capability 专用字段扩散给 Direction。
- 当前 Role Effect 只引用 `capability_draft_artifact=role.json`，没有最终产品物化边界。
- 当前 `observation_sources` 可以解析 Artifact 来源，但 Hook case 需要在来源 ref 后附加稳定 case ref，避免最终 Product 只引用整个 Probe。
- 当前正式文档仍声明 `capability_summarizer@1`、`capability_summary@1` 和四字段 Draft，必须随代码同步替换。
- 本轮已明确不保留旧字段、旧 output contract 或旧 artifact ref 兼容；历史 Run 继续作为只读来源，不要求用当前 Role Runner 恢复旧 Summarizer session。
