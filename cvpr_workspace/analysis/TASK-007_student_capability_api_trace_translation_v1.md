# TASK-007 `Student Capability` 真实 API 轨迹翻译与审阅摘要（v1）

## 1. 范围与结论边界

本文只审阅最终真实 API 批次 `cvpr_workspace/analysis/task_007_attribution_validation_v5/` 中最终输出包含 `student_capability` 的 12 个 Role Run：4 个 case，每个 case 3 次重复。前三个 case 只输出 `student_capability`；`candidate_reject_hook_false_positive_scope` 同时输出 `student_capability` 和 `experiment_direction`，本文只逐条翻译其中的 Capability item，Direction item 留给对应方向文档处理。

这些 artifact 是 TASK-007 开发期的角色归因与输出合同验证，用于检查 Experience Summarizer 能否从紧凑输入生成 consumer-ready Experience Draft。它们**不是 H3 正式证据**，不能推出 Experience Store 已建立、经验已跨 Run 复用、历史经验能被去重或修正，也不能证明正式研究效果。

结构审计显示，12/12 Run 均完成且 exact type、输出长度、工具预期与工具协议通过；三次重复的类型集合完全稳定。质量审计也判定 12 条 Capability Draft 均把主体限定在冻结的 Student/Hook model，没有把 Reviewer、Compiler、数据缺失或干预无效误写成模型能力。

主要依据：

- `cvpr_workspace/configs/task_007_attribution_cases.json`
- `cvpr_workspace/configs/task_007_attribution_selection_v3.json`
- `cvpr_workspace/analysis/task_007_attribution_validation_v5/execution_context.json`
- `cvpr_workspace/analysis/task_007_attribution_validation_v5/summary.json`
- `cvpr_workspace/analysis/task_007_attribution_validation_v5/structural_audit.json`
- `cvpr_workspace/analysis/task_007_attribution_validation_v5/quality_audit.md`
- `cvpr_workspace/analysis/task_007_attribution_validation_v5/quality_verdict.json`

## 2. 如何从输入支持或排除 Capability 归因

下面只总结可观察的归因流程，不复制或声称暴露模型隐藏 chain-of-thought、raw reasoning 或 transcript 中的内部推理文本。

| 输入字段 | 在归因中的可观察作用 | 不能单独证明的内容 |
| --- | --- | --- |
| `direction` | 标识被测试的因果主张或机制方向，用来界定任务与决策边界。 | 方向失败不自动等于 Student/Hook 能力失败。 |
| `attempt` | 说明实际运行的 actor、机制、模式与覆盖范围。 | 它不是输入、标签或实现有效性的权威证明。 |
| `outcome` | 给出实际观察到的模型行为和直接后果，例如重复误报、跨边界 defer 或回归。 | 单个异常、无效输入上的异常或未归因的聚合变化不足以建立能力边界。 |
| `comparison` | 提供重复、matched case、正负例、no-op 路径、激活归因、回归与成本等对照，用来判断是否是稳定且狭窄的模型行为。 | 对照只能否定干预主张时，不能反过来自动证明模型能力不足。 |
| `boundary_facts` | 依次关闭硬门：`reference_validity`、`input_validity`、`implementation_fidelity`、`data_sufficiency`。四项确认后，标签错误、错误输入、解析/接线缺陷和数据不足不再是更直接解释。 | 它们只在声明的模型、任务、输入与 decision contract 范围内支持结论。 |
| source Transition | 区分报告结果的 decision role、实际 route target 和证据支持的 causal subject；同时确定 Experience 的 consumer。 | `revise`、`reject` 或路由到某角色不证明该角色造成了失败。 |

可观察的最小逻辑是：

`有效 outcome/comparison` → `reference/input/implementation/data 四个 gate 通过` → `重复或至少两个等价有效 case 命中同一窄边界` → `student_capability` → `Hypothesis Researcher 不按原样依赖，增加确定性 guard 或执行指定 recheck` → `只有新模型、重新验证后的合同/输入范围，或同范围复测证明边界恢复，才重新评估使用限制`。

这里要区分两件事：确定性 guard 可以缓解系统行为，但不会让冻结模型本身的能力限制消失；只有模型或同一能力边界上的新证据才能解除模型层结论。

