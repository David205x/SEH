# Search Harness

本项目研究并运行由 Teacher Agent 引导 Student Agent 自进化的闭环。

## Language

### Naming Semantics

**Definition**:
对某类对象身份、结构和可用行为的可复用机器可读定义。
_Avoid_: Specification、Configuration、Runtime Instance

**Specification**:
实现无关的规范性要求，是验证实现是否符合预期的依据；可在名称中缩写为 Spec。
_Avoid_: Definition、Configuration、Implementation Plan

**Configuration**:
为某次部署、装配或运行选择的参数值。
_Avoid_: Definition、Specification、State

**Manifest**:
Template 内可序列化的顶层索引，引用 Definition、Declaration、entrypoint 和 Configuration。
_Avoid_: Registry、Template、Configuration

**Contract**:
两个边界之间的输入、输出、错误及不变量约定；Teacher Role 输入输出协议属于 Role Contract。
_Avoid_: Specification、Prompt、Implementation

**Resource**:
在明确作用域内提供给 Agent、Role 或 Component 的数据或能力。
_Avoid_: Artifact、Store、Run Context

**Store**:
负责持久化、按身份检索和恢复对象的边界。
_Avoid_: Resource、Artifact、Journal

**Artifact**:
某个 Work Item 产生并持久化的不可变内容；体量较大或不适合嵌入 Event 时，通过 Artifact Reference 引用。
_Avoid_: Result、Record、State

**Record**:
一个有身份对象或事实的结构化持久化表示，通常较小且可索引。
_Avoid_: Artifact、State、Summary

**State**:
某个运行中对象当前可变化或由 Event 投影得到的值。
_Avoid_: Record、Artifact、Result

**Result**:
一次有界操作直接返回的完整结果，不保证已经持久化。
_Avoid_: Artifact、Report、State

**Report**:
对多个 Result、Metric 或 Finding 的结构化聚合；持久化后可以作为 Artifact。
_Avoid_: Result、Summary、Review

**Summary**:
从完整内容派生的有损概览，不是新的事实源。
_Avoid_: Report、Record、State

### Agent System

**Model**:
Agent 中负责根据输入生成输出的可调用模型抽象或实例；项目公共接口统一使用 Model，不把该抽象命名为 ModelClient。Model 不包含上下文维护、工具执行、生命周期控制或其他外部状态管理。
_Avoid_: Agent、Harness、ModelClient

**Model Name**:
由 Model Provider 识别并用于选择具体 Model 的字符串名称或标识，例如 `glm-5.2`。
_Avoid_: Model Profile、Model Role

**Model Provider**:
根据 Model Name 提供或解析 Model 实现的后端适配边界。
_Avoid_: Model、Model Client、API Endpoint

**Model Settings**:
控制一次 Model 生成行为的参数集合，例如 temperature、top_p、max_tokens、工具选择和结构化输出设置。
_Avoid_: Model Configuration、Model Profile

**Model Profile**:
描述 Model 能力与兼容性的元数据，例如上下文限制、工具调用、结构化输出和输入输出模态支持；不得用作 Student 或 Teacher 配置组的别名。
_Avoid_: Model Configuration、Model Settings、Model Alias

**Model Configuration**:
部署和实例化 Model 所需配置的统称，可组合 Model Provider、Model Name、Model Settings、Endpoint 与凭据引用；Student Model Configuration 和 Teacher Model Configuration 分别表示两类用途的配置。
_Avoid_: Model Profile、Model Binding、Model Provenance

**Model Client**:
用于访问 Model Provider 的底层 SDK、HTTP 或其他传输客户端，是基础设施实现而非可调用 Model 抽象或领域角色；Client 一词只用于这一传输边界。
_Avoid_: Model、Model Provider、Teacher Agent

**Model Provenance**:
一次执行实际采用的 Model Name、Model Provider、Model Settings 及相关非敏感配置来源的可追溯记录。
_Avoid_: Model Configuration、Credential、Model Profile

**Model Input**:
Prompt Component 从当前 Model Context 构造并提交给一次 Model 调用的 provider-ready 结构化请求。
_Avoid_: Model Context、Prompt Component、Run Context

**Model Response**:
一次 Model 调用返回的完整结构化结果，直接承载生成内容、usage 和 Provider metadata；不得依赖“最近一次调用”之类的旁路可变状态取得元数据。
_Avoid_: Raw Model Output、Parsed Model Output、Run Result

