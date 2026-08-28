# TASK-007 Student Capability 原始输出与忠实直译

## 1. 说明

本文只转录最终 v5 真实 API 批次中 `experience_type=student_capability` 的终态 payload。每条先保留 Summarizer 的英文原文，再给出尽量贴近句法和模态强度的中文直译。直译不替模型修正事实、范围或 release 条件；问题判断单独放在最后。

这 12 条输出是开发期角色验证结果，不是 H3 正式证据。

## 2. `candidate_reject_hook_false_positive_scope`

### Repetition 1

Artifact：`cvpr_workspace/analysis/task_007_attribution_validation_v5/runs/candidate_reject_hook_false_positive_scope/run_01.json`

**Lesson 原文**

> Frozen semantic Hook model activated positive on two distinct valid explicit contract-negative questions (joint and single-entity); one caused a direct regression, and no intended positive behavior appeared. Narrow boundary: the Hook's positive decision does not separate genuine one-sided two-candidate evidence gaps from explicit contract negatives. Hypothesis Researcher: do not rely unchanged; add a deterministic explicit-negative guard or run a specified recheck before any use.

**Lesson 直译**

冻结的语义 Hook 模型在两个不同、有效、且合同明确规定为负例的问题上激活为 positive（一个 joint question、一个 single-entity question）；其中一次造成直接回归，并且没有出现预期的正向行为。狭窄边界：Hook 的 positive 决策无法区分真正的单侧双候选证据缺口与合同明确规定的负例。Hypothesis Researcher：不要原样依赖；在任何使用前增加确定性的显式负例 guard，或执行指定的复查。

**Applicability 原文**

> Frozen Hook three-way decision on valid real evaluation prefixes with explicit contract-negative joint/single-entity questions. Released if a matched probe shows no positive activation on explicit negatives or a deterministic negative filter precedes Hook activation.

**Applicability 直译**

适用于冻结 Hook 在有效真实评估 prefix 上，对合同明确规定为负例的 joint/single-entity questions 所作的三路决策。如果匹配 probe 显示显式负例上没有 positive activation，或者在 Hook activation 前放置了确定性负例过滤器，则解除该限制。

### Repetition 2

Artifact：`cvpr_workspace/analysis/task_007_attribution_validation_v5/runs/candidate_reject_hook_false_positive_scope/run_02.json`

**Lesson 原文**

> Frozen semantic Hook model over-triggers on explicit contract negatives: on two valid evaluation prefixes (a joint and a single-entity explicit-negative question) it emitted positive activations, one causing a direct regression, with no intended positive behavior. It cannot selectively detect genuine one-sided evidence gaps. Hypothesis Researcher: do not rely unchanged; add a deterministic explicit-negative guard or recheck its selectivity before reuse.

**Lesson 直译**

冻结的语义 Hook 模型在合同显式负例上过度触发：在两个有效评估 prefix 上（一个 joint question 和一个 single-entity 显式负例问题），它都发出了 positive activation，其中一次造成直接回归，并且没有预期的正向行为。它无法有选择地检测真正的单侧证据缺口。Hypothesis Researcher：不要原样依赖；增加确定性的显式负例 guard，或在复用前重新检查其选择性。

**Applicability 原文**

> Semantic Hook three-way decision on two-candidate evaluation prefixes with explicit contract-negative joint and single-entity questions, faithful Candidate wiring. Recheck after adding an explicit-negative guard or recalibrating the Hook so neither case over-triggers.

**Applicability 直译**

适用于语义 Hook 在双候选评估 prefix 上，对合同显式负例的 joint 和 single-entity questions 所作的三路决策，且 Candidate wiring 忠实。增加显式负例 guard，或者重新校准 Hook 使两个 case 都不再过度触发后，重新检查。

### Repetition 3

Artifact：`cvpr_workspace/analysis/task_007_attribution_validation_v5/runs/candidate_reject_hook_false_positive_scope/run_03.json`

**Lesson 原文**

> The frozen semantic Hook model positively activates on explicit contract-negative joint and single-entity questions in two valid evaluation prefixes, one activation causing a direct regression and no intended positive behavior; it does not selectively detect genuine one-sided two-candidate evidence gaps. Do not rely unchanged: add a deterministic explicit-negative guard or recheck Hook selectivity on negatives before reuse.

