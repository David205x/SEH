# TASK-007 方案报告 v1

## 1. 当前状态

- `STAGE-001` 已验收，Controller 已能用 `run_id → generation_id → research_attempt_id → candidate_attempt_id / logical_work_id → work_id` 定位轨迹，并为有研究意义的终态生成 typed `TrajectorySettlement`。
- Teacher Role 的硬作用域已经统一为 `role_id + role_contract_version + model_provider + model_id`；`base_prompt_digest` 与 `input_view_digest` 只承担审计 provenance，不作为匹配 Gate。
- `STAGE-002` 的依赖和进入条件已经满足，当前进入“三类经验领域合同”的方案确认阶段。
- 当前代码只有冻结评测样本的 `Experience Set`，尚无 optimizer Research Experience 的类型、生命周期状态或事件投影。
- 本任务尚未修改研究代码，三类经验 schema、provisional/settled 边界和生命周期合法性尚未实现或验证。

## 2. 任务意图

本任务建立 H3 经验系统的最小领域合同，先回答三件事：什么对象可以成为跨 attempt/generation 的经验、三类经验分别描述什么、经验从 provisional 到 settled 后如何通过追加事件被反驳、失效、取代和复查。该合同将作为后续 Experience Store、Curator Work 和 Controller 接入的唯一数据基础。

涉及的 Goal H3 原文为：

> 将已结算轨迹中的 typed verification verdict 与终态转为有 provenance、严格 consumer/scope、可失效和可复查的 role-scoped experience，能够减少跨 attempt/generation 的能力越界、同角色错误复发和方向重走，并提高单位总预算的 useful Candidate yield，同时控制 false pruning 与 held-out utility。

本任务只建立可确定性验证的经验对象与生命周期规则，不在本任务中判断 H3 是否提高搜索收益。

## 3. 实施思路

### 3.1 分离 provisional 总结与跨 generation 事实

回流中的 reject/revise 可以形成 `ExperienceCandidate`，但该对象只属于当前研究轨迹，不能进入后续 generation 的可消费经验集合。只有绑定一个或多个符合条件的 `TrajectorySettlement` 后，才能形成 `SettledExperience`。

这样，当前 Reviewer 的局部判断可以及时被总结，但不会因一次回流直接升级为长期事实；跨 generation 消费只面向已结算经验。

### 3.2 三类经验使用独立 payload 与 scope

1. `StudentCapabilityExperience` 描述目标 Student 在某一责任类别上的已验证能力边界。其消费者固定为 Hypothesis Researcher；scope 记录 Student provider/model、来源 Harness Version、task family 与 responsibility class。
2. `TeacherWorkExperience` 描述某个 Teacher Role 已结算的工作义务、错误模式或有效做法。其消费者必须与记录内的 `TeacherRoleScope` 相同；硬作用域沿用 TASK-006 的四字段定义，Prompt 与 Input View digest 仅进入 provenance 审计字段。
3. `ExperimentDirectionExperience` 描述一个 `problem_direction_id` 已结算的正向或负向研究结果。其消费者固定为 Hypothesis Researcher；scope 记录来源 Student、Harness Version、Evaluator 与 task family，供后续匹配、漂移和 recheck 使用。

三类经验不共享一个自由文本 payload。每类分别定义自身的结论字段、适用范围和 `retry_condition`，从 schema 层阻止消费者把角色经验、Student 能力和研究方向结果混用。

### 3.3 使用离散证据等级，不使用自由浮点置信度

`ExperienceCandidate` 的证据等级固定为 `provisional_observation`；`SettledExperience` 根据绑定的独立 settlement 数量确定为 `single_settlement` 或 `corroborated_settlements`。等级由输入事实复算，不允许总结角色自由填写概率或置信分数。

### 3.4 生命周期采用追加事件与投影

经验生命周期由不可变事件表达：

- `candidate_created`：创建当前轨迹内的 provisional 经验候选；
- `experience_settled`：绑定 qualifying settlement，生成可跨 generation 使用的经验；
- `experience_contradicted`：新 settlement 对既有经验形成直接反证；
- `experience_invalidated`：scope 或来源条件已不再适用；
- `experience_superseded`：新经验取代旧经验，旧记录仍保留；
- `recheck_requested`：要求后续重新验证；
- `recheck_completed`：记录复查 settlement 及其对当前状态的确定性影响。

`ExperienceState` 只由事件序列投影得到。任何状态变化都不得原地覆盖旧记录；非法跳转、重复 sequence、缺少 cause settlement 或 superseding experience 的事件直接拒绝。

### 3.5 provenance 与幂等身份使用 typed 引用

经验来源直接引用 `settlement_id`、source work/event 和 artifact refs，不解析自然语言 verdict，也不从 `settlement_id` 字符串反推 lineage。总结执行的 role/model/contract 与 Prompt/Input View digest 记录为 provenance。

