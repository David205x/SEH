# V1 实现清理计划

## 文档状态

本文档记录只保留 V2 实现时的架构清理范围、迁移步骤和验收标准。
当前状态为**规划完成、尚未执行**。本文档不是删除记录，也不表示所列 V1
入口已经停止工作。

本次清理的目标不是保留旧接口兼容性，而是在不改变 V2 行为的前提下：

- 将仍被 V2 使用的通用能力迁出 V1 命名空间；
- 删除 V1 Teacher 角色、V1 Evolution Runner 及其模板和测试；
- 让 Teacher 角色只由 `search_harness.teacher` 实现；
- 让进化流程只由 `search_harness.evolution.control` 编排；
- 保留历史设计文档和实验产物的可追溯性。

## 当前结论

这是一项中等偏大的架构清理，不能直接删除 `search_harness/adapter/` 和旧
`search_harness/evolution/`。

V2 当前仍依赖两组位于 V1 命名空间下的能力：

1. `search_harness.evolution.control.effects` 复用
   `LocalEvolutionBackend` 执行 Actor rollout 和 evaluation；
2. V2 Teacher Intervention 复用 `search_harness.adapter.intervention`
   中的前缀恢复、Hook bridge、Teacher Worker 和单分支试验 runtime。

因此，清理必须按照“先迁移共享能力，再删除 V1”的顺序执行。

## V1 与 V2 边界

### 明确属于 V2

- `search_harness/teacher/`
- `search_harness/evolution/control/`
- `harness_templates/teacher/`
- `docs/manual_v2/`
- `tests/teacher/`
- `tests/evolution/test_control.py`
- Actor core、dataset、evaluation、registry、versioning 等公共框架模块
- `harness_templates/actor/`
- `harness_templates/search-o1/`
- `harness_templates/experiments/` 中仍用于研究的 Actor Harness

### 明确属于 V1

- `search_harness/adapter/compiler/`
- `search_harness/adapter/critic/`
- V1 Intervention Coordinator
- `search_harness/evolution/runner.py`
- `search_harness/evolution/backend.py` 中除 rollout/evaluation 外的角色编排
- `search_harness/evolution/types.py` 中的 V1 状态机协议
- `search_harness/evolution/research.py`
- `search_harness/evolution/journal.py`
- `search_harness/evolution/progress.py`
- `harness_templates/adapter/`
- V1 Adapter 和 Evolution Runner 测试

### 名义属于 V1、实际被 V2 使用

以下实现不能直接删除，必须先迁移：

| 当前模块 | V2 使用目的 | 处理方式 |
| --- | --- | --- |
| `adapter/intervention/prefix.py` | 读取 rollout、构造可恢复时间线、重建模型可见前缀 | 迁入中立 Intervention runtime |
| `adapter/intervention/bridge.py` | 将 Intervention action 映射到 HookContext | 迁入中立 Intervention runtime |
| `adapter/intervention/types.py` | Prefix selector、重建结果和 action 类型 | 迁入中立 Intervention runtime |
| `adapter/intervention/worker.py` | 在一个 Actor 分支的 Hook activation 中运行 Teacher Worker | 迁入中立 Intervention runtime |
| `adapter/intervention/runtime.py` | 执行并记录单案例 Intervention 分支 | 拆除 Coordinator 工具包装后迁移 |
| `evolution/backend.py` 的 rollout/evaluation 部分 | 评估 incumbent 和 candidate | 提取为 V2 评估服务 |
| `evolution/types.py` 的 `EvaluationArtifact`、`CandidateArtifact` | 连接旧 backend 与 V2 effect | 用 V2 本地类型或直接参数替换 |

## 目标结构

### Intervention runtime

建议将可复用的 Intervention 执行能力迁入：

```text
search_harness/runtime/intervention/
  __init__.py
  types.py
  prefix.py
  bridge.py
  worker.py
  runner.py
```

各模块职责如下：

