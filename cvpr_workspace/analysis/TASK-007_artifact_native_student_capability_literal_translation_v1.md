# TASK-007 Artifact-native Student Capability 原文与忠实翻译 v1

## 1. 说明

本文收录最终采用输入协议下的 12 条 `student_capability` 真实 API 终态：Hook Feasibility 3 条、Mechanism Distillation 3 条、Conformance 3 条、Candidate Review overlap 3 条。

中文仅忠实翻译原输出，不补充、修正或强化模型原意。原始 Role Artifact 分别位于：

- `cvpr_workspace/analysis/task_007_attribution_validation_v7/runs/hook_feasibility_student_instability/`
- `cvpr_workspace/analysis/task_007_attribution_validation_v7/runs/distiller_not_distillable_model_boundary/`
- `cvpr_workspace/analysis/task_007_attribution_validation_v6/runs/conformance_semantic_evaluator_boundary/`
- `cvpr_workspace/analysis/task_007_attribution_validation_v8_overlap_final/runs/candidate_reject_hook_false_positive_scope/`

## 2. Hook Feasibility：single-entity / both-entity negative boundary

### Run 1

原文 lesson：

> Under valid probes with thinking modes enabled and disabled (2 repetitions each), the Student model when used as the Hook evaluator cannot reliably realize the negative boundary of the three-way pre_final decision contract: disabled mode never emits negative (2/2 false positives on trial_002 and trial_003) and enabled mode flips trial_002 between negative and positive within mode.

忠实翻译：

> 在 thinking mode 为 enabled 和 disabled 的有效 probe 条件下（每种各重复 2 次），Student 模型用作 Hook evaluator 时，无法可靠实现三路 pre_final 决策合同的 negative 边界：disabled 模式从不输出 negative（trial_002 和 trial_003 均为 2/2 false positive），enabled 模式则在同一模式内令 trial_002 在 negative 与 positive 之间翻转。

原文 applicability：

> Frozen Hook model as three-label evaluator of pre_final decisions (two-entity comparative finalized on first-entity-only evidence = positive; single-entity factoid / both-entity query = negative); thinking modes enabled and disabled; reference, inputs, implementation, and repetition count validated.

忠实翻译：

> 冻结 Hook 模型作为 pre_final 决策的三标签 evaluator（基于仅覆盖第一实体的证据完成的双实体比较 = positive；单实体 factoid / 同时涉及两个实体的 query = negative）；thinking mode 为 enabled 和 disabled；reference、输入、实现和重复次数均已验证。

### Run 2

原文 lesson：

> Under the pre_final three-label Hook decision contract (two-entity comparison finalized on first-entity-only evidence vs single-entity factoid vs both-entity query), the Student model when used as the Hook evaluator cannot reliably label single-entity factoid negatives as negative: with thinking disabled it false-positives trial_002 and trial_003 (2/2 each), and with thinking enabled it flips trial_002 within mode.

忠实翻译：

> 在 pre_final 三标签 Hook 决策合同（基于仅覆盖第一实体的证据完成的双实体比较、单实体 factoid、同时涉及两个实体的 query）下，Student 模型用作 Hook evaluator 时，无法可靠地把单实体 factoid 负例标为 negative：thinking disabled 时，它对 trial_002 和 trial_003 均产生 false positive（各 2/2）；thinking enabled 时，它在同一模式内翻转 trial_002。

原文 applicability：

> Frozen Student/Hook model; pre_final decision phase; three-label decision contract with single-entity factoid negative class; thinking_mode enabled/disabled probes at 2 repetitions.

忠实翻译：

> 冻结 Student/Hook 模型；pre_final 决策阶段；包含单实体 factoid negative 类别的三标签决策合同；thinking_mode enabled/disabled probe，各重复 2 次。

### Run 3

原文 lesson：

