# Evolution

当前 Evolution 是事件驱动、证据驱动的控制流程。Evolution Controller 只负责 Run Agenda、预算、重试、路由与确定性 Decision；Teacher Role 负责局部研究判断；大产物保存在 Control Event 之外。

## 主流程与角色激活

| WorkKind | 激活的角色或机制 | 激活条件 |
| --- | --- | --- |
| `evaluate_incumbent` | Evaluation | 每个 Generation 起点 |
| `analyze_failure` | Failure Analyst | incumbent 评估完成 |
| `research_hypothesis` | Hypothesis Researcher | 获得失败方向；或 Evidence/Trial 反馈要求修订 |
| `select_trial` | 确定性批次选择 | 新假设、Reviewer 要求更多证据或 Mechanism Distiller 要求补证据；按 example、replicate、prefix 分层选出有序 Assignment 批次 |
| `execute_trial` | Intervention Executor；Trial Reviewer 随后审阅轨迹 | 在 `rollout_workers` 限制内并发消费批次 Assignment；正确不干预也是可审阅 Trial |
| `review_evidence` | Trial Reviewer → Evidence Reviewer | 整批 Assignment 处理完后，在 `judge_workers` 限制内并发形成逐 phase predicate observation，程序按 Trial 输入顺序聚合当前 Hypothesis 的累计跨案例正负覆盖，再统一判断是否继续、修订、拒绝或进入蒸馏 |
| `distill_mechanism` | Mechanism Distiller + Hook Evaluator Probe | Evidence Reviewer 返回 `ready_to_distill`；Distiller 读取结构化 Trial observations 与 coverage summary，并对 Hook-model 决策契约作真实重复分类探测 |
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
- Mechanism Compiler 的 `needs_evidence` 回到试验选择，`needs_mechanism_revision` 或 `implementation_blocked` 回到 Mechanism Distiller；`submitted` 才能建立 Candidate。
- Candidate Validation 失败回到 Mechanism Compiler。
- Conformance Reviewer 为失败标明 evidence、mechanism 或 implementation 路由；Controller 按 Reviewer 的结构化诊断回到相应阶段。
- Candidate Reviewer 的 `revise` 可明确指向 evidence、mechanism 或 implementation。
- Candidate Reviewer 的真正 `reject` 或 Promotion Gate 的最终拒绝只结束当前 Research Attempt；Controller 保留当前 Accepted Template Version 与 incumbent 评估，在全局 Work Item/token 预算允许时从新的 Failure Analysis 开始同一 Generation 内的下一次 Research Attempt。

每条回流受独立预算限制，不依赖一个不断增长的固定条件分支流程。

Research Attempt 是一个 Generation 内从失败分析到 Candidate 决策的研究方向。定向 `revise` 仍属于当前 Research Attempt，不会启动新方向；新 Research Attempt 会清除旧 Hypothesis、Trial、Mechanism、Candidate 与局部 revision 状态，只复用 incumbent report、rollout 和 metrics。同一已拒 Candidate digest 再次提交时，Stage 返回 `unchanged_rejected_candidate` 并放弃当前方向，不会伪装成 Candidate Validation 失败或消耗 Compiler validation revision。

Intervention Trial 验证语义条件、干预动作与 Student 行为之间的因果关系。它不会实例化未来 Candidate 的 Hook model。Mechanism Distiller 对每个 phase 分离确定性 `guards` 与三值 `decision_contract`，明确 `positive/negative/uncertain` 的可操作边界、证据类别和各自 fallback；对 `decision_evaluator=hook_model` 的规则，Distiller 必须调用 Hook Evaluator Probe，使用正式 Student Hook-model backend 对已观察的正负边界及可用的不确定边界各重复分类。Probe 只产出匹配率、一致性、解析失败和 usage，不设置确定性通过门禁，结论仍由 Distiller 负责。Packet Builder 再把受控 `runtime_inputs` Topic 展开为完整、源码派生的 Python-native API 文档；只有 Mechanism Compiler 负责把已冻结契约实现为 Candidate，不能重新发明语义边界。

