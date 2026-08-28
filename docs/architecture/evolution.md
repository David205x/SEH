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
| `distill_mechanism` | Mechanism Distiller | Evidence Reviewer 返回 `ready_to_distill`；Distiller 读取结构化 Trial observations 与 coverage summary，必要时自行发起描述性 Student Model Experiment |
| `verify_hook_feasibility` | Student Hook Probe → Hook Feasibility Reviewer | 配置启用且已蒸馏 Mechanism 至少有一个 `hook_model` phase；在已审阅的真实 prefix 上独立调用 Student 作三值判断，不恢复轨迹 |
| `compile_candidate` | Mechanism Compiler | 得到已蒸馏机制；或验证/实现反馈要求修订 |
| `stage_candidate` | Candidate Attempt + Candidate Validation | Mechanism Compiler 提交 Candidate Template |
| `verify_conformance` | Conformance Reviewer + 小样本 Evaluation | candidate 校验通过；按参考 trial 检查行为保真，并用正式 Judge 结果做局部效果负向预检 |
| `evaluate_candidate` | Evaluation | conformance 通过 |
| `review_candidate` | Candidate Reviewer | candidate 评估完成 |
| `promote_candidate` | Promotion Gate + Version Store | Reviewer 建议与确定性门禁均允许 |
| `reject_candidate` | Candidate Attempt Journal | conformance、Reviewer 或门禁拒绝 |

“Intervention Executor”和“Mechanism Compiler”是规范术语；当前内部稳定 `role_id` 仍分别为 `intervention_worker` 与 `compiler`。

Teacher artifact 以现有 `role.id/version` 和 `model` 字段作为身份事实源。未来 Teacher work experience 的 hard scope 只投影 Role ID、Role Contract Version 与 Teacher Model provider/model ID；不复制 output contract、Model Settings 或 digest。`base_prompt_digest` 对装配后的基础 Prompt 内容取指纹，`input_view_digest` 对 Role Runner 实际提交的紧凑 Model Input 取指纹；二者只用于 provenance、soft drift 和 recheck，不作为 Gate 或经验 exact-match key。Experience projection 在实际注入时使用独立 digest，不混入上述两个字段。

通用 Role Runner 的 input view 是 Prompt Component 在 typed input validation 和 `TeacherResources.model_context()` 删减投影之后形成的 messages/tools。digest 在本地对该实际视图计算，不向模型追加内容。Intervention Executor 则复用其 Worker trace 已保存的逐请求 `model_input`，不从 rollout、resource config 或 branch artifact 重建更大的输入。

## 非固定流程的路由

每项工作是一个不可变 Work Item。`logical_work_id` 标识跨 retry 不变的逻辑工作，`work_id` 标识一次物理执行；Work Item 还保存 kind、typed lineage、输入引用、轻量 payload、父工作和 attempt。Control Effect 只返回小型 outcome、Artifact Reference 与 usage，并持久化为 Effect Receipt。Transition 函数根据已持久化结果生成下一批 Work Item，不直接执行副作用。

因此路由可以局部回流：

- Evidence Reviewer 的 `continue` 回到试验选择，`revise/reject` 回到 Hypothesis Researcher。
- Mechanism Distiller 的 `needs_evidence` 在 Trial/Assignment 预算仍可调度时回到试验选择；预算耗尽时必须就现有证据终结蒸馏判断。
- Hook Feasibility 的 `feasible` 进入 Compiler；`needs_spec_revision` 只把操作定义或 runtime input 歧义交回 Distiller；模型边界不稳定、支持范围需要变化或代表性证据缺失时以 `needs_research_revision` 回到同一 Hypothesis Researcher Session。
- Mechanism Compiler 的 `needs_evidence` 回到试验选择，`needs_mechanism_revision` 或 `implementation_blocked` 回到 Mechanism Distiller；`submitted` 才能建立 Candidate。
- Candidate Validation 的普通 `validation_failed` 在 revision 预算内回到 Mechanism Compiler；`unchanged_rejected_candidate` 结算当前 Candidate Attempt，并从 Failure Analysis 开启新的 Research Attempt。
- Conformance Reviewer 为失败标明 evidence、mechanism 或 implementation 路由；Controller 按 Reviewer 的结构化诊断回到相应阶段。
- Candidate Reviewer 的 `revise` 可明确指向 evidence、mechanism 或 implementation。
- Candidate Reviewer 的真正 `reject` 或 Promotion Gate 的最终拒绝结束当前 Candidate Attempt；Controller 保留当前 Accepted Template Version、incumbent 评估和上一 Candidate 的紧凑效果引用，并先把结果作为 continuation 交回 Hypothesis Researcher。Researcher 选择修订当前 Research Scheme、在同一 Failure Direction 下建立平行 Research Scheme，或请求 Failure Analyst 重新分析；只有最后一种会建立新的 Failure Direction。

每条回流受独立预算限制，不依赖一个不断增长的固定条件分支流程。

