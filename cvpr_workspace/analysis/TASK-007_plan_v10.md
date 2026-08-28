# TASK-007 全局职责上下文、结构化输入与 Prompt 增强方案 v10

## 1. 当前状态

- 当前 Experience Summarizer 只看到 `trigger`、`route_target_role`、`direction`、`attempt`、紧凑 evidence 和 evidence directory。
- 当前 Prompt 提供五层通用因果检查，但没有提供各 Evolution Role 的具体职责，也没有提供主流程与非固定回流关系。
- `route_target_role` 的局部约束存在于输入合同中；完整职责定义与 Transition 语义只存在于 `CONTEXT.md`、架构文档和 Controller 代码，对 Summarizer 不可见。
- 因此当前模型能区分“上游设计、实现、Student、数据”等抽象层，却不能稳定判断某个具体失败违反了 Failure Analyst、Hypothesis Researcher、Evidence Reviewer、Mechanism Distiller、Compiler 或 Reviewer 中哪一方的职责。
- v7 的 evidence directory 和 implementation routing 已通过真实 API 验证；v2 仍有一次终态失败和一次明确上游设计类型误归因。
- v8 已获接受但未实施；v9 增加了 20 次工具上限和结构化 evidence。经本次审查，v9 缺少全局职责与转移上下文，本报告取代 v9。
- 当前未执行 v10 的代码修改，TASK-007 保持未验收。

## 2. 任务意图

本次修订让 Experience Summarizer 在归因前了解完整 Evolution 中各角色或确定性机制“负责什么”，以及负向决定会“从哪里转移到哪里、为什么转移”。模型随后使用当前 outcome、comparison、boundary 和裁剪证据判断真正违反职责的因果层，不能把触发者或下一路由角色直接当作根因。

涉及 Goal H3 原文为：

> 将已结算轨迹中的 typed verification verdict 与终态转为有 provenance、严格 consumer/scope、可失效和可复查的 role-scoped experience，能够减少跨 attempt/generation 的能力越界、同角色错误复发和方向重走，并提高单位总预算的 useful Candidate yield，同时控制 false pruning 与 held-out utility。

本任务仍只产生无状态 Experience Draft，不接入 Controller 自动触发、Experience Store、已有经验合并或跨 generation 生命周期。

## 3. 实施思路

### 3.1 明确三种不同身份

- `trigger_decision_role`：作出当前 typed reject/revise/refuse 的角色；它只是发现并报告问题。
- `route_target_role`：Controller 下一步交付修复工作的角色；它是路由事实，不是根因事实。
- `causal_owner`：其职责、输入、实现或能力边界实际解释失败的角色或机制；由 Summarizer 根据职责图和证据判断，不新增为输出字段。

Prompt 必须先确定 causal owner 所属职责层，再选择经验类型。触发角色与路由目标只能限制可能解释，不能直接决定归因。

### 3.2 注入完整但紧凑的 Evolution Attribution Context

程序向每次 Experience Summarizer 的 `resource_context` 注入同一份模型可见职责与转移上下文：

- `roles`：覆盖 Failure Analyst、Hypothesis Researcher、Intervention Executor、Trial Reviewer、Evidence Reviewer、Mechanism Distiller、Hook Feasibility Reviewer、Mechanism Compiler、Candidate Validation、Conformance Reviewer、Candidate Reviewer，以及 Student/Hook evaluator 的职责边界。
- `deterministic_mechanisms`：覆盖 Trial Selector、Evolution Controller 和 Promotion Gate 的确定性职责，避免把规则或预算行为归给 Teacher。
- `negative_transitions`：覆盖 Evidence revise/reject、Distiller needs-evidence/not-distillable、Hook spec/research revision、Compiler blocked/needs-evidence、Candidate Validation reject、Conformance 分层 revision、Candidate Reviewer revision/reject 和 Promotion Gate failure 的来源、目标与路由语义。
- `experience_consumers`：明确 Student capability 与 experiment direction 后续只供 Hypothesis Researcher，Teacher work 只供对应 Teacher Role。

每项只写一句职责或路由语义，不包含 Prompt、Artifact、代码、完整合同、历史结果或自由审计字段。整个上下文设置固定字符预算，防止变成架构文档复制。

### 3.3 由单一程序注册表维护上下文

职责和负向转移上下文不硬编码在 Prompt 文本中，而由程序注册表提供。输入合同的 trigger/route 校验和 Model Context 使用同一注册表；现有 Transition 测试增加一致性检查，避免 Prompt、合同和 Controller 路由各维护一套互相漂移的映射。

职责注册表描述 ownership，不替代 Controller Transition 实现。Summarizer 只能使用它判断“谁有权负责什么”，仍必须用当前 evidence 证明具体根因。

### 3.4 保留五字段顶层输入并结构化 evidence

顶层仍为 `trigger`、`route_target_role`、`direction`、`attempt`、`evidence`。`evidence` 的每个 ref 值改为：

- `outcome`：决定性失败结果；
- `comparison`：对照、重复、activation-attributed delta 或 before/after 差异，可空；
- `boundary`：已确认的 contract、input、implementation 或 data/environment 边界，可空。

这三个字段分别被归因流程直接消费，不增加 verdict、confidence、scope、status 或其他未被当前任务使用的字段。每个观察设置合计字符上限，不扩大为完整 artifact 摘要。

### 3.5 Evidence 工具最多调用 20 次