**Lesson 直译**

冻结的语义 Hook 模型在两个有效评估 prefix 中，对合同显式负例的 joint 和 single-entity questions 产生 positive activation，其中一次 activation 造成直接回归，并且没有预期的正向行为；它无法有选择地检测真正的单侧双候选证据缺口。不要原样依赖：增加确定性的显式负例 guard，或在复用前重新检查 Hook 在负例上的选择性。

**Applicability 原文**

> Applies to the frozen Hook model's decisions on valid evaluation prefixes under the current contract, covering explicit contract-negative joint and single-entity questions. A release/recheck needs valid positive cases with matched negatives showing zero negative activation.

**Applicability 直译**

适用于冻结 Hook 模型在当前合同下对有效评估 prefix 所作的决策，覆盖合同显式负例的 joint 和 single-entity questions。解除限制或复查需要有效正例，以及显示“零 negative activation”的匹配负例。

## 3. `conformance_semantic_evaluator_boundary`

### Repetition 1

Artifact：`cvpr_workspace/analysis/task_007_attribution_validation_v5/runs/conformance_semantic_evaluator_boundary/run_01.json`

**Lesson 原文**

> Frozen Hook evaluator cannot selectively implement 'defer only unsupported committed values': with faithful Hook structure and deterministic action wiring, four valid mismatches deferred explicitly grounded values (explicit-link negative boundary) and treated refusals/bare mentions as committed unsupported values (no-committed-value boundary). Repeated two-boundary over-trigger; do not rely unchanged - add a deterministic guard or recheck the defer boundary.

**Lesson 直译**

冻结的 Hook evaluator 无法有选择地实现“只 defer 缺乏支持的已承诺值”：在 Hook 结构忠实且确定性 action wiring 正确的情况下，四个有效 mismatch 仍 defer 了有明确 grounding 的值（explicit-link negative boundary），并把 refusal/bare mention 当作已承诺但缺乏支持的值（no-committed-value boundary）。这是跨两个边界的重复过度触发；不要原样依赖——增加确定性 guard，或重新检查 defer 边界。

**Applicability 原文**

> Applies to the Hook evaluator's defer decision on valid committed-answer and evidence-gap inputs under the conformance three-way contract. Releases when a recheck with corrected boundary examples or a deterministic guard eliminates over-deferral on explicit negatives and non-commitments.

**Applicability 直译**

适用于 Hook evaluator 在 conformance 三路合同下，对有效 committed-answer 和 evidence-gap 输入所作的 defer 决策。当使用修正后的边界样例进行复查，或者确定性 guard 消除了显式负例和非承诺输入上的过度 defer 时，解除该限制。

### Repetition 2

Artifact：`cvpr_workspace/analysis/task_007_attribution_validation_v5/runs/conformance_semantic_evaluator_boundary/run_02.json`

**Lesson 原文**

> The frozen Hook evaluator cannot realize 'defer only unsupported committed values': four valid mismatches flagged explicitly grounded values as positive and refusals/bare mentions as committed unsupported values, violating both explicit-link negative and no-committed-value uncertain clauses despite faithful Hook and deterministic wiring. Hypothesis Researcher: do not rely unchanged; add a deterministic guard for explicit negatives and evidence-gap refusals, or recheck on a valid probe.

**Lesson 直译**

冻结的 Hook evaluator 无法实现“只 defer 缺乏支持的已承诺值”：四个有效 mismatch 把有明确 grounding 的值标为 positive，并把 refusal/bare mention 当作已承诺但缺乏支持的值；尽管 Hook 与确定性 wiring 忠实，它仍同时违反 explicit-link negative 和 no-committed-value uncertain 条款。Hypothesis Researcher：不要原样依赖；为显式负例和 evidence-gap refusal 增加确定性 guard，或在有效 probe 上重新检查。

**Applicability 原文**

> Scope: Hook-model evaluator on committed-answer/evidence-gap examples in conformance with faithful Hook and deterministic wiring; limit holds for explicit-negative and uncertain clauses. Release only if a valid probe shows discrimination of explicit negatives from positives on both clauses.

