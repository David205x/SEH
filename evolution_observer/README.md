# Evolution Observer

`evolution_observer` 是 Evolution Run 产物的独立只读观察器。它直接解析指定
`runs-root` 的直接子目录，不要求实验主程序额外生成可视化专用产物，也不导入或继承
旧的 `search_harness.visualizer`。

## 启动

```powershell
python -m evolution_observer --runs-root runs/evolution --port 8766
```

服务仅监听 `127.0.0.1`。页面不自动刷新；运行中的 Run 可通过顶栏的“刷新数据”按钮
重新读取。

## Overview 聚合

`GET /api/runs/{run}/overview` 在原始 Run 摘要之外提供以下观察器投影：

- `generation_flows`：每个 Generation 一份独立流程状态，供页面通过 Tab 切换；
  `flow` 保留为最后一个 Generation 的兼容字段。
- 流程节点的 `budget`：从 Run 配置读取上限，并根据 WorkItem 父子关系统计实际消耗；
  失败的 Promotion 不会激活到下一代 Incumbent 的连线。
- `statistics.role_turns.run`：整个 Run 内按角色聚合的回合数箱型图数据。
- `statistics.role_turns.by_generation`：按 Generation 独立聚合的相同统计。
- `statistics.evolution_metrics`：每个 Generation 的 Student 平均回合、逐轨迹
  Student token 最小/平均/最大值、静态匹配正确率、Teacher Judge 补充后的最终
  正确率和平均答案一致性。每代优先选择最后完成的 Candidate Evaluation；没有
  Candidate 时回退 Incumbent Evaluation。

箱型图的样本取自可读取的 Teacher Role artifact 中 `usage.requests`；回合上限优先取
artifact 的 `role_budget.max_turns`，缺失时回退到 Run 配置中的
`effects_config.teacher_max_turns`。缺失值保持“未记录”，不会补零。

Evolution Metrics 的 token 分布读取 Evaluation Report 的 `per_rollout.jsonl`；
匹配正确率为 `static_pass_count / scored_count`，Teacher Judge 曲线为报告中的最终
`accuracy`，稳定性使用 `mean_answer_consistency`。
