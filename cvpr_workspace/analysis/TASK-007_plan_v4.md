# TASK-007 方案报告 v4

## 1. 当前状态

- `STAGE-001` 已验收，负向决策及其上游 Role Output、Trial、Probe、Conformance 和 Candidate 结果均可从 Work lineage 与 Artifact Reference 定位。
- 当前代码没有 H3 Experience Summarizer；Observer Timeline 的 summary model 只改写单条事件展示文本。
- Teacher Role 通用 Runner 已提供严格 Input/Output Contract、角色工具装配、紧凑 Model Input 和统一 provenance artifact。
- sub-agent 已阅读三个历史 Evolution Run 的实际事件链和负向案例，完成决策点归因与所需内容审计。
- 尚未修改研究代码，也尚未验证 Experience Summarizer Prompt 的真实模型行为。

## 2. 任务意图

本任务实现 Experience Summarizer 的最小输入、受限核查工具、Prompt 与输出合同。第一版仍从 reject 或等价 blocked/not-distillable 决策点开始，但不把决策点、决策角色或 Controller 后续路由直接当成根因；当初始紧凑内容不足时，Summarizer 可以按需核查少量上游合同或过程证据。

涉及的 Goal H3 原文为：

> 将已结算轨迹中的 typed verification verdict 与终态转为有 provenance、严格 consumer/scope、可失效和可复查的 role-scoped experience，能够减少跨 attempt/generation 的能力越界、同角色错误复发和方向重走，并提高单位总预算的 useful Candidate yield，同时控制 false pruning 与 held-out utility。

TASK-007 只验证“默认给总结角色看什么、归因不清时允许核查什么、Prompt 如何判断、输出什么”。它不接入 Controller 自动触发、Experience Store、既有经验检索或跨 generation 生命周期。

## 3. 实施思路

### 3.1 一种无状态总结产物

本任务只输出 `ExperienceDraft`，不增加 provisional/settled、confidence、invalidation 或 supersession 字段，也不决定该总结何时生效。

### 3.2 区分触发、路由目标与根因

- `trigger` 是造成负向路由的决策点，例如 `evidence_reviewer.reject` 或 `promotion_gate.failed`。
- `route_target_role` 是当前 Controller 已选择的下一修正角色，例如 Hypothesis Researcher、Mechanism Distiller 或 Compiler；它只是已有路由提示。
- 根因由 Experience Summarizer 结合决策内容和按需证据判断。Prompt 不得把 trigger 角色或 route target 自动写成责任角色。

第一版仍以决策点建立 Summary Input。若证据只支持“信息不足、上游约束不完整或数据不可检索”，Summarizer 应输出相应的有限 lesson 或空列表，不把问题归给当前决策角色。

### 3.3 Initial Model Input 保持五个字段

`ExperienceSummaryInput` 直接包含：

- `trigger`：由 adapter 根据真实负向路由生产；Prompt 用它理解当前发生了什么决策。
- `route_target_role`：由 Transition 的实际后续路由生产；Prompt 将其作为下一处理角色提示，而不是责任事实。
- `direction`：由当前 Failure Direction 生成有界文本；Prompt 用它判断结论是否评价研究方向。
- `attempt`：由当前 Hypothesis、Mechanism 或 Candidate implementation summary 生成有界文本；Prompt 用它区分具体尝试和整个方向。
- `evidence`：由 adapter 从决策 output 与 deterministic summary 生成 `ref -> observation` 映射；每个 ref 同时是受限核查工具的授权入口。

Initial evidence 最多 5 条，每条 observation 有长度上限。初始输入不包含完整 Role Artifact、transcript、rollout、Candidate workspace、完整报告或代码。

### 3.4 默认零工具，归因混杂时使用一个受限工具

Experience Summarizer 只注册：

`inspect_experience_evidence(evidence_ref, view, selectors=[])`

- `evidence_ref` 必须是本次 Input `evidence` 中已有的 key，不能传文件路径。
- `view` 只允许：
  - `upstream_contract`：返回与当前结论直接相关的上游 Hypothesis、Mechanism、Evaluator contract、known limit 或 Compiler claim；
  - `decision_trace`：返回一条 Trial、Probe 或 Conformance 的裁剪因果链；
  - `candidate_comparison`：返回聚合 Candidate delta 与少量代表 improvement/regression 对照。