**Applicability 直译**

范围：在 Hook 与确定性 wiring 忠实的 conformance 条件下，Hook-model evaluator 对 committed-answer/evidence-gap examples 的判断；限制覆盖 explicit-negative 和 uncertain 条款。只有当有效 probe 显示它在两项条款上都能把显式负例与正例区分开时，才解除限制。

### Repetition 3

Artifact：`cvpr_workspace/analysis/task_007_attribution_validation_v5/runs/conformance_semantic_evaluator_boundary/run_03.json`

**Lesson 原文**

> Frozen Hook-model evaluator cannot realize "defer only unsupported committed values": across four valid cases it treated explicitly grounded values as positive (defer) and refusals/bare mentions as committed unsupported values, false-positive on two required boundaries despite faithful structural Hook and deterministic wiring. Do not rely unchanged; revise the three-way decision contract or add a deterministic guard, then recheck.

**Lesson 直译**

冻结的 Hook-model evaluator 无法实现“只 defer 缺乏支持的已承诺值”：在四个有效 case 中，它把有明确 grounding 的值当作 positive（defer），并把 refusal/bare mention 当作已承诺但缺乏支持的值；尽管结构 Hook 与确定性 wiring 忠实，它仍在两个必需边界上产生 false positive。不要原样依赖；修订三路 decision contract，或增加确定性 guard，然后重新检查。

**Applicability 原文**

> Hook-model evaluator for committed-value deferral under explicit-link negative and no-committed-value uncertain contract clauses. A revised contract/guard must be re-validated on both boundaries, or a different Hook model re-probed on these cases, before reuse.

**Applicability 直译**

适用于 explicit-link negative 和 no-committed-value uncertain 合同条款下、负责 committed-value deferral 的 Hook-model evaluator。复用前，修订后的合同/guard 必须在两个边界上重新验证；或者必须换一个 Hook 模型，在这些 case 上重新 probe。

## 4. `distiller_not_distillable_model_boundary`

### Repetition 1

Artifact：`cvpr_workspace/analysis/task_007_attribution_validation_v5/runs/distiller_not_distillable_model_boundary/run_01.json`

**Lesson 原文**

> The frozen Hook model cannot realize the validated activation contract's required negative boundary: it mislabeled the both-entities-queried negative in 4/4 parse-clean probes across two contract wordings and also a valid single-entity negative, with reference, input, and probe fidelity confirmed. Hypothesis Researcher must not rely unchanged on this Hook evaluator; add a deterministic guard for both-entity negatives or run a specified boundary recheck before reuse.

**Lesson 直译**

冻结的 Hook 模型无法实现已验证 activation contract 所要求的负例边界：在两种合同措辞下的 4/4 次 parse-clean probe 中，它都误标了“两个实体都已查询”的负例，并且还误标了一个有效 single-entity negative；reference、input 和 probe fidelity 均已确认。Hypothesis Researcher 不得原样依赖该 Hook evaluator；为 both-entity negatives 增加确定性 guard，或在复用前执行指定的边界复查。

**Applicability 原文**

> Applies to this Hook model's decision scope on both-entity and single-entity negatives for the one-sided-search task. Upstream control success does not transfer to deployability; reuse requires a recheck with another permitted model or a corrected boundary specification.

**Applicability 直译**

适用于该 Hook 模型在单侧搜索任务中，对 both-entity 和 single-entity negatives 的决策范围。上游 control 成功不能转移为可部署性；复用要求换用另一个获准模型重新检查，或者使用修正后的边界规格。

### Repetition 2

Artifact：`cvpr_workspace/analysis/task_007_attribution_validation_v5/runs/distiller_not_distillable_model_boundary/run_02.json`

**Lesson 原文**

> The frozen Hook model mislabeled valid explicit negatives in 4/4 both-entity-queried probes and also mislabeled a single-entity negative; two contract wordings and parse-clean probe execution rule out parser or wiring defects. The model cannot realize the required negative boundary from the validated activation contract, so Hypothesis Researcher must not rely unchanged on it: add a deterministic guard or run a specified recheck before reusing distillation.

**Lesson 直译**

