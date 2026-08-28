# TASK-006 Plan v2（待确认）

## 1. 当前状态

- TASK-005 已验收；STAGE-001 当前只剩 Teacher Role scope 与输入 provenance 尚未固化。
- TASK-006 已登记为 `proposed`，尚未开始代码实施。
- v1 将 input contract、output contract、tool contract 分别扩展为独立身份、版本和 content digest，并计划建立持久化 `role_identity` 聚合对象。
- 复查 Goal、H3 消费方式和当前代码后，v1 的合同拆分超过了后续消费者的实际需要：现有 `role.id/version` 已表示 Role Contract 版本，现有 output contract 已承担结构化输出解析责任，工具面也无需成为独立的 experience scope。
- 当前角色实际输入先经过 typed validation 和 `TeacherResources.model_context()` 的删减投影，再由 Prompt Component 渲染为模型可见输入；原始资源配置和完整底层材料不会被整体塞入模型上下文。
- 本版报告只收缩 TASK-006 方案，没有修改研究代码、Prompt、角色输入或模型调用路径。

## 2. 任务意图

TASK-006 要为后续 Teacher work experience 提供最小且有真实消费意义的角色作用域，同时记录足以复查 Prompt 和实际模型输入变化的 provenance。它不建立一套新的合同注册系统，也不要求后续消费者逐项比较所有 digest。

### H3 原文

> 将已结算轨迹中的 typed verification verdict 与终态转为有 provenance、严格 consumer/scope、可失效和可复查的 role-scoped experience，能够减少跨 attempt/generation 的能力越界、同角色错误复发和方向重走，并提高单位总预算的 useful Candidate yield，同时控制 false pruning 与 held-out utility。

Goal 的直接要求为：

> Teacher role identity 记录 role_id、teacher model、role contract、base prompt digest 与 input-view digest；experience projection digest 单独记录。

这里的“记录”分为两种责任：

- `role_id`、Teacher model 和 Role Contract version 是后续经验消费者的 hard scope。
- base Prompt digest 与 input-view digest 是 provenance 和 soft drift 观察量，不作为逐条经验的严格相等过滤键。

这些字段均由当前运行时自动解析或计算，不要求用户为每次角色调用手工指定。

## 3. 实施思路

### 3.1 最小 Role Scope

后续 Teacher work experience 的 hard scope 只使用：

| 字段 | 权威来源 | 后续意义 |
|---|---|---|
| `role_id` | 现有 artifact `role.id` | 经验只能返回给承担同一职责的 Teacher Role。 |
| `role_contract_version` | 现有 artifact `role.version` | 输入、输出或角色可用行为发生不兼容变化时必须升级该版本；版本不同即 hard mismatch。 |
| `teacher_model` | 现有 artifact `model` 中的 provider 与 model ID | 经验只能直接匹配同一 Teacher Model；完整 Model Settings 继续作为运行 provenance，不复制进 scope。 |

不新增独立的 input contract ID/version、tool contract version 或 tool contract digest。`TeacherRoleDefinition.version` 已被定义为固定角色输入输出协议版本；工具面若发生改变角色能力边界的变化，也由该 Role Contract version 升级表达。

现有 `output_contract` 及其 schema digest继续服务结构化输出解析和 artifact 审计，不进入 H3 experience scope，也不复制进新的 identity 对象。

### 3.2 Digest 的实际责任

| 字段 | 生成方式 | 消费方式 |
|---|---|---|
| `base_prompt_digest` | 对装配后的 base instructions、user template 和 continuation templates 计算内容指纹。 | 用于确认经验产生时的基础 Prompt，以及识别 Prompt soft drift；不作为硬过滤条件。 |
| `input_view_digest` | 对 Role Runner 实际提交给 Model 的紧凑 Model Input 计算内容指纹。 | 用于来源复查、漂移诊断和 recheck；不同任务的 digest 本来就可能不同，因此不得用相等比较决定是否能检索经验。 |
| `experience_projection_digest` | 后续在实际经验投影形成时，对本次投影内容单独计算。 | 用于 usage receipt 和投影审计；不属于 TASK-006，也不混入 base Prompt 或 input-view digest。 |

content digest 不是 ID，不参与 TASK-005 生命周期 ID 的生成、验证或消费。

### 3.3 Input View 的准确定义

`input-view digest` 指向真实模型输入视图，不是针对 Pydantic validation 另外构造的一份验证 JSON。