**Raw Model Output**:
Model Response 中尚未由 Harness 解释的生成内容。
_Avoid_: Model Response、Parsed Model Output、Final Output

**Parsed Model Output**:
Harness 根据约定协议对 Raw Model Output 解析得到的结构化分支，例如 Tool Call、Final Output Candidate 或解析错误。
_Avoid_: Model Response、Raw Model Output、Final Output Decision

**Output Contract**:
Agent Run 对 Parsed Model Output 与 Final Output 的稳定结构和约束；它是调用方、Evaluation 与下游消费者依赖的接口，不等同于实现该接口的 Output Component。
_Avoid_: Output Component、Role Output、Final Output

**Tool Call**:
Model 请求调用某个 Tool 的结构化指令。
_Avoid_: Tool Component、Tool Result、Tool Interaction

**Tool**:
Agent 可通过 Tool Call 请求的外部能力。
_Avoid_: Tool Component、Tool Definition、Tool Execution

**Tool Definition**:
Tool 暴露给 Model 与 Harness 的名称、描述和输入 Schema。
_Avoid_: Tool、Tool Component、Component Declaration

**Tool Execution**:
根据 Tool Call 执行 Tool 并产生 Tool Result 的过程。
_Avoid_: Tool Call、Tool Result、Tool Runtime

**Tool Executor**:
根据 Tool Definition 定位并执行 Tool Call、规范化错误并返回 Tool Result 的角色无关运行边界。
_Avoid_: Tool、Tool Execution、Agent Runner

**Tool Result**:
Tool 执行后的完整结构化结果，可包含 Tool Output、错误和执行元数据。
_Avoid_: Tool Call、Tool Output、Run Result

**Tool Output**:
Tool Result 中提供给 Model Context 的内容。
_Avoid_: Tool Result、Final Output、Raw Model Output

**Tool Interaction**:
一组相互关联的 Tool Call 与 Tool Result。
_Avoid_: Tool Execution、Trajectory、Tool Component

**Final Output Candidate**:
Parsed Model Output 提出的、尚待 Harness 接受的终态输出。
_Avoid_: Final Output、Candidate Template、Raw Model Output

**Final Output Decision**:
Harness 对 Final Output Candidate 作出的接受、替换或延迟决定。
_Avoid_: Final Output、Promotion Gate、Candidate Review

**Final Output**:
Agent Run 最终向调用方返回的通用终态值；搜索问答任务中的 Answer 是它的领域投影。
_Avoid_: Final Output Candidate、Run Result、Answer

**Answer**:
搜索问答任务对 Final Output 的领域字段，不属于通用 Agent 或 Harness core 接口。
_Avoid_: Final Output、Raw Model Output、Teacher Judgment

**Harness**:
Agent 中除 Model 调用之外的全部运行机制，负责管理模型可见上下文、外部状态、工具交互与执行生命周期；经 Harness Assembly 得到的 Harness 是可复用、无单次运行状态的组合对象。Harness 是通用 Agent 系统概念，不特指本项目中的某一类 Agent。
_Avoid_: Prompt、Template、Agent Runtime

**Harness Template**:
用于实例化一套 Harness 的压缩、可配置表示；Template 描述 Harness，但不是运行中的 Harness 本身。
_Avoid_: Harness、Agent Template

**Template Version**:
Harness Template 的不可变版本快照，是进化流程持久化、比较和接受的版本单位；完整形式为 Harness Template Version，仅在需要跨语境消歧时展开。
_Avoid_: Harness Instance、Harness Snapshot

**Harness Instance**:
Harness 在一次 Agent Run 开始时创建的 run-scoped 实例，持有该次执行的 Harness State 与 Extension State。
_Avoid_: Harness Template、Harness Version

**Candidate Template**:
基于一个 Accepted Template Version 创建、尚未被接受或拒绝的待验证 Harness Template；完整形式为 Candidate Harness Template。
_Avoid_: Candidate Harness、Harness Instance

**Agent**:
由一套 Harness 与一个 Model 组合而成的可运行系统，即 `Agent = Harness + Model`。
_Avoid_: Model、Harness

### Participants

**Agent Role**:
Agent 在一次有界工作中承担的职责配置；它描述职责，不是 Agent、Model 或 Harness。复合词 Role Session 中的 Role 指 Agent Role。
_Avoid_: Message Role、Agent、Teacher Role

