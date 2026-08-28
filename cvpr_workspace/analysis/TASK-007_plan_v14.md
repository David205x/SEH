# TASK-007 修订实施方案 v14

> 用户批准补充约束：`Student Capability.lesson` 只描述“在条件 X 下，Student 无法稳定完成 Y”的模型能力边界事实；研究动作、guard、复检、Candidate 效用和 Direction 结论不写入该字段，`applicability` 只限定观察范围。

## 1. 当前状态

- `experience_summarizer@2` 的五字段合同、实际 Transition 上下文、角色职责上下文、20 次 evidence tool 硬熔断和三类输出合同已经实现。
- 最终 v5 批次的 28 个真实 API Run 使用了真实历史 artifact 作为案例来源，但模型可见的 `direction`、`attempt`、`evidence.outcome`、`evidence.comparison` 和 `evidence_views` 内容由人工改写后写入 fixture。
- 当前入口只检查 `source_artifacts` 文件存在，不读取其中字段来生成模型输入；因此 v5 只能证明 Summarizer 在人工整理的因果事实下能够归因，不能证明它面对真实上游产物原文时仍然可靠。
- 12 条 `student_capability` 原始终态输出已经逐条转录并忠实直译；原输出是“能力事实 + 使用限制 + guard/recheck 建议”的复合草稿，不是纯能力事实句。
- TASK-007 当前保持 `executed`，不进入 `accepted`；需要完成 artifact-native 输入验证后重新判断。
- 尚未修改 artifact 投影代码、case schema、API 入口或 Prompt，尚未运行新一轮 API。

## 2. 任务意图

本次修订要验证的不是“模型能否复述人工准备好的归因结论”，而是：在尽量直接使用真实上游 artifact 原文和结构化值的条件下，Experience Summarizer 能否自行区分 Student Capability、Experiment Direction 与 Teacher Work，并生成范围准确的 Experience Draft。

涉及的 H3 原文为：

> 将已结算轨迹中的 typed verification verdict 与终态转为有 provenance、严格 consumer/scope、可失效和可复查的 role-scoped experience，能够减少跨 attempt/generation 的能力越界、同角色错误复发和方向重走，并提高单位总预算的 useful Candidate yield，同时控制 false pruning 与 held-out utility。

本任务针对 H3 中“typed verification verdict 与终态转为 role-scoped experience”的输入真实性。若输入中的行为、结果、比较和因果结论均由人工重写，实验无法判断 Summarizer 是否真正具备读取上游产物并归因的能力。

## 3. 实施思路

### 3.1 区分 artifact-derived 与 program-derived 信息

模型输入中的信息分为两类：

- artifact-derived：`direction`、`attempt`、`evidence.outcome`、`evidence.comparison` 和 evidence tool view 内容。它们必须来自指定 artifact 的原始字符串或选定结构化子树，不允许在 fixture 中自由改写。
- program-derived：`trigger`、source classification、decision role、actual next work、route target、causal neighbors、boundary kind/status、授权 evidence ref/view/selector。它们属于确定性控制事实，可以由配置手动填写来模拟未来程序补全。

`boundary_facts.statement` 只描述程序确认了哪项 gate 以及其产物定位，不重复 outcome、comparison 或归因结论，避免通过手写 statement 把答案提前告诉模型。

### 3.2 用冻结提取规格替代手写业务文本

每个 case 保存 artifact 引用和字段提取规格。提取操作只允许：

- `copy_text`：复制一个 JSON pointer 指向的原始字符串；
- `copy_json`：把指定结构化子树按固定 JSON 序列化；
- `join_values`：用固定字段标签连接多个原始值，不改写值本身。

不允许模型输入构造器调用 LLM 总结、不允许自由文本 fallback、不允许静默截断。原文超过当前字段预算时，应选择更紧凑的现有 artifact 字段，或把完整原文放到授权 evidence view；无法满足时 case 构造失败，而不是改写原文使其通过。

### 3.3 按上游职责选择真实原文字段