冻结的 Hook 模型在 4/4 次“已查询两个实体”的 probe 中都误标了有效显式负例，并且还误标了一个 single-entity negative；两种合同措辞和 parse-clean 的 probe 执行排除了 parser 或 wiring defect。该模型无法实现已验证 activation contract 所要求的负例边界，因此 Hypothesis Researcher 不得原样依赖它：增加确定性 guard，或在复用蒸馏结果前执行指定的复查。

**Applicability 原文**

> Scope: the permitted Hook model, three-way distillation of the one-sided-search intervention, valid both-entity-queried and single-entity queried negatives. Limit holds until a recheck on equivalent negatives shows reliable separation, or the negative boundary is moved to a deterministic guard.

**Applicability 直译**

范围：获准 Hook 模型、单侧搜索干预的三路蒸馏，以及有效的 both-entity-queried 和 single-entity-queried negatives。限制持续到等价负例上的复查显示可靠区分，或者负例边界被移交给确定性 guard 为止。

### Repetition 3

Artifact：`cvpr_workspace/analysis/task_007_attribution_validation_v5/runs/distiller_not_distillable_model_boundary/run_03.json`

**Lesson 原文**

> The frozen deployable Hook model mislabeled the contract's required both-entity negative in 4/4 probes and also a single-entity negative, despite valid inputs and two contract wordings ruling out parser/wiring defects. The upstream intervention passed controls, so the Hook model cannot realize the required negative rejection boundary. Hypothesis Researcher: do not rely unchanged; add a deterministic guard or recheck.

**Lesson 直译**

冻结且可部署的 Hook 模型在 4/4 次 probe 中都误标了合同要求的 both-entity negative，并且还误标了一个 single-entity negative；输入有效，且两种合同措辞排除了 parser/wiring defect。上游干预通过了 controls，因此 Hook 模型无法实现要求的负例拒绝边界。Hypothesis Researcher：不要原样依赖；增加确定性 guard 或重新检查。

**Applicability 原文**

> Applies only to this Hook model's three-way decision on explicit both-entity and single-entity negatives from the validated activation contract. A model change, a revised contract boundary, or a deterministic rejection guard would release the limit.

**Applicability 直译**

仅适用于该 Hook 模型依据已验证 activation contract，对显式 both-entity 和 single-entity negatives 所作的三路决策。模型变更、修订后的合同边界或确定性拒绝 guard 会解除该限制。

## 5. `hook_feasibility_student_instability`

### Repetition 1

Artifact：`cvpr_workspace/analysis/task_007_attribution_validation_v5/runs/hook_feasibility_student_instability/run_01.json`

**Lesson 原文**

> Frozen Hook model: with thinking disabled, both valid explicit-negative cases (one-sided two-entity gaps) were repeatedly labeled positive; with thinking enabled, one identical negative flipped across repetitions. The explicit-negative boundary is narrow and unstable, so Hypothesis Researcher must not rely on it unchanged—revise evidence scope or add a deterministic negative guard.

**Lesson 直译**

冻结 Hook 模型：关闭 thinking 时，两个有效显式负例 case（单侧双实体缺口）都被重复标为 positive；开启 thinking 时，同一个负例在重复之间发生翻转。显式负例边界狭窄且不稳定，因此 Hypothesis Researcher 不得原样依赖它——修订证据范围，或增加确定性负例 guard。

**Applicability 原文**

> Only the frozen Hook three-way evaluator on real-prefix, parse-clean one-sided evidence-gap negatives in both thinking modes. Recheck if the decision contract, input scope, or model changes, or after a deterministic guard is added.

**Applicability 直译**

仅适用于冻结 Hook 三路 evaluator 在两种 thinking mode 下，对 real-prefix、parse-clean 的单侧 evidence-gap negatives 所作的判断。如果 decision contract、输入范围或模型变化，或者增加确定性 guard 后，重新检查。

### Repetition 2

Artifact：`cvpr_workspace/analysis/task_007_attribution_validation_v5/runs/hook_feasibility_student_instability/run_02.json`

**Lesson 原文**