**Message Role**:
消息协议中用于区分 system、user、assistant 或 tool 消息的标签。
_Avoid_: Agent Role、Teacher Role、Role Session

**Student Agent**:
执行目标领域任务并接受进化的 Agent，由 Student Harness 与 Student Model 组成。
_Avoid_: Actor、Student

**Student Harness**:
Student Agent 所使用的 Harness，是当前进化过程直接改变的行为机制。
_Avoid_: Actor Harness、Student

**Student Model**:
Student Agent 所使用的 Model；Harness 进化不等同于修改该模型本身。
_Avoid_: Actor Model、Student

**Teacher Agent**:
承担研究、干预、蒸馏、编译或评审职责的 Agent，由 Teacher Harness 与 Teacher Model 组成。
_Avoid_: Adapter、Teacher

**Teacher Harness**:
Teacher Agent 所使用的 Harness，为特定 Teacher Role 组织上下文、工具、状态和执行生命周期。
_Avoid_: Adapter Harness、Teacher

**Teacher Model**:
Teacher Agent 所使用的 Model。
_Avoid_: Adapter Model、Teacher

**Teacher Role**:
Teacher Agent 在进化研究域中承担的 Agent Role 特化。
_Avoid_: Teacher Agent、Sub-agent、Message Role

### Execution Lifecycle

**Agent Run**:
任意 Agent 从接收一次运行输入到产生终态的一次执行，是通用运行概念。
_Avoid_: Evolution Run、Run Result、Student Rollout

**Run Result**:
Agent Run 完成后返回的结果对象，可包含最终输出、终态、错误和对运行记录的引用；它不是执行过程本身。
_Avoid_: Agent Run、Evolution Run、Trajectory

**Agent Runner**:
接收 Agent 与运行输入、执行 Agent Run 并返回 Run Result 的角色无关执行边界；它是统一职责类别，不要求不同执行方式共享同一调用协议，只有输入与结果契约相同时才构成可替换实现。
_Avoid_: Agent、Agent Loop、Runtime

**Loop Runner**:
通过 Agent Loop 驱动 Harness Lifecycle 的 Agent Runner 实现；它接收 Agent，不同时充当 Agent 或 Harness 容器。
_Avoid_: Agent Loop、Agent、Role Runner

**Agent Loop**:
Agent Run 内反复驱动 Model 调用、Tool 调用、状态更新和终止判断的角色无关控制机制；它执行 Harness Lifecycle 所定义的阶段与边界，同一实现可以服务 Student Agent 或 Teacher Agent。
_Avoid_: Student Runner、Evolution Controller、Harness Lifecycle

**Runtime**:
承载 Agent Runner、Model Provider、工具执行和持久化等能力的运行环境；不作为某个 Runner 或 Agent Loop 类的同义词。
_Avoid_: Agent Runner、Agent Loop、Harness

**Role Runner**:
根据 Role Definition 验证 Role Input、准备 Role Resource 与 Role Continuation，并委托 Agent Runner 执行 Agent 后验证 Role Output 的应用边界；该名称和职责不依赖特定 Teacher。
_Avoid_: Agent Runner、Teacher Role Runner、Role Session

**Session**:
跨多个 Agent Run 保存并恢复对话历史的通用上下文边界。
_Avoid_: Harness State、Run Result、Collector

**Role Session**:
绑定到某个 Role 工作上下文、允许 Role Continuation 的 Session；该概念和实现不依赖特定 Teacher，尽管当前主要用于 Teacher Role。
_Avoid_: Teacher Role Session、Agent Run、Role Continuation

**Tool Call Collector**:
收集一次 Agent Run 内 Tool Call 的通用短生命周期对象，不保存跨 Run 对话历史。
_Avoid_: Tool Session、Session、Tool Component

**Output Collector**:
收集一次 Agent Run 所提交结构化终态输出的通用短生命周期对象。
_Avoid_: Output Session、Session、Run Result

**Run Context**:
一次 Agent Run 可访问的本地依赖、资源和元数据；默认不会自动进入 Model Input。
_Avoid_: Model Context、Harness State、Component Factory Context

**Model Context**:
截至某次调用前累积的模型可见语义材料，例如消息、指令、工具描述，以及 Harness State 与 Run Context 的受控投影；它由 Prompt Component 封装成该次调用的 Model Input。
_Avoid_: Run Context、Harness State、Model Settings