幂等判断使用“经验类型 + 有序 source settlement refs + summarizer role contract”的 typed 复合键直接比较，不生成 hash key。`experience_id` 与 lifecycle event ID 使用共享的可读 ID 生成规则，不使用内容 hash。

### 3.6 保持与 Experience Set 的领域边界

新增能力使用独立的 `optimizer_experience` 包。现有 `search_harness.evolution.experience` 继续只表示一次 Evolution Run 冻结的评测 Example 集合；新类型、Store 和 API 不放入该包，避免两种 Experience 在导入路径和持久化 schema 上混淆。

## 4. 计划实现

### 4.1 `search_harness/evolution/optimizer_experience/domain.py`

新增严格、可序列化的领域类型及当前 schema-only 读取：

- `ExperienceType`：区分 `student_capability`、`teacher_role_work`、`experiment_direction`。
- `ExperienceEvidenceGrade`：表达 `provisional_observation`、`single_settlement`、`corroborated_settlements`，并由来源数量和对象阶段校验。
- `ExperienceStatus`：表达 `provisional`、`settled`、`contradicted`、`invalidated`、`superseded` 和 `recheck_pending`。
- `ExperienceProvenance.source_settlement_ids`：保存支持当前结论的 typed settlement 引用；settled 记录必须非空。
- `ExperienceProvenance.source_artifact_refs`：保存总结实际使用的证据 Artifact Reference。
- `ExperienceProvenance.summarizer_scope`：保存总结角色的 `TeacherRoleScope`，用于确认生产者 role/model/contract。
- `ExperienceProvenance.base_prompt_digest`：保存总结执行的 base Prompt 内容指纹，仅用于审计与漂移诊断。
- `ExperienceProvenance.input_view_digest`：保存总结执行的真实 compact Model Input 指纹，仅用于审计与复查。
- `ExperienceSourceKey.experience_type`：标识本次总结要产生的经验类型。
- `ExperienceSourceKey.source_settlement_ids`：按稳定顺序保存 qualifying settlement 集合，作为幂等来源的一部分。
- `ExperienceSourceKey.summarizer_role_id`：标识执行总结的角色合同。
- `ExperienceSourceKey.summarizer_contract_version`：区分不兼容的总结合同版本。
- `StudentCapabilityScope.student_model_provider`：标识被观察 Student 的模型提供方。
- `StudentCapabilityScope.student_model_id`：标识被观察 Student 模型。
- `StudentCapabilityScope.harness_version_id`：标识产生能力证据的 Accepted Template Version。
- `StudentCapabilityScope.task_family`：限定能力结论适用的任务族。
- `StudentCapabilityScope.responsibility_class`：限定 recognition、decision、adherence、fallback 或 parse 等被验证职责。
- `TeacherWorkScope.teacher_role`：复用 TASK-006 的 `TeacherRoleScope` 作为硬兼容范围。
- `DirectionScope.problem_direction_id`：引用已存在的研究方向身份，不使用内容 fingerprint 生成新身份。
- `DirectionScope.student_model_provider`：记录方向结论对应的 Student provider。
- `DirectionScope.student_model_id`：记录方向结论对应的 Student model。
- `DirectionScope.harness_version_id`：记录方向被验证时的 Harness Version。
- `DirectionScope.evaluator_id`：记录形成方向结果的 Evaluator 身份。
- `DirectionScope.evaluator_version`：记录 Evaluator 合同版本。
- `DirectionScope.task_family`：限定方向结论适用的任务族。
- `StudentCapabilityPayload.capability_verdict`：保存 supported、unsupported 或 inconclusive 的类型化能力结论。
- `StudentCapabilityPayload.observation`：保存被 settlement 证据支持的简洁能力观察。
- `StudentCapabilityPayload.applicability`：描述能力结论在哪些输入条件下适用。
- `StudentCapabilityPayload.retry_condition`：描述何种变化或新证据应触发复查。
- `TeacherWorkPayload.obligation`：保存该角色需要遵守或修正的具体工作义务。
- `TeacherWorkPayload.guidance`：保存后续同 scope Role Run 可执行的工作指导。
- `TeacherWorkPayload.applicability`：限定该工作经验适用的任务条件。
- `TeacherWorkPayload.retry_condition`：描述何时需要重新核对该经验。
- `ExperimentDirectionPayload.outcome`：保存 locally_supported、locally_refuted、student_infeasible、implementation_failed、globally_regressed 或 useful 的类型化方向结果。
- `ExperimentDirectionPayload.summary`：保存该方向及其结算结果的紧凑描述。
- `ExperimentDirectionPayload.applicability`：限定方向结论适用的条件。
- `ExperimentDirectionPayload.retry_condition`：描述何时应重新探索该方向。
- `ExperienceCandidate`：组合 provisional identity、typed scope/payload、source work/event 与 summarizer provenance；其 schema 不允许被标记为 settled。
- `SettledExperience`：组合稳定 `experience_id`、来源 candidate、typed scope/payload、consumer、settled provenance 与 evidence grade；其 consumer 必须符合经验类型。
- `ExperienceLifecycleEvent`：保存 event ID、连续 sequence、event type、目标经验、cause settlement refs 与 superseding/recheck refs。
- `ExperienceState`：保存由事件投影得到的 candidate、settled record、当前 status 和生命周期关系。
- `project_experience_events()`：校验事件顺序、合法状态转换、引用完整性、重复事件内容一致性和 append-only replay。

