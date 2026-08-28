# TASK-007 Prompt 终态与上游因果门槛修订方案 v8

## 1. 当前状态

- v7 的 evidence directory、可纠正工具协议和无 invocation hard cap 已实现并通过离线回归。
- 同一 18-case 组合已完成 30 次真实 Teacher API v2 验证；29 次完成、1 次终态失败。
- evidence 工具 33/33 次调用成功，v1 的 28 次非法 ref/view/selector 已清零。
- 明确 implementation defect 已稳定只生成 route-target `teacher_work`，Student capability 条目由 26 条收敛为 7 条。
- 15 次初次 terminal submit 因 `lesson` 超过 600 字符失败；另 1 次 JSON 截断后反复耗尽 6 个回合。
- “无 differential effect”案例仍错误生成 `student_capability`；TASK-007 当前未验收。

## 2. 任务意图

本次修订只解决真实 API 暴露的两个 Prompt 问题：让模型首次提交就满足终态字段预算；在干预相对 control 无差异、存在 clean falsifier 或在完整证据上 harmful over-trigger 时，先否定上游干预设计，而不是仅凭 faithful implementation 和多次行为写成 Student capability。

涉及 Goal H3 原文为：

> 将已结算轨迹中的 typed verification verdict 与终态转为有 provenance、严格 consumer/scope、可失效和可复查的 role-scoped experience，能够减少跨 attempt/generation 的能力越界、同角色错误复发和方向重走，并提高单位总预算的 useful Candidate yield，同时控制 false pruning 与 held-out utility。

本次仍只完善无状态 Experience Draft 的生成质量，不接入 Controller、Experience Store、duplicate/revise/new 或跨 generation 生命周期。

## 3. 实施思路

### 3.1 给出低于 Schema 上限的写作预算

Prompt 明确要求每条 `lesson` 不超过 500 字符、`applicability` 不超过 300 字符，并要求 `evidence_refs` 始终为 JSON 字符串数组。保留 Schema 的 600/400 硬上限作为 validator 边界，给模型留出计数误差余量。

### 3.2 一次完成因果选择后立即提交

Prompt 要求按既有五层顺序检查一次，选定主要因果层后直接调用 terminal submit；不得反复重开同一层级或类型权衡。该约束只限制冗余推理与终态拖延，不限制 evidence 工具调用次数。

### 3.3 在 capability 前排除干预设计失败

补充一条明确优先级：faithful implementation 只是 capability 判断的必要条件，不是充分条件。若 treated behavior 相对 control 无 differential effect，或 clean falsifier 直接否定方向，或 intervention 在完整/有效输入上 harmful over-trigger，则经验优先属于 upstream hypothesis/experiment design；不得把“该干预没有可靠诱发目标行为”改写为 Student capability。

只有在干预条件本身有效、对照已排除设计因果问题，且相同能力边界由重复/受控直接模型行为支持时，才生成 `student_capability`。

## 4. 计划实现

### 4.1 `harness_templates/teacher/experience_summarizer/prompt/system.md`

- 写入 `lesson <= 500`、`applicability <= 300` 和 `evidence_refs` 数组约束。
- 要求完成一次因果检查后立即提交，禁止重复权衡相同类型。
- 增加 no differential effect、clean falsifier、harmful over-trigger 的 upstream-design 优先级。

### 4.2 `tests/evolution/research/test_experience_summary.py`

- 增加 Prompt 文本断言，锁定字段预算、单次因果选择和 upstream-design 优先级。
- 保留 directory、无 invocation hard cap、implementation teacher work 与术语边界的现有测试。

### 4.3 最小真实 API 复核

- 使用本轮失败的 `evidence_reject_harmful_overtrigger` 和误归因的 `evidence_reject_no_differential_effect` 作为定向回归，各执行三次。
- 验收要求六次均首次或经一次格式修复后获得合法终态；不得生成 `student_capability`；必须保留 differential/control 或 falsifier/over-trigger 的上游设计义务。
- 若定向回归通过，不重跑已由 v2 证明稳定的 16 个 case。

## 5. 盘点结果

- evidence 工具 33 次调用全部成功，当前问题不在工具说明或调用次数边界，无需继续修改工具。
- 16 次 terminal submit 失败中，15 次是 `lesson` 超过 600 字符，1 次是 JSON 截断；Prompt 未呈现字段上限是直接可修正原因。
- 唯一终态失败 Run 的 reasoning 多次重复比较 upstream design 与 Student capability，并非证据不足。
- “无 differential effect”完成 Run 已准确复述 control 事实，错误发生在经验类型选择，不需要增加输入字段或 evidence view。