- Evidence Review：读取 `phase_findings[*].assessment`、总 `assessment`、`key_risk`、`next_obligation` 和 coverage/trial review 的结构化值。
- Hook Feasibility：读取 effect 中的 `phase_findings`、`assessment`、`revision_feedback`，以及 `probe.json` 的 thinking modes、repetitions、decision contract 和逐 probe label。
- Mechanism Distillation：读取 `rationale`、`decision` 和对应 Mechanism/Hypothesis 原文。
- Conformance：读取 `summary`、`route_feedback`、`finding_refs` 指向的 finding `assessment/repair_obligation`；语义判断与实现判断分别保留原产物措辞。
- Candidate Review：读取 `observed_effect`、`reason`、recommendation，以及 Work lineage 中对应 Mechanism/Candidate 原文和结构化对照值。
- Candidate Validation：读取 typed status、`rejection_reason`、`prior_validation`，并从 Compiler role input 原样读取当时可见的修复义务。

`direction` 与 `attempt` 缺少直接来源时，从该 Work 的 lineage/input refs 解析对应 Hypothesis、Mechanism、Compiler 或 Candidate artifact；不再由 case 作者重新概括。

### 3.4 保存输入来源审计，但不增加 Model Input 字段

每次构造生成独立的 program-side projection audit，记录：

- 目标 Model Input 字段；
- artifact 相对路径；
- JSON pointer；
- 提取操作；
- 实际复制值。

该审计用于证明输入忠实性，不进入 Summarizer 的五字段协议，不新增 provenance/digest/hash 字段。

### 3.5 重新验证 Capability 输出形态

新一轮审计同时检查：

- Capability 是否形成纯粹、狭窄的模型行为边界；
- 是否把 deterministic guard 误写成模型能力已经恢复；
- 是否允许仅通过改写 contract 绕过必需边界；
- overlap case 是否把 Direction 的 utility/cost 事实混入 Capability；
- `lesson` 是否只包含条件化 Student 模型能力事实，`applicability` 是否只限定真实观察范围。

原始英文输出、忠实中文直译和审阅意见分别保存，不再在“翻译”过程中修正模型原意。

## 4. 计划实现

### 4.1 Artifact 投影与输入配置

- 新增 `cvpr_workspace/analysis/task_007_artifact_input_projection.py`：实现受限 JSON pointer 读取、`copy_text/copy_json/join_values`、长度检查和 projection audit；禁止自由文本 fallback 与静默截断。
- 将 `cvpr_workspace/configs/task_007_attribution_cases.json` 升级为仅支持 artifact projection 的新 schema：删除 `direction`、`attempt`、`evidence` 和 `evidence_views` 中手写的业务文本，改为 artifact source、pointer 和确定性字段配置；不保留旧 schema 兼容分支。
- 补充当前 case 缺失的上游 Hypothesis、Mechanism、finding、Candidate 或 Compiler artifact 引用，全部从历史 Work lineage/input refs 定位。

### 4.2 API 入口与证据产物

- 修改 `cvpr_workspace/entrypoints/run_task_007_attribution_validation.py`：真实读取 source artifact，调用投影器构造请求；`source_artifacts` 不再只做存在性检查。
- 每个 Run 保存 `input_projection.json`，记录模型可见非确定性文本的 artifact/path/pointer 来源，并保存最终实际 `role_input`。
- `trigger`、source/Transition context 和 boundary kind/status 继续由确定性配置模拟；`route_target_role` 仍由 next work 派生。

### 4.3 检查与分析

- 新增 `cvpr_workspace/checks/check_task_007_artifact_input_projection.py`：断言所有 model-visible artifact-derived 文本都能在指定 artifact 字段或结构化子树中逐值找到；断言 fixture 不再含对应手写自由文本；断言 transcript、reasoning、usage、resource config 和完整 artifact 不进入模型输入。
- 更新 `tests/evolution/research/test_experience_summary.py`：保留 Summarizer 合同和工具边界测试，不把 artifact 文件系统读取加入核心协议。
- 更新 `cvpr_workspace/analysis/analyze_task_007_attribution_validation.py`：增加 input provenance 完整性、原文覆盖、静默截断、类型和 Capability 形态审计。

