# Evolution Experiment Observer 实施计划

本计划落实 [Evolution Experiment Observer 方案](experiment-observer-visualization.md)。观察器是
新建的顶层独立软件包，不使用、继承或依赖现有 `search_harness.visualizer`；旧 Trace Viewer
不构成新包的实现、接口或测试前提。

## 1. 实施边界

首版目录建议为：

```text
evolution_observer/
  __main__.py                 # 本地服务命令行入口
  server.py                   # 127.0.0.1 的只读 HTTP 服务和静态文件分发
  discovery.py                # 直接子目录 Run 发现与不可读条目
  journal.py                  # JSONL 增量读取、Control Event 和 WorkItem 投影
  artifacts.py                # 受限的 Artifact Reference 解析与 JSON/JSONL 加载
  metrics.py                  # Evaluation Snapshot、用量和耗时投影
  harness.py                  # Accepted Version、candidate 摘要和静态 Hook 推断
  details.py                  # WorkKind 专用详情投影及通用回退
  models.py                   # 观察器自身的只读数据结构
  static/                     # 原生 HTML、CSS、JavaScript 和 SVG/CSS 图表
tests/evolution_observer/
  fixtures/                   # 小型、脱敏、版本固定的 Run 产物夹具
```

顶层包只依赖 Python 标准库和浏览器原生能力。它不 import `search_harness.visualizer`，不调用
Harness Assembly，不调用 `HarnessVersionStore.stage()`，也不执行任何 Template 中的 Python。

可以读取项目现有的 JSON Schema、常量或纯数据类型以减少重复，但每项复用必须不引入 Template
执行、Model 调用或写文件副作用。若不能明确证明无副作用，观察器自行按 JSON 文件解析。

## 2. 首版数据模型

以下对象都是只读投影，不是项目领域事实的新替代品。

| 投影 | 字段 | 职责 |
| --- | --- | --- |
| `RunListing` | `directory_name`、`path`、`modified_at_utc`、`read_status`、`error_summary` | 实验选择页的一项直接子目录。 |
| `ObservedRun` | `listing`、`run_metadata`、`journal_status`、`last_event_at_utc` | 已解析 Evolution Run 的概览。 |
| `ObservedEvent` | `sequence`、`event_type`、`created_at_utc`、`payload` | 原始 Control Journal 事件。 |
| `ObservedWorkItem` | `work_id`、`kind`、`category`、`attempts`、`status`、`parent_work_id`、`start/end`、`artifact_refs` | 一个 Work Item 的业务可读生命周期。 |
| `EvaluationSnapshot` | `snapshot_id`、`generation`、`candidate_revision`、`subject`、`metrics`、`provenance` | 一次可比较的 incumbent 或 candidate Evaluation。 |
| `UsageBreakdown` | `student`、`hook_model`、`teacher_role`、`teacher_judge`、`unknown` | 有来源的用量分组；Hook 作为 Student 内子项呈现。 |
| `HarnessSummary` | `accepted_version`、`manifest`、`components`、`hook_inference` | 最终 accepted Harness 的静态展示信息。 |
| `CandidateSummary` | `attempt_id`、`status`、`changed_files`、`validation`、`diff`、`evaluation`、`review` | 不重建工作树的历史候选预览。 |
| `DetailDocument` | `kind`、`summary`、`blocks`、`selectors`、`references` | 可由前端统一渲染或按 kind 扩展的详情视图。 |

`category` 仅为观察器展示分组：Teacher Role 或机制。它不改变 WorkKind 的项目语义。未知 WorkKind
必须进入 `unknown` 类别，保留原始名称和原始事件，而不能伪装成已知角色。

## 3. 只读 API

所有 API 返回 JSON，所有时间字段均为 Journal 原始 UTC 字符串。请求只接受观察器生成的 Run ID、
Work ID、Artifact ID 或受控相对路径；不接受任意绝对文件路径。

| 路由 | 响应 | 用途 |
| --- | --- | --- |
| `GET /api/runs` | `RunListing[]` | 发现实验，含不可读取条目。 |
| `GET /api/runs/{run}/overview` | `ObservedRun` + 流程节点、摘要、统计 | Run 概览页。 |
| `GET /api/runs/{run}/works` | 分页 `ObservedWorkItem[]` | 默认倒序工作进展列表与筛选。 |
| `GET /api/runs/{run}/journal` | 分页 `ObservedEvent[]` | 原始 Control Journal 视图。 |
| `GET /api/runs/{run}/works/{work}` | `DetailDocument` | Work Item 详情页。 |
| `GET /api/runs/{run}/metrics` | `EvaluationSnapshot[]` + `UsageBreakdown` | 指标卡、趋势图和用量视图。 |
| `GET /api/runs/{run}/harness` | `HarnessSummary` + `CandidateSummary[]` | Harness 与候选摘要页。 |
| `GET /api/runs/{run}/refresh-state` | 修改标识、末尾 sequence、待写入项目 | 客户端轮询的轻量检查。 |

静态资源位于根路径；服务只能监听 `127.0.0.1`。`--host` 不作为首版 CLI 参数，以避免把局域网
暴露变成无意的默认能力。

## 4. 详情投影策略

详情构造遵循“专用优先、通用回退”：

1. 普通 Teacher Role Artifact：渲染 system/user/assistant/reasoning/tool call/tool result/final output/error
   块；reasoning 默认折叠。