> Under the three-label feasibility evaluator distinguishing two-entity comparisons finalized on first-entity-only evidence (positive) from single-entity factoid or both-entity-query negatives on real trial prefixes, the Student model when used as the Hook evaluator cannot reliably realize the negative boundary: disabled thinking mode false-positives trial_002 and trial_003 in 2/2 repetitions each, and enabled mode is unstable on trial_002.

忠实翻译：

> 在真实 trial prefix 上，三标签 feasibility evaluator 用于区分基于仅覆盖第一实体的证据完成的双实体比较（positive）与单实体 factoid 或 both-entity-query 负例时，Student 模型用作 Hook evaluator 无法可靠实现 negative 边界：disabled thinking mode 对 trial_002 和 trial_003 各在 2/2 次重复中产生 false positive，enabled 模式在 trial_002 上不稳定。

原文 applicability：

> Real trial prefixes; three-label feasibility decision contract; enabled and disabled thinking modes; two probe repetitions; explicit negatives are single-entity factoids and both-entity queries.

忠实翻译：

> 真实 trial prefix；三标签 feasibility 决策合同；enabled 与 disabled thinking mode；两次 probe 重复；显式负例是单实体 factoid 和同时涉及两个实体的 query。

## 3. Mechanism Distillation：query-target verification boundary

### Run 1

原文 lesson：

> Under the mechanism activation decision on two-entity comparison transcripts, the Student model when used as the Hook evaluator cannot reliably verify query-target naming: it labeled the both-entities-queried explicit negative as activating in 4/4 generations across two contract wordings and the single-entity negative as activating 2/2 in contract 002.

忠实翻译：

> 在双实体比较 transcript 的 mechanism activation 决策条件下，Student 模型用作 Hook evaluator 时，无法可靠验证 query target 的命名情况：在两种 contract wording 下，它在 4/4 个 generation 中把“query 同时涉及两个实体”的显式负例标为 activating，并在 contract 002 中把单实体负例在 2/2 次中标为 activating。

原文 applicability：

> Frozen Student model probed as Hook evaluator on the mechanism activation decision; two-entity comparison questions; explicit-negative inputs where the query names both entities or only the first entity; two distinct contract wordings.

忠实翻译：

> 冻结 Student 模型作为 Hook evaluator 接受 mechanism activation 决策 probe；双实体比较问题；query 命名两个实体或只命名第一实体的显式 negative 输入；两种不同的 contract wording。

### Run 2

原文 lesson：

> Under the three-way Hook decision contract across two distinct contract wordings, the Student model when used as the Hook evaluator cannot reliably classify explicit-negative query targets: it mislabeled both-entities-queried inputs as positive in 4/4 generations, factually asserting the query named only the first entity when it named both, and mislabeled the single-entity negative as positive 2/2.

忠实翻译：

> 在两种不同 contract wording 的三路 Hook 决策合同下，Student 模型用作 Hook evaluator 时，无法可靠分类显式 negative 的 query target：它在 4/4 个 generation 中把“query 同时涉及两个实体”的输入误标为 positive，并在 query 实际命名两个实体时错误断言其只命名第一实体；它还在 2/2 次中把单实体负例误标为 positive。

原文 applicability：

> Frozen classification task through the production model backend as Hook evaluator for the one-shot deferral mechanism's pre_final phase (comparison detection, passage-evidence judgment, query-target verification); explicit-negative inputs: both-entities-queried and single-entity queries.

忠实翻译：

> 冻结 classification task，经 production model backend 作为 one-shot deferral 机制 pre_final 阶段的 Hook evaluator（comparison detection、passage-evidence judgment、query-target verification）；显式 negative 输入为 both-entities-queried 与单实体 query。

### Run 3

原文 lesson：

> Under a two-entity, single-retrieval comparison contract requiring the evaluator to verify that the query names only the first entity, the Student model when used as the Hook evaluator cannot reliably classify the query target: it mislabeled both-entities-queried inputs as positive in 4/4 generations across two contract wordings (asserting the query named only the first entity) and mislabeled the single-entity negative as positive in 2/2 in one wording.