**Component Factory Context**:
装配 Harness Component 时传给 factory 的稳定配置与依赖视图；Student 与 Teacher 的组件装配共享该概念和名称。
_Avoid_: Plugin Context、Teacher Plugin Context、Model Context

**Evolution Run**:
一次有独立身份和冻结边界的进化控制执行，具有固定的 Evolution Set、预算和初始 Template Version；它可以处于运行中、暂停或完成状态。
_Avoid_: Run、Experiment Run

**Evolution History**:
一个 Evolution Run 截至当前实际经历的有序过程，可覆盖不完整 Generation、完整 Generation 或多个 Generation，并随未终止的 Run 继续增长。
_Avoid_: Evolution Trajectory、Run、Version Lineage

**Generation**:
Evolution Run 中以一个已接受版本为 incumbent 开始，到接受下一版本或本次研究终止为止的演化周期。
_Avoid_: Iteration、Candidate Attempt

**Work Item**:
Controller 议程中一个可持久化、可独立重试的有界工作。
_Avoid_: Task、Step、Iteration

**Student Rollout**:
Student Agent 针对一个 Example 的一次完整 Agent Run，是 Agent Run 在 Evaluation 和 Evolution 语境中的领域特化。
_Avoid_: Actor Run、Evolution Run、Run Result

**Replicate**:
同一 Example 的一次独立重复 Student Rollout，由独立身份和采样条件区分。
_Avoid_: Retry、Run

**Trajectory**:
Student Rollout 内按执行顺序排列的模型交互、工具交互和 Harness 生命周期事件序列，用于行为分析、Trajectory Prefix 重建和 Intervention Trial。
_Avoid_: Rollout、Trace

**Trajectory Event**:
Trajectory 中一个有序的模型、工具或 Harness 生命周期事实，是当前运行记录器的最小记录单位。
_Avoid_: Trace Event、Control Event、Span

**Trace**:
一次端到端操作的标准可观测性记录，由 Span 组成；一个 Trace 可以覆盖一个或多个 Agent Run，不等同于 Student Rollout 的行为 Trajectory。
_Avoid_: Trajectory、Event List、Log File

**Span**:
Trace 中具有起止时间、父子关系和操作数据的可观测性单元。
_Avoid_: Trajectory Event、Lifecycle Step、Control Effect

**Intervention Trial**:
从一个既有 Trajectory Prefix 建立受控分支，并将分支行为与源执行进行比较的实验。
_Avoid_: Rollout、Candidate Evaluation

**Candidate Attempt**:
一次 Candidate Template 的事务性暂存、验证及接受或拒绝过程。
_Avoid_: Iteration、Generation

**Candidate Attempt Status**:
Candidate Attempt 当前所处的有限状态，例如 pending、accepted 或 rejected。
_Avoid_: Iteration Status、Candidate Attempt State、Run Status

**Candidate Attempt Event**:
Candidate Attempt 内一个不可变、追加式的模板事务事实，由 Template Version Store 拥有；Control Plane 只通过 candidate_attempt_id 引用所属 Candidate Attempt，不复制该事实。
_Avoid_: Iteration Event、Control Event、Candidate Attempt State

**Candidate Attempt State**:
由一个 Candidate Attempt 的 Event 折叠得到的当前状态。
_Avoid_: Iteration Summary、Control State、Candidate Workspace

**Candidate Attempt Journal**:
Template Version Store 持久化 Candidate Attempt Event 的权威有序记录；它不记录 Work Item 编排状态。
_Avoid_: Iteration Journal、Control Journal、Session

### Version Lifecycle

**Accepted Template Version**:
已经通过接受流程、可以实例化 Harness 的 Template Version；完整形式为 Accepted Harness Template Version。
_Avoid_: Checkpoint、Snapshot、Candidate Template

**Incumbent Version**:
当前 Generation 正在尝试改进的 Accepted Template Version。
_Avoid_: Baseline、Parent Version

**Parent Version**:
Candidate Template 创建时直接派生自的 Accepted Template Version，描述版本谱系关系；在串行 Evolution Run 中通常也是当时的 Incumbent Version。
_Avoid_: Incumbent Version、Baseline

**Promotion**:
Candidate Attempt 通过全部门禁后生成新 Accepted Template Version 的状态转换。
_Avoid_: Acceptance Recommendation、Validation

