# TASK-006 Plan v1（待确认）

## 1. 当前状态

- TASK-005 已通过任务级验收，最后账本事件为 `TASK-005-E005 accepted`；`state.yaml` 的 `last_accepted_task_id` 已是 `TASK-005`。
- STAGE-001 仍为 `running`。route-to-obligation、typed lineage、settlement、retry/resume/replay 合同已经形成，role identity 尚未成为可持久化合同。
- 当前 Teacher artifact 已保存 `role.id/version`、模型 provenance、完整结构化输入和 output contract，但没有统一的 base prompt/template digest、input contract、tool contract 和 input-view digest。
- 通用 Native Chat、Agents SDK 与 Intervention Worker 都会生成 Teacher artifact；前两者复用 `role_execution.py`，Intervention Worker 仍自行组装相似但独立的 artifact envelope。
- TASK-006 当前仅完成代码与合同盘点，尚未修改研究代码，也尚未产生任务级检查结果。

## 2. 任务意图

TASK-006 要把一次 Teacher Role 调用的角色身份、模型身份、基础 Prompt、输入输出合同、工具合同和实际输入视图固化为可复算、可比较的 artifact 字段。STAGE-002/003 后续据此判断 Teacher work experience 的来源和适用范围，不再依赖模板路径、类名或人工解释来判断两个角色运行是否属于同一身份。

本任务解决以下问题：

- 明确 `role_id`、role version、Teacher model、base Prompt/template、input/output/tool contract 分别承担什么身份责任。
- 为每次调用保存 input-view digest，使经验来源能够定位到角色实际收到的结构化输入、资源上下文和续接反馈。
- 让成功、失败、continuation 以及 Intervention Worker artifact 使用同一 role identity 语义。
- 为后续 Teacher work experience 的 hard mismatch 与 soft drift 判断提供稳定输入合同。

### H3 原文

> 将已结算轨迹中的 typed verification verdict 与终态转为有 provenance、严格 consumer/scope、可失效和可复查的 role-scoped experience，能够减少跨 attempt/generation 的能力越界、同角色错误复发和方向重走，并提高单位总预算的 useful Candidate yield，同时控制 false pruning 与 held-out utility。

Goal 对本任务还有一条直接有效性要求：

> Teacher role identity 记录 role_id、teacher model、role contract、base prompt digest 与 input-view digest；experience projection digest 单独记录。

本任务中的 digest 是内容指纹，不是生命周期 ID。它不改变 TASK-005 的 ID 生成与消费方式，也不使用 digest 生成 role、work、attempt 或 settlement ID。

## 3. 实施思路

### 3.1 将角色身份分成稳定核心与单次输入视图

每条 Teacher artifact 保存一个结构化 `role_identity`：

- `role_id`：标识 Teacher 的稳定职责名称。
- `role_version`：标识该职责定义的版本。
- `model`：保存实际 Teacher 的 provider、endpoint/model ID 和 configured thinking mode，用于区分实际承担该职责的模型身份；完整生成参数继续由现有 artifact `model` 保存。
- `base_prompt_digest`：对装配后的 instructions、user template 和 continuation templates 的规范化内容计算 digest，不使用模板路径作为内容身份。
- `input_contract`：保存输入合同 ID、版本和 JSON Schema digest，标识角色可接收的数据合同。
- `output_contract`：保存现有输出合同 ID、版本和 JSON Schema digest，标识角色必须产生的结构化结果合同。
- `tool_contract_digest`：对实际启用工具的名称、描述、参数 schema 和注册顺序计算 digest，标识角色可调用的工具面。
- `input_view_digest`：对本次角色可见的结构化输入视图计算 digest，定位该条工作经验产生时的实际上下文。

其中 model、role/input/output/tool contract 不兼容时，后续经验匹配可以判定 hard mismatch；Prompt 或输入视图改变时，后续任务可以依据具体 digest 判定 soft drift 和 recheck。TASK-006 只提供事实字段，不在本任务中实现经验匹配策略。

### 3.2 明确定义 input view

通用角色的 input view 由以下结构化内容组成：

- 经 Pydantic 验证后的 `role_input`；
- `TeacherResources.model_context()` 实际注入 user template 的 resource context；
- continuation 时本轮之前累计的结构化 feedback history，以及本轮追加的 feedback event。

Intervention Worker 的 input view 由以下内容组成：

