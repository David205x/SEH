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
  `flow` 保留为最后一个 Generation 的兼容字段。每个节点同时声明
  `work_kinds` 和 `event_types`，作为事件筛选映射的唯一来源。
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

## 节点事件筛选

环形流程图节点是严格单选筛选器。点击节点后，事件进展仅显示当前 Generation 中
映射到该节点的 WorkItem；点击另一个节点会替换筛选，再次点击当前节点或标题旁的
筛选标签会清除筛选。切换 Generation、类别、状态或原始 Journal 视图时会保留同一
节点筛选。

- `GET /api/runs/{run}/works?node={node_kind}&generation={generation}`：返回节点映射的
  WorkItem，可继续叠加 `category` 和 `status` 查询参数。
- `GET /api/runs/{run}/journal?node={node_kind}&generation={generation}`：返回这些
  WorkItem 的生命周期 Control Events，以及节点直接归属的 Control Events。
- Promotion 的原始 Journal 筛选包含 `version_advanced`；该事件不被伪造为 WorkItem。
- 事件进展中的 `#N` 使用该 WorkItem 首条 Journal 事件的 `sequence`，因此筛选和刷新
  不会改变编号；悬停编号可查看完整的 Journal sequence 范围。

当前邻近节点映射中，Intervention 同时覆盖 `select_trial` 与 `execute_trial`，
Candidate Review 同时覆盖 `review_candidate` 与 `reject_candidate`。Trial Reviewer 和
Evidence Review 共享现有的 `review_evidence` WorkItem；这是当前产物粒度下的只读投影。
