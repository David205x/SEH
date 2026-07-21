# 当前代码架构

## 文档职责

本文档记录当前 `search_harness` 仓库已经实现的模块边界、运行链路和工程约定，供维护和新增代码时核对。

它不替代 `../design/` 中的研究设计。本文明确区分“当前已实现”与“已确认但尚未迁移”的方向，避免将讨论中的目标误认为代码事实。

## 当前模块布局

```text
search_harness/
  core/          固定 Agent Loop、协议、解析、工具运行时、Hook 状态与 Trace
  framework/     通用工具定义、参数校验与 prompt renderer
  registry/      外部 plugins root 的 manifest 读取、显式加载与装配
  versioning/    内存候选 workspace、规则验证与已接受版本的 Git 存储
  models/        OpenAI-compatible 文本模型客户端
  datasets/      筛选 HotpotQA JSONL 的加载与规范化
  runtime/       UTF-8 .env 读取与基础配置解析
  runners/       单题与数据集 rollout 入口
  evaluation/    独立任务评分、Teacher 兜底裁判与实验报告
  adapter/       离线 Adapter 边界、统一入口及 critic/compiler 角色包
  visualizer/    本地 Trace Viewer
  paths.py       模板、checkpoint、组件运行与完整实验的默认根路径
```

具体工具、prompt 和 hook 不再位于 `search_harness/` 框架包中。当前 Actor 基线位于 `harness_templates/actor/baseline/plugins/`，其加载协议见 [Harness Plugins](harness-plugins.md)。框架外产物目录见 [Artifact Layout](artifact-layout.md)。

## Actor Rollout

`core.AgentLoop` 是当前稳定的执行内核。它只依赖四类抽象实例：

- `ModelClient`：从结构化 `ModelInput` 生成文本；
- `PromptBuilder`：从 `AgentState` 构造结构化 chat messages；
- `OutputParser`：将模型文本分为工具调用、最终答案或无效输出；
- `ToolRuntime`：一次串行执行一个已启用工具。

当前循环为：

```text
pre_prompt hook
  -> PromptBuilder
  -> post_prompt hook
  -> model.generate
  -> post_model hook
  -> parser
  -> post_parse hook
  -> tool call / final answer / invalid output
```

工具分支还会触发 `pre_tool` 与 `post_tool`，最终答案分支触发 `pre_final`。该阶段接收 `stage.final_decision: FinalDecision`，默认 accept 当前候选答案；Hook 可 defer 并提供下一轮反馈，core 随即保留模型原文、追加 feedback 并继续循环。defer 在一个阶段中不可被后续 Hook 改回 accept，且仍由 `max_steps` 统一限制。无效解析结果不会立即终止：`post_parse` hook 可以根据 `stage.parser_input` 细化 `stage.parsed_output.error`，随后 core 保留模型原文、生成通用 user 纠错消息，并将二者追加到 `conversation_messages` 进入下一步。连续无效输出最终由 `max_steps` 限制终止。`on_error` 只覆盖工具运行时错误和达到最大步数等真正终止情形。工具运行时不处理并发或读写冲突；同一时刻只有一个工具调用。

## 当前 Hook 与状态机制

`BaseHook` 是抽象基类。每个 hook 声明订阅的 `phases`，并实现唯一的 `handle(context)`；`HookPipeline` 以外部 manifest 的 extension 顺序执行订阅当前阶段的实例。

每次 hook 调用获得 `HookContext`，并可读取当前 rollout 的完整可见状态：

- `core.*`：由 loop 管理的状态投影，只读；
- `stage.*`：当前阶段的临时主载荷，例如 `stage.raw_model_output`、`stage.tool_call`；
- `extension.<hook_id>.*`：扩展自身声明的持久状态；
- `shared.*`：多个 hook 可协作读取的声明式状态。

Hook 对 `stage.*` 的修改必须在实例的 `writable_stage_keys` 中声明；对持久状态的修改必须由 `StateRef` 注册并拥有 writer 权限。一次 hook 调用中的写入先暂存，再原子提交；异常时记录 `hook_error` 并丢弃未提交变更。声明 `model_profiles` 的 hook 还可通过 `context.call_model(...)` 调用受控的小模型后端；教师生成的 hook 自行选择可见状态中的上下文，但不能绕过 profile 与单次调用上限。

