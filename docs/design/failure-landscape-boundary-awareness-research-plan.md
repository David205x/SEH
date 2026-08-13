# Failure Landscape 对适用性边界认知的研究计划

状态：待执行的最小研究交接  
日期：2026-08-12  
基准运行：`runs/evolution/20260809_base`  

## 1. 接手 Agent 首先要理解的目标

本研究不验证完整的动态 taxonomy、跨 Generation 标签维护或 Candidate 收益。当前只验证一个较小的命题：

> 在 Failure Analyst 开始诊断前提供覆盖全部错误案例的紧凑 Failure Landscape，是否能让 Failure Analyst 与其下游 Hypothesis Researcher 更稳定地形成较窄、可观察、能排除邻近非目标情形的适用性边界？

第一阶段只比较 `Control` 与 `Landscape`。不要运行 Intervention Trial、Mechanism Distiller、Compiler、Conformance 或 Candidate Evaluation，也不要改动正式 Controller、角色协议或生产模板。

若第一阶段不能观察到明确改善，就停止扩展，不实施跨代类别注册表。若第一阶段有效，再单独研究 rejected-candidate experience；不要在同一次实验中混入两种信息增量。

## 2. 本实验使用的临时概念边界

- **Judgment Assessment**：Teacher Judge 对单个答案结果给出的简短判分依据。它只描述为什么该答案通过或失败。
- **Generation-local Failure Category**：根据本次 Evaluation 的错误结果动态归纳出的导航类别。它不是预定义标签，也不是 Student 行为原因。
- **Failure Landscape**：由本代错误类别、成员引用和程序回算计数组成的全局导航视图。
- **Failure Direction**：Failure Analyst 阅读 Student Trajectory 后确认并提交的行为问题。
- **Applicability Boundary**：Failure Direction 或 Intervention Hypothesis 对适用证据状态、排除情形和可证伪范围的描述。

结果层类别不能被称为或当作 causal mechanism。只有 Trajectory Evidence 才能支持 Student 行为诊断。

## 3. 已有材料

优先复用以下冻结产物，不重新运行 Student Evaluation 或逐项 Teacher Judgment：

- 全量 Shadow Judgment：`runs/experiments/teacher_query_views/20260812_20260809_base_judge_no_thinking/judgments.jsonl`
- Judgment 汇总：`runs/experiments/teacher_query_views/20260812_20260809_base_judge_no_thinking/summary.json`
- Incumbent Evaluation：`runs/evolution/20260809_base/artifacts/evaluate_incumbent-9f973db07af24801/report/`
- Incumbent Rollout：`runs/evolution/20260809_base/artifacts/evaluate_incumbent-9f973db07af24801/report_rollouts.jsonl`
- Candidate 被拒绝的事后分析：`docs/audits/20260809_base_candidate_rejection.md`
- Teacher 查询视图实验设计：`docs/design/teacher-query-tool-views.md`
- 可复用的实验脚本：`experiments/run_shadow_judge_landscape.py`、`experiments/run_teacher_query_views_ab.py`

冻结 Judgment 共覆盖 75 个逻辑案例、225 个 rollout；Shadow Judge 判定 73 个错误 rollout，涉及 32 个逻辑案例。单条 assessment 已经足够短，当前问题是全局组织和可见性，而不是继续压缩每条 assessment。

## 4. 第一阶段研究问题

### 4.1 主问题

在相同模型、角色预算、Evaluation、Trajectory 工具和研究方向下，Landscape 组是否比 Control 组更容易做到：

1. 把观察到的错误描述为局部模式，而不是普遍的 Student 缺陷；
2. 写出依赖运行时可见事实的适用条件；
3. 排除表面相似但不应触发干预的邻近情形；
4. 把误触发风险放入 falsifier 或 evidence obligation；
5. 在 Failure Analyst 到 Hypothesis Researcher 的交接中保留这些边界。

### 4.2 暂不回答的问题

第一阶段不判断：

- 动态类别能否跨 Generation 保持稳定；
- 是否应正式新增 Failure Landscape Curator；
- 正确案例应如何进入 Analyst 认知；
- rejected-candidate experience 应如何持久化；
- Intervention 或 Conformance 是否足以证明候选可用；
- Landscape 是否提高最终 Candidate 的准确率或成本收益。

