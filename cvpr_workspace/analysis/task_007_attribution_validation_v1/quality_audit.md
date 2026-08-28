# TASK-007 Experience Summarizer 真实归因质量审计

## 1. 审计边界

本审计使用 18 个 Goal 前历史负向 artifact 构造紧凑输入，通过真实 `deepseek-v4-flash` Teacher API 执行 30 个 `experience_summarizer@1` Run。结果只用于 TASK-007 角色行为诊断和后续 Prompt/工具协议修订，不构成 H3 方法效果、正式 baseline 或 Goal 验收证据。

人工审计逐项对照冻结 case rubric、原始负向 decision、授权 evidence view、模型输出和工具轨迹。`pass` 表示主要归因、类型、证据和行动义务均可直接使用；`partial` 表示保留了正确核心，但同时存在错误类型、过度泛化、工具失败或局部事实表述问题；`fail` 表示主要经验会被投影给错误 consumer 或遗漏当前明确责任层。

## 2. 执行结果

- 18 个 case 共执行 30 个真实 Role Run，全部获得合法 `ExperienceSummary`，无 provider、超时或终态结构失败。
- 实际发生 69 次 Teacher API request，累计 205,953 input tokens、131,475 output tokens、337,428 total tokens。
- 所有 `evidence_refs` 均通过运行时授权校验；无完整 transcript、Model Input、workspace/code 或任意路径进入 Model-visible evidence tool result。
- 预注册类型 rubric 完全匹配 19/30；其余差异主要来自额外生成 `student_capability` 或遗漏 `teacher_work`。
- 工具共尝试 51 次，成功 23 次、失败 28 次；15/30 个 Run 出现至少一次非法调用，10/30 实际尝试超过两次，5 个要求按需核查的 Run 没有获得任何成功工具结果。
- 只有 15/30 个 Run 同时满足“总尝试不超过两次且无非法 ref/view/selector”的工具协议。

## 3. 逐 case 归因结论

| Case | 结论 | 直接观察 |
| --- | --- | --- |
| `evidence_revise_corpus_confound` | partial | 三次均正确生成 Hypothesis revision 和 corpus-sufficiency experiment direction；三次都额外把单个 corpus-empty Trial 泛化为 Student capability。三次均发生非法工具调用，其中一次没有成功读取任何 view。 |
| `evidence_reject_no_differential_effect` | partial | 正确指出处理组没有超过 untreated control 的差异，并要求 Hypothesis/实验比较 matched control；额外把四次 Trial 行为写成广义稳定 Student capability，证据强度偏高。 |
| `evidence_reject_harmful_overtrigger` | pass | 正确归因于 Hypothesis trigger 约束不足，同时保留 clean falsifier 和 harmful over-trigger 两类事实，没有归责 Evidence Reviewer。 |
| `hook_feasibility_student_instability` | partial | 三次主要因果层、三类经验和主要义务稳定，均识别 single-entity negative flip；但输出把 `thinking_mode enabled/disabled` 多次表述成 Hook enabled/disabled，且三次都有非法工具调用，一次没有成功 view。 |
| `distiller_not_distillable_model_boundary` | partial | 正确区分 Intervention evidence 与生产 evaluator realizability，并形成 Student capability 与 boundary-probe direction；但先后请求不存在的 view/selector，实际三次尝试后才成功读取一次 trace。 |
| `conformance_activation_budget_implementation` | partial | 三次均生成正确 Compiler obligation；其中两次又把纯 rollout-local budget 实现错误写成 Student capability，只有一次保持单一 `teacher_work`。 |
| `conformance_empty_passage_projection` | partial | 正确生成“把真实 passages 投影给 classifier”的 Compiler obligation；同时把“输入为空时无法判断”错误包装成 Student capability，并增加非必要 experiment direction。 |
| `conformance_positive_action_not_applied` | pass | 准确归因于 Compiler 未把 positive decision 接到 defer/feedback/consumed action，类型、适用边界和义务均正确。 |
| `conformance_semantic_evaluator_boundary` | partial | 三次稳定识别 Hook-model 跨越 negative/uncertain 边界，并形成 capability、Distiller obligation 和 boundary controls；两次因 ref/selector 混淆实际调用四次工具。个别 Teacher lesson 把修复描述为 deterministic action wiring，弱化了“现有 wiring 已正确”的事实。 |
| `conformance_query_coverage_projection` | fail | 文本内容知道 first-only 不能等于 both，但输出只给 `student_capability` 和 `experiment_direction`，完全遗漏 route target 为 Compiler 的 `teacher_work`；纯 query-coverage projection 实现错误会被投影给错误 consumer。 |
| `conformance_missing_fact_model_misclassification` | partial | 正确保留 Mechanism Distiller obligation 和 evaluator capability 边界，工具读取正确；Student lesson 无证据地断言“只有两个记录都存在时才 emit positive”，超过已提供事实。 |
| `candidate_reject_intrinsic_grounding_predicate` | pass | 三次稳定识别 single-passage predicate 内生过严，并形成 cross-passage synthesis capability 与 experiment direction；虽然只有一次成功调用工具，但 Initial Input 已明确 faithful mechanism、正确答案被 defer 和 aggregate harm，输出仍由可见证据充分支持。 |
| `candidate_reject_hook_false_positive_scope` | partial | 三次均正确识别 explicit-negative false positive、无 activation-attributed benefit 和高成本，且没有生成 `teacher_work`；三次都有非法工具调用，一次完全没有成功 view。 |
| `candidate_reject_no_attributed_utility` | pass | 正确区分 activation path 与 no-op Student variance，并形成 self-assessed evidence-gap capability boundary 和 activation-level cost/benefit direction。 |
| `candidate_reject_low_precision_retrieval` | partial | 核心识别 activation precision、post-deferral efficacy、no-op variance 和成本；三次工具尝试全部失败，且 lesson 自相矛盾地称 7 次为 `contract-conformant activations`，随后又承认其中 3 次违反 negative rule。 |
| `candidate_reject_two_false_positive_activations` | partial | 正确识别两次 activation 均为 contract negative、无 activation-driven improvement；发生一次非法 selector 调用，且 direction lesson 把 both-entity-query case 表述成 first-entity-only 条件，局部事实不准确。 |
| `candidate_reject_selectivity_and_cost` | pass | 正确保留一项目标收益，同时把 out-of-scope harm、flat aggregate 和 per-event classifier cost 合并为 selectivity/cost direction，没有因单个成功 case 误判为可采纳。 |
| `candidate_validation_query_coverage_defect` | pass | 只生成 Compiler `teacher_work`，正确要求实际修改 coverage projection 和 positive defer action 后再提交，没有扩展为 Student capability。 |