Selector 先使用 Failure Analyst 的有序 `evidence_refs`，不足时继续扫描冻结 Evaluation rollout。一个批次优先覆盖尚未选择的 `example_id`，其次把新 replicate 分散到不同的既有 example，最后才复用同一 replicate 的剩余 phase-compatible prefix。`selection_mode=fresh` 只表示该批至少扩展了一个 example；未扩展时为 `reuse`，精确组成始终以 `assignments` 为准。批次大小不超过 `trial_batch_size`、剩余 Trial 预算和剩余 Assignment 预算三者的最小值。

Controller 把一个 Assignment 批次作为单个可恢复的 `execute_trial` WorkItem。各 Intervention Trial 在 `rollout_workers` Semaphore 下并发运行，各自产生内容指纹 checkpoint；批次失败后的 Work retry 只重跑未完成 Assignment。结果始终按 Selector 输入顺序提交一次 Transition。随后，尚无有效 checkpoint 的 Trial Review 在 `judge_workers` Semaphore 下并发运行，仍按 Trial 输入顺序交给 Evidence Reviewer；整批只有在产生至少一个有效 Trial 时才调用一次 Evidence Reviewer。并发完成顺序不影响 Trial 编号、Coverage 或聚合顺序。

Hypothesis Researcher 每次提交完整 Hypothesis（包括修订版）后，Controller 都把 Trial、Assignment、Coverage 与待执行批次状态归零。修订续接期间旧 Trial 仍作为按需诊断材料附加给同一 Researcher Session；新版提交后旧 Trial 引用不会进入新版 Evidence Review。

## 持久化与恢复

`run.json` 冻结 Evolution Run 身份、Template Version Store 身份、初始版本、Evolution Set、Dataset、Control Policy 和 Control Effect 配置。`events.jsonl` 是 append-only Control Journal，Evolution Controller 从它重建 Control State。每个 Control Effect 的完整输出写入 `artifacts/`，Control Event 只保存引用。

Evolution Controller 先检查已有 Effect Receipt，再决定执行。因此一个已完成但尚未提交 Transition 的 Work Item 能在 Run Resume 后复用结果；外部调用失败按 `max_work_retries` 执行 Work Retry。Work Item、token、trial、revision 和 Generation 都有显式预算。

## 候选与晋升

Candidate Attempt 以当前 Accepted Template Version 为 Parent Version，通过文件编辑事件形成 Candidate Workspace。它必须依次通过 Candidate Validation、Conformance Review、同口径 Evaluation、Candidate Review 与 Promotion Gate。Gate 至少检查 Candidate Validation、Candidate Reviewer Recommendation、准确率增量下限和可选 token 比率上限。

Conformance Review 不直接把持久化完整 trace 输入模型。Controller 先生成只承担裁剪、不承担语义裁决的 Conformance trajectory view：重复对话快照、reasoning、usage 与无关事件被移除，工具证据、Student 解析动作、Hook 判定、Hook change、相关状态和最终结果保持可审查。Reviewer 仍负责所有 trigger、fallback 与实现保真判断。

当 Conformance 或 Candidate Validation 要求 implementation revision 时，下一次 Mechanism Compiler 从上一轮已提交 Candidate workspace 的精确文件 overlay 接续，并接收既有 changed paths、实现摘要和已查询 API 标识；Parent Version 仍是当前 Accepted Template Version。Conformance 若诊断为 `ambiguous_spec` 或 evaluator 契约问题则回到 Mechanism Distiller，若诊断为研究证据不足则回到 Trial selection。只有机制修订才重新建立新的实现方向，局部实现修订不从 Parent Template 重做接口探索。

旧 Mechanism artifact 仍可被读取和展示，但若其 phase rule 没有原生 `decision_contract`，正式 Controller 不会把兼容投影交给 Compiler；它直接返回 `needs_mechanism_revision`，要求从结构化 Trial observations 重新蒸馏。兼容投影只能防止历史文件无法查看，不能凭空补出 trial-grounded negative/uncertain 边界。

被拒候选不会成为 Accepted Template Version，也不会推进 Generation；它可以在全局预算允许时触发同一 Accepted Version 上的新 Research Attempt。通过后 Version Store 原子物化、Git commit，并生成下一个 `harness_vNNNN`。
