# Teacher Role Contracts

Teacher Role 的输入、输出与版本由 `search_harness/evolution/research/roles/contracts.py` 固定定义。所有 payload 使用严格 Pydantic 模型，拒绝未知字段；资源支持的事实义务在角色返回后再次校验。

| 规范角色 | 内部 `role_id@version` | Output contract |
| --- | --- | --- |
| Failure Analyst | `failure_analyst@1` | `failure_direction@1` |
| Hypothesis Researcher | `hypothesis_researcher@1` | `intervention_hypothesis@4` |
| Intervention Executor | `intervention_worker@1` | `intervention_worker_result@4` |
| Trial Reviewer | `trial_reviewer@1` | `trial_review@2` |
| Evidence Reviewer | `evidence_reviewer@1` | `evidence_review@2` |
| Mechanism Distiller | `mechanism_distiller@1` | `mechanism_distillation@2` |
| Mechanism Compiler | `compiler@1` | `compiler_result@2` |
| Conformance Reviewer | `conformance_reviewer@1` | `conformance_review@3` |
| Candidate Reviewer | `candidate_reviewer@1` | `candidate_review@2` |

## 职责与终态

- Failure Analyst 从 incumbent Evaluation 选择有证据引用的失败方向。
- Hypothesis Researcher 输出带 phase plan、成功条件和 falsifier 的可证伪干预假设；程序提供通用跨案例正负覆盖要求，Researcher 只在默认要求不足时补充至多两项假设特有证据义务。Evidence Reviewer 要求修订时，Researcher 优先直接应用反馈约束；只有反馈不足以确定具体 condition、instruction 或 falsifier 时，才按 `list_trial_evidence`、`get_trial_evidence`、必要时 `get_trial_event` 的顺序读取旧 Trial。旧 Trial 只用于修订诊断，不计入新版 Hypothesis 的 Evidence。
- Intervention Executor 在冻结 prefix 上使用数字编号的 Editable Context Block 执行分支实验；其结果由程序从跨 phase transcript 提取，不能通过通用 standalone role runner 伪造。目标 phase 已到达且 Worker 正确选择 `continue_without_change` 时，Trial 仍以 `executed` 保留，`modified_phases` 为空；只有目标 phase 未到达时才视为 `unsuitable_assignment`。
- Trial Reviewer 对单条完整 intervention trajectory 作事实性分析，并为每个冻结 phase 记录 `positive`、`negative` 或 `uncertain` predicate label、决定性观察、实际执行状态、直接行为效果和独立的 outcome evidence。标签描述 activation predicate 是否成立，不把干预成功与触发条件混为一谈。
- Evidence Reviewer 聚合 trial review，并接收当前 trial/assignment 上限、已用与剩余预算以及程序维护的证据覆盖摘要；返回 `continue`、`revise`、`reject` 或 `ready_to_distill`。默认要求至少覆盖 3 个不同案例，并为每个 phase 从不同案例收集至少 2 个正例和 2 个负例；同题 replicate 只用于判断稳定性，不增加覆盖计数。默认覆盖未满足时程序禁止 `ready_to_distill`，任一剩余调度预算为零时程序也禁止 `continue`，角色必须缩小或否定当前结论，而不能把缺失证据降格为已蒸馏机制的限制。`revise` 时，Reviewer 在现有自由文本 `assessment` 中按 Observed failure、Required revision、Must preserve、Claim limit 的顺序组织反馈；`phase_findings` 保留局部判断，`key_risk` 保留首要风险，`next_obligation` 只服务于 `continue`。这些标签不新增或改变 `evidence_review@2` 字段。
- Mechanism Distiller 接收完整结构化 Trial Review、程序生成的 coverage summary 以及与 Evidence Reviewer 相同的 Trial/Assignment 预算，返回 `distilled`、`needs_evidence` 或 `not_distillable`；预算耗尽时程序禁止 `needs_evidence`。每个 phase 必须分别声明确定性 `guards`、三值 `decision_contract`、语义输入、evaluator、positive action 和 negative/uncertain/budget-exhausted fallback。`decision_contract` 中模糊概念必须给出可观察的操作边界，并把已观察证据分类为 positive、negative、uncertain；不得用 `known_limits` 抵消更强的正文承诺。对 `hook_model` evaluator，Distiller 必须先运行正式 backend 的重复 Probe，再决定收窄契约、补证据或提交；Probe 每个标签最多取两个 fixture、每项最多重复三次，且不替角色作通过判断。
- Mechanism Compiler 返回 `submitted`、`needs_evidence`、`needs_mechanism_revision` 或 `implementation_blocked`；后三者必须给出一个 `next_obligation`，提交必须引用 Candidate Artifact。Compiler 只实现冻结的 evaluator 输入投影、提示、三值解析、状态和动作，不负责把含糊机制重新解释成可运行规则。
- Conformance Reviewer 对 Candidate rollout 与参考 trial 作逐例保真判断；输入使用 `candidate_trajectory_view`，保留问题、工具证据、解析动作、Hook-model 输出、Hook change、预算状态与最终结果，省略重复 `model_input`、reasoning、usage 和无关运行事件。它独立把 trace-visible decision inputs 对照 Mechanism Spec 判为 positive、negative 或 uncertain，区分正确 fallback 和遗漏正向动作，不能把 Hook-model classification 当作权威事实。非 faithful 结果必须标明 `failure_layer`、决定性输入摘要、修复义务和 `recommended_route`；evaluator/parsing 问题还要给出 predicate 与期望/实际标签。Controller 聚合这些角色判断并回流到 evidence、mechanism 或 implementation。
- Candidate Reviewer 返回 `accept`、`revise` 或 `reject`；它不能用形式上的 conformance 或 fallback-only 行为替代正向机制证据，`revise` 必须给出 evidence、mechanism 或 implementation 目标和下一义务。

