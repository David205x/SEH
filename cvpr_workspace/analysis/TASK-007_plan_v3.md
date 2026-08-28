# TASK-007 方案报告 v3

## 1. 当前状态

- `STAGE-001` 已验收，负向决策可通过 Work、typed Role Output、deterministic summary 和 Artifact Reference 定位。
- 当前代码没有 H3 Experience Summarizer；Observer Timeline 的 summary model 只改写单条事件展示文本，不能复用为经验总结角色。
- Teacher Role 通用 Runner 已提供严格 Input/Output Contract、无工具运行、紧凑 Model Input 和统一 provenance artifact。
- TASK-007 v2 已完成独立 sub-agent 冗余审查；本版本已按逐字段生产者/消费者和真实路由责任删减。
- 尚未修改研究代码，经验总结 Prompt 的真实模型行为尚未验证。

## 2. 任务意图

本任务先实现 Experience Summarizer 的最小可验证合同：针对现有 reject 或语义等价的 blocked/not-distillable 结果，将分散在 Role Output、Work payload 和确定性摘要中的负向行为证据投影成一个固定大小的 Model Input，再输出零至三条有证据引用的经验总结。

涉及的 Goal H3 原文为：

> 将已结算轨迹中的 typed verification verdict 与终态转为有 provenance、严格 consumer/scope、可失效和可复查的 role-scoped experience，能够减少跨 attempt/generation 的能力越界、同角色错误复发和方向重走，并提高单位总预算的 useful Candidate yield，同时控制 false pruning 与 held-out utility。

TASK-007 只验证“给总结角色看什么、怎样输入、Prompt 从哪些角度总结、输出什么”。它不在当前 Controller 中自动调度总结，也不实现 Store、检索、状态或跨 generation 生效；这些能力在本角色合同确认后由 STAGE-002 后续原子任务接入。

## 3. 实施思路

### 3.1 一种无状态总结产物

本任务只输出 `ExperienceDraft`，不增加 provisional、settled、confidence、invalidation 或 supersession 字段，也不判断该总结何时可被消费。它只是负向行为的结构化总结结果。

PLAN-001 要求的 settled 激活、失效与复查仍属于 STAGE-002 后续生命周期任务；TASK-007 不预先为这些机制添加字段。

### 3.2 负向来源按因果决策点建输入

输入 adapter 绑定造成负向路由的决策 Work，不绑定随后写 rejection receipt 的 `REJECT_CANDIDATE` Work，防止同一原因被重复总结。

MVP 为以下真实来源建立 adapter：

- `evidence_reviewer.reject`；
- `mechanism_distiller.not_distillable`；
- `hook_feasibility.needs_spec_revision` 与 `hook_feasibility.needs_research_revision`；
- `compiler.implementation_blocked`；
- `candidate_validation.rejected`；
- `conformance.revise` 与 `conformance.revise_implementation`；
- `candidate_reviewer.reject`；
- `promotion_gate.failed`。

`responsible_role` 不等于 trigger 来源，而由现有后续路由确定。例如 Evidence Reviewer reject 的责任角色是 Hypothesis Researcher，Compiler implementation blocked 的责任角色是 Mechanism Distiller；没有明确修正责任的终止结论使用 `null`。

### 3.3 Model Input 只有五个字段

`ExperienceSummaryInput` 直接包含：

- `trigger`：由 adapter 生产，Prompt 用它识别负向结论类型；值是上述真实路由枚举，因此无需额外 stage、source role 或 decision 字段。
- `responsible_role`：由现有 Transition 后续路由生产；Prompt 只在该值非空时允许生成对应角色的 `teacher_work`。
- `direction`：由当前 `FailureDirection.pattern + applicability` 生成有界文本；Prompt 用它判断证据是否评价了研究方向本身。
- `attempt`：由当前 Hypothesis、Mechanism 或 Candidate implementation summary 生成有界文本；Prompt 用它把一次具体尝试与整个方向区分开。
- `evidence`：由 adapter 从 typed output 和 deterministic summary 白名单字段生成 `ref -> observation` 映射；Prompt 用它作为唯一事实依据，输出校验也用键集合验证引用。

