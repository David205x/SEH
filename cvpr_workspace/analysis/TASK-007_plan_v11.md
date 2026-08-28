# TASK-007 Experience 类型语义、职责上下文与提取增强方案 v11

## 1. 当前状态

- 当前 Prompt 只用一句话定义三类 Experience，并提供部分排除规则；没有规定各类型的结论对象、必需证据、lesson 组成和互斥优先级。
- 当前五字段输入中的 evidence 为自由文本，outcome、comparison、validity boundary 和观察主体没有固定位置。
- v10 已计划加入全局角色职责/转移上下文、结构化 evidence、20 次工具预算和终态限制，但仍以抽象因果层决定类型，不能完全消除 `teacher_work` 与 `experiment_direction`、`student_capability` 与失败机制方向之间的重叠。
- v2 已实际出现“无 differential effect 被写成 Student capability”和 Hook capability/Teacher work 类型不稳定，证明该缺口会影响真实输出。
- 三类 Experience 的定义与提取审计已保存于 `TASK-007_experience_type_extraction_audit_v1.md`。
- v11 取代 v10；当前未执行代码修改，TASK-007 保持未验收。

## 2. 任务意图

本次修订让 Experience Summarizer 同时了解：完整 Evolution 职责与转移关系、当前负向事实的因果结构，以及三类 Experience 各自在描述什么对象、需要什么证据、应形成什么可消费结论。模型先确定结论对象和 causal owner，再选择经验类型并提取具体义务。

涉及 Goal H3 原文为：

> 将已结算轨迹中的 typed verification verdict 与终态转为有 provenance、严格 consumer/scope、可失效和可复查的 role-scoped experience，能够减少跨 attempt/generation 的能力越界、同角色错误复发和方向重走，并提高单位总预算的 useful Candidate yield，同时控制 false pruning 与 held-out utility。

本任务仍只产生无状态 Experience Draft，不接入 Controller 自动触发、Experience Store、已有经验合并或跨 generation 生命周期。

## 3. 实施思路

### 3.1 以结论对象定义三类 Experience

- `student_capability` 描述冻结 Student/Hook Model 在有效输入和 faithful 投影下的重复能力或稳定性边界。
- `teacher_work` 描述 route target Teacher Role 在其职责、Role Contract 和有效输入下的具体工作缺陷与下次义务。
- `experiment_direction` 描述与具体 Teacher 身份无关的研究方向、因果假设、机制类别、证据采集或评测设计。

类型选择先问“结论在描述谁或什么”，再用因果层和证据强度验证。仅靠 trigger、route target 或失败发生位置不能决定类型。

### 3.2 为每类 Experience 固定提取组成

#### `student_capability`

- 主体：Student 或 Hook Model；
- 条件：有效 input/contract、faithful implementation/probe；
- 证据：重复、matched control 或多个直接模型行为；
- 结论：窄能力/稳定性边界；
- 义务：后续方向应规避、限制或重新验证的行为边界；
- applicability：输入、任务、模式或决策条件。

#### `teacher_work`

- 主体：与 causal owner 相同的 route target Teacher Role；
- 职责：Attribution Context 中该角色拥有的工作；
- 证据：有效输入下的实际职责违反和后果；
- 结论：该角色工作方式的具体缺陷；
- 义务：下次执行可检查的步骤或验证要求；
- applicability：相同角色职责、合同和工作情境。

#### `experiment_direction`

- 主体：研究方向、因果假设、机制类别或评测设计；
- 证据：control、falsifier、confound、activation attribution、cost/regression 或 data sufficiency；
- 结论：方向被支持、否定、混杂、需缩窄或不应原样继续；
- 义务：下一次研究选择、控制、证据或评测要求；
- applicability：相同机制类别、问题条件或评测设置。

### 3.3 类型互斥与多条输出

默认只输出一个主要类型：

1. 有效输入与 faithful 投影下的直接重复模型边界，才允许 `student_capability`。
2. causal owner 等于 route target，且结论是角色工作方式，才允许 `teacher_work`。
3. 结论对替换 Teacher 身份仍成立，且描述方向或评测，选择 `experiment_direction`。

只有结论对象不同、依据事实不同且未来义务不同，才允许第二条。例如“Hook Model 重复跨越明确 negative boundary”可形成 capability；若另有独立 Candidate comparison 证明 aggregate gain 全来自 no-op 且成本过高，可再形成 direction。相同事实的改写不构成第二条经验。

### 3.4 完整 Evolution Attribution Context

程序向真实 Model Input 注入：

- 全部路由相关 Teacher Role 的单句职责；
- Student/Hook Model 的能力归属；
- Trial Selector、Evolution Controller、Candidate Validation 和 Promotion Gate 等确定性机制职责；
- 负向 Transition 的 decision role、route target 和 route meaning；
- 三类 Experience 的固定 consumer。

