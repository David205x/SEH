# Hypothesis Researcher 边界保持 Prompt 实验计划

状态：待实施的实验交接  
日期：2026-08-13  
基准运行：`runs/evolution/20260809_base`  
前置实验：`runs/experiments/failure_landscape_boundary_awareness/20260812_173314`

## 1. 实验目标

本实验回答两个彼此分离的问题：

1. 在不修改角色协议的情况下，整体强化 shadow Hypothesis Researcher Prompt，能否让 Researcher 稳定区分“决定性失败状态”和“失败前置风险”，并据此选择可观察的干预阶段、条件与证据边界？
2. 对同一份冻结 Hypothesis 和同一批 Intervention Assignment，Intervention Worker 使用的 Teacher 模型开启或关闭 thinking，是否会造成条件判断、动作选择或干预效果的不稳定和劣化？

本实验不再验证 Failure Landscape。前置实验已经表明 Landscape 没有为 Analyst 或 Researcher 带来配对增益；本轮直接复用其冻结 Failure Direction，隔离 Researcher Prompt 的影响。

## 2. 前置证据与待验证命题

前置实验的六份 shadow Researcher 输出中，四份选择了 `post_tool`：在第一次单边检索后立即激活。对应 Analyst 已经说明“单边检索本身不是缺陷，决定性失败是随后把缺失证据解释为零并定案”，因此这些输出把决定性失败前移成了更宽的前兆。另两份 `pre_final` 输出保留了该时间边界。

当前 Prompt 已要求保持 `pattern`、`applicability` 和 `caveats`，但没有明确要求：

- 所选 phase 必须能观察到 Hypothesis 实际声称的触发状态；
- 当前 phase 的 `activation_condition` 不得依赖尚未发生的未来行为；
- 早于决定性失败的干预必须被表述为预防性干预，而不能冒充对已发生失败的精准识别；
- Intervention Worker 只判断冻结条件是否成立，不会额外替 Researcher 判断“这个案例是否真的需要帮助”。

本轮主命题是：

> 将这些要求融入 shadow Researcher Prompt 的目标、流程、字段说明和提交前检查后，Researcher 会更稳定地保持 Analyst 的时间边界；当它有意选择较早触发时，也能如实定义预防性范围及其相邻对照证据，而不是机械地一律选择更晚 phase。

## 3. 本实验使用的术语

- **决定性失败状态**：Analyst 诊断中已经观察到、足以把该行为判为目标失败的运行时状态。例如已生成把缺失证据当作零的最终比较结论。
- **前置风险状态**：可能通向目标失败，但也可能自然恢复或正确完成的更早状态。例如第一次检索只覆盖比较中的一个实体。
- **纠正性干预**：在决定性失败状态已经可观察后阻止或修正该决定。
- **预防性干预**：在决定性失败尚未发生时，对前置风险状态进行干预。
- **同前兆自然恢复对照**：与目标案例共享前置风险，但在未干预分支中会继续检索、正确作答或安全地表达不确定性的案例。
- **边界保持**：Researcher 没有把 Analyst 的决定性失败、适用条件、排除项或未知项静默扩宽；若主动研究更宽的预防性触发，则明确改变了因果主张并为该宽度设置可判定的证据义务。

“错误在全数据集中的比例”不属于 Researcher 的估计职责。Researcher 只保留 Analyst 已提供的计数和范围，不自行推断总体流行度。

## 4. 实施和修改边界

### 4.1 允许的改动

- 整体修订实验 shadow Researcher Prompt：
  `experiments/teacher_query_views/templates/hypothesis_researcher/prompt/system.md`
- 在 `experiments/` 下新增或修改一次性实验编排脚本和测试。
- 在 `runs/experiments/researcher_boundary_prompt/<timestamp>/` 保存运行产物。
- 调用当前已配置的 Teacher API、Student backend、shadow Hypothesis Researcher、正式 Intervention Worker 和 Trial Reviewer。
- 为实验脚本增加只作用于单次运行的 Intervention Worker `thinking_mode=enabled|disabled` 覆盖。

### 4.2 保持不变

- 不修改 `harness_templates/teacher/hypothesis_researcher/` 正式模板。
- 不修改 `InterventionHypothesis`、`trial_review@2` 或其他正式协议。
- 不修改正式 Selector、Controller、Distiller、Compiler、Conformance 或 Candidate promotion 逻辑。
- 不在本实验中运行 Distiller、Compiler、Conformance 或完整 Candidate Evaluation。
- 不把案例实体、正确答案或隐藏边界结论写入 Researcher 或 Worker Prompt。

