# TASK-007 Prompt 与证据工具修订方案 v7

## 1. 当前状态

- 18 个真实 artifact case、30 个真实 Teacher API Run 和独立 sub-agent Prompt/工具审查已完成。
- 主要因果主线总体可用；工具合法调用空间不可见、Student capability 过度生成和明确 implementation defect 漏 teacher work 尚未解决。
- 28 次工具失败中，17 次为 selector 猜错、6 次为 ref/selector 混淆、4 次为当前 ref 不支持所选 view、1 次为 selector 超限。
- v6 中“让失败调用也消耗两次预算”的方案不再采用；本报告取代 v6。
- 当前未修改 Experience Summarizer 研究实现，TASK-007 保持 `executed`、未验收。

## 2. 任务意图

本次修订让 Experience Summarizer 在不读取完整 artifact 的前提下明确知道可用 evidence ref、view 和 selector，允许模型按归因需要读取并纠正调用，同时收紧类型因果门槛和术语保真。

涉及的 Goal H3 原文为：

> 将已结算轨迹中的 typed verification verdict 与终态转为有 provenance、严格 consumer/scope、可失效和可复查的 role-scoped experience，能够减少跨 attempt/generation 的能力越界、同角色错误复发和方向重走，并提高单位总预算的 useful Candidate yield，同时控制 false pruning 与 held-out utility。

本任务仍只修订无状态 Experience Draft 的 Prompt 与只读 evidence view，不接入 Controller、Store 或经验生命周期。

## 3. 实施思路

### 3.1 不限制工具调用次数

移除 `ExperienceEvidenceStore` 的 per-run call count 和 Prompt 的“最多两次”。归因可能需要 contract、trace 和 comparison，也可能需要在错误反馈后纠正调用；硬拦截不会提高证据质量。

上下文边界继续由以下机制控制：

- 每个 view 最多三条 detail；
- 单条最多 1500 字符、单次结果最多 4000 字符；
- 角色 Runner 的 max turns 和 token budget；
- Prompt 在四层因果关系已可区分后停止读取，不重复浏览相同 view。

### 3.2 暴露不含证据内容的工具目录

五字段 Role Input Contract 不变。Experience Summarizer 的 `resource_context` 从空对象改为小型目录：

`evidence_ref -> available view -> exact selector list`

目录只说明可调用空间，不包含 detail content、路径或 artifact。模型由 evidence JSON key 取得 ref，由目录取得合法 view/selector，不再从 observation 普通名词中猜测。

### 3.3 让错误反馈可纠正

- 非法 ref：返回合法 ref 列表；
- unavailable view：返回该 ref 的合法 view；
- 非法 selector：返回该 ref/view 的精确 selector；
- selector 为空时返回该 view 的全部有界 detail。

失败只形成可修正反馈，不消耗人为调用额度。

### 3.4 收紧经验类型

- `student_capability` 只在模型收到有效 contract input、implementation 已确认 faithful 或来自独立 model probe、且重复/对照或多个直接行为证据支持同一边界时生成。
- 空 passage、coverage projection、activation counter、action wiring 等错误属于 implementation，不得写成 Student capability。
- route target 为 Compiler 且 evidence 已隔离 implementation defect 时，核心输出必须是 `teacher_work`；无独立证据时不补 capability/direction。
- 只输出实际必要类型，不为了覆盖三类 taxonomy 填满三条。

### 3.5 术语保真与 fixture 修正

Prompt 要求沿用 evidence 原术语。真实回归 case 明确写出 `thinking_mode enabled/disabled`，并把 `implementation conformance passed, but semantic activations violated negative rules` 与 `contract-conformant activations` 分开。

工具必调 rubric 改为仅在 Initial Input 无法区分责任层时要求；Initial Input 已充分的 Candidate reject 不因零工具调用失败。

## 4. 计划实现

### 4.1 `search_harness/evolution/research/experience_summary.py`

- 删除 `MAX_EVIDENCE_TOOL_CALLS`、`call_count` 和调用次数拒绝逻辑。
- 新增只导出 ref/view/selector 名称的 `directory()`。
- 扩充 ref/view/selector 错误消息，返回当前合法选项。
- 保持每次结果的条数与字符边界。

### 4.2 `search_harness/evolution/research/resources/base.py`

- Experience Summarizer 的 `model_context()` 返回 evidence directory，不返回证据内容。

### 4.3 `search_harness/evolution/research/tools.py`

- 保留 `evidence_ref`、`view` 和可选 `selectors`。
- 工具说明明确 ref 来自 Initial Input `evidence` key，view/selector 来自 resource directory，selector 为空读取整个有界 view。

### 4.4 `harness_templates/teacher/experience_summarizer/prompt/system.md` 与 `user.md`

- 删除工具调用次数限制。
- 说明 evidence key、目录、view、selector 的关系和停止读取条件。
- 增加 Student capability、implementation teacher work、必要类型和原术语保真规则。

### 4.5 验证 fixture、测试与真实回归

- 修正 Hook thinking-mode、low-precision activation 文本和工具必调 rubric。
- 更新单元测试和 stage check，覆盖目录无内容泄漏、可修正错误反馈、无调用次数限制和类型因果门槛。
- 先运行确定性回归，再复用 18 个 case 执行新的真实 API v2；重复 anchor 保留三次，全部结果独立保存。
- v2 审计分开报告 Prompt/模型偏差、fixture/rubric 偏差和工具接口偏差，不沿用首轮 6/11/1 作为通过阈值。

## 5. 盘点结果

- 27/28 次失败直接来自合法调用空间不可见；多个 Run 在收到错误后能够自我修正并取得正确证据。
- 全局 view 枚举使模型合理地假设每个 ref 支持三种 view；自由字符串 selector schema 又促使模型生成语义关键词。
- Initial Input 的 “Inspect hypothesis and trial_004” 直接诱导模型把两个 selector 当作 ref，说明 case 构造也承担责任。
- 现有每次结果和 Runner 已有自然资源边界，不需要额外 invocation hard cap。
- 明确 implementation case 中，positive action 未执行和 Candidate Validation 能正确只生成 teacher work；activation budget、empty passage 和 query projection 则显示 Prompt 门槛不稳定。
- Candidate reject 样本证明 capability 类型仍有价值，但必须禁止把 prior knowledge 自动纳入 grounding，并区分 cross-passage evidence 与无证据推断。