> Frozen Hook model cannot reliably realize the explicit-negative boundary of the three-label one-sided two-entity-gap evaluator: both explicit negatives were repeatedly labeled positive with thinking disabled, one identical negative flipped with thinking enabled, and positives stayed stable and parse-clean. Do not rely unchanged: add a deterministic guard or run a fixed-mode repeated negative recheck.

**Lesson 直译**

冻结 Hook 模型无法可靠实现三标签单侧双实体缺口 evaluator 的显式负例边界：关闭 thinking 时，两个显式负例都被重复标为 positive；开启 thinking 时，同一个负例发生翻转；正例保持稳定且 parse-clean。不要原样依赖：增加确定性 guard，或执行固定 mode 的重复负例复查。

**Applicability 原文**

> Frozen Hook three-way decision over real-prefix one-sided two-entity evidence-gap cases in both probed thinking modes. Limit may release only if a fixed-mode repeated probe stably labels both explicit negatives correctly.

**Applicability 直译**

适用于冻结 Hook 在两种已 probe 的 thinking mode 下，对 real-prefix 单侧双实体 evidence-gap cases 所作的三路决策。只有固定 mode 的重复 probe 能稳定、正确地标注两个显式负例时，才可以解除限制。

### Repetition 3

Artifact：`cvpr_workspace/analysis/task_007_attribution_validation_v5/runs/hook_feasibility_student_instability/run_03.json`

**Lesson 原文**

> The frozen Hook evaluator mislabels explicit negatives under the three-way decision contract: with thinking disabled, both valid negative real-prefix cases were positive on every repetition; with thinking enabled, one identical negative flipped across repetitions. Its explicit-negative boundary is neither selective nor stable. Hypothesis Researcher must not rely unchanged on the Hook negative verdict; add a deterministic guard or a specified recheck.

**Lesson 直译**

冻结 Hook evaluator 在三路 decision contract 下误标显式负例：关闭 thinking 时，两个有效负例 real-prefix case 在每次重复中都是 positive；开启 thinking 时，同一个负例在重复之间发生翻转。它的显式负例边界既没有选择性，也不稳定。Hypothesis Researcher 不得原样依赖 Hook 的负例 verdict；增加确定性 guard 或执行指定的复查。

**Applicability 原文**

> Applies only to the frozen Hook model's three-way decision on one-sided two-entity real-prefix cases with explicit negatives; the boundary may be released or rechecked under the same decision contract by a deterministic guard or a specified recheck.

**Applicability 直译**

仅适用于冻结 Hook 模型在含显式负例的单侧双实体 real-prefix cases 上所作的三路决策；在同一 decision contract 下，可以通过确定性 guard 或指定复查解除或重新检查该边界。

## 6. 这些 Capability 输出实际“长什么样”

12 条输出不是单纯的能力事实句，而是统一采用下面的复合模板：

```text
冻结模型主体
+ 直接观察到的重复误分类/翻转
+ 已排除的实现或输入问题
+ 一个狭窄 decision boundary
+ “不要原样依赖”
+ guard / recheck 动作
+ applicability 与 release 条件
```

因此它们更像“带使用策略的 Capability Draft”，而不是纯粹的：

```text
模型在条件 X 下无法稳定区分 Y 与 Z。
```

## 7. 原始输出中真实存在的问题

以下问题来自原输出本身，不是翻译修正：

1. 多条输出把“增加确定性 guard”写成可解除模型能力限制。guard 可以降低系统风险，但不会证明冻结模型能力已经恢复。
2. 多条输出允许通过“修订 contract/boundary”解除限制；如果只是改写定义来绕开必需负例边界，这不构成能力恢复。
3. `hook_feasibility_student_instability` repetition 1 把显式负例括注为“one-sided two-entity gaps”，而真实负例包括 single-entity factoid，原文自身存在类别混写。
4. `candidate_reject_hook_false_positive_scope` repetition 3 的 `zero negative activation` 有语义歧义；原文没有明确说是“负例上零 positive activation”还是“零 negative-label activation”。
5. overlap case 的 Capability lesson 混入了“没有 intended positive behavior”，这项事实更主要服务于 Direction 的效用判断，削弱了两类经验的证据分离。
6. Capability 输出普遍同时承担“事实记录”和“未来研究建议”，所以看起来不像纯粹的 Student 能力边界描述。
