# Teacher 角色定义

## 文档目的

本文档定义 Teacher 控制面中的模型角色。它只回答三个问题：自进化过程需要哪些模型职责、各角色完成职责时需要看到什么、模型应当输出什么语义结果。

本文档不规定代码模块、类名、持久化格式或完整状态机，也不要求角色之间的字段逐项对接。

当前已独立实现并验证 `Failure Analyst`、`Hypothesis Researcher`、`Intervention Worker`、`Trial Reviewer`、`Evidence Reviewer`、`Mechanism Distiller`、`Compiler` 和 `Candidate Reviewer`，并由正式
[Evolution Controller](evolution-controller.md) 装配为可恢复闭环。Teacher
Judge 仍使用原有 evaluation 实现。角色实现与运行边界见
[Teacher Runtime](teacher-runtime.md)。

## 协议边界

系统需要区分两类协议：

- **状态转移协议**是控制面维护的完整记录，包括 ID、版本与父子关系、预算、时间、状态、输入摘要、provenance、验证结果和下一状态。
- **模型输入输出协议**只包含当前角色作出语义判断所必需的信息，是状态转移协议的子集。
- 模型不生成可由程序确定的字段。控制面负责补充运行元数据、执行工具动作、验证模型输出，并将语义结果合并为完整状态记录。
- 角色输出只表达局部判断，例如继续取证、形成机制或拒绝候选；任何单一模型角色都不能终止整个 evolution run。
- 内容较多的产物应通过多次窄工具调用逐步构造。最终结构化输出只提交决策和产物引用，不要求模型一次返回完整大对象。

确定性的 Experiment Controller 负责调度、预算、检查点、重试和状态转移，不属于本文定义的模型角色。

## 跨回合经验边界

Teacher 未来可以使用跨回合的 Experience Store 保存修改尝试中的可复用经验，但该存储仍属于确定性控制面：

- 程序负责记录、索引、版本绑定、去重和持久化，模型不能直接改写共享经验。
- 角色通过 Tool 按当前职责检索经验；角色输出中的问题方向、假设、证据结论、机制和评审理由可以成为经验候选。
- 程序在确认来源和状态后把经验候选写入 Experience Store，不把未经审查的模型自由文本直接当作长期事实。
- Failure Analyst、Hypothesis Researcher、Evidence Reviewer、Mechanism Distiller、Compiler 和 Candidate Reviewer 会读取或贡献不同类型的经验。
- Intervention Worker 只执行当前假设并产生原始 trial artifact；Trial Reviewer 只审阅当前一条 trial。二者都不读取宽泛经验，避免历史案例污染局部事实。
- Teacher Judge 使用固定 rubric 独立评分，不维护随 evolution 变化的经验，避免评分标准漂移。

当前 standalone v2 尚未实现 Experience Store。现有角色只读取 request
显式声明的本轮资源；本节描述的是后续接入时必须保持的边界。

下文“信息来源”使用以下分类：`模型生成`表示语义内容来自模型，`程序维护`表示内容由控制面计算、验证或持久化，`数据集`和`设计规范`分别表示任务数据与预先确定的规则。一个信息可以同时具有多个来源。

## Failure Analyst

**作用：从 Actor 的评估结果中识别有边界、可观察且值得实验的行为问题方向。**

职责：

- 分析错误、波动和高成本轨迹中的共性行为。
- 区分 Actor 行为缺陷、外部服务故障、数据不支持和随机失败。
- 将宽泛问题收敛为可筛选样本、可施加干预的问题方向。
- 说明适用边界和仍未解决的混淆原因。
- 选择能够支持该判断的代表性证据。

模型所需信息：

