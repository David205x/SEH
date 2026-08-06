# V1 实现清理清单

## 状态与目标

**状态：已于 2026-07-31 完成。** 主分支只保留 V2 Active Implementation，
`archive/v1-final` 保存 V1 最后一个完整可运行版本。

### Historical cleanup vocabulary

以下用语只描述已经完成的 V1 清理工作，不属于项目当前领域模型：

- **V2 Active Implementation**：清理完成时主分支唯一保留的可执行 Teacher 角色、Evolution Controller、模板、测试与命令入口。
- **V1 Historical Archive**：只用于追溯旧设计与历史行为的 V1 文档，以及作为完整 run 保留的一份实验记录；不得成为当前运行时依赖。
- **V1 Archive Branch**：指向 V1 仍可完整运行的最后基线提交，只用于恢复和查阅，不接受后续功能维护。
- **Semantic Detachment**：只重建 V2 当时实际依赖的行为语义，使其不再依赖 V1 实现，而不预先决定最终接口和目录。
- **Post-removal Normalization**：V1 实现删除后统一当前项目接口、名称、架构和根命令的阶段。
- **V2 Cleanup Baseline**：V1 移除前用于固化可运行 V2 状态的独立提交。
- **V1 Removal Gate**：清理阶段使用的定向测试、导入检查、残留扫描、完整剩余测试及最小 V2 Controller 闭环门禁。

实际归档与提交：

- V1 archive branch：`archive/v1-final` → `63c094c`；
- 唯一完整 V1 run：`runs/archive/v1/evolution/exp_03`，共 46 个文件；
- 产物归档：`5eed23e`；
- V1 templates、入口和纯 V1 tests 删除：`22031ea`；
- V1 专用可视化删除：`ec9c20b`；
- V2 intervention/evaluation 语义脱钩及剩余实现删除：`cc97f57`；
- 最终验证：标准发现 119 项、Teacher 85 项、template 5 项均通过，V2
  compile/import/CLI smoke 通过。

已确认的边界：

- 主分支删除全部 V1 可执行代码、模板、测试、命令入口和专用可视化；
- 不保留兼容 import、deprecated wrapper 或 V1 命令转发；
- `docs/manual_v1/` 保留为历史档案，不改写各篇正文；
- 只保留一个完整 V1 run，不跨 run 拼接文件；
- V2 实验产物不属于本次清理范围；
- V2 当前依赖的 V1 行为只做最小语义脱钩；
- 全项目最终接口、名称和根入口留到清理后的独立整理阶段决定。

相关决策见 [ADR-0001](../adr/0001-remove-v1-from-main-without-compatibility.md)，
领域术语见仓库根目录 `CONTEXT.md`。

## 清理前代码审计结论

V2 当前仍有三类实际耦合：

1. `search_harness.teacher` 和 Controller 直接导入
   `search_harness.adapter.intervention` 的 prefix 重建、branch bridge、worker 和
   trial runtime；
2. `search_harness.evolution.control.effects` 通过 `LocalEvolutionBackend` 使用
   accepted/candidate rollout 与 evaluation，并使用旧 `CandidateArtifact`；
3. 导入 `search_harness.evolution.control` 时会先执行父包
   `search_harness.evolution.__init__`，该文件当前会主动导入 V1 Runner、Backend
   和 Research Store。

此外，`search_harness.visualizer` 仍包含 V1 专用 Critic、Compiler 和旧
Evolution Runner 页面、API、CLI 参数、解析器与测试。其源码由 archive branch
保存，主分支不另建源码副本。

因此，清理顺序必须是：先删除没有 V2 行为依赖的外围内容，再重写两组共享行为，
最后删除剩余 V1 模块。

## 0. 固化可回滚基线

- [x] 盘点当前 dirty worktree，区分项目变更、本地 IDE 文件、凭据和生成物；
- [x] 确认 `.env`、本机路径和私密配置不进入提交；
- [x] 运行当前 V1 完整入口 smoke test，确认“最后可运行版本”属实；
- [x] 运行当前 V2 定向测试和最小 Controller smoke test；
- [x] 将当前 V2 代码、Teacher templates、测试和文档纳入独立基线提交；
- [x] 从该提交创建只读分支 `archive/v1-final`；
- [x] 记录 archive branch 的 commit hash 和验证结果；
- [x] 切回主分支，并确认后续提交不会合并回 archive branch。

在 archive branch 建立前，不执行任何 V1 移动或删除。

## 1. 先做纯减法

本阶段不重写 V2 行为，只删除 V2 不使用的外围实现和重复产物。每个批次完成后均
执行 V2 import smoke 和受影响的定向测试。

