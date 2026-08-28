# TASK-007 真实 Transition、三类 Experience 提取与输入增强方案 v12

## 1. 当前状态

- 当前 Prompt 只用一句话定义三类 Experience，未完整规定结论对象、必需证据、消费者动作、解除条件和互斥规则。
- 当前输入 evidence 为自由文本；当前 Model Context 没有完整角色职责，也没有实际 Transition 语义。
- v10/v11 已提出职责图、结构化 evidence、类型提取和 20 次工具上限，但角色驱动审查发现 route target、Teacher subject 和 source validity 仍存在结构性问题。
- 三位独立 sub-agent 的结论为两个 `conditional_pass`、一个 `fail`；红队阻断已由主 Agent 独立核对成立。
- `candidate_validation_query_coverage_defect` 的真实 source 是 `unchanged_rejected_candidate`，Controller 实际开启新 Research Attempt，当前 fixture 的 `route_target_role=compiler` 不是真实 Transition route。
- v12 取代 v11；当前未执行代码修改，TASK-007 保持未验收。

## 2. 任务意图

本次修订使 Experience Summarizer 只处理有效负向来源，看到真实 decision/Transition、局部 causal neighborhood、结构化因果证据和完整角色职责，并严格区分：Student/Hook 能力边界、某个 Teacher Role 的既有工作义务违反、以及研究方向或评测的后验更新。

涉及 Goal H3 原文为：

> 将已结算轨迹中的 typed verification verdict 与终态转为有 provenance、严格 consumer/scope、可失效和可复查的 role-scoped experience，能够减少跨 attempt/generation 的能力越界、同角色错误复发和方向重走，并提高单位总预算的 useful Candidate yield，同时控制 false pruning 与 held-out utility。

本任务的验收范围是形成 consumer-ready Experience Draft；跨 Run 去重、持久化、invalidation、projection、usage/effect receipt 和实际 recurrence 改善由 STAGE-002 后续任务及 EVAL-H3 验证。

## 3. 实施思路

### 3.1 在模型调用前确定 source eligibility

- `settled_negative` 和有效的负向 provisional decision 可以构造 Experience Draft。
- `invalid_indeterminate`、runtime/provider/protocol failure、reference truth 不可判或无法确认有效负向决定的来源不调用 Summarizer。
- eligibility 由 typed source/settlement/decision adapter 确定，不让模型从自由文本猜测。
- 历史 case 仅作为明确标注的 development fixture，不冒充正式 settled evidence。

### 3.2 使用实际 Decision 与 Transition Context

程序向 Model Context 提供：

- exact typed decision，而不是把不同状态压成泛化 trigger；
- 作出决定的 role/mechanism；
- 已提交 TransitionPlan 的真实 next work 或 terminal；
- 真实 `route_target_role`，只有下一 Work 确实激活该 Teacher Role 时才非空；
- 当前 decision 的 causal-neighbor roles/mechanisms。

删除 `ExperienceSummaryInput` 内从 trigger 固定推导 route target 的字典。全局职责注册表仍让 Summarizer 了解整个 Evolution 的角色边界；每个 Run 只突出与当前 source 相关的 causal neighborhood，减少无关归责候选。

### 3.3 将 Teacher subject 与 route target 分离

`route_target_role` 只表示真实下一路由。Teacher work 的 causal subject 可以是另一 Teacher Role，也可以在当前 Transition terminal 时仍形成未来同角色经验。

因此输出合同升级为 `experience_summary@2`：

- `student_capability` 与 `experiment_direction` 仍含 `experience_type`、`lesson`、`applicability`、`evidence_refs`；
- `teacher_work` 另有必填 `teacher_role_id`，明确经验属于哪个 Teacher Role；
- 非 Teacher-work 类型禁止携带 `teacher_role_id`。

后续 lifecycle 使用 `teacher_role_id` 结合 source Role Identity 形成 hard scope，不解析 lesson 文本，也不再借用 route target 充当经验 subject。

### 3.4 Teacher Work 的严格门槛

只有同时满足以下事实才生成 `teacher_work`：

- 存在该 Teacher Role 在运行前已经拥有的 Role Contract 或程序职责；
- 完成义务所需事实当时已进入该角色的真实紧凑输入或授权工具面；
- 角色未履行该义务；
- 后果由当前 evidence 支持；
- 结论不依赖把试验结果事后解释为新的科学方向。

