# 运行产物 Schema

所有项目自有文本产物使用 UTF-8。JSON 对象未知字段的处理取决于对应 loader；不要把人工编辑后的文件视为可恢复日志。

## Agent Run trace

`run --trace-file` 写出 `RunResult.to_dict()`：终态 status、answer/error、AgentState 快照与有序 trace。Trace event 至少包含事件类型、step 和 payload；model、parse、tool、final、Hook 及 error 事件按实际运行追加。

## Rollout JSONL

一行对应一个 replicate：

- `example`：数据集样本。
- `replicate`：`replicate_id`、index、sampling seed。
- `harness`：模板或 Version Store 来源及 digest。
- `provenance`：可选实验上下文。
- `run`：成功调用 Runner 后的 RunResult；或 `runner_error`：异常类型与消息。

## Evaluation Report

Evaluation 目录包含：

| 文件 | 内容 |
| --- | --- |
| `summary.json` | schema version、生成时间、输入 provenance 与总体 metrics |
| `per_example.jsonl` | 逻辑样本聚合和稳定性 |
| `per_rollout.jsonl` | 每个 replicate 的判分与执行指标 |
| `summary.md` | 面向阅读的摘要 |

当前 report `schema_version` 为 `1`。

## Teacher Role artifact

当前 `schema_version` 为 `2`。共享 envelope 包含 `created_at`、`template_root`、`harness_id`、`role`、`output_contract`、`runtime`、非秘密 model provenance、实际 `role_budget`、validated input/output、resource config/artifacts、tool calls、usage 与 transcript。`output_contract.schema_digest` 用于确认本次运行实际使用的 JSON Schema。

Evidence Reviewer artifact 的 validated input 含完整 `trial_reviews`、程序维护的 `coverage_summary` 与当前 `trial_selection_capabilities`；同一 Effect 另写 `coverage_summary.json`，供恢复和外部审计直接读取。Mechanism Distiller 与 Compiler artifact 的 `resource_artifacts.student_model_experiments` 保存 Teacher 发起的描述性 Student 模型实验：稳定 `experiment_signature`、实验目的、完整 system prompt、案例输入、逐请求 thinking mode、原始输出、错误、usage 和 provider metadata。工具回显按 case/mode 聚合原始输出与总 token，不生成 expected label、匹配率或程序所有的通过结论；相同签名在后续 Compiler revision 中直接复用。提交的 `candidate_workspace.json` 同步携带这些实验以支持新 Role Session 的结构化接续。

`verify_hook_feasibility` 写入 `probe.json` 与 Hook Feasibility Reviewer 的 `role.json`。Probe 按 phase 保存冻结 decision contract、Trial Review reference label、原 prefix 的 Student-visible observation、实际 system/user prompt、thinking mode、repetition、raw output、错误、usage 与 provider metadata；不保存恢复后的 Student 分支，因为该调用在 Hook 判断后终止。Reviewer artifact 的 `resource_artifacts.hook_feasibility_probe` 保留同一完整 Probe，Effect Receipt 分别引用两份文件。进入 Compiler 时，各 phase 的 experiment 以原 `experiment_signature` 合入 `student_model_experiments`，Reviewer 的 `compiler_guidance` 进入实现约束。

Capability 与 Direction Summarizer 使用相同 Role Artifact envelope。Capability side work 写入 `capability_summarizer_artifact` 和程序组装的 `capability_experience_artifact`；Direction 仍写入 `direction_draft_artifact`。Capability Role Artifact 的模型输出只含 `observed_limitation` 与本地 Observation refs，独立 `capability_experience.json` 则含从来源 Artifact 原样提取的冻结 predicate（`decision_scope`）、由结构化 expected/observed decision 聚合的紧凑 `evidence_summary` 和解析后的稳定来源 refs。模型输入保存规范化 Observation 和不含正文的数字 Detail Directory；`resource_config.experience_summary` 保存 Source Processing Context、授权 Detail 投影、Observation 来源映射和程序专用的结构化 Capability Evidence。`resource_artifacts.experience_observation_sources` 保存稳定来源引用，`experience_details_read` 保存实际读取的 Detail ID。正式 Experience Store 尚未建立，因此 Capability Product 尚未结算或跨 Attempt 合并。

Evidence Review 在总评前把每条已完成的 Trial Reviewer artifact 写入 `trial_reviews/trial_review_NNN.json`。同一 Work 重试会发现并复用这些 checkpoint；若后续角色失败，failure artifact 的 usage 同时计入本次已完成但尚未形成 Effect Receipt 的子角色调用，避免漏记或重复调用。