Trace 会保留 core 事件和每次 `hook_applied` 事件。后者记录 hook ID、阶段及每个状态键完整的 before/after 值，因此可还原“模型生成 A，hook 改为 B，parser 消费 B”的因果链。Hook 内模型的完整结构化输入、原始输出、原生 reasoning 与 usage 单独记录为 `hook_model_output`；调用失败记录为 `hook_model_error`。模型输出本身不等同于状态修改，只有 hook 显式提交的状态变化才进入后续流程。

Student baseline 是不预装 extension 的干净初始化模板，只保留 fixed Retriever 与 simple
search prompt。`result_summary_prompt`、`lifecycle_audit`、`tool_delegation` 和
`decomposed_context_controller` 等研究实现保留在 `harness_templates/experiments/`；具体
策略应由 Adapter 发现并通过 mutable extension 演化产生。

Critic baseline 默认启用 fixed `format_error_feedback` extension 作为 Adapter 自身可靠性能力。它订阅 `post_parse`，仅在 invalid 分支读取 `stage.parser_input`，诊断缺失的 action 开始/结束标签和误用的 `<tool_use>`，再用更具体的错误替换 `stage.parsed_output`。Core 仍统一负责把该错误组装成下一轮 user 反馈。

## 当前 Prompt、工具与模型

当前 simple search prompt plugin 维护应用侧的结构化消息，不直接拼接服务端 chat template。系统模板由 plugin 目录中的 UTF-8 文件加载，工具描述由 `ToolDefinition` 和 tagged renderer 动态插入。Core 按发生顺序维护 `conversation_messages`：成功工具调用写入 assistant 原文与 user observation，无效输出写入 assistant 原文与 user 格式反馈；PromptBuilder 将该历史原样放入下一轮消息，不再通过工具调用下标推断对话对应关系。

Tagged parser 只显式匹配 `<tool_call>` 和 `<final_answer>` action 块，不再要求或正则提取 `<thinking>`。完整 action 块以外的所有非空正式 content 统一记录为 `ParsedOutput.inband_thinking`。没有完整 action 块时仍产生 invalid parse 事件，但由 loop 反馈并继续，而不是立即结束。

当前工具定义通过函数 docstring、`@tool` 与 `Annotated[..., ToolArg(...)]` 生成。`ToolSet` 同时提供给 PromptBuilder 与 ToolRuntime，确保模型可见工具集合和实际可调用集合一致。OpenAI-compatible 客户端把服务端 `message.content` 作为正式 `raw_output` 交给 parser；独立的原生 `reasoning_content`、`reasoning` 或 `thinking` 字段则按 provider 原字段名保存到 `model_output` trace metadata，不参与 parser 或后续 prompt。前者 action 块外推导出的 `inband_thinking` 与后者 provider 原生 reasoning 是两个不同概念。

基线 Retriever plugin 从 `.env` 读取 `RETRIEVER_URL` 等配置，调用受控检索服务，并将结果作为 JSON 文本 observation 返回。模型客户端 `OpenAICompatibleTextModel` 从同一 UTF-8 `.env` 读取 `STUDENT_*` 或 `TEACHER_*` 配置，支持 OpenAI-compatible chat completions 与本地 Ollama 的 `think` 参数。

## 数据、Runner 与 Trace

数据集层当前支持筛选后的 HotpotQA JSONL。默认可从 `.env` 的 `OUTPUT_DIR` 加 `DATASET_FILE` 找到 `supported.jsonl`；其中 `supported` 表示当前检索服务具备支持证据的问题子集。

`run_actor_once` 运行单题；`run_dataset` 通过有界线程池执行指定数量的独立样本，并支持
`--rollouts-per-example N`。Experience Set 不复制，Runner 将每题展开为 `r000..rNNN`，按
数据集顺序和 replicate 顺序写入 UTF-8 JSONL；`(example_id, replicate_id)` 是轨迹唯一键。
实际 seed 由角色 base seed 加 replicate index 派生，并同时用于主 Actor 和 Hook 小模型。
每个 worker 构造独立 Loop，插件组装中的全局模块导入区间受锁保护。单题运行时异常写入
`runner_error`，默认继续后续样本。每条 rollout 记录数据、Harness、模型、并发数、重复次数
和 seed strategy provenance。服务端是否兑现 seed 仍由 provider 决定。

