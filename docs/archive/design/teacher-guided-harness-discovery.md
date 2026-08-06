# 教师引导的 Harness 机制发现与架构上限

## 1. 研究问题

本文研究三个相互关联的问题：

1. Critic 与 Compiler 怎样才有机会从失败轨迹中推导出“在 Hook 中调用小模型”“按状态选择上下文”等机制，而不是长期停留在修改提示词措辞的局部搜索中。
2. 当前 `AgentLoop + Hook` 架构能够实现什么，哪些能力在不修改 core 的条件下无法可靠实现。
3. 现有自进化 Harness 工作采用了哪些可借鉴的搜索空间、历史记忆和候选验证设计。

这里的目标不是让提示词直接命令教师“使用模型 Hook”，而是让机制成为可发现、可比较、可证伪的候选。

## 2. 当前代码事实

以下结论以当前实现为准，而不是设计文档中的远期设想。

### 2.1 Core loop

`search_harness/core/loop.py` 实现单一主模型、单工具串行执行的线性循环。每一步依次经历 prompt 构建、模型生成、解析、工具调用或最终回答。工具集合在组装 loop 时确定，运行中不动态增删。

Hook 生命周期包括：

- `pre_prompt`
- `post_prompt`
- `post_model`
- `post_parse`
- `pre_tool`
- `post_tool`
- `pre_final`
- `on_error`

### 2.2 Hook 状态与修改边界

`search_harness/core/hooks.py` 与 `search_harness/core/hook_state.py` 给出的边界是：

- Hook 在任一订阅阶段都可读取完整可见投影，包括 `core.*`、当前 `stage.*`、`shared.*` 和自身 `extension.*`。
- `core.*` 只读；`stage.*` 只有被 Hook 声明且当前激活的键可修改。
- `stage.*` 替换必须保持运行时类型。
- 单个 Hook 的暂存修改原子提交；后续 Hook 失败不会回滚同阶段已经提交的前序 Hook。
- Hook 按 manifest 顺序同步运行，异常默认终止本次 rollout。
- `shared.*` 和 `extension.*` 只在当前 rollout 内持久，不构成跨样本记忆。
- `post_prompt` 对 `ModelInput` 的替换只影响当前生成；下一步 prompt 仍从 `AgentState` 重新构建。

### 2.3 Hook 内模型调用

当前实现已经提供受控语义调用：

- Hook 通过 `context.call_model(HookModelRequest(...))` 请求一次生成。
- Hook 必须声明可用 profile；运行时目前只开放 `student` profile。
- 默认建议每次 Hook 触发最多调用一次。
- 该调用不会进入嵌套 `AgentLoop`，不能继续调用工具。
- 模型输出不会自动改变 Actor；Hook 必须解析结果并显式写入允许的状态。
- 请求、响应、错误均写入 trace。

因此，这项能力本质上是“有界、同步、可审计的语义函数”，不是 sub-agent。

## 3. 为什么当前 Critic 不容易自行发现模型 Hook

上一轮 Critic 能看到失败轨迹、评分差异和当前 Harness 组件，但看不到完整的干预能力空间。Compiler 虽能读取 Hook authoring guide，Critic 提案却通常先把问题定型为“提示词不够清楚”。Compiler 再忠实实现这个行为意图，就很少有理由主动升级机制。

这不是单纯的模型能力不足，而是搜索问题的信息结构导致的：

1. **能力不可见**：模型不知道存在有界语义调用、上下文重写、工具结果变换等不同机制族。
2. **失败尝试不可积累**：一次 review 能看候选与父版本，但“某类静态提示已连续失败”的结论没有成为可检索的一等历史。
3. **提案与机制绑定过早**：Critic 若直接写“增加一条提示”，Compiler 容易把它当作实现规格，而不是待满足的行为假设。

仅靠更强的 prompt 可能偶尔产生模型 Hook，但可重复性较差。更合理的是改善可见信息和职责边界。

## 4. 三项机制设计

### 4.1 可见的能力空间

给 Critic 暴露抽象能力目录，而不是 Hook 教程。建议新增只读工具或短提示段 `get_intervention_capabilities`，返回机制族、适用条件、成本与限制：

| 机制族 | 适合问题 | 主要成本或限制 |
|---|---|---|
| 静态 prompt | 普遍且稳定的规则缺失 | 容易被忽略，不具条件判断能力 |
| 确定性 Hook | 可由结构化状态可靠判断 | 不能解决开放语义判断 |
| 上下文策略 | 信息过载、顺序或相关性问题 | 需要明确选择与压缩规则 |
| 工具边界变换 | 参数、结果格式或证据门禁 | 受固定工具集合限制 |
| 有界语义 Hook | 必须依据当前语义条件决定是否干预 | 增加延迟、token 和第二模型误差 |

