# TASK-007 `Experiment Direction` 真实 API 轨迹中文翻译与审阅摘要

## 1. 审阅范围与证据等级

本文只审阅最终真实 API 批次 `cvpr_workspace/analysis/task_007_attribution_validation_v5/` 中最终输出包含 `experiment_direction` 的 17 条 Run，共 7 个 case group；其中 `candidate_reject_hook_false_positive_scope` 是同时输出 `student_capability` 与 `experiment_direction` 的 overlap case，本文只逐条翻译它的 Direction item，并另行核对两类输出是否独立。

这些 artifact 是 `experience_summarizer@2` 的**开发期角色行为验证**，验证目标是能否把负向研究决策压缩成 consumer-ready Experience Draft。它们不是 Experience Store、跨 Run 复用效果或 **H3 正式实验**的证据，不能据此声称某项研究假设已经通过 H3，也不能把模型生成的摘要当作新的实验观测。

审阅依据：

- 批次摘要：`cvpr_workspace/analysis/task_007_attribution_validation_v5/summary.json`
- 结构审计：`cvpr_workspace/analysis/task_007_attribution_validation_v5/structural_audit.json`
- 质量审计：`cvpr_workspace/analysis/task_007_attribution_validation_v5/quality_audit.md`
- 质量结论：`cvpr_workspace/analysis/task_007_attribution_validation_v5/quality_verdict.json`
- case 输入：`cvpr_workspace/configs/task_007_attribution_cases.json`
- 实际批次的重复次数覆盖：`cvpr_workspace/configs/task_007_attribution_selection_v3.json`（由 `execution_context.json` 明确引用）

结构审计显示，本子集 17/17 完成，17/17 通过 exact type、输出长度、工具期望、view 与工具协议检查。质量审计对 `experiment_direction` 的结论为通过。

## 2. 如何读取输入中的归因信息

每个 Run 的可观察输入由以下部分组成。这里总结的是显式字段支持的决策依据，不是模型隐藏 chain-of-thought，也不复制 raw reasoning。

- `direction`：待检验的机制主张，限定“什么方向”可以被接受、否定或缩窄。
- `attempt`：实际做过的干预及其规模，防止把未执行的设想当成结果。
- `outcome`：观测终点，例如是否搜索、是否答对、是否发生回归。
- `comparison`：使因果判断成立的对照关系，例如 treated 对 source control、Candidate 对 incumbent、activation 对 no-op。
- `boundary_facts`：归因硬门槛。`reference_validity` 确认对照和标签可信；`implementation_fidelity` 确认机制确实被执行，从而排除“实现没跑”的解释；`input_validity` 确认输入属于真实有效前缀；`data_sufficiency` 决定可以下方向结论，还是只能记为受数据环境混杂的 inconclusive。
- source transition：`evidence_reviewer.revise → hypothesis_researcher` 表示证据不足、应回到假设设计；`evidence_reviewer.reject → hypothesis_researcher` 表示当前方向被反证、应重设计；`candidate_reviewer.reject` 的这批 Candidate case 在 Run 输入中没有 `route_target_role`，case 配置将它们标成 `settled_negative`、`next_work_kinds=[reject_candidate]`，所以结论落在 Candidate/方向处置，而不是把失败归给 Reviewer 或 Compiler。

可审计的共同决策结构如下：

`evidence + 边界事实` → 选择适用的 `control / falsifier / confound / activation attribution / cost` → 判断方向效应是否可归因 → `stop unchanged / narrow / inconclusive` → 写出可证伪、可执行的 revisit 条件。

具体而言，匹配对照排除自然行为；clean falsifier 直接检验必要行为；数据缺失保留 confound、阻止强归因；activation/no-op 分解排除聚合波动；成本与回归平衡防止把单点改善误写成净收益。所有处置都应附解除条件，而不把当前负结论无限外推。

## 3. 分 case、逐 repetition 翻译

### 3.1 `evidence_revise_corpus_confound`（3 次）

**输入与归因。** 方向是检验“单侧检索是否导致基于缺失的比较错误”；attempt 是在最终回答前一次性延迟，并要求 Student 搜索第二个命名实体。`trial_004` 忠实查询了 Cia Berg，但返回语料没有成功条件所需的标题数量证据。实现忠实而数据充分性失败，因此只能把结论归为 corpus sufficiency confound；不能归因成 Student 能力失败，也不能说 Evidence Reviewer 造成失败。`revise → hypothesis_researcher` 与“保留未决、修改成功条件或语料条件”一致。