所有 `from_dict()` 只接受本任务建立的当前 schema，不增加旧字段 alias 或兼容回退。

### 4.2 `search_harness/evolution/optimizer_experience/__init__.py`

只导出三类 payload/scope、候选/settled 记录、生命周期事件和纯投影函数，形成与 frozen Experience Set 独立的公共 API。

### 4.3 `search_harness/evolution/identifiers.py`

新增 `new_experience_candidate_id()`、`new_experience_id()` 与 `make_experience_event_id()`。三个接口沿用可读时间/随机后缀或显式序号组合，不使用 hash 派生或 hash 校验。

### 4.4 `CONTEXT.md`

补充 `Experience Candidate`、`Student Capability Experience`、`Teacher Work Experience`、`Experiment Direction Experience` 与 `Experience Lifecycle Event` 的领域定义，并明确它们与现有 `Experience Set`、`Evidence` 和 `Research Experience` 的关系。

### 4.5 `docs/architecture/evolution.md`

记录 provisional 与 settled 的激活边界、三类 experience 的 consumer/scope 关系、append-only 生命周期以及 typed source key 的幂等含义。

### 4.6 开发检查与测试

- 新增 `tests/evolution/optimizer_experience/test_domain.py`，覆盖三类 schema、consumer/scope 不变量、provisional 越权拒绝、settled 来源要求、离散 evidence grade 和生命周期合法/非法转换。
- 新增 `cvpr_workspace/checks/check_stage_002_experience_contract.py`，固定运行代表性的 positive/negative settlement、provisional-to-settled、contradiction、invalidation、supersession、recheck 与 replay 场景。
- 在 `cvpr_workspace/入口清单.yaml` 登记 TASK-007 的 `stage_check`；检查只作为本任务的开发验收证据，不承担 H3 搜索收益验证。

## 5. 盘点结果

### 5.1 盘点范围

- `search_harness/evolution/control/domain.py`
- `search_harness/evolution/control/controller.py`
- `search_harness/evolution/control/transitions.py`
- `search_harness/evolution/identifiers.py`
- `search_harness/evolution/experience/`
- `search_harness/evolution/research/roles/provenance.py`
- `search_harness/evolution/research/roles/contracts.py`
- `search_harness/evolution/control/research_role_effects.py`
- `docs/architecture/evolution.md`
- `CONTEXT.md`

### 5.2 直接观察事实与方案影响

- `TrajectorySettlement` 已保存 typed scope、classification、terminal code、lineage、source event/work/verdict 和 artifact refs。它能够作为 settled experience 的权威来源，因此本任务直接引用 settlement，不再建立第二套轨迹或 verdict schema。
- `ControlJournal` 已采用连续 sequence、追加写入和 replay 投影，且 `ControlArtifactStore` 将大结果放在 journal 外。经验生命周期可以沿用相同事件化边界，但需保持独立领域类型，后续再由专用 Store 持久化。
- `search_harness/evolution/experience/sets.py` 只负责冻结 Dataset Example；它与 H3 的 optimizer Research Experience 职责不同，因此新增独立 `optimizer_experience` 包。
- `CandidateReviewerInput.historical_experience` 仍是 `list[str]`，Controller 固定传空列表。该入口没有 typed scope，也不是当前任务的实现基础；正式迁移属于 STAGE-003 的 consumer projection 工作。
- 当前只有 `TeacherRoleScope` 是可复用的经验硬作用域；Student capability scope 与 direction scope 尚无统一类型，因此本任务需要首次定义这两类 scope，但不在本任务中实现检索匹配或失效策略。
- 当前 `problem_direction_id` 已是可读、generation-local 的权威方向身份，经验记录可直接引用它，不需要生成 failure fingerprint 或 hash ID。
- 现有角色产物已保存 Teacher role/model、`base_prompt_digest` 与 `input_view_digest`。这些字段可直接进入 summarizer provenance；其中两个 digest 继续只用于审计，不进入 consumer hard scope。
