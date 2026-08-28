# TASK-007 v1 / v2 真实 API 对照

## 结论

v7 对工具可发现性和明确 implementation 归因有效，但 Prompt 的终态长度约束与 upstream-design 优先级还需一次最小修订。TASK-007 保持 `executed`、未验收。

| 项目 | v1 | v2 | 判断 |
| --- | ---: | ---: | --- |
| 计划 Run | 30 | 30 | 同一 18-case 组合 |
| 完成 Run | 30 | 29 | v2 有一例结构终态失败 |
| evidence 工具尝试 | 51 | 33 | v2 不再因猜错目录产生额外调用 |
| evidence 工具成功 | 23 | 33 | 合法读取增加 |
| evidence 工具失败 | 28 | 0 | directory/feedback 修复有效 |
| `student_capability` 条目 | 26 | 7 | 类型门槛明显收紧 |
| `experiment_direction` 条目 | 24 | 13 | 不再填满 taxonomy |
| `teacher_work` 条目 | 18 | 14 | 明确实现缺陷仍保留必要路由 |
| 人工 case 结论 | 6 pass / 11 partial / 1 fail | 14 pass / 3 partial / 1 fail | 主要归因质量改善 |

v2 的剩余 fail 不来自 evidence 工具：模型连续输出长 reasoning，唯一 submit JSON 被截断。完成 Run 中仍有一个明确偏差：对“处理组相对 control 没有差异”的结果生成了 `student_capability`，而不是拒绝上游因果方向。