**Rejection**:
Candidate Attempt 终止且不产生新 Accepted Template Version 的状态转换；它不必终止整个 Evolution Run。
_Avoid_: Run Failure、Revision

**Version Lineage**:
Accepted Template Version 之间的父子谱系，不包含被拒 Candidate Attempt。
_Avoid_: Evolution History、Candidate History

**Template Version Store**:
持久化 Accepted Template Version、Candidate Attempt 及 Version Lineage 的存储边界；完整形式为 Harness Template Version Store。
_Avoid_: Checkpoint Store、Harness Checkpoint Store

### Data, Evidence, and Experience

**Dataset**:
项目从外部获得的任务数据来源，可包含尚未进入任何 Evolution Run 的样本。
_Avoid_: Evolution Set、Experience Store

**Example**:
从 Dataset 规范化得到的一个任务样本，是选择、执行和比较 Student Rollout 的逻辑单位。
_Avoid_: Case、Question、Replicate

**Evolution Set**:
从 Dataset 物化并在一个 Evolution Run 内冻结的 Example 集合，用于失败发现、Intervention Trial 选择和 Candidate 比较。
_Avoid_: Experience Set、Evaluation Set、Dataset

**Evidence**:
由 Student Rollout、Intervention Trial、评审或评估产生，用于支持或反驳某个具体判断的可追溯观察。
_Avoid_: Research Experience、Artifact、Metric

**Research Experience**:
经过确认、能够跨 Evolution Run 复用的抽象研究结论；未经审查的模型自由文本不构成 Research Experience。
_Avoid_: Evidence、Historical Experience、Memory

**Experience Store**:
持久化和检索 Research Experience 的确定性存储边界。
_Avoid_: Evolution Set、Memory Store、Evidence Store

### Research Execution

**Research Attempt**:
一个 Generation 内从 Failure Analysis 开始、以 Candidate Promotion、Rejection 或研究阶段终止为边界的单一研究方向；定向 Revision 仍属于原 Research Attempt。
_Avoid_: Generation、Candidate Attempt、Evolution Run

**Research Experiment**:
为回答一个明确研究问题而设计的经验研究，规定假设、控制变量、比较条件和判据，并可包含一个或多个具体执行。
_Avoid_: Evolution Run、Experiment Run

**Focused Probe**:
Research Experiment 中只验证一个局部能力、机制或接口边界的有界执行，不运行完整 Evolution 闭环。
_Avoid_: Evolution Run、Intervention Trial、Experiment Run

### Verification and Promotion

**Evaluation Input**:
一次 Evaluation 所需的 Example、Student Rollout 输出和参考信息。
_Avoid_: Evaluation Case、Example、Evaluation Result

**Example Evaluation Result**:
针对一个 Example 的一次 Evaluation 结果，可包含 Metric、错误与 Teacher Judgment。
_Avoid_: Evaluation Input、Evaluation Report、Teacher Judgment

**Evaluation Report**:
聚合多个 Example、Replicate 或评估层的持久化结果。
_Avoid_: Example Evaluation Result、Candidate Review、Artifact

**Evaluation Outcome**:
由评估规则计算出的分类结果，例如 pass、needs_teacher 或 unresolved。
_Avoid_: Decision、Recommendation、Metric

**Finding**:
Reviewer 对具体 Evidence 作出的可追溯事实性或解释性发现。
_Avoid_: Evidence、Verdict、Evidence Obligation

**Verdict**:
Review 对被审对象的分类判断，例如 faithful、inconclusive 或 implementation_mismatch。
_Avoid_: Finding、Recommendation、Decision

**Recommendation**:
Teacher Role 建议 Evolution Controller 接下来采取的动作；Recommendation 不直接提交 Control State。
_Avoid_: Decision、Transition、Promotion

**Decision**:
具有确定性权限的程序机制最终提交的控制选择，例如 Promotion Gate 的 Promotion 或 Rejection；Teacher Role 的路由意见不得命名为 Decision。
_Avoid_: Recommendation、Verdict、Teacher Judgment

**Candidate Validation**:
确定性检查 Candidate Template 是否结构合法、可装配、遵守不可变边界并满足 Harness 生命周期契约；不判断任务效果。
_Avoid_: Task Evaluation、Conformance Evaluation、Candidate Review