## 运行与资源

正式 Evolution Controller 中的普通 Teacher Role 由 `NativeChatRoleRunner` 执行：共享 Assembly 加载模板、资源工具与 Prompt，OpenAI-compatible 原生工具循环追加 `submit_<contract_id>` 终态工具。Hypothesis Researcher 的修订通过 Role Continuation 复用同一 Role Session。项目另提供 `AgentsSdkRoleRunner` 用于独立角色执行与适配验证，支持 terminal tool 或 SDK native structured output；它不是当前 Controller 的默认 Runner。Intervention Executor 使用专用 `InterventionRoleRunner`，以便一个 transcript 跨多个 Student Hook activation 保持状态；内部同样使用 API 原生 structured tool calling，但每次 terminal action 只暂停当前 activation，后续 Hook 继续同一个原生 Tool Session。

Role Input 只承载任务本身；较大证据由 `TeacherResourceConfig` 定位并通过资源工具按需读取。Role artifact 会保存输入、资源配置、输出 contract digest、工具调用、usage、transcript、validated mechanisms 与实际读取的资源产物。

Evolution Controller 和 Teacher Judgment 都不是 Teacher Role：前者是确定性 control plane，后者是 Evaluation 的判分能力。

Intervention Executor 不直接接收完整内部状态。`inspect_editable_context` 仅返回按顺序编号的数字 `block_id`、块类型、角色、字符数和短摘要；`inspect_context_block(block_id)` 才按需返回一个块的完整 Student-visible 内容。`apply_context_patch` 以一组有序操作原子地新增、替换或删除块；实时分支中仅在 `post_prompt`、`post_tool` 提供，并只影响下一次 Student generation。终态工具只向 Role Session 回显动作名，完整 patch 保留在审计 metadata 与 trial artifact 中，避免跨 phase transcript 再复制一次大段内容。块与 ToolResult 等内部对象的映射、工具元数据和其他任务无关 metadata 由程序维护，不要求 Teacher 查看或填写。`pre_final` 的接受/退回仍使用专用 FinalDecision 工具。

Intervention Worker 不解析文本工具 envelope。每次 activation 将当前动态 ToolSet 作为 OpenAI-compatible `tools` 发送，并只执行 `message.tool_calls` 中的单个调用；assistant tool call 与对应的 `role=tool` 结果原样保留在跨 phase transcript。无原生 tool call 的自由文本只进入审计 trace，不回放进 Role Session，避免 Provider 标记泄漏污染后续重试。Trial artifact 记录 `worker_tool_protocol=native`、完整结构化 transcript、工具调用审计与 usage。

每次 activation 还会提供只读 `active observation`：它声明当前 phase、Student step、活动 stage 字段和此前干预次数。`pre_final` 会完整提供当前 `final_decision` 候选，使 Worker 无需从可编辑消息块猜测候选是否存在；其他 phase 只声明 stage 字段处于活动状态，完整 Student 可见内容仍通过数字 block 按需读取，避免重复注入长工具结果。该投影只提供生命周期事实，不替 Worker 判断候选是否获得证据支持，也不执行假设特定的确定性触发检查。

字段级 JSON Schema 以运行时 `model_json_schema()` 和 artifact 中的 `schema_digest` 为准；本文不复制完整 Schema，避免与代码双重维护。

`runtime_inputs` 是非空、去重的受控字符串数组，可选值为 `task`、`conversation`、`tool`、`model_io`、`parsed_output`、`final_decision`、`trajectory`、`persistent_state`。它表达实现需要的运行时信息类别，不表达具体 API；`decision_inputs` 仍只描述机制语义需要的值。Capability packet v9 按 Topic 加载完整相关 symbol contract、Python-native reference、phase 生命周期、推荐用法与禁用用法，并包含 phase 的 guards、三值 decision contract 与局部 fallback；它可附带通用 reference Hook。`query_hook_api` 可按 Topic、精确 symbol 或搜索短语查询；Topic 与 packet 内 symbol 的重取不消耗查询预算，未知查询返回建议，只有新的有效 symbol 查询计入最多 12 次的预算。

逐角色的实际路由、资源义务、Prompt 边界、程序后处理和审计关注项见[当前 Teacher Roles 代码分析](../audits/teacher_roles_current_code_audit.md)。
