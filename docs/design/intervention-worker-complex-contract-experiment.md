# Intervention Worker 复杂 Role Contract 实验计划

## 实验目的

本实验只评估关闭 thinking 的 Intervention Worker 是否能够理解并忠实执行复杂
`InterventionHypothesis + Assignment`。不以 Student 最终准确率作为 Worker 通过条件，也不在
实验中修改 Worker Prompt、工具、源 rollout 或中间产物。若实验暴露协议或能力缺口，先保留
失败证据并结束对应实验组，再另行决定是否修改实现。

Teacher 使用正式 `intervention_worker` 配置，`thinking_mode=disabled`；Student 使用正式
本地模型配置。相同输入独立执行三次。原始 artifact、紧凑判定和 token/请求统计写入
`runs/experiments/20260816_intervention_complex_contract/`。

## 评估口径

每次 Trial 分别记录：

1. **理解正确性**：Worker 对 activation condition 的判断是否与当前可见证据一致。
2. **动作忠实性**：终态工具、修改目标和具体值是否与冻结 instruction 一致。
3. **字段忠实性**：修改后实际进入下一环节的语义字段是否正确，未授权字段和 metadata 是否
   保持不变。
4. **事务因果性**：Stage Patch 是否发生在 live transaction，并直接成为 parser、Tool
   Executor 或下一次 generation 的输入；不把 Student 独立重生成的巧合计为成功。
5. **状态一致性**：Trial state 是否按写入值跨 activation 可见、按条件更新，且不进入
   Student Model Input。
6. **负向控制**：条件不成立时是否选择 `continue_without_change`，而不是为了执行计划强行
   修改。
7. **模型负担**：Teacher 请求次数、工具调用序列、输入/输出 token、无效重复检查和工具错误。

单次结果分为 `pass`、`fail`、`unsupported`：`unsupported` 表示 role contract 请求了当前
工具面没有声明的字段或动作，不与 Worker 理解失败混淆。一个测试单元三次均为 `pass` 才称为
稳定；两次通过记为有波动；其余记为不稳定。

## 字段覆盖边界

底层 artifact 保留完整阶段对象；Worker 只接收语义投影。第一组同时审计“底层 phase 字段”
和“当前可编辑投影”，避免把隐藏 metadata 当成 Teacher 应填写内容。

| Hook phase | 底层活动字段 | 当前 Worker 可读/可改语义 | 验证责任 |
| --- | --- | --- | --- |
| `post_prompt` | `model_input` | 读取既有块 role/content；替换或删除既有 content；插入带指定 role/content 的新块 | 三类操作进入本次模型调用，其他消息不变；既有 role 不宣称可改 |
| `post_model` | `raw_model_output` | `content` | 替换文本直接进入 parser |
| `post_parse` | `parser_input`、`parsed_output` | `parsed_output.kind` 及对应 `tool_call`、`final_answer`、`error` | 分别覆盖三种 union 分支；`parser_input` 当前不可编辑，`inband_thinking` 隐藏且由程序保留 |
| `pre_tool` | `tool_call` | `name`、`arguments` | 读取工具名并改参数，实际 Tool Executor 执行修改值 |
| `post_tool` | `tool_call`、`tool_result` | Tool Result 的 `name` 只读、`content` 可改 | 下一 generation 看到修改内容，runtime metadata 保留；活动 `tool_call` 不宣称可改 |
| `pre_final` | `final_decision` | `action=defer/accept` 与相应 `feedback/answer` | 分别覆盖 defer 和保留当前答案的 accept |

`pre_prompt`、`on_error` 不在当前 `InterventionHypothesis.HookPhaseName` 中，不属于本次“可选
phase”。若第一组确认上述不可编辑字段阻碍常见干预表达，只在报告中记录能力缺口，本轮不扩展
工具面。

## 第一组：单 Phase 字段实验

每个测试单元只包含一个实际干预 phase；`post_model`、`post_parse`、`pre_tool` 从更早的
`post_prompt` retained prefix 恢复，以保证修改发生在 live transaction。计划单元如下：

1. `post_prompt/context_operations`：一次原子 patch 同时 replace、insert、delete 三类消息操作。
2. `post_model/raw_output`：把 live raw output 改为一条确定的合法 Tool Call。
3. `post_parse/tool_call`：把 ParsedOutput 的 `kind/tool_call.name/tool_call.arguments` 一并改写。
4. `post_parse/tool_call_to_final`：把 live Tool Call ParsedOutput 改为非金标固定 sentinel，
   验证 union 切换。
5. `post_parse/existing_final_answer`：从 routed-adaptive 的真实 synthesis `post_prompt` 恢复，
   读取 live final-answer ParsedOutput 并在原值后追加 sentinel，验证 `final_answer` 字段读取与修改。
6. `post_parse/invalid`：把 ParsedOutput 改为 `kind=invalid,error=<固定诊断>`，验证错误分支对象
   恢复；预期 Agent Loop 进入现有 invalid/error 路径，不要求完成答案。
   正常 rollout 没有原生 invalid 分支，因此本项只证明构造/恢复 error union，不宣称读取过历史
   invalid 值。