能力目录应描述“能做什么”和“何时不该用”，不要给出某个任务的答案或直接要求使用模型 Hook。这样模型仍需完成机制选择。

### 4.2 可见的失败尝试历史

Iteration Journal 应从操作日志提升为可查询的实验记忆。最小记录项建议包括：

- 版本与父版本；
- 行为假设；
- 实际机制族；
- 修改组件；
- rollout/evaluation/review 引用；
- 接受、拒绝或证据不足；
- 改善、回归和成本变化；
- 适用范围，例如模型、数据集、采样配置；
- 从本次尝试得到的、带范围限定的结论。

建议提供 `list_iteration_attempts` 和 `inspect_iteration_attempt` 两层工具。前者分页和筛选机制族、状态、版本；后者读取证据引用与结论。不要把所有历史直接塞进 prompt，也不要把一次失败写成全局真理。

“静态 prompt 在当前模型和该类实体消歧样本上两次无显著收益”是有效记忆；“prompt 无效”不是。

### 4.3 Compiler 的机制选择自主权

Critic 提案应优先表达：

- 观察到的失败模式；
- 支持证据；
- 希望改变的行为；
- 干预所需的输入信息；
- 可证伪的预期；
- 不应改变的行为。

Compiler 再依据能力目录和 authoring guide 选择最小充分机制。选择准则为：

1. 能由确定性规则表达时，不调用模型。
2. 只缺少信息选择时，先采用上下文策略。
3. 只有判断依赖开放语义、且静态机制已有失败证据时，才考虑有界语义 Hook。
4. 语义 Hook 必须定义触发门、最大上下文、输出 schema、解析失败回退和 trace 证据。
5. 每次候选保持一个可归因的事务，但事务可包含实现该机制所需的多个新文件。

这里的“原子”是评估归因单位，不等于只能改一个文件或只能处理一个 proposal。

## 5. AgentLoop + Hook 能达到什么

### 5.1 正向表达能力

在单条 rollout 内，它可以看作“主模型驱动的线性状态机 + 多个同步、受权限约束的状态转换器”。只要策略可分解为每一步的读取、判断和有限修改，Hook 就能表达相当宽的 Harness 行为。

当前架构可实现：

- **条件上下文编排**：按步骤、工具结果、历史消息和扩展状态选择、压缩、重排或注入信息。
- **有限状态控制器**：记录是否刚调用工具、失败次数、证据阶段、预算状态，并据此改变后续输入。
- **工具守卫与归一化**：修正参数、拒绝不满足前置条件的调用、压缩或标注工具结果。
- **输出协议修复**：分析格式错误、补充反馈、触发有限重试。
- **证据门禁**：在回答前检查结构化条件，要求继续检索或允许结束。
- **按需语义路由**：只在确定性触发条件成立时调用小模型做分类、摘要、实体消歧或证据充分性判断。
- **主模型与小模型分工**：小模型输出建议或标签，Hook 决定如何影响主流程，而不是让其直接接管 Actor。
- **可审计的在线干预实验**：每次触发、输入、输出和状态变更可落入同一 trajectory，适合比较因果假设。

从表达角度看，它能逼近任意“有界历史、同步单步决策、固定动作集合”的 rollout 内策略。研究搜索问答 Harness 时，这已经覆盖提示策略、检索策略、结果摘要、格式恢复、语义判断和预算控制等主要实验变量。

### 5.2 不修改 core 无法可靠实现的系统

以下能力不是多写几个 Hook 就能自然获得：

- **动态执行图**：运行时新增工具、替换 parser、生成新 Hook 或改变生命周期拓扑。
- **并发和竞争**：并行工具调用、多模型投票、异步等待、race 或 speculative execution。
- **真正的 sub-agent**：拥有独立 loop、工具、预算和上下文的嵌套 Agent。
- **分支搜索**：prefix fork、多候选轨迹展开、回溯和树搜索。
- **跨 rollout 在线记忆**：当前 Hook 状态随单条轨迹结束而销毁；外部持久存储尚不是统一协议。
- **事务级全局回滚**：单 Hook 提交原子，但整个 phase 和完整 rollout 不是数据库事务。
- **运行中自改 Harness**：插件集合与工具集合在装配时固定；版本迭代发生在离线 Adapter 流程。
- **模型权重学习**：Harness 只能改变模型可见信息与调用过程，不能把领域能力写入参数。
- **严格实时系统**：Hook 和语义调用均同步，额外延迟会串行叠加。