- 每个 Role Run 前 20 次 `inspect_experience_evidence` 调用允许执行，第 21 次及以后拒绝。
- 所有 invocation 都计数，包括非法 ref、view、selector 和其他失败调用。
- evidence directory 的初始注入与 terminal submit 不计入这 20 次。
- 保留单次最多三条、单条最多 1500 字符、单次结果最多 4000 字符。

Prompt 允许模型在职责归因仍不明确时读取多个必要视图；不要求用满额度，也不因一次失败调用停止必要核查。

### 3.6 Prompt 的归因与经验提炼顺序

1. 根据 `trigger` 和 `negative_transitions` 确认决策角色与路由事实。
2. 从 `outcome` 提取决定性失败事实。
3. 从 `comparison` 判断 differential effect、重复稳定性或 activation-attributed effect。
4. 从 `boundary` 和工具证据判断有效输入、实现保真、上游限制或数据充分性。
5. 将已违反的条件映射到 `roles` 或 `deterministic_mechanisms` 的职责，确定主要 causal owner。
6. 根据 `experience_consumers` 选择必要经验类型；无法为当前 consumer 形成有证据支持的经验时输出空列表。
7. 每条经验只写“职责条件与因果关系 → 下次具体义务”，并限定 applicability。

faithful implementation 只是 capability 判断的必要条件。若 treated behavior 相对 control 无 differential effect、clean falsifier 否定方向，或干预在完整有效输入上 harmful over-trigger，则首先归为 Hypothesis/experiment design，不生成 Student capability。

### 3.7 Prompt 终态限制

- `lesson` 最多 500 字符；
- `applicability` 最多 300 字符；
- `evidence_refs` 必须是授权 ref 组成的 JSON 字符串数组；
- 完成一次职责映射和主要层选择后直接 terminal submit，不重复重开相同判断；
- 不为了覆盖 taxonomy 生成缺少独立证据的经验。

## 4. 计划实现

### 4.1 新增职责与转移注册表

在 `search_harness/evolution/control/` 增加紧凑 attribution registry，维护 role responsibility、deterministic mechanism responsibility、negative transition semantics 和 experience consumer mapping。

注册表只输出 Model Context 需要的字段。`ExperienceSummaryInput` 的 trigger/route 校验改为读取该注册表，删除现有合同内重复的固定路由字典。

### 4.2 `search_harness/evolution/research/roles/contracts.py`

- 新增 `ExperienceEvidenceObservation`，只含 `outcome`、可选 `comparison`、可选 `boundary`，并限制字段与合计长度。
- `ExperienceSummaryInput.evidence` 改为 `ref -> ExperienceEvidenceObservation`。
- 将 `experience_summarizer` 角色版本升级为 2；输出仍为 `experience_summary@1`。
- 不接受旧自由字符串 evidence。

### 4.3 `search_harness/evolution/research/experience_summary.py`

- Request builder 接受结构化 evidence。
- Store 增加 20 次 invocation 预算，在参数授权检查前计数。
- 第 21 次返回已用次数和上限；其他 evidence directory 与单次返回边界不变。

### 4.4 `search_harness/evolution/research/resources/base.py` 与 `tools.py`

- `model_context("experience_summarizer")` 同时返回内容无关的 evidence directory 和完整紧凑 Evolution Attribution Context。
- 工具说明写明 20 次总调用预算、失败计数和目录使用方法。

### 4.5 `harness_templates/teacher/experience_summarizer/`

- Harness 身份升级为 v2。
- Prompt 使用 Attribution Context 区分 trigger role、route target 和 causal owner。
- Prompt 使用结构化 evidence 顺序、上游设计优先级、经验 consumer 和终态字符预算。

### 4.6 验证与真实 API 复核

- 更新 18-case fixture，把现有紧凑事实重组为 outcome/comparison/boundary，不增加 artifact 内容。
- 单元测试覆盖：完整职责集合、负向路由映射、合同与 Transition 一致性、Model Input 可见性、字符预算、无完整 artifact、20 次调用预算和无旧输入兼容。
- 更新 stage check、role version、验证入口和入口清单。
- 离线回归后执行 12 次真实 API 定向复核：两个历史偏差 case 各三次；corpus confound、Hook capability、implementation defect、semantic boundary、Candidate intrinsic direction 和 activation-attributed effect 各一次。
- 人工审计要求每次都能说明“触发者、路由目标、实际职责层”三者关系；两个历史偏差 case 不得生成 Student capability，代表 case 不得发生责任角色回归。

## 5. 盘点结果

- `CONTEXT.md` 已定义主要 Teacher Role 职责，`docs/architecture/evolution.md` 与 `transitions.py` 已定义主流程和回流关系，但这些内容当前均不进入 Experience Summarizer Model Input。
- 当前 Prompt 的五层因果描述只能区分抽象层，无法告诉模型 Mechanism Distiller 与 Compiler、Evidence Reviewer 与 Hypothesis Researcher、Conformance Reviewer 与 Candidate Reviewer 各自拥有哪类决定。
- 当前 `route_target_role` 校验只覆盖局部 trigger-to-target 映射；它没有携带 route 的语义，也无法表示触发者、修复者和根因拥有者不同。
- v2 在 implementation cases 上表现改善，说明局部硬规则有效；但对无差异干预仍误归 capability，说明仅靠抽象因果层和自由文本证据不足。
- 完整职责与转移上下文可以保持紧凑：只需稳定 role ID、单句 responsibility、负向 transition 的 source/target/meaning 和三类经验 consumer，不需要输入完整架构文档或 Controller 状态。