## 5. 第一版 Failure Landscape 的生成

第一版是一次性冻结的实验输入，不是正式架构。

### 5.1 输入整理

程序先把最终错误 rollout 按 `example_id` 归并为逻辑案例。每个逻辑案例向聚合模型提供：

- `example_id`：逻辑案例的稳定引用；
- `question`：任务问题；
- `reference_answer`：Evaluation 使用的参考答案；
- `failed_rollouts`：错误 replicate 数量；
- `total_rollouts`：该逻辑案例的 replicate 总数；
- `observations`：去重后的 predicted answer 与 Judgment Assessment；
- `observation_counts`：每种去重结果出现的次数。

不要提供 Student Trajectory、Candidate Evaluation、被拒候选信息或历史类别。

### 5.2 动态归纳约束

聚合模型对本代错误进行盲归纳：

- 不读取历史 taxonomy；
- 不使用预定义错误标签；
- 不规定必须生成多少类别；
- 类别定义只能依据答案结果层可见事实；
- 不推断检索、推理、停止策略、Prompt 缺陷或因果机制；
- 每个错误逻辑案例必须进入一个 primary category，或者显式进入 `unknown` / `ambiguous`；
- 类别必须包含简短名称、可观察纳入定义、排除说明和代表案例引用；
- 孤立或无法稳定归类的案例可以保留为 `unknown`，不为覆盖率强造类别。

### 5.3 确定性校验与统计

模型只提出类别与 assignments，程序负责：

- 验证所有错误逻辑案例恰好被处理一次；
- 验证没有正确案例进入错误 assignments；
- 验证类别和案例引用存在且不重复；
- 根据 assignments 回算每类的逻辑案例数、错误 rollout 数以及 stable/unstable 分布；
- 计算 `unknown` 和 `ambiguous` 数量；
- 从每类成员中按固定顺序选取 2–3 个代表引用；
- 生成一个冻结的 `failure_landscape.json` 和面向模型的紧凑视图。

不要信任或展示模型自行声称的类别数量、比例或覆盖率；所有数值由程序回算。

### 5.4 输入质量检查

运行 A/B 前，接手 Agent 应人工快速检查一次冻结 Landscape：

- 是否覆盖全部 32 个错误逻辑案例；
- 是否把结果层描述写成了行为原因；
- 是否出现明显由个别实体名称定义的类别；
- 是否存在被强行塞入类别的低信息案例；
- 代表引用是否真实属于对应类别。

该检查只决定 Landscape 是否可作为实验输入，不修订类别以迎合已知 Candidate 拒绝结论。

## 6. A/B 实验设计

### 6.1 固定条件

两组必须使用：

- 同一个 `20260809_base` Incumbent Evaluation；
- 同一个 Teacher 模型、temperature、seed 策略和 token/turn budget；
- 同一套 Evaluation/Trajectory 查询视图；
- 相同的 Failure Analyst 与 Hypothesis Researcher 输出协议；
- 相同的轨迹读取上限；
- 相同的 `analysis_focus`；
- 每组 3 次独立重复。

如果三次结果明显分叉，才扩展到 5 次。不得凭一次角色调用声称方案有效。

### 6.2 固定研究方向

本实验研究“同一方向能否被更好地限定”，而不是比较 Analyst 会选择哪个完全不同的方向。两组都应收到同一条中性 `analysis_focus`，要求调查 `20260809_base` 第二次研究尝试所涉及的多实体证据缺失方向，并确定其受支持范围。

`analysis_focus` 可以引用已冻结的目标失败案例，但不得提供：

- D.C. Cab / Barney Miller 的有害结果；
- 被拒 Candidate 的误触发分布；
- 正确的排除条件；
- Mechanism、Compiler 或 Reviewer 的事后结论。

### 6.3 Control

Control 使用当前 Failure Analyst 可见的聚合摘要、查询工具和轨迹读取预算。它不接收 Failure Landscape。