## 3. Case A：`hook_feasibility_student_instability`

### 3.1 输入、gate 与 Transition

- `direction`：实现一个识别单侧双实体证据缺口的三标签 evaluator。
- `attempt`：冻结 evaluator 在开启/关闭 `thinking_mode` 下，对相同真实 prefix 做重复 probe。
- `outcome`：开启 thinking 时，同一个 single-entity negative 在重复间翻转；关闭 thinking 时，两个 negative case 都被重复判为 positive。
- `comparison`：positive cases 稳定且解析干净，因此错误被定位到冻结 Hook model 的显式负例边界，而不是整体解析不稳定。
- 四个 `boundary_facts` 均为 `confirmed`：参考标签来自冻结的三路 decision contract，输入是真实有效 prefix，执行与解析忠实且 parse-clean，重复等价负例足以建立狭窄稳定性边界。这排除了 Hook Feasibility Reviewer 错误与 parser failure。
- source Transition 为 `hook_feasibility.needs_research_revision`：`hook_feasibility_reviewer` 报告 provisional negative，实际 route target 是 `hypothesis_researcher`。该路由说明后续由 Hypothesis Researcher 消费并修订研究假设，但不说明 Reviewer 或 Hypothesis Researcher 是失败原因。

### 3.2 三次重复的逐条翻译

#### Repetition 1

Artifact：`cvpr_workspace/analysis/task_007_attribution_validation_v5/runs/hook_feasibility_student_instability/run_01.json`

- **Lesson 译文**：冻结的 Hook 模型在关闭 thinking 时，把两个有效的显式负例（原文括注为“单侧双实体缺口”）都重复判为 positive；开启 thinking 时，同一个负例又在重复运行之间发生翻转。这个显式负例边界既狭窄又不稳定，因此 Hypothesis Researcher 不应原样依赖它，而应修订证据范围或增加确定性负例 guard。
- **Applicability 译文**：仅适用于冻结 Hook 三路 evaluator 在两种 thinking mode 下，对真实 prefix、parse-clean 的单侧证据缺口负例所作的判断。如果 decision contract、输入范围或模型发生变化，或者加入确定性 guard，应重新检查。

#### Repetition 2

Artifact：`cvpr_workspace/analysis/task_007_attribution_validation_v5/runs/hook_feasibility_student_instability/run_02.json`

- **Lesson 译文**：冻结 Hook 模型无法可靠实现单侧双实体缺口三标签 evaluator 的显式负例边界：关闭 thinking 时，两个显式负例都被重复判为 positive；开启 thinking 时，同一个负例发生翻转，而正例保持稳定且解析干净。不要原样依赖；应加入确定性 guard，或在固定 mode 下对负例执行重复 recheck。
- **Applicability 译文**：适用于冻结 Hook 在两种已探测 thinking mode 下，对真实 prefix 的单侧双实体证据缺口 case 所作的三路判断。只有固定 mode 的重复 probe 能稳定正确标注两个显式负例，才可解除这一限制。

#### Repetition 3

Artifact：`cvpr_workspace/analysis/task_007_attribution_validation_v5/runs/hook_feasibility_student_instability/run_03.json`

- **Lesson 译文**：冻结 Hook evaluator 在三路 decision contract 下错误标注显式负例：关闭 thinking 时，两个有效负例真实 prefix 在每次重复中都被判为 positive；开启 thinking 时，同一个负例在重复之间翻转。它的显式负例边界既没有选择性，也不稳定。Hypothesis Researcher 不应原样依赖 Hook 的负例判定；应增加确定性 guard 或执行明确指定的 recheck。
- **Applicability 译文**：仅适用于冻结 Hook 模型在含显式负例的单侧双实体真实 prefix 上所作的三路判断；在相同 decision contract 下，可以通过确定性 guard 或明确指定的 recheck 重新评估这一边界。

### 3.3 稳定共识、差异与问题

三次均稳定保留两个决定性事实：关闭 thinking 时两个负例重复误报，开启 thinking 时一个相同负例跨重复翻转；均输出 `do not rely unchanged`，并把 guard/recheck 指向 Hypothesis Researcher。差异主要是措辞：Rep 1 强调“修订证据范围”，Rep 2 给出最具体的“固定 mode 重复负例 recheck”，Rep 3 强调 selectivity 与 stability。