当前通用 Role Runner 的真实路径是：

1. Pydantic 验证 `role_input`；
2. `TeacherResources.model_context()` 只产生该角色需要的删减资源视图；
3. `TeacherPromptSpec.render_input()` 将这两部分渲染进 user message；
4. Role Runner 把 system/user messages 和工具声明组成 provider-ready Model Input。

因此本任务应在第 4 步对实际 Model Input 的结构化表示计算 digest，而不是对原始 `resource_config`、完整 Artifact、底层文件或验证前 payload 计算。规范化 JSON 只是在本地为 provider-ready messages/tools 建立确定性字节表示，不会向模型追加 JSON，不会复制输入，也不会增加输入 token。

Native Chat continuation 对本次恢复后、发出请求前的实际 Model Input 计算 digest。Intervention Worker 已在 `worker_model_output.model_input` 中保存每次调用实际使用的 messages 和 tools，本任务直接对这些既有紧凑输入视图按顺序计算整次 Role Run 的 digest，不重建一份更大的 Worker 输入。

### 3.4 不建立重复的 `role_identity` 持久化对象

Teacher artifact 继续以现有字段作为权威来源：

- `role.id/version` 保存职责与 Role Contract version；
- `model` 保存 Model Provenance；
- `output_contract` 保存结构化输出合同；
- 新增 `base_prompt_digest` 与 `input_view_digest` 两个 provenance 字段。

需要消费 scope 时，由共享 helper 从 artifact 投影最小 `TeacherRoleScope(role_id, role_contract_version, model_provider, model_id)`。不在 artifact 内再复制一份嵌套 `role_identity`，从而避免同一事实出现两套来源。

### 3.5 验收方式

TASK-006 不改变 Prompt 内容、Model Input 内容、Role Output 或 API 请求行为。任务级检查使用真实模板装配与注入式假 Model/Runner，验证 digest 取自实际 Model Input 且不会改变请求；不需要调用真实 Teacher API。

## 4. 计划实现

### 4.1 建立最小 provenance helper

文件：`search_harness/evolution/research/roles/provenance.py`

计划实现：

- 提供 base Prompt content digest 计算函数。
- 提供 provider-ready Model Input content digest 计算函数。
- 提供从现有 artifact 字段解析 `TeacherRoleScope` 的函数；该投影不持久化第二份身份事实。
- digest helper 只接受实际装配或实际请求对象，不读取原始资源目录重新构造输入。

### 4.2 明确现有 Role Contract version 责任

文件：`search_harness/evolution/research/roles/contracts.py`

计划实现：

- 明确 `TeacherRoleDefinition.version` 是该 Role 的兼容性合同版本，覆盖输入、输出和角色可用行为边界。
- 不增加 input contract ID/version、tool contract version 或额外 schema digest。
- 保留现有 output contract 字段与版本，用于结构化输出协议自身的解析和审计。

### 4.3 从真实通用 Model Input 记录 digest

文件：

- `search_harness/evolution/research/roles/role_execution.py`
- `search_harness/evolution/research/roles/native_chat_runner.py`
- `search_harness/evolution/research/roles/agents_sdk_runner.py`

计划实现：

- 对装配后的 `TeacherPromptSpec` 计算 `base_prompt_digest`。
- 由 Runner 把实际提交的 messages/tools 交给共享 helper，计算 `input_view_digest`。
- 成功与已有失败 artifact 都保存这两个 provenance 字段。
- 不修改 `render_input()` 的删减投影、序列化内容或消息顺序。

### 4.4 从 Worker 已有请求快照记录 digest

文件：`search_harness/evolution/research/intervention/role_runner.py`

计划实现：

- 从 `worker_trace` 中已经保存的 `worker_model_output.model_input` 取得实际 messages/tools。
- 按请求顺序计算整次 Worker Role Run 的 `input_view_digest`。
- 复用共享 base Prompt digest helper，删除重复的通用 digest 实现时只保留 output contract 所需逻辑。
- 不把 source rollout 全文、resource config 或 branch 结果重新拼进输入视图。

### 4.5 Continuation 与 Control 持久化

文件：

- `search_harness/evolution/research/roles/native_chat_runner.py`
- `search_harness/evolution/research/roles/sessions.py`
- `search_harness/evolution/control/research_role_effects.py`

计划实现：

