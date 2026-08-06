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

当前 `schema_version` 为 `1`。共享 envelope 包含 `created_at`、`template_root`、`harness_id`、`role`、`output_contract`、`runtime`、非秘密 model provenance、实际 `role_budget`、validated input/output、resource config/artifacts、tool calls、usage 与 transcript。`output_contract.schema_digest` 用于确认本次运行实际使用的 JSON Schema。

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
| `findings/finding_NNN.json` | 程序附加 identity 后的规范化 Finding、原始 Role artifact 与单次 usage |
| `failures/finding_NNN_<suffix>.json` | 单条审查失败阶段、traceback、部分 transcript 与已产生 usage |
| `summary.json` | 仅从规范化 Finding 确定性聚合的 Conformance Summary |

每条 Finding 的角色输入保存 `candidate_trajectory_view`，而不是完整 Candidate trace。该 view 是可重建的审查投影，不替代 `candidate_replays.jsonl` 中用于复现的原始运行记录。

Controller Work 重试复用同一内容摘要目录，只重新调用没有完成 Finding checkpoint
的 Reviewer。成功重试的 Effect usage 只报告本次新产生的 token；先前失败尝试的
token 已由对应 `work_failed` 事件计入，避免漏计或重复计数。

## Evolution Run

一个完整 Run 目录是不可拆分的保留单位：

| 路径 | 内容 |
| --- | --- |
| `run.json` | schema v2；Evolution Run/Template Version Store 身份、初始版本、Control Policy/Effect 配置、Evolution Set 与 Dataset provenance |
| `experience_set.jsonl` | 本次 Evolution Run 冻结的 Evolution Set；文件名保留当前实现名称 |
| `events.jsonl` | append-only ControlEvent；sequence、event type、payload、created time |
| `artifacts/` | 按 WorkItem 保存 effect、role、rollout、evaluation、trial、mechanism 与 candidate 相关大产物 |

Control State 从 `events.jsonl` 投影，不从 `artifacts/` 猜测 Run Agenda。Effect Receipt 完整存在时，Run Resume 可以复用它并补做尚未提交的 Transition。

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