审阅注意：Rep 1 把“显式负例”括注为“单侧双实体缺口”，容易与 positive 的真正单侧双实体缺口语义混淆；Rep 3 的 applicability 未像前两次一样明确 `thinking_mode` 与 parse-clean 条件，范围略宽。此外，guard 只能缓解系统误触发，不能单独解除冻结模型的能力限制。

## 4. Case B：`distiller_not_distillable_model_boundary`

### 4.1 输入、gate 与 Transition

- `direction`：把已经验证的单侧搜索干预蒸馏为可部署的 Hook evaluator。
- `attempt`：上游 intervention coverage 已通过，再用 production-model probes 检查部署模型能否实现语义边界。
- `outcome`：唯一允许的 Hook model 在 4/4 次 probe 中都把“已查询两个实体”的负例判错，并且还判错一个 single-entity negative。
- `comparison`：上游干预通过两正两负 control，但部署模型仍无法实现必需的负例边界；因此“干预有效”不等于“可部署 evaluator 能实现合同”。
- 四个 gate 均确认：负例标签来自已验证 activation contract；both-entity 与 single-entity negatives 均有效；两种 contract wording 与 parse-clean probe 排除了 parser/wiring defect；4/4 重复失败足以建立狭窄模型边界。这排除了 Mechanism Distiller error 与 Compiler implementation defect。
- source Transition 为 `mechanism_distiller.not_distillable`：`mechanism_distiller` 给出 settled negative，terminal reason 是证据不可蒸馏，没有 route target。它说明当前蒸馏尝试终止，但 Capability Draft 的 causal subject 仍由 probe 锁定为 Hook model，后续 consumer 仍是 Hypothesis Researcher。

### 4.2 三次重复的逐条翻译

#### Repetition 1

Artifact：`cvpr_workspace/analysis/task_007_attribution_validation_v5/runs/distiller_not_distillable_model_boundary/run_01.json`

- **Lesson 译文**：冻结 Hook 模型无法实现已验证 activation contract 所要求的负例边界：在两种 contract wording 下的 4/4 次 parse-clean probe 中，它都误标“两个实体均已查询”的负例，并且还误标一个有效 single-entity negative；参考、输入与 probe 忠实性均已确认。Hypothesis Researcher 不应原样依赖这个 Hook evaluator；复用前应为 both-entity negatives 增加确定性 guard，或执行明确的边界 recheck。
- **Applicability 译文**：适用于该 Hook 模型在单侧搜索任务中对 both-entity 与 single-entity negatives 的判断范围。上游 control 成功不能转移为可部署性；复用需要换用另一个获准模型重新检查，或使用修正后的边界规格。

#### Repetition 2

Artifact：`cvpr_workspace/analysis/task_007_attribution_validation_v5/runs/distiller_not_distillable_model_boundary/run_02.json`

- **Lesson 译文**：冻结 Hook 模型在 4/4 个“已查询两个实体”的有效显式负例 probe 中都给出错误标注，并且也误标一个 single-entity negative；两种 contract wording 与 parse-clean 执行排除了 parser 或 wiring defect。该模型无法实现已验证 activation contract 要求的负例边界，因此 Hypothesis Researcher 不应原样依赖它：复用蒸馏结果前应增加确定性 guard，或执行明确的 recheck。
- **Applicability 译文**：范围是获准 Hook 模型对单侧搜索干预的三路蒸馏，以及有效的 both-entity-queried 与 single-entity-queried negatives。在等价负例 recheck 能证明可靠区分之前，或者在把负例边界交给确定性 guard 之前，该限制持续成立。

#### Repetition 3

Artifact：`cvpr_workspace/analysis/task_007_attribution_validation_v5/runs/distiller_not_distillable_model_boundary/run_03.json`

- **Lesson 译文**：冻结、可部署的 Hook 模型在 4/4 次 probe 中都误标 contract 必需的 both-entity negative，并且还误标一个 single-entity negative；输入有效，两种 contract wording 排除了 parser/wiring defect。上游干预已通过 controls，因此问题是 Hook 模型无法实现要求的负例拒绝边界。Hypothesis Researcher 不应原样依赖；应增加确定性 guard 或重新检查。
- **Applicability 译文**：仅适用于该 Hook 模型依据已验证 activation contract，对显式 both-entity 与 single-entity negatives 所作的三路判断。模型变更、contract boundary 修订或确定性拒绝 guard 可触发对该限制的重新评估。

