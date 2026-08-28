# TASK-007 角色驱动审查原始输出

以下内容按 sub-agent 最终返回保存，未由协调者改写结论。

## `/root/task007_summarizer_role_validation`

结论：`conditional_pass`。

当前实现并非 v11：当前 Prompt 仅用一句话区分三类 Experience；`evidence` 仍为 `ref -> str`；`resource_context` 只注入 evidence directory；角色仍为 `experience_summarizer@1`。v2 已实际出现 no-differential 被写为 capability、harmful-overtrigger 无终态、Hook instability 在 capability/teacher work 间翻转。

角色模拟结论：

- `evidence_reject_no_differential_effect`：结论对象是 generic verification treatment 的因果主张；3/4 无搜索且唯一搜索在 untreated control 同样发生，应只生成 `experiment_direction`，要求 matched untreated control 证明增量效果。
- `evidence_reject_harmful_overtrigger`：clean falsifier 无搜索且答错，同时 complete-evidence 输入过触发并 correct-to-wrong，应生成 `experiment_direction`，分别验证 positive efficacy 与 negative safety。
- `evidence_revise_corpus_confound`：可分别形成 Hypothesis Researcher success-condition 工作义务与 corpus-dependent experiment 的 inconclusive direction，但必须由不同事实和不同义务支持。
- `hook_feasibility_student_instability`：contract 明确、parse clean、相同 negative 重复翻转且 thinking mode 条件下持续误判，应为 `student_capability`，不能因 repair route 变成 Teacher work。
- `distiller_not_distillable_model_boundary`：production Hook evaluator 的 repeated mandatory-negative failure 支持 capability；intervention controls 不能替代 production-model acceptance probes 支持独立 direction。
- `conformance_activation_budget_implementation`、`conformance_empty_passage_projection`、`candidate_validation_query_coverage_defect`：观察对象均是 Compiler 工作，应为 `teacher_work`，禁止 capability。
- `conformance_semantic_evaluator_boundary`：structurally faithful Hook 下 frozen evaluator 跨越 explicit negative/uncertain boundary，主要为 capability。
- `candidate_reject_hook_false_positive_scope`：两个不同 explicit negatives 的 firing 可支持 capability；独立 Candidate comparison 的 correct-to-wrong、无 attributed gain 和成本可支持 direction。
- `candidate_reject_no_attributed_utility`：当前材料只支持 direction，缺少充分 positive-opportunity/重复边界信息，不应升级 capability。

仍含糊的规则：

1. no-differential、clean falsifier、harmful over-trigger 对 capability 的覆盖优先级未写死。
2. “假设被否定”与“Hypothesis Researcher 工作缺陷”仍可双向改写。
3. `multiple direct behaviors` 未说明有效 activation denominator。
4. route-target repair 仍可能被当作 Teacher fault 证据。
5. “独立证据”未定义为不同 ref 还是同一 ref 内不重叠 observation。
6. `attempt` 与 `boundary` 冲突时没有权威优先级。

建议规则原文：

> No differential effect against a matched control, a clean falsifier of the treatment claim, or harmful over-trigger on valid complete-evidence inputs makes the intervention direction the primary conclusion object. Faithful implementation and repeated behavior do not convert that finding into `student_capability`. Add capability only when separate probes isolate a model boundary independent of the treatment claim.

> A falsified but properly formed hypothesis is not `teacher_work`. Use `teacher_work` only when independent evidence shows that the route-target role violated a role-owned contract or process obligation under sufficient input. If the evidence only invalidates or confounds the hypothesis, success condition, mechanism class, or evaluation, use `experiment_direction`.

> A repair assigned to `route_target_role` is not evidence that the route target caused the failure. A mitigation written for a Teacher consumer does not change a demonstrated Student/Hook boundary into `teacher_work`.

> For `student_capability`, “multiple direct behaviors” means at least two independent valid inputs or repeated matched probes supporting the same narrow boundary. Failure to activate is capability evidence only when the number and validity of positive opportunities are established.

> Independent support for a second lesson means non-overlapping observations that establish a different conclusion object and a different future obligation. The observations may share an `evidence_ref`; changing only the wording or consumer is not independent support.

> Treat `boundary` as authoritative for input, contract, implementation, and data validity. `attempt` describes what was applied or claimed. If validity is absent, conflicting, or unresolved, inspect authorized evidence; otherwise do not emit `student_capability`.

## `/root/task007_consumer_role_validation`

结论：`conditional_pass`。

v11 已具备正确 consumer routing 骨架，但还没有完全定义消费者收到经验后改变哪项决策，以及何时允许重试。本任务只产出无状态 Draft，因此最多验证 consumer-ready draft，不能验证跨 generation recurrence/duplicate reduction。

消费者要求：

- `student_capability`：Hypothesis Researcher 必须能判断 proposal 是否依赖已证实不稳定的具体行为，并选择拒绝、缩窄、deterministic lowering 或指定 recheck。Lesson 需包含具体模型行为、有效 input/contract/faithful projection、重复行为、窄边界和明确处置；applicability 需限定 model/config、任务形状、输入表示、thinking mode/decision boundary 和解除条件。
- `experiment_direction`：Hypothesis Researcher 必须能识别方向是否重复，决定停止、缩窄、inconclusive 或满足额外证据后重访。Lesson 需包含方向签名、disposition、control/falsifier/confound/activation/cost 事实和合法重访条件。
- `teacher_work`：对应 Teacher Role 必须知道上次违反哪项自身职责、下一 Run 执行什么、用什么结果证明完成。Lesson 需包含 role-owned obligation、failure fingerprint、后果、动作和完成检查。

