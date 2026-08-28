# TASK-007 Capability/Direction 优先的 Experience Summarizer 方案 v13

## 1. 当前状态

- 当前实现与 v2 真实 API 已证明三类 Experience 的主要风险集中在 `student_capability` 与 `experiment_direction` 的误分：无 differential effect 曾被写成 capability，Hook instability 又曾被写成 Teacher work。
- v12 已修正 source eligibility、实际 Transition、Teacher subject、权威 boundary facts、类型决策表和错误 Candidate Validation fixture。
- v12 对三类 Experience 仍采用相近的设计与验收篇幅，没有体现用户确认的重要性顺序。
- 用户现确认优先级为 `Student Capability >= Experiment Direction > Teacher Work`，要求重点保证前两类提取准确，Teacher Work 不作为主要目标。
- v13 取代 v12；当前未执行代码修改，TASK-007 保持未验收。

## 2. 任务意图

本次修订优先形成两类直接影响搜索空间的经验：

1. 准确识别冻结 Student/Hook 的窄能力边界，避免后续 proposal 再次依赖已证实不可实现或不稳定的行为；
2. 准确识别方向、因果主张、机制类别与评测设计的后验结论，避免方向重走、无效试验和错误 utility attribution；
3. Teacher Work 仅在证据明确且不会干扰前两类时保守提取。

涉及 Goal H3 原文为：

> 将已结算轨迹中的 typed verification verdict 与终态转为有 provenance、严格 consumer/scope、可失效和可复查的 role-scoped experience，能够减少跨 attempt/generation 的能力越界、同角色错误复发和方向重走，并提高单位总预算的 useful Candidate yield，同时控制 false pruning 与 held-out utility。

本任务只验收 consumer-ready Experience Draft，不声称已实现 Store、projection、invalidation 或 H3 效果。

## 3. 实施思路

### 3.1 优先级的含义

`Student Capability >= Experiment Direction > Teacher Work` 表示归因和验证资源的优先次序，不表示放宽 Capability 的证据门槛：

- Capability 价值最高，同时错误 capability 最可能造成能力越界判断和 false pruning，因此采用最高精度门槛。
- Direction 次之，重点保证 direction signature、disposition 和合法重访条件准确。
- Teacher Work 不追求高召回；缺少明确事前义务或 role-input sufficiency 时直接省略。

若 Direction 证据清楚而 Capability 证据不足，只输出 Direction，不能为了优先级强行生成 Capability。

### 3.2 Student Capability 为第一提取目标

Prompt 首先检查是否存在可提取的 Student/Hook capability boundary，但必须同时满足：

- reference/label 有效且可判；
- 输入与 contract projection 有效；
- implementation/probe faithful；
- data/environment 不构成更直接混杂；
- 同一窄 predicate 在相同输入重复，或至少两个等价有效 case 中出现相同行为边界。

Lesson 必须写：Student/Hook subject、有效条件、重复/多 case decisive behavior、窄边界，以及 Hypothesis Researcher 的动作——不得原样依赖、增加 deterministic guard，或满足指定 recheck 后才能解除限制。

Applicability 只写已证实的 model/task/input/mode/decision boundary 和解除条件。无有效正例机会数时，“未 activation”不能证明 capability。

### 3.3 Experiment Direction 为第二提取目标

Capability 判断后，Prompt 独立检查方向结论：

- treated/control 无 differential effect；
- clean falsifier；
- valid complete-evidence input 上 harmful over-trigger；
- corpus/data/reference/evaluation confound；
- Candidate 收益来自 no-op，而非 mechanism activation；
- activation cost、回归或 selectivity 使方向不值得原样继续。

Lesson 必须写：可匹配的 direction signature、决定性证据、明确 disposition（停止、缩窄、inconclusive、conditional continue）和合法重访所需的新差异或新证据。

Direction 证据不能被改写成 Capability：faithful implementation 只说明干预被正确施加，不会把“干预没有因果效应”变成模型能力不足。

### 3.4 Capability 与 Direction 并存

两类经验都重要，但只有在结论对象、decisive evidence atoms 和 future action 均不同的情况下并存：

- Capability 必须由有效 reference 下的重复直接模型行为证明；
- Direction 必须由独立 Candidate comparison、control、utility/cost 或 research-design 事实证明。

例如，Hook Model 在两个明确 negative classes 上重复误触发可形成 Capability；同一 Candidate 的 aggregate gain 全来自 no-op、并增加成本和回归，可由另一组 comparison 形成 Direction。

### 3.5 Teacher Work 为低优先级保守输出

只有以下事实已经在现有输入或为前两类读取的证据中明确出现时，才生成 Teacher Work：

- 某 Teacher Role 在运行前已有明确 Role Contract/程序职责；
- 完成该职责所需事实当时对该角色可见；
- 角色未履行义务且后果明确。

不为了 Teacher Work 单独扩大 evidence 输入或优先消耗工具调用。被路由去修复、能够增加 guard 或适合承担下一步工作，不构成 Teacher fault。

Teacher Work 若生成仍必须带 `teacher_role_id`、具体动作和完成检查，保证不会进入错误 consumer；其遗漏不作为前两类归因验收的阻断，但错误 Teacher Work 仍视为安全问题。

### 3.6 Source、Transition 与职责上下文

