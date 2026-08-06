# Evolution

当前 Evolution 是事件驱动、证据驱动的控制流程。Evolution Controller 只负责 Run Agenda、预算、重试、路由与确定性 Decision；Teacher Role 负责局部研究判断；大产物保存在 Control Event 之外。

## 主流程与角色激活

| WorkKind | 激活的角色或机制 | 激活条件 |
| --- | --- | --- |
| `evaluate_incumbent` | Evaluation | 每个 Generation 起点 |
| `analyze_failure` | Failure Analyst | incumbent 评估完成 |
| `research_hypothesis` | Hypothesis Researcher | 获得失败方向；或 Evidence/Trial 反馈要求修订 |
| `select_trial` | 确定性试验选择 | 新假设、Reviewer 要求更多证据或 Mechanism Distiller 要求补证据 |
| `execute_trial` | Intervention Executor；Trial Reviewer 随后审阅轨迹 | 选定 prefix 与任务后；正确不干预也是可审阅 Trial |
| `review_evidence` | Evidence Reviewer | 至少一项 trial 执行并完成逐 trial 审阅 |
| `distill_mechanism` | Mechanism Distiller | Evidence Reviewer 返回 `ready_to_distill` |
| `compile_candidate` | Mechanism Compiler | 得到已蒸馏机制；或验证/实现反馈要求修订 |
| `stage_candidate` | Candidate Attempt + Candidate Validation | Mechanism Compiler 提交 Candidate Template |
| `verify_conformance` | Conformance Reviewer | candidate 校验通过；按参考 trial 检查行为保真 |
| `evaluate_candidate` | Evaluation | conformance 通过 |
| `review_candidate` | Candidate Reviewer | candidate 评估完成 |
| `promote_candidate` | Promotion Gate + Version Store | Reviewer 建议与确定性门禁均允许 |
| `reject_candidate` | Candidate Attempt Journal | conformance、Reviewer 或门禁拒绝 |

“Intervention Executor”和“Mechanism Compiler”是规范术语；当前内部稳定 `role_id` 仍分别为 `intervention_worker` 与 `compiler`。

## 非固定流程的路由

每项工作是一个不可变 Work Item，包含稳定 `work_id`、kind、subject、输入引用、轻量 payload、父工作和 attempt。Control Effect 只返回小型 outcome、Artifact Reference 与 usage，并持久化为 Effect Receipt。Transition 函数根据已持久化结果生成下一批 Work Item，不直接执行副作用。

因此路由可以局部回流：

- Evidence Reviewer 的 `continue` 回到试验选择，`revise/reject` 回到 Hypothesis Researcher。
- Mechanism Distiller 的 `needs_evidence` 在 Trial/Assignment 预算仍可调度时回到试验选择；预算耗尽时必须就现有证据终结蒸馏判断。
- Mechanism Compiler 的 `needs_revision` 回到 Mechanism Distiller。
- Candidate Validation 失败回到 Mechanism Compiler。
- conformance failure 回到 implementation 修订。
- Candidate Reviewer 的 `revise` 可明确指向 evidence、mechanism 或 implementation。

每条回流受独立预算限制，不依赖一个不断增长的固定条件分支流程。

Intervention Trial 验证语义条件、干预动作与 Student 行为之间的因果关系。它不会在蒸馏前实例化未来 Candidate 的 Hook model。Mechanism Distiller 对需要语义判断的 phase 声明 `decision_evaluator=hook_model` 及其输入、输出和 fallback，并为每条 phase rule 选择受控的宽粒度 `runtime_inputs` Topic；Packet Builder 负责把 Topic 展开为完整、源码派生的 Python-native API 文档。只有 Mechanism Compiler 负责把声明实现为 Candidate 中的真实 Hook-model 调用，后续 Conformance 与 Candidate Evaluation 检查实际行为。

## 持久化与恢复

`run.json` 冻结 Evolution Run 身份、Template Version Store 身份、初始版本、Evolution Set、Dataset、Control Policy 和 Control Effect 配置。`events.jsonl` 是 append-only Control Journal，Evolution Controller 从它重建 Control State。每个 Control Effect 的完整输出写入 `artifacts/`，Control Event 只保存引用。

Evolution Controller 先检查已有 Effect Receipt，再决定执行。因此一个已完成但尚未提交 Transition 的 Work Item 能在 Run Resume 后复用结果；外部调用失败按 `max_work_retries` 执行 Work Retry。Work Item、token、trial、revision 和 Generation 都有显式预算。

## 候选与晋升

Candidate Attempt 以当前 Accepted Template Version 为 Parent Version，通过文件编辑事件形成 Candidate Workspace。它必须依次通过 Candidate Validation、Conformance Review、同口径 Evaluation、Candidate Review 与 Promotion Gate。Gate 至少检查 Candidate Validation、Candidate Reviewer Recommendation、准确率增量下限和可选 token 比率上限。

Conformance Review 不直接把持久化完整 trace 输入模型。Controller 先生成只承担裁剪、不承担语义裁决的 Conformance trajectory view：重复对话快照、reasoning、usage 与无关事件被移除，工具证据、Student 解析动作、Hook 判定、Hook change、相关状态和最终结果保持可审查。Reviewer 仍负责所有 trigger、fallback 与实现保真判断。

当 Conformance 或 Candidate Validation 要求 implementation revision 时，下一次 Mechanism Compiler 从上一轮已提交 Candidate workspace 的精确文件 overlay 接续，并接收既有 changed paths、实现摘要和已查询 API 标识；Parent Version 仍是当前 Accepted Template Version。只有机制修订才重新建立新的实现方向，局部实现修订不从 Parent Template 重做接口探索。

被拒候选不会成为 Accepted Template Version，也不会推进 Generation。通过后 Version Store 原子物化、Git commit，并生成下一个 `harness_vNNNN`。