- `selectors` 只能从 Initial evidence 暴露的 case/finding/example ID 中选择，最多三个。
- 一次调用最多返回三条、单条不超过 1500 字符、总计不超过 4000 字符；一次 Summary Run 最多调用两次。
- passage 只返回与判因直接相关的至多两个摘录，每个不超过 400 字符。
- 工具永久排除完整 Prompt、transcript、conversation、Model Input、raw reasoning、resource config、完整 rollout/report、workspace/code 和 hash/digest。

Conformance 等初始摘要充分的场景应直接输出；Evidence Review、Hook Feasibility 或 Candidate Review 存在上游条件、数据充分性或机制归因混杂时才调用工具。

### 3.5 Prompt 先做责任层检查，再生成经验

System Prompt 在生成 lesson 前依次检查：

1. 当前决策角色是否遗漏或误读了已经可见的证据；
2. 上游 contract、Hypothesis、Mechanism 或实验成功条件是否不充分或过强；
3. Candidate/Compiler implementation 是否违反已确认 contract；
4. 数据、Retriever、Probe coverage 或环境充分性是否使结论暂不可归因。

只有能说明“失败事实 → 被违反或过强的条件 → 适用责任层 → 下次可执行义务”时才输出 lesson。证据不足、不同责任层仍无法区分或只能复述 decision 时输出空列表。

允许的经验角度仍为：

- `student_capability`：Probe/行为证据直接说明 Student 对某项 responsibility 的能力边界；
- `teacher_work`：证据能够形成 route target role 下次应执行的具体义务；若 route target 不是合理归属，不生成该类型；
- `experiment_direction`：证据评价研究方向或机制条件本身，而非单个实现错误。

每种 `experience_type` 最多一条。

### 3.6 Output 只保留四个业务字段

`ExperienceDraft` 包含：

- `experience_type`：Output Validator 用于类型唯一性与 teacher-work 路由约束，后续类型化处理据此选择经验类别。
- `lesson`：后续投影时实际呈现的经验内容。
- `applicability`：限制 lesson 的适用条件，避免局部失败被无条件泛化。
- `evidence_refs`：Output Validator 立即校验其来自 Initial evidence 或该 ref 的授权工具返回。

`ExperienceSummary` 只包含 `items`；允许空列表，最多三条，且类型不得重复。

### 3.7 后续 TODO

- 归因输入迭代：记录真实 Summary Run 的工具调用率、调用后归因改变率和空输出率；若某类上游输出高频必需，再讨论将其固定投影到 Initial Input。若误归因集中来自当前未覆盖的上游信息，再扩展相应白名单 view，不建立通用全链路输入。
- 既有经验对照：在 Experience Store/检索任务中，让 Summarizer 读取与目标角色和 scope 匹配的已有 experience，判断当前结果是 `duplicate`、对旧经验的修正，还是新经验；届时再讨论比较输入、输出动作和持久化语义，本任务不预设字段。
- 生命周期：provisional、跨 generation 生效、失效与 recheck 在 STAGE-002 后续任务结合实际 Summary/Store 行为继续确定，本任务的 Draft 不承担这些状态。

## 4. 计划实现

### 4.1 `search_harness/evolution/research/roles/contracts.py`

- 新增 `ExperienceSummaryInput`：只含 `trigger`、`route_target_role`、`direction`、`attempt` 和 `evidence`。
- 新增 `ExperienceDraft`：只含 `experience_type`、`lesson`、`applicability` 和 `evidence_refs`。
- 新增 `ExperienceSummary`：只含 `items`。
- 注册 `experience_summarizer@1`。
- 校验文本长度、Initial evidence 数量、类型唯一性、teacher-work route target 约束和 evidence 引用合法性。

### 4.2 `search_harness/evolution/research/experience_summary.py`

- 为已确认负向来源实现决策点白名单 adapter。
- adapter 根据现有 Transition 生成 `route_target_role`，不把它命名为责任角色。
- 实现授权 evidence registry 和三个 `view` 的裁剪逻辑；只读取 typed output 与确定性 summary 的白名单字段。
- 实现工具调用次数、selectors、条数和字符预算。
- 实现 Input/Output 交叉校验；禁止整体序列化任意 Artifact 进入 Model Input 或 Tool Result。