Trial Selector 的 `selection.json` 保存 `status`、`selection_mode`、有序
`assignments`、当前 Hypothesis 的累计 `assignment_count` 和完整
`used_assignments`。`selection_mode` 只有 `fresh` 与 `reuse`：前者表示本批至少含一个
此前未选择的 `example_id`，后者表示没有扩展 example coverage；混合批次的精确
example、replicate 与 prefix 组成只由 `assignments` 审计。Controller payload 中的
`pending_assignments`、`batch_assignment_count` 与 `batch_executed_count` 是可恢复的
批次执行状态，批次结束并转入 Evidence Review 前会清除。

并发 Intervention Trial 的子产物按批次内容指纹写入
`artifacts/intervention_trial_checkpoints/<digest>/trials/`；并发 Trial Reviewer 的子产物
写入 `artifacts/evidence_review_checkpoints/<digest>/trial_reviews/`。每个子任务使用独立
文件，聚合结果仍保持 Assignment/Trial 输入顺序。失败诊断保存在同一 checkpoint 的
`failures/` 下；Controller Work retry 会复用已完成子产物，已计费调用不会重复执行。

Intervention Trial 记录 `runtime.extended_worker_tools`、每次改写的 source/live scope、
phase 和终态 action；扩展工具启用时另保存最终 `trial_state`，并在各 activation trace 中
记录 `trial_state_before`/`trial_state_after`。Scratch state 只属于当前 Assignment branch，
不会进入 Student Model Input，也不替代底层完整 trajectory。

原生 Teacher 工具循环耗尽时不会伪造 Role Output。Controller 在对应 Work Artifact
目录写入 `<role_id>.failed.json`：`status` 为 `failed`、`output` 为 `null`，并保留
输入、模型 provenance、完整部分 transcript、所有工具调用、usage、回合数、每轮
`finish_reason` 和终止错误。`events.jsonl` 的 `work_failed` 事件只保存错误摘要和
`failure_artifact` 引用，避免控制日志复制大体积 transcript。失败调用已经产生的
`total_tokens` 仍写入 `work_failed` 并计入 Control State；可识别的执行层写入
`failure_stage`，完整 traceback 保留在 failure artifact。

## Conformance checkpoint

每个 Candidate/Mechanism/Trial/Evolution Set 组合按内容摘要建立一套
`artifacts/conformance_checkpoints/<digest>/`：

| 路径 | 内容 |
| --- | --- |
| `suite.json` | 输入摘要、Candidate 身份、rollout summary 与本次 replay token 用量 |
| `candidate_replays.jsonl` | 固定复用的 Candidate replay suite |
| `local_evaluation/` | 对同一 replay suite 使用正式 Evaluation/Judge 规则生成的 report |
| `batches/batch_NNN.json` | 同一 Example 的有序 Review Batch、一次 Role artifact 与批次 usage |
| `findings/finding_NNN.json` | 程序附加 identity 后的规范化 Finding及其 Batch artifact 引用；不复制 Role artifact |
| `failures/finding_NNN_<suffix>.json` | Example 批次审查失败阶段、traceback、部分 transcript 与已产生 usage |
| `summary.json` | 仅从规范化 Finding 确定性聚合的 Conformance Summary |

每个 Batch 的角色输入保存同一 Example 的有序 `candidate_trajectory_views`，而不是完整
Candidate trace。该 view 是可重建的审查投影，不替代 `candidate_replays.jsonl` 中用于
复现的原始运行记录。Mechanism 与 reference observations 在批次输入中只呈现一次；每条
Finding 通过 `role_artifact_ref` 指回该 Batch。

Conformance Review Batch v5 为每个 replicate 保存一条 Review；程序附加权威 identity 后
形成 Finding。非 faithful 结果保存 `failure_layer`、`decisive_input_summary`、
`recommended_route`，并在 evaluator/parsing 问题上保存 `predicate_ref` 与期望/实际标签。
每条 Finding 另保存独立的 `local_efficacy`、`target_behavior_observed` 与短 assessment；Reviewer 只能依据投影中的
正式 score/Teacher assessment 和 Trial outcome 判断，不自行重判答案。Summary 汇总
`failure_layer_counts`、`recommended_route_counts`、`local_efficacy_counts`、
`local_efficacy_gate`、`effect_goal`、目标行为逻辑样本数、最终 `recommended_route` 及按路由分组的 `route_feedback`。明确局部
伤害但实现保真时路由 evidence；若同时存在实现硬失败，则 implementation repair 优先。

