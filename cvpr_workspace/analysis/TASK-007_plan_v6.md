# TASK-007 归因质量修订方案 v6

## 1. 当前状态

- 已使用 18 个真实历史负向 artifact 执行 30 个 `deepseek-v4-flash` Experience Summarizer Run，全部得到合法结构化输出。
- 人工归因审计为 6 个 case `pass`、11 个 `partial`、1 个 `fail`；TASK-007 保持 `executed`，当前质量不验收。
- 主要归因内容通常能识别真实问题，无 route target 的 Candidate reject 没有生成 `teacher_work`。
- 工具协议仅 15/30 个 Run 完全合规；10 个 Run 实际调用超过两次，15 个 Run 至少有一次非法 ref/view/selector。
- `student_capability` 会吸收 implementation defect；query coverage projection case 还遗漏了 Compiler `teacher_work`。
- 本轮尚未修改 Experience Summarizer 合同、Prompt、工具或 adapter。

## 2. 任务意图

本次修订只解决真实 API 验证已经复现的归因质量缺陷：让模型明确知道每个 evidence ref 可读取哪些 view，保证最多两次工具尝试是硬约束，并防止 Candidate/Compiler 实现错误被写成 Student capability 或漏投影给 route target。

涉及的 Goal H3 原文为：

> 将已结算轨迹中的 typed verification verdict 与终态转为有 provenance、严格 consumer/scope、可失效和可复查的 role-scoped experience，能够减少跨 attempt/generation 的能力越界、同角色错误复发和方向重走，并提高单位总预算的 useful Candidate yield，同时控制 false pruning 与 held-out utility。

本次仍只修订无状态 Experience Draft 的输入、工具和 Prompt 行为，不接入 Controller 自动触发、Experience Store 或跨 generation 生命周期。

## 3. 实施思路

### 3.1 evidence 直接暴露可用 view

五个顶层字段保持不变。`evidence` 仍是 `ref -> observation` 映射，但 observation 从自由字符串改为紧凑对象：

- `observation`：当前决策点的紧凑事实；
- `available_views`：该 evidence ref 实际可调用的 view 名称。

`available_views` 由 adapter 根据授权 registry 自动生成，不由调用方重复维护。它只服务当前模型工具选择，具有直接消费者，不作为持久化经验字段。

### 3.2 删除 selector 工具参数

每个 view 当前最多保存三条、工具一次也最多返回三条，因此 selector 没有减少返回内容，反而造成 ref/selector 混淆。`inspect_experience_evidence` 改为只接受：

- `evidence_ref`；
- `view`。

工具返回该 view 下全部有界 detail。detail 的内部 selector 标签可以随结果返回用于说明来源，但不再由模型提交。

### 3.3 每一次 invocation 都消耗预算

工具在完成 bound 检查后立即消耗一次调用额度，再检查 ref 和 view。非法 ref 或 unavailable view 也计入两次总预算；第三次调用固定拒绝。模型不能通过失败尝试绕过工具预算。

### 3.4 收紧 Student capability 因果门槛

Prompt 只有同时满足以下条件才允许输出 `student_capability`：

- 模型实际收到 contract 要求的有效输入；
- implementation 已经确认 faithful，或失败明确发生在独立 model probe；
- 重复、对照或多个直接行为证据支持同一能力边界。

空 passage projection、query coverage、activation counter、动作未执行等 implementation defect 禁止写成 Student capability。

### 3.5 明确 implementation route 的核心类型

当 typed trigger、route target 和 evidence 已把根因隔离到 implementation 时，必须生成 route target 的 `teacher_work`；除非存在独立证据支持其他层，否则不额外生成 Student capability 或 experiment direction。

Prompt 同时要求保留输入中的原术语，例如 `thinking_mode` 不得改写为 Hook state；输出只生成证据支持的类型，不为了覆盖 taxonomy 填满三条。

## 4. 计划实现

### 4.1 `search_harness/evolution/research/roles/contracts.py`

- 将 `ExperienceEvidenceObservation` 改为只含 `observation` 和 `available_views` 的严格模型。
- `ExperienceSummaryInput` 顶层仍只含 `trigger`、`route_target_role`、`direction`、`attempt`、`evidence`。

### 4.2 `search_harness/evolution/research/experience_summary.py`

- `build_experience_summary_request` 根据 registry 自动把 available view 投影进 Initial Input。
- 移除工具侧 selector 入参和 selector 授权分支；每个 view 返回已有的全部有界 detail。
- 将调用次数递增移动到 ref/view 校验之前，使失败 invocation 同样消耗预算。
- 保持最多两次、每次三条、单条 1500 字符和总计 4000 字符不变。

### 4.3 `search_harness/evolution/research/tools.py`

- `inspect_experience_evidence` 工具 schema 只保留 `evidence_ref` 与 `view`。
- 工具说明明确 evidence ref 来自 Input JSON key，view 必须来自该 ref 的 `available_views`。

### 4.4 `harness_templates/teacher/experience_summarizer/prompt/system.md`

- 增加 Student capability 的有效输入、faithful implementation 与重复/对照门槛。
- 增加 isolated implementation defect 必须输出 route-target teacher work 的规则。
- 要求精确保留 `thinking_mode`、Hook state、route 和 decision contract 等原术语。
- 明确只生成实际支持的类型，不默认生成三类经验。

### 4.5 测试与真实 API 回归

- 更新 `tests/evolution/research/test_experience_summary.py`：覆盖结构化 available views、无 selector 工具、失败调用计入预算、implementation-only type guidance 和初始证据隔离。
- 更新 TASK-007 stage check 和 validation entry 以适配新输入合同。
- 先运行确定性检查与 Evolution 回归。
- 复用完全相同的 18-case rubric 重新执行 30 个真实 API Run，输出到新的 `task_007_attribution_validation_v2/`，不覆盖 v1。
- 逐项比较 v1/v2 的非法工具调用、implementation 误分类、核心归因、术语保真和 anchor 稳定性；仍保留全部失败结果。

## 5. 盘点结果

- 51 次工具尝试中只有 23 次成功，28 次失败；失败主要是 selector 被当作 evidence ref、猜测不存在 view 或提交未授权 selector。
- 当前 view 最多三条且一次调用也最多返回三条，因此 selector 没有实际裁剪收益；删除它能直接缩小工具面。
- `ExperienceEvidenceStore.call_count` 只在成功返回后增加，导致 10 个 Run 超过批准的两次实际尝试；预算位置需要调整，而不是仅修改 Prompt。
- activation budget、空 passage projection 和 query coverage 三类样本均已由 typed evidence 隔离为 implementation defect，模型仍产生 Student capability；仅靠现有四层检查文字不足以建立类型门槛。
- query coverage case 已提供 `route_target_role=compiler`，模型仍未输出 `teacher_work`，说明 route target 当前只是弱提示，需增加明确的 implementation 输出义务。
- Hook Feasibility 三次输出均把 `thinking_mode enabled/disabled` 表述为 Hook enabled/disabled，说明 lesson 需要原术语保真约束。
- Candidate intrinsic-grounding 等案例说明 `student_capability` 并非应整体删除：当 faithful mechanism 下的多个行为证据直接展示 cross-passage synthesis 或 semantic classifier instability 时，该类型具有实际价值；修订应收紧因果门槛而不是减少 taxonomy。
