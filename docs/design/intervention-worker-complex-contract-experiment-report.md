# Intervention Worker 复杂 Role Contract 实验报告

## 实验身份

- 计划：`docs/design/intervention-worker-complex-contract-experiment.md`
- Worker：正式 `intervention_worker@1`
- Teacher thinking：`disabled`
- 重复次数：每个冻结输入 3 次
- 原始产物：`runs/experiments/20260816_intervention_complex_contract/`
- 评判原则：以真实 trace、stage before/after、工具执行和 Trial state 为准，不以 Worker 自述或 Student 最终准确率代替设施验证。

## 计划冻结与预检

计划共包含 10 个单 phase 单元、固定 seed 抽取的 3 个多 phase 单元，以及 1 个 routed-adaptive 复杂单元。`InterventionWorkerInput` 协议校验、Python 编译、prefix 边界解析均已通过。

Terra 的只读预审促成了三项边界修正：补测 live `final_answer` 的读取与修改；不把 invalid 构造误称为读取历史 invalid；不声称 retained prefix 能恢复 routed-adaptive 扩展的私有 Hook State。第三组因此只复现外显的路由、obligation 与状态传递语义。

## 第一组：单 Phase 字段

已完成 10 个冻结单元、每单元 3 次，共 30 次。30/30 通过结构检查，进一步按原始 artifact 做 exact-value 审查后仍为 30/30 通过。

| 单元 | 结果 | 真实效果核对 |
| --- | --- | --- |
| `post_prompt/context_operations` | 3/3 | 同一原子 patch 完成 delete/insert/replace/insert；原 assistant action 原文恢复，result 仅追加标记，其余块不变 |
| `post_model/raw_output` | 3/3 | 指定 raw Tool Call 被 parser 解析并以指定 query/topk 执行 |
| `post_parse/tool_call` | 3/3 | `kind/name/arguments` 完整替换，Tool Executor 收到同值 |
| `post_parse/tool_call_to_final` | 3/3 | union 切换为固定 final，未执行 Tool Call |
| `post_parse/existing_final_answer` | 3/3 | 三次均读取 live `Mr. Burns`，形成 `Mr. Burns [POST_PARSE_FINAL_READ]` |
| `post_parse/invalid` | 3/3 | 构造 exact invalid/error，Agent Loop 产生正常 invalid feedback 后继续 |
| `pre_tool/tool_call` | 3/3 | 保留 `search`，指定 arguments 与真实执行值一致 |
| `post_tool/tool_result` | 3/3 | Worker 参数只提交 `content`，下一次 ModelInput 只看到替换内容；`name` 和 metadata 的保留来自实现路径保证，artifact 未单独持久化 patch 后的临时对象，不能称为实验 before/after 观测 |
| `pre_final/defer` | 3/3 | exact feedback 形成 `final_deferred`，随后发生新一轮生成 |
| `pre_final/accept` | 3/3 | 接受值与当次 live candidate 原文完全一致 |

Teacher artifact 均记录 `deepseek-v4-flash`、`thinking_mode=disabled`。本组共使用 221,664 Teacher token。最复杂的 context 原子操作固定需要 5 次请求；多数 stage patch 需要 2–3 次请求，说明关闭 thinking 后依然会通过显式 inspect 获取必要字段，但未出现工具参数错误或错误 phase。

这里的 30/30 严格指“当前 Worker 可见、可写的语义字段及其紧随的真实 lifecycle 效果”，不包含程序刻意隐藏的 parser input、in-band thinking 或 runtime metadata。`summary.json` 中的 `structural_pass` 也没有自动比较 exact value；表中结论来自对 30 份原始 artifact 的额外逐值复核。

## 第二组：多 Phase 联动

固定 seed 实际选择了 `context_action`、`observe_state_final`、`raw_result_final`。由于首轮执行在发现 `context_action` 三次均缺状态后被人工暂停，保留了原始中断目录；其余两项在独立目录按同一冻结输入完成三次。

| 组合 | 动作忠实性 | state 忠实性 | 结论 |
| --- | ---: | ---: | --- |
| `context_action` | 3/3 | 0/3 | post_prompt marker 与 pre_tool query 均正确，但 `route/status` 从未持久化；一次曾并行提交 state 与终态 patch，被 runtime 同时拒绝，重试后只保留 patch |
| `observe_state_final` | 3/3 | 不触发 | Worker 三次都读出首次结果已覆盖比较双方，故 post_tool 与 pre_final 均正确 `continue_without_change`；是稳定负向控制，不构成正向 state 传递证据 |
| `raw_result_final` | 3/3 | 2/3 | raw rewrite、result rewrite、final accept 均稳定；一次漏写首阶段 `route`，后续虽补齐其他状态，仍不算完整忠实 |

正向的“state 写入 + 终态动作 + 后续读取”样本合计只有 2/6 完整通过；另 4 次的终态动作正确但 state 不完整。已完整写入的 state 会出现在后续 Worker activation 的只读 observation 中，且检查的 state key 没有泄漏到 Student ModelInput。