7. `pre_tool/tool_call`：保留有效工具名并修改完整 arguments；工具名只有 `search` 可合法执行，
   因此验证“正确读取并保留 name”，不制造不存在的工具。
8. `post_tool/tool_result`：在 live `post_tool` 读取 name/content，只替换 content；验证 metadata 没有交给 Worker 也
   没有丢失。
9. `pre_final/defer`：基于 live 当前候选和历史证据 defer，验证反馈进入下一 generation。
10. `pre_final/accept`：接受 live 当前 Student 候选原文，验证 Worker 不改写答案。

每单元执行三次，共 30 次 Trial。成功标准由 trace 的真实 before/after、紧随其后的 parser/
tool/model 事件确定，不采用 Worker 自述。

## 第二组：随机多 Phase 联动

使用固定 seed 从可行组合集中抽取三个组合，选择结果在运行前写入实验 manifest；随机性只用于
组合选择，不改变每个组合的冻结 contract。

候选组合覆盖不同依赖形态：

- context → action：`post_prompt → pre_tool`；
- observation → state → final control：`post_tool → pre_final`；
- raw/parsed action → result rewrite → later control：`post_model/post_parse → post_tool → pre_final`；
- state-conditioned repeated retrieval：`pre_tool → post_tool → pre_tool`，同一 phase 通过
  `max_activations` 重复激活。

抽取 2–3 个组合，每个执行三次。每份 contract 必须明确 state key 的职责：

- `route`：记录本 Trial 选择的干预路径，不携带答案事实；
- `status`：记录阶段进度，例如 `awaiting_result` 或 `ready_to_synthesize`；
- `search_count`：记录已观察的目标检索次数；
- `evidence_gap`：记录早期 observation，后续 phase 必须重新检查其是否仍成立。

Trial state 最多 16 个 key、序列化后最多 4096 字符；`evidence_summary` 只能保存短摘要，
不得复制原始检索结果。

验证 state 不进入 Student 输入，后续动作同时依据 state 和当前可见证据；若当前证据已经修复
早期缺口，Worker 应更新/忽略旧状态并选择不干预。

## 第三组：Routed Adaptive Decomposition 模拟

参考 `experiments/as_you_can/final_template_routed_adaptive`，只复现其行为思路，不复制实现代码：

1. 先区分直接委托与需要 bridge decomposition 的问题；
2. 对 decomposition 路径维护 `route/status/search_count/evidence_summary`；
3. 将当前 evidence obligation 投影为 Student-visible retrieval instruction；
4. 在 `pre_tool` 保证待执行 query 与当前 obligation 一致；
5. 在 `post_tool` 读取实际结果、更新状态并形成下一 obligation；
6. 证据充分时允许 synthesis；若 Student 过早 final，则在 `pre_final` defer。

复杂 contract 使用 3–4 个 phase directive、每 phase 至多两次 activation，不要求 Worker
模拟 Question Router 或 Hook Model 的隐式推理过程。所有 route、obligation 和状态值必须来自
问题文本与 Worker 实际读取的 Student-visible evidence；不得写入金标答案。

优先从现有
`experiments/as_you_can/artifacts/benchmarks/train24_v11_routed_adaptive/rollouts.jsonl`
选择一条真实进入 decomposition、完成至少两次检索且保留完整 phase trace 的样本。Student
Template 使用 `final_template_routed_adaptive`；若 retained prefix 与该 Template 的私有 Hook
State 无法忠实恢复，则改用同一 rollout 作为只读设计证据、在 baseline Template 上执行等价
Intervention contract，并将此限制记录为基础设施边界，不伪造原 Hook State。

该复杂 contract 独立执行三次。通过条件是 route、两次 retrieval obligation、state 更新和
最终控制的因果链均与 contract 一致；最终答案正确与否单独记录。

## Terra 子智能体任务

计划冻结后调用 Terra，职责限定为：

1. 只读审阅上述矩阵是否遗漏 phase 字段或把不可恢复源事务当作 live edit；
2. 从 routed-adaptive rollout 中选择第三组候选样本并说明选择依据；
3. 独立提出第三组复杂 contract 的 phase/state 设计和可观察判据；
4. 在主 Agent 完成实验脚本后，复核原始 artifact 与紧凑结果是否一致。

Terra 不修改正式 Worker Prompt、工具或源 artifact。主 Agent 负责最终 contract、脚本、真实调用
和实验结论。

## Fail-fast 条件

出现下列任一情况时停止受影响实验组，不在同轮修补：

- phase 恢复点不能形成真实 live transaction；
- role contract 请求当前工具面未声明的能力；
- Teacher API 或 Student runtime 连续失败，无法区分模型行为与基础设施故障；
- 源 rollout 与所用 Student Template 身份不一致；
- 为获得通过结果必须修改冻结 instruction、activation condition 或中间 artifact。