**Task Evaluation**:
通过 Student Rollout 测量任务质量、稳定性、执行错误和成本；不判断 Candidate Template 是否忠实实现 Mechanism Spec。
_Avoid_: Candidate Validation、Candidate Review、Teacher Judgment

**Teacher Judgment**:
Task Evaluation 中针对单个 Example 的可选 Teacher Model 评分，只贡献评估结果，不决定 Promotion。
_Avoid_: Candidate Review、Promotion Gate

**Mechanism Conformance Evaluation**:
在 Intervention Trial 涉及的 Example 上评估 Candidate Template 是否忠实实现 Mechanism Spec，不要求精确重放既有 Trajectory。
_Avoid_: Mechanism Conformance Replay、Task Evaluation、Candidate Validation

**Conformance Review**:
Teacher Agent 对一条 Candidate Student Rollout 作出的实现保真判断，是 Mechanism Conformance Evaluation 的证据输入。
_Avoid_: Candidate Review、Task Evaluation

**Candidate Review**:
Teacher Agent 综合 Candidate Validation、Mechanism Conformance Evaluation、Task Evaluation 和版本差异后给出的采纳或修订建议。
_Avoid_: Promotion、Promotion Gate、Teacher Judgment

**Promotion Gate**:
程序拥有的最终确定性门禁，结合前置检查、Candidate Review 建议和配置阈值决定 Promotion 或 Rejection。
_Avoid_: Candidate Review、Acceptance Recommendation

**Metric**:
Evaluation 产生的测量值，是 Evidence 的一种结构化观察，但本身不是 Review 或 Decision。
_Avoid_: Evidence、Review、Decision

### Evolution Research

**Failure Direction**:
从 Task Evaluation 中识别并选定的、具有 Evidence 范围和适用边界的 Student Agent 行为问题。
_Avoid_: Failure Case、Implementation Proposal、Mechanism

**Intervention Hypothesis**:
关于在指定 Harness 生命周期位置施加某种临时 Intervention 会产生何种可观察效果的可证伪预测。
_Avoid_: Mechanism Spec、Candidate Proposal

**Trajectory Prefix**:
Student Trajectory 中截至某个 Harness 生命周期边界的完整前缀，是 Intervention Trial 的分支起点。
_Avoid_: Trajectory、Prompt Prefix、Partial Rollout

**Intervention**:
Teacher Agent 在 Intervention Trial 中对 Student Harness Instance 施加的临时、受控影响，不会自动成为 Candidate Template 中的永久行为。
_Avoid_: Mechanism、Template Edit、Teacher Feedback

**Trial Review**:
针对一条 Intervention Trial 的事实分析，不负责跨 Trial 作总体判断。
_Avoid_: Evidence Review、Candidate Review

**Evidence Review**:
综合多条 Trial Review 后，对 Intervention Hypothesis 的支持程度和下一步作出的判断。
_Avoid_: Trial Review、Candidate Review、Promotion Gate

**Evidence Obligation**:
当前 Evidence 尚不能回答、下一步必须验证的一个明确可证伪问题。
_Avoid_: TODO、Research Experience、Reviewer Comment

**Mechanism**:
无需 Teacher Agent 在线参与、由 Student Harness 自主执行的可复用行为。
_Avoid_: Intervention、Hook、Template Edit

**Mechanism Spec**:
Mechanism 的实现无关表示，描述触发条件、输入、动作、状态、fallback、约束和可观测信号；它不是代码。
_Avoid_: Candidate Template、Intervention Hypothesis、Implementation Plan

**Distillation**:
把已支持的 Intervention Hypothesis 和 Evidence 转换为 Mechanism Spec 的过程。
_Avoid_: Compilation、Summarization

**Mechanism Compilation**:
把 Mechanism Spec 转换为 Candidate Template 的过程。
_Avoid_: Python Compilation、Harness Instantiation、Distillation

### Teacher Roles

**Failure Analyst**:
从 Task Evaluation 中选择 Failure Direction 的 Teacher Role。
_Avoid_: Failure Critic、Critic

**Hypothesis Researcher**:
提出或修订 Intervention Hypothesis 的 Teacher Role。
_Avoid_: Researcher、Intervention Researcher

**Intervention Executor**:
依据 Intervention Hypothesis 在 Trajectory Prefix 上执行 Intervention Trial 的 Teacher Role。
_Avoid_: Intervention Worker、Worker