Controller Work 重试复用同一内容摘要目录；完整 Batch 已存在时不会重复调用 Reviewer，
只有尚未完成的 Example Batch 才会重试。成功重试的 Effect usage 只报告本次新产生的
token；先前失败尝试的 token 已由对应 `work_failed` 事件计入，避免漏计或重复计数。

Candidate Evaluation 完成后，Candidate Review Work 保存
`candidate_outcome_digest.json`；它只含配对变化、Hook 活动与归因计数、邻近样本引用、
机制指纹和实现摘要，不复制轨迹。Review 或 Gate 完成后，Promote/Reject Work 另保存带
`candidate_review` 和 `promotion_gate` 的最终 Digest，并以同名 Artifact ref 覆盖后续读取。

## Evolution Run

一个完整 Run 目录是不可拆分的保留单位：

| 路径 | 内容 |
| --- | --- |
| `run.json` | schema v2；Evolution Run/Template Version Store 身份、初始版本、Control Policy/Effect 配置、Evolution Set 与 Dataset provenance |
| `experience_set.jsonl` | 本次 Evolution Run 冻结的 Evolution Set；文件名保留当前实现名称 |
| `events.jsonl` | append-only ControlEvent；sequence、event type、payload、created time |
| `artifacts/` | 按 WorkItem 保存 effect、role、rollout、evaluation、trial、mechanism 与 candidate 相关大产物 |

Control State 从 `events.jsonl` 投影，不从 `artifacts/` 猜测 Run Agenda。Effect Receipt 完整存在时，Run Resume 可以复用它并补做尚未提交的 Transition。

由 `experiments.clone_run_from_incumbent` 创建的 Run 仍使用相同 schema，并在
`run.json.incumbent_evaluation_reuse` 记录单一源 Run、源/新 Work ID、原始 usage 和
本 Run 实际计费 token。新 Run 的 `version_store/` 保存具有新 Store 身份的 Accepted
Version 历史与当前模板，不复制未接受的 Candidate Attempt。其 journal 将复制的
Incumbent Evaluation 记为已完成且计费为 0，再通过正式 transition 排队 Failure
Analyst；下游研究产物不得随之复制。
克隆命令若提供 `--env-file`，新 `run.json` 的 `control_config` 和通用
`effects_config` 由当前 runtime 配置重新生成，路径型的 Evolution Set 与独立 Version
Store provenance 仍由克隆过程确定；未提供时则保留源 Run 的冻结配置。

## Template Version Store

| 路径 | 内容 |
| --- | --- |
| `version_store.json` | schema v2；稳定 `version_store_id` 与初始化来源 |
| `template/` | 当前接受模板的工作树 |
| `.harness-store/versions.jsonl` | schema v2 VersionRecord 索引 |
| `.harness-store/candidate_attempts.jsonl` | schema v2 Candidate Attempt 事件 |
| `.git/` | 每个 Accepted Template Version 的 Git 历史 |

Accepted Version ID 使用 `harness_vNNNN`。VersionRecord 保存 parent、Git commit、内容 digest、summary、evaluation 与可选 `candidate_attempt_id`。Candidate Attempt ID 使用 `candidate_attempt_<UTC timestamp>_<suffix>`，事件可重放得到 pending workspace；候选文件不作为长期重复副本保存。

Loader 仍可读取少量 v1 字段用于已有活动产物迁移，但所有新产物必须写 v2 名称与 Schema；旧名不是新代码的写入契约。规范决策见 [ADR-0002](../adr/0002-version-store-artifact-schema-v2.md) 与 [ADR-0003](../adr/0003-candidate-attempt-artifact-schema-v2.md)。

Mechanism 的旧 phase rule 若只有 `trigger_condition` 和共享字符串 fallback，可为只读展示投影成当前对象；该投影不构成新的研究证据。正式 compile Effect 会识别缺少原生 `decision_contract` 的 payload 并路由回 Mechanism Distiller，不允许 Compiler 把自动生成的泛化边界当作已验证规格。

Controller 的 Candidate Stage Effect 使用互斥状态区分生命周期结果：`valid` 表示新建或恢复的 pending Candidate 已通过本次校验；`validation_failed` 表示本次 Candidate 的确定性校验实际失败；`unchanged_rejected_candidate` 表示相同 Parent Version 和 digest 已存在 rejected Candidate Attempt。最后一种状态携带原 Candidate Attempt 标识、拒绝原因和 `prior_validation`，不得被解释为新的校验失败。