| 信息 | 信息来源 | 用途 | 访问方式 |
| --- | --- | --- | --- |
| 紧凑结果与执行摘要 | 数据集 + 程序维护 | 了解总体表现和证据边界，不输入路径、token 统计、模型配置或完整 provenance | Prompt |
| 样本列表、错误类型和聚合指标 | 数据集 + 程序维护 | 筛选候选失败簇 | Tool |
| 指定 evaluation case | 数据集 + 模型生成 + 程序维护 | 核查答案、评分和 replicate 目录 | Tool |
| Actor 行为轨迹视图 | 模型生成 + 程序维护 | 默认保留原生 reasoning、模型输出、动作、观察与结果，移除重复 model input 和运行元数据 | Tool |
| Actor 完整轨迹视图 | 模型生成 + 程序维护 | 仅在排查 Prompt、provider 字段或内部事件时按需读取 | Tool |
| 当前 Harness manifest | 程序维护 | 仅在诊断依赖某项能力是否注册时读取，不向该角色开放组件源码 | Tool |
| replicate 级 token 分布 | 程序维护 | 仅在效率是明确分析焦点或轨迹呈现成本异常时检查覆盖率、均值和分位数 | Tool |
| 按 token 排序的案例目录 | 程序维护 | 按 replicate token 均值定位高成本逻辑样本，不把报告总 token 当作单样本成本 | Tool |

Failure Analyst 当前不接收跨回合 `historical_experience`。这类经验会携带
先前方案偏见，应由后续假设研究或候选审查角色在需要时查询，而不应改变
首轮行为诊断。

Failure Analyst 每次运行最多读取 6 个唯一 Actor 轨迹；并行工具调用共享
同一预算，重复查看同一 `example_id/replicate_id` 的不同视图不重复计数。
最终输出仍只引用其中最具代表性的 2-4 条。提示词说明取证策略，资源层
负责执行这一角色边界。

结构化语义输出：

| 字段 | 类型 | 含义 |
| --- | --- | --- |
| `pattern` | `string`，最多 400 字符 | 可直接从轨迹中观察到的单一错误行为序列 |
| `applicability` | `string`，最多 300 字符 | 该模式成立的任务或证据状态 |
| `caveats` | `list[string]`，1-3 项 | 未决混淆因素或该诊断不能支持的推论 |
| `evidence_refs` | `list[string]`，2-4 项 | 唯一且已实际读取的 `example_id/replicate_id` |

模型完成职责的方式：

- 使用聚合工具发现错误簇和稳定性问题。
- 使用案例与轨迹工具验证共性是否真实存在。
- 推理问题是否能通过 Harness 影响，而非依赖不可控环境。
- 用行为描述而不是 Hook、Prompt、query 策略或代码方案表达问题方向。

## Hypothesis Researcher

**作用：把一个冻结问题方向转化为一个具体、可执行、可证伪的软介入假设。**

职责：

- 将问题方向转化为触发条件明确的因果猜想。
- 从实际可恢复阶段和允许动作中选择一个短的临时干预计划。
- 单 phase 无法表达机制时，允许同一分支包含最多四个有因果依赖的 phase 指令。
- 只预测各 phase 的直接 Actor 过程响应，不预言检索成功、答案正确或总体准确率。
- 为单次 activated trial 预注册主观测、成功条件和证伪条件。
- 保留 Failure Analyst 给出的适用边界和不确定性。

模型所需信息：

| 信息 | 信息来源 | 用途 | 访问方式 |
| --- | --- | --- | --- |
| 冻结的问题方向 | 模型生成 | 唯一研究目标，包括适用边界、caveat 和证据引用 | Prompt |
| 紧凑证据与 Actor 摘要 | 程序维护 | 只说明引用规模、replicate 设置、Harness ID、工具与 extension ID | Prompt |
| Analyst 引用的行为轨迹 | 模型生成 + 程序维护 | 核实触发条件、评分和可观察状态；提交前必须读完所有引用轨迹，视图不含 golden answer | Tool |
| Intervention 能力目录 | 程序维护 + 设计规范 | 选择真实可恢复 phase、可见 stage 字段和允许 action；提交前必须读取 | Tool |

结构化语义输出：

当前 `intervention_hypothesis` 输出协议版本为 3。`fork_phase` 是唯一的
prefix 恢复点；`phase_plan` 表达同一个持久 Worker 在该 Student 分支后续
phase 上执行的一到四条有界指令。运行时仍可读取 v2 单 phase 产物，并将其
无损投影成一项 `phase_plan`。

