# TASK-007 方案报告 v2（冗余审查前草案）

## 1. 当前状态

- `STAGE-001` 已验收，负向决策可以通过 Work、Role Output、`TrajectorySettlement` 和 Artifact Reference 定位到具体研究轨迹。
- 当前代码没有 H3 经验总结角色；`models.summary` 只服务 Observer Timeline，把单条事件改写为中文摘要，不负责分析研究行为或产出经验。
- 当前 Teacher Role 已有严格 Input/Output Contract、紧凑 Model Input、角色专用工具和统一 artifact envelope，可直接承载新的经验总结角色。
- 当前进入 TASK-007 方案修订；尚未修改研究代码，也尚未验证经验总结 Prompt 的真实模型行为。

## 2. 任务意图

本任务实现一个最小 Experience Summarizer Role：当现有流程产生 reject 或等价 refusal/blocked 结果时，程序先构造一个紧凑、类型化的负向行为视图，再由该角色判断是否存在可复用经验，以及该经验属于 Student 能力、Teacher Role 工作还是研究方向。

涉及的 Goal H3 原文为：

> 将已结算轨迹中的 typed verification verdict 与终态转为有 provenance、严格 consumer/scope、可失效和可复查的 role-scoped experience，能够减少跨 attempt/generation 的能力越界、同角色错误复发和方向重走，并提高单位总预算的 useful Candidate yield，同时控制 false pruning 与 held-out utility。

TASK-007 只建立经验总结角色、紧凑输入和输出草稿，不实现 Store、检索、跨 generation 投影或 H3 效果判断。

## 3. 实施思路

### 3.1 当前不拆 provisional 与 settled

本任务只生成一种 `ExperienceDraft`。它是一次负向决策的总结产物，不携带 provisional/settled 状态，也不声明自己可以被跨 generation 消费。后续 Store 接入时再根据实际实验需要决定是否增加激活状态。

### 3.2 只在造成负向路由的决策点总结

总结请求绑定造成负向路由的决策 Work，而不是绑定随后执行的 `REJECT_CANDIDATE` receipt，避免同一原因被总结两次。MVP 覆盖：

- Evidence Reviewer 的 `reject`；
- Mechanism Distiller 的 `not_distillable`；
- Hook Feasibility 的负向能力结论；
- Compiler 的 `implementation_blocked`；
- Candidate Validation 或 Conformance 导致的 Candidate rejection；
- Candidate Reviewer 的 `reject`；
- Promotion Gate 的确定性 rejection。

现有协议没有名为 `refuse` 的统一枚举；MVP 将语义等价的 `not_distillable`、`implementation_blocked` 和确定性 Candidate rejection 归入同一负向总结入口。

### 3.3 输入采用程序构造的紧凑行为视图

Experience Summarizer 不接收完整 Role Artifact、完整 transcript、完整 rollout 或任意文件读取工具。程序从当前 Work payload、typed Role Output 和已有 deterministic summary 中抽取三个输入块：

1. `trigger`：说明哪个角色或机制在什么阶段作出了什么负向结论，以及直接原因或后续义务。
2. `research_context`：用简短文本说明当前研究方向和本次被尝试的 hypothesis/mechanism/candidate。
3. `evidence`：最多 8 条带稳定 ref 的行为观察或确定性结果，每条只保留支持负向结论的必要内容。

各来源的抽取规则为：

- Evidence Reviewer：输入 Failure Direction、Hypothesis、Review assessment/key risk、phase findings 和 coverage 结论；不输入完整 Trial Review 列表。
- Mechanism Distiller：输入 Hypothesis、Evidence Review 结论、Distiller decision/obligation 和 coverage 结论；不输入完整 trial artifact。
- Hook Feasibility：输入 Mechanism 目标、phase findings、assessment 与 revision feedback；不输入完整 probe responses。
- Compiler：输入 Mechanism 目标、implementation summary、unresolved risk、decision 与 next obligation；不输入候选文件或 Compiler transcript。
- Candidate Validation/Conformance：输入 Mechanism 目标、Candidate implementation summary、validation errors 或 conformance summary 中的 route/failure 结论；不输入完整 Candidate workspace 或逐条 rollout。
- Candidate Reviewer/Promotion Gate：输入 Candidate Review、Candidate Outcome Digest 的聚合变化与 attribution、Promotion Gate 失败原因；不输入完整 incumbent/candidate reports。

输入构造器对文本长度和 evidence 数量设上限，使任何 artifact 的增长都不会等比例扩大 Model Input。

