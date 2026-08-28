# TASK-007 v7 真实归因质量审计

## 1. 审计边界

本审计复用与 v1 相同的 18 个历史负向 artifact case，通过真实 `deepseek-v4-flash` Teacher API 执行 30 个 Experience Summarizer Run。历史 artifact 和本次输出只用于 TASK-007 开发诊断，不构成 H3 Claim、正式实验或 Goal 验收证据。

人工审计同时检查：主要因果层、经验类型、route discipline、证据保真、行动义务、适用边界、工具调用和终态结构。`pass` 表示当前 case 的主要输出可直接作为无状态 Experience Draft；`partial` 表示核心事实可用但类型或稳定性仍需修正；`fail` 表示没有形成可消费输出或会投影到错误类型。

## 2. 执行与工具结果

- 18 个 case 共执行 30 个真实 Role Run；29 个获得合法 `ExperienceSummary`，1 个因连续 6 回合达到输出长度上限而失败。
- 共发生 70 次 provider request，累计 301,266 input tokens、127,186 output tokens、428,452 total tokens。
- evidence 工具调用 33 次，33 次成功，0 次非法 ref/view/selector；v1 为 51 次尝试、23 次成功、28 次失败。
- evidence directory 消除了合法调用空间猜测。没有设置工具调用次数上限，模型可分别读取同一 view 的不同 selector；所有单次返回仍受条数和字符边界约束。
- terminal submit 共尝试 45 次，其中 15 次先因 `lesson` 超过 schema 的 600 字符上限失败，另 1 次因生成 JSON 截断失败。前 15 次均经 validator 反馈修正；JSON 截断案例持续耗尽剩余回合。
- 29 个完成 Run 均通过当前结构合同；30 个 Run 的 evidence 工具协议均通过，29 个完成 Run 满足 case 的工具期望。

## 3. 逐 case 归因结论

| Case | 结论 | 直接观察 |
| --- | --- | --- |
| `evidence_revise_corpus_confound` | pass | 三次都把结论落到未验证 corpus sufficiency 和不可满足的 success condition，没有归责 Reviewer 或 Student；`teacher_work` 与 `experiment_direction` 的取舍虽不稳定，但都指向正确消费层。 |
| `evidence_reject_no_differential_effect` | partial | 正确识别 3/4 未搜索且唯一搜索也出现在 untreated control，明确要求 differential effect；但将“被干预方向没有因果效应”写成 `student_capability`，违反该 case 的上游设计归因边界。 |
| `evidence_reject_harmful_overtrigger` | fail | 模型反复在 upstream design 与 Student capability 之间重新权衡，未及时提交；唯一 submit 被截断，连续 6 回合均因 length 结束，最终无 Experience Draft。 |
| `hook_feasibility_student_instability` | partial | 三次都保留 single-entity negative 的重复误判与 `thinking_mode` 翻转，术语未再漂移；一次生成 `student_capability`，两次生成 `teacher_work`，主要因果层正确但类型稳定性不足。 |
| `distiller_not_distillable_model_boundary` | pass | 正确区分 intervention evidence 与 production evaluator realizability，保留 4/4 boundary failure，并形成 capability boundary 与必须加入负例 probe 的实验义务。 |
| `conformance_activation_budget_implementation` | pass | 三次均只生成 Compiler `teacher_work`，明确要求 compiled-in rollout-local budget；v1 的额外 Student capability 已消失。 |
| `conformance_empty_passage_projection` | pass | 只生成 Compiler `teacher_work`，把空 passage 定位为 data-flow/projection 实现错误，没有再写成 Student capability。 |
| `conformance_positive_action_not_applied` | pass | 只生成 Compiler `teacher_work`，覆盖 defer、feedback 与 consumed flag 的缺失 action wiring。 |
| `conformance_semantic_evaluator_boundary` | pass | 三次均识别 structurally faithful Hook 下 semantic evaluator 跨越 negative/uncertain boundary；输出在 capability 与 Distiller 修订间合理分配，没有归因于 action wiring。 |
| `conformance_query_coverage_projection` | pass | 只生成 Compiler `teacher_work`，明确 first-only query 不能投影为 both，并保留 positive defer 义务；修复了 v1 的错误 consumer。 |
| `conformance_missing_fact_model_misclassification` | partial | 正确路由到 Mechanism Distiller 并要求缺失另一实体 decisive record 时保持 positive；但只形成 `teacher_work`，对“partial relevance 不是 decisive fact”的适用边界表达仍偏窄。 |
| `candidate_reject_intrinsic_grounding_predicate` | pass | 三次稳定识别 single-passage predicate 过强、correct-answer recall/稳定性/成本损失；没有引入 prior knowledge，第三次工具核查也保持 cross-passage contract 边界。 |
| `candidate_reject_hook_false_positive_scope` | pass | 三次均识别 activation 只落在 contract negatives、无 activation-attributed benefit 和约 48% 额外成本；没有归因于 Compiler。 |
| `candidate_reject_no_attributed_utility` | pass | 正确分离 activation path 与 no-op variance，并把 false defer、零修复收益及约 271k token 成本写成 evaluation obligation。 |
| `candidate_reject_low_precision_retrieval` | pass | 正确保留 1/7 有益、3/7 违反 negative rule、4/7 仍错误，并要求 activated/no-op 分开聚合；没有再称其为 contract-conformant activation。 |
| `candidate_reject_two_false_positive_activations` | pass | 正确保留唯一两次 activation 均为 contract negatives、其中一次 correct-to-wrong 且没有 activation-driven improvement。 |
| `candidate_reject_selectivity_and_cost` | pass | 正确把 out-of-scope regression、flat aggregate 与约 93% token 增长合并为 selectivity/cost 义务。 |
| `candidate_validation_query_coverage_defect` | pass | 只生成 Compiler `teacher_work`，要求 rejected attempt 真正修改 coverage check 和 one-shot defer，而不是原样重交。 |

