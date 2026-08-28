# TASK-007 Capability Experience 表述收敛实施计划 v20

> 实施状态：待用户批准。本轮只修正 Capability Experience Product 的权威来源和表述质量。

## 当前状态

- `capability_summarizer@2` 已只生成 `observed_limitation + evidence_refs`，程序负责物化最终 Product。
- 当前 `decision_scope` 不是来源 Artifact 中的原字段，而是 Adapter 使用 phase、inputs 和 predicate 重新拼接的英文说明。
- 当前 Prompt 要求删除 model identity 和 evaluator type，真实输出因此容易使用 `condition`、`conjunct`、`outcome` 等抽象措辞，不能直接形成“Hook model 在哪些具体输入边界上不可靠”的经验。
- 当前 `evidence_summary` 机械拼接 Observation 编号、匹配计数和 raw labels，事实正确但不适合 Researcher 快速阅读。
- Hook Feasibility Artifact 已包含 `decision_contract.predicate`、逐 case reference label、`decisive_observation`、thinking mode 和重复输出；Conformance Finding 已包含 `predicate_ref`、expected/observed label 和 decisive input，且可通过 Mechanism Artifact 解析冻结 predicate。

## 任务意图

本次把 Capability Product 收敛为三项职责清楚的信息：来源 Artifact 直接提供被测决策范围，Summarizer 用具体任务语义描述观察到的能力限制，程序把重复结果压缩为条件化证据概况。最终单项应接近以下阅读形态：

```json
{
  "decision_scope": "<来源 Artifact 中冻结的 predicate 原文>",
  "observed_limitation": "Hook model cannot reliably exclude two inputs that should not activate: single-entity factoid questions and cases whose query history already covers both compared entities.",
  "evidence_summary": "With thinking disabled, both cited negative cases were repeatedly labeled positive; with thinking enabled, the single-entity case flipped from negative to positive.",
  "evidence_refs": ["<稳定 case ref>"]
}
```

本任务服务 Goal H3：

> “将已结算轨迹中的 typed verification verdict 与终态转为有 provenance、严格 consumer/scope、可失效和可复查的 role-scoped experience，能够减少跨 attempt/generation 的能力越界、同角色错误复发和方向重走，并提高单位总预算的 useful Candidate yield，同时控制 false pruning 与 held-out utility。”

本轮验证产品语义和稳定性，不验证 Researcher 消费后的 H3 效果。

## 实施思路

### Decision Scope 使用权威原文

- Hook Feasibility Observation 直接使用 `phase_probe.decision_contract.predicate`，不再添加 phase、inputs 或 `to decide whether` 包装。
- Conformance Observation 对结构化 `predicate_ref` 从冻结 Mechanism 精确解析对应 `decision_contract.predicate`；Finding 已直接携带完整判定文本时使用该文本原值。
- 指向 Artifact 字段路径但缺少对应 Mechanism 的输入直接拒绝组装，不再退化成面向消费者的内部路径说明。

### Observed Limitation 改为行为边界句

- Observation 的 `subject` 使用明确行为主体 `Hook model` 或 `Student`；Prompt 允许并要求在限制句中保留该主体。
- 每项使用“主体 + 不能稳定完成的语义区分 + 具体混淆输入”结构，优先列出 decisive observations 已支持的输入类型。
- Prompt 禁止用 `condition`、`predicate`、`conjunct`、`outcome`、`comparison-confirmation decision` 等实现层代称替代具体问题、Query、Evidence 或 Final Answer 关系。
- 同一 Decision Scope 下支持同一限制的近邻输入必须合并为一项，并在限制句中分别点明；仍不生成修复建议或 Researcher 策略。

### Evidence Summary 压缩条件化事实

- 不新增模型输出字段；程序从被引用 Observation 的 expected label、thinking condition 和重复 raw labels 生成摘要。
- 同一 condition 下先聚合被引用案例，再表达“全部重复误判”“部分翻转”或“重复正确”等事实；不再输出 Observation 编号和逐项匹配分数。
- Conformance 等不含 thinking mode 的来源使用相同原则，按引用案例汇总 expected-versus-observed 结果。

## 计划实现

- 修改 `search_harness/evolution/research/experience_summary.py`：
  - 删除 `_hook_decision_scope()` 的说明文字拼接，直接提取 predicate；
  - 将 `_conformance_decision_scope()` 改为严格的 Artifact 字段解析；
  - 将 Hook/Conformance Observation 的主体收敛为真实行为主体；
  - 重写 `_capability_evidence_summary()`，输出条件化聚合事实。
- 修改 `harness_templates/teacher/capability_summarizer/prompt/system.md` 和 `prompt/user.md`：明确期望句式、具体语义要求和实现术语禁区，并通读消除与“保留 Hook model 主体”冲突的旧指导。
- 更新 `CONTEXT.md` 的 Capability Decision Scope 定义，以及 `docs/design/experience-summarizer-redesign.md`、`docs/reference/role-contracts.md`、`docs/reference/artifact-schemas.md` 中对应协议说明。
- 更新 `tests/evolution/research/test_experience_summary.py`：验证 Decision Scope 与来源 predicate 完全相等、缺失的结构化引用不能生成内部路径文本、Evidence Summary 能聚合 thinking 条件和重复误判。
- 使用现有 Hook Feasibility 与 Conformance Artifact 各并行调用真实 API 三次，检查限制句是否稳定包含行为主体和具体输入边界；随后运行 `tests/evolution`、`compileall` 和 `git diff --check`。

## 盘点结果

- Hook Probe 的权威字段位于 `probe.json -> phase_probes[].decision_contract.predicate`；当前 `_hook_decision_scope()` 在该原文外自行添加 phase 与 inputs。
- Conformance 所用 Mechanism 的权威字段位于 `mechanism.json -> phase_rules[].decision_contract.predicate`；当前无法解析时会返回包含 `predicate_ref` 的说明句，使内部引用路径泄漏到产品。
- Hook Probe 的两个关键负例已在 `case_references[].decisive_observation` 中明确区分为单实体事实题和 Query 同时覆盖两个实体；不是 Summarizer 需要猜测的隐藏语义。
- 同一 Probe 已保存各 case 在 enabled/disabled thinking 下的重复 raw labels，能够确定性生成条件化 Evidence Summary。
- 当前 Prompt 一方面要求描述具体语义，另一方面要求移除 model identity/evaluator type；后者直接促成了抽象无主体的限制句，需在本轮同步消除。