- 经验证的 `InterventionWorkerInput`；
- source rollout 的内容 digest、example/replicate、fork step 与 phase；
- 由 hypothesis 形成的 worker intent、phase guidance 和 activation budgets。

input view 使用规范化 JSON 计算，不将本次模型输出、tool call 结果或运行后评估结果混入输入指纹。后续经验投影内容不进入该 digest；STAGE-003 会为 experience projection 单独保存 digest。

### 3.3 统一 artifact 形成路径

角色模板装配完成后先建立 Prompt 与 Contract snapshot；模型配置解析完成后补齐 model identity；在发出模型请求前形成 input view。运行结束时，成功和失败 artifact 都写入同一 `role_identity`。

Native Chat continuation 恢复时比较上一 artifact 的稳定角色核心，拒绝 role、model、Prompt 或 contract 不一致的续接；允许结构化反馈扩展 input view，并为新 revision 生成新的 `input_view_digest`。

Intervention Worker 继续保留专用的多阶段执行器，但复用共享 identity 与 contract snapshot 构造函数，不再自行维护另一套 schema digest 和 role envelope 语义。

### 3.4 验收方式

本任务不改变角色请求内容、模型响应处理或 Reviewer 判据，因此任务级验收使用真实模板装配、确定性输入和注入式假模型/假运行器即可，不需要调用真实 Teacher API。

检查重点是：内容相同但路径不同的模板得到相同 Prompt digest；Prompt、合同、工具或输入视图发生变化时只有对应 digest 改变；成功、失败、continuation 和 Intervention Worker artifact 都能形成完整且一致的 role identity。

## 4. 计划实现

### 4.1 建立共享 Role Identity 合同

文件：`search_harness/evolution/research/roles/identity.py`

计划实现：

- 定义规范化 JSON content-digest helper，只用于内容指纹。
- 定义 model identity、input/output/tool contract snapshot、base prompt snapshot 和 input-view snapshot 的构造函数。
- 对 model provenance 的必需身份字段执行显式验证。
- 统一生成成功、失败和专用 Runner 都能复用的 `role_identity` 字典。

### 4.2 补齐输入合同身份

文件：`search_harness/evolution/research/roles/contracts.py`

计划实现：

- 为 `TeacherRoleDefinition` 增加稳定的 `input_contract_id` 与 `input_contract_version`。
- 为当前每个 Teacher role 显式登记输入合同，而不是从 Python 类名推断合同身份。
- 保留现有 role/output contract 版本作为独立事实源。

### 4.3 保存 Prompt 与输入视图材料

文件：

- `search_harness/evolution/research/roles/spec.py`
- `search_harness/evolution/research/roles/role_execution.py`

计划实现：

- 从装配后的 `TeacherPromptSpec` 生成只依赖内容的 Prompt snapshot。
- 在 `PreparedRoleRun` 中保存已验证的 resource context 和规范化 input-view material。
- 将 artifact schema 更新为包含 `role_identity`、input contract 和现有 output contract 的当前版本。
- 成功与失败 artifact 通过同一 builder 写入一致字段。

### 4.4 接入通用 Runner 与 continuation

文件：

- `search_harness/evolution/research/roles/native_chat_runner.py`
- `search_harness/evolution/research/roles/agents_sdk_runner.py`
- `search_harness/evolution/research/roles/sessions.py`

计划实现：

- 在解析实际模型配置后构造 model identity，并在请求前完成 input-view snapshot。
- continuation 把结构化 feedback history 纳入本轮 input view。
- continuation 使用稳定 role identity core 验证是否允许恢复，不再只依赖模板路径与 system instruction 文本比较。
- Agents SDK 和 Native Chat 输出相同的 identity contract。

### 4.5 接入 Intervention Worker

文件：`search_harness/evolution/research/intervention/role_runner.py`

计划实现：

- 使用共享 Role Identity 和 contract snapshot builder。
- 将 source rollout 内容 digest、prefix 定位、worker intent、phase guidance 与 activation budgets 组成 Worker input view。
- 删除本文件重复的 schema digest helper，并使 Worker artifact 与通用角色使用相同当前 schema。

### 4.6 更新消费边界与架构文档

文件：

- `search_harness/evolution/control/research_role_effects.py`
- `search_harness/evolution/control/evidence_review_effects.py`
- `search_harness/evolution/control/conformance_effects.py`
- `search_harness/evolution/control/hook_feasibility_effects.py`
- `docs/architecture/evolution.md`

