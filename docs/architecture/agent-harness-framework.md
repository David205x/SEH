# Agent 与 Harness Framework

Framework 的目标是提供角色无关、可复用的 Agent 运行骨架。它不把 Student、Teacher、搜索任务或进化策略写入核心类型。

## 组合与装配

`Agent` 只有两个成员：`harness` 和 `model`。`Harness` 包含 Prompt、Output、ToolExecutor 与 HookPipeline，并且本身不保存单次运行状态。`Harness.instantiate()` 为每次 Agent Run 创建隔离的 `AgentState`、Trajectory Recorder 和 Hook State Store。

模板装配按以下顺序执行：

1. 读取并严格校验 `harness.json`。
2. 依 Manifest 顺序加载启用的 Tool Component。
3. 构造 Prompt Component；ToolSet 作为其可选工厂依赖。
4. 构造 Output Component。
5. 构造 Extension Component，保留声明顺序。
6. 上层 Runner 把装配结果绑定到具体 Model 与运行时。

Component Factory 只获得 `ComponentFactoryContext`：模板根目录、可选 `.env` 路径和可选 runtime context。Teacher Template 同样经过共享 Manifest 与 Assembly。正式 Evolution Controller 当前使用 OpenAI-compatible 原生工具循环，独立角色验证还可使用 OpenAI Agents SDK Runner；两者都是外层执行适配器，不改变 Framework 的角色无关性。

## Agent Loop

每个 step 的稳定顺序是：

1. `pre_prompt`
2. 构造 Model Input
3. `post_prompt`
4. 调用 Model
5. `post_model`
6. 解析输出
7. `post_parse`
8. 若为工具调用：`pre_tool` → 执行工具 → `post_tool`
9. 若为最终答案：`pre_final` → 接受或退回

工具错误和步数耗尽会进入 `on_error`。`pre_final` 的 `FinalDecision.defer` 会保留候选回答并追加反馈，使 Agent 回到下一 step；已经被某个 Hook defer 的决定不能被后续 Hook 改回 accept。

## Hook 状态所有权

Hook 通过声明式、事务式接口访问状态：

| 命名空间 | 所有者 | 可写性 |
| --- | --- | --- |
| `core.*` | Agent Loop | Hook 只读 |
| `stage.*` | 当前 lifecycle phase | Hook 必须显式声明写权限，且保持类型 |
| `extension.<hook_id>.*` | 指定 Extension | 仅声明的 writer 可写 |
| `shared.*` | 多 Extension 协作 | 仅声明的 writer 可写，所有 Hook 可读 |

一次 Hook 调用的修改先暂存，成功后整体提交，并以 `hook_applied` 事件写入 Trajectory；异常则记录 `hook_error`。需要调用辅助模型的 Hook 还必须声明允许的 profile 和单次调用预算，调用及错误同样进入 Trajectory。

## 稳定边界

- Prompt、Output、Tool 与 Extension 是 Component 类型；Harness 不是 Component 的集合名称替代品。
- Template 是实例化资产，不等于 Harness 运行实例。
- Runner 负责把共享组件绑定到具体运行后端；它不拥有领域路由。
- Evolution Policy 决定哪些 Component 可修改，不改变 Framework 的装配语义。

Manifest 与 Component 接口见[Harness Template Reference](../reference/harness-template.md)和[生命周期与 Component API](../reference/lifecycle-and-components.md)。
