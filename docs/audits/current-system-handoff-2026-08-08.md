# Search Harness 当前系统交接

## 1. 交接口径

本文记录 2026-08-08 时工作区中已经存在的实现和已经落盘的实验结果，不描述路线图或待实现方案。代码快照为 `main` 分支提交 `006426f` 加当前未提交工作区改动；V1 最终可运行状态保存在 `archive/v1-final`，活动实现只采用当前新格式。

结论先行：当前系统已经形成可运行、可恢复、可审计的 Harness 自进化闭环，并在真实 API 实验中完整运行到 Candidate Review；但是现有实验没有晋升出新的 Accepted Template Version，当前已接受版本仍是 `harness_v0001`。因此，已经验证的是闭环工程能力和否决无效候选的能力，不是稳定提升 Student 效果的能力。

## 2. 当前已完成内容

### 2.1 通用 Agent/Harness Framework

- 已统一术语和对象边界：`Agent = Harness + Model`；Harness 负责模型调用以外的上下文、状态、工具和生命周期机制，Harness Template 只是其实例化资产。
- 已建立角色无关的 `framework` 边界，包含 Agent、Model、Agent Loop、Harness、Manifest/Assembly、Component、Tool、Hook 生命周期、状态和 Trajectory。
- Student 与 Teacher Template 已共用 `HarnessManifest`、`HarnessAssembler` 和 Component Factory；Teacher Role Contract 不再写入 Harness Manifest。
- Agent Loop 已实现 `pre_prompt`、`post_prompt`、`post_model`、`post_parse`、`pre_tool`、`post_tool`、`pre_final` 和 `on_error` 生命周期，并支持事务式 Hook 状态修改及 `FinalDecision.defer`。
- 已提供 OpenAI-compatible Model/Tool Runner 和 OpenAI Agents SDK Runner 两种外层适配；正式 Evolution Controller 使用 OpenAI-compatible 原生工具循环。

### 2.2 Template、Evaluation 与 Version Store

- 正式 Student/Teacher Template 已迁移为较浅目录：`harness.json` 与 `prompt/`、`output/`、`tools/` 等职责目录直接位于角色或模板根下；角色转移提示也已外置为模板资产。
- Evaluation 已拆分为不可变 Rollout、静态 HotpotQA 判分、可选 Teacher Binary Judge 和聚合报告；支持同一 Example 多 replicate，并报告准确率、稳定性、步骤、工具调用和 token。
- Template Version Store 已使用 Git 保存 Accepted Template Version，并以独立 Journal 保存 Candidate Attempt；Candidate Workspace 支持事务式增删改、digest、确定性校验、拒绝和原子晋升。
- Promotion Gate 已独立于 Candidate Reviewer，确定性检查 Candidate Validation、准确率增量、运行错误和 token 比率；Reviewer 的接受建议不能绕过安全门禁。

### 2.3 Teacher Roles 与证据链

当前已实现九个闭集 Teacher Role：Failure Analyst、Hypothesis Researcher、Intervention Executor、Trial Reviewer、Evidence Reviewer、Mechanism Distiller、Mechanism Compiler、Conformance Reviewer 和 Candidate Reviewer。普通角色通过严格 Pydantic 输入输出协议、动态终态工具和资源访问义务执行；Role Artifact 保存协议版本、Schema digest、输入、输出、工具调用、usage、transcript 和资源读取记录。

- Failure Analyst 从 Incumbent Evaluation 中读取并引用失败轨迹。
- Hypothesis Researcher 生成带 phase plan、成功条件和 falsifier 的干预假设；修订可复用同一 Role Session。
- Intervention Executor 在真实 Student 分支中跨 phase 保持 Tool Session；使用 API 原生 structured tool calling，不再解析文本工具 envelope。
- Trial Reviewer 对每个 phase 分别记录 predicate label、执行状态、直接行为效果和 outcome evidence。
- Evidence Reviewer 接收完整 Trial Review、程序聚合的覆盖摘要以及 Trial/Assignment 总量、已用量和剩余量。
- Mechanism Distiller 将证据转为逐 phase 的 guard、三值 decision contract、evaluator、action 和 fallback；`hook_model` 规则可以调用正式 Hook Evaluator Probe 做重复分类观测。
- Mechanism Compiler 只能通过受控 Candidate Workspace 修改模板；提交前必须得到可解析的 Candidate Artifact，并经过确定性 source review 和 Candidate Validation。
- Conformance Reviewer 使用裁剪后的 `candidate_trajectory_view` 判断实现保真，并按 evidence、mechanism 或 implementation 标注回流层级。
- Candidate Reviewer 对同一 Evolution Set 的 incumbent/candidate 指标、配对轨迹和实现变化给出接受、修订或拒绝建议。