#### repetition 1

- artifact：`cvpr_workspace/analysis/task_007_attribution_validation_v5/runs/evidence_revise_corpus_confound/run_01.json`
- lesson（译）：单侧检索假设仍无定论：`trial_004` 忠实地执行了对 Cia Berg 的第二实体检索，但语料没有返回标题数量证据，因此“单侧检索导致基于缺失的比较错误”这一主张尚未得到验证（完整成功 1/2）。只有当语料能够提供所需的第二实体证据时才应继续；否则不能依赖该检索提示来修复基于缺失的错误。
- applicability（译）：适用于命名实体比较任务中、最终回答前的延迟检索提示；判定因果效应要求语料段落同时含有两个实体的证据。范围限于实现忠实、但语料数据不足的一次性软干预试验。
- 原 evidence ref：`review`

#### repetition 2

- artifact：`cvpr_workspace/analysis/task_007_attribution_validation_v5/runs/evidence_revise_corpus_confound/run_02.json`
- lesson（译）：单侧检索假设——要求 Student 搜索第二个实体能够防止基于缺失的比较错误——仍无定论：`trial_004` 忠实发出了查询，但语料没有返回标题数量证据，因此该试验的成功条件无法判定，基于缺失的结论也不能归因于检索方向。只有在语料包含第二实体证据，或成功条件可测量时才应重访。
- applicability（译）：适用于这一“先检索、后判断”的比较设计，即需要第二实体标题数量证据而语料覆盖不足的场景；不外推到包含所需证据的语料，在后一场景中该检索方向仍未被测试。
- 原 evidence ref：`review`

#### repetition 3

- artifact：`cvpr_workspace/analysis/task_007_attribution_validation_v5/runs/evidence_revise_corpus_confound/run_03.json`
- lesson（译）：最终回答前的一次性第二实体搜索执行忠实（`trial_004` 查询了 Cia Berg），但返回段落缺少成功条件要求的标题数量证据，因此“单侧检索导致基于缺失的比较错误”仍未得到检验。处置：无定论；只有在检索语料确实包含第二实体证据时重访，或把成功标准拆成“搜索执行忠实度”和“证据可获得性”。
- applicability（译）：范围限于该语料上的一次性、最终回答前第二实体搜索及其基于缺失的比较假设。当返回段落含有所需的第二实体证据，或搜索忠实度可以独立于语料证据可获得性进行判断时，再次检查。
- 原 evidence ref：`review`

**重复稳定性。** 三次均稳定输出 `experiment_direction`，共同结论是“实现已执行，但语料不足，所以 inconclusive，而非 reject”。措辞差异主要在重访方案：rep 1 强调更换/补足语料，rep 2 增加可测量成功条件，rep 3 最明确地提出拆分 search fidelity 与 evidence availability。

### 3.2 `evidence_reject_no_differential_effect`（3 次）

**输入与归因。** 方向是让通用 verification context 在最终回答前触发后续搜索；attempt 在四个忠实 positive activation 上插入通用验证块。3/4 直接结束而未搜索，唯一搜索成功也出现在 untreated source control，因此 treated 分支没有 differential action-type effect。reference、fidelity、data sufficiency 均确认，缺失的 negative-stratum coverage 不是拒绝原因；结论应归于通用机制没有可识别因果效应，而非 Reviewer 或 Student。

#### repetition 1

- artifact：`cvpr_workspace/analysis/task_007_attribution_validation_v5/runs/evidence_reject_no_differential_effect/run_01.json`
- lesson（译）：插入通用验证上下文不会促成最终回答前的后续搜索：四次忠实 positive activation 中有三次没有后续搜索就结束，唯一一次搜索成功也发生在未经处理的 source control，treated 分支没有产生差异化的动作类型效应。对这一机制类别停止原样使用；只有重设计触发器，并证明搜索结果来自干预而不是 control 自然行为时才重访。
- applicability（译）：适用于最终回答前、作用在 positive activation 上的通用验证块机制，以相对于匹配 source control 的动作类型差异来评估。再次检查要求触发器产生可归因于 activation、且 control 中不存在的搜索效应。
- 原 evidence ref：`review`

#### repetition 2

