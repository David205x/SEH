# Hook 工具委托与提示注入实验

## 目的

验证 Hook 能否在不嵌套 AgentLoop 的前提下，为主 Actor 生成一次检索委托；并比较委托指令放在 user、既有 system 或临时子任务 system 中时，对 STUDENT 的首轮工具调用遵循和任务表现有何影响。

实验日期：2026-07-16。Actor 与 Hook 模型均为本地 `qwen3:8b`；检索使用当前 `RETRIEVER_URL`。样本为 `supported.jsonl` 的前 3 条，因此结论仅是机制验证和探索性信号。

## 实现

`extensions/tool_delegation` 新增两个独立配置轴：

- `query_strategy`：`fixed`、`question` 或 `hook_model`。后两者分别直接使用 `core.question`，或由一次受控的 Hook STUDENT 调用返回 `{"query": "..."}`。
- `injection_mode`：`user`、`system_append` 或 `replace_system`。后两种修改当前 `ModelInput` 的首个 system message；`replace_system` 使用独立的子任务 prompt 文件。

动态请求以普通 JSON object 保存在 `extension.tool_delegation.requested_tool_call`，而非直接保存 `ToolCall`。这样 state、trace 和 JSONL runner 均可序列化；`pre_tool` 再将该 object 恢复为 `ToolCall`。这一点由回归测试覆盖。

所有模式共享同一事务边界：`post_prompt` 生成并注入控制帧，`pre_tool` 强制执行已记录的调用，`post_tool` 保存结果，下一轮 `post_prompt` 追加恢复提示。Hook 不直接调用 `ToolRuntime`。

## 实验组

| Harness | Query 来源 | 注入位置 |
| --- | --- | --- |
| `delegation_question_user` | 原问题 | user 控制帧 |
| `delegation_question_system_append` | 原问题 | 合并到原 system |
| `delegation_question_replace_system` | 原问题 | 临时替换为子任务 system |
| `delegation_hook_model_user` | Hook STUDENT | user 控制帧 |

对应 rollout 位于 `traces/`，评估报告位于 `reports/`，plugins root 位于 `harnesses/experiments/`。

## 结果

所有四组均完成 3/3 rollout：没有 runner 或 retriever 错误；每条均恰有一次委托控制帧、一次结果恢复帧；`post_tool` 都保存了结果，事务状态均为 `completed`。Teacher 二值裁判和静态规则给四组均为 3/3 正确，平均 2.33 个步骤、1.33 次工具调用。该样本过小且答案轨迹近似，不支持任务正确率差异的结论。

| 注入模式 | 首轮 Actor 调用与委托参数完全一致 | 任务正确率 | 总 token |
| --- | ---: | ---: | ---: |
| user + 原问题 | 3/3 | 3/3 | 12,851 |
| system append + 原问题 | 3/3 | 3/3 | 12,430 |
| replace system + 原问题 | 1/3 | 3/3 | 12,713 |
| user + Hook 模型 query | 3/3 | 3/3 | 14,217 |

`replace_system` 的两次不一致分别是省略 `topk` 和生成占位 query `"..."`；`pre_tool` 因而仍是必要的确定性边界。将指令写入既有 system 没有比 user 注入表现出可辨别提升。临时子任务 system 反而降低了本样本的参数遵循，可能因为它覆盖了原系统工具 schema，不能据此推荐。

Hook 模型的三次输出均为可解析、与题目语义相关的 query，例如将“Fast Cars, Danger, Fire and Knives”的问题改写为针对 hip hop record executive 的检索句。它没有改变这三题的评分，但带来 1,443 个额外 hook token，约每条 481 个。因此：当原问题已经是良好检索 query 时，直接 `question` 策略更简单；Hook 模型应留给需要查询改写、分解或检索判断的情形。

## 当前结论

1. Hook 可跨轮持有一个可审计的委托事务，并由主 loop 安全执行工具。
2. 原问题 query 与 user 控制帧已足以使 qwen3:8b 在本小样本中正确生成首轮调用。
3. system 级别注入目前没有可测收益；替换 system 不应进入 baseline。
4. Hook 小模型接口、trace 和 JSONL 序列化均已被真实调用验证，但其策略价值需在更有难度、更大规模的检索问题上单独评估。

原计划是在固定的 20--100 条样本上继续比较 `question` 与 `hook_model`；以下记录已完成的 20 条验证。后续才应考虑让 Hook 模型做是否委托、查询分解或结果后的 guidance 决策。

## 扩大验证：20 条固定样本

随后在同一批 20 条 `supported.jsonl` 样本上重新运行四组实验，并对所有非静态命中的答案使用同一 Teacher 二值裁判。四组均为 20/20 completed、无 runner error、无 retriever error；因此下表的差异来自模型轨迹和提示策略，而非基础设施失败。

| Harness | 首轮调用完全遵循 | 委托结果保存/恢复 | 正确数 | 准确率 | 平均工具调用 | 总 token |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `question + user` | 14/20 | 20/20 | 18/20 | 0.90 | 1.30 | 94,195 |
| `question + system_append` | 11/20 | 20/20 | 17/20 | 0.85 | 1.25 | 97,117 |
| `question + replace_system` | 14/20 | 18/20 | 16/20 | 0.80 | 1.05 | 72,571 |
| `hook_model + user` | 20/20 | 20/20 | 17/20 | 0.85 | 1.15 | 97,871 |

`replace_system` 的 2 条在首轮直接输出 final answer，绕过了委托；当前 MVP 尚未在 `post_parse` 对这一分支重试，因此没有产生结果保存和恢复事件。其较低 token 与工具调用数是少走了检索步骤的结果，不应当被视为效率收益。

以 `question + user` 为配对基线：`system_append` 仅有 1 条基线正确而对方错误；`replace_system` 为 2 条；`hook_model + user` 为 2 条基线正确而 Hook 模型错误、1 条相反。20 条不足以把 0.90 对 0.85 的差异视为统计显著，但已没有证据支持 system 注入或当前 Hook query 改写优于简单的 user + 原问题策略。

Hook 模型的好处在此被限定为协议层：它使 20 条首轮调用都精确复现 Hook 请求。代价是 13,997 hook token，约 700/条；在该数据切片上没有换来正确率提升。当前 baseline 候选应仍是 `question + user`，而不是 system 注入或每题无条件 Hook 模型改写。