### 4.3 稳定共识、差异与问题

三次均稳定区分“上游 intervention controls 通过”和“部署 Hook model 能否实现边界”，并保留 4/4 both-entity negative 失败、额外 single-entity negative 失败、两种 wording 与 parse-clean 执行排除实现问题。三次动作均为不原样依赖，并加入 guard 或 recheck。Rep 1 最完整列出 reference/input/probe fidelity，Rep 2 最清楚表达限制持续条件，Rep 3 最简洁地强调上游成功不能覆盖模型失败。

审阅注意：输入中的 authoritative contract 明确指出 both-entity negative 是已验证 activation condition 的必需边界，不能作为“已知限制”直接豁免。因此 Rep 1 的“修正后的边界规格”和 Rep 3 的“contract boundary 修订”若被理解为仅靠改写合同就解除限制，会造成事实漂移；更准确的表述应是“经独立重新验证且仍满足任务语义的新合同/机制”，或换模型后在同一必需边界上 recheck。确定性 guard 同样只迁移判断责任，不证明原模型能力已恢复。

## 5. Case C：`conformance_semantic_evaluator_boundary`

### 5.1 输入、gate 与 Transition

- `direction`：使用 Hook-model evaluator，只 defer 缺少支持证据的已承诺值。
- `attempt`：结构忠实的 Hook 在多次 case 上仍反复违反显式 negative 与 uncertain 规则。
- `outcome`：四个 mismatch 横跨两类边界：把已有明确 passage link 的值判为 positive；把 refusal 或 bare mention 当成缺证据的已承诺值。
- `comparison`：结构 Hook 与确定性 action wiring 均存在且忠实，因此直接原因不是 defer action wiring，而是 evaluator 跨越 explicit-link negative 与 no-committed-value uncertain 两条语义边界。
- 四个 gate 均确认：每个 mismatch 都按明确 contract clause 标注；输入是有效 committed-answer/evidence-gap examples；结构与 deterministic wiring 忠实；多个有效 case 覆盖两个不同必需边界。这排除了 Conformance Reviewer error 与 deterministic wiring 是已证原因的说法。
- source Transition 为 `conformance.revise`：`conformance_reviewer` 报告 provisional negative，`next_work_kinds` 为 `reject_candidate`，没有直接 route target。Transition 只说明 candidate 流程如何继续，不能把 Reviewer、Compiler 或 reject target 当成因果主体；Capability consumer 仍按类型映射为 Hypothesis Researcher。

### 5.2 三次重复的逐条翻译

#### Repetition 1

Artifact：`cvpr_workspace/analysis/task_007_attribution_validation_v5/runs/conformance_semantic_evaluator_boundary/run_01.json`

- **Lesson 译文**：冻结 Hook evaluator 无法有选择地实现“只 defer 缺乏支持证据的已承诺值”：在 Hook 结构与确定性 action wiring 忠实的情况下，四个有效 mismatch 仍 defer 了证据明确支持的值（跨越 explicit-link negative 边界），并把 refusal/bare mention 当成缺证据的已承诺值（跨越 no-committed-value 边界）。这是跨两个边界的重复过度触发；不要原样依赖，应增加确定性 guard 或重新检查 defer 边界。
- **Applicability 译文**：适用于 Hook evaluator 在 conformance 三路 contract 下，对有效 committed-answer 与 evidence-gap 输入所作的 defer 判断。当覆盖边界的 recheck 或确定性 guard 能消除显式负例和非承诺输入上的过度 defer 时，可重新评估该使用限制。

#### Repetition 2

Artifact：`cvpr_workspace/analysis/task_007_attribution_validation_v5/runs/conformance_semantic_evaluator_boundary/run_02.json`