Research Attempt 是一个 Generation 内从失败分析到 Candidate 决策的研究过程。定向 `revise` 仍属于当前 Research Attempt，但被拒 Candidate Attempt 已结算；后续 work 不再携带该 Candidate identity。终态拒绝会清除旧 Hypothesis、Trial 与局部 revision 状态，但保留 Candidate Outcome Digest、Evaluation、Compiler、Mechanism、Conformance 和 Reviewer 的只读引用，供 Analyst 复核诊断、Researcher 设计下一方案。累计多次方案失败只形成换向建议，不构成硬门禁。同一逻辑 staging work 重试时复用原 Candidate Attempt，不创建重复事务。

## Lineage 与结算

一次 Controller Run 直接以 `run_id` 作为 optimizer episode 身份。Run 内每次 version-advancement 搜索区间具有 `generation_id=<run_id>_gNNNN`；Generation 内每次研究过程具有 `research_attempt_id=<generation_id>_rNNNN`。Controller 另在 Work payload 中维护 `failure_direction_id`、`research_scheme_id`、`mechanism_scheme_id` 及 revision：每次 Analyst 成功输出建立新 Failure Direction，Researcher 的 clarification 保留 Scheme ID 而平行方案建立新 ID，MechanismSpec 修订保留 Mechanism Scheme ID。Candidate 物化后由 Candidate Journal 分配 `candidate_attempt_id`。这些身份均按可读父身份与顺序生成，不使用哈希派生。

`trajectory_settled` 是 source work terminal event 之后追加的 typed lifecycle boundary。`settlement_scope` 只允许 `candidate_attempt`、`research_attempt` 和 `work_attempt`；目标分别直接读取 lineage 的 Candidate ID、Research ID 或 source work ID，不保存通用 `scope_id`。Candidate promotion/rejection、研究性 terminal 与无效物理执行分别形成 `settled_positive`、`settled_negative` 或 `invalid_indeterminate`。仍在 continuation/revision 的 work 不创建 settlement。Direction map、Student capability boundary 和 Teacher role experience 后续只消费 typed scope、classification、verdict 和 source refs，不解析 `settlement_id` 或 `complete_reason`。

Experience 总结由两个自动挂载的独立旁路 Work 完成。`capability_summarizer@2` 在程序确定的 Capability Decision Scope 内，只归纳 Student/Hook-model 的具体 `observed_limitation` 并选择直接 Observation；Source Adapter 默认向其展示已审阅的决定性语义与逐条件模型决策，程序再生成 Evidence Summary 和稳定 refs，写入独立 Capability Experience Product。`direction_summarizer@1` 仍更新程序维护的 Failure Direction、Research Scheme 或 Mechanism Scheme。`inspect_experience_detail(detail_id)` 每个 ID 只允许读取一次，不限制固定 Detail 总数；Role 自身预算负责总调用上限。两个 side work 不执行 Experience Store 合并，其空结果或失败不改变原 Review、修订、晋升或拒绝语义。

角色优先提取 Student capability，其次是 experiment direction，最后才尽力提取 teacher work。Student capability 只有在冻结模型主体、有效 reference/输入、忠实实现、无数据混杂和重复窄边界同时成立时输出；experiment direction 必须给出处置和重访条件；teacher work 必须携带由证据确认的 `teacher_role_id`。归因需要更多过程证据时，唯一白名单工具可读取裁剪后的 upstream contract、decision trace 或 candidate comparison；正常预期为零至三次有效读取，单次 Role Run 的第 21 次调用由程序硬熔断，失败调用也计数。工具不暴露路径、完整 artifact、prompt、transcript、model input、reasoning、workspace/code 或 usage。输出按 capability、direction、teacher work 顺序至多各一条；证据不足时允许空结果。

Intervention Trial 验证语义条件、干预动作与 Student 行为之间的因果关系。它不会实例化未来 Candidate 的 Hook model。Mechanism Distiller 对每个 phase 分离确定性 `guards` 与三值 `decision_contract`，明确 `positive/negative/uncertain` 的可操作边界、证据类别和各自 fallback；Distiller 或 Compiler 的 Student Model Experiment 仍是可选的合成探索。正式 Hook Feasibility 则把冻结 contract 投影到 Trial 已审阅的原始 prefix，以相同 Student profile、配置的 thinking modes 和重复次数独立调用模型，Hook 输出后立即结束，不恢复 Student 轨迹。程序保存 reference label、真实模型输入、逐请求原始输出、usage 与 metadata，但不以确定性程序判断语义通过；Reviewer 决定稳定性、thinking mode 与回流目标。Packet Builder 再把受控 `runtime_inputs` Topic 展开为完整、源码派生的 Python-native API 文档；只有 Mechanism Compiler 负责把已经通过 feasibility 的契约实现为 Candidate，不能重新发明语义边界。

Selector 先使用 Failure Analyst 的有序 `evidence_refs`，不足时继续扫描冻结 Evaluation rollout。一个批次优先覆盖尚未选择的 `example_id`，其次把新 replicate 分散到不同的既有 example，最后才复用同一 replicate 的剩余 phase-compatible prefix。它不读取自然语言 obligation 的语义，也不能选择未来分支结果；Evidence Reviewer 得到这一能力边界，不得要求 Selector 持续采样直到出现某个随机行为。`selection_mode=fresh` 只表示该批至少扩展了一个 example；未扩展时为 `reuse`，精确组成始终以 `assignments` 为准。批次大小不超过 `trial_batch_size`、剩余 Trial 预算和剩余 Assignment 预算三者的最小值。