人工汇总：14 个 case 为 `pass`，3 个为 `partial`，1 个为 `fail`。该汇总是开发期质量判断，不是 Goal 指标。

## 4. v7 已解决的问题

- 工具目录把 ref、view 和 selector 的合法空间显式提供给模型，evidence 调用失败由 28 次降为 0。
- 不再设置 invocation hard cap；本轮没有因“需要继续读说明”被程序拒绝。
- activation budget、empty passage、positive action、query coverage 和 Candidate Validation 五类明确 implementation defect 均只投影为 route-target `teacher_work`。
- `thinking_mode`、implementation conformance、query/passage 和 prior-knowledge 边界在本轮审计样本中保持原术语。
- 经验类型总量从 v1 的 capability 26、direction 24、teacher work 18，收敛为 capability 7、direction 13、teacher work 14；不再机械填满 taxonomy。

## 5. 尚未解决的问题

### 5.1 Prompt 未显式给出输出字段上限

Schema 已限制 `lesson <= 600`、`applicability <= 400`，Prompt 只说 concise，没有给模型可执行的字符预算。15 次初次 submit 超出 lesson 上限，最长为 733 字符；这些可避免的修复回合增加 token，并放大终态失败概率。

### 5.2 Prompt 没有阻止重复权衡

`evidence_reject_harmful_overtrigger` 的模型 reasoning 在 upstream design 与 Student capability 之间多次往返，6 次 request 全部以 length 结束。Prompt 需要要求完成一次分层检查后立即选定主要层并提交，禁止反复重开同一类型判断；这不是工具调用次数限制。

### 5.3 “faithful implementation”仍被误当成 capability 的充分条件

`evidence_reject_no_differential_effect` 已给出 untreated control 无差异，`evidence_reject_harmful_overtrigger` 已给出 clean falsifier 与 complete-evidence over-trigger。两者首先否定的是 generic patch 的因果方向或适用条件。Prompt 仍允许模型因“实现 faithful + 多次行为”跳到 Student capability，缺少“先排除干预设计自身无效或过宽”的明确门槛。

## 6. TASK-007 当前结论

v7 已验证 evidence directory、无 invocation hard cap、implementation-to-teacher-work 和术语保真方案有效，工具接口问题可以视为解决。但真实 API 仍有 1/30 终态失败和 1 个完成 case 的明确类型误归因，不能将 TASK-007 标记为已验收。

下一步只需要修订 Experience Summarizer Prompt 与对应 Prompt 测试：写明字段字符预算、一次性完成因果选择、把无 differential effect / clean falsifier / harmful over-trigger 优先归入 upstream design。无需修改证据工具、输入输出字段、adapter 或 Runner。