### 2.4 Intervention 与编译能力

- Student 可见对话已投影为顺序数字 `block_id`；Worker 可按需检查单块，并通过一组原子操作在指定位置新增、替换或删除内容。程序维护块与内部消息、ToolResult 和 metadata 的映射，Worker 不需要填写任务无关 metadata。
- `pre_final` 仍使用专用 FinalDecision 动作；`post_prompt` 和 `post_tool` 可使用通用 context patch。
- Search-o1 改写案例迁移到原生 structured tool calling 后，真实 API 并行执行 3 次，三次都完成 `inspect_editable_context → inspect_context_block → apply_context_patch`，均得到 `executed` 和完成的 Student branch，未再出现 DSML 文本标记污染。
- Mechanism 的 `runtime_inputs` 使用受控 Topic；Capability packet v9 按 Topic 提供源码派生的 Python-native 类型、docstring、生命周期、用法、禁用用法和通用 reference Hook。`query_hook_api` 支持 Topic、精确 symbol 和搜索词查询。
- Compiler 的 implementation revision 可从上一轮已提交 Candidate Workspace overlay 接续，保留 changed paths、实现摘要和已查询 API 标识，不再每次从 Accepted Parent 重新探索。

### 2.5 Evolution Controller、恢复与观测

- Controller 已采用不可变 Work Item、Effect Receipt、append-only `events.jsonl` 和纯 transition 组织路由，而不是一个固定 workflow 函数。
- 已实现 Incumbent Evaluation、研究、Trial、Distillation、Compilation、Candidate Validation、Conformance、Candidate Evaluation、Candidate Review、Promotion/Rejection 的路由及 evidence/mechanism/implementation 局部回流。
- Run 的 Generation、Trial、Assignment、各类 revision、Work retry、Work item 和总 token 均有显式预算；每个 Teacher Role 还有独立 `max_tokens`、`max_turns`。
- 非敏感运行参数已迁移到 UTF-8 `config/runtime.yaml`，`.env` 只承担 API 凭据；新 Run 会把控制与 Effect 配置冻结到 `run.json`，Resume 不受全局配置后续修改影响。
- 角色耗尽回合或结构化输出失败时会持久化失败 transcript、工具调用、usage 和 finish reason；Control Journal 只保存 artifact 引用。Conformance replay 和单条 Finding 使用内容摘要 checkpoint，重试只补做未完成项。
- Controller 已自动挂载新格式 Timeline 投影，在 Run 内生成 `timeline/state.json`、`entries.jsonl` 和 `summaries.jsonl`；确定性事件身份与来源关系不由概要模型决定。
- `experiments.clone_run_from_incumbent` 已能从一个完整 Incumbent Evaluation 创建新 Run，同时创建独立 Version Store、复制 Accepted 历史并重新生成 Run/Work 身份；复用的基线工作在新 Run 中计费为 0。

## 3. 核心改动归纳

### 3.1 从版本并存转为单一活动架构

V1 可执行代码、模板、测试和入口已经从主分支活动路径移除，历史文档集中在 `docs/archive/`，最终可运行版本由 `archive/v1-final` 保存。主分支不再维持 V1 兼容入口，当前代码和新产物统一采用新格式。

### 3.2 从角色专用基础设施转为共享 Framework

原先分散在 `core`、`registry`、`models` 和 `teacher` 的运行、装配与模型能力被收敛到 `framework` 与 `integrations`。Student/Teacher 的差异由 Template、Model Configuration 和上层 Role Runner 表达，不再通过两套 Manifest、Loader 和 Assembly 表达。

