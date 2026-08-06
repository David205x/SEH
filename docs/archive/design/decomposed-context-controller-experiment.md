# 分解上下文 Controller Hook 实验

## 目标

验证一个带 STUDENT Hook 模型和有限状态机的 extension，能否把主 Actor 的每次生成强制投影为当前检索子任务，完成有限次检索后再进入独立的综合上下文。该 Hook 不嵌套 AgentLoop，也不直接执行工具。

## Hook 设计清单

| 项 | 设计 |
| --- | --- |
| 实例 | `decomposed_context_controller`，baseline manifest 默认禁用，`mutable` |
| Hook 模型 | `student` profile；每条 rollout 在 `pre_prompt` 最多调用一次，用于生成 JSON 子任务计划 |
| 计划格式 | `{"subtasks":[{"task":"...","query":"..."}]}`，最多 2 项 |
| 状态 | `status`、`plan`、`index`、`evidence`、`planner_error`，均在 `extension.decomposed_context_controller.*` 下声明并可追踪 |
| 状态机 | `unplanned -> subtask_pending -> awaiting_tool -> subtask_pending/synthesis_pending -> awaiting_final -> completed` |
| 每步上下文 | `post_prompt` 完全替换 `stage.model_input`：子任务阶段仅含子任务 system + 原问题/当前 query；综合阶段仅含综合 system + 原问题/受限证据投影 |
| 主工具调用 | `pre_tool` 将当前 Actor 调用归一为计划中的 `search(query, topk)`；实际工具仍由主 `ToolRuntime` 串行执行 |
| 结果推进 | `post_tool` 记录完整结果，推进索引；最后一项后转入 synthesis |
| 最终收束 | synthesis 输入只允许 `<final_answer>`；`pre_final` 将状态标为 `completed` |
| 原始格式桥接 | 仅在 `awaiting_tool` 时，`post_parse` 将裸 `{"name":"search","arguments":...}` 转为 `ParsedOutput.tool_call`；原始输出与 Hook 修改均留在 trace |
| 规划降级 | planner 不能解析 JSON 时，将错误写入 `planner_error`，并使用原问题作为一个直接检索子任务；不让单次格式错误中断整个数据集批次 |
| 边界 | 不递归调用 loop、不直接调用 ToolRuntime、不修改 core state、不并发工具、不自动接受模型的任意工具动作 |

实现位于 `harnesses/baseline/plugins/extensions/decomposed_context_controller/`；三个 prompts 分别持久化于 `templates/planner.md`、`subtask_system.md` 与 `synthesis_system.md`。

## 初版观察

初版 controller 在 19 条已落盘轨迹中出现两个关键问题：

1. 5 条中，qwen3:8b 在强子任务 system 下反复输出裸 JSON 工具对象，例如 `{"name":"search","arguments":...}`，而 tagged parser 只能识别 `<tool_call>...</tool_call>`；模型每轮重复同一内容，最终达到 `MAX_AGENT_ITERS=30`，没有执行工具。
2. 3 条 planner 未返回 JSON object，导致 runner 记录 `planner output must contain a JSON object`。

这不是“上下文重设没有发生”，而是模型的实际工具协议与 parser 的应用协议不一致。它说明更强的 system 约束会改变模型输出表面，而不能单靠提示词保证 parser 兼容。

## 修复后 20 条 STUDENT 验证

修复为受限裸 JSON 桥接和 planner 直接检索降级后，使用相同前 20 条 `supported.jsonl`、本地 `qwen3:8b`、同一检索服务重跑：

| 指标 | 结果 |
| --- | ---: |
| 完成 rollout | 20/20 |
| runner / retriever 错误 | 0 / 0 |
| controller 状态 `completed` | 20/20 |
| Hook planner 调用 | 20 |
| planner 降级 | 1 |
| 裸 JSON 桥接 | 26 |
| 两次检索后综合 | 18 条 |
| 一次检索后综合 | 2 条（其中 1 条为 planner 降级） |
| 平均 Actor steps / 工具调用 | 2.95 / 1.90 |
| Teacher 评分正确数 | 18/20，准确率 0.90 |
| 总 token | 97,135，其中 Hook 19,531，Actor 77,604 |

与同一批次的 `question + user` 单委托基线比较：两者均为 18/20；18 条判定一致，双方各有 1 条独占正确。因此不能把该 controller 视为当前任务表现的提升。它的已验证收益是把“规划、子任务、工具结果、综合”变成独立且可审计的状态转换；成本是一次 Hook 模型调用、约两次检索以及对裸工具 JSON 的适配需求。

## 当前判断

该 Hook 是一个可工作的研究性 Harness 原语，不应默认替代单委托 baseline。较合适的后续方向是：由 Critic 只对多跳、检索不足或可明确分解的问题启用它，并让 Adapter 演化 planner prompt、子任务数和综合证据投影，而不是对每题无条件强制两次检索。