`evaluation` 在 Actor Harness 外部读取这些 JSONL。当前 HotpotQA 实现先顺序执行确定性规范化 Exact Match；非精确但有答案的项可由线程独立的 `TEACHER_*` Judge 进行有界并发的离线 0/1 语义裁判，默认 `--judge-workers 8`，Teacher 故障保留为 unresolved。报告顺序保持不变，并使用 `summary.json`、`summary.md` 与 `per_example.jsonl` 汇总可用的 provider token usage、执行状态和工具行为指标。完整协议见 [Offline Evaluation](evaluation.md)。

`visualizer` 默认只读加载 `runs/components/actor/` 下各 run 的 rollout JSON/JSONL，提供文件列表、对话轨迹与轨迹信息三栏视图。批量 JSONL 的 `example.answer` 会显示为 Golden Answer。所有 `hook_applied`、`hook_error`、`hook_model_output` 与 `hook_model_error` 都按 Trace 顺序渲染，不再由额外开关隐藏。时间线将一次 `model_output` 与同 step 的 `parsed_output` 配对：provider metadata 中的 `reasoning_content`、`reasoning` 或 `thinking` 显示为 Native thinking；action 标签外由 parser 得到的 `inband_thinking` 显示为 In-band thinking；完整 `<tool_call>` / `<final_answer>` 显示为 assistant action。三者互不混用。assistant、两类 thinking、user 和 error 内容使用可翻译的普通文本容器；tool、hook 与 context 内容标记为 `translate="no"` 并保留等宽技术文本。桌面端的左栏、中部内容区和右栏分别使用独立滚动容器；窄屏回退为自然纵向页面滚动。每个轨迹块限制高度并在内容区滚动；顶栏的 `Expand roles` 多选菜单只控制各角色块的默认展开状态，单块标题可临时切换展开状态。`/translation-test.html` 仍提供翻译插件对照验证，但不占用主导航位置。

同一服务的 `/evaluation.html` 展示 `runs/components/actor/` 下的评估汇总和逐样本判定，中部为当前样本详情，右栏上方为所选报告的 Metrics、下方为 Items 目录。`/critic.html` 与 `/compiler.html` 默认分别读取 `runs/components/critic/` 和 `runs/components/compiler/`。`/experiment.html` 读取 `runs/experiments/`，按 iteration 聚合 Runner event，并在同页逐条呈现 Actor、evaluation、Critic、Compiler 与 decision artifact。通过 `--checkpoint-store` 配置 checkpoint store 后，`/harness.html` 可在 Evolution 与 Topology 间切换：前者展示 iteration journal、accepted version 链及 manifest/file diff，后者通过真实 registry 装配所选版本并显示 prompt、tools、extensions、hook 生命周期、状态权限与小模型 profile。六个主要页面通过紧凑的 navbar item 导航；所有数据投影均为只读，不会修改底层文件或 Store。

## Plugins Root 与演化边界

`run_actor_once` 与 `run_dataset` 都提供 `--plugins-root`，默认使用 `harness_templates/actor/baseline/plugins`。registry 根据该目录的 UTF-8 `harness.json` 显式加载 factory，并在 core 之外组装 `PromptBuilder`、`ToolSet` 和 `HookPipeline`。`run_dataset` 还可通过 `--checkpoint-store` 搭配 `--harness-version` 或 `--iteration-id` 运行 accepted snapshot 或 pending candidate；pending candidate 会在 rollout 前按当前 digest 重新验证，并在整批运行期间保持临时 plugins root 有效。输出 JSONL 的每条记录都会保存 Harness 来源、checkpoint store ID、版本或迭代 ID 与 digest。

每个组件实例都声明 `evolution_policy`。`versioning` 以已接受快照和内存 overlay 管理候选修改，按父版本保护 `fixed` 组件，并在临时目录完成语法与真实装配验证。新增 extension 由受控接口自动标记为 `mutable`。只有接受后的完整 plugins tree 才写入 Version Store 自己的 Git 仓库；候选版本不会持久复制为目录。