类型约束也构成实际边界：Hook 只能替换当前激活且允许写入的 stage 值，并保持类型。它能重写同类 payload，却不能把一个阶段变成新的控制流节点。

### 5.3 重要的灰区

某些机制可以模拟，但代价很高：

- Hook 可用状态模拟小型 planner，但不能让 planner 自己调用工具验证计划。
- 每一步重复改写 `ModelInput` 可模拟持续上下文策略，但一次 `post_prompt` 修改不会自动延续。
- 外挂文件或服务可提供跨 rollout 记忆，但这会引入并发、版本、数据泄漏和可重复性问题，应成为明确的新协议，而不是 Hook 私自读写。
- 多个顺序 Hook 可模拟处理流水线，但不能提供并行模型调用或失败后的完整回滚。

因此，本架构的上限不是“只能做 prompt engineering”，也不是“任何 Agent 都能由 Hook 表达”。更准确的定位是：**固定线性 loop 上的可进化同步控制层**。

## 6. 与现有工作的对照

### 6.1 Meta-Harness

[Meta-Harness](https://arxiv.org/abs/2603.28052) 让 proposer 通过文件系统访问所有既往候选的源码、分数和执行轨迹，并搜索 Harness 代码。其关键启发不是必须开放整个文件系统，而是“丰富的候选历史访问”本身就是优化能力的一部分。它直接支持本项目把 iteration journal 和历史证据变成 Critic 工具，而非只把最近一次摘要放进 prompt。

### 6.2 A-Evolve

[A-Evolve](https://github.com/A-EVO-Lab/a-evolve) 把可进化状态定义为文件系统 workspace，循环为 Solve、Observe、Evolve、Gate、Reload；退化候选通过 Git 回滚，接受修改打 tag。其 EvolutionEngine 可以访问 trial runner、历史和版本控制，但不被固定为某一种算法。这与本项目“Version Store 管事实与边界，Compiler 自主选择机制”的方向高度一致。

### 6.3 Self-Harness

[Self-Harness](https://arxiv.org/abs/2606.09498) 明确采用 Weakness Mining、Harness Proposal、Proposal Validation 三段循环，强调模型特定的失败模式、最小多样修改和回归测试。它与当前 Critic、Compiler、candidate rollout/review 最接近，也支持继续保持离线候选门禁，而不是立刻改成运行中自修改。

### 6.4 GEPA

[GEPA](https://arxiv.org/abs/2507.19457) 使用轨迹、标量与文本反馈进行反思式 prompt 演化，并维护 Pareto 候选。它说明自然语言反思适合生成候选，但也提醒本项目：只优化单一准确率会忽略 token、工具调用和回归分布，候选比较应至少保留表现与成本两个维度。

### 6.5 ADAS 与 Darwin Godel Machine

[ADAS](https://arxiv.org/abs/2408.08435) 的 Meta Agent Search 在代码空间生成 Agent，并维护不断增长的发现档案；[Darwin Godel Machine](https://arxiv.org/abs/2505.22954) 通过修改 Agent 代码、基准验证和开放式分支档案进行自改进，其[官方实现](https://github.com/jennyzzt/dgm)也明确警告执行模型生成代码的风险。二者比本项目的线性 accepted-version 链具有更大的架构搜索宽度，但也需要更强沙箱、候选选择和资源治理。当前阶段更值得借鉴“保留失败和分支”，不必复制开放式自改代码。

### 6.6 AgentSquare

[AgentSquare](https://arxiv.org/abs/2410.06153) 把搜索空间拆为 Planning、Reasoning、Tool Use、Memory 模块，并进行模块演化与重组。它支持本报告的能力目录思路：没有机制词汇，优化器容易只在最显眼的 prompt 维度附近搜索；但目录应是开放的能力族，不应变成固定配方。

### 6.7 Continual 与 Adaptive Harness

[Continual Harness](https://github.com/sethkarten/continual-harness) 允许 Refiner 在单个持续 episode 中 CRUD prompt、sub-agent、skill 和 memory，代表在线、无重置的 Harness 更新。它能处理长期环境中的即时适应，却牺牲了部分离线候选的清晰归因。

[Adaptive Auto-Harness](https://arxiv.org/abs/2606.01770) 进一步使用有状态多 Agent evolver、Harness tree 和 solve-time routing，应对开放任务流、任务异质性和分布漂移。这揭示当前单一线性 accepted Harness 的远期上限：当不同样本需要冲突策略时，继续把规则压进一个 Harness 会变脆，届时应考虑路由多个专门 Harness，而不是无限加 Hook。

### 6.8 Harness 与权重的边界

[SIA](https://arxiv.org/abs/2605.27276) 同时更新 Harness 与模型权重，并报告二者结合优于只改 scaffold。对本项目而言，这不是近期实现建议，而是边界提醒：上下文、工具和控制流可以弥补行为缺陷，却未必能注入模型原本缺失的领域直觉。失败不能永远归咎于 Harness。

## 7. 教师模型对照实验

已新增可复现实验入口：

```powershell
python -m experiments.teacher_mechanism_probe \
  --output-file adapter_logs\teacher_mechanism_probe_20260716.json
```

实验矩阵包括：

1. 只给候选证据和现有 Hook，重复两次观察自然发现。
2. 单独暴露抽象能力空间。
3. 单独暴露多轮失败历史。
4. 给 Compiler 行为目标和机制选择自主权。
5. 同时给能力、历史和自主权，再做成本与回退的对抗追问。
6. 分别做架构上限分析和 red-team 修正。
7. 让教师生成非处方式的能力披露与升级准则。

脚本只读取 `TEACHER_*` 配置，并在每次请求后保存完整消息、正式输出、原生 `reasoning_content`、usage 或错误。用户明确授权数据发送后，完整实验已使用 `deepseek-v4-flash`、温度 `0.2`、`max_tokens=4096` 和单请求超时 180 秒运行成功。完整 artifact 为 `adapter_logs/teacher_mechanism_probe_20260716_full.json`，包含 10 个记录、7,846 prompt tokens、26,105 completion tokens，总计 33,951 tokens，无请求错误。

`e1_capability_space` 的正式 `content` 为空，因为 4,096 completion tokens 全部消耗在原生 reasoning；分析时采用 artifact 中保留的 `metadata.reasoning_content`。这也说明评估教师轨迹时不能只读取正式 content。

## 8. 实验结果

### 8.1 分组观察

| 实验 | 观察到的机制选择 | 结论 |
|---|---|---|
| `e0_evidence_only_a/b` | 两次都从静态提示升级为条件 Hook，但没有提出额外模型调用 | 教师可仅凭 loop/Hook 能力发现动态上下文干预；模型 Hook 不会自然稳定出现 |
| `e1_capability_space` | 明确把实体消歧判定为语义问题，选择有界模型调用，并把空结果处理留给确定性规则 | 能力原语可见后，教师开始比较机制，而非只调整文本 |
| `e2_failure_history` | 识别出静态措辞无法完成条件语义判断，但因未告知模型调用能力，只提出状态条件 prompt 重写 | 失败历史帮助形成行为需求，不能凭空产生可实现 primitive |
| `e3_compiler_autonomy` | 形成确定性触发门、有界语义判断、JSON schema、失败回退、状态传递和 trace 的完整设计 | 行为目标加机制自主权足以让 Compiler 设计可落地模型 Hook |
| `e4_combined_discovery` | 没有立即使用模型 Hook，而是选择更便宜的条件确定性 Hook，并设置失败后升级标准 | 三项条件不会机械诱导复杂方案，反而改善实验归因与最小机制选择 |
| `e4_adversarial_followup` | 坚持当前无需模型调用，同时把未来语义 Hook 缩为有门控的 `YES/NO` 分类器 | 对抗追问成功收紧语义调用范围、上下文和回退 |
| `e5_loop_upper_bound` | 正确识别多数同步策略能力，但高估了安全阻断、树搜索和上下文恢复 | 教师会把“可模拟”误写成“可可靠实现”，需要 red-team |
| `e5_upper_bound_red_team` | 纠正为无真回溯、无立即 abort、无动态工具、无并发、语义调用无工具 | 约束复述显著降低了架构能力夸大 |
| `e6_non_prescriptive_guidance` | 生成确定性优先、重复失败后升级语义 Hook 的三阶段准则 | 可以用能力披露和升级规则引导发现，无需写死“使用模型 Hook” |

### 8.2 对预注册假设的判断

- **H1 基本成立**：只给当前证据时，教师两次都提出条件 Hook，但没有主动引入第二模型。
- **H2 成立**：失败历史组准确识别条件语义需求，却只使用已知的状态与 prompt 变换，没有臆造未公开接口。
- **H3 成立**：能力空间组明确区分空结果等确定性信号和实体消歧等语义信号，选择按需调用。
- **H4 需要修正**：组合条件没有立即形成模型辅助 Hook，而是先测试确定性条件显著性。更准确的假设应是：三项条件提高机制选择质量，但不保证选择最强机制。
- **H5 成立但表现形式不同**：当前候选本来没有模型调用；对抗追问仍成功把未来升级方案压缩为窄输入、二值输出、有确定性回退的分类器。

### 8.3 教师回答中的实现误差

实验也证明 capability catalog 必须来自机器可读的权威接口，不能只靠教师自由回忆：

- 教师多次使用不存在的 `on_tool_result`、`post_tool_execution`、`pre-model` 等阶段名称；实际阶段是 `post_tool`、`post_prompt` 等。
- 它有时声称 post-tool Hook 可直接替换下一步 `ModelInput`；实际应先写入 rollout 状态，再由下一次 `post_prompt` 修改当前生成的输入。
- 它把语义调用限额描述成“每阶段一次”或“每 rollout 一次”；当前约束是每个 Hook invocation 的调用上限，并由 Hook 声明 profile 和运行时 backend 共同约束。
- 它提出按 `len(results)` 判断空结果，但当前检索工具结果是模型可见文本，不保证存在结构化 `results` 列表。Compiler 必须依据真实 payload 实现或先增加稳定解析层。
- 初次上限分析把顺序重采样当作树搜索、把工具替换当作立即阻断；red-team 后才纠正。

因此，教师适合提出机制假设，不应直接成为接口事实来源。Compiler 在产出 patch 前仍必须调用 versioned authoring guide，并通过导入、类型和行为测试校验。

### 8.4 主要结论

教师模型确实能够推导出“Hook 中调用小模型并控制其上下文”的模式，但需要两个前提：语义调用作为抽象能力可见，Compiler 被允许根据行为目标自主选机制。失败历史的作用不是直接生成实现，而是证明静态机制族已进入局部最优。

更重要的是，成熟的发现结果并不总是模型 Hook。组合实验选择先做确定性候选，以隔离“条件触发是否有效”和“额外语义能力是否必要”。这比直接加入第二模型更符合当前研究框架的低耦合、可审计和因果归因目标。

这些结果仍只描述一个教师模型在特定提示和单次采样下的倾向，不能证明通用因果关系。下一轮可对关键组重复 3 至 5 次，并替换不同教师模型，比较机制选择稳定性。

## 9. 建议推进顺序

### 第一阶段：不改 core

1. 给 Critic 增加抽象 capability catalog。
2. 把 iteration journal 暴露为分页的尝试历史工具。
3. 将 Critic proposal 改为行为假设与必要证据，避免过早绑定实现。
4. 在 Compiler 中落实最小充分机制准则和语义 Hook 升级门槛。
5. 对同一 proposal 比较静态、确定性和模型辅助候选，记录准确率、回归、工具调用、token 和延迟。

### 第二阶段：增强搜索而非运行时

1. 允许同一父版本产生多个候选分支。
2. 保留 rejected 与 inconclusive 尝试及其证据，不只保留 accepted commit。
3. 引入简单 Pareto 选择，避免准确率小幅提升掩盖成本显著上升。
4. 增加 holdout 或重复 rollout，降低 100 条单次采样的偶然性。

### 第三阶段：由证据决定是否扩 core

只有当失败明确来自当前不可表达边界时，再考虑：

- 跨 rollout 的版本化 memory protocol；
- 独立 sub-agent loop；
- 分支 rollout/prefix fork；
- 多 Harness 路由；
- 并行工具或模型调用。

不建议为了“更像完整 Agent 框架”提前加入这些能力。当前研究最有价值的问题，是在受限但可审计的搜索空间中，教师能否发现有效的 Harness 个性化机制。

## 10. 结论

当前架构已经足以研究一大类有意义的 Harness 进化：条件上下文、有限状态策略、工具守卫、结果变换、格式恢复，以及带确定性门控的有界语义 Hook。它的主要短板暂时不在 core loop，而在 Adapter 看不到完整机制空间、失败经验没有形成可检索知识、Critic 与 Compiler 对“行为意图”和“实现机制”的职责仍容易粘连。

因此，下一步最小而关键的改进不是扩展 loop，而是改善进化系统的认知接口：让能力可见、让失败可记忆、让 Compiler 能选择并解释机制。本次教师实验已经表明，这些条件能让模型从反复改 prompt 上升到机制比较，并在语义 Hook 与确定性 Hook 之间做成本敏感选择。下一步应把这三项条件接入真实 Critic/Compiler，再用候选 rollout 检验这种设计判断能否转化为任务收益。