| 字段 | 类型 | 含义 |
| --- | --- | --- |
| `fork_phase` | `enum` | Controller 选择 inclusive prefix 的恢复 phase，必须等于第一条计划 phase |
| `phase_plan` | `list`，1 至 4 项 | 同一 Student 分支上的有序 phase 指令 |
| `phase_plan[].phase` | `enum` | 唯一、可恢复的 Hook phase |
| `phase_plan[].activation_condition` | `string`，最多 350 字符 | 仅依赖该 phase 可见快照的条件 |
| `phase_plan[].instruction` | `string`，最多 600 字符 | 临时上下文或控制意图，不含插件实现 |
| `phase_plan[].expected_effect` | `string`，最多 300 字符 | 该 phase 动作后直接可观察的 Actor 行为 |
| `phase_plan[].max_activations` | `int`，1 至 4 | 该 phase 在一个分支中的独立激活预算 |
| `evaluation.primary_signal` | `string`，最多 200 字符 | 每个 activated trial 测量的主观测 |
| `evaluation.success_condition` | `string`，最多 250 字符 | 主观测在单次 trial 中的预期值 |
| `evaluation.falsifier` | `string`，最多 250 字符 | 直接反驳预测响应的单次 trial 观察 |
| `evaluation.secondary_metrics` | `list[string]`，最多 3 项 | 正确性、工具调用或 token 等非因果辅助指标 |
| `applicability` | `string` | 假设适用与不适用的边界 |

模型完成职责的方式：

- 逐条读取 Analyst 引用的行为轨迹，而不重新搜索整个失败池。
- 使用能力目录确认 phase 的可恢复性、stage 可见字段和 action 兼容性。
- 优先建立单 phase 因果链；只有前一 phase 的观察或修改必须影响后一
  phase 决策时，才建立短的多 phase 因果链。
- 把聚合支持阈值交给 Evidence Reviewer，把任务收益与回归交给 Candidate Reviewer。

### Intervention 能力目录的生成边界

`get_intervention_capabilities` 不是手写的 Hook 教程。以下内容直接从当前
运行时定义生成：

- `HookPhase` 与 `STAGE_KEYS_BY_PHASE` 提供 phase 和阶段字段；
- prefix 恢复映射提供当前真正可重建的 phase；
- `InterventionActionName` 提供 Worker 允许提交的 action 集合；
- Hook API 查询目录提供 stage 值类型、稳定性和字段说明。

action 的副作用、持续范围和兼容 phase 仍需要人工语义注解，因为 Python
反射无法可靠推断行为语义。构造器会校验注解 action 集合与
`InterventionActionName` 完全相等，测试同时检查 phase、action 和关键
可见性约束。由此可防止名称或签名静默漂移，但行为实现发生语义变化时仍需
同步修改注解和测试。

目录同时区分两种可见信息：Worker 可读取恢复点的 `model_input.messages`
和 selector；每个 phase 下的 `stage` 列表则是该时机额外活跃的阶段值。
能力目录同时声明 `multiple_phases_per_trial` 和
`same_worker_transcript_across_activations`。每个 phase 激活只允许一个终止
动作，但一个 trial 可在不同 phase 上激活多次；各 phase 使用独立预算。

## Intervention Worker

**作用：在指定轨迹分支上，由同一个 Teacher transcript 执行一组 phase
局部的受控软介入。**

职责：

- 根据冻结假设理解每个 phase 的局部触发条件。
- 读取恢复点之前对 Actor 可见的结构化上下文。
- 在每个实际到达且预算未耗尽的 Hook 点选择一个终止动作。
- 保留前序 phase 的 Worker 观察和决策，用于同一分支的后序 phase。
- 保持干预与假设一致，不替 Actor 解题或注入案例答案。
- 在完成干预后把控制权交还 Actor，不判断假设是否成立。
- 只依据当前假设和当前分支行动，不主动读取跨回合经验；完整 trial 由程序保存供后续评审。

模型所需信息：