需要断点恢复的候选通过 `IterationSession` 修改。其完整 file patch、验证报告与 accept/reject 决策追加到 `.harness-store/iterations.jsonl`；重启后可从 parent version 重放 patch 并校验 candidate digest。Git 保存接受版本，iteration journal 保存待定及拒绝的修改经历。当前历史和 journal 都是单进程线性模型，接口与约束见 [Harness Version Store](version-store.md)。

## Adapter 当前边界

`adapter.critic.CriticResult` 保留完整自然语言 `analysis`，并以开放字典承载行为级
`problem_directions`，同时允许记录 `evidence_requests` 与候选 review。问题方向只描述
失败模式、排除原因、目标行为、成功标准和约束，不指定 Hook、Prompt 或代码方案。

当前只读 Critic Agent 将一次运行绑定到一个 Experience Set evaluation report、其 source rollout 和一个 Actor Harness snapshot，并可选择绑定第二组报告、rollout 与 snapshot。单版本证据和跨版本对比证据均通过外部注册工具按需读取。除 accepted `--harness-version` 外，Critic 还可通过 `--iteration-id` 将 pending candidate 作为 primary Harness，并默认以其 parent accepted version 作为 comparison；模型调用前会校验 rollout 的 checkpoint store、version/iteration ID 与 digest。具体 prompt 和工具位于 `harness_templates/adapter/critic/baseline/plugins/`；registry 的可选 `PluginContext.runtime_context` 只负责把本次只读数据视图交给这些实例，普通 Actor 装配不受影响。运行入口、日志结构和工具语义见 [Read-only Critic Agent](critic-agent.md)。

独立 Compiler 只接受 `verdict=supported` 的 Coordinator artifact，并沿其中的
`direction_source` 校验 Critic parent version/digest；它读取问题方向、代表 trial 和验证
账本，将验证策略编译为完整 `FileEdit` 事务。Compiler 本身不执行候选 rollout、accept
或 reject；候选保持 pending。

`search_harness.adapter.intervention` 的 Coordinator 正式绑定一个 Critic 问题方向，在失败
池中跨案例提出和验证实际方案，输出 `supported/rejected/inconclusive`。EvolutionRunner
将其作为 failure Critic 与 Compiler 之间的可恢复阶段；Worker 使用当前 accepted Harness
的临时 stage，产物写入对应 iteration。静态 `needs_teacher` 分支可由独立 Teacher Judge
解析为不暴露 golden 的 0/1。接口见 [Standalone Intervention Worker 与 Coordinator](intervention-worker.md)。

Evaluation 先将每条 replicate 写入 `per_rollout.jsonl`，再按 `example_id` 聚合到唯一的
`per_example.jsonl`，输出 success rate、稳定正确、稳定失败、不稳定、answer consistency、
majority 和 pass@n。Critic 的概要工具只接收 `example_id`；完整轨迹、paired diff、prefix
恢复和 Intervention trial 必须同时接收 `example_id + replicate_id`。候选 review 在模型
调用前校验两侧复合身份及 sampling seed 完全对齐。

Compiler clarification 会在同一外层 iteration 内返回 Coordinator。修订会话继承旧 trial
账本和完整反馈，使用额外有界 trial 预算补证，再重新调用 Compiler；Coordinator 的 fixed
`PRE_FINAL` 守门禁止在没有跨案例正向证据，或收到反馈后没有新增正向 trial 时提交
`supported`。内层修订预算耗尽后才产生 run 级 `needs_clarification`。
格式错误的 Coordinator final 会由该守门 Hook defer 后反馈，无法恢复的运行也会保存失败
artifact。相同通用 Hook guidance 必须在至少两个失败案例上原样取得正向结果，避免把多个
手写案例提示误判为可编译机制。Compiler 的 deterministic validation 失败会在 backend
内部有界返修：每次使用同一 accepted parent 创建新事务，完整校验错误进入下一次 Compiler
输入。连续拒绝候选时，同一 accepted parent 的 incumbent evaluation 在 run 内复用。

模型采样由 `.env` 中角色级 `<ROLE>_TEMPERATURE` 和 `<ROLE>_SEED` 控制，并写入 rollout
provenance；当前默认模板使用 `0.6` 与固定 seed，provider 是否兑现 seed 仍由服务端决定。