`evidence` 最多 5 条，每条 observation 有固定长度上限。直接原因、revision obligation、assessment、phase finding、validation error、conformance route feedback、Candidate outcome 和 Gate reason 都作为 evidence observation 输入，不建立重复字段。

### 3.4 不提供任何工具或完整 Artifact

Experience Summarizer 的 Harness 不注册工具。角色不能读取 Role Artifact、transcript、rollout、Candidate workspace、完整报告或代码。

adapter 只允许读取以下紧凑内容：

- Evidence Reviewer：assessment、key risk、必要 phase finding 和 coverage 结论；
- Mechanism Distiller：decision、next obligation 与当前 Evidence Review 结论；
- Hook Feasibility：phase finding、assessment 与 revision feedback；
- Compiler：decision、implementation summary、unresolved risk 与 next obligation；
- Candidate Validation/Conformance：validation error 或 conformance summary 中的 failure/route 结论；
- Candidate Reviewer/Promotion Gate：review reason、observed effect、Candidate Outcome Digest 聚合结果和 Gate failure reason。

输入测试会在未允许的 transcript、rollout、resource_config、tool_calls 和大字段中放入 sentinel，确认它们不出现在最终 Model Input。

### 3.5 Prompt 的三个总结角度

System Prompt 只允许从三个角度生成经验：

- `student_capability`：行为证据直接说明 Student 对某项 responsibility 的能力边界；实现错误不能归因为 Student 能力。
- `teacher_work`：负向结果形成了 `responsible_role` 下次应执行的具体义务；其他角色的错误不能写入该角色经验。
- `experiment_direction`：证据评价的是研究方向本身；单个实现失败不能扩大为方向无效。

每条结果必须是后续消费者可直接使用的一句 lesson，带适用条件，并引用输入中的 evidence key。没有可复用结论时输出空列表；每种 `experience_type` 最多一条。

### 3.6 Output 只有四个业务字段

`ExperienceDraft` 包含：

- `experience_type`：Output Validator 用它执行类型唯一性和 teacher-work 责任校验，后续类型化处理据此选择经验类别。
- `lesson`：经验的实际内容，是后续投影时唯一需要呈现的规则或工作指导。
- `applicability`：与 lesson 一起使用，显式限制适用条件，避免将局部失败泛化为无条件规则。
- `evidence_refs`：Output Validator 立即校验其必须来自当前输入 `evidence`，拒绝没有输入依据的 lesson。

`ExperienceSummary` 只包含 `items`；允许空列表，最多三条，且同一 `experience_type` 不得重复。

Role Output 不复制 ID、consumer、scope、role/model provenance、Prompt/Input View digest 或 token usage。通用 Role Artifact 已保存生产运行的输入、输出和 provenance；后续生命周期组件从 source Work 和类型派生自身所需字段。

## 4. 计划实现

### 4.1 `search_harness/evolution/research/roles/contracts.py`

- 新增 `ExperienceSummaryInput`：只含 `trigger`、`responsible_role`、`direction`、`attempt` 和 `evidence`。
- 新增 `ExperienceDraft`：只含 `experience_type`、`lesson`、`applicability` 和 `evidence_refs`。
- 新增 `ExperienceSummary`：只含 `items`。
- 注册 `experience_summarizer@1`，Input 为 `ExperienceSummaryInput`，Output 为 `ExperienceSummary`。
- 校验输入文本长度、evidence 数量与键唯一性；校验输出引用、experience type 唯一性，以及 `teacher_work` 只有在 `responsible_role` 非空时合法。

### 4.2 `search_harness/evolution/research/experience_summary.py`