| 信息 | 信息来源 | 用途 | 访问方式 |
| --- | --- | --- | --- |
| 当前假设、试验目标和禁止事项 | 模型生成 + 程序维护 + 设计规范 | 约束本次软介入 | Prompt |
| 当前案例与 replicate 标识 | 数据集 + 程序维护 | 确认试验对象 | Prompt |
| Inclusive prefix 与 phase 计划 | 程序维护 | 确认唯一分支和各 phase 预算 | Runtime |
| 当前 phase 的完整 Worker 快照 | 数据集 + 模型生成 + 程序维护 | 判断局部条件和已有干预状态 | Activation tool |
| 允许的上下文操作 | 程序维护 + 设计规范 | 执行追加、替换、defer 或 no-op | Activation tool |
| 分支继续运行结果 | 模型生成 + 程序维护 | 由程序保存，供独立 Trial Reviewer 审阅 | Runtime |

结构化语义输出：

| 字段 | 类型 | 含义 |
| --- | --- | --- |
| `result_kind` | `enum` | `executed`、`unsuitable_assignment` 或 `unsupported_hypothesis` |
| `activated_phases` | `list[phase]` | Worker 实际收到快照的计划 phase，包括 no-op |
| `modified_phases` | `list[phase]` | Worker 对 Actor 状态或上下文产生具体修改的 phase |
| `unmet_phases` | `list[phase]` | 分支结束前从未到达的计划 phase |

模型完成职责的方式：

- 程序验证 `prefix_id` 与 `fork_phase` 并重建 inclusive prefix。
- 源边界和后续 live phase 都把完整可见快照交给同一个 Worker 对象。
- Worker 每次激活检查局部条件并调用一个终止 action；no-op 仍记录为已到达。
- Student 从修改后的前缀持续运行，完整动作、预算、Teacher transcript 和
  Student 轨迹统一保存在一个 trial artifact。

`executed` 必须至少包含一个 `modified_phases`，并进入 Evidence Reviewer。
`unsuitable_assignment` 表示仅当前 case/prefix 不满足 trigger，由 Controller
重新分配；`unsupported_hypothesis` 表示假设依赖当前 runtime 不具备的状态
或动作，原始 Worker 结果会直接追加回 Researcher session。程序不会把仅到达
phase 或执行 no-op 误记为上下文修改。

当前输出协议为 `intervention_worker_result@3`。Worker 不再在分支末尾生成
自然语言 `summary`；终态仅保留程序可验证的 phase 事实，避免执行者自述影响
后续证据判断，也省去一次额外 Teacher 调用。

## Trial Reviewer

**作用：在一个独立 Teacher 对话中，读取一条完整 Worker 轨迹并形成局部事实
分析。**

每条 executed trial 启动一个新的 Trial Reviewer，不共享其他 trial 的消息
历史。它必须调用 `get_trial_evidence` 读取绑定的完整 source/branch 轨迹，
核查适用性、各 phase 的条件/动作/直接效果、泄漏、显式评分、成本和运行异常。
工具视图保留 Worker activation 的 reasoning 与动作，但不暴露旧版
`worker_summary`。

结构化输出保持最小：

| 字段 | 类型 | 含义 |
| --- | --- | --- |
| `trial_ref` | `string` | 当前唯一绑定且已完整读取的 trial |
| `assessment` | `string`，最多 4000 字符 | 只依据该轨迹形成的自包含事实分析 |

Trial Reviewer 不提出新干预，不跨 trial 判断整个假设，也不决定后续路由。

## Evidence Reviewer

**作用：判断现有 Intervention 证据对假设的支持程度，并指出最有价值的下一项证据。**

职责：

- 聚合多个独立 Trial Reviewer 的局部分析和程序维护的确定性计数。
- 对多 phase 计划分别判断局部证据，不以某一个成功动作替代整条因果链。
- 比较各 trial 的一致性、收益、无效和副作用。
- 判断证据能否跨案例、跨 replicate 支持同一机制。
- 给出继续取证、修订假设、拒绝假设或进入蒸馏的局部建议。
- 当证据不足时，只提出一项最关键的证据义务。
- 检索同类历史证据，并贡献可复用的支持、反驳、副作用和下一证据义务。

模型所需信息：