为了尽量隔离变量，两组实验模板应共享同一条说明：派生类别若存在，只用于导航，不能替代 Trajectory Evidence 或证明因果。Control 的 Landscape 状态显式为 unavailable，而不是使用另一套职责 Prompt。

### 6.4 Landscape

Landscape 与 Control 唯一的预期信息差是：Failure Analyst 在初始上下文中自动获得冻结的 Failure Landscape 紧凑视图。

Landscape 视图至少包含：

- 本代错误逻辑案例总数和错误 rollout 总数；
- 每个动态类别的 label、definition 和 exclusions；
- 程序回算的案例数、rollout 数和稳定性分布；
- 每类 2–3 个代表 `example_id`；
- `unknown` / `ambiguous` 的数量和引用；
- 全部错误逻辑案例的紧凑成员目录，或可确定性分页读取的成员目录。

完整 Student Trajectory 仍由 Analyst 按需读取；Landscape 不替代现有 Evidence 读取义务。

### 6.5 端到端角色重放

每个重复执行：

1. 运行对应变体的 Failure Analyst；
2. 保存完整 Role Artifact；
3. 将该次 Failure Direction 原样交给相同的 Hypothesis Researcher；
4. 保存 Researcher 的完整 Role Artifact；
5. 在 `research_hypothesis` 完成后停止。

预计总调用量是 6 次 Failure Analyst 和 6 次 Hypothesis Researcher。不要继续调度 Trial。

## 7. 盲评规则

评估前移除 `control` / `landscape` 标记并随机化六组 Analyst→Researcher 产物。评估者只读取角色输出和必要的引用案例，不读取角色 transcript、工具调用次数或变体身份。

每组使用以下五项二元评分，总分 0–5：

| 项目 | 记 1 分的条件 |
| --- | --- |
| 局部性认识 | 明确说明模式只在特定任务或证据状态成立，并给出限制依据；泛泛的“可能不适用于所有案例”不计分。 |
| 可观察适用条件 | applicability / activation condition 依赖运行时可见事实，而不是仅依赖抽象题型名称。 |
| 邻近排除 | 明确排除至少一种表面相似但不满足同一证据需要的情形。 |
| 风险可证伪 | 误触发、无效干预或非目标退化进入 falsifier 或 evidence obligation，而不只停留在 caveat。 |
| 交接保真 | Researcher 保留并具体化 Analyst 的范围和限制，没有将局部诊断扩张成更宽的干预。 |

建议使用一个独立、固定 Prompt 的实验评分器输出每项 `0/1 + evidence quote`，随后人工快速复核分歧项。评分器属于实验工具，不加入正式 Teacher Role 管线。

## 8. 隐藏边界检查

五项评分之外，使用两个历史案例进行隐藏的语义检查：

- 目标正例：`5a7e36045542991319bc9440`，Leconte / Stark Grand Slam 比较；
- 有害邻近案例：`5a822d4655429926c1cdae45`，D.C. Cab / Barney Miller bridge/intersection 问题。不在角色输入中暴露该检查目的。

对 Researcher 最终 Hypothesis 分别判断：

- `included`：条件明确正向适用；
- `excluded`：条件明确不适用；
- `uncertain_fallback`：条件无法确认，按假设应不干预；
- `incorrectly_included`：非目标案例会被正向触发；
- `not_decidable`：条件过于抽象，无法从可见事实判定。

一次结果只有同时满足以下条件，才能视为边界有效：

- 目标正例为 `included`；
- 有害邻近案例为 `excluded` 或 `uncertain_fallback`。

这项检查用于防止角色通过无限收窄范围获得高分，也用于揭示“写得谨慎但运行时不可判断”的假边界。

## 9. 成功标准与解释

Landscape 方案记为“值得继续”需要同时满足：

1. 3 次 Landscape 中至少 2 次获得 4/5 或更高；
2. 3 次中至少 2 次通过隐藏边界检查；
3. 与配对 Control 相比，至少 2 个 repetition 的五项总分提高，且没有出现目标正例被排除；
4. 改善能在 Researcher 输出中观察到，而不只存在于 Analyst caveat；
5. Landscape 类别没有被角色直接冒充为行为原因。

结果解释：