- **Lesson 译文**：冻结 Hook evaluator 无法实现“只 defer 缺乏支持证据的已承诺值”：尽管 Hook 与确定性 wiring 忠实，四个有效 mismatch 仍把证据明确支持的值标成 positive，并把 refusal/bare mention 当成缺证据的已承诺值，同时违反 explicit-link negative 与 no-committed-value uncertain 条款。Hypothesis Researcher 不应原样依赖；应针对显式负例和 evidence-gap refusal 增加确定性 guard，或在有效 probe 上重新检查。
- **Applicability 译文**：范围是 Hook-model evaluator 在 Hook 与确定性 wiring 忠实的 conformance 条件下，对 committed-answer/evidence-gap examples 的判断；限制覆盖 explicit-negative 与 uncertain 两类条款。只有有效 probe 能证明它在两类条款上区分显式负例与 positive，才可解除限制。

#### Repetition 3

Artifact：`cvpr_workspace/analysis/task_007_attribution_validation_v5/runs/conformance_semantic_evaluator_boundary/run_03.json`

- **Lesson 译文**：冻结 Hook-model evaluator 无法实现“只 defer 缺乏支持证据的已承诺值”：在四个有效 case 中，它把证据明确支持的值当成 positive（defer），并把 refusal/bare mention 当成缺证据的已承诺值；即使结构 Hook 与确定性 wiring 忠实，仍在两个必需边界上产生 false positive。不要原样依赖；应修订三路 decision contract 或加入确定性 guard，再重新检查。
- **Applicability 译文**：适用于 Hook-model evaluator 在 explicit-link negative 与 no-committed-value uncertain contract clauses 下进行 committed-value defer。修订后的 contract/guard 必须在两条边界上重新验证；或者在复用前，换用其他 Hook model 对这些 case 重新 probe。

### 5.3 稳定共识、差异与问题

三次均稳定识别同一组四个 mismatch、两条语义边界，以及结构和 deterministic wiring 忠实这一排除事实；均拒绝把问题归因给 Conformance Reviewer 或 action wiring。Rep 1 强调“跨两边界的重复过度触发”，Rep 2 明确 consumer 为 Hypothesis Researcher 并列出两类 guard，Rep 3 给出“换模型重新 probe”的替代路径。

审阅注意：Rep 1 的“corrected boundary examples”原措辞容易暗示原 case/标签有误，但输入已确认 reference 与 input validity；更准确的是“覆盖两条已确认边界的代表性 probe”。Rep 3 的“修订 contract”如果只是改定义以回避失败，同样会过宽；修订后仍需证明任务语义与两条必需边界得到保留。Rep 2 的“a valid probe”用单数表达，低估了输入中依靠多个 case 建立 data sufficiency 的要求。

## 6. Case D：`candidate_reject_hook_false_positive_scope`（Capability item）

### 6.1 输入、gate、Transition 与双输出分离

- `direction`：用 semantic Hook 检测真正的单侧双候选证据缺口。
- `attempt`：忠实 Candidate 检查每个 pre-final state，并在 Hook positive 时 defer。
- `outcome`：positive activation 只出现在两个明确 contract-negative 的有效 prefix（joint question 与 single-entity question）；其中一次造成直接回归，未观察到 intended positive behavior。
- `comparison`：所有改善都发生在 Hook-negative 的 no-op runs；整体 accuracy 下降，Hook cost 显著增加。这组聚合/激活归因事实用于 companion `experiment_direction`，而 Capability 的核心证据是两个不同显式负例上的模型 positive activation。
- 四个 gate 均确认：负例规则明确、两个 prefix 有效、Candidate 忠实执行 Hook decision/action wiring、两个不同负例足以建立窄 selectivity boundary。这排除了 Candidate Reviewer error 与 Compiler implementation defect。
- source Transition 为 `candidate_reviewer.reject`：`candidate_reviewer` 给出 settled negative，`next_work_kinds` 为 `reject_candidate`，没有直接 route target。reject 是流程结果而不是 Reviewer 致因；Capability item 按 consumer mapping 交给 Hypothesis Researcher。
- 三次都按固定顺序输出 `student_capability` 后接 `experiment_direction`。Capability 消费“两个显式负例均误触发”并要求 guard/recheck；Direction 消费“没有 intended positive、改善来自 no-op、accuracy/cost 恶化”并要求停止或重设计。两者主体与 action 基本独立。