忠实翻译：

> 在双实体、单次 retrieval 的比较合同下，evaluator 需要验证 query 是否只命名第一实体；Student 模型用作 Hook evaluator 时，无法可靠分类 query target：它在两种 contract wording 的 4/4 个 generation 中把 both-entities-queried 输入误标为 positive（断言 query 只命名第一实体），并在其中一种 wording 的 2/2 次中把单实体负例误标为 positive。

原文 applicability：

> Frozen Student model probed as Hook evaluator on the validated two-entity, single-retrieval decision contract; repeated matched probes across two distinct contract wordings; query-target verification and explicit-negative classification.

忠实翻译：

> 冻结 Student 模型作为 Hook evaluator，在已验证的双实体、单次 retrieval 决策合同上接受 probe；跨两种不同 contract wording 的重复 matched probe；query-target verification 与显式 negative 分类。

## 4. Conformance：explicit-link / no-commitment boundary

### Run 1

原文 lesson：

> Under the pre_final boundary condition where the most recent retrieval explicitly states the requested attribute together with the committed entity or phrase and no search tool call followed that retrieval, the Student model used as the Hook evaluator cannot reliably emit the negative/pass-through decision: it repeatedly returns positive instead, injecting feedback and consuming the one-shot deferral budget.

忠实翻译：

> 在 pre_final 边界条件下，最近一次 retrieval 显式陈述了所请求属性及其对应的 committed entity 或 phrase，并且该 retrieval 后没有 search tool call；Student 模型用作 Hook evaluator 时，无法可靠输出 negative/pass-through 决策：它反而重复返回 positive、注入 feedback 并消耗 one-shot deferral budget。

原文 applicability：

> Frozen Student model as the pre_final Hook evaluator under the three-way decision contract; observed when returned passages explicitly establish the requested link for the committed entity (negative rule) and for refusal statements committing to no entity (uncertain rule).

忠实翻译：

> 冻结 Student 模型作为三路决策合同下的 pre_final Hook evaluator；观察条件包括返回 passage 为 committed entity 显式建立所请求 link（negative rule），以及 refusal statement 不承诺任何实体（uncertain rule）。

### Run 2

原文 lesson：

> Under the pre_final boundary where the most recent retrieval explicitly states the requested attribute or link for the committed entity, the Student model when used as the Hook evaluator cannot reliably perform negative classification, returning positive instead.

忠实翻译：

> 在 pre_final 边界下，最近一次 retrieval 显式陈述了 committed entity 所请求的属性或 link；Student 模型用作 Hook evaluator 时，无法可靠执行 negative 分类，反而返回 positive。

原文 applicability：

> Verified retrieval tasks at the pre_final decision point where the most recent retrieved passage explicitly states the requested attribute or link for the committed entity; Student model evaluated as the three-way Hook decision evaluator.

忠实翻译：

> 已验证的 retrieval task，位于 pre_final 决策点；最近检索到的 passage 显式陈述了 committed entity 所请求的属性或 link；Student 模型作为三路 Hook 决策 evaluator 接受评估。

### Run 3

原文 lesson：

> Under conditions where the retrieved passages explicitly state the requested attribute or link for the entity the final answer commits to, the Student model when used as the Hook evaluator cannot reliably classify the case as negative and instead classifies it as positive.

忠实翻译：

> 在 retrieved passage 显式陈述了 final answer 所承诺实体对应的请求属性或 link 的条件下，Student 模型用作 Hook evaluator 时，无法可靠把该 case 分类为 negative，反而将其分类为 positive。

原文 applicability：

> Three-way Hook decision task on retrieval-QA examples where the most recent retrieval explicitly states the requested attribute or link for the committed entity, in the thinking mode and input format of the tested trials.

忠实翻译：

> 针对 retrieval-QA example 的三路 Hook 决策任务；最近一次 retrieval 显式陈述 committed entity 所请求的属性或 link；使用被测 trial 的 thinking mode 和输入格式。