直接原因不是跨 phase 存储失效，而是同一 activation 要先调用非终态 `update_trial_state`、再调用终态修改工具时，关闭 thinking 的 Worker 会省略前者，或在一次响应中并行发出两个工具。指令顺序也有明显影响：`context_action` 先写终态动作、后说“并设置 state”，稳定遗漏；`raw_result_final` 明确“先 set、再 replace”，达到 2/3。

## 第三组：Routed Adaptive 模拟

三次均完成完整外显控制链：`post_prompt → pre_tool(1) → post_tool(1) → pre_tool(2) → post_tool(2) → pre_final`；`route/status/search_count/planned_search_index/bridge_entity/evidence_summary` 在正确 activation 间传递，且未泄漏进 Student ModelInput。三次都从第一份实际检索结果提取出 `Otto Mann`，随后形成包含该 bridge entity 的第二次关系检索，最后按 contract 接受 live candidate。

机械控制骨架的忠实性为 3/3，但 routed-adaptive 的高层实验语义为 0/3：第二个 query 都在语义上指向“谁资助含 Otto Mann 的保龄球队”，实际结果却均不包含 `Mr. Burns`。Contract 只要求第二次检索完成后进入 `ready_to_synthesize`，没有要求 Worker 依据结果重新判定“直接关系证据是否存在”，所以 Worker 忠实地执行了一个证据门槛不足的 contract，三次最终答案都表示无法从现有证据确定资金方。这是 Researcher contract 的可操作定义不足，而不是 stage/state 工具失效；因此不能称为对 routed-adaptive 语义的成功复现。

三次 Teacher 用量分别为 97,261、106,597、114,564 token，共 318,422 token；请求数为 18、19、20。第 1、3 次各出现两次多工具同响应，被 runtime 拒绝后恢复。持久 session 会反复携带先前检索内容和工具结果，复杂 phase 链的 token 成本增长明显。

## 综合结论

Terra 已完成最终只读复核，结论与逐值审查一致。按冻结矩阵计，本次产生 42 份正式 Trial artifact，共 721,883 Teacher token、201 次 Teacher 请求。人工暂停时还完成过一份随后在正式三次中重跑的负向控制，实际 API 总消耗因此为 43 份、739,282 token、206 次请求；该重复项不计入通过率。

1. **单 phase 能力稳定。** 关闭 thinking 时，Worker 能稳定读取当前投影、选择正确原生工具，并把复杂 context patch 或 stage patch 精确送入真实 lifecycle。六类 Hook phase 的当前可写语义面均有三次直接证据。
2. **跨 phase state 本身可用，但“state + terminal action”不稳定。** 一旦 state 成功写入，后续 activation 能稳定读取，且不会泄漏到 Student；不稳定发生在同一次 activation 需要先写 state、再提交终态修改时。正向多 phase 小组合中完整 state 链只有 2/6。
3. **Role contract 的动作顺序显著影响关闭 thinking 的表现。** “先 set state，再 patch”的明确顺序明显优于把 state 要求放在终态动作之后；即便如此，模型仍可能在同一响应并行发出两个工具，依赖 runtime 拒绝和重试恢复。
4. **复杂控制骨架可执行，不等于机制语义成立。** 第三组证明了 bridge、两次检索、变量传递和 final control 可以 3/3 连通；但错误地以 `search_count=2` 代替“关系证据已满足”，让无效检索也进入 synthesis。这是 Researcher 必须给出可操作 evidence predicate 的直接证据。
5. **复杂持久会话成本很高。** 第三组平均约 19 次请求、106,141 token。多工具重试、反复 inspect，以及完整检索结果随持久 Worker session 累积共同放大输入。关闭 thinking 降低了隐式推理输出，却没有消除复杂工具编排和上下文增长成本。

因此，当前设计已足以把 Intervention Worker 用作“外显、分阶段的 Hook 行为实验器”，但还不能把任意自然语言复杂 contract 视为稳定可执行程序。优先事项不是增加更多 phase，而是：要求 Researcher 把每个 activation 写成明确的 `inspect → update state → terminal action` 顺序；把“证据充分”定义为对当前结果的可观察谓词；并评估是否需要让 state 更新与终态动作具备一次原子提交形式。

## 后续 Prompt 补强

根据第二组失败，正式 Intervention Worker Prompt 已明确：每个 assistant 响应只允许一个 native tool call；不得并行提交 inspection、state 和 terminal 调用；若同一 activation 同时需要 state 与终态动作，必须先单独 `update_trial_state`，等待 `TRIAL_STATE_UPDATED` 后再在后续响应提交 terminal action，也不得只在 reason 中声称状态已经写入。

运行时原本已在执行前检查 `len(tool_calls) != 1`：多调用响应中的所有调用均被阻断，每个调用收到 `multiple_tool_calls` 纠错结果，之后继续同一 activation；不会选择一个执行，也不会部分持久化 state。新增确定性回归构造了同响应的 `update_trial_state + continue_without_change`，确认两者均未执行、state 保持空值，随后单工具重试才形成唯一 intervention change。

本次补强后的真实 DeepSeek 回归因当前执行环境无法连接外部 API 而尚未完成，因此不能声称 Prompt 已把先前 2/6 的 state 忠实性提高到某个新比例。原实验 artifact 和失败结论保留不变。
