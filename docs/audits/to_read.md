> 是否可以认定从两组reviewer的门控设置都有问题？我们先来解决researcher-intervention-trial reviewer-evidence reviewer这个循环链路吧。请你结合角色prompt和确定性门控代码用无序列表列出控制逻辑流程



可以认定“两组 Run 暴露出的 Reviewer 门控体系都有问题”，但不能认定“两次 Evidence Reviewer 的判断都错了”。

更准确地说：默认覆盖门槛本身基本合理，问题集中在门控要求没有和选样、修订、证据继承及预算形成确定性闭环。`debug` 中 Reviewer 正确否证了 `post_tool` 方案；`debug2` 中 Reviewer 也正确指出 negative distinct 不足，但系统无法执行它提出的补证义务。

当前 `Researcher → Intervention → Trial Reviewer → Evidence Reviewer` 控制逻辑如下。标记为“确定性”的是程序硬门，其余主要依赖 Prompt 和模型判断。

- Hypothesis Researcher 接收冻结的 Failure Analyst `pattern`。

  - `[Prompt]` 不允许替换或重新解释失败方向，也不负责判断假设是否已经得到支持。
  - `[Prompt]` 必须检查引用轨迹和 Intervention Capability，生成一个可证伪假设。
  - 输出包含：
    - `fork_phase`
    - 1–4 个 `phase_plan`
    - 每个 phase 的 `activation_condition`
    - `instruction`
    - `expected_effect`
    - `max_activations`
    - `evaluation.primary_signal`
    - `success_condition`
    - `falsifier`
    - `applicability`
    - 最多两个 `special_evidence_obligations`
  - `[确定性]` 提交前验证 Researcher 已读取允许的证据并调用 `get_intervention_capabilities`。
  - `[确定性]` phase 不得重复，`fork_phase` 必须等于第一项 phase。
  - `[缺口]` 没有检查 revision 是否弱化了上一版的 `success_condition`，也没有把历史 falsifier 固化为新版本必须保留的回归义务。

  参考：[Researcher Prompt (line 3)](D:/_Project/Agent/search_harness/harness_templates/teacher/hypothesis_researcher/prompt/system.md:3)、[Researcher 输出校验 (line 313)](D:/_Project/Agent/search_harness/search_harness/evolution/research/resources/base.py:313)。

- Researcher 提交假设后，Controller 创建新的 Trial 循环。

  - `[确定性]` 将以下状态全部重置：
    - `trial_count = 0`
    - `assignment_count = 0`
    - `used_assignments = []`
    - `prior_obligation = None`
  - `[确定性]` 只保留基线报告、Failure Artifact 和最新 Hypothesis Artifact 等引用。
  - `[缺口]` Hypothesis revision 后，旧 Trial 虽在 Researcher 修订时可读，但不会进入新版 Hypothesis 的覆盖计数。
  - `[缺口]` 已经验证过的正负边界、历史 falsifier 和已满足的 special obligation 都没有结构化继承规则。

  参考：[Research 完成后的状态重置 (line 114)](D:/_Project/Agent/search_harness/search_harness/evolution/control/transitions.py:114)。

- Trial Selector 为假设选择一个 rollout prefix。

  - `[确定性]` 候选顺序是 Failure Analyst 引用的 rollout，随后是整个 rollout 文件中的其他记录。
  - `[确定性]` Selector 只检查：
    - prefix 的 phase 等于 `hypothesis.fork_phase`
    - 精确的 `example_id/replicate_id/prefix_id` 尚未使用
  - `[确定性]` 找到第一个匹配项就立即返回。
  - `[确定性]` `used_assignments` 只排除完全相同的 assignment。
  - `[缺口]` 不检查：
    - example 是否已经出现过
    - 是否能形成新的 distinct positive/negative
    - 是否满足 `applicability`
    - 是否满足 activation condition
    - 是否满足 Reviewer 的 `next_obligation`
    - 是否覆盖 special evidence obligation
  - `[缺口]` `prior_obligation` 只是拼接到 `trial_objective` 文本中，不参与过滤、排序或选后校验。
  - 因此 Reviewer 即使要求“新的 distinct negative example”，Selector 仍可以选择同一 example 的不同 replicate。

  这是 `debug2` 循环不收敛的直接原因。参考：[Trial Selection (line 50)](D:/_Project/Agent/search_harness/search_harness/evolution/control/intervention_effects.py:50)。