实验脚本启动时必须记录正式模板和 shadow 模板的 SHA-256；结束时重新计算，证明正式模板未被改动。API 密钥只从现有环境配置读取，不写入实验产物。

## 5. Shadow Researcher Prompt 的整体修订要求

### 5.1 修改方式

不要在现有 Prompt 尾部追加一段“注意边界”的补丁。应在保持原有职责和输出协议的基础上，重新组织以下部分，使逻辑按“诊断目标 → 边界解释 → phase 选择 → 干预合同 → 证据预注册 → 输出字段”自然展开：

1. `Objective`
2. `Intervention handoff`
3. 边界与 phase 选择原则
4. `Required procedure`
5. 修订 continuation 说明
6. `Output contract`
7. `Before submitting` 检查

原有工具读取义务、能力目录读取、协议字段、长度限制、禁止泄露和多 phase 约束必须保留。

### 5.2 Prompt 必须表达的控制语义

#### Objective 与角色边界

- Researcher 把冻结的 Failure Direction 转成一份具体、可证伪的软干预假设。
- 不估计全局错误比例，不替 Selector 选择具体样本，不判断总体 Candidate 收益。
- 必须保持 Analyst 的决定性失败、适用范围、排除项、证据范围和未知项。

#### Intervention Worker 的真实语义

Prompt 必须明确说明：

> Intervention Worker 只根据当前 phase 可见快照判断冻结的 `activation_condition` 是否成立。条件成立时它必须忠实执行 `instruction`；它不会在条件之外自行判断 Student 是否本来会恢复、当前是否“真的需要帮助”，也不会替 Researcher 收窄触发范围。

这条说明应放在 `Intervention handoff` 中，而不是只放在末尾检查。

#### 决定性失败与前置风险

在选择 `fork_phase` 前，Researcher 必须从 Failure Direction 中区分：

- 哪些事实只是失败前兆；
- 哪些事实使目标失败成为决定性、可观察的状态；
- 哪些相邻行为共享前兆但不满足决定性失败；
- 哪些信息仍未知，不能被写成肯定条件。

不要求新增输出字段；这些判断应落实到已有的 `fork_phase`、`activation_condition`、`applicability`、`falsifier` 和 `special_evidence_obligations`。

#### 纠正性与预防性方案

- 若声称纠正 Analyst 已诊断的失败，选择的 phase 必须已经能观察到构成该失败的必要事实。
- 若选择更早 phase，只因该位置更容易干预并不充分。Researcher 必须把方案表述为针对前置风险的预防性假设。
- 预防性方案应把“同前兆自然恢复”或“同前兆正确行为”写入一项具体的 `special_evidence_obligation`，以观察不必要激活、附加工具调用、答案扰动或成本。
- 不应诱导 Researcher 一律选择 `pre_final`；只要语义主张和证据义务匹配，`post_tool` 仍然是合法研究方案。

#### Phase 可观察性

- `activation_condition` 的每个必要事实都必须能从该 phase 的快照独立判断。
- 不得在第一次 `post_tool` 时写入“这是唯一一次检索”“Student 将直接定案”等未来事实。
- 对当前 phase 不可观察、但对精准边界不可缺少的事实，应选择更晚 phase；若坚持早期触发，则按预防性方案处理。
- “最早可恢复 phase”只是能力约束，不等于“最佳或最窄触发 phase”。

#### 证据义务

- 默认 cross-case positive/negative coverage 只保证一般数量覆盖，不自动保证最关键的邻近语义边界被覆盖。
- 若精确失败状态与前兆之间存在决定性区别，Researcher 应使用最多两项现有 `special_evidence_obligations` 指明需要观察的相邻状态。
- Researcher 只描述需要什么类别的证据，不指定命名案例或样本 ID；Selector 仍由程序控制。

### 5.3 提交前检查应嵌入原有检查清单

最终检查至少包含：

- 逐项确认 Analyst pattern 中的必要事实已进入 Hypothesis，或被明确保留为限制；
- 确认 `activation_condition` 没有引用当前 phase 之后的行为；
- 确认方案是纠正性还是预防性，并且字段表述与该类型一致；
- 若是预防性，确认至少一项证据义务能够观察同前兆自然恢复或不需要干预的状态；
- 确认 success/falsifier 都位于冻结触发范围内；
- 确认没有假设 Worker 会在冻结条件之外自行收窄触发。