- artifact：`cvpr_workspace/analysis/task_007_attribution_validation_v5/runs/evidence_reject_no_differential_effect/run_02.json`
- lesson（译）：在忠实 positive activation 上插入通用验证块不会促成最终回答前的后续搜索：四次 activation 中三次未搜索即结束，唯一搜索成功也出现在对应的 untreated source control，treated 分支没有差异化的动作类型效应。停止原样使用。只有当机制表现出超越 control、可归因于 activation 的搜索，并有明确触发谓词时才重访。
- applicability（译）：范围限于该任务/决策场景中、作用于忠实 positive activation 的通用验证上下文软干预；negative stratum 覆盖缺失不是因果原因。应在具有明确成功谓词、并与匹配 control 比较的精炼上下文干预上再次检查。
- 原 evidence ref：`review`

#### repetition 3

- artifact：`cvpr_workspace/analysis/task_007_attribution_validation_v5/runs/evidence_reject_no_differential_effect/run_03.json`
- lesson（译）：把通用验证块插入忠实 positive activation，并不会促成最终回答前的后续搜索：四次 activation 中三次没有搜索就结束，唯一搜索成功也发生在 untreated source control，因此 treated 分支没有差异化的动作类型效应。停止原样使用该机制。
- applicability（译）：适用于该任务场景中旨在触发最终回答前后续搜索的验证上下文插入；只有重设计后的机制能相对匹配 control 展示差异效应时才重访。
- 原 evidence ref：`review`

**重复稳定性。** 三次在核心数字、matched control 和 `stop unchanged` 上完全稳定。rep 2 对边界最完整，明确排除了 negative-stratum 缺失，并要求显式 trigger predicate；rep 3 最短，省略了该非因果缺口，但没有改变处置。

### 3.3 `evidence_reject_harmful_overtrigger`（3 次）

**输入与归因。** 方向是用通用 evidence-gap patch 促成所需的后续搜索；两个忠实 positive activation 检验预期行为并含完整默认覆盖。clean falsifier 未搜索且错误结束；另一试验在证据完整时过触发，把正确答案改错。fidelity 与 sufficiency 均确认，因而“漏掉目标正例 + 伤害完整证据例”直接反证该通用方向的 selectivity，应停止原样使用，而不是归因给 Reviewer。

#### repetition 1

- artifact：`cvpr_workspace/analysis/task_007_attribution_validation_v5/runs/evidence_reject_harmful_overtrigger/run_01.json`
- lesson（译）：应拒绝原样使用用于促成后续搜索的通用 evidence-gap patch：两次忠实 positive activation 中只有一次触发预期搜索，而一个 complete-evidence case 发生过触发，把正确答案改成错误答案，说明机制没有选择性。只有重设计触发器、加入明确负例防护，并证明其相对匹配 control 有收益且不会伤害完整证据时才重访。
- applicability（译）：适用于 evidence review / trial pipeline 中、旨在促成后续搜索的通用 evidence-gap patch，并限于已测试的 positive 与 complete-evidence case 类型；只有选择性机制通过明确负例验证后才重新检查。
- 原 evidence ref：`review`

#### repetition 2

- artifact：`cvpr_workspace/analysis/task_007_attribution_validation_v5/runs/evidence_reject_harmful_overtrigger/run_02.json`
- lesson（译）：作为后续搜索触发器，通用 evidence-gap patch 不可行：两次忠实 activation 中，它既漏掉目标正例（clean falsifier 立即给出错误最终答案），又在完整证据上过触发，把正确答案改错。处置：停止原样使用；只有触发器能在匹配的“明确缺口”和“完整证据”案例间展示选择性时才重访。
- applicability（译）：适用于完整覆盖下忠实 activation 的通用 evidence-gap 后续搜索触发器；在证明它能同时区分明确缺口与完整证据 case 之前，不应复用。
- 原 evidence ref：`review`

#### repetition 3

- artifact：`cvpr_workspace/analysis/task_007_attribution_validation_v5/runs/evidence_reject_harmful_overtrigger/run_03.json`
- lesson（译）：拒绝原样使用通用 evidence-gap patch：它在两次决定性试验中都被忠实应用，却漏掉一个目标正例（clean falsifier 立即给出错误最终答案），并在完整证据上过触发，把正确答案改错。成对出现的漏触发与有害过触发反证了该方向声称的选择性；停止原样使用，任何重访都必须采用有选择性的触发器。
- applicability（译）：适用于旨在促成后续搜索、并在完整默认覆盖的忠实 activation trial 中评估的通用 evidence-gap 软干预；只有触发器能命中真实缺口，同时不改变完整证据决策时才重访。
- 原 evidence ref：`review`