Controller 把一个 Assignment 批次作为单个可恢复的 `execute_trial` WorkItem。各 Intervention Trial 在 `rollout_workers` Semaphore 下并发运行，各自产生内容指纹 checkpoint；批次失败后的 Work retry 只重跑未完成 Assignment。结果始终按 Selector 输入顺序提交一次 Transition。随后，尚无有效 checkpoint 的 Trial Review 在 `judge_workers` Semaphore 下并发运行，仍按 Trial 输入顺序交给 Evidence Reviewer；整批只有在产生至少一个有效 Trial 时才调用一次 Evidence Reviewer。并发完成顺序不影响 Trial 编号、Coverage 或聚合顺序。

Hypothesis Researcher 每次提交完整 Hypothesis（包括修订版）后，Controller 都把 Trial、Assignment、Coverage 与待执行批次状态归零。修订续接期间旧 Trial 仍作为按需诊断材料附加给同一 Researcher Session；新版提交后旧 Trial 引用不会进入新版 Evidence Review。

## 持久化与恢复

`run.json` 使用当前 schema 冻结 Evolution Run 身份、Template Version Store 身份、初始版本、Evolution Set、Dataset、Control Policy 和 Control Effect 配置。`events.jsonl` 是 append-only Control Journal，Evolution Controller 从它重建 Control State 与 settlement projection。每个 Control Effect 的完整输出写入 `artifacts/`，Control Event 只保存引用。Control Run、Candidate Journal 和 Version Store 只读取当前 schema，不迁移旧 ID 字段或旧文件名。

Evolution Controller 先检查已有 Effect Receipt，再决定执行。因此一个已完成但尚未提交 Transition 的 Work Item 能在 Run Resume 后复用结果；外部调用失败按 `max_work_retries` 执行 Work Retry。Work Item、token、trial、revision 和 Generation 都有显式预算。

## 候选与晋升

Candidate Attempt 以当前 Accepted Template Version 为 Parent Version，通过文件编辑事件形成 Candidate Workspace，并通过 start metadata 绑定完整 Controller lineage。它必须依次通过 Candidate Validation、Conformance Review、同口径 Evaluation、Candidate Review 与 Promotion Gate。Mechanism 的 `effect_goal` 区分 `task_outcome` 与 `behavioral_intermediate`；Conformance、Candidate Reviewer 和 Gate 共享该目标，但分别检查局部效果、全量语义证据和确定性阈值。Gate 还检查 Candidate Validation、Reviewer Recommendation、目标专用准确率/归因阈值和可选 token 比率上限。

Conformance Review 不直接把持久化完整 trace 输入模型。Controller 先生成只承担裁剪、不承担语义裁决的 Conformance trajectory view：重复对话快照、reasoning、usage 与无关事件被移除，工具证据、Student 解析动作、Hook 判定、Hook change、相关状态和最终结果保持可审查。相同少量 replay 另经正式 Evaluation/Judge 得到 score 与 assessment；Reviewer 分开提交实现保真、目标行为是否出现和局部效果结论。明确局部伤害总会拦截；`task_outcome` 全中性时因未见局部收益而拦截，`behavioral_intermediate` 则允许结果中性但必须实际观察到声明的中间行为。

当 Conformance 或 Candidate Validation 要求 implementation revision 时，下一次 Mechanism Compiler 从上一轮已提交 Candidate workspace 的精确文件 overlay 接续，并接收既有 changed paths、实现摘要、已查询 API 标识、模型实验以及紧凑 Conformance failures；Parent Version 仍是当前 Accepted Template Version。Compiler 修订是新的 Role Session，而不是无限续长旧 transcript；结构化接续避免重复读 Harness，同时隔离已膨胀上下文。若 workspace 与被拒 revision 相同，finalizer 要求实际修改或返回非提交结论。Conformance 若诊断为 `ambiguous_spec` 或 evaluator 契约问题则回到 Mechanism Distiller，若诊断为研究证据不足则回到 Trial selection。只有机制修订才重新建立新的实现方向，局部实现修订不从 Parent Template 重做接口探索。

旧 Mechanism artifact 仍可被读取和展示，但若其 phase rule 没有原生 `decision_contract`，正式 Controller 不会把兼容投影交给 Compiler；它直接返回 `needs_mechanism_revision`，要求从结构化 Trial observations 重新蒸馏。兼容投影只能防止历史文件无法查看，不能凭空补出 trial-grounded negative/uncertain 边界。

被拒候选不会成为 Accepted Template Version，也不会推进 Generation；它可以在全局预算允许时触发同一 Accepted Version 上的新 Research Attempt。通过后 Version Store 原子物化、Git commit，并生成下一个 `harness_vNNNN`。