## 6. 阶段一：Researcher Prompt 配对实验

### 6.1 冻结输入

不重新运行 Failure Analyst。使用前置实验中三份边界信息充分、但表达方式不同的冻结 Failure Direction：

1. `replay_shadow/control/analyst_01.json`：明确说明单边检索也出现在正确轨迹中，决定性缺陷是最终化未验证负面结论。
2. `replay_shadow/control/analyst_02.json`：明确把该模式称为风险而非确定性失败，并限制在已检查案例。
3. `replay_shadow/landscape/analyst_03.json`：明确区分单边证据前兆、最终 absence-as-zero 决定和查询双方后的拒答对照。

基准目录为：

`runs/experiments/failure_landscape_boundary_awareness/20260812_173314/replay_shadow/`

运行前把三份输入复制到新实验目录并记录摘要和 SHA-256。Landscape 身份不进入 Researcher 上下文；这里只有冻结 Failure Direction，不再提供 Landscape。

### 6.2 A/B 变体

- `Control`：修改前的 shadow Researcher Prompt 冻结副本。
- `Boundary`：按第 5 节整体修订后的 shadow Researcher Prompt。

两组使用完全相同的：

- Failure Direction；
- Researcher 工具和查询视图；
- Teacher 模型、thinking 配置、temperature、token/turn budget；
- Student Behavior Interface 和 Intervention Capability；
- 每个配对 repetition 的 seed。

每份输入执行 3 次配对重复，共 `3 inputs × 2 prompts × 3 repetitions = 18` 次 Researcher 调用。每个 repetition 在 Control/Boundary 间交替先后顺序；配对 seed 相同，输入间使用确定性派生的不同 seed。

### 6.3 评估维度

匿名化十八份输出。自动评分器只能提供辅助意见；前置实验的自动评分器漏掉了时间边界问题，因此本轮人工复核是权威结果。

每份 Hypothesis 按以下项目记 `0/1`，并引用具体字段：

| 项目 | 通过条件 |
| --- | --- |
| 诊断保持 | 没有丢失 Analyst 的决定性失败状态、适用范围和关键 caveat。 |
| 时间可观察性 | `activation_condition` 的全部必要事实在所选 phase 已经可见，不依赖未来行为。 |
| 主张与 phase 一致 | 纠正性方案观测到决定性失败；较早触发被明确视为预防性风险干预。 |
| 相邻边界可证伪 | 预防性方案要求观察同前兆自然恢复；纠正性方案明确排除尚未失败的前兆状态。 |
| Worker 语义正确 | 没有依赖 Worker 在冻结条件之外自行判断“是否需要干预”。 |
| 比例纪律 | 不猜测总体比例，只保留输入已支持的范围和计数。 |

额外记录：协议是否合法、phase 分布、Researcher requests/tool calls/tokens、是否命中 max token、是否包含案例泄露。

`post_tool` 不自动扣分，`pre_final` 也不自动加分；只判断 phase、因果主张和证据义务是否一致。

### 6.4 阶段一判定

Boundary Prompt 记为值得进入下游验证，需要同时满足：

- 9/9 输出协议合法且没有案例泄露；
- 至少 8/9 通过“时间可观察性”和“Worker 语义正确”；
- 三份输入中至少两份各有 2/3 以上重复通过全部六项；
- 相对配对 Control，至少 4/9 输出提高，且最多 1/9 出现边界保持回退；
- 改善不是简单地把所有输出强制成同一个 phase，而是能正确处理纠正性或预防性两种方案。

若未达到该条件，停止下游扩展，保留产物并只在 shadow Prompt 中继续研究；不得修改正式 Researcher Prompt。

## 7. 阶段二：下游 Intervention 行为验证

阶段一通过后才执行。该阶段不证明 Candidate 的全局价值，只检查 Prompt 差异是否会转化为实际激活和 Student 分支差异。

### 7.1 冻结 Hypothesis 的选择

按固定规则从阶段一选择一对 Control/Boundary Hypothesis：

1. 按输入顺序、repetition 顺序寻找第一对“Control 时间边界失败、Boundary 通过”的合法输出；
2. 若不存在这种分叉，选择第一对均合法的输出，并在报告中注明没有形成预期边界分叉；
3. 选择后立即冻结两份 Hypothesis 及其 SHA-256，不因下游结果修改。