**重复稳定性。** 三次都保留 clean falsifier、complete-evidence regression 和 selectivity 反证，处置稳定。rep 1 使用了“explicit-negative guarding”措辞，而显式输入只给出 complete-evidence case，不等同于 contract explicit negative；这是轻微术语外移，rep 2/3 的“明确缺口 vs 完整证据”更贴近事实。

### 3.4 `candidate_reject_intrinsic_grounding_predicate`（3 次）

**输入与归因。** 方向要求单个 passage 明确陈述关系后才能提交答案；attempt 是忠实的 two-phase withhold/defer 机制，在同一 225 条记录上与 incumbent 比较。Conformance 已通过，故排除 Compiler 实现缺陷；同集比较与数据充分性确认，故可以把 +0.6pp、14 regressions/15 improvements、stable-correct 下滑、正确检索支持答案被延迟及约 5.6 倍 token 成本归入 predicate 的方向级 trade-off，而不是 Reviewer 错误。

#### repetition 1

- artifact：`cvpr_workspace/analysis/task_007_attribution_validation_v5/runs/candidate_reject_intrinsic_grounding_predicate/run_01.json`
- lesson（译）：严格的 single-passage grounding gate（提交前必须有一个 passage 明确陈述该关系）实现忠实且通过 conformance，但没有净收益：准确率仅 +0.6 个百分点，14 次回归对 15 次改善，token 约增至 5.6 倍，而且多次延迟已有正确检索支持的答案。停止把它原样用作强制 withhold gate；只有选择性 predicate 能避免延迟受支持答案，并把成本控制在可接受范围内时才重访。
- applicability（译）：适用于检索语料上的关系型问答中，强制要求单 passage 明确 grounding 的 withhold gate；不覆盖 soft-signal 或 multi-passage grounding 变体，也不覆盖延迟成本可忽略的设置。
- 原 evidence ref：`candidate_review`

#### repetition 2

- artifact：`cvpr_workspace/analysis/task_007_attribution_validation_v5/runs/candidate_reject_intrinsic_grounding_predicate/run_02.json`
- lesson（译）：single-passage grounding predicate（提交答案前要求一个 passage 明确陈述关系）忠实符合规范，并在相同 225 条记录上评估，但没有净收益：准确率 +0.6 个百分点，14 次回归对 15 次改善，token 约增至 5.6 倍，不稳定性升高，并反复延迟正确且有检索支持的答案。停止原样把该 predicate 用作答案提交 gate；只有新证据能改变这一权衡时才可重访。
- applicability（译）：适用于与 incumbent 在 225 条记录上比较、commit predicate 要求单 passage 明确陈述关系的 two-phase withhold/defer 机制。只有显著提高延迟精度，或用更廉价的 gate 在不承担约 5.6 倍 token 成本的情况下获得准确率收益，才应重访。
- 原 evidence ref：`candidate_review`

#### repetition 3

- artifact：`cvpr_workspace/analysis/task_007_attribution_validation_v5/runs/candidate_reject_intrinsic_grounding_predicate/run_03.json`
- lesson（译）：single-passage grounding（提交前要求一个 passage 明确陈述关系）缺乏支持：与 incumbent 在 225 条记录上比较，准确率仅 +0.6 个百分点，14 次回归对 15 次改善，正确且有检索支持的答案被延迟，stable-correct 降低，token 约增至 5.6 倍。处置：停止原样使用。只有在真正无支持 case 上展示差异收益、保持 supported-answer rate 且成本可接受时才重访。
- applicability（译）：范围限于冻结 Mechanism Spec 下、用于 retrieval-supported QA 的 single-passage grounding / withhold-defer 机制及该 225 条记录比较。合法重访要求单独测量对 unsupported relation 的选择性、不延迟 supported answer，并使成本接近 incumbent。
- 原 evidence ref：`candidate_review`

**重复稳定性。** 三次数字、conformance 边界、supported-answer harm、成本和 `stop unchanged` 均稳定。rep 1 以“mandatory gate”限定最窄；rep 2 侧重整体 trade-off；rep 3 的重访合同最可测。rep 1 applicability 中“延迟成本可忽略的设置”来自范围排除而非现有证据验证，且即便成本可忽略，supported-answer harm 仍存在，阅读时不应把成本当作唯一障碍。

