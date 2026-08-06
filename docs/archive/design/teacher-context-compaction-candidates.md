# Teacher 上下文压缩候选方案

## 状态与范围

本文记录候选设计，不表示当前 runtime 已实现上下文压缩。

分析参考：

- `learn-claude-code/s08_context_compact`
- `claude-code-main/src/services/compact/`
- `claude-code-main/src/query.ts`

目标只覆盖有多次只读工具调用和 transcript continuation 的 Teacher
角色。Actor context 是否进化仍由 Harness plugin 决定，不在这里引入
固定的 core 压缩策略。

## 当前观测

真实 Researcher -> Worker -> Reviewer -> Researcher 实验中：

- Reviewer revision 1 的最后一次请求约为 31.6k prompt tokens；
- Reviewer revision 2 的最后一次请求约为 48.0k prompt tokens；
- Researcher 读取两条完整 trial 后的最后一次请求约为 67.9k prompt
  tokens。

全文证据能够支持模型独立判断，但旧只读工具结果被永久回放后，开销随
trial 数快速增长。

## 可借鉴的不变量

Claude Code 的具体阈值和 API cache edit 不应直接搬运，但以下不变量适用：

1. 压缩前先持久化完整 transcript 或确保工具结果可确定性重读。
2. 不拆分 assistant tool call 与对应 tool result。
3. 流式产生、共享同一 assistant message ID 的 native thinking 和 tool
   call 必须作为同一保留单元。
4. 先执行零模型调用的确定性清理，再考虑 LLM 摘要。
5. 压缩后恢复稳定任务状态和最近工作集，而不是只保留一段自由文本摘要。
6. 自动压缩和失败重试必须有阈值、滞回区间和熔断上限。
7. 主角色与 fork/子角色分别维护压缩状态，不能共享可变删除账本。

## 候选层次

### C1：旧只读工具结果替换

优先级最高。

当同一角色累计多次读取型工具结果后，保留最近若干结果的全文，把更早
结果替换为确定性 tombstone：

```text
[Earlier read-only tool result removed]
tool=get_trial_evidence
arguments_digest=<sha256>
result_digest=<sha256>
replay=call the same tool with the recorded arguments
```

适合优先纳入的工具：

- `get_actor_trajectory`
- `get_trial_evidence`
- `get_evaluation_case`
- 各类 `list_*` 和只读 summary
- `read_harness_file`
- `query_hook_api`

不应按相同规则清理：

- 当前 Compiler transaction 的写入、diff、校验错误；
- 尚未消费的 Worker 分支执行结果；
- terminal submit 的校验反馈；
- 外部角色反馈、冻结输入和当前证据义务。

删除单位应按 tool call/result 配对维护，不能只删除一侧消息。

### C2：按 token 预算保留最近证据

不能只按“最近 N 次工具调用”设置，因为一条完整 trial 可能远大于若干
目录查询。每次模型调用前统计各工具结果估算 token，并为不同角色配置：

- 活跃只读结果总预算；
- 单条结果上限；
- 必须保留的最近 trial 数；
- 受保护的当前 obligation 所引用 trial。

超出预算时先处理最旧、最大的可重放结果。C1 与 C2 都不改变工具首次
返回全文的边界。

### C3：保留最近完整 API rounds

在旧结果清理后仍超预算时，保留冻结输入和最近若干完整 API rounds，
裁剪中间历史。切点必须向前调整到合法边界：

- 不产生孤立 tool result；
- 不丢失同一 assistant message 的 native thinking；
- 不跨越未完成 terminal 校验与修复对话；
- 不裁掉 Reviewer 当前 `next_obligation`。

### C4：结构化角色检查点

压缩后应由程序重新注入稳定状态，而不是要求摘要模型自行回忆：

- role ID、冻结输入和模板版本；
- 当前结构化输出及 output history；
- 原始 feedback history；
- trial refs 和已读账本；
- 当前未关闭 obligation；
- 最近一至两条完整 trial 工具结果。

这相当于 Claude Code compact 后恢复 plan、recent files 和 invoked skills，
但恢复对象改为本项目的角色协议状态。

### C5：LLM transcript 摘要

只有 C1-C4 后仍超过阈值时再启用。摘要模型不得调用工具，输出应覆盖：

- 冻结假设或问题方向；
- 已确认与已反驳的观察；
- 仍开放的唯一 obligation；
- 每个已读 trial 的事实引用和结论来源；
- 最近路由决定；
- 下一步动作。

完整 transcript 必须继续持久化；摘要只替换活跃模型上下文。摘要结果需
通过结构化协议校验，失败时回退到未压缩 transcript，不能静默丢失状态。

### C6：应急压缩与熔断

API 返回 prompt-too-long 时，允许一次更激进的 tail-preserving compact。
连续压缩失败达到上限后应产生可恢复 artifact 并结束当前角色调用，禁止
无限重试。

## 暂不采用

- Claude API `cache_edits`：依赖 provider 特性，不适合作为
  OpenAI-compatible runtime 的基础协议。
- 完整照搬 Claude Code session memory：当前项目尚未定义跨角色经验
  memory，其职责与单角色 transcript continuation 不同。
- 语义化裁剪 trial：程序不应替 Reviewer 判断“上下文修改成功”或
  “主观测已满足”。
- Actor core 自动 compact：Actor 的 context policy 仍属于可进化 Harness
  能力，不应固化到共享 AgentLoop。

## 推荐验证顺序

1. 先实现 C1，并检查 Reviewer 结论与全文回放基线是否一致。
2. 再实现 C2，测量 token、重读次数和结论稳定性。
3. 只有多 trial 会话仍接近上下文上限时，加入 C3-C4。
4. 最后评估 C5；摘要前后应对同一证据产生一致的结构化决定。

