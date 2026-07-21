# Hook 上下文生命周期与学生模型提示实验

## 1. 研究问题

本文回答三个问题：

1. 一次 Hook 对 `ModelInput` 的修改能否自动跨主循环轮次存在。
2. 放宽 system prompt，并提示学生模型听从后续 user 消息，是否能提高 Hook 指导的执行效果。
3. 在 Hook 不直接调用工具、也不嵌套 `AgentLoop` 的前提下，如何让 Hook 借用主 Agent 完成工具调用并恢复正常上下文。

实验使用 `STUDENT_MODEL_ID=qwen3:8b` 的真实 Ollama API。原始 artifact、正式 content、原生 reasoning 和 usage 均保存在 `adapter_logs/`。

## 2. 单次 ModelInput 修改是否跨轮

### 2.1 结论

**不会自动跨轮存在。**

当前每一轮的顺序是：

1. `pre_prompt`；
2. PromptBuilder 根据 `AgentState` 新建 `ModelInput`；
3. `post_prompt` 可替换本轮 `stage.model_input`；
4. 修改后的输入被记录到 `state.model_inputs` 并发送给模型；
5. 下一轮重新从 PromptBuilder 开始。

baseline 的 `SimplePromptBuilder` 只读取：

- 固定 system prompt；
- `state.question`；
- `state.conversation_messages`。

它不读取 `state.model_inputs`。因此，某轮临时追加到 `stage.model_input` 的消息只对该次模型生成有效。Loop 记录这份输入是为了 trace 和调试，不代表它会成为下一轮上下文来源。

### 2.2 哪些内容会跨轮

当前有三类持久路径：

1. `conversation_messages`：工具分支会把 Actor 原始输出和工具结果追加进去；无效格式分支也会追加原始输出与纠错消息。
2. `extension.*` / `shared.*`：在同一 rollout 内跨 Hook、跨阶段、跨轮保存。
3. 外部固定资源：prompt 模板、manifest 和工具定义在 rollout 装配时存在，但不会由单次 Hook 临时修改。

Hook 不能直接写 `core.*` 或 `conversation_messages`。如果希望一条临时指导在多轮持续生效，应把策略状态写入 `extension/shared`，并在每次 `post_prompt` 根据状态重新构造本轮 `ModelInput`。

### 2.3 验证测试

在 `tests/core/test_hooks.py` 增加两条测试：

- `test_model_input_rewrite_is_ephemeral_without_reinjection`：第一轮追加 `ephemeral context`，第二轮确认该消息消失。
- `test_hooks_bridge_context_across_rounds_through_shared_state`：`post_tool` 把结果写入 `shared.next_model_context`，下一轮 `post_prompt` 读取并注入，确认跨位置联动成立。

两条测试及该文件全部 9 项测试通过。

### 2.4 对上下文管理的含义

临时性不是缺陷，反而适合精确上下文控制：

- Hook 可以为某一步构造任务专用上下文，不污染后续轮次。
- 持久策略与模型可见文本分离：状态保存“为什么和何时注入”，`ModelInput` 只保存“这一轮看什么”。
- 多 Hook 可通过 typed shared state 联动，而不需要互相修改内部字段。
- 每轮重新投影使上下文压缩、角色替换、隐藏旧消息和恢复默认视图都可审计。

但“恢复上下文”只影响未来发送给模型的投影。已经发生的模型输出、工具调用和工具结果仍保存在 `AgentState` 与 trace 中，不应被删除。

## 3. STUDENT system prompt 对照实验

### 3.1 实验一：策略层优先级

入口：

```powershell
python -m experiments.student_system_prompt_probe \
  --output-file adapter_logs\student_system_prompt_probe_20260716.json \
  --repeats 3
```

三种 system 条件：

- `rigid`：要求每次检索后必须再次检索，并声明 user 只能提供观察。
- `baseline`：证据不足时检索，一次一个工具调用。
- `user_adaptive`：system 固定协议和默认策略，后续 user 可提供当前状态控制，但不能破坏 action schema。

六类案例包括充分证据、空检索、实体消歧、多跳充分证据、部分证据和 user 要求破坏标签协议。每类重复 3 次，共 54 次真实生成，使用 16,357 tokens。

结果：

| 条件 | schema | 决策 | 内容 | 联合成功 |
|---|---:|---:|---:|---:|
| rigid | 15/18 | 15/18 | 15/18 | 15/18 |
| baseline | 15/18 | 15/18 | 15/18 | 15/18 |
| user_adaptive | 15/18 | 15/18 | 15/18 | 15/18 |

三个条件在五个正常策略案例上均为 15/15。`rigid` 并没有迫使模型执行额外搜索：当 user 明确说证据充分时，模型仍直接回答。