### 1.1 收敛 V1 运行产物

- [x] 将 `runs/experiments/evolution/exp_03` 整体移动到
  `runs/archive/v1/evolution/exp_03`；
- [x] 不修改归档 run 内部内容，接受其中旧绝对路径失效；
- [x] 删除其余 V1 Evolution runs：
  `closed_loop_20260720`、`exp_01`、`exp_02`、`exp_04`、`exp_05`；
- [x] 删除 V1 standalone component logs：`runs/components/critic/`、
  `compiler/`、`intervention_coordinator/` 和 `intervention/`；
- [x] 删除只被上述 V1 Intervention 记录引用的
  `runs/components/actor/candidate_84f16d34_100/`；
- [x] 删除 V1 visualizer 自身的运行日志；
- [x] 删除前再次按 provenance 扫描这些目录，若发现 V2 Controller 或
  `teacher_v2` 来源则停止该项，不得误删；
- [x] 保持 `runs/experiments/evolution_controller_v2/`、
  `runs/experiments/teacher_v2_promotion/` 和 V2 Teacher 产物不变。

选择 `exp_03` 是因为它覆盖两轮 iteration、Intervention continuation、Compiler、
candidate rollout/evaluation、Candidate Review、拒绝路径和明确 run 终态；其他
V1 run 不再保留副本。

### 1.2 删除 V1 templates 与独立入口

- [x] 删除 `harness_templates/adapter/`；
- [x] 删除 `search_harness/adapter/__main__.py`；
- [x] 删除 V1 Critic 和 Compiler 子命令入口；
- [x] 删除 `search_harness/evolution/__main__.py`；
- [x] 只保留 `python -m search_harness.evolution.control`；
- [x] 不把根 `python -m search_harness.evolution` 转发到 V2。

### 1.3 删除纯 V1 tests

- [x] 删除 V1 Adapter CLI、Critic、Compiler 和 Coordinator tests；
- [x] 删除 `tests/evolution/test_runner.py`；
- [x] 删除 `tests/evolution/test_research.py`；
- [x] 暂时保留 prefix reconstruction、Intervention trial 和 V2 Controller 所需
  的行为测试，待第 2 阶段迁入 V2 测试目录；
- [x] 不保留只用于证明 V1 API 兼容性的测试。

### 1.4 移除 V1 专用可视化运行面

- [x] 从主分支删除 `CriticLogStore`、`CompilerLogStore` 和
  `ExperimentRunStore`；
- [x] 删除对应 API、CLI 参数和 V1 artifact 识别逻辑；
- [x] 删除 `critic.html/js`、`compiler.html/js`、`experiment.html/js`；
- [x] 移除其他页面中的 V1 导航链接；
- [x] 删除相应 visualizer tests 和 V1 fixtures；
- [x] 保留通用 Trace、evaluation、Harness version/topology 可视化；
- [x] 本阶段不实现 V2 Controller 可视化替代品。

V1 专用可视化源码仅从 `archive/v1-final` 查阅，不复制到主分支的 archive 目录。

## 2. 对 V2 的 V1 行为依赖做最小重写

### 2.1 Intervention 语义脱钩

- [x] 将 V2 当前使用的 prefix selector、rollout record 加载、时间线重建、
  Hook bridge、跨 activation worker transcript 和单分支 trial 行为重写到
  `search_harness.teacher` 的内部模块；
- [x] 只支持 V2 当前调用，不迁移 V1 Coordinator、工具包装或 result 协议；
- [x] 修改 `teacher/intervention_runtime.py`、`resources.py`、
  `role_resources.py`、`intervention_capabilities.py` 和 Controller imports；
- [x] 修改仍保留的 `experiments/intervention_value_probe.py` import；
- [x] 将有效的 prefix/runtime 测试迁到 `tests/teacher/`；
- [x] 验证 prefix inclusive 边界、模型可见消息、Hook phase、defer/accept、
  activation budget 和 transcript 保持语义一致；
- [x] 不建立通用 runtime registry，不决定最终公共模块名。

完成标准：V2 源码不再导入 `search_harness.adapter.intervention`。

### 2.2 Rollout/evaluation 语义脱钩

- [x] 将 V2 实际使用的 `evaluate_accepted`、`evaluate_candidate` 和
  `rollout_candidate_examples` 重写到 `search_harness.evolution.control` 的内部
  evaluation 模块；
- [x] 配置只保留 V2 当前需要的 Actor、rollout、Judge、并发和错误熔断字段；
- [x] 用 V2 内部结果或直接参数替换旧 `CandidateArtifact`；
- [x] 保持 Experience Set digest、example/replicate ID、seed 策略、Harness
  source provenance、report metrics 和 candidate error streak 行为；