Prompt 明确区分 Trigger Decision Role、Route Target Role 和根据证据判断的 Causal Owner。职责图只约束 ownership，不预判根因。

### 3.5 五字段内的结构化因果输入

顶层仍为 `trigger`、`route_target_role`、`direction`、`attempt`、`evidence`：

- `direction` 必须写被检验因果主张/机制方向和预期行为；
- `attempt` 必须写实际执行者或机制、施加方式、覆盖条件和已知有效性；
- `outcome` 必须写观察主体、行为和直接后果；
- `comparison` 必须写比较两侧与差异、重复模式或 activation-attributed effect，可空；
- `boundary` 必须写已确认的 contract/input/implementation/data 边界和仍存在的混杂，可空。

不增加 observed_actor 等新字段；观察主体是 `outcome` 的强制语义组成。每个 observation 设置合计字符预算，避免扩大输入。

### 3.6 Evidence 工具上限

- 每个 Role Run 最多 20 次 `inspect_experience_evidence` invocation；第 21 次拒绝。
- 非法或失败调用也计数；directory 注入和 terminal submit 不计数。
- 每次最多三条、单条最多 1500 字符、单次结果最多 4000 字符。

### 3.7 Prompt 终态限制

- 完成一次“结论对象 → causal owner → 证据门槛 → 类型”判断后立即提交；
- `lesson <= 500` 字符，`applicability <= 300` 字符；
- `evidence_refs` 为授权 ref 的 JSON 字符串数组；
- 证据不足时输出空列表；
- 不填满 taxonomy，不重复改写同一义务。

## 4. 计划实现

### 4.1 `CONTEXT.md`

- 在用户确认后记录三类 Experience 的规范定义和互斥边界。
- 明确 Teacher Work、Student Capability 与 Experiment Direction 的结论对象。

### 4.2 Evolution Attribution Registry

- 在 `search_harness/evolution/control/` 建立单一职责、确定性机制、负向 Transition 和 Experience consumer 注册表。
- `ExperienceSummaryInput` 路由校验与 Model Context 共用该注册表；现有 Transition 测试核对一致性。

### 4.3 `search_harness/evolution/research/roles/contracts.py`

- `ExperienceEvidenceObservation` 只含 `outcome`、可选 `comparison`、可选 `boundary`，并限制字段和合计字符数。
- `ExperienceSummaryInput.evidence` 使用结构化 observation，不兼容旧字符串。
- Experience Summarizer 升为 role version 2；输出保持 `experience_summary@1`。

### 4.4 `experience_summary.py`、`resources/base.py` 与 `tools.py`

- Request builder 接受结构化 evidence。
- Model Context 注入 Attribution Context 和内容无关 evidence directory。
- Store 对所有 evidence tool invocation 计数，前 20 次允许、第 21 次拒绝。
- 保留现有单次 evidence 返回边界和授权校验。

### 4.5 Experience Summarizer Prompt

- 写入三类 Experience 的结论对象、必需证据、lesson 组成和 applicability 边界。
- 写入互斥决策表、第二条经验的独立证据条件和具体反例。
- 使用结构化 input 与 Attribution Context 完成一次性提取流程。
- 写入 20 次工具预算和终态字符限制。

### 4.6 Fixture、检查与真实 API

- 迁移 18-case fixture，只重组已审核紧凑事实，不增加完整 artifact 内容。
- 单元测试覆盖类型语义、互斥决策、职责/Transition 一致性、结构化输入、20 次预算、字符边界和无旧输入兼容。
- 更新 stage check、role version、验证入口和入口清单。
- 离线回归后执行 14 次真实 API 定向复核：no-differential 与 harmful-overtrigger 各三次；Student capability、Teacher implementation、Hypothesis/corpus、semantic boundary、intrinsic direction、activation attribution、Candidate Validation 和无充分证据空输出各一次。
- 人工审计每条输出的结论对象、causal owner、证据门槛、lesson 组成、applicability 和重复类型。

## 5. 盘点结果

- 当前 Prompt 已具备 capability 的部分因果门槛、implementation 的排除规则和三类名称，但没有完整提取合同。
- 当前输出合同只有 `experience_type`、`lesson`、`applicability`、`evidence_refs`，因此类型语义必须由 Prompt 明确，不能依赖额外输出字段补救。
- v10 的职责/Transition Context 能解决“谁负责什么”，结构化 evidence 能解决“发生了什么和哪些层已排除”，但二者都不能单独解决“该结论属于哪种 Experience”。
- v2 的真实偏差集中在类型重叠，而不是 evidence ref 缺失：模型通常复述了正确事实，却把无差异方向写成 capability，或在 Hook capability 与 Teacher work 间不稳定。
- 不需要增加新的顶层或输出字段；增加明确的对象判定、必需证据、提取组成和互斥规则即可直接指导现有四字段 Draft。