- continuation 继续使用现有 role、模板和 session 一致性检查；额外核对 Role Contract version 和 Teacher Model hard scope。
- 每个 continuation revision 根据本轮实际 Model Input 记录新的 `input_view_digest`。
- Control effect 继续原样持久化 role artifact，不复制或重建 Role Scope。

### 4.6 文档与检查

文件：

- `CONTEXT.md`
- `docs/architecture/evolution.md`
- `tests/evolution/research/roles/test_role_provenance.py`
- `tests/evolution/research/roles/test_native_chat_runner.py` 或现有对应测试
- `tests/evolution/research/intervention/test_role_runner.py`
- `cvpr_workspace/checks/check_stage_001_role_identity.py`
- `cvpr_workspace/analysis/stage_001_role_identity_check.json`
- `cvpr_workspace/入口清单.yaml`

计划验证：

- `TeacherRoleScope` 只由现有 role/model 权威字段投影。
- base Prompt 内容变化会改变 `base_prompt_digest`，模板路径变化不会。
- 实际 compact Model Input 变化会改变 `input_view_digest`，未投影给模型的资源配置变化不会。
- digest 计算不改变实际 messages/tools，不增加模型输入内容。
- input/output/tool schema 不产生额外 scope 字段；Role Contract 的不兼容变化由 `role.version` 表达。
- Native Chat、Agents SDK、continuation 与 Intervention Worker 均能记录相同语义的两个 provenance digest。

### 4.7 状态与验收

文件：

- `.cvpr/tasks.jsonl`
- `.cvpr/runs.jsonl`
- `.cvpr/state.yaml`

计划实现：

- 用户批准 v2 后才追加 TASK-006 `started` 并修改研究代码。
- 检查结果先登记 `executed`，再按最小 Role Scope、真实 Model Input provenance 和无请求变更三项标准决定是否 `accepted`。
- TASK-006 通过后再综合 TASK-004/005/006 证据核对 STAGE-001，不以本任务单独代替阶段验收。

## 5. 盘点结果

### 5.1 盘点范围

- G-001、PLAN-001 及 H3 定位材料对 Teacher work experience scope 的原文。
- `TeacherRoleDefinition`、Teacher artifact、Prompt Component、Role Runner、Role Session 与 Intervention Worker 的实际实现。
- 后续 STAGE-002/003 中 Teacher work experience 的匹配、投影和 usage receipt 需求。

### 5.2 直接观察事实与判断

- `TeacherRoleDefinition` 的文档已说明其固定角色输入和输出协议，artifact 的 `role.version` 已是可用的 Role Contract version。因此没有必要再创建 input/output/tool 三套合同身份和版本。
- artifact 已保存完整 Model Provenance。后续 scope 只需从中读取 provider/model ID；复制完整 model settings 到 `role_identity` 会形成双重事实源。
- output contract schema digest 已被运行时用于结构化输出协议。它有独立的解析意义，但没有证据表明 H3 检索需要用它进行第二次严格匹配。
- Tool Definition 会进入实际 provider-ready Model Input；工具面的实际变化会反映到 input-view provenance。若工具变化改变 Role 的兼容性边界，应提升 `role.version`，无需增加 tool contract digest。
- `TeacherPromptSpec.render_input()` 将验证后的角色输入和删减后的 `model_context` 序列化进真实 user message。因此“规范化 JSON”不是旁路验证文件，但 v1 直接对 raw input/resource material 计算的表述不准确。
- Intervention Worker 的 trace 已保存每次模型请求实际使用的 messages/tools。直接复用这些 Model Input 快照能够覆盖其分阶段紧凑视图，不需要把 rollout 或 branch artifact 再展开一次。
- 后续 Teacher work experience 需要按同一 role/model/contract 做 hard scope；base Prompt 和单次 input view 更适合解释漂移、触发 recheck 和审计来源。把两个 digest 当成 exact-match key 会导致几乎每个不同任务都无法复用经验。

### 5.3 复审结论

- Goal 中列出的信息都应可记录，但不都需要手工指定、独立版本、独立 schema 或逐项硬校验。
- 必须用于后续 hard scope 的只有 `role_id + role_contract_version + teacher model provider/model ID`。
- 必须记录但只用于 provenance/soft drift 的是 `base_prompt_digest + input_view_digest`。
- `experience_projection_digest` 在经验真正投影时单独记录，不属于本任务。
- v1 的 input/output/tool contract 拆分和嵌套 `role_identity` 对象不进入 v2 实施方案。