| 信息 | 信息来源 | 用途 | 访问方式 |
| --- | --- | --- | --- |
| 假设及其证伪条件 | 模型生成 + 程序维护 | 确定评审标准 | Prompt |
| 确定性聚合计数 | 程序维护 | 核查累计调用、状态变化和计划覆盖 | Prompt |
| 独立 `trial_review@1` 列表 | 模型生成 + 程序维护 | 比较各条完整轨迹的局部事实分析 | Prompt |
| 同签名假设的历史证据 | 模型生成 + 程序维护 | 判断证据是否可合并 | Tool |
| 跨回合 Evidence 经验 | 模型生成 + 程序维护 | 复用已确认的适用边界、副作用和证据缺口 | Tool |

结构化语义输出：

| 字段 | 类型 | 含义 |
| --- | --- | --- |
| `decision` | `enum` | `continue`、`revise`、`reject` 或 `ready_to_distill` |
| `assessment` | `string` | 当前证据支持或反驳了什么 |
| `key_risk` | `string \| null` | 最重要的副作用或泛化风险 |
| `next_obligation` | `string \| null` | 改变当前判断所需的下一项关键证据 |

`next_obligation` 只有在 `continue` 时是路由必需字段。`revise` 可以直接
依靠 `assessment` 描述修改方向。模型返回的空字符串、`0`、`"null"`、
`"none"` 或 `"n/a"` 会在协议边界归一为 `null`，不会仅因缺失值写法
触发整次输出重写。

模型完成职责的方式：

- 使用确定性聚合字段约束 Trial Reviewer 的语义结论。
- 比较独立 trial 分析的一致性、冲突和适用边界。
- 不读取完整轨迹，也不调用证据工具；原始轨迹审阅职责只属于 Trial Reviewer。
- 推理当前证据对应继续、修订、拒绝或蒸馏中的哪一种局部转移。

Evidence Reviewer 保留原有输出协议：`revise` 和 `reject` 直接追加回
原 Researcher transcript；`continue` 保留冻结假设并由 Controller 安排
下一项证据义务；`ready_to_distill` 进入 Mechanism Distiller。新增 trial
先产生新的独立 TrialReview，再与已有 TrialReview 一起重新执行全局判断。

## Mechanism Distiller

**作用：把得到支持的 Teacher 软介入提炼为不依赖 Teacher 的 Harness 机制规格。**

职责：

- 审计成功干预实际使用了哪些输入、判断和上下文动作。
- 判断这些输入在无 Teacher Harness 中是否仍然可获得。
- 将案例专用指导抽象为可泛化的触发、决策、动作与回退机制。
- 识别需要规则、Prompt、学生模型调用或状态协作的部分。
- 为触发判断显式选择确定性规则或有界 Hook 小模型，不把开放语义判断留给 Compiler 猜测。
- 当无法蒸馏时，指出缺失能力或新的证据义务。
- 检索既有蒸馏经验，并贡献可复用机制或不可蒸馏边界。

模型所需信息：

| 信息 | 信息来源 | 用途 | 访问方式 |
| --- | --- | --- | --- |
| 已通过评审的假设与证据结论 | 模型生成 + 程序维护 | 明确需保留的有效行为 | Prompt |
| 成功和失败干预的签名摘要 | 模型生成 + 程序维护 | 区分核心机制与偶然措辞 | Prompt |
| 代表性干预轨迹与上下文 diff | 模型生成 + 程序维护 | 审计 Teacher 实际依赖的信息 | Tool |
| Actor Harness 能力与可用模型配置 | 程序维护 + 设计规范 | 判断无 Teacher 的实现边界 | Tool |
| Mechanism draft 构造与校验能力 | 模型生成 + 程序维护 | 分步建立机制规格 | Tool |
| 跨回合蒸馏经验 | 模型生成 + 程序维护 | 复用成功机制、失败迁移和 Teacher 依赖模式 | Tool |

结构化语义输出：

| 字段 | 类型 | 含义 |
| --- | --- | --- |
| `decision` | `enum` | `distilled`、`needs_evidence` 或 `not_distillable` |
| `mechanism_ref` | `string \| null` | 通过工具逐步构造并校验的机制规格引用 |
| `rationale` | `string` | 为什么该机制能够或不能脱离 Teacher |
| `next_obligation` | `string \| null` | 蒸馏前仍需补齐的能力或证据 |

