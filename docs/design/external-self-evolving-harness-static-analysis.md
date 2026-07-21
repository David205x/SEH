# 外部自进化 Harness 静态代码调研

## 范围

本调研下载并静态分析 `teacher-guided-harness-discovery.md` 第六章列出的公开工作。源码镜像及固定 SHA 在 `research/external_harness_works/CATALOG.md`；未安装依赖、未运行任一外部项目、模型或 benchmark。Self-Harness 未找到可确认的官方源码，边界记录在 `research/external_harness_works/self-harness/NOTES.md`。

深度报告：

- `research/external_harness_works/analysis/meta_harness_and_gepa.md`
- `research/external_harness_works/analysis/adas_and_agent_square.md`
- `research/external_harness_works/analysis/code_evolution_and_versioning.md`
- `research/external_harness_works/analysis/continual_adaptive_and_weights.md`

## 横向结论

| 工作 | 搜索对象 | 历史注入方式 | 接受/稳定机制 | 主要边界 |
|---|---|---|---|---|
| Meta-Harness | 完整 Harness 源码 | 文件系统、summary、frontier、报告 | import/smoke、validation/test 隔离、Pareto | 开放式代码编辑，候选文件不总回滚 |
| GEPA | 组件化文本映射 | trajectory -> reflective dataset，谱系与 Pareto state | minibatch 严格提升、full validation、cache、stoppers | full validation 变差不二次否决 |
| ADAS | 完整 agent architecture JSON | 整个 archive 直接拼入 proposer prompt | reflexion、debug retry、固定代数 | 成功即入 archive，失败结构化不足 |
| AgentSquare | 四类 module 与组合 | module archive + 最后 feedback；tested combinations | 单模块严格提升、组合 predictor | 无限格式 retry、固定轮数、工具模块在主路过滤 |
| A-Evolve / DGM | workspace 或完整代码 | history/version/archive、评估日志 | git/worktree、分层评估、阈值或 rollback | 停止和稳定化不等于理论收敛 |
| Continual / Adaptive / SIA | prompt/skills/memory、Harness tree、部分权重 | 在线轨迹窗口、历史、路由状态 | cadence、阈值、分支/路由隔离、超时 | 多项门禁未必接入论文主路径；权重更新超出当前范围 |

## 对 Search Harness 的建议

1. 将候选统一记录为“parent、patch、组件清单、逐样本 metrics、trace 引用、成本、接受状态”，借鉴 GEPA 的证据契约。
2. 把 Critic 的失败模式、Compiler 的机制选择和 Version Store 的 patch 关联为可查询 journal；失败必须可见但不进入 accepted version。
3. 采用两阶段评估：小样本/定向案例用于筛选，完整 validation 或 holdout 具有最终接受/拒绝权；不要让小样本提升自动变成版本接受。
4. 将停止原因单独编码为 `budget_exhausted`、`patience`、`no_valid_candidate`、`no_novel_candidate`、`safety_block`、`manual_stop` 等。固定轮数、plateau、archive 或 rollback 都不是理论收敛证明。
5. 在 plugins 上显式声明 evolvable scope，并由 Version Store 在执行层强制 fixed 边界；不要只依赖 prompt 约束。
6. 当前不引入开放式全代码自改、在线无重置 CRUD、权重更新、并发树搜索或多 Harness 路由。它们都需要更强的隔离、评估和版本协议。

## 与当前 Hook 设计的连接

AgentSquare 的模块化搜索支持把当前插件层理解为“prompt、tool、extension”三类候选，而非只优化 system prompt。GEPA 的 component-level trajectory feedback 则适合本项目的 Hook：proposal 应声明它读取何种 state、改写何种 stage、预期影响哪个 failure class，并由 trace 提供逐样本验证。Meta-Harness/ADAS 的经验同时说明，不应把全部历史直接塞进模型上下文；应通过分页工具、摘要与目标案例选择向 Critic/Compiler 渐进暴露。