**Trial Reviewer**:
对一条 Intervention Trial 形成 Trial Review 的 Teacher Role。
_Avoid_: Evidence Reviewer、Critic

**Evidence Reviewer**:
聚合 Trial Review 并形成 Evidence Review 的 Teacher Role。
_Avoid_: Trial Reviewer、Critic

**Mechanism Distiller**:
执行 Distillation 并产出 Mechanism Spec 的 Teacher Role。
_Avoid_: Summarizer、Mechanism Designer

**Mechanism Compiler**:
执行 Mechanism Compilation 的 Teacher Role。
_Avoid_: Compiler、Harness Compiler、Code Generator

**Conformance Reviewer**:
判断一条 Candidate Student Rollout 是否符合 Mechanism Spec 的 Teacher Role。
_Avoid_: Candidate Reviewer、Conformance Judge

**Candidate Reviewer**:
综合候选 Evidence 并提出采纳、修订或拒绝建议的 Teacher Role；它不执行 Promotion。
_Avoid_: Promotion Gate、Candidate Critic

Teacher Role 的闭合集合不包含 Evolution Controller 或 Teacher Judgment；前者是确定性控制机制，后者是 Task Evaluation 的可选评分能力。

### Harness Composition

**Harness Component**:
Harness 中可独立声明、配置和替换的组成单元。
_Avoid_: Plugin、Hook、Component Declaration

**Prompt Component**:
负责根据当前 Harness State 构造 Model Input 的 Harness Component。
_Avoid_: Prompt Template、System Prompt

**Output Component**:
负责把 Model Response 转换为 Parsed Model Output，并按照 Output Contract 识别 Tool Call、Final Output Candidate 或解析失败的 Harness Component。
_Avoid_: Output Contract、Output Collector、Final Output

**Tool Component**:
向 Model 暴露可调用外部能力的 Harness Component。
_Avoid_: Tool Call、Tool Result、Teacher Tool

**Extension Component**:
向 Harness 生命周期贡献一个或多个协同 Hook 的 Harness Component，可作为跨 Lifecycle Phase 行为和共享状态的组合边界。
_Avoid_: Hook、Plugin、Mechanism

**Hook**:
绑定到一个或多个 Lifecycle Phase 的最小拦截行为，由 Extension Component 提供。
_Avoid_: Extension Component、Intervention、Mechanism

**Harness Manifest**:
Harness Template 中声明 Harness Component、配置和装配顺序的索引；它不携带 Evolution Policy。
_Avoid_: Harness Template、Plugin Registry

**Component Declaration**:
Harness Manifest 中对一个 Harness Component 实例的声明，包括稳定身份、实现入口和配置。
_Avoid_: Harness Component、Component Spec

**Evolution Policy**:
Evolution 应用对 Mechanism Compilation 是否允许修改某个 Harness Component 或模板文件的约束；它独立于 Harness Manifest 和 Component Declaration。
_Avoid_: Promotion Policy、Access Control

**Harness Assembly**:
根据 Harness Template、Harness Manifest 和运行依赖解析并构造 Harness Component 的过程。
_Avoid_: Harness Instantiation、Registry、Mechanism Compilation

**Component Factory**:
根据 Component Declaration 和 Component Factory Context 创建 Harness Component 的 callable。
_Avoid_: Component Loader、Plugin、Harness Component

**Component Loader**:
解析组件 entrypoint 并加载 Component Factory 的基础设施。
_Avoid_: Component Factory、Registry、Plugin Importer

**Registry**:
维护稳定 key 到 implementation 或 provider 映射的对象；当前仅执行 manifest 读取、动态加载和组件装配的代码不构成 Registry。
_Avoid_: Harness Assembly、Component Loader、Manifest

**Template Contents**:
一个 Template Version 对应的不可变文件内容集合。
_Avoid_: Harness Snapshot、Candidate Workspace、Template Version

**Candidate Workspace**:
从 Parent Version 的 Template Contents 创建、供一次 Candidate Attempt 事务性修改的可变工作区。
_Avoid_: Candidate Template、Template Contents、Harness Instance

**Template File Edit**:
Candidate Workspace 中一次明确的文件写入或删除操作。
_Avoid_: Patch、Template Contents、Candidate Attempt

### Harness Lifecycle and State

**Harness Lifecycle**:
Harness 在一个 Agent Run 内遵守并向 Hook 暴露的阶段与边界模型，覆盖输入构造、Model 调用、输出解析、Tool 执行和 Final Output 处理；Agent Loop 是驱动该 Lifecycle 的一种控制机制。
_Avoid_: Evolution History、Agent Loop