模型完成职责的方式：

- 使用轨迹与 diff 工具分离通用决策信息和案例专用内容。
- 使用能力目录确认触发输入和动作能在 Actor Harness 中获得。
- 通过窄工具调用构造自然语言约束和一段实现无关的连续行为伪代码。
- 为每个得到证据支持的 phase 分别构造 `phase_rules[]`，保留其局部输入、
  evaluator、动作和预算。
- 在伪代码中分开 Hook 控制流与 defer 后交还给 Actor 的任务。
- 明确单次 rollout 的触发预算、依赖能力、禁止行为、trace 信号和已知边界。
- 当触发判断需要语义分类时，明确其 Hook-model 输入、结果使用方式与确定性 fallback。
- 使用规格校验工具检查 Teacher 依赖、信息泄漏、字段完整性和伪代码长度。

## Compiler

**作用：将已校验的 MechanismSpec 实现为一个可装配、可验证的 Harness candidate。**

本节只描述角色分工。当前实现的输入输出协议、内存 workspace、源码驱动 Hook API
capability packet 和五个固定工具的完整定义见 [Compiler](compiler.md)。

职责：

- 理解机制规格和目标 Harness 的真实接口。
- 选择最小充分的插件组合实现机制。
- 通过受控编辑工具新增或修改 mutable 组件。
- 处理 manifest、fixed 边界、语法、导入、装配和 Hook contract 校验反馈。
- 提交候选引用和实现摘要，不决定候选是否被接受。
- 接收调用方提供的历史实现约束和 validation feedback。

模型所需信息：

| 信息 | 信息来源 | 用途 | 访问方式 |
| --- | --- | --- | --- |
| 已校验的 MechanismSpec | 模型生成 + 程序维护 | 确定实现目标和行为边界 | Prompt |
| Parent Harness 标识与 fixed/mutable 约束 | 程序维护 + 设计规范 | 限定修改范围 | Prompt |
| 上一轮编译或验证错误 | 程序维护 | 定向修复候选 | Prompt |
| Candidate 文件目录、manifest 和组件源码 | 程序维护 | 理解现有实现 | Tool |
| Authoring guide | 程序维护 + 设计规范 | 理解 Hook 生命周期与组合语义 | Tool |
| 源码驱动 Hook API catalog | 程序维护 + 源码 | 查询公开签名、状态键、稳定性与形状 | Tool |
| 创建、编辑、删除和查看 diff 的能力 | 程序维护 | 构造原子候选 workspace | Tool |
| 确定性静态、装配和 Hook contract 校验 | 程序维护 | 在提交前发现实现错误 | Tool |
| Candidate submit | 程序维护 | 提交已通过本地检查的候选 | Tool |

结构化语义输出：

| 字段 | 类型 | 含义 |
| --- | --- | --- |
| `decision` | `enum` | `submitted` 或 `needs_revision` |
| `candidate_ref` | `string \| null` | 已由工具提交的候选引用 |
| `implementation_summary` | `string` | 机制如何映射到 Harness 组件 |
| `unresolved_risk` | `string \| null` | 校验后仍需 Candidate Reviewer 关注的风险 |

模型完成职责的方式：

- 使用文件目录、manifest 和源码工具理解 Parent Harness。
- 将 `behavioral_pseudocode` 作为控制流与状态转移的权威来源。
- 将每个 `phase_rules[].decision_evaluator` 作为该 phase 触发判断实现方式的
  权威来源，允许同一机制混合确定性规则和有界 Hook 小模型。
- 使用 authoring guide 理解机制语义，再通过 API catalog 精确查询实际接口。
- 使用文件工具编辑完整文件，并查看相对 Parent 的完整 diff。
- 运行确定性校验，根据结构化错误在同一 run 中持续修订。
- 仅通过 submit 工具提交候选，不在最终输出中序列化完整文件。

## Candidate Reviewer