- Intervention Worker 在选定 prefix 上执行冻结假设。

  - `[确定性]` 加载指定 `example_id/replicate_id/prefix_id`，并验证该 prefix 的 phase 与 `fork_phase` 一致。
  - `[确定性]` 将每个 phase 的 condition、instruction 和 expected effect 原样转换为运行指导。
  - `[确定性]` 每个 phase 的 `max_activations` 形成运行时激活预算。
  - `[Prompt]` Worker 读取 phase-local observation，自行完成 activation condition 的语义判断。
  - `[Prompt]` condition 为真时执行最小干预；为假时调用 `continue_without_change`。
  - `[Prompt]` 每次 activation 必须以唯一一个 terminal action 结束。
  - `[确定性]` 如果没有任何 planned phase 被实际到达，结果为 `unsuitable_assignment`；Controller 返回 Selector 继续选样。
  - `[确定性]` 只要某个 phase 被到达，就记为 `executed`；是否产生正确效果交给 Trial Reviewer 判断。
  - `[缺口]` Selector 不预判适用性，因此 assignment budget 可能消耗在不激活或不符合补证目标的 prefix 上。

  参考：[Worker Prompt (line 11)](D:/_Project/Agent/search_harness/harness_templates/teacher/intervention_worker/prompt/system.md:11)、[Intervention Runner (line 45)](D:/_Project/Agent/search_harness/search_harness/evolution/research/intervention/role_runner.py:45)。

- Trial 执行完成后进入单条 Trial Reviewer。

  - `[确定性]` 每个 Trial 都有独立 Trial Reviewer Artifact。
  - `[Prompt]` Reviewer 必须先调用 `get_trial_evidence`。
  - `[确定性]` 提交时校验它确实读取了所分配的完整 Trial，且 `trial_ref` 完全一致。
  - `[Prompt]` 对冻结假设的每个 phase 输出一个 `predicate_observation`：
    - `positive`：activation condition 可观察为真
    - `negative`：可观察为假
    - `uncertain`：现有轨迹无法决定
  - 同时分别记录：
    - `phase_execution`
    - `observed_effect`
    - `outcome_evidence`
  - `[Prompt]` 明确禁止把“发生了行为变化”直接当成任务收益。
  - `[确定性]` observation 的 phase 必须与冻结 `phase_plan` 顺序完全一致。
  - `[缺口]` Trial Reviewer 只审一条轨迹，不负责判断 assignment 是否满足上轮 Evidence Reviewer 提出的跨 Trial obligation。

  参考：[Trial Reviewer Prompt (line 3)](D:/_Project/Agent/search_harness/harness_templates/teacher/trial_reviewer/prompt/system.md:3)、[Trial Review 校验 (line 353)](D:/_Project/Agent/search_harness/search_harness/evolution/research/resources/base.py:353)。

- 每次新增 Trial 后，程序重新构造聚合 Evidence。

  - `[确定性]` 已存在且与冻结假设、`trial_ref` 匹配的 Trial Review 会复用，只执行缺失的 Review。
  - `[确定性]` 程序生成 aggregate observations 和 `coverage_summary`。
  - 当前固定默认门槛为：
    - 总 distinct example 至少 `3`
    - 每个 phase 的 positive distinct example 至少 `2`
    - 每个 phase 的 negative distinct example 至少 `2`
  - `[确定性]` same-example replicate 只增加原始计数，不增加 distinct count。
  - `[确定性]` positive/negative 来自 Trial Reviewer 的 `predicate_label`，而不是 intervention 是否成功。
  - `[缺口]` uncertain 没有最低覆盖要求。
  - `[缺口]` `special_evidence_obligations` 只是复制进 Coverage Summary，没有程序维护的 `resolved/unresolved` 状态。
  - `[缺口]` 程序无法确认某个 Trial 是否真正满足 special obligation，完全交给 Evidence Reviewer 文本判断。

  参考：[Evidence Review 编排 (line 42)](D:/_Project/Agent/search_harness/search_harness/evolution/control/evidence_review_effects.py:42)、[默认覆盖聚合 (line 15)](D:/_Project/Agent/search_harness/search_harness/evolution/research/evidence.py:15)。

- Evidence Reviewer 接收完整聚合输入。

  - 输入包括：
    - 冻结 Hypothesis
    - 所有 Trial Review
    - 程序维护的 aggregate observations
    - `coverage_summary`
    - Trial/Assignment 剩余预算
    - 上一轮 `prior_obligation`
  - `[Prompt]` 程序统计与 Reviewer 语义判断冲突时，以程序统计为准。
  - `[Prompt]` Reviewer 为每个 phase 输出：
    - `supported`
    - `unsupported`
    - `not_reached`
    - `contaminated`
    - `inconclusive`
  - `[Prompt]` 总体决策为：
    - `continue`：再做一个最高价值的区分性 Trial
    - `revise`：需要改变机制、适用范围或支持范围
    - `reject`：因直接反例或污染否决
    - `ready_to_distill`：允许进入蒸馏
  - `[Prompt]` `ready_to_distill` 要求默认覆盖满足、special obligation 已解决、无重要未解释反例，而且主张不得强于证据。
  - `[Prompt]` 必须区分过程效果与任务/安全收益。

  参考：[Evidence Reviewer Prompt (line 28)](D:/_Project/Agent/search_harness/harness_templates/teacher/evidence_reviewer/prompt/system.md:28)。