人工汇总：6 个 case 为 `pass`，11 个为 `partial`，1 个为 `fail`。这不是 Goal 指标，只是本次冻结诊断组合下的任务级行为结论。

## 4. Anchor 重复稳定性

- `evidence_revise_corpus_confound`：三次类型和主要方向一致；错误的 Student capability 泛化也稳定复发。工具成功情况不稳定。
- `hook_feasibility_student_instability`：三次均输出相同三类经验和相同主要因果层；`thinking_mode` 被误称为 Hook state 的语义偏差稳定出现。
- `conformance_activation_budget_implementation`：Compiler obligation 三次稳定；附加类型不稳定，三次分别为 `teacher_work + student_capability`、仅 `teacher_work`、`student_capability + teacher_work`。
- `conformance_semantic_evaluator_boundary`：三次主要因果层和三类输出稳定；工具协议只在一次 Run 完全合规。
- `candidate_reject_intrinsic_grounding_predicate`：三次均输出相同两类经验并保持机制内生归因；工具使用从零调用到四次尝试不等。
- `candidate_reject_hook_false_positive_scope`：三次类型和主要归因稳定；工具协议三次均失败。

结论是“生成内容主线”比“工具行为和严格类型克制”稳定；重复运行不会自然消除错误 Student capability 或非法工具调用。

## 5. 已确认问题

### 5.1 工具调用预算没有约束实际尝试

`ExperienceEvidenceStore.call_count` 只在成功返回后递增。模型使用非法 evidence ref、view 或 selector 时不消耗预算，因此出现最多四次实际尝试，违背 Prompt 和方案中的“最多调用两次”。预算必须覆盖每一次 invocation，而不是只覆盖成功读取。

### 5.2 evidence ref、view 和 selector 的可发现性不足

Initial Input 只以 `ref -> free-text observation` 暴露 evidence。虽然 ref 是 JSON key，模型仍反复把 observation 中的 `hypothesis`、`trial_004` 等 selector 当作 evidence ref，或自行猜测 `candidate_comparison` 等不存在 view。当前自由文本无法可靠表达“可用 ref、该 ref 的 views、各 view 的 selectors”。

### 5.3 `student_capability` 的因果门槛过低

当前 Prompt 的“demonstrated model capability or stability boundary”不足以阻止模型把 Candidate 代码行为、空 classifier input、query projection 和 activation-budget 实现错误写为 Student capability。Student capability 应只在模型收到合同要求的有效输入、implementation 已确认 faithful，且重复或对照行为直接支持能力边界时产生。

### 5.4 明确 implementation defect 不保证生成 route-target teacher work

`conformance_query_coverage_projection` 已明确给出 Compiler route 和 projection defect，模型仍没有生成 `teacher_work`。Prompt 需要规定：当 typed trigger/route 和 evidence 已隔离出 implementation defect 时，核心 lesson 必须是 route target 的 `teacher_work`，不能只用其他类型改写同一修复义务。

### 5.5 事实术语和局部表述仍会漂移

模型把 thinking mode 写成 Hook state，并在少量 case 中生成未由证据支持的行为规律或自相矛盾描述。即使类型正确，lesson 仍需要更严格地绑定 evidence view 的原术语和因果限定。

## 6. TASK-007 当前结论

当前实现已经证明：真实 Teacher API 能在全部样本上形成合法、可读、通常抓住主要问题的 Experience Draft，并能避免在无 route target 的 Candidate rejection 上生成 `teacher_work`。但工具协议、Student capability 门槛和明确 implementation route 的类型约束未达到可直接消费的质量。

因此 TASK-007 保持 `executed`，本轮真实 API 质量验证结论为 `not accepted`。下一步需要先形成修订方案，最小修改应解决：所有调用都计入两次预算、结构化暴露 ref/view/selector、收紧 Student capability 因果门槛、强制明确 implementation defect 形成 route-target teacher work，并增加原术语保真检查。未经新的方案批准，不修改当前 Experience Summarizer 实现。
