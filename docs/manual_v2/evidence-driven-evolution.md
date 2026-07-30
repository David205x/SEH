# 证据驱动的 Evolution 研究状态

本模块把 Harness evolution 视为一个受预算约束的搜索过程。候选版本不是唯一有价值的结果；能力边界、被反驳的假设和下一项证据义务也必须能够跨 iteration 留存。

本页的 `EvolutionResearchStore` 和 `IterationProduct` 描述现有旧版 Runner 的
研究记录实现。正式 v2 [Evolution Controller](evolution-controller.md) 当前用
WorkItem 事件和角色 artifact 保存同一轮证据，没有同时写入
`EvolutionResearchStore`；跨 run Experience Store 仍未实现。

## 四类研究记录

`EvolutionResearchStore` 在一次 experiment run 的 `research/` 目录中追加保存：

| 记录 | 作用 | 关键约束 |
| --- | --- | --- |
| `ActorCapabilityProfile` | 记录特定 Actor 模型与 Harness 组合已经展示的能力边界 | 必须绑定 Harness digest 和证据引用 |
| `EvaluationContract` | 在 trial 前冻结核心指标、机制指标、预期效果和证伪条件 | trial 完成后不得按结果改写评分口径 |
| `EvidenceObligation` | 表示下一步最值得回答的一个可证伪问题 | 以追加事件从 `open` 转为终态，不覆盖历史 |
| `IterationProduct` | 记录一轮搜索实际获得的研究产物 | 角色不能借此终止整个 run |

研究状态使用 UTF-8 JSONL，保存程序生成的时间与 schema 版本。模型只贡献语义内容；稳定 ID、时间、文件位置和状态变更由程序维护。

## Iteration 产物

当前支持以下产物类型：

- `evidence_recorded`
- `hypothesis_rejected`
- `more_evidence_required`
- `ready_for_distillation`
- `candidate_compiled`
- `candidate_accepted`
- `candidate_rejected`

当 Critic 没有给出问题方向、Coordinator 在局部预算内仍无法确认假设，或 Compiler 澄清预算耗尽时，Runner 会记录对应产物并进入下一 iteration。只有全局 iteration 预算耗尽、确定性不可恢复错误或外部停止才结束 experiment run。

`candidate_compiled` 只是中间研究记录。候选仍需通过冻结的 `EvaluationContract` 和 Candidate Reviewer，才能由 Version Store 接受为新 checkpoint。

## MechanismSpec 边界

`MechanismSpec` 使用两类互补信息：

- 自然语言字段描述机制目标、证据、能力和约束；
- `behavioral_pseudocode` 是行为顺序、分支和状态变化的唯一连续描述。

字段职责如下：

| 字段 | 职责 |
| --- | --- |
| `goal` | 说明为什么需要这个机制 |
| `phase_rules` | 保存一至四条有序、唯一的 phase 局部机制 |
| `phase_rules[].phase` | 指定当前规则进入的 Hook phase |
| `phase_rules[].trigger_condition` | 用一句话概括当前 phase 何时触发 |
| `phase_rules[].decision_inputs` | 限定当前规则允许读取的信息 |
| `phase_rules[].decision_evaluator` | 指定当前规则使用确定性逻辑还是有界 Hook 小模型 |
| `phase_rules[].action` | 用一句话概括当前 phase 的动作 |
| `phase_rules[].activation_budget` | 限制当前 phase 在单次 rollout 的触发次数 |
| `behavioral_pseudocode` | 描述完整控制流、状态变化、Actor 交接和 fallback |
| `state_scope` | 说明伪代码状态变量的生命周期 |
| `fallback` | 解释不确定或异常分支的安全行为 |
| `expected_behavior` | 说明外部应观察到的过程变化 |
| `evidence_refs` | 引用支撑该机制的 trial 或评审证据 |
| `required_capabilities` | 列出无 Teacher Harness 必须具备的能力 |
| `prohibited_behaviors` | 列出机制不得实施的行为 |
| `observability` | 列出验证机制真实执行所需的 trace 信号 |
| `known_limits` | 列出机制不能解决的环境或能力边界 |

`behavioral_pseudocode` 不采用需要机器解析的固定语法，也不要求特定标题、控制词或
行数。它可以使用任意简洁、实现无关的写法，但必须连续表达：

- 机制在什么 Hook phase 和条件下执行；
- 分支读取哪些输入和状态；
- Hook 按什么顺序修改哪些抽象效果；
- 哪些工作通过 feedback 交还给 Actor；
- 重复触发、不确定情况和 fallback 如何结束。

伪代码只描述实际读取值和实际变化。保持当前 decision 不变属于 no-op，不应描述为
重新构造同一个 decision；one-shot 行为通常使用一个 rollout-local boolean 即可。
伪代码不得包含 Python、框架 API、文件路径、案例答案、案例实体或案例专用 query。
语义谓词只有在 evaluator 和可用输入被明确描述时才能出现。
每条 `phase_rules[].decision_evaluator=deterministic` 都要求该 phase 的全部
触发条件可由明确、可复现的规则计算，不得由 Compiler 临时发明关键词或启发式
近似；`hook_model` 表示该 phase 的触发判断必须通过允许的 Hook 小模型完成，
并由机制同时规定输入、结果使用方式和确定性 fallback。同一机制可以按 phase
混合两种 evaluator。旧单 phase 机制可被运行时投影成一项 `phase_rules`，但
缺失 evaluator 的产物仍不会获得默认值。

当前 MVP 不为伪代码建立 parser。程序保证字段存在、`decision_evaluator` 属于
受支持枚举、伪代码长度不超过 3000 字符并能构造完整 `MechanismSpec`；自然语言
字段、evaluator 与伪代码的语义一致性由 Distiller prompt 自检，后续由 Compiler
和 Candidate Reviewer 继续核查。

## Distiller 到 Compiler

Distiller 和 Compiler 可以组成一次候选提交，但不能合并职责：

1. Distiller 依据已评审证据生成带行为伪代码的实现无关 `MechanismSpec`。
2. Compiler 将规格映射为最小 mutable 插件变更。
3. Version Store 创建 pending iteration 并执行 manifest、fixed 边界、语法、导入与 Hook contract 校验。
4. 正式 Controller 在 pending candidate 上执行完整冻结 Experience Set 评估；
   standalone Compiler 本身不执行数据集 rollout。
5. 候选保持 pending，直到配对评估、Candidate Reviewer 建议和确定性 promotion
   gate 共同允许接受。

Compiler 校验通过只表示代码可装配、可运行，不表示机制在任务上有效。