- Evidence Reviewer 输出会经过确定性门控。

  - `[确定性]` `phase_findings` 必须按冻结 phase 顺序完整提交。
  - `[确定性]` 当 `conclusion_required=true` 时，禁止 `continue`。
  - `[确定性]` 当默认 Coverage 未满足时，禁止 `ready_to_distill`。
  - `[确定性]` `continue` 必须携带 `next_obligation`。
  - `[确定性]` `reject` 和 `ready_to_distill` 不得携带 `next_obligation`。
  - `[缺口]` 没有确定性验证：
    - 所有 phase 是否为 `supported`
    - special obligation 是否真正解决
    - 是否存在未解释 falsifier
    - task-benefit 主张是否超过 outcome evidence
    - `next_obligation` 是否能被当前数据集满足
    - `next_obligation` 是否真的被下一个 assignment 满足

  因此当前硬门实际上只有“默认计数 + 预算 + 输出结构”，其余关键科学判据仍是 Prompt-only。参考：[Evidence 输出硬门 (line 325)](D:/_Project/Agent/search_harness/search_harness/evolution/research/resources/base.py:325)、[EvidenceReview Contract (line 184)](D:/_Project/Agent/search_harness/search_harness/evolution/research/roles/contracts.py:184)。

- Evidence Reviewer 的决定进入 Controller 路由。

  - `continue`：
    - 检查当前 Trial/Assignment 数量未达到上限。
    - 保存 `next_obligation` 为 `prior_obligation`。
    - 回到 Selector。
    - 但 obligation 仍只进入 `trial_objective` 文本。
  - `ready_to_distill`：
    - 直接进入 Mechanism Distiller。
    - 没有额外确定性 special-obligation gate。
  - `revise`：
    - 把完整 Reviewer 输出作为 authoritative feedback。
    - 继续同一 Researcher Session。
    - Researcher 可读取已有 Trial。
    - 产生一个完整的新 Hypothesis。
  - `reject`：
    - 当前与 `revise` 走同一个 `_research_revision` 路由。
    - 不是终止当前研究方向。
    - 因此代码层面 `reject` 与 `revise` 的控制语义基本相同。
  - 新 Hypothesis 提交后：
    - `trial_count`、`assignment_count`、`used_assignments` 和 `prior_obligation` 再次清零。
    - 新版 Coverage 从零开始。

  参考：[Evidence 决策路由 (line 222)](D:/_Project/Agent/search_harness/search_harness/evolution/control/transitions.py:222)、[Hypothesis Revision (line 718)](D:/_Project/Agent/search_harness/search_harness/evolution/control/transitions.py:718)。

- 还有一个实现现状需要纳入链路判断：

  - 代码存在 `continue_reviewer()`，能够延续 Evidence Reviewer Session。
  - 但正式 `EvidenceReviewEffects.review()` 当前每轮调用的是新的 `role_runner.run()`。
  - 它会重新传入全部 Trial Review 和 Coverage，而不是实际复用 Evidence Reviewer 对话 Session。
  - 因而 Evidence Reviewer 的延续性主要依赖结构化输入和 `prior_obligation`，不依赖此前完整推理上下文。

- 综合判断：

  - 不能简单说“两个 Reviewer 的 3/2/2 门槛都设置错了”。
  - 可以认定“Reviewer 门控与上下游控制逻辑的组合存在系统性缺陷”。
  - 最关键的断点是：
    - Reviewer 提出缺口，但 Selector 不执行该缺口。
    - Revision 可以弱化成功条件，却不继承历史 falsifier。
    - Revision 清空 Coverage，却没有证据继承规则。
    - special obligation 只有文本语义，没有确定性状态。
    - `reject` 与 `revise` 路由不区分。
    - Evidence Reviewer 每轮是新调用，连续性弱。
    - 默认门控要求最多 5 个 Trial，而当前常见组合 `3 distinct + 2 positive + 2 negative` 在重复样本下很容易不可达。

因此，这条链路优先要解决的不是先调低 `2 positive / 2 negative`，而是先让 `next_obligation → Assignment Constraint → Trial → Coverage` 成为可验证的闭环。