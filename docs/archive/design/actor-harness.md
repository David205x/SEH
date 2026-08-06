# Actor Harness

## 文档职责

本文档说明 Actor Harness 的定位、组成部分、运行边界和扩展方式。

Actor Harness 是最终部署系统的一部分。它负责让小模型 Actor 在固定 Agent Core Loop 下完成 Search Agent 任务，并通过 Registry Extensions 获得逐步增强的外部结构支持。

Adapter Harness 如何观察、干预和编译 Harness Patch，见 `adapter-harness.md`。Patch 如何被审计、评估、接受和版本化，见 `evolution-protocol.md`。

## Actor Harness 定位

Actor Harness 服务于小模型 Actor。

它的核心职责是提供一个可运行、可记录、可扩展、可复现的 Search Agent Runtime，使 Actor 能在基础工具环境中完成任务。

第一阶段的 Actor Harness 不追求一开始就具备复杂工作流。基础 Core Loop 保持相对自由，系统通过统一 Schema 的 Registry Extension 逐步加入模型外部结构。

这一设计保留了一个研究空间：观察外部适配过程是否会自然发现小模型需要哪些额外结构，而不是在实验开始前把复杂流程全部手写进 Core Loop。

## 最终部署形态

经过离线适配后，最终导出的系统应只包含：

```text
Small Actor Model
+ Actor Core Loop
+ Accepted Registry Extensions
```

最终部署系统不得调用外部强模型。外部强模型只参与离线适配阶段，不进入最终实时推理路径。

## 组成部分

Actor Harness 至少包含以下组成部分。

### Actor Model

Actor Model 是被适配的小基础模型。

第一阶段默认固定一个 Actor Model，不进行训练或微调。Harness 的变化应来自模型外部结构，而不是模型参数变化。

### Actor Core Loop

Actor Core Loop 是 Actor Runtime 的基础执行循环。

在本项目中，Actor Core Loop 被视为不会由 Harness 自动适配过程修改的核心代码。它通过预留接口和 Hook 接入扩展，但自身不因为某次 Harness Patch 发生代码变动。

第一阶段基础 loop 可以近似为自由 ReAct-style loop：

```text
observe task
construct prompt
model generates thought/action/final answer
parse output
if action:
    call tool
    append observation
    continue
if final:
    submit answer
```

Core Loop 负责维持基本执行过程，但不应承载大量手写任务逻辑。

它的职责包括：

- 构造 Actor 输入；
- 调用 Actor Model；
- 解析模型输出；
- 调用基础工具；
- 维护运行状态；
- 调用 Registry Extensions；
- 记录 Trace；
- 执行终止条件；
- 向 Evaluator 提交最终结果。

Core Loop 是稳定边界。Harness 自动适配过程不得直接修改 Core Loop，只能通过预留接口和 Hook 加载 Registry Extension。

### Registry Extensions

Registry Extensions 是 Actor Harness 的主要可变层。

外部适配过程发现的稳定干预模式，应尽量被编译为 Registry Extension，而不是写入 Core Loop。

所有 Registry Extension 应共享同一套基础 Schema。文档和实现不应提前为 prompt、tool、parser、validator、controller 等不同 Harness 部分分别设计完全不同的修改入口，以免把人工先验过早写入适配空间。

Registry Extension 的差异主要由其声明、挂载位置、可访问变量和实现内容体现。一个 Extension 可以通过文本、变量、代码及其组合来实现 Harness 的某部分修改。

第一阶段不应过早限制 Extension 的实现形式，但所有 Extension 都必须通过 Registry 暴露给 Actor Core Loop，并接受统一的审计、版本化和回滚机制。

### State Manager

State Manager 管理 Actor Runtime 的运行状态，用于保证 Rollout 可复现、可 fork、可比较。

它至少需要覆盖：

- prompt 组成；
- actor conversation history；
- scratchpad；
- working memory；
- tool state；
- tool call history；
- 检索缓存；
- budget；
- retry 计数；
- parser 状态；
- validator 状态；
- workflow extension 状态；
- registry 已加载组件；
- sampling config；
- random seed；
- hook execution log；
- external intervention log。

State Manager 是 Prefix-Fork 的基础。若工具存在状态，该状态必须由 State Manager 管理并可快照化。

### Tool Layer

Tool Layer 提供 Actor 可以调用的基础工具。

第一阶段 Actor Agent 的初始工具只包含 `search`。

如果后续需要 `open`、`read`、`extract`、`verify` 或其他工具，这些工具不应作为手写默认能力直接加入 Actor Harness，而应由外部适配过程设计并通过 Registry Extension 引入。

工具调用结果应进入 Trace，并在需要时进入 Tool Cache。工具行为应尽量可复现，以便比较不同 Harness Version 或不同 Prefix-Fork 的结果。

每个启用工具应以同一份 `ToolDefinition` 描述名称、工具级说明和输入 schema。实现函数的 docstring 提供工具级说明，函数签名与 `Annotated[..., ToolArg(...)]` 提供字段约束。Prompt renderer、native tool-calling adapter 与 runtime 参数绑定都消费该定义；模板不得手写具体工具名或参数。

一次 rollout 使用一个不可变 `ToolSet`。同一 `ToolSet` 同时注入 Prompt Builder 和 Tool Runtime，保证模型可见的工具集合与实际可调用集合一致。

Dataset runner 顺序读取规范化 `DatasetExample`，并将每题的样本信息和完整 `AgentRun` 写入一行 UTF-8 JSONL。单题外部服务异常记录为 `runner_error`；默认继续后续样本，实验可显式选择 fail-fast。

本地 Trace Viewer 只读加载 `traces/` 下的 JSON 和 JSONL。JSONL 的每一行视为一条轨迹；页面提供文件、轨迹和当前轨迹信息三栏，便于复查 rollout。

### Trace Recorder

Trace Recorder 记录 Actor Rollout 的关键事件。

Trace 至少应支持：

- 还原 Actor 的主要决策过程；
- 支持 Critic 分析失败模式；
- 支持 Prefix-Fork 定位可分叉状态；
- 支持 Evaluation 统计；
- 支持 Audit 发现越权修改、数据泄漏或异常行为。

Trace 是研究与治理的共同基础。它既服务于 Adapter 的离线分析，也服务于系统的可复现性和可审计性。

## Core Loop 与 Extension 的关系

Core Loop 与 Registry Extension 的关系应是“稳定核心代码 + 可版本化扩展层”。

Core Loop 只提供必要执行框架和扩展接口，不把具体任务策略写死。Registry Extension 通过 Hook 接入 Core Loop，在声明范围内读取状态、修改可写状态、调整文本、执行代码逻辑或改变后续运行控制。

因此，Registry Extension 不是 Core Loop 之后的顺序处理阶段，而是 Core Loop 在特定运行点调用的扩展逻辑。

这种设计的目标是：

- 保持 Core Loop 稳定，便于比较不同 Harness；
- 让 Harness 改进集中在可审计、可回滚的扩展层；
- 允许外部适配过程逐步发现小模型需要的结构；
- 避免为了提高实验分数而直接改写 Runtime 主逻辑。

## Runtime Hooks

Core Loop 需要暴露足够 Hook 供 Registry Extension 接入。

第一阶段建议从较小 Hook 集开始：

1. `pre_prompt`：构造 Actor 输入前触发；
2. `post_prompt`：Prompt Builder 产出 `ModelInput` 后、发送模型前触发；
3. `post_model`：Actor 生成后、解析前触发；
4. `post_parse`：解析后触发，可读取 parser 实际输入并细化 invalid 原因；
5. `pre_tool`：工具调用前触发；
6. `post_tool`：工具返回后触发；
7. `pre_final`：提交最终答案前触发；
8. `on_error`：tool、validator、达到最大步数或 runtime 等终止错误发生时触发。普通 invalid parse 由 core 反馈后继续，不属于终止错误。

每个 Hook 都可读取当前 rollout 的完整可见状态，而非仅读取本阶段参数。写入则通过 `HookContext.state` 的事务式 `set` 完成：`core.*` 只读；当前阶段的 `stage.*` 槽位仅对声明了该键写权限的 Hook 开放；持久扩展状态使用显式注册的 `extension.<hook_id>.*` 或 `shared.*` `StateRef`。后者由 `writers` 声明可写 Hook，所有 Hook 均可读取以支持协作。

阶段槽位描述 Core 接下来要消费的主输入/输出，例如 `stage.model_input`、`stage.raw_model_output`、`stage.parsed_output`、`stage.tool_call`、`stage.tool_result` 和 `stage.final_answer`。它们不是 Hook 的可见性边界。Hook 按注册顺序串行执行，后一个 Hook 会立即看到前一个 Hook 已提交的变更。

每次 Hook 调用都生成 `hook_applied` Trace 事件；事件保留 Hook ID、阶段和每个变更的完整 before/after 值。模型原始输出等 Core 事件先被记录，再记录 Hook patch，因此 Trace 可还原“模型生成 A，某 Hook 将其修改为 B，parser 消费 B”的完整因果链。Hook 出错则记录 `hook_error` 并 fail-fast，未提交的事务变更会被丢弃。

第一阶段暂不把 `post_final` 作为必要 Hook。最终答案提交后通常只需要 Trace 和 Evaluation 记录；如果后续存在明确的清理、统计或状态写入需求，再考虑加入。

这些 Hook 不等于固定 Workflow。它们只是为未来 Extension 提供受控插槽。

## 可变层与不可变层

Actor Harness 中需要清晰区分可变层和不可变层。

不可由 Harness 自动适配过程直接修改的部分包括：

- Actor Core Loop；
- State Manager 的核心状态管理逻辑；
- Prefix-Fork Runner 的核心逻辑；
- Evaluator；
- 数据划分；
- Golden Answer；
- Registry Loader 的核心逻辑。

可由 Harness Patch 新增或修改的部分主要是 Registry Extension 层，包括：

- 通过文本实现的扩展；
- 通过变量和状态实现的扩展；
- 通过代码实现的扩展；
- 通过文本、变量、代码组合实现的扩展。

这些扩展共享同一套 Registry Extension Schema。具体扩展最终表现为 prompt、tool、parser、validator、controller、workflow、memory 或其他 Harness 能力，不应由文档预先拆成互不相同的修改通道。

这里的“不允许修改”描述的是 Harness 自动适配过程的权限边界，并不表示开发仓库中的编码 Agent 永远不能实现或修复这些模块。开发任务可以修改核心模块，但不得为了提高实验分数而改变评估语义、绕过审计或破坏可比性。

## 对 Prefix-Fork 的支持

Prefix-Fork，也可称为 Trajectory-Fork，指从某个 Actor Prefix 或 Runtime State Snapshot 出发，重新生成后续轨迹。

它不是 Actor Harness 的最终在线能力，也不是生产事务回滚，而是 Adapter Harness 在离线适配阶段使用的实验工具。

Actor Harness 本身不负责决定何时 fork、fork 多少次、如何比较 fork 结果；这些属于 Adapter Harness 和评估流程的职责。

但 Actor Harness 的设计需要支持 Prefix-Fork 所需的基础能力：

- State Manager 能生成可复现的 Runtime Snapshot；
- Tool State 和 Tool Cache 可被纳入快照或复现协议；
- Trace 能定位可分叉的 Prefix；
- Registry Version、sampling config 和 random seed 可被记录；
- fork 后的 Rollout 能与原始 Rollout 对齐比较。

Prefix-Fork 在 Adapter Harness 中的主要用途包括：

- 比较不同 Soft Guidance；
- 评估同一 Guidance 下 Actor 采样稳定性；
- 观察某类干预是否改变失败路径；
- 验证某个 Harness Extension 是否改善局部行为；
- 分析 Failure Transition；
- 为 Hardening 提供证据。

Prefix-Fork 不作为最终部署系统的默认在线机制。最终部署系统应依赖已接受的 Registry Extensions，而不是依赖外部强模型持续 fork 和试错。

## 与 Adapter Harness 的边界

Adapter Harness 可以在离线适配阶段观察 Actor Rollout，并通过受控接口请求 Soft Guidance 或 Prefix-Fork。

但 Adapter Harness 不得：

- 直接修改 Actor Core Loop；
- 直接修改 State Manager 核心逻辑；
- 绕过 Registry 提交 Extension；
- 在最终部署阶段参与 Actor 推理；
- 向 Actor 提供题目相关的 query、实体、答案线索或证据路径；
- 将 Experience Set 中的题目级信息写入长期 Memory 或 Registry Extension。

Adapter 发现的改进必须经过 Patch、Audit、Controlled Evaluation 和版本化流程，才能进入 Actor Harness。

## 第一阶段简化假设

第一阶段 Actor Harness 采用以下简化假设：

- 固定一个小模型 Actor；
- 初始工具只包含 `search`；
- 固定 Agent Core Loop；
- 使用 Controlled Corpus；
- 工具调用不产生外部副作用；
- 检索结果和工具输出可以缓存；
- Registry Extension 是主要可变层；
- Actor Harness 提供支持 Prefix-Fork 的可复现状态能力，但 Prefix-Fork 本身属于 Adapter Harness 的离线实验工具；
- 最终部署系统不调用外部强模型。

## 未决事项

以下事项仍需要后续确认或在实现中细化：

- Registry Extension 的最终实现类型和目录结构；
- Registry Extension 统一 Schema 的字段设计；
- Hook 输入输出协议；
- Extension priority 与冲突处理规则；
- State Manager 中各类状态的精确 schema；
- Prefix-Fork 的 snapshot 粒度；
- Tool Cache 的键设计和失效策略；
- Actor Trace 的最小必填字段。