阶段一的主要结论使用全部十八份输出，不依赖这一个下游选择，因此该选择只用于机制示范，不替代 Prompt A/B 统计。

### 7.2 固定案例组

对两份 Hypothesis 使用相同逻辑案例和 replicate；程序根据各自 `fork_phase` 确定性解析 phase-compatible prefix：

| 类别 | Assignment |
| --- | --- |
| 目标失败 | `5a7e36045542991319bc9440/r000` |
| 目标失败重复 | `5a7e36045542991319bc9440/r001` |
| 同类比较、会继续检索并可正确完成 | `5a736bfa5542991f29ee2e03/r001` |
| 单边证据下仍获得正确结果 | `5a81ff1d554299676cceb1c3/r001` |
| 表面相邻但不是两实体属性比较 | `5a822d4655429926c1cdae45/r000` |

案例用途只存在于实验清单和评审中，不把“正例/负例”、参考答案或预期动作告诉 Intervention Worker。

若某 Hypothesis 的 phase 在某案例中没有兼容 prefix，记录 `not_reachable`，不替换案例。对于 `post_tool`，选择最早的 phase-compatible prefix；对于 `pre_final`，选择冻结 final candidate 对应 prefix。多 phase 方案从其 `fork_phase` 启动，并保留同一 Worker session。

### 7.3 Prompt 差异的下游运行

先固定 Intervention Worker Teacher `thinking_mode=enabled`，运行：

- Control Hypothesis × 5 assignments × 3 repeats；
- Boundary Hypothesis × 5 assignments × 3 repeats。

每个 Assignment 后运行正式 Trial Reviewer。Reviewer 的模型、thinking、temperature 和 seed 策略在两组间固定，不继承 Worker thinking 开关。Trial Reviewer 只评估冻结 Hypothesis，不向 Researcher回流修订。

比较：

- predicate `positive/negative/uncertain`；
- terminal action 是否与 predicate 一致；
- 目标失败上的 immediate expected effect；
- 自然恢复和正确案例上的激活、答案扰动、额外 tool calls/tokens；
- 非目标案例是否保持不变；
- instruction fidelity、case leakage、runtime failure 和 branch score。

## 8. 阶段三：Intervention Worker thinking 开关实验

### 8.1 隔离变量

冻结阶段二使用的 Boundary Hypothesis 和五个 Assignment。复用其 `thinking_mode=enabled` 结果，再以完全相同的输入运行 `thinking_mode=disabled`，每个 Assignment 3 次。

唯一允许变化的是 Intervention Worker Teacher 模型请求中的 thinking 开关。以下配置必须保持相同：

- Hypothesis 和 prefix；
- Student 模型、seed、temperature 和 max steps；
- Worker 模型 ID、temperature、max tokens、max turns 和配对 seed；
- Worker Prompt 和工具视图；
- Trial Reviewer 与可选 Teacher Judge 配置。

实验产物必须记录 Worker 请求实际生效的 `thinking_mode`。如果当前 provider 不支持显式 thinking 开关，或请求层没有发送该字段，应 fail fast，把本阶段记为未执行，而不是把两组相同配置当作有效 A/B。

为避免 Reviewer/Judge 的 thinking 同时变化，实验 runner 应在构造 Worker `teacher_config` 时局部覆盖该字段，不修改 `.env` 或全局 `config/runtime.yaml`。如果现有 runner 无法将 Worker 与 Judge 配置分离，先在实验脚本中增加显式的独立配置；不要修改生产运行路径。

### 8.2 稳定性和效果指标

每个 mode 分别统计：

- API/协议完成率、tool error、max-turn/max-token 失败；
- 同一 Assignment 三次的 predicate verdict 和 terminal action 一致性；
- Worker 对冻结 instruction 的忠实度与泄露；
- 正向激活后的 immediate expected-effect 成功数；
- negative/uncertain 状态是否正确保持不变；
- Student branch score、steps、tool calls、tokens；
- Worker requests、input/output/total tokens。

定义：

- **模式内不稳定**：同一 mode、同一 Assignment 的三次有效运行出现不同 predicate verdict 或不同 terminal action kind。
- **跨模式决策漂移**：thinking on/off 对同一 Assignment 的多数 predicate verdict 或多数 action kind 不同。
- **效果劣化**：在至少两个有效正向 Trial 且覆盖至少两个逻辑案例时，一种 mode 的 expected-effect 成功数比另一种少至少 2，或在至少两个不同案例上造成更差 branch score/明显额外工具调用而没有对应过程收益。
- **不可判定**：正向激活不足两个、provider 开关未实际生效，或传输错误使任何一组少于 2/3 有效重复。