2. Evaluation：摘要、per-example、per-rollout 与选中 Student Trajectory。
3. Intervention：source/branch、phase、activation、patch、worker trace 和比较信息。
4. Conformance：candidate replay、finding、Mechanism Spec 和 aggregate。
5. Candidate、validation、promotion 或 rejection：候选摘要、diff、门禁和失败/暂停原因。
6. 不认识的 WorkKind 或不完整 Artifact：显示 Control Journal、可读取的 `effect.json` 和原始 JSON
   树，并标记缺失内容。

前端使用统一可折叠 Block 组件；按块类别提供“全部展开/折叠”和单块切换。多个 rollout、trial 或
finding 必须先以 selector 列表呈现，随后按需请求详情，不在 overview 载入完整 JSONL。

## 5. 分阶段实施

### 阶段 0：包骨架和只读安全

- 新建独立包、CLI 和仅 `127.0.0.1` 的标准库 HTTP 服务。
- 实现安全的 Run ID/相对路径解析；拒绝路径穿越和未声明的外部引用。
- 建立小型 Run fixture，包含有效、损坏和缺少外部引用三种目录。
- 验收：服务不产生 Run 内文件；路径穿越被拒绝；不可读取 Run 仍列出。

### 阶段 1：发现、Journal 和双层时间线

- 发现直接子目录，解析 `run.json` 和 `events.jsonl`。
- 将 `scheduled → started → completed/failed → transitioned` 投影为 Work Item，并保留重试。
- 实现原始 Journal 与 WorkItem 双层 API/UI、角色/机制/状态筛选及 UTC 时间展示。
- 将 `run_paused`、`work_failed`、无终态的 `running` 区分开。
- 验收：`20260803` 显示为 `Generation 1 · paused`，并可定位两次 Promotion 的
  `PermissionError`。

### 阶段 2：Evaluation、指标和用量

- 从 incumbent/candidate Evaluation Report 发现快照，构造
  `G1 incumbent → G1 candidate r1 → ...` 序列。
- 提取准确率、稳定性、执行和 token 指标，保存 provenance 与可比性标记。
- 聚合 Student（含 Hook 子项）、Teacher Role、Teacher Judge、未知用量；无 cache 契约时显示未记录。
- 以原生 SVG/CSS 绘制首版曲线和占比图，无新增前端依赖。
- 验收：不能把同一用量在 Work completed、Role Artifact 和 Evaluation Report 中重复相加；
  不能将缺失值补为 0。

### 阶段 3：Artifact 详情和通用对话块

- 实现受限 Artifact Resolver、懒加载 JSON/JSONL 和“待写入或不完整”状态。
- 实现 Teacher Role、Evaluation、Intervention、Conformance 和 Candidate 的详情投影。
- 实现 transcript/trajectory block、选择器、reasoning 默认折叠和批量展开。
- 验收：详情页面初始不读取未选 rollout；缺失/半写入 Artifact 不被显示为 Work failed。

### 阶段 4：Harness 和候选摘要

- 从声明的 Version Store 只读获取最终 Accepted Template Version 的文件和 Manifest。
- 静态读取 Prompt/Tool/Output/Extension 内容，不装配或 import Component。
- 对 Extension 源码做保守 Hook 注册推断；无法确认时显示“未能静态推断”。
- 从 Candidate Attempt Journal 与 compiler/stage artifacts 提取候选摘要和 diff。
- 验收：不创建 staging 目录、不 import Template；候选仅展示实际可读取的摘要，不假装有完整快照。

### 阶段 5：轮询、性能和交付验证

- 实现 10 秒默认轮询、暂停自动刷新和立即刷新；Journal 增量读取及末尾半行重试。
- 使用虚拟列表或分页限制长列表初始 DOM；详情维持按需读取。
- 补充 API、投影、路径边界、半写入、轮询和静态推断测试。
- 用 `20260803` 做端到端 smoke test，并确认服务没有写入实验根、Version Store 或系统临时目录。

## 6. 测试层次

| 层次 | 验证内容 |
| --- | --- |
| 单元测试 | JSON/JSONL 解析、Journal 投影、状态机、用量去重、路径允许列表、Hook 静态推断。 |
| Fixture 集成测试 | 一个完整 Run、一个暂停 Run、一个半写入 Run、一个不可读取 Run。 |
| HTTP 测试 | 每个 API 的成功、404、不可读、路径穿越和部分写入响应。 |
| 浏览器 smoke test | 选择 Run、筛选 Work、展开日志/对话块、切换 rollout、刷新后保持选择。 |
| 只读验证 | 比较启动前后 Run 根与 Version Store 的文件清单；不允许创建 staging、缓存或临时文件。 |

## 7. 实施次序和风险控制

先完成阶段 0–1，以得到能阅读、定位和审计控制过程的最小可用观察器；阶段 2–4 分别增加指标、
详证与 Harness，避免前端先假设尚不存在的稳定数据结构。阶段 5 最后引入实时刷新，以免早期调试时
将半写入问题与数据投影问题混淆。

当前已知风险及处理：

- Role Artifact 结构可能随 role/contract 演进：使用专用 renderer registry 和通用原始 JSON 回退。
- 候选 workspace 不保证可物化：候选页仅承诺摘要和 diff。
- Hook 注册没有稳定 metadata：静态分析只给出保守结果并显式标注。
- 用量来源可能重叠：UsageProjector 按来源优先级去重，无法证明归属时进入未归类。
- 运行中 JSONL 的末行可能不完整：只延迟解析该行，不把它升级为 Run failure。