| 模块 | 职责 |
| --- | --- |
| `types.py` | 保存前缀定位、重建结果和 Intervention action 的内部类型 |
| `prefix.py` | 从 rollout trace 重建指定可恢复节点的模型可见上下文 |
| `bridge.py` | 在一个 Actor loop 中应用 Worker 产生的上下文操作 |
| `worker.py` | 维护单分支、跨 Hook activation 的 Teacher transcript |
| `runner.py` | 装配 Student、Teacher、Hook bridge，并执行一次 Intervention trial |

该包是运行机制，不是新的 Teacher 角色。V2 角色协议仍由
`search_harness.teacher` 定义。

迁移时不保留以下 V1 Coordinator 能力：

- `InterventionCoordinatorRunner`
- `InterventionCoordinatorContext`
- `RunInterventionWorkerTool`
- V1 Coordinator result 协议
- V1 Coordinator prompt 和插件工具

### Rollout 和 evaluation 服务

建议从旧 backend 提取：

```text
search_harness/evolution/evaluation.py
```

该服务只负责：

- 从冻结的 Experience Set 加载样本；
- 解析 accepted version 或 pending candidate 的 Harness source；
- 按 `rollouts_per_example` 运行 Actor；
- 保持 example ID、replicate ID 和随机种子策略；
- 保存 rollout provenance；
- 执行静态评估和可选 Teacher Judge；
- 写入 evaluation report；
- 返回 rollout 路径、report 路径和 metrics。

该服务不得继续携带以下 V1 配置：

- Critic template root；
- Compiler template root；
- Coordinator template root；
- Critic 或 Compiler repair budget；
- V1 proposal、review 或 iteration 类型。

V2 `LocalControlEffects` 应直接依赖这个窄服务，不再实例化
`LocalEvolutionBackend`。

## 变更清单

### 第一阶段：建立安全基线

开始删除前必须：

1. 将当前 V2 代码、Teacher templates、V2 tests 和 `manual_v2` 纳入 Git；
2. 提交一个不包含 V1 清理的 V2 基线 commit；
3. 保存当前测试结果；
4. 确认未提交的实验产物不会被清理提交意外包含或删除。

当前工作区中以下 V2 主体仍主要处于未跟踪状态：

- `search_harness/teacher/`
- `search_harness/evolution/control/`
- `harness_templates/teacher/`
- `tests/teacher/`
- `tests/evolution/test_control.py`
- `docs/manual_v2/`

在完成基线提交前，不应执行目录级删除。

### 第二阶段：迁移 Intervention 底座

1. 创建中立 Intervention runtime 包；
2. 迁移 prefix、bridge、types、worker 和 trial runner；
3. 删除 runner 中只服务于 V1 Coordinator 的工具包装；
4. 修改 V2 Teacher、resources、capability catalog 和 Controller imports；
5. 修改 `experiments/intervention_value_probe.py` 的 import；
6. 将仍有效的 prefix/runtime 测试迁入新的测试目录；
7. 验证迁移前后重建前缀和 Hook action 的输出完全一致。

建议独立提交这一阶段，避免它与 V1 删除混在同一个 diff 中。

### 第三阶段：提取 V2 评估服务

1. 从 `LocalEvolutionBackend._rollout_and_evaluate` 提取评估服务；
2. 为评估服务定义只包含 V2 所需字段的配置；
3. 由 `LocalControlEffects` 直接调用新服务；
4. 移除 Controller 对旧 `CandidateArtifact` 的依赖；
5. 验证 accepted version 和 pending candidate 两种 Harness source；
6. 对比迁移前后的 rollout provenance、seed、replicate 和 report metrics。

### 第四阶段：删除 V1 实现

迁移完成后删除：

```text
search_harness/adapter/
search_harness/evolution/backend.py
search_harness/evolution/runner.py
search_harness/evolution/types.py
search_harness/evolution/research.py
search_harness/evolution/journal.py
search_harness/evolution/progress.py
harness_templates/adapter/
```

同时：

- 重写 `search_harness/evolution/__init__.py`，不再导出 V1 Runner；
- 将 `python -m search_harness.evolution` 转发到 V2 Controller，或明确只保留
  `python -m search_harness.evolution.control`；
- 从 `search_harness/paths.py` 删除 V1 Critic、Compiler 和 Coordinator
  template 常量；