三种条件在 `protocol_conflict` 上均为 0/3：user 要求普通文本后，模型都丢弃 `<final_answer>` 标签。这表明该模型在本实验中不是过度服从 system，而是对最近 user 指令相当敏感。单纯增加“听从 user”不会改善策略，反而需要防止 user/Hook 文本意外覆盖协议。

### 3.2 实验二：真实 Hook 指导形态

入口：

```powershell
python -m experiments.student_hook_guidance_probe \
  --output-file adapter_logs\student_hook_guidance_probe_20260716.json \
  --repeats 5
```

模型看到完整多轮结构：原始问题、assistant 工具调用、user 工具结果，以及 Hook 追加的 user 指导。指导要求先用 `Summary:` 概括，再给出工具调用或答案。

三种 system 条件：

- `action_only`：只允许 action block，禁止任何块外文本。
- `baseline`：允许 action 前 reasoning。
- `hook_adaptive`：明确说明后续 user 可能来自 Hook，应在保留 action schema 时遵循。

三类案例各重复 5 次，共 45 次生成，使用 17,744 tokens。

| 条件 | schema | action 正确 | 摘要遵循 | 联合成功 |
|---|---:|---:|---:|---:|
| action_only | 13/15 | 13/15 | 15/15 | 13/15 |
| baseline | 15/15 | 15/15 | 15/15 | 15/15 |
| hook_adaptive | 15/15 | 15/15 | 15/15 | 15/15 |

`action_only` 中的两次失败都发生在“概括后回答”：模型服从 user 输出了摘要和答案，却漏掉 `<final_answer>`。这不是 system 服从过强，而是互相冲突的强指令降低了格式稳定性。

`baseline` 与 `hook_adaptive` 无差异，说明当前 baseline 中“允许 reasoning 位于 action block 前”已经足以承载该类 Hook 指导。继续泛化地强调“服从 user”没有可测收益。

### 3.3 问答结论

**适当放宽过度排他的 system prompt 有帮助，但不应把 user 提升为无条件权威。**

推荐分层：

- system 固定不可破坏的不变量：角色、可用工具、一次一个 action、标签 schema。
- system 给出默认而非绝对的任务策略：证据不足检索、充分时回答。
- user/Hook 提供当前 rollout 的观察、局部目标和一次性控制。
- Hook 文本不要出现“忽略以上规则”“只输出普通文本”等可能覆盖协议的措辞。

对当前 baseline，无需仅为了“让模型听 Hook”继续放宽 system。更值得做的是让 Hook 指导短、位置靠后、目标具体，并在 parser 层保留格式恢复。

## 4. Hook 委托主 Agent 调用工具

### 4.1 目标和边界

目标是让 Hook 或 Hook 内的小模型提出工具需求，但工具仍由现有主循环执行：

- 不在 Hook 内创建 `AgentLoop`；
- 不在 Hook 内直接调用 `ToolRuntime`；
- 不递归进入当前 loop；
- 不隐藏工具调用与结果；
- 允许多占用主循环轮次和 token；
- 每次委托仍有明确终止预算。

这可以称为 **tool delegation through the main loop**，而不是 Hook tool runtime。

### 4.2 状态机

建议用一个 typed shared state 表示委托事务：

```text
IDLE
  -> REQUESTED
  -> AWAITING_ACTOR_TOOL_CALL
  -> AWAITING_TOOL_RESULT
  -> RESULT_READY
  -> RESUMING
  -> IDLE

任一阶段 -> FAILED
```

状态至少记录：

- `request_id`：区分同一 rollout 中多次委托；
- `requester_hook_id`；
- `tool_name` 和期望参数；
- `purpose`；
- `status`；
- `actor_attempts` / `max_actor_attempts`；
- `delegation_count` / `max_delegations`；
- `tool_call`、`tool_result` 或失败原因；
- `resume_context_policy`；
- 可选的原始 `ModelInput` 投影或消息选择策略。

### 4.3 生命周期协作

1. **提出请求**：Hook 或 Hook 小模型在某次 invocation 中判断需要工具，把事务写为 `REQUESTED`。
2. **构造控制帧**：同次或下一次 `post_prompt` 临时替换 `stage.model_input`，要求 Actor 执行一个明确工具调用。控制帧只影响当前生成，不会污染后续轮次。
3. **检查 Actor 决策**：`post_parse` 判断是否得到工具调用。若 Actor 回答或格式错误，可写反馈状态并在下一轮重试，不递归调用。
4. **规范工具调用**：`pre_tool` 验证工具名和参数。对于明确的计划参数，可做确定性归一化，防止 Actor 改变委托意图。
5. **接收结果**：`post_tool` 把完整 `ToolResult` 写入事务，标记 `RESULT_READY`。核心仍按正常路径把调用和结果加入 conversation 与 trace。
6. **恢复并消费**：下一轮 `post_prompt` 不再注入工具控制帧，而是按 `resume_context_policy` 构造正常 Actor 输入，并追加简短的委托结果或 Hook 小模型根据结果产生的 guidance。
7. **结束事务**：结果被注入后标记 `IDLE` 或保存为 `CONSUMED` 审计记录。