- [x] 让 `LocalControlEffects` 不再实例化 `LocalEvolutionBackend`；
- [x] 将 backend 中只属于 Critic、Compiler、Coordinator 和 V1 proposal/review
  的逻辑全部舍弃；
- [x] 为 accepted version、pending candidate 和 conformance replay 各保留最小
  定向测试；
- [x] 不在本阶段设计最终公共 evaluation service。

完成标准：V2 Controller 不再导入 `evolution.backend` 或 `evolution.types`。

### 2.3 切断父包 import-time 耦合

- [x] 重写 `search_harness/evolution/__init__.py`，停止导出 V1 Runner、Backend、
  Research Store 和 V1 types；
- [x] 不在根包建立新的统一 facade；
- [x] 验证独立导入 `search_harness.evolution.control` 不触发任何 V1 模块。

## 3. 删除剩余 V1 实现

完成第 2 阶段后删除：

```text
search_harness/adapter/
search_harness/evolution/backend.py
search_harness/evolution/runner.py
search_harness/evolution/types.py
search_harness/evolution/research.py
search_harness/evolution/journal.py
search_harness/evolution/progress.py
```

同时完成：

- [x] 从 `search_harness/paths.py` 删除 Critic、Compiler 和 Coordinator template
  常量；
- [x] 删除残留 V1 配置字段、CLI 参数、exports 和 dead imports；
- [x] 删除 V1 `__pycache__`、`.pyc` 和测试缓存生成物；
- [x] 不增加任何兼容包、别名或弃用包装。

`search_harness/evolution/experience.py` 和 `conformance.py` 当前仍服务 V2，不能因
位于同一父目录而整目录删除。

## 4. 文档收尾

- [x] 在 `docs/manual_v1/` 增加目录级 archive 标记；
- [x] 更新该目录 README，说明正文仅作历史参考、命令不再可运行，并记录
  `archive/v1-final` 与归档 run 路径；
- [x] 不逐篇修改 V1 文档正文；
- [x] 更新 `docs/manual_v2/evolution-controller.md`，删除 V1/V2 并存和
  `LocalEvolutionBackend` 复用说明；
- [x] 更新 `teacher-runtime.md`、`evidence-driven-evolution.md` 和
  `framework-mechanisms.md` 中的现状描述；
- [x] 更新 Manual v2 索引，并将本清单状态改为“已完成”；
- [x] 记录实际 archive branch commit、删除范围和最终验证结果。

## 5. 验收门禁

### 每阶段

- [x] 运行受影响的 V2 定向测试；
- [x] 运行 V2 package import smoke；
- [x] 扫描新增的 V1 名称和 import；
- [x] 确认本阶段未触碰 V2 实验产物；
- [x] 保持每个提交职责单一、可独立回滚。

### 最终静态边界

- [x] `search_harness/adapter/` 和 `harness_templates/adapter/` 不存在；
- [x] V1 Runner、Backend、types、Research Store 和根入口不存在；
- [x] 主分支可执行源码、模板、测试和实验脚本中不存在
  `search_harness.adapter`、`EvolutionRunner`、`LocalEvolutionBackend` 等 V1
  依赖；
- [x] V1 名称仅允许出现在 `docs/manual_v1/`、明确标记为历史的设计文档和
  `runs/archive/v1/evolution/exp_03`；
- [x] `search_harness.teacher` 是唯一 Teacher 角色实现；
- [x] `.control` 是唯一 Evolution 执行入口。

### 最终行为

- [x] 使用一条标准命令执行全部剩余测试；
- [x] Python compile/import 检查通过；
- [x] accepted Harness 可以 rollout/evaluation；
- [x] pending candidate 可以 rollout/evaluation；
- [x] Intervention Worker 可以从指定 prefix 继续分支；
- [x] Candidate promotion/rejection 仍使用 Version Store 事务；
- [x] 最小 V2 Controller 闭环 smoke test 完成；
- [x] archive branch 可定位，归档 run 目录完整。

## 6. 明确不在本次完成

- 不统一全项目最终接口和名称；
- 不建立新的根 Evolution 命令；
- 不重新设计 Teacher 角色或其输入输出协议；
- 不改变 Actor Hook phase 和 Version Store checkpoint 格式；
- 不恢复 V1 run 的可继续执行能力；
- 不实现新的 V2 Controller 可视化；
- 不清理 V2 实验产物；
- 不开展与 V1 删除无关的重构。

这些事项统一留到 **Post-removal Normalization** 阶段另行讨论和设计。