## 5. Candidate Review overlap：contract-negative false-positive boundary

### Run 1

原文 lesson：

> Under the pre_final three-way decision contract whose negative_rule classifies joint 'A and B' questions and single-entity questions as NEGATIVE, the Student model when used as the Hook evaluator cannot reliably classify contract-negative real prefixes; it emits POSITIVE on both a joint 'A and B' question and a single-entity question, violating the frozen boundary.

忠实翻译：

> 在 pre_final 三路决策合同下，negative_rule 将 joint “A and B” 问题和单实体问题分类为 NEGATIVE；Student 模型用作 Hook evaluator 时，无法可靠分类 contract-negative 的真实 prefix：它对 joint “A and B” 问题和单实体问题都输出 POSITIVE，违反冻结边界。

原文 applicability：

> Frozen Student model as Hook evaluator on real pre_final QA prefixes; three-way decision contract with negative_rule; joint 'A and B' and single-entity question shapes; no other task conditions validated.

忠实翻译：

> 冻结 Student 模型作为真实 pre_final QA prefix 上的 Hook evaluator；包含 negative_rule 的三路决策合同；joint “A and B” 与单实体问题形态；没有验证其他任务条件。

### Run 2

原文 lesson：

> Under the pre_final three-way decision contract with negative_rule on real question prefixes, the Student model when used as the Hook evaluator cannot reliably classify explicit-negative questions (joint 'A and B' and single-entity forms) as NEGATIVE; it emits POSITIVE instead.

忠实翻译：

> 在真实 question prefix 上带有 negative_rule 的 pre_final 三路决策合同下，Student 模型用作 Hook evaluator 时，无法可靠地把显式 negative 问题（joint “A and B” 与单实体形式）分类为 NEGATIVE；它反而输出 POSITIVE。

原文 applicability：

> Frozen Student-as-Hook evaluator over the pre_final NEGATIVE/POSITIVE/NO-OP decision contract on real question prefixes from the two-candidate evaluation material; explicit-negative cases per negative_rule.

忠实翻译：

> 冻结 Student-as-Hook evaluator，在 two-candidate evaluation material 的真实 question prefix 上执行 pre_final NEGATIVE/POSITIVE/NO-OP 决策合同；显式 negative case 由 negative_rule 定义。

### Run 3

原文 lesson：

> Under the frozen three-way decision contract with negative_rule on real pre-final prefixes, the Student model when used as the Hook evaluator cannot reliably classify explicit-negative questions as NEGATIVE: it emits POSITIVE for both a joint 'A and B' question and a single-entity question, each producing a harmful or wasted deferral.

忠实翻译：

> 在真实 pre-final prefix 上带有 negative_rule 的冻结三路决策合同下，Student 模型用作 Hook evaluator 时，无法可靠地把显式 negative 问题分类为 NEGATIVE：它对 joint “A and B” 问题和单实体问题都输出 POSITIVE，分别导致有害或浪费的 deferral。

原文 applicability：

> Frozen Student model as Hook evaluator; decision contract: three-way hook classification with negative_rule; input class: real pre-final prefixes containing explicit-negative questions (joint A-and-B, single-entity); setting: candidate_review evaluation of the two-candidate deferral mechanism.

忠实翻译：

> 冻结 Student 模型作为 Hook evaluator；决策合同为带有 negative_rule 的三路 Hook 分类；输入类别为包含显式 negative 问题（joint A-and-B、单实体）的真实 pre-final prefix；场景为 candidate_review 对 two-candidate deferral 机制的评估。

## 6. 形态结论

12 条最终输出均采用同一形态：

> Under 条件 X, the Student model [when used as the Hook evaluator] cannot reliably 完成 Y.

其中 X 来自已验证的真实输入、decision contract、thinking mode 或 prefix 范围；Y 只描述 narrow model classification/decision boundary。原文 lesson 没有加入 guard、研究动作、复检、release、cost 或 utility；这些内容也没有通过 applicability 重新引入。