- 删除 V1 Adapter CLI；
- 不增加兼容 import、deprecated wrapper 或旧参数适配层。

### 第五阶段：删除和迁移测试

删除：

- V1 Critic tests；
- V1 Compiler tests；
- V1 Coordinator tests；
- V1 Adapter CLI tests；
- V1 Evolution Runner tests；
- 只服务于 `EvolutionResearchStore` 的测试。

迁移并保留：

- prefix reconstruction tests；
- intervention runtime tests；
- Teacher Intervention capability tests；
- Controller effect tests；
- Version Store 和 candidate transaction tests。

测试目录还需要统一发现规则。当前：

- `python -m unittest discover -s tests` 执行 177 项并通过；
- `tests/teacher` 的 69 项测试需要单独 discover，当前通过；
- `tests/templates` 的 5 项测试需要单独 discover，当前通过；
- `tests/experiments` 的 4 项测试需要单独 discover，其中 2 项因旧
  `InterventionHypothesis` 协议而失败。

默认测试命令没有覆盖所有 V2 测试，因此“177 项通过”不能作为 V2 全绿结论。
清理过程中应先修正测试发现方式，并更新失配的 experiment fixture。

### 第六阶段：文档和可视化

更新 `manual_v2`：

- 删除“V1 与 V2 并存”的当前状态描述；
- 删除 V2 复用 `LocalEvolutionBackend` 的说明；
- 更新 V2 CLI 和模块结构；
- 将 Intervention runtime 记录为内部运行机制；
- 将 `docs/manual_v1/` 明确保留为历史档案。

历史文档和产物默认不删除：

- `docs/manual_v1/`
- `docs/design/`
- 已有 `runs/`
- 已有 `traces/`
- accepted Harness checkpoints

旧 V1 run 在删除 Runner 后不能继续 resume，但其 JSON、JSONL 和报告仍可作为
历史证据读取。Accepted checkpoint 仍由同一 Version Store 管理，可继续作为
V2 初始版本。

当前可视化包含 V1 专用 Critic/Compiler 页面、API 和 Experiment artifact
识别逻辑。严格执行“只保留 V2 实现”时，应由可视化维护方单独完成：

- 删除或重写 V1 Critic/Compiler standalone 页面；
- 将 Experiment 页面改为读取 V2 `artifacts/<work-id>/`；
- 识别 V2 Teacher role artifact，而不是旧 `critic_result` 和
  `compiler_result` 日志；
- 更新旧 schema fixtures 和可视化测试。

该部分应独立提交，不与核心运行时迁移耦合。

## 规模评估

当前静态统计如下：

| 范围 | 文件数 | 约行数 | 预计结果 |
| --- | ---: | ---: | --- |
| `search_harness/adapter` | 26 | 5,162 | 约 1,835 行迁移，其余删除 |
| V1 evolution 文件 | 8 | 2,828 | 提取少量评估逻辑，其余删除 |
| V1 Adapter templates | 30 | 1,390 | 全部删除 |
| V1 相关测试 | 15 | 3,072 | 约 700 行迁移，其余删除 |
| V2 Teacher | 20 | 7,531 | 主要修改 import 和资源绑定 |
| V2 Controller | 9 | 2,671 | 修改 evaluation dependency 和类型 |

预计核心清理：

- 涉及约 80 至 95 个文件；
- 代码 diff 约 9,000 至 12,000 行，多数为删除和文件迁移；
- `search_harness` 包净减少约 6,000 行；
- 需要 4 至 6 个职责单一、可独立验证的提交。

## 风险评估

### P0：V2 基线尚未完整进入 Git

这是开始清理前的阻断项。否则目录级删除后的回退依赖未跟踪工作区，无法形成可靠
版本边界。

### P0：V2 对 V1 的隐藏依赖

直接删除 `adapter` 或旧 backend 会导致 V2 在导入阶段失败。验收时必须保证源码
中除历史文档和历史产物外，不再引用 `search_harness.adapter`。

### P1：Intervention 行为漂移

风险集中在：