### 6.2 三次重复的 Capability 逐条翻译

#### Repetition 1

Artifact：`cvpr_workspace/analysis/task_007_attribution_validation_v5/runs/candidate_reject_hook_false_positive_scope/run_01.json`

- **Lesson 译文**：冻结 semantic Hook 模型在两个不同且有效的显式 contract-negative 问题（joint 与 single-entity）上都激活为 positive；其中一次造成直接回归，并且没有出现 intended positive behavior。狭窄边界是：Hook 的 positive decision 无法把真正的单侧双候选证据缺口与显式 contract negatives 区分开。Hypothesis Researcher 不应原样依赖；任何使用前都应加入确定性显式负例 guard，或执行明确的 recheck。
- **Applicability 译文**：适用于冻结 Hook 在有效真实 evaluation prefixes 上，对显式 contract-negative 的 joint/single-entity questions 所作的三路判断。如果 matched probe 证明显式负例上不再出现 positive activation，或者在 Hook activation 前放置确定性负例过滤器，可重新评估使用限制。

#### Repetition 2

Artifact：`cvpr_workspace/analysis/task_007_attribution_validation_v5/runs/candidate_reject_hook_false_positive_scope/run_02.json`

- **Lesson 译文**：冻结 semantic Hook 模型在显式 contract negatives 上过度触发：对两个有效 evaluation prefix（一个 joint、一个 single-entity 的显式负例问题），它都发出 positive activation；其中一次造成直接回归，且没有 intended positive behavior。它无法有选择地识别真正的单侧证据缺口。Hypothesis Researcher 不应原样依赖；应增加确定性显式负例 guard，或在复用前 recheck 其 selectivity。
- **Applicability 译文**：适用于 semantic Hook 在 two-candidate evaluation prefixes 上，面对显式 contract-negative 的 joint 与 single-entity questions 所作的三路判断，且 Candidate wiring 忠实。加入显式负例 guard，或重新校准 Hook 并证明两种 case 都不再过度触发后，应重新检查。

#### Repetition 3

Artifact：`cvpr_workspace/analysis/task_007_attribution_validation_v5/runs/candidate_reject_hook_false_positive_scope/run_03.json`

- **Lesson 译文**：冻结 semantic Hook 模型在两个有效 evaluation prefix 中，对显式 contract-negative 的 joint 与 single-entity questions 都产生 positive activation；其中一次 activation 造成直接回归，且没有 intended positive behavior。它不能有选择地检测真正的单侧双候选证据缺口。不要原样依赖；复用前应加入确定性显式负例 guard，或重新检查 Hook 在负例上的 selectivity。
- **Applicability 译文**：适用于冻结 Hook 模型在当前 contract 下，对有效 evaluation prefixes 所作的判断，覆盖显式 contract-negative 的 joint 与 single-entity questions。解除限制或重新检查需要有效 positives 与 matched negatives，并在负例上观察到零 positive activation。

### 6.3 稳定共识、差异与问题

三次均稳定保留两个不同显式负例、两次 positive activation、一次直接回归，以及“冻结 Hook 缺少 selectivity”的狭窄边界；均要求显式负例 guard 或 matched recheck。Rep 1 最明确写出 genuine gap 与 contract negative 的区分失败，Rep 2 强调 faithful Candidate wiring，Rep 3 对重新验证提出 valid positives + matched negatives 的更完整设计。

审阅注意：三条 Capability lesson 都带入“没有 intended positive behavior”。该事实本身真实，但更主要服务于 Direction 的 utility 判定；放进 Capability 会轻微削弱双输出的证据分离，尽管两个显式负例仍足以独立支持 Capability。Rep 1 把“前置 deterministic filter”写成可 release limit，也容易把系统级缓解误读为模型能力已恢复。Rep 3 原文的 `showing zero negative activation` 有语义歧义，直译会像是“不出现负激活”；结合上下文应理解为“matched negatives 上零 positive activation”，本文已按这一意图译出。

## 7. 三次重复的总体稳定性