计划实现：

- 确认 Control effect 持久化完整 role artifact，不在 effect outcome 中复制或重建 identity。
- 对 continuation 和恢复入口增加完整 identity 的读取与错误定位。
- 在活动架构文档中记录稳定 role core、单次 input view 和未来 experience projection 三者的边界。

### 4.7 建立 TASK-006 检查

文件：

- `tests/evolution/research/roles/test_role_identity.py`
- `tests/evolution/research/roles/test_native_chat_runner.py` 或现有对应 Runner 测试
- `tests/evolution/research/intervention/test_role_runner.py`
- `cvpr_workspace/checks/check_stage_001_role_identity.py`
- `cvpr_workspace/analysis/stage_001_role_identity_check.json`
- `cvpr_workspace/入口清单.yaml`

计划验证：

- 所有活动 Teacher template 均能形成完整 role identity。
- Prompt content、input/output schema、tool definition 和 input view 的变化分别反映到对应 digest。
- 模板绝对路径变化不改变内容身份。
- 成功、失败、continuation 和 Intervention Worker 使用同一合同。
- continuation 的稳定核心不一致时拒绝恢复，合法 feedback continuation 只更新本轮 input view。
- 检查不请求真实外部 API，并登记为 `development_check`。

### 4.8 更新任务状态与证据

文件：

- `.cvpr/tasks.jsonl`
- `.cvpr/runs.jsonl`
- `.cvpr/state.yaml`

计划实现：

- 实施开始时追加 TASK-006 `started` 事件。
- 检查运行分别登记独立 Run ID、输入、代码版本、环境和输出。
- 先记录 `executed`，再按 TASK-006 完成标准决定是否 `accepted`。
- TASK-006 通过后重新核对 STAGE-001 的全部验收规则；只有 role identity、route matrix、settled trajectory 和 replay 证据共同满足阶段合同，才申请 STAGE-001 验收。

## 5. 盘点结果

### 5.1 盘点范围

- STAGE-001 与 G-001 H3 的 role identity、scope 和有效性要求。
- Teacher role 定义、模板装配、Prompt 渲染、资源上下文、模型配置与 artifact builder。
- Native Chat、Agents SDK、continuation 和 Intervention Worker 的实际运行路径。
- Control 层对角色 artifact 的持久化位置及当前活动 Teacher templates。

### 5.2 直接观察事实与方案依据

- `TeacherRoleDefinition` 已有稳定 `role_id/version` 和 output contract，但没有显式 input contract ID/version。由此需要在 `contracts.py` 增加输入合同身份，而不是从 Pydantic 类名推断。
- `TeacherPromptSpec` 已包含装配后的 instructions、user template 与 continuation templates。由此可直接对运行时真实 Prompt 内容计算 digest，无需扫描文件路径或建立第二套模板解析器。
- `prepare_role_run()` 已完成输入验证、资源绑定和 resource context 渲染，但 `PreparedRoleRun` 没有保存 resource context。由此 input-view material 应在该处形成并沿 artifact builder 传递。
- 当前通用 artifact 保存完整 `input`、`resource_config`、`model` 和 output schema digest，但缺少 Prompt、input schema、tool surface 与 input-view identity。由此 TASK-006 可以在现有 artifact envelope 上补齐字段，不需要修改角色业务输出。
- Native Chat continuation 当前通过 role ID、模板路径、输入/资源对象和 system instruction 文本验证恢复。由此需要升级为稳定 role core 验证，并为每个 continuation revision 单独计算 input-view digest。
- Intervention Worker 自行复制 output schema digest 与 artifact envelope；其实际输入还包含 rollout/prefix 与 phase plan。由此必须接入共享 identity builder，并使用 Worker 专用 input-view material。
- Control 层已经原样持久化角色 artifact。由此 identity 的权威来源应保留在 role artifact，不在多个 effect outcome 中重复维护。
- G-001 明确要求 base prompt digest、input-view digest，并要求 experience projection digest 单独记录。由此 TASK-006 只冻结无经验投影的角色身份与输入视图，projection digest 留给实际引入 experience projection 的后续阶段。

### 5.3 当前结论边界

本报告支持将 TASK-006 定义为 STAGE-001 的下一原子任务。它不支持直接验收 STAGE-001；只有 TASK-006 实施并通过检查后，才能结合 TASK-004/005 证据执行阶段级核对。