### 3.3 从固定流程转为事件驱动 Controller

Evolution 的决策与副作用已经分离：Effect 执行外部调用并落盘结果，transition 只根据已持久化 outcome 安排下一项工作。由此获得 Work 级重试、Resume、局部 checkpoint、预算控制和按失败层级回流，同时避免将全部角色顺序写死在单一函数中。

### 3.4 从自由文本工具协议转为原生 structured tool calling

普通 Teacher Role 和 Intervention Executor 都使用 API 原生 `tools`/`tool_calls`。这项改动消除了 Intervention 文本解析中 DSML/JSON 边界漂移的主要来源，并保留跨 phase session、严格单一动作语义和完整审计 transcript。

### 3.5 从“提示词描述机制”转为可编译契约

研究链路已把单条 Trial 事实、跨案例覆盖、逐 phase guard、三值 predicate、fallback、runtime input Topic 和 Candidate API packet 分层。Compiler 不再负责自行寻找全部接口或重新发明机制语义，而是在受控 Workspace 中实现冻结 Mechanism Spec。

### 3.6 从全量轨迹灌入转为面向职责的视图

Intervention 使用数字 Editable Context Block；Conformance 使用保留问题、工具证据、解析动作、Hook 判定、Hook change、状态和最终结果的 trajectory view，删除重复 model input、reasoning、usage 和无关事件。失败和重试产物也改为可复用 checkpoint，降低重复 API 调用和上下文膨胀。

## 4. 当前实验结果

### 4.1 主要 Evolution Run

| Run | 已到达阶段 | 实际结果 |
| --- | --- | --- |
| `20260803_qwen3-8b` | Evidence Review | 50 个 Example、每题 3 次 rollout；基线准确率 `0.72`。Evidence Reviewer 在 20 回合内未形成合法结构化输出，Work 重试后 Run 暂停。该案例直接推动了角色独立预算、失败 artifact 和长度校验补强。 |
| `20260804_qwen3-8b` | Mechanism Distillation | 基线报告的 scored accuracy 为 `0.7583`，但 150 条中有 30 条 unresolved。5 条同方向 Trial 后 Evidence Reviewer 给出 `ready_to_distill`，Distiller 因缺少正确不干预的负例要求补证据；Trial 预算已耗尽，Run 终止。 |
| `20260804_qwen3-8b_budget_fix` | Conformance | 基线准确率 `0.7067`。仅 1 条 Trial 即进入 Distillation；4 次 Compiler/Stage/Conformance 均未得到可接受实现，候选全部拒绝。它证明预算与回流能运行，也暴露了单案例证据仍可能被上游接受的问题。 |
| `20260804_qwen3-8b_02` | Conformance | 75 个 Example、225 条 rollout，基线准确率 `0.7022`。6 条 Trial 后形成两 phase 机制；4 次 Candidate 尝试均在 Conformance 被拒，未进入 Candidate Evaluation。主要问题是 Hook-model evaluator 与冻结语义边界不稳定，而非模板静态校验失败。 |
| `20260806_qwen3-8b` | Candidate Review 与 Promotion Gate | 首次完整走到 Candidate Evaluation。Incumbent 为 `158/224 = 0.7054`，Candidate 为 `160/225 = 0.7111`，表面增量约 `+0.0058`；但稳定正确 `45→42`、不稳定 `16→20`，总 token `558,474→3,114,949`，比率 `5.58×`。Conformance 的 3 条 Finding 均为 faithful，但 Candidate Reviewer 因回归和成本拒绝，Promotion Gate 也因超过 `3.0×` 成本上限拒绝。 |
| `20260807_qwen3-8b` | Compiler/Conformance 修订 | 75 个 Example、225 条 rollout，基线准确率 `0.6622`。3 条 Trial 后蒸馏并进行 6 次 Compile/Stage、2 次 Conformance；最终在 Compiler revision 预算耗尽后以 Candidate Validation 失败结束，没有 Candidate Evaluation。 |
| `20260807_debug` | 第二个 Research Attempt | 复用 `20260807_qwen3-8b` 的完整 Incumbent Evaluation，并使用独立 Version Store。80 个 Work Item 用尽前完成 20 条 Trial、20 次 Evidence Review、3 次 Compile/Stage 和 2 次 Conformance；候选从 `6 faithful / 9 mismatch` 改善到 `11 faithful / 4 mismatch`，仍因 evaluator mismatch 被拒，随后新研究方向再次进入证据循环。 |
| `20260807_debug2` | Evidence Review | 同样复用基线；80 个 Work Item 中包含 24 条 Trial 和 24 次 Evidence Review，未进入 Distillation。多个 Hypothesis 修订反复得到足够正例但只有 1 个 distinct negative Example，最终因 Work Item 预算暂停。 |