### 4.4 Hook 小模型如何间接使用工具

若请求来自 Hook 内小模型，可以把过程拆成两个独立 invocation：

1. 第一次 Hook 模型调用输出结构化 `need_tool` 意图；
2. 主 Actor 在后续 loop step 执行工具；
3. `post_tool` 保存结果；
4. 下一次 Hook invocation 再调用小模型，把工具结果作为新输入，得到最终 guidance；
5. guidance 注入主 Actor。

每次 Hook invocation 仍只有一次模型生成，工具调用发生在两次 invocation 之间，不存在嵌套 loop 或递归栈。

### 4.5 恢复上下文的准确含义

控制帧是临时 `ModelInput`，下一轮天然消失。需要恢复的是消息投影和角色任务，而不是删除历史：

- 保留原始 question、必要证据和实际工具结果；
- 隐藏仅用于驱动工具的冗余控制文本；
- 可压缩 Actor 的委托工具调用为一句审计摘要；
- trace 始终保留原始控制输入、Actor 输出和工具结果。

如果直接从旧 `ModelInput` snapshot 恢复，可能漏掉委托期间新增的真实结果。更稳妥的是保存 `resume_context_policy`，在恢复阶段从最新 `AgentState` 重新投影。

### 4.6 失败和终止

虽然当前不把 token 成本作为主要约束，也不能取消终止边界：

- Actor 连续不执行指定工具时，最多重试若干次后转 `FAILED`；
- 工具错误不自动递归重试；
- 同一 request 不允许在 `post_tool` 再创建自身 request；
- 每条 rollout 限制委托事务数量；
- `request_id` 防止旧结果被新请求消费；
- 达到主 loop `max_steps` 时保留未完成事务和失败原因。

Actor 的默认 `MAX_AGENT_ITERS` 已从 10 放宽到 30，为委托控制帧、工具执行、Hook 结果消费和格式恢复留出空间。该值是总保险丝，事务仍应有更小的局部预算。

### 4.7 当前 MVP 实现与验证

基线 plugins 已提供默认禁用的 `tool_delegation` extension。它以固定的工具名、参数与请求文本演示一笔最小委托事务：

1. 初次 `post_prompt` 注入临时 user 控制帧，并将自身状态从 `requested` 写为 `awaiting_tool_result`；
2. `pre_tool` 将 Actor 已生成的调用规范为 manifest 中声明的固定工具与参数；
3. 主 `AgentLoop` 仍按正常路径执行 `ToolRuntime`，并保留调用及结果；
4. `post_tool` 保存结果，标为 `result_ready`；
5. 下一轮 `post_prompt` 注入结果已可用的恢复提示并标为 `completed`，不重复注入控制帧。

`tests/core/test_hooks.py` 的确定性测试验证了上述路径：控制帧仅影响第一轮、Actor 的错误参数被归一、工具由主 loop 执行、结果在下一轮恢复，并且事务最终完成。该 MVP 尚未处理 Actor 不调用工具、直接回答、工具失败或局部重试；这些分支应在 `post_parse` 状态机扩展后再接入。

使用本地 STUDENT `qwen3:8b` 的三条真实 rollout 也完成了该路径，输出位于 `traces/student_tool_delegation_probe_3.jsonl`，实验 harness 位于 `harnesses/experiments/tool_delegation_student/plugins/`：三条均只收到一次控制帧和一次恢复帧，均成功保存委托结果并以 `completed` 结束。三次模型都生成了与原问题相关的 `search` query，而 `pre_tool` 均将其归一为固定 `delegated evidence query`。这验证真实模型可执行控制帧和框架可接管参数；同时也证明固定 query 的示例只能验证控制流，不能用于评估任务正确性或作为实际策略。

### 4.8 当前是否需要修改 core

上述协作可以由现有阶段、typed shared state 和临时 `ModelInput` 完成，MVP 不需要修改 core。真正需要新增的是插件层的委托协议与一组协作 Hook。

只有出现以下需求时才应扩 core：

- Actor 必须被跳过，由调度器确定性地直接提交工具调用；
- 一个步骤需要多个并发工具；
- 需要暂停、恢复或分叉完整 loop snapshot；
- 需要工具调用不进入 Actor conversation；
- 需要事务级回滚外部工具副作用。

## 5. 后续实验

1. 验证 Actor 不遵循、输出 final answer、输出错误工具、工具失败和达到步数上限等分支。
2. 再把 Hook 内 STUDENT 接到 `need_tool -> result -> guidance` 两次 invocation 流程。
3. 比较普通 Actor、直接小模型 Hook、委托工具 Hook 三种轨迹的正确率和错误类型；token 只记录，不作为当前接受门槛。
4. 若多轮控制帧导致 Actor 角色漂移，再研究更严格的恢复投影和对话压缩。