**Lifecycle Step**:
一次从 Model Input 构造到 Tool Call 或 Final Output Decision 的决策循环。
_Avoid_: Work Item、Generation、Lifecycle Phase

**Lifecycle Phase**:
Lifecycle Step 中允许 Hook 观察或修改状态的稳定边界。
_Avoid_: Lifecycle Step、Mechanism Activation

**Harness State**:
Harness Instance 在一个 Agent Run 期间拥有的全部 Model 外部可变状态。
_Avoid_: Model Context、Control State、Artifact

**Stage State**:
当前 Lifecycle Step 某个处理阶段的短生命周期状态。
_Avoid_: Extension State、Control State

**Extension State**:
由一个 Extension Component 拥有、可跨 Lifecycle Phase 或 Lifecycle Step 保留的 Agent-Run-scoped 状态。
_Avoid_: Stage State、Global State

**Hook Context**:
一次 Hook Invocation 获得的受限状态与能力视图，不代表完整 Harness State。
_Avoid_: Harness State、Model Context

**Hook Invocation**:
Harness 到达某个 Lifecycle Phase 时对一个 Hook 的调用；即使 Hook 不修改状态，也仍然发生 Invocation。
_Avoid_: Mechanism Activation、Intervention Invocation

**Intervention Invocation**:
Intervention Executor 在指定 Lifecycle Phase 获得控制权的一次调用，可以施加 Intervention 或选择 no-op。
_Avoid_: Hook Invocation、Mechanism Activation

**Mechanism Activation**:
Mechanism 触发条件满足且实际执行动作的一次行为；仅经过对应 Lifecycle Phase 不构成 Activation。
_Avoid_: Hook Invocation、Phase Visit、Intervention Invocation

### Evolution Control Plane

**Evolution Controller**:
根据 Evolution History 和 Control Policy 选择 Work Item、执行恢复协议并提交状态转换的确定性控制机制。
_Avoid_: Teacher Role、Agent、Workflow

**Run Agenda**:
一个 Evolution Run 中已安排 Work Item 的持久化有序集合。
_Avoid_: Workflow、Queue、Evolution History

**Control Policy**:
预算、重试限制和 Promotion Gate 等不依赖模型自由判断的确定性规则。
_Avoid_: Evolution Policy、Teacher Recommendation

**Control Effect**:
执行 Work Item 时发生的、可能访问 Model、文件、Student Rollout 或 Template Version Store 的有界外部操作。
_Avoid_: Transition、Hook、Work Item

**Effect Receipt**:
Control Effect 完成后、Transition 提交前持久化的结果与 Artifact Reference，用于中断恢复和幂等复用。
_Avoid_: Effect Result、Control Event、Artifact

**Transition**:
根据当前 Control State 和已完成 Effect Receipt，纯计算下一批 Work Item、Evolution Run 终态或版本推进。
_Avoid_: Control Effect、Routing Workflow

**Control Event**:
Evolution Controller 提交的一个不可变、追加式编排事实；涉及模板事务时只记录 Candidate Attempt、Effect Receipt 或 Artifact 的引用，不复制 Candidate Attempt Event。
_Avoid_: Artifact、Log Message、Effect Receipt

**Control Journal**:
Evolution Controller 持久化 Control Event 的权威顺序记录；它不持久化 Template File Edit、Candidate Validation 或版本事务细节。
_Avoid_: Evolution History、Artifact Store

**Control State**:
由 Control Journal 投影得到的当前 Evolution Run 状态，不是独立事实来源。
_Avoid_: Harness State、Stage State、Source of Truth

**Artifact Reference**:
Effect Receipt、Control Event 或角色协议中指向 Artifact 的稳定引用。
_Avoid_: Artifact、Evidence Reference

**Work Retry**:
同一个 Work Item 因失败而重新执行，保留工作身份并增加 attempt。
_Avoid_: Run Resume、Role Continuation

**Run Resume**:
从已有 Evolution History 恢复一个暂停或中断的 Evolution Run。
_Avoid_: Work Retry、Role Continuation

**Role Continuation**:
向既有 Role Session 追加反馈并继续同一研究职责的动作。
_Avoid_: Work Retry、Run Resume、新 Role Invocation