**作用：结合确定性门禁和配对评估，判断候选是否值得接受、修订或放弃。**

职责：

- 检查候选是否复现 MechanismSpec 预期的过程行为。
- 比较 candidate 与 incumbent 的正确性、稳定性、成本和错误类型。
- 识别局部收益是否伴随严重回归或机制未激活。
- 区分实现缺陷、假设缺陷和证据不足。
- 给出局部 promotion 建议及后续证据义务。
- 检索相似候选历史，并贡献接受、拒绝、回归和修订原因。

模型所需信息：

| 信息 | 信息来源 | 用途 | 访问方式 |
| --- | --- | --- | --- |
| MechanismSpec 与预期行为 | 模型生成 + 程序维护 | 判断候选是否实现目标机制 | Prompt |
| 确定性 validation 与 safety gate 摘要 | 程序维护 | 了解候选的基本合法性 | Prompt |
| Incumbent/candidate 聚合指标 | 模型生成 + 程序维护 | 比较收益、稳定性和成本 | Prompt |
| Harness diff 与实现摘要 | 模型生成 + 程序维护 | 解释行为变化来源 | Tool |
| 配对变化案例列表 | 模型生成 + 程序维护 | 查找改善、回归和不变样本 | Tool |
| 指定 case/replicate 的两版轨迹 | 模型生成 + 程序维护 | 核查机制是否真实生效 | Tool |
| 历史相似候选评审 | 模型生成 + 程序维护 | 识别重复失败和累计风险 | Tool |
| 跨回合 Candidate 经验 | 模型生成 + 程序维护 | 复用已知回归、收益条件和 promotion 结论 | Tool |

结构化语义输出：

当前 `candidate_review` 输出协议版本为 2；相对 v1 新增
`revision_target`，把修订层从 Reviewer 理由文本提升为显式路由字段。
Controller 同时转发 `next_obligation`：证据层作为下一试验义务，机制层作为
能力约束，实现层作为实现约束。只返回职责层而丢失修订义务不构成有效回边。

| 字段 | 类型 | 含义 |
| --- | --- | --- |
| `recommendation` | `enum` | `accept`、`revise` 或 `reject` |
| `observed_effect` | `string` | 候选实际产生的主要行为和任务变化 |
| `reason` | `string` | 支持该局部建议的核心依据 |
| `next_obligation` | `string \| null` | `revise` 时必须给出的具体可验证义务 |
| `revision_target` | `enum \| null` | `revise` 时必须明确返回 `evidence`、`mechanism` 或 `implementation` 层 |

模型完成职责的方式：

- 使用聚合结果判断收益是否超过方差和运行错误影响。
- 使用配对差异工具定位改善与回归样本。
- 使用轨迹工具核查预期机制是否触发并产生目标行为。
- 将建议交给确定性控制面，由控制面决定版本与后续搜索状态。

## Teacher Judge

**作用：在静态规则无法可靠评分时，对单条 Actor 答案给出受约束的离散正确性判断。**

职责：

- 依据问题、参考答案和评分规则判断模型答案是否正确。
- 只评估答案语义，不诊断 Harness，不提出改进方案。
- 对别名、等价表述和必要限定进行一致判断。
- 为评分结果提供简短、可审计的理由。
- 不读取或维护 evolution 经验，评分行为只受固定 rubric 约束。

模型所需信息：

| 信息 | 信息来源 | 用途 | 访问方式 |
| --- | --- | --- | --- |
| 问题、参考答案和 Actor 最终答案 | 数据集 + 模型生成 + 程序维护 | 完成语义正确性比较 | Prompt |
| 任务评分规则与边界示例 | 设计规范 | 保持评分口径一致 | Prompt |

结构化语义输出：

| 字段 | 类型 | 含义 |
| --- | --- | --- |
| `score` | `enum[0, 1]` | 离散错误或正确 |
| `reason` | `string` | 支持评分的简短理由 |

模型完成职责的方式：

- 对照参考答案识别语义等价、别名和无关附加内容。
- 按固定 rubric 推理是否满足正确答案的必要条件。
- 输出离散分数和最小充分解释，不参与 evolution 决策。