真实 case 结论：

- no differential：direction only；必须写 matched-control differential 才可重访。
- corpus confound：先判 inconclusive direction；只有独立 role-input-sufficiency 证据才可另生成 Teacher work。
- Hook instability：capability；不得因 repair route 写 Teacher work。
- Distiller model boundary：capability 与独立 production-probe direction 可并存。
- empty passage、activation budget、unchanged validation：Compiler Teacher work，需完成检查。
- semantic evaluator boundary：首要 capability；仅凭 Distiller 可加 guard 不证明 Teacher fault。
- intrinsic grounding predicate：direction，需写合法新 variant。
- Hook false-positive scope：独立行为矩阵可支持 capability，独立 Candidate comparison 可支持 direction。

互斥规则：

1. 同一事实、同一未来动作即为重复。
2. Teacher work 必须有充分输入下违反已有义务的独立事实。
3. no differential、clean falsifier、harmful over-trigger 或 data confound 优先 direction。
4. capability + direction 仅在行为矩阵与 Candidate comparison 分别支持不同动作时并存。
5. capability + Teacher work 仅在模型边界和角色忽略该边界分别有独立事实时并存。
6. Teacher work 与 direction：前者是跨方向角色程序义务，后者是具体方向 disposition。
7. data insufficiency 应写 inconclusive/补证据，不能写 capability 或已否定方向。

另指出：v11 的 20 次调用上限与 v2 报告“无 hard count limit”存在历史变化，需要明确这是用户新决定并同步文档。

## `/root/task007_attribution_reviewer_validation`

结论：`fail`。

阻断项：

1. `route_target_role` 被同时用作真实下一路由和 Teacher experience 隐式 subject，但两者不恒等。`candidate_validation_query_coverage_defect` 的 source 是 `unchanged_rejected_candidate`，Transition 启动新 Research Attempt，不回 Compiler；普通 `validation_failed` 也只有在 revision budget 未耗尽时回 Compiler。
2. “替换 Teacher 身份后是否仍成立”不能区分 Teacher work 与 direction。正确边界是：Teacher work 必须有事前 Role Contract 义务、事实当时对角色可见、角色未履行且后果有证据；direction 是 Trial/Candidate outcome 带来的后验研究更新。
3. v11 输入不能证明角色当时有足够输入。`upstream_contract` 只说明合同写了什么，不能说明事实在角色决定时可见；`role_input_sufficiency` 必须有权威来源。
4. 缺少 invalid/indeterminate eligibility gate。invalid source、错误输入、runtime failure、corpus 缺事实或模糊 spec 不得进入 capability extraction。
5. 20 次调用与旧架构文档冲突，且最多 15 个不同 ref/view。20 应是绝对熔断；默认 0 次，通常 1–3 次成功读取，不重复 ref/view，达到 20 次即质量失败。

仍会误归 capability 的反例：treated/control 相同行为；generic patch falsifier/over-trigger；重复空 passage；重复 query projection；模糊 spec label；corpus 缺事实；非-faithful Hook projection；Candidate activation 无收益。

仍会把 direction 改写为 Teacher work 的反例：no differential、harmful overtrigger、corpus confound、Hook instability、semantic evaluator boundary，以及真实 route 已 terminal 的 unchanged Candidate rejection。

输入判断：

- `direction` 必要，只写主张与预期。
- `attempt` 必要，只写执行方式/actor/覆盖，不与 boundary 重复 validity。
- `outcome` 必要，强制 observation actor。
- `comparison` 必要，写两侧、delta、重复关系。
- `boundary` 必要，但必须为权威确认事实，不能可空地承担硬门槛。
- `trigger` 必须细分真实 typed outcome。
- `route_target_role` 只能从实际 TransitionPlan 投影。
- 每次 Model Context 应突出当前 decision role、真实 route 和 causal-neighbor；全局职责作为共同语言。
- source validity 与 role-input sufficiency 当前缺失。

建议决策表：

| 顺序 | 条件 | 输出 |
| --- | --- | --- |
| 0 | invalid/transient/protocol/runtime failure 或 reference truth 不可判 | 不调用或空 |
| 1 | Model 收到空、错误、缺字段或非-faithful 投影 | 禁止 capability；严格 Teacher 门槛成立才 Teacher work，否则空 |
| 2 | data/corpus/label/evaluation 使实验不可解释 | inconclusive direction 或空 |
| 3 | no differential、falsifier、over-trigger、no-op gain、cost/regression | direction |
| 4 | reference-correct、有效输入、faithful probe、多直接行为同一边界 | capability |
| 5 | 事前 Role Contract 义务、当时输入足够、角色未履行、后果明确 | Teacher work |
| 6 | causal Teacher role 不等于 route target | 当前四字段 schema 下无法诚实表达 Teacher work |
| 7 | 两种类型成立 | subject、evidence atoms、future obligation 均不同时才输出第二条 |

Fixture 必须收紧精确类型：corpus confound direction only；no differential direction only；harmful direction only；Hook instability capability only；Distiller production-model boundary capability；明确 implementation cases Compiler Teacher work；semantic boundary capability；intrinsic predicate direction；activation overlap 需分别绑定 capability 和 direction 证据；no-attributed-utility/selectivity-cost direction。错误的 unchanged Candidate source 必须替换或单独表示真实 terminal route。