- prefix 边界是否 inclusive；
- 只重建模型可见上下文还是混入内部 event；
- Hook phase 与 activation budget 是否保持；
- Teacher transcript 是否跨 activation 保留；
- `pre_final` defer/accept 行为是否保持；
- trial trace 和 token usage 是否保持可审计。

迁移应优先采用移动和改名，不在同一阶段重写行为。

### P1：Evaluation 可复现性漂移

必须保持：

- Experience Set digest；
- example ID 和 replicate ID；
- `base_seed + replicate_index` 策略；
- Harness source provenance；
- rollout 和 Judge 并发配置；
- Teacher Judge 开关；
- report metrics 和路径语义。

### P1：测试覆盖假绿

当前默认 discover 不包含全部 V2 测试，并且 research experiment 已出现协议漂移。
若不先修复测试入口，清理可能在表面全绿的情况下破坏 Teacher runtime。

### P2：旧入口和外部脚本失效

以下接口将不再工作：

- `python -m search_harness.adapter ...`
- V1 `python -m search_harness.evolution run/resume`
- `from search_harness.evolution import EvolutionRunner`
- `search_harness.adapter.*` imports

这是不保留兼容层的预期结果，应通过文档和明确的 V2 CLI 取代，而不是添加兼容
wrapper。

### P2：历史实验不能继续恢复

已有 V1 run 保留为只读历史证据，但删除 V1 Runner 后不能继续推进。Version Store
中的 accepted Harness 版本不受影响；未完成的 V1 candidate iteration 应视为历史
未完成事务，不自动导入 V2 Controller。

### P2：可视化协议仍面向 V1

若核心清理先完成，可视化中的旧页面仍可能读取历史产物，但不再代表当前运行协议。
应由可视化维护方明确迁移或删除，避免用户误把 V1 页面当作 V2 控制面。

## 提交建议

建议按以下提交拆分：

1. `chore: checkpoint current v2 implementation`
2. `refactor: move intervention trial runtime out of adapter`
3. `refactor: extract v2 rollout evaluation service`
4. `remove: delete v1 adapter and evolution runner`
5. `test: align v2 discovery and remove v1 suites`
6. `docs: make v2 the sole active architecture`

可视化迁移由其维护方使用独立提交完成。

## 验收标准

### 静态边界

- `search_harness/adapter/` 不存在；
- `harness_templates/adapter/` 不存在；
- 旧 Evolution Runner、backend 和 V1 types 不存在；
- V2 源码不引用 `search_harness.adapter`；
- `search_harness.evolution.__init__` 不导出 V1 类型；
- `search_harness.paths` 不包含 V1 Teacher template 常量；
- `search_harness.teacher` 是唯一 Teacher 角色实现。

允许旧名称只出现在：

- `docs/manual_v1/`
- 明确标记为历史的设计文档；
- 不参与运行的旧实验产物。

### 测试

- 使用一条标准命令发现并执行所有测试；
- V2 Teacher tests 全部通过；
- V2 Controller tests 全部通过；
- prefix reconstruction 和 Intervention runtime tests 全部通过；
- experiment fixtures 与当前协议一致；
- Python compile/import 检查通过。

### 行为

- 可启动一个最小 V2 Controller run；
- 可从 V2 events 和 effect artifacts 恢复；
- accepted Harness 可以 rollout 和 evaluation；
- pending candidate 可以 rollout 和 evaluation；
- Intervention Worker 可以从指定 prefix 继续 Student 分支；
- Candidate Reviewer 后的 accept/reject 仍使用 Version Store 事务；
- rollout provenance、replicate 和 seed 语义保持不变。

## 不在本次清理中处理

- 不重新设计八个 Teacher 角色；
- 不改变 Teacher 输出协议；
- 不改变 Actor core loop 或 Hook phase；
- 不改变 Version Store 的 accepted checkpoint 格式；
- 不删除历史文档、历史 rollout、evaluation report 或 accepted checkpoint；
- 不引入 V1 兼容层；
- 不顺手重构与 V1 删除无关的 Teacher runtime；
- 不由核心清理提交修改可视化实现。