| Case | 三次 type 集合 | 稳定共识 | 主要措辞差异 |
| --- | --- | --- | --- |
| Hook feasibility | 3/3 仅 `student_capability` | thinking disabled 的重复负例误报 + thinking enabled 的相同 case 翻转；不原样依赖。 | evidence scope、固定 mode recheck、selectivity/stability 的侧重点不同。 |
| Distillation | 3/3 仅 `student_capability` | 4/4 both-entity negative 失败 + single-entity negative；上游 control 不代表模型可部署。 | reference/fidelity 细节、限制持续条件、合同/模型/guard 的 release 表述不同。 |
| Conformance | 3/3 仅 `student_capability` | 四个 mismatch 跨 explicit-negative 与 uncertain 两条边界；wiring 不是原因。 | guard 粒度、合同修订、换模型 probe 的方案不同。 |
| Candidate overlap | 3/3 均为 Capability + Direction | 两个不同显式负例均 positive activation，冻结 Hook 不具选择性；Capability 与 Direction 顺序稳定。 | matched probe、recalibration、valid positives + matched negatives 的 recheck 强度不同。 |

总体上，三次重复的**归因主体、类型、决定性事实与 consumer action 均稳定**；差异主要出现在 release/recheck 条件的严格程度和句子压缩方式，没有出现把错误转移给 Reviewer、Compiler 或 route target 的类型漂移。

## 8. 实际 API、tool calls 与终态

- 执行上下文：OpenAI-compatible provider，`https://api.deepseek.com`，模型 `deepseek-v4-flash`，`thinking_mode=enabled`，`temperature=0.2`，`seed=42`，每次最多 4096 output tokens。
- 目标子集共 12 个 Role Run、22 个 provider requests，使用 139,211 input tokens、42,555 output tokens、181,766 total tokens。
- artifact 中实际记录 18 次 `tool_calls`，全部是 `submit_experience_summary`：12 次成功的 terminal submit，另有 6 次非终态结构校验失败，模型随后缩短超长的 `lesson` 或 `applicability` 并重新提交。涉及 Candidate overlap Rep 1、Conformance Rep 2/3、Distillation Rep 1/3、Hook feasibility Rep 2。
- `inspect_experience_evidence` 实际调用为 **0**。结构审计中的 `tool_call_count=0` 专指 evidence tool 调用，不包括 terminal `submit_experience_summary`；因此它与 artifact 中的 18 次 submit 调用并不矛盾。
- 12/12 Run 在 `summary.json` 中均为 `status=completed` 且 `error=null`；`structural_audit.json` 也记录 12 条均完成、type contract/output limits/tool protocol 通过。artifact 顶层没有独立 `status` 字段，因此本文不从顶层字段推断完成状态。
- 没有 evidence tool 失败、重复 evidence view、非法 view 或熔断触达。22 个 provider requests 多于 18 个 submit tool calls，说明 provider turn 与 tool invocation 不是一一对应；本文不从未提交 tool 的 provider turn 推断额外证据读取。

## 9. 最终审阅意见

这 12 条真实 API 轨迹对开发期 `student_capability` 角色验证是稳定且可验收的：它们都在参考、输入、实现和数据四个 gate 已确认后，才用重复或多 case 的直接模型行为建立狭窄边界，并把动作交给 Hypothesis Researcher。尤其重要的是，Distillation 正确区分了“干预通过 control”与“部署模型可实现”，Conformance 正确排除了 deterministic wiring，Candidate overlap 也没有把 no-op 改善当成 Capability 证据。

建议审阅时保留以下非阻断修订意见：

1. 将“guard 解除模型能力限制”统一改成“guard 缓解系统风险；模型限制仍需同边界 recheck 才能解除”。
2. 将“修订 contract/boundary 即 release”收紧为“经独立重新验证、且不回避原必需语义边界的新合同/机制”。
3. 修正 Hook Rep 1 中显式负例与“单侧双实体缺口”的混合括注，以及 Candidate Rep 3 的 `zero negative activation` 歧义。
4. 在 overlap case 中，把“没有 intended positive behavior”尽量只留给 Direction item，使 Capability 严格依赖两个有效显式负例上的重复 false positive，进一步强化双输出独立性。
5. 若面向人类审阅，可把当前较长的单句 lesson 拆成“证据—边界—动作”三小句；不改变事实，但能显著提升可读性。

以上修订不改变当前质量审计的通过结论，也不扩大为 H3 正式结果。