### 3.5 `candidate_reject_hook_false_positive_scope`（overlap，3 次 Direction）

**输入与归因。** 方向是用 semantic Hook 检测真实的单侧双候选证据缺口；Candidate 忠实地在每个 pre-final state 评估，并在 Hook positive 时 defer。两次 positive activation 都落在有效真实前缀中的 contract explicit negatives（joint question 与 single-entity question），一例造成直接回归；改善只出现在 Hook-negative no-op，整体准确率下降且 Hook 成本大幅增加。`input_validity`、`implementation_fidelity` 与 `data_sufficiency` 均确认，因此可以分别形成狭窄 Capability 边界和方向级无效用结论。

#### repetition 1

- artifact：`cvpr_workspace/analysis/task_007_attribution_validation_v5/runs/candidate_reject_hook_false_positive_scope/run_01.json`
- lesson（译）：用于检测真实单侧双候选证据缺口的 semantic Hook：停止原样使用。忠实运行中的 positive activation 只出现在 contract explicit-negative question，没有出现预期正向行为，也没有可归因效用（改善只发生在 Hook-negative no-op）；准确率下降，Hook 成本显著增加。只有机制能对真实缺口进行选择性 activation，并以可接受成本产生经测量的效用时才重访。
- applicability（译）：适用于该双候选评估设置中的 semantic-Hook gap detection。不覆盖带 explicit-negative rule 预过滤的 Hook contract 或其他 decision scope；这些变体需要各自的选择性和效用证据。
- 原 evidence ref：`candidate_review`

#### repetition 2

- artifact：`cvpr_workspace/analysis/task_007_attribution_validation_v5/runs/candidate_reject_hook_false_positive_scope/run_02.json`
- lesson（译）：用于单侧双候选证据缺口的 semantic-Hook detection 没有可归因效用：positive activation 只落在 contract explicit negatives，改善只来自 Hook-negative no-op，准确率下降且 Hook 成本大幅增加。处置：停止原样使用；只有变体展示差异化的 positive-case 收益并把成本控制在可接受范围内时才重访。
- applicability（译）：适用于双候选评估中、在有效前缀上运行的 semantic-Hook evidence-gap detection；只有单独测得 positive-case utility 且 Hook 成本有界，或采用更廉价的选择性机制时才继续。
- 原 evidence ref：`candidate_review`

#### repetition 3

- artifact：`cvpr_workspace/analysis/task_007_attribution_validation_v5/runs/candidate_reject_hook_false_positive_scope/run_03.json`
- lesson（译）：按本次运行方式，用 semantic-Hook gate 识别单侧双候选证据缺口并不可行：每次 positive activation 都命中 contract explicit negative，聚合证据也没有可归因效用——收益只来自 Hook-negative no-op，准确率下降，Hook 成本显著增加。停止原样使用；只有重设计方案能在真实 positive 上测得 activation-attributed benefit，并限制成本时才重访。
- applicability（译）：适用于当前 decision contract 与 evaluation prefix 下的 semantic-Hook 软干预类别。合法重访要求重设计机制，测得 activation-attributed utility、对 explicit negative 零 activation，并保证成本有界。
- 原 evidence ref：`candidate_review`

**Direction 重复稳定性。** 三次均稳定输出第二个 `experiment_direction` item，且坚持“positive 只落在显式负例、no-op 改善不可归因、准确率/成本不利、停止原样使用”。rep 1 最明确排除带 deterministic pre-filter 的新 contract；rep 2 更简洁；rep 3 的重访条件最严格，增加“显式负例零 activation”。

**与 Capability 的独立性。** 同一 artifact 的两个 item 使用相关但不相同的证据切片与消费动作：

- Capability 使用两个有效前缀上的具体分类错误——joint 与 single-entity explicit negative 被判 positive，其中一例直接回归——来限定冻结 Hook model 的狭窄 decision-boundary 缺陷；动作是不要原样依赖该模型，增加 deterministic explicit-negative guard，或做 matched negative recheck。
- Direction 使用“没有 intended positive activation”、改善仅在 Hook-negative no-op、整体准确率下降及约 430k Hook tokens / 总 token 约 +48% 等聚合证据，判断机制没有 activation-attributed utility；动作是停止或重设计该机制，并要求真实正例收益、选择性和有界成本。

