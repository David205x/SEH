# TASK-007 v2 冗余性独立审查

## 审查范围

- `cvpr_workspace/analysis/TASK-007_plan_v2.md`
- Experience Summary 相关 Teacher Role、Resource、Tool、Artifact 和 Prompt 装配代码
- Evidence、Distillation、Hook Feasibility、Compiler、Validation、Conformance、Candidate Review 与 Promotion Gate 的负向路由

## 结论

v2 的核心方向成立：使用无工具的 Experience Summarizer，并由程序提供白名单紧凑输入。但输入模型、触发归属和计划文件仍可继续删减。

## 必须删减

- 将 `source_role + stage + decision` 合并为一个真实路由 `trigger`。
- 删除独立 `reason` 与 `obligation`；它们作为带 ref 的 evidence observation 输入。
- 删除 `ExperienceTrigger`、`ExperienceResearchContext` 和 `ExperienceEvidenceItem` 包装模型；输入直接保存 trigger、responsible_role、direction、attempt 和有界 evidence 映射。
- 删除专用 Model Input renderer 模块职责；模板 Prompt Component 直接序列化已验证输入。
- 本任务不增加未被 Controller 调用的 `summarize_negative_outcome()`，也不提前增加角色运行预算。
- 本任务不修改 Controller、Effect 或 Transition；自动触发应与 first-class Summary Work 在后续原子任务中同时接入。

## 必须修正

- `teacher_work` 的责任角色不能等同于负向结论的触发角色。`responsible_role` 必须由实际后续路由确定；不存在明确责任角色时不得生成 `teacher_work`。
- TASK-007 只生成无状态 summary item；它不实现也不取消 PLAN-001 后续要求的 provisional/settled、invalidation、supersession 和 recheck 生命周期。
- 当前任务只能证明各负向来源能够构造紧凑输入并运行角色，不能声称现有 Controller 已自动触发经验总结。

## 最小合同

- `ExperienceSummaryInput`：trigger、responsible_role、direction、attempt、evidence。
- `ExperienceDraft`：experience_type、lesson、applicability、evidence_refs。
- `ExperienceSummary`：items；允许空，最多三条且 experience_type 不重复。

## 完整 Artifact 风险

无工具 Harness 不会主动读取 artifact。风险只存在于 input adapter；因此 adapter 必须逐字段抽取 typed output，并通过包含 transcript、rollout、resource_config、tool_calls sentinel 的测试确认这些内容不会进入 Model Input。
