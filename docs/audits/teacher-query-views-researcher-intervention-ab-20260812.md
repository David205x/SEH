# Researcher 与 Intervention 查询视图 A/B 实验

日期：2026-08-12  
结论状态：影子方案验证完成，尚未切换正式工具

## 1. 实验目的

本实验回答两个问题：

1. Hypothesis Researcher 使用压缩、分层的 Trajectory 与 Student Behavior Interface
   后，是否仍能充分查阅问题并生成可执行的 Intervention Hypothesis；
2. Intervention Worker 使用紧凑 Editable Context 和精确 Block View 后，是否仍能区分
   应当干预与正确不干预，并正确调用上下文修改工具。

底层 Evaluation、Trajectory 和 Trial Artifact 保持不变。Researcher A/B 使用两套
当前完整方案，包含各自提示与查询工具；Intervention A/B 仅替换只读查询视图，使用
相同 Prompt、Role Input、终端修改工具和模型配置。

## 2. 实验材料与方法

Researcher 使用 `20260809_base` 中两个已保存角色输入：

- 第一次检索遗漏问题所需实体或关系，Student 仍直接提交答案；
- `topk=1` 的属性检索没有返回出生信息，Student 直接提交无法确定的非答案。

每类输入正式与影子各运行五次，共 20 次 DeepSeek Role Run。

Intervention 使用同一冻结 Hypothesis 下两个已保存 Trial：

- 正触发：Henri Leconte 与 Jonathan Stark 比较题，第一次结果只覆盖一侧；
- 正确不触发：检索结果已支持 El-P 的别名关系，不应追加干预。

每个 Trial 正式与影子各运行三次，共 12 次 DeepSeek Worker Run；每次从同一保存前缀
继续运行本地 Student，并使用 Teacher Judge 记录 Branch 结果。执行顺序在重复间交替，
避免固定先后顺序偏差。

## 3. Researcher 结果

| Scheme | Completed | Mean turns | Mean queries | Mean Tool Result chars | Mean input tokens | Mean total tokens | Mean submit retries |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| formal | 10/10 | 5.20 | 4.50 | 55301.00 | 115672.80 | 130439.90 | 2.20 |
| shadow | 10/10 | 3.90 | 7.20 | 30935.60 | 58086.80 | 71635.50 | 0.20 |

影子方案相对正式方案：

- 查询调用增加 `60.0%`；
- Tool Result 字符减少 `44.1%`；
- 输入 token 减少 `49.8%`；
- 总 token 减少 `45.1%`；
- 终端修订从平均 `2.20` 次降为 `0.20` 次。

两套的 20 次运行均提交了结构有效、与 Failure Pattern 对齐且可由现有 Worker 执行的
Hypothesis。影子方案没有表现出少读 Evidence：它仍读取全部引用 Trajectory，并使用
Student Behavior Interface 与 Intervention Capability；增加的查询主要来自精确 Block
下钻。

两套都没有形成唯一的阶段选择。第一个样本中，两侧均出现 `post_tool` 三次与
`pre_final` 两次；第二个样本中，正式为 `post_tool` 四次、`pre_final` 一次，影子为
`post_tool` 三次、`pre_final` 两次。两种方案分别在证据返回后预防终答，或在终答前
拒绝非答案，均符合当前能力边界。该方差属于假设空间多解，不是查询视图缺失。

影子侧 10 次中有 3 次工具参数 JSON 截断，Runner 给出错误后模型自行恢复；正式侧
没有同类查询错误。由于影子侧调用更多且参数更长，不能据此认定排版本身导致错误，
但正式迁移时仍应把 Provider Structured Tool Calling 稳定性作为边界。

## 4. Intervention Worker 结果

| Scheme | Worker runs | Correct positive action | Correct no-op | Mean queries | Mean Tool Result chars | Mean total tokens |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| formal | 6 | 3/3 | 3/3 | 4.17 | 4696.67 | 12758.83 |
| shadow | 6 | 3/3 | 3/3 | 3.67 | 4441.00 | 11831.50 |

正触发样本中，正式与影子均 3/3 调用 `apply_context_patch`。所有修改后的 Student
下一动作都是针对缺失实体的 `search`，两侧 Branch 均 3/3 判对。正确不触发样本中，
两侧均 3/3 调用 `continue_without_change`；Student 的下一动作均为原始终答。

正确不触发样本的最终 Judge 分数正式为 1/3、影子为 2/3。这来自 Student 对同一前缀
重新采样后的答案表达波动，因为 Worker 决策、上下文是否修改和立即动作均一致，不是
视图效果证据。

影子方案平均减少 `12.0%` 查询调用、`5.4%` Tool Result 字符和 `7.3%` Worker 总
token。Worker 必须阅读精确检索正文以判断覆盖缺口，正文占返回主体，所以其压缩空间
自然小于 Researcher。

Worker 的共同不稳定性是 Provider 在一次 Assistant Response 中并发请求多个只读工具，
与该角色“一次只调用一个工具”的规则冲突。正式方案平均产生 2.0 条约束反馈，影子为
1.33 条；所有运行均恢复并提交终端动作。错误内容表明问题不是未知 Block ID，也不是
精确正文的新格式无法阅读。

## 5. 结论与边界

影子查询视图没有降低角色完成率、Evidence 查阅能力或 Worker 意图遵循。Researcher
获得显著 token 降幅，Intervention Worker 获得稳定的小幅降幅；正触发与正确不触发的
行为在全部重复中保持一致。结果支持后续独立实施正式迁移，但不授权在本实验中删除或
覆盖正式工具。

本实验不证明所有 Failure Pattern 都会产生唯一 Hypothesis，也不证明所有 Provider 都
能稳定遵循单工具调用。阶段选择准则和 Structured Tool Calling 稳定性应分别处理，不能
通过进一步删除 Evidence 解决。

## 6. 产物

- Researcher 合并统计：
  `runs/experiments/teacher_query_views/20260812_researcher_ab_multi/researcher_combined_5x_summary.json`
- Intervention 完整 A/B：
  `runs/experiments/teacher_query_views/20260812_intervention_ab_deepseek/summary.json`
- 影子 Intervention 视图：`experiments/teacher_query_views/intervention.py`
- Intervention A/B 脚本：`experiments/run_intervention_query_views_ab.py`

Intervention 摘要中的源文件 SHA-256 在运行前后完全一致。