### 4.2 已验证的正向效果

- 完整闭环可实际运行到 Candidate Review，候选的代码修改、校验、Conformance、同口径 Evaluation、成本门禁和拒绝均有真实产物支撑。
- Intervention 的原生 structured tool calling 在同一改写任务的 3 次并行真实 API 验证中均完成目标块替换，修复了此前 DSML/JSON 文本协议的不稳定来源。
- `20260806_qwen3-8b` 中候选确实在部分 bridge question 上触发额外检索并修复回答；Candidate Reviewer 能同时识别这些收益、相邻问题回归和显著成本增长，没有因 Conformance 通过而直接接受。
- Compiler workspace 接续已在真实 Compiler–Conformance 定点实验中工作：Compiler 能在上一版 Candidate 上继续修改并通过静态 Candidate Validation，而不是重新生成全部实现。
- Incumbent clone 已通过真实 smoke test 创建独立 Version Store，Accepted Template digest 与源一致，且源 Store 不受新 Candidate 生命周期影响。

### 4.3 当前效果边界

- 截至上述实验，没有 Candidate 被晋升；所有相关 Version Store 的 Accepted Template 仍是 `harness_v0001`。
- 当前最强候选只获得约 `+0.58` 个百分点的表面准确率增量，同时稳定性下降且 token 成本增至 `5.58×`，不能视为有效改进。
- Hook-model evaluator 对相同语义边界仍会出现标签漂移。`20260807_debug` 的实现修订提高了 faithful 数量但没有消除 evaluator mismatch；Compiler–Conformance 定点复验也出现同一修订在 3 个 replay 中得到不同判断的现象。
- 当前 Evidence 流程在“正例已满足、distinct negative 不足、Trial/Work 预算耗尽”的组合状态下会反复要求缩小或修订 Hypothesis；`20260807_debug2` 已实证该循环会消耗大量 Work Item，而不会产生更多不同负例。
- Conformance 的模型成本仍高。轨迹视图和 checkpoint 已减少重复输入与失败重跑，但角色仍需对多个 Candidate replay 逐条做语义判断，近期实验中仍是主要 Teacher token 消耗来源之一。

## 5. 代码与产物入口

- 当前架构：[系统上下文](../architecture/system-overview.md)、[Agent/Harness Framework](../architecture/agent-harness-framework.md)、[Evolution](../architecture/evolution.md)
- 当前协议：[Teacher Role Contracts](../reference/role-contracts.md)、[Artifact Schemas](../reference/artifact-schemas.md)
- 当前角色静态审计：[Teacher Roles 代码分析](teacher_roles_current_code_audit.md)
- 运行方式：[运行 Evolution Experiment](../guides/run-evolution.md)
- 核心实现：`search_harness/framework/`、`search_harness/evolution/control/`、`search_harness/evolution/research/`、`search_harness/evolution/versioning/`
- 正式模板：`harness_templates/student/baseline/`、`harness_templates/teacher/<role_id>/`
- 实验产物：`runs/evolution/20260803_qwen3-8b` 至 `runs/evolution/20260807_debug2`

## 6. 当前验证状态

使用指定 Conda Python 执行 `python -m unittest discover -s tests -t .`，共发现 281 项测试，其中 280 项通过。唯一错误是已排除在当前架构范围之外的旧 `tests.visualizer.test_trace_store` 仍导入已删除的 `search_harness.versioning`；当前 Evolution Observer、Framework、Evaluation、Evolution Research/Control/Versioning 及 Integration 测试均已执行通过。本次交接没有修改该旧 Visualizer 实现或测试。