被路由去修复、适合增加 guard、能够解决问题或 route target 指向某角色，都不是该角色曾犯错的证据。`role_input_sufficiency` 未确认时禁止 Teacher work。

### 3.5 Student Capability 的严格门槛

只有以下条件全部成立才生成 `student_capability`：

- reference/label 可判且有效；
- Student/Hook 收到的 contract input 有效；
- probe/implementation 投影 faithful；
- data/environment 不构成更直接混杂；
- 同一窄 predicate 在相同输入重复，或至少两个等价有效 case 中出现相同直接模型边界。

matched control 只能帮助排除 intervention causal claim，不能单独证明 capability。没有有效正例机会数时，“未 activation”不能成为 capability。空输入、错误 projection、模糊 spec、corpus 缺事实、no differential effect 和单纯无 utility 都禁止 capability。

### 3.6 Experiment Direction 的严格门槛

`experiment_direction` 是 Trial/Candidate outcome 带来的后验研究更新，结论对象是方向、因果主张、机制类别、数据/证据设计或评测：

- treated/control 无 differential effect；
- clean falsifier；
- complete-evidence harmful over-trigger；
- data/corpus/reference/evaluation confound；
- activation-attributed utility 缺失、收益来自 no-op、成本或回归否定原方向。

Lesson 必须包含方向签名、证据带来的 disposition（停止、缩窄、inconclusive 或 conditional continue）、以及合法重访所需的新差异或新证据。实验结果改变研究选择时，即使 Hypothesis Researcher 是下一路由，也不能改写成 Teacher work。

### 3.7 结构化因果输入

顶层仍为 `trigger`、`route_target_role`、`direction`、`attempt`、`evidence`：

- `direction`：被检验的因果主张/机制方向和预期行为；
- `attempt`：实际 actor/机制、执行方式和覆盖，不再重复 validity；
- `outcome`：观察 actor、行为和直接后果；
- `comparison`：两侧条件、差异、重复关系、有效机会数或 activation attribution，可空；
- `boundary_facts`：最多五条 typed assertion，每条含 `kind`、`status` 和紧凑 statement。

`boundary_facts.kind` 只允许：`reference_validity`、`input_validity`、`implementation_fidelity`、`data_sufficiency`、`role_input_sufficiency`。`status` 只允许 `confirmed`、`failed`、`unknown`。Assertion 必须来自 typed verdict、实际 Role Input projection 或授权证据；adapter 不作无来源推断。

### 3.8 三类 Experience 的输出组成

#### Student capability

- Student/Hook subject；
- 有效且 faithful 的条件；
- 重复或多有效 case 的 decisive behavior；
- 窄 capability/stability boundary；
- consumer action：不得原样依赖、增加 deterministic guard，或执行指定 recheck；
- applicability：已证实 scope 和解除/recheck 条件。

#### Teacher work

- `teacher_role_id`；
- 运行前既有职责；
- 当时可见输入下的违反和后果；
- 下次动作与可检查完成标准；
- applicability：Role Contract/工作情境和解除条件。

#### Experiment direction

- direction signature；
- control/falsifier/confound/utility evidence；
- disposition；
- 合法重访条件；
- applicability：机制类别、问题条件或评测设置。

### 3.9 类型顺序与多条输出

1. invalid/indeterminate 在模型调用前拦截。
2. invalid input/projection 禁止 capability；只有严格 Teacher 门槛成立时生成 Teacher work，否则为空。
3. data/reference/evaluation confound 生成 inconclusive direction，或证据仍不足时为空。
4. no differential、falsifier、harmful over-trigger、no activation utility 或 cost/regression 优先 direction。
5. 全部 capability 门槛成立才生成 capability。
6. 全部 Teacher work 门槛成立才生成带 `teacher_role_id` 的 Teacher work。

默认一个主要类型。第二条只有在 subject、decisive evidence atoms 和 future obligation 三者均不同的情况下允许；同一事实和同一动作换类型改写仍算重复。

### 3.10 工具调用策略

