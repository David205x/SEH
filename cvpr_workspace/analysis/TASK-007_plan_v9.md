# TASK-007 Experience Summarizer 输入与 Prompt 增强方案 v9

## 1. 当前状态

- v7 已完成 evidence directory、可纠正工具反馈、implementation-to-teacher-work 约束和真实 API v2 验证。
- v2 的 evidence 工具 33/33 次调用成功；明确 implementation defect 已稳定生成对应角色的 `teacher_work`。
- v2 仍有 15 次首次提交超过输出字段长度，一次 Run 因重复权衡和 JSON 截断未形成终态。
- “无 differential effect”和“clean falsifier + harmful over-trigger”仍可能被误归为 `student_capability`。
- v8 已获用户接受，但尚未实施；用户新增“工具调用最多 20 次”和“同时增强 Prompt 与输入”的要求，本报告取代 v8。
- TASK-007 保持未验收，当前未执行本报告中的代码修改。

## 2. 任务意图

本次修订让 Experience Summarizer 在紧凑输入中直接看到判因所需的结果、对照和已确认边界，并在必要时最多调用 20 次 evidence 工具补充裁剪证据。Prompt 据此先确定因果层，再生成短、具体、可复用且消费对象正确的经验。

涉及 Goal H3 原文为：

> 将已结算轨迹中的 typed verification verdict 与终态转为有 provenance、严格 consumer/scope、可失效和可复查的 role-scoped experience，能够减少跨 attempt/generation 的能力越界、同角色错误复发和方向重走，并提高单位总预算的 useful Candidate yield，同时控制 false pruning 与 held-out utility。

本任务仍只生成无状态 Experience Draft，不接入 Controller、Experience Store、已有经验合并或跨 generation 生命周期。

## 3. 实施思路

### 3.1 保留五个顶层输入字段

`trigger`、`route_target_role`、`direction`、`attempt`、`evidence` 五个顶层字段不增加。`direction` 只描述被检验的因果主张和期望行为；`attempt` 只描述本次实际干预、检查或实现及其覆盖条件。

`evidence` 的每个来源值由自由文本改成三个有直接消费用途的紧凑字段：

- `outcome`：触发 reject/revise/refuse 的决定性结果；经验中的失败事实只能从这里或工具证据取得。
- `comparison`：matched control、重复行为、activation-attributed delta 或 before/after 对照；用于判断因果效应和 Student capability 的重复性。没有对照时为 `null`。
- `boundary`：已经确认的 contract、input、implementation 或 data/environment 边界；用于排除错误责任层。没有已确认边界时为 `null`。

不增加 verdict、confidence、consumer、scope、状态或任意审计字段。每个观察仍有总字符预算，不允许用三个字段扩大成完整 artifact 摘要。

### 3.2 将 Experience Summarizer 升为角色版本 2

结构化 evidence 改变真实 Model Input Contract，因此将 `experience_summarizer@1` 升为 `experience_summarizer@2`；输出仍为 `experience_summary@1`。历史自由字符串输入不保留兼容分支，验证 fixture 和调用端统一迁移。

### 3.3 Evidence 工具最多调用 20 次

每个 Experience Summarizer Role Run 独立计数：

- 第 1 至第 20 次 `inspect_experience_evidence` 调用允许执行；
- 第 21 次及以后拒绝；
- 非法 ref、view、selector 和其他失败调用同样占用一次额度；
- evidence directory 的初始注入不算工具调用；terminal submit 不算 evidence 工具调用。

保留每次最多三条、单条最多 1500 字符和单次结果最多 4000 字符的边界。Prompt 说明可以按归因需要读取多个不同视图，不要求用满额度，也不因一次调用失败停止必要核查。

### 3.4 Prompt 先判因，再抽取经验

Prompt 使用以下一次性流程：