- 为 3.2 列出的负向来源实现白名单 adapter。
- adapter 直接输出 `ExperienceSummaryInput`，不创建 Trigger、Context 或 EvidenceItem 包装模型。
- 从现有 typed output 和 deterministic summary 逐字段抽取，禁止对任意 artifact 执行整体 `str()` 或 `json.dumps()`。
- 保存输入/输出交叉校验函数：`evidence_refs` 必须属于输入 evidence keys。

### 4.3 `harness_templates/teacher/experience_summarizer/`

- `harness.json`：只声明 Prompt 与 Role Contract Output，`tools` 为空。
- `prompt/system.md`：写入三类经验的归因规则、空输出规则和每类最多一条的限制。
- `prompt/user.md`：只呈现已验证的紧凑 `role_input`，`resource_context` 固定为空对象。
- `prompt/component.py`：序列化 `ExperienceSummaryInput`，不读取资源。
- `output/component.py`：使用现有 Role Contract Output 适配方式。

### 4.4 检查与验证

- 新增 `tests/evolution/research/test_experience_summary.py`：覆盖每个负向来源的字段投影、真实责任角色、长度/数量上限、非法 evidence ref、重复 experience type、teacher-work 责任约束和空输出。
- 更新 `tests/evolution/research/roles/test_loader.py`：确认无工具模板能够装配到 `experience_summarizer@1`。
- 新增 `cvpr_workspace/checks/check_stage_002_experience_summary.py`：用代表性负向 fixtures 核对最终 Model Input 只包含五字段，并通过 sentinel 检查确认完整 artifact 内容不可见。
- Prompt 行为需要真实 Teacher API 验证；实现与确定性检查完成后，再单独申请运行 evidence、compiler、candidate 三类代表输入的 3 次重复，不在未确认情况下调用外部模型。

TASK-007 不修改 `control/domain.py`、`control/transitions.py`、`control/effects.py`、`control/research_role_effects.py` 或 `config/runtime.yaml`。Experience Summarizer 的 first-class Work、自动触发与角色预算在下一原子任务一起接入，避免留下不可达方法或无生产者配置。

## 5. 盘点结果

### 5.1 盘点范围

- `evolution_observer/timeline.py`
- `search_harness/evolution/control/transitions.py`
- `search_harness/evolution/control/research_role_effects.py`
- `search_harness/evolution/research/roles/contracts.py`
- `search_harness/evolution/research/roles/role_execution.py`
- `search_harness/evolution/research/roles/native_chat_runner.py`
- `search_harness/evolution/research/resources/base.py`
- `search_harness/evolution/research/resources/stores.py`
- `search_harness/evolution/research/tools.py`
- `harness_templates/teacher/`
- `cvpr_workspace/analysis/TASK-007_redundancy_review_v1.md`

### 5.2 直接观察事实与方案影响

- 当前 Timeline Summarizer 的输入是单条事件元数据，输出是展示文本，没有 H3 Role Contract 或研究行为视图，因此新建 Experience Summarizer Role，而不扩展 Timeline Summarizer。
- Native Role Runner 只把 system prompt、rendered role input、已注册工具 schema 和终态提交工具交给模型；当模板工具为空且 adapter 不注入完整对象时，旧 Artifact 不会自动进入上下文。
- 负向原因已经存在于 typed Role Output 和确定性摘要中，不需要重新读取完整 transcript 或 rollout；adapter 只投影与归因直接相关的字段。
- 触发角色和责任角色在当前 Transition 中经常不同，因此输入保留程序派生的 `responsible_role`，并删除冗余的 source-role/stage/reason/obligation 包装字段。
- Candidate rejection receipt 是原因决策的后续持久化结果，不是新的总结原因；adapter 绑定因果决策点以避免重复。
- 独立 sub-agent 逐字段审查后，输入由三层包装模型压缩为一个五字段模型；删除了当前没有消费者的 Role Effect 方法、角色预算、专用 renderer 和通用 Runner 重复测试。