- 每 Run 最多 20 次 `inspect_experience_evidence` invocation，第 21 次拒绝；失败调用也计数。
- 20 次是绝对 hard fuse，不是建议预算；Prompt 默认零调用，每个未决门槛读取最小 view，通常 1–3 次成功读取后提交或返回空。
- 不重复同一 `ref/view`；任何 Run 实际达到 20 次都视为质量失败。
- 单次最多三条、单条最多 1500 字符、单次结果最多 4000 字符。

## 4. 计划实现

### 4.1 领域定义与架构

- 更新 `CONTEXT.md`，记录三类 Experience、Trigger Decision Role、Route Target Role、Teacher Work Subject 和 Causal Owner 的规范定义。
- 更新 `docs/architecture/evolution.md`，删除旧“两次工具”描述，写明 20 次 hard fuse、正常最小读取、source eligibility 和实际 Transition context。

### 4.2 Attribution Registry 与 Transition 投影

- 在 `search_harness/evolution/control/` 建立角色职责、确定性机制、负向 decision family 和 Experience consumer 注册表。
- 从真实 TransitionPlan 构造当前 decision/route context；不从 trigger 无条件推导 route target。
- 现有 Transition 测试核对普通 revision、预算耗尽、unchanged rejection 和 terminal 分支。

### 4.3 Experience 合同

- `ExperienceEvidenceObservation` 使用 outcome、可选 comparison 和 typed boundary facts。
- Experience Summarizer 升为 role version 2。
- Experience Summary 升为 output contract version 2，以 discriminated typed Draft 支持 Teacher-work-only `teacher_role_id`。
- 不兼容旧自由字符串 evidence 和隐式 route-target Teacher subject。

### 4.4 Request、Resource 与工具

- Request builder 在调用前校验 source eligibility。
- Model Context 注入全局职责摘要、当前实际 transition/causal neighborhood 和 evidence directory。
- Store 对所有工具 invocation 计数，前 20 次允许、第 21 次拒绝。
- 保留单次 view、selector、条数和字符授权边界。

### 4.5 Prompt

- 写入三类结论对象、严格门槛、consumer action、解除/重访条件和类型顺序。
- 写入 route target 不等于 Teacher subject、repair 不等于 historical fault。
- 写入 boundary facts 权威优先于 attempt 描述；未知或冲突时读取最小 evidence，否则输出空。
- 写入 `lesson <= 500`、`applicability <= 300`、terminal JSON 和第二条独立性规则。

### 4.6 Fixture 与真实 API

- 收紧 18-case rubric 的精确类型集合和 decisive evidence atoms。
- 用真实普通 `validation_failed -> compiler` artifact 替换错误的 unchanged-candidate route fixture；unchanged rejection 另保留为“真实 route terminal/new research attempt，但 causal Compiler subject 可形成 Teacher work”的专门 case。
- 增加 invalid/indeterminate、role-input-sufficiency unknown 和 ambiguous reference 的空输出 case。
- 离线回归后执行 22 次真实 API 定向复核：no-differential、harmful-overtrigger、corpus-confound、Hook-instability、semantic-boundary 和 activation-overlap 各三次；empty-passage、普通 Candidate Validation、intrinsic-direction 和 invalid/insufficient 各一次。

## 5. 盘点结果

- 当前 Prompt 已描述三类名称和部分排除条件，但没有完整提取合同；v10/v11 仍不足以防止同一事实跨类型改写。
- 当前五字段可保留，但 evidence 需要 typed boundary facts 才能可靠支持 capability 和 Teacher-work 的硬门槛。
- Teacher work 的 subject 不能继续隐式借用 route target；真实 Transition 可能 terminal 或进入另一 Research Attempt，但历史 Compiler 工作缺陷仍需要未来同角色消费。
- 当前 candidate-validation fixture 的 route 与 source artifact 不一致，必须更换或拆分。
- 全局职责知识与本地 attribution context 应分层：完整职责摘要提供共同语言，实际 Transition 和 causal neighborhood 限制当前归因候选。
- 用户要求的 20 次上限可以实现为 hard fuse；正常工具使用仍应由最小证据读取规则约束，架构文档必须同步。
- 不需要为 capability 或 direction 增加 subject/status 等输出字段；只有 Teacher work 的 `teacher_role_id` 是当前准确 scope 所必需且有直接后续消费者的新增字段。