### 4.3 `search_harness/evolution/research/resources/base.py`

- 在 `TeacherResourceConfig` 中增加 Experience Summary 专用只读资源配置。
- 在 `TeacherResources` 中装配授权 evidence registry，并在绑定 `ExperienceSummaryInput` 时校验 Input evidence keys 与 registry 一致。
- Experience Summarizer 的初始 `resource_context` 保持空对象；资源只能通过受限工具读取。

### 4.4 `search_harness/evolution/research/tools.py`

- 注册唯一工具 `inspect_experience_evidence`。
- 工具只接受 evidence ref、三种 view 和有界 selectors，调用 `experience_summary.py` 的裁剪逻辑。
- 工具不接受路径、任意查询、页码扩展或自由文本检索。

### 4.5 `harness_templates/teacher/experience_summarizer/`

- `harness.json`：只声明 Prompt、Role Contract Output 和 `inspect_experience_evidence`。
- `tools/runtime/component.py`：复用共享 built-in Teacher tool factory。
- `prompt/system.md`：固化四层责任检查、三类经验边界、工具使用条件和空输出规则。
- `prompt/user.md`：只呈现五字段 Initial Input 与空 resource context。
- `prompt/component.py`：序列化已验证 Input，不读取资源。
- `output/component.py`：使用现有 Role Contract Output 适配方式。

### 4.6 检查与验证

- 新增 `tests/evolution/research/test_experience_summary.py`：覆盖所有负向来源 adapter、route target、三个工具 view、授权 ref、selector、调用次数、返回长度、非法引用和空输出。
- 更新 `tests/evolution/research/roles/test_loader.py`：确认模板只装配一个受限工具和 `experience_summarizer@1`。
- 新增 `cvpr_workspace/checks/check_stage_002_experience_summary.py`：使用历史 Run 裁剪 fixtures 核对决策点默认输入、按需上游核查和 sentinel 隔离。
- Prompt 行为需要真实 Teacher API 验证；实现与确定性检查完成后，再单独申请运行 Evidence Review、Hook Feasibility、Conformance 和 Candidate Review 代表输入的重复检查。

TASK-007 不修改 Controller Work、Effect、Transition、Experience Store 或运行预算。Experience Summarizer 的自动触发与角色预算在下一原子任务接入 first-class Summary Work 时一起实现。

## 5. 盘点结果

### 5.1 盘点范围

- `runs/evolution/20260815_qwen3-8b_hook_feasibility/`
- `runs/evolution/20260806_qwen3-8b/`
- `runs/evolution/20260803/`
- `search_harness/evolution/control/transitions.py`
- `search_harness/evolution/research/roles/`
- `search_harness/evolution/research/resources/`
- `search_harness/evolution/research/tools.py`
- `harness_templates/teacher/`
- `cvpr_workspace/analysis/TASK-007_run_attribution_audit_v1.md`

### 5.2 直接观察事实与方案影响

- Evidence Reviewer revise 案例需要上游 Hypothesis success condition 与失败 Trial 的检索结果，才能区分 Reviewer 问题、成功条件设计和 corpus sufficiency；因此决策点保留为默认输入，但增加上游合同与决策轨迹 view。
- Hook Feasibility needs-research-revision 案例需要 evaluator contract 与 repetition label matrix，才能区分 contract ambiguity 和 Student evaluator 稳定性；因此 Probe Tool Result 只返回 contract 与矩阵，不返回完整 prompt/conversation。
- Conformance revise-implementation 案例的 compact summary 基本足够，只需按需核对 Compiler claim 与单条 finding；因此工具不是强制调用。
- Candidate Reviewer reject 案例需要 Mechanism relevant rule 和少量 regression causal slice，才能判断问题属于机制条件还是实现；因此 Candidate view 返回聚合 delta 与最多三条对照，不返回完整报告。
- sub-agent 审计确认决策者、Controller route target 和根因责任经常不同，因此字段从 `responsible_role` 改为 `route_target_role`，Prompt 必须执行多层因果检查。
- 现有 Role 工具体系能够通过 runtime resource store 提供受限视图，无需把完整 Artifact 预先注入 Model Input；由工具白名单、授权 ref、调用次数和字符预算共同限制上下文增长。