### 3.4 Experience Summarizer 不提供工具

MVP 的 `harness.json` 不注册工具。角色只能基于程序提供的紧凑视图总结，不能自行读取完整 artifact、轨迹或代码。若紧凑视图不足，应返回空 `items`，由后续开发检查暴露缺口，而不是通过通用读取工具扩大上下文。

### 3.5 Prompt 只从三个角度提炼经验

System Prompt 明确要求：

- 只有行为证据直接说明 Student 在某项 responsibility 上可行或不可行时，才生成 `student_capability`；实现 bug 不能被归因为 Student 能力边界。
- 只有负向结果暴露了触发角色可复用的分析、判断或执行义务时，才生成 `teacher_work`；不能把其他角色的问题写成当前角色经验。
- 只有证据能够评价研究方向本身时，才生成 `experiment_direction`；单个实现失败不能被扩大为方向无效。
- 每条经验必须写成后续消费者可执行的一句 lesson，并给出适用条件和输入中已有的 evidence refs。
- 没有足够依据时输出空列表，不强制生成经验。
- 最多输出 3 条，禁止复述输入、输出泛化口号或推断未观察原因。

### 3.6 输出只保留四个会被使用的字段

`ExperienceDraft` 仅包含：

- `experience_type`：程序据此把草稿送入对应类型的后续处理；允许 `student_capability`、`teacher_work`、`experiment_direction`。
- `lesson`：未来投影给对应消费者的实际经验内容。
- `applicability`：与 lesson 一起投影，用于限制其适用条件，防止一次失败被写成无条件规则。
- `evidence_refs`：程序校验其必须来自本次输入的 evidence refs，用于拒绝无来源总结。

`ExperienceSummary` 只包含 `items: list[ExperienceDraft]`，允许空列表，最多 3 条。

Role Output 不保存 experience ID、status、confidence、consumer、scope、retry condition、invalidation、supersession、usage receipt 或重复的 provenance 字段。Role Runner 已在 artifact envelope 中保存 role/model/contract、Prompt digest、Input View digest、输入、输出与 token usage；后续确定性组件可以从 source Work 和 `experience_type` 派生 consumer/scope，而不是要求模型填写。

## 4. 计划实现

### 4.1 `search_harness/evolution/research/roles/contracts.py`

新增以下严格 Pydantic 合同：

- `ExperienceTrigger.source_role`：Prompt 用它判断负向结论来自哪个角色或确定性机制。
- `ExperienceTrigger.stage`：Prompt 用它区分 evidence、feasibility、implementation、conformance 与 promotion 语义。
- `ExperienceTrigger.decision`：保存直接触发总结的 typed 决策标签。
- `ExperienceTrigger.reason`：保存负向决策的紧凑直接原因。
- `ExperienceTrigger.obligation`：仅在原决策已有后续义务时传入，帮助生成 role-work lesson。
- `ExperienceResearchContext.direction`：说明当前研究方向，供 direction experience 判断使用。
- `ExperienceResearchContext.attempt`：说明本次具体尝试，避免把单个实现和研究方向混淆。
- `ExperienceEvidenceItem.ref`：为输入观察提供可被输出引用的稳定局部标识。
- `ExperienceEvidenceItem.observation`：保存一条有长度上限的行为观察或确定性结果。
- `ExperienceSummaryInput.trigger`：组合本次负向决策。
- `ExperienceSummaryInput.research_context`：组合方向和本次尝试。
- `ExperienceSummaryInput.evidence`：提供最多 8 条实际总结依据。
- `ExperienceDraft.experience_type`：选择三类经验之一。
- `ExperienceDraft.lesson`：保存未来实际使用的经验正文。
- `ExperienceDraft.applicability`：保存 lesson 的适用条件。
- `ExperienceDraft.evidence_refs`：声明 lesson 使用的输入证据。
- `ExperienceSummary.items`：保存 0 至 3 条经验草稿。

注册 `experience_summarizer@1`，Input 为 `ExperienceSummaryInput`，Output 为 `ExperienceSummary`。

### 4.2 `search_harness/evolution/research/experience_summary.py`

- 实现各负向来源到 `ExperienceSummaryInput` 的显式 adapter。
- 只从 typed Role Output、Work payload、Candidate Outcome Digest、validation/conformance summary 和 Promotion Gate 读取白名单字段。
- 对 direction、attempt、reason、obligation、observation 和 evidence 数量设置固定上限。
- 实现输出校验：每个 `evidence_ref` 必须存在于对应输入；重复 lesson 或重复 ref 拒绝。
- 实现 Experience Summarizer 的专用 Model Input renderer，只渲染 `role_input`，`resource_context` 固定为空对象。