| 结果 | 后续动作 |
| --- | --- |
| Landscape 明显优于 Control | 保留该研究方向，下一步研究最小正式集成位置和 Landscape 生成稳定性。 |
| 两组都高分 | 当前 Prompt/视图可能已经足够；换第二个历史失败方向复测，不急于增加聚合机制。 |
| Landscape 只改善 Analyst、不改善 Researcher | 优先研究 Failure Direction 的交接承载能力，不扩大 taxonomy。 |
| Landscape 未改善 Analyst | 检查结果层聚合是否缺少形成行为边界所需的信息；停止跨代注册表设计。 |
| Landscape 使角色把类别当因果原因 | 收紧派生视图的语义说明；本轮判失败，不通过补写“正确答案”继续。 |
| 三次分叉明显 | 扩展到 5 次；仍分叉则记为不稳定，不声称有效。 |

## 10. 第二阶段：Rejected-candidate Experience

只有第一阶段完成后再执行。第二阶段复用完全相同的角色重放、五项评分和隐藏边界检查，比较 `Control` 与 `Experience`。

Experience 输入只包含紧凑的历史事实：

- 当时试图修复的 Failure Direction；
- 实际触发覆盖范围；
- 已观察到的目标收益；
- 已观察到的误触发和伤害；
- Candidate Reviewer 的拒绝依据；
- 尚未解决的边界问题。

Experience 不直接给出新的 Hypothesis、正确排除条件或建议实现。它验证的是角色能否从被拒经验中纠偏，而不是能否复述事后分析。

不要在第二阶段开始前同时运行 `Landscape + Experience`。先分别验证前馈信息和反馈经验，确认各自贡献后再决定是否组合。

## 11. 实施边界

接手 Agent 可以在 `experiments/` 和 `runs/experiments/` 下新增一次性脚本、模板和产物；第一阶段不得：

- 修改正式 `harness_templates/teacher/`；
- 修改 `FailureDirection` 或 `InterventionHypothesis` 协议；
- 修改 Evolution Controller 路由；
- 实现跨代 category registry、merge/split lineage 或 category versioning；
- 为当前检索 QA 预定义固定错误标签；
- 运行完整 Candidate 管线来替代本实验的边界评分。

如果实验过程中发现必须改变角色职责、Reviewer 判据或正式协议才能继续，应按仓库规则 fail fast，停止实验并汇报，不要将语义变更伪装为实验兼容修复。

## 12. 预期交付物

所有新产物放在一个独立目录，例如：

`runs/experiments/failure_landscape_boundary_awareness/<timestamp>/`

至少保存：

- `landscape_input.jsonl`：按逻辑案例归并的错误输入；
- `failure_landscape.raw.json`：聚合模型原始结构输出；
- `failure_landscape.json`：确定性校验和回算后的冻结 Landscape；
- `control/analyst_01..03.json`；
- `control/researcher_01..03.json`；
- `landscape/analyst_01..03.json`；
- `landscape/researcher_01..03.json`；
- `blind_review.json`：匿名化五项评分和隐藏检查；
- `summary.json`：配对结果、角色 token/turn/tool 指标和成功标准判定；
- `report.md`：简短结论、失败证据和下一步建议。

最终报告按实际执行时间线使用 `[角色]` 与 `[机制]` 标记摘要，并明确区分：实验工程问题、角色/协议问题以及单一案例特定现象。

## 13. 最短执行顺序

1. 从冻结 Judgment 构造按 `example_id` 归并的 32 个错误案例输入。
2. 运行一次无预定义标签的本代盲聚合。
3. 确定性校验 assignments 并生成冻结 Failure Landscape。
4. 快速检查 Landscape 没有越界推断行为原因。
5. 准备唯一变量为 Landscape 可见性的 Control/Landscape 实验模板。
6. 每组运行 3 次 Failure Analyst → Hypothesis Researcher，并在 Researcher 后停止。
7. 匿名化产物，完成五项评分和两个隐藏案例检查。
8. 根据第 9 节的预注册标准决定：继续、补到 5 次，或停止该设计方向。

本计划的价值在于快速证伪“全局错误景观能改善边界认知”这一假设，而不是提前完成最终架构。