报告必须给出原始分子、分母和 distinct-example 数，不把这五个案例外推成全局结论。若观察到任何模式内不稳定，扩展对应 Assignment 到 5 次；不要无差别扩展全部案例。

## 9. 实验编排与测试要求

建议新增单一入口：

`experiments/run_researcher_boundary_prompt_experiment.py`

入口至少支持：

- `prepare`：冻结输入、Control Prompt、Boundary Prompt、模板和哈希；
- `run-researcher-ab`：执行阶段一配对调用；
- `review-researcher`：匿名化并生成评分包；
- `prepare-intervention`：按固定规则冻结 Hypothesis 和 Assignment；
- `run-intervention`：运行指定 Hypothesis 与 Worker thinking mode；
- `review-trials`：调用 Trial Reviewer并聚合确定性指标；
- `summarize`：生成 `summary.json` 和 `report.md`。

最低测试覆盖：

- 正式 Researcher 模板在 prepare/run 后哈希不变；
- Control/Boundary 配对输入、预算和 seed 一致；
- `post_tool` condition 中未来事实能被评审规则标记；
- Assignment 顺序和 prefix 解析可重复；
- Worker thinking 覆盖只改变 Worker model config；
- enabled/disabled 产物记录实际生效配置；
- 传输错误与协议错误不会被计为模型行为差异；
- 汇总按 example 与 replicate 分别计数，不把重复当成跨案例覆盖。

## 10. 产物目录

所有产物写入：

`runs/experiments/researcher_boundary_prompt/<timestamp>/`

至少包含：

- `manifest.json`：输入、模板、模型配置和哈希；
- `templates/control/hypothesis_researcher/`：修改前的冻结 shadow 模板；
- `templates/boundary/hypothesis_researcher/`：整体修订后的冻结 shadow 模板；
- `inputs/failure_directions/`：三份冻结输入；
- `researcher_ab/<input>/<variant>_<rep>.json`；
- `researcher_review/anonymous_packet.json`；
- `researcher_review/manual_review.json`；
- `intervention/selection.json`：冻结 Hypothesis 和 Assignment 选择依据；
- `intervention/thinking_enabled/` 与 `intervention/thinking_disabled/`；
- `trial_reviews/`；
- `summary.json`；
- `report.md`。

`report.md` 应分别给出：

1. Prompt A/B 的边界保持结果；
2. 下游真实激活与 Student 分支结果；
3. Worker thinking on/off 的稳定性、效果与 token 差异；
4. 工程错误、角色行为和案例特定现象的区分；
5. 是否值得把 Boundary Prompt 的语义迁移到正式 Researcher 的建议。

## 11. 停止与后续决策

- 阶段一未通过：停止；继续在实验 shadow Prompt 上修改，不进入正式模板。
- 阶段一通过但下游行为没有改善：检查评分是否只优化了文字表述，或 Evidence Assignment 是否没有命中声明的邻近边界；不直接迁移正式 Prompt。
- Boundary Hypothesis 下游边界合理，且一种 Worker thinking mode 明显更稳定：只形成 Worker 配置建议，Researcher Prompt 结论独立保留。
- thinking 两组无明显差异：记录为本案例组内未观察到劣化，不声称两个配置全局等价。
- Prompt 和下游结果均稳定改善：再单独提出正式 Researcher Prompt 迁移任务；迁移不属于本实验执行范围。

## 12. 最短执行顺序

1. 冻结三份 Failure Direction、修改前 shadow Prompt 和正式模板哈希。
2. 整体改写实验 shadow Researcher Prompt，并保存 Boundary 模板副本。
3. 执行 18 次配对 Researcher 调用和人工权威评审。
4. 阶段一通过后，按固定规则冻结一对 Hypothesis 和五个 Assignment。
5. 以 Worker thinking enabled 运行 Control/Boundary 下游 Trial，并执行 Trial Reviewer。
6. 复用 Boundary-enabled 结果，补跑 Boundary-disabled 的同输入三次重复。
7. 对分叉 Assignment 必要时扩展到 5 次。
8. 生成 `summary.json` 和 `report.md`，不自动修改正式 Prompt。