### 4.4 真实 API 验证

- 使用新的 artifact-native schema 和独立输出目录运行同一组 18 个历史 case。
- 继续使用已冻结的 28-run 定向重复计划，保留所有失败、重试和非预期输出。
- 对 v5 人工改写输入与新批 artifact-native 输入执行逐 case 对照，判断类型稳定性、归因变化和输出形态变化。
- 任一 implementation/data-confound case 误产 Capability，或 Capability 无法给出有效输入、忠实执行和重复模型行为依据，直接判定失败。

### 4.5 文档

- 保留 `cvpr_workspace/analysis/TASK-007_student_capability_output_literal_translation_v1.md` 作为 v5 原输出忠实翻译。
- 新批次完成后生成同格式的 artifact-native Capability 原文/直译文档，不把审阅修正混入翻译正文。
- 更新 `cvpr_workspace/入口清单.yaml` 和追加式 Run/Task 账本，TASK-007 仍只在用户确认后标记 accepted。

## 5. 盘点结果

### 5.1 当前输入并未从 artifact 构造

`run_task_007_attribution_validation.py::_validated_cases()` 只遍历 `source_artifacts` 并检查文件存在；`_build_request()` 随后直接把 case JSON 中的 `trigger/direction/attempt/evidence/evidence_views/source_context` 传给 builder。没有任何 source artifact 字段读取或投影。

这意味着 v5 的 28 个真实 API Run 验证了真实模型调用和 Summarizer 输出合同，但没有验证上游产物解析能力。

### 5.2 现有 artifact 已包含可直接使用的原文

- Hook Feasibility effect 的 `output.phase_findings[*].assessment` 已原文记录 enabled 7/8、相同 negative 翻转、disabled 对两个 negative 误报、positive cases 一致且 parse-clean；总 `assessment` 和 `revision_feedback` 还明确区分 model-capability/stability defect 与 ambiguous contract。
- Distiller effect 的 `output.rationale` 已原文记录 intervention 2/2 positive、2/2 negative controls、production backend 对 both-entity negative 的 4/4 误判、额外 single-entity 误判及为何不能把它列为 known limit。
- Evidence Reviewer effect 已提供 `phase_findings[*].assessment`、总 `assessment` 和 `key_risk`，包括 no differential、clean falsifier、over-trigger、coverage 和 runtime/leakage 排除事实。
- Candidate Reviewer effect 已提供 `observed_effect` 与 `reason`，包括具体 activation case、no-op improvements、accuracy/pass@N、Hook token cost 和 reject 原因。
- Conformance effect 已提供结构化 `finding_counts`、`failure_layer_counts`、`route_feedback` 与 `finding_refs`；对应 finding 可提供逐 case assessment 和 repair obligation。
- Candidate Validation effect 已提供 typed status、原始 `rejection_reason` 和 `prior_validation`；Compiler role artifact 的 input 含真实 `implementation_constraints`，可以直接检验 role-input sufficiency。

这些原文足以替换当前多数人工 outcome/comparison，并能通过上游 artifact/lineage 补齐 direction 与 attempt。

### 5.3 当前 Capability 输出不是纯能力事实

12 条 v5 Capability 输出普遍包含：模型主体、重复误分类、狭窄边界、`do not rely unchanged`、guard/recheck 动作和 release 条件。原输出还存在以下可见偏差：

- 把 deterministic guard 写成能够解除模型能力限制；
- 允许通过“修订 contract/boundary”解除必需边界；
- 将 single-entity negative 与“one-sided two-entity gap”混写；
- `zero negative activation` 措辞有歧义；
- overlap Capability 混入“没有 intended positive behavior”这一 Direction 事实。

因此新实验不仅要比较类型是否正确，也要审查 Capability Draft 的事实部分和使用策略是否被混写。

### 5.4 当前结论边界

v5 的 `28/28 exact type` 结论仍可作为“人工结构化输入条件下的角色行为”证据，但不能支持 Summarizer 在真实上游 artifact 输入条件下可靠。TASK-007 需要在完成本方案的 artifact-native 重跑后重新判断。