### 4.3 `harness_templates/teacher/experience_summarizer/`

- `harness.json`：只装配 Prompt 与 Role Contract Output，不声明工具。
- `prompt/system.md`：固化三类经验的判断角度、归因限制、空输出条件和 3 条上限。
- `prompt/user.md`：只呈现紧凑 `role_input`，不嵌入 artifact 内容或资源路径。
- `prompt/component.py`：调用 `experience_summary.py` 的专用 renderer。
- `output/component.py`：复用现有 Role Contract Output 适配方式。

### 4.4 `search_harness/evolution/control/research_role_effects.py`

新增 `summarize_negative_outcome()`：接收已经构造并验证的 `ExperienceSummaryInput`，使用空 `TeacherResourceConfig` 调用 `experience_summarizer@1`，把统一 Role Artifact 保存到当前 Work 目录。该方法不在本任务中修改 Controller 路由或 Store。

### 4.5 `config/runtime.yaml`

在 `teacher_roles` 中增加 `experience_summarizer` 的角色预算。预算只限制一次紧凑、无工具调用；具体 token 上限按实际 Prompt 与输出规模设置，不复制其他长流程角色预算。

### 4.6 检查与验证

- 新增 `tests/evolution/research/test_experience_summary.py`，覆盖各负向来源的白名单投影、长度上限、无完整 artifact/rollout/transcript、空输出、三类输出和非法 evidence ref。
- 更新 Role Runner 测试，确认 `experience_summarizer@1` 能按通用 artifact envelope 保存输入、输出和 TASK-006 provenance。
- 新增 `cvpr_workspace/checks/check_stage_002_experience_summary.py`，用代表性 rejection fixtures 核对输入内容、Prompt 可见范围和输出协议。
- Prompt 行为需要真实 Teacher API 核对时，使用 evidence、compiler、candidate 三类代表性输入分别重复 3 次；由于会调用外部模型，在执行前单独确认。

## 5. 盘点结果

### 5.1 盘点范围

- `evolution_observer/timeline.py`
- `search_harness/evolution/control/research_role_effects.py`
- `search_harness/evolution/control/transitions.py`
- `search_harness/evolution/research/roles/contracts.py`
- `search_harness/evolution/research/roles/role_execution.py`
- `search_harness/evolution/research/roles/native_chat_runner.py`
- `search_harness/evolution/research/resources/base.py`
- `search_harness/evolution/research/resources/stores.py`
- `search_harness/evolution/research/tools.py`
- `harness_templates/teacher/`
- `config/runtime.yaml`

### 5.2 直接观察事实与方案影响

- 当前没有 Experience Curator 或 Experience Summarizer Role。Observer Timeline Summarizer 的输入只有 category、actor、action、outcome、summary 和 facts，输出是最长 240 字的展示文本且没有 Role Contract 或工具，因此不具备 H3 经验总结语义。
- 通用 Teacher Role Runner 已把 validated role input 与紧凑 resource context 渲染为 Model Input，并持久化 role/model/Prompt/Input View provenance；新角色无需建立第二套运行器或 provenance envelope。
- 当前 Candidate Reviewer、Failure Analyst 等角色已经采用“初始紧凑总览 + 专用工具按需读取”的方式控制上下文，但部分工具可返回完整 case、trajectory 或 diff。经验总结 MVP 不需要探索式读取，因此采用无工具输入更符合本任务边界。
- 当前负向原因分散在 typed Role Output、Work payload、validation/conformance summary、Candidate Outcome Digest 和 Promotion Gate 中；完整 Role Artifact 还包含 resource config、tool calls 和 transcript。白名单 view adapter 能保留决定经验质量的行为结论，同时避免把整个 artifact 放入上下文。
- Candidate rejection 通常先由 Review、Conformance 或 Gate 形成原因，再由 `REJECT_CANDIDATE` Effect 写入 rejection receipt。若两处都触发总结会重复，因此总结请求应绑定前者的因果决策点。
- 当前 Compiler 没有 `refuse` 标签，语义最接近的是 `implementation_blocked`；Mechanism Distiller 的终止负向标签是 `not_distillable`。方案以当前真实协议标签建立 adapter，不新增同义状态。