因此 Capability 不是用成本/聚合收益来宣称“模型普遍不行”，Direction 也不是仅把两个误分类换个标签复述。两者共享来源，但证据单位、归因对象、处置和解除条件独立，符合 overlap 要求。

### 3.6 `candidate_reject_no_attributed_utility`（1 次）

**输入与归因。** 方向是延迟 evidence-gap 最终答案以诱发定向后续搜索；conformant one-shot Hook 在 75-example 评估的四个 case 中 activation。八次 activation 都未产生新的正确答案，activation case 回归或持平；全部改善来自 no-op path，一次 definitive answer 被误延迟，额外约 271k input tokens。比较已把 activation 与 negative/guard-exit path 分开，所以不能用聚合改善声称机制收益；但 case rubric 也明确“一次 false positive 本身不足以建立 Capability”，本 Run 只输出 Direction。

#### repetition 1

- artifact：`cvpr_workspace/analysis/task_007_attribution_validation_v5/runs/candidate_reject_no_attributed_utility/run_01.json`
- lesson（译）：defer-to-search Hook 缺乏效用：八次 activation 的每次后续搜索都没有产生新的正确答案，activation case 不是回归就是持平，所有改善都来自 no-op path；另有一个 definitive answer 被错误延迟，Hook 成本增加约 271k tokens。处置：停止原样使用；只有选择性 gate 能避开 definitive answer，并由 matched control 证明延迟在扣除成本后提高准确率时才重访。
- applicability（译）：适用于可比的约 75-example 评估中，通过一次性 Hook 延迟 evidence-gap 最终答案以诱发定向后续搜索的机制。不适用于 deterministic guard、已验证的 retrieval augmentation，或后续搜索已被证明能带来新正确答案的设置。
- 原 evidence ref：`candidate_review`

**措辞观察。** lesson 对 activation/no-op、false positive 与成本的区分准确。applicability 的三个排除项是合理的范围保护，但“已验证 retrieval augmentation”是类别性排除，不是本 case 直接比较过的对象；不应读成对这些未测变体的正向背书。

### 3.7 `candidate_reject_selectivity_and_cost`（1 次）

**输入与归因。** 方向是只在 count/possession comparison 出现单侧证据时触发第二实体搜索；Hook 虽在目标 case 上有一次可归因改善，却几乎分类每个 search event，并在 out-of-scope shared-membership case 上 false positive，使 stable-correct 样例回归。整体准确率持平、consistency 与 majority-correct 下滑、10 regressions 对 7 improvements，约 497k Hook tokens 使总成本近乎翻倍（+93%）。target benefit、selectivity harm、聚合回归与成本共同支持缩窄/停止，而单个成功 case 不足以支持采用。

#### repetition 1

- artifact：`cvpr_workspace/analysis/task_007_attribution_validation_v5/runs/candidate_reject_selectivity_and_cost/run_01.json`
- lesson（译）：针对单侧证据 count/possession comparison 的第二实体搜索触发器发生过触发：Hook 几乎分类了每个搜索事件；一个目标 case 得到改善，但 out-of-scope shared-membership false positive 使一个 stable-correct case 回归；准确率持平，consistency/majority-correct 下降，回归多于改善，token 增加 93%。处置：把方向缩窄到已经证明的 activation-attributed benefit 与 selectivity；只有 matched control 显示有界成本下的净准确率增益时才重访。
- applicability（译）：适用于具有单侧证据的 count/possession comparison、由 Hook 语义触发第二实体搜索，并在 Candidate review 中同时评估 activation attribution、回归平衡与成本的场景。
- 原 evidence ref：`candidate_review`

**措辞观察。** lesson 完整保留了“局部改善不等于可采用”的核心权衡。applicability 是名词短语式范围描述，没有复述 lesson 中的停止/重访门槛，单独消费时行动性弱；建议下游把 lesson 与 applicability 作为一体读取。

## 4. 重复共识与跨 case 区分

五个三重复 group 的类型与处置方向稳定，没有一次把方向问题漂移成 Teacher 工作，也没有把 Reviewer 决策本身写成失败原因：

- `corpus_confound`：稳定为 **inconclusive/revise**，不是 reject；差异仅在如何解除数据混杂。
- `no_differential_effect`：稳定为 **stop unchanged**；matched control 是决定性证据。
- `harmful_overtrigger`：稳定为 **stop unchanged / require selectivity**；clean falsifier 与 complete-evidence harm 必须同时保留。
- `intrinsic_grounding_predicate`：稳定为 **stop mandatory gate unchanged**；对照、回归平衡、supported-answer harm 与约 5.6 倍成本共同决定。
- `hook_false_positive_scope`：Direction 稳定为 **no attributed utility / stop unchanged**，并与 Capability 的模型边界动作保持独立。