1. 从 `outcome` 提取失败事实，不能把 trigger 或 route hint 当作根因。
2. 从 `comparison` 判断是否存在 differential effect、重复稳定边界或 activation-attributed effect。
3. 从 `boundary` 排除已确认 faithful/invalid/confounded 的层；信息不足时再调用工具。
4. 只选择一个主要因果层；只有独立证据支持时才增加第二种经验类型。
5. 每条经验写成“失败条件与因果关系 → 下次必须采取的具体义务”，`applicability` 只界定适用条件。

faithful implementation 只是 Student capability 的必要条件，不是充分条件。若 treated behavior 相对 control 无 differential effect，clean falsifier 否定方向，或干预在完整有效输入上 harmful over-trigger，优先形成上游 hypothesis/experiment-design 经验，不生成 Student capability。

### 3.5 Prompt 明确终态约束

- `lesson` 最多 500 字符；
- `applicability` 最多 300 字符；
- `evidence_refs` 必须是授权 ref 组成的 JSON 字符串数组；
- 完成一次因果选择后直接 terminal submit，不重复重开同一类型判断；
- 证据不足时提交空 `items`，不以泛化文本补齐 taxonomy。

## 4. 计划实现

### 4.1 `search_harness/evolution/research/roles/contracts.py`

- 新增最小 `ExperienceEvidenceObservation` 对象，字段只含 `outcome`、可选 `comparison`、可选 `boundary`，并限制单字段和合计字符数。
- `ExperienceSummaryInput.evidence` 改为 `ref -> ExperienceEvidenceObservation`。
- 将 `experience_summarizer` 角色版本更新为 2，输出合同版本保持 1。

### 4.2 `search_harness/evolution/research/experience_summary.py`

- `build_experience_summary_request()` 只接受新的结构化 evidence，不接受旧字符串。
- 新增每个 Store 独立的 20 次 invocation 计数，在 ref/view/selector 校验前计数，保证失败调用也计入。
- 第 21 次返回包含已用额度和上限的可纠正错误；保留现有单次结果边界。

### 4.3 `search_harness/evolution/research/tools.py`

- 工具说明写明最多 20 次、失败调用计数、合法 ref/view/selector 的来源以及空 selector 的读取语义。

### 4.4 `harness_templates/teacher/experience_summarizer/`

- `harness.json` 更新为 v2 身份。
- `system.md` 增加结构化 evidence 的消费顺序、20 次工具预算、上游设计优先级、经验抽取格式和输出字符预算。
- `user.md` 说明 `outcome/comparison/boundary` 是真实紧凑 Model Input，不是验证用 JSON；工具只补足未在输入中建立的因果链。

### 4.5 验证 fixture、检查与入口

- 将 18 个历史 artifact case 的 evidence 迁移为结构化因果观察，不增加 artifact 内容，只重组已经审计过的紧凑事实。
- 更新 `tests/evolution/research/test_experience_summary.py`，覆盖新输入合同、无旧格式兼容、20 次完整调用预算、失败调用计数、Prompt 因果与长度约束。
- 更新 stage check、验证 suite 的 role version、入口清单和分析入口引用。
- 离线回归通过后运行 10 次真实 API 定向复核：两个历史偏差 case 各三次；corpus confound、Hook capability、implementation defect 和 Candidate activation effect 各一次。

## 5. 盘点结果

- 当前五字段结构本身没有冗余；问题在 `evidence` 自由文本把 outcome、comparison 和 established boundary 混在一句话中，模型需要自行恢复因果结构。
- v2 的“无 differential effect”输出已经复述了正确 control 事实，但仍选错经验类型，说明不需要更多 artifact，而需要把 comparison 在输入中明确成独立语义。
- 唯一终态失败 case 同时具有 clean falsifier 和 harmful over-trigger；把两者放入 `comparison`，并把 faithful activation 放入 `boundary`，可以直接支持上游设计归因。
- Evidence directory 已消除 ref/view/selector 猜测；本次只增加 20 次总调用计数，不改变目录和三种 view。
- 当前 Role Input 是实际发送给模型的紧凑 JSON；结构化 evidence 不是验证文件，也不会替代现有对完整 artifact 的裁剪隔离。