- invalid/indeterminate、runtime/provider/protocol failure 和 reference truth 不可判来源在模型调用前拦截。
- exact decision 与 route target 从实际 TransitionPlan 投影，不从 trigger 固定推导。
- 全局职责摘要让模型了解完整 Evolution 角色边界；每个 Run 的 local context 只突出实际 decision role、route、Student/Hook 和 causal-neighbor roles/mechanisms。
- `route_target_role` 是下一路由；Capability subject、Direction object 和 Teacher subject 均由证据分别确定。

### 3.7 结构化因果输入

顶层仍为 `trigger`、`route_target_role`、`direction`、`attempt`、`evidence`：

- `direction`：因果主张/机制方向和预期行为；
- `attempt`：实际 actor/机制、执行方式和覆盖，不重复 validity；
- `outcome`：观察 actor、行为和直接后果；
- `comparison`：两侧条件、差异、重复、有效机会数或 activation attribution，可空；
- `boundary_facts`：reference validity、input validity、implementation fidelity、data sufficiency、role-input sufficiency 的 typed assertion。

Boundary facts 必须来自 typed verdict、实际 input projection 或授权证据。前四类优先服务 Capability/Direction 判定；`role_input_sufficiency` 只有在已有明确 Teacher-work 证据时提供，不要求所有 case 填充。

### 3.8 Prompt 提取顺序

1. source eligibility 在调用前确定。
2. 检查 invalid input/projection、data/reference confound 和方向 falsifier，排除伪 capability。
3. 满足全部硬门槛时提取 Capability。
4. 独立提取 Direction，并写 disposition/revisit condition。
5. 若已有独立证据，再保守提取 Teacher Work。
6. 按 `student_capability`、`experiment_direction`、`teacher_work` 顺序输出。

默认只输出必要类型；相同事实和相同动作换类型改写仍算重复。

### 3.9 工具策略

- 每 Run 最多 20 次 evidence invocation，第 21 次拒绝；失败调用也计数。
- 20 次只是绝对 hard fuse。
- 工具读取优先解决 Capability 与 Direction 的未决门槛；默认零调用，通常 1–3 次成功读取后提交或返回空。
- 不为提高 Teacher Work 召回单独读取额外 view；不重复同一 `ref/view`。
- 任何 Run 达到 20 次均视为质量失败。

## 4. 计划实现

### 4.1 领域与架构

- 更新 `CONTEXT.md`，记录三类 Experience 的规范定义与 `Student Capability >= Experiment Direction > Teacher Work` 优先级。
- 更新 `docs/architecture/evolution.md`，记录 source eligibility、实际 Transition context、Teacher subject、20-call hard fuse 和 Capability/Direction-first 策略。

### 4.2 Attribution Registry 与 Transition Context

- 建立全局角色职责、确定性机制、negative decision family 和 Experience consumer 注册表。
- 从实际 TransitionPlan 投影 decision/route/local causal neighborhood。
- 删除 trigger 到 route target 的无条件固定映射，并覆盖普通 revision、预算耗尽、unchanged rejection 与 terminal 分支测试。

### 4.3 Input 与 Output Contract

- Experience Summarizer 升为 role version 2。
- Evidence observation 使用 outcome、可选 comparison 和 typed boundary facts，不兼容旧自由字符串。
- Experience Summary 升为 output version 2；Teacher-work Draft 独有 `teacher_role_id`，其他类型禁止该字段。
- Request builder 在调用前校验 source eligibility。

### 4.4 Resource、工具与 Prompt

- Model Context 注入全局职责摘要、实际 local transition context 和 evidence directory。
- Store 对所有 invocation 计数，前 20 次允许、第 21 次拒绝。
- Prompt 写入 Capability-first/Direction-second/Teacher-best-effort 顺序、严格证据门槛、consumer action、解除/重访条件、输出顺序和 `lesson <= 500`、`applicability <= 300` 限制。

### 4.5 Fixture 与真实 API

- 修正 Candidate Validation 的真实 source/route；收紧各 case 的 exact expected type set 和 decisive evidence atoms。
- 增加 invalid/indeterminate、unknown boundary 和空输出 case。
- 离线回归后执行 28 次真实 API 定向复核：
  - Capability：Hook instability、Distiller model boundary、semantic evaluator boundary，各三次；
  - Direction：no differential、harmful overtrigger、corpus confound、intrinsic grounding，各三次；
  - Capability + Direction overlap：Hook false-positive scope，各三次；
  - Teacher Work：empty passage、ordinary Candidate Validation 各一次；
  - invalid/insufficient 空输出一次。

## 5. 盘点结果

- v2 的主要未解决偏差正是前两类：方向无差异被误写成 capability，Hook capability 又被 route target 吸收到 Teacher Work。
- H3 的 capability-violating proposal 和 duplicate direction 指标直接依赖前两类；Teacher same-role recurrence 虽仍在 Goal 中，但用户明确不要求当前总结角色把它作为重点。
- 保留 Teacher-work-only `teacher_role_id` 仍有必要，因为即使低优先级输出也不能依赖自然语言解析或错误 route target；但无需为其提高输入体积或工具调用量。
- 28 次定向复核中，25 次直接验证 Capability、Direction 或两者重叠；Teacher Work 只保留两个 sanity case，符合新的优先级。
- Capability 的高优先级不能以召回替代精度：任何 invalid/implementation/direction case 被写成 capability 都会增加 false pruning 风险，应作为整套验证的硬失败。