两个单次补充 case 分别补足了方向判断的两个常见盲点：`no_attributed_utility` 防止把 no-op variance 当收益，`selectivity_and_cost` 防止用单点成功覆盖 false positive、整体退化和高成本。

## 5. 实际 API、工具调用与终态

执行上下文显示，本批使用 `deepseek-v4-flash`（OpenAI-compatible DeepSeek API，thinking enabled，temperature 0.2，seed 42）。仅统计本文 17 条 Direction Run：

- provider requests：26 次；149,538 input tokens、48,350 output tokens、197,888 total tokens。
- 证据工具 `inspect_experience_evidence`：**0 次**。结构审计中的 `tool_call_count=0` 指 evidence 读取工具，而不是说 artifact 没有终态提交。
- `submit_experience_summary`：24 次提交尝试，其中 17 次 `metadata.terminal=true`，对应 17/17 合法终态；7 次 `terminal=false` 都是结构化输出长度校验退回，随后修正并成功提交。
- 7 次非终态提交分布：`corpus_confound` rep 2（lesson 超 500 字符）、rep 3（applicability 超 300）；`no_differential` rep 2（lesson 超 500）；overlap rep 1（Capability applicability 与 Direction lesson 超限）；`no_attributed_utility` rep 1（lesson 超 500）；`selectivity_and_cost` rep 1 连续两次 lesson 超 500。
- 另外有 2 次 provider response 没有提交工具调用，均发生在 overlap rep 1 与 rep 3 的首轮；harness 发出“尚未提交终态”的继续提示后完成。故 26 次 provider request 与 24 次 submit attempt 并不矛盾。
- 没有 evidence tool 失败、重复 `evidence_ref/view`、非法 view 或 20 次熔断触达；17 条均由 `summary.json` 与 `structural_audit.json` 记录为 completed。原始 Run artifact 顶层没有 `status` 字段，不应据此误判未完成。

## 6. 审阅问题与风险提示

未发现阻断性事实漂移。以下为低优先级、建议审阅时留意的问题：

1. `harmful_overtrigger` rep 1 把 complete-evidence control 延伸成“explicit-negative guarding / explicit negatives”，输入并未明确把 complete-evidence case 定义为 contract explicit negative；rep 2/3 的表述更严格贴合证据。
2. `intrinsic_grounding_predicate` rep 1 将“deferral cost negligible”的设置排除在 applicability 外，但现有证据同时包含 supported-answer harm，成本降低本身并不足以解除全部反证。
3. `no_attributed_utility` applicability 排除 deterministic guard 和 validated retrieval augmentation，是保护性范围声明，不代表这些变体已经由本 Run 验证有效。
4. `selectivity_and_cost` applicability 可读性较弱，是压缩的名词短语，缺少独立的 consumer action；实际停止/重访门槛只在 lesson 中。
5. 多条英文 lesson 把证据、处置、重访条件压在一个长句中，虽满足长度合同，但人读时信息密度高；本译文用标点拆分，未改变事实强度。
6. base case 配置中 `evidence_reject_no_differential_effect` 与 `evidence_reject_harmful_overtrigger` 的 `repetitions` 为 1，而最终 v5 实际各运行 3 次。此处不是批次漂移：`execution_context.json` 明确引用 `task_007_attribution_selection_v3.json`，后者对最终批次重复数进行了覆盖。仅凭 base case 文件无法复现最终调度，复核时必须同时读取 selection 文件。

## 7. 结论

17 条 Direction Draft 在开发期角色验证口径下通过：它们能够把显式 evidence 与 control、falsifier、confound、activation attribution 和 cost 联系起来，形成边界明确的 `inconclusive / stop unchanged / narrow` 处置及合法 revisit 条件。最关键的稳定共识是：自然 control 行为不能计作干预收益，no-op 改善不能计作 activation 收益，数据不足不能强归因，单点改善不能覆盖选择性伤害与成本。

该结论只证明 Experience Summarizer 能生成可消费的 Direction Draft；它不证明这些 Draft 已进入 Store、能跨 Run 复用、能提升研究流程，也不构成 H3 正式证据。
