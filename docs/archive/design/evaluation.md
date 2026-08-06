# 评估体系

## 文档职责

本文档说明 Search Harness 的数据划分、评估协议、指标体系、反馈可见性和成功判据。

本文档回答“如何判断 Harness 是否真的变好”，不展开 Actor Runtime、Adapter 角色或 Patch 提交流程。Actor 运行机制见 `actor-harness.md`，Adapter 机制见 `adapter-harness.md`，Patch 闭环见 `evolution-protocol.md`，数据泄漏与权限规则见 `governance.md`。

## 评估目标

评估体系需要同时服务两个目标：

1. 判断当前 Actor Harness 是否提升了小模型的 Search Agent 能力；
2. 判断某个 Harness Patch 是否值得进入后续迭代。

第一阶段以正确率为主，但不能只看正确率。一个 Patch 即使提高了某个集合上的正确率，也可能带来过拟合、成本上升、输出格式退化、工具调用失控或 Blind-OOD 退化。

因此，评估应同时关注：

- 任务正确率；
- Regression；
- 成本；
- Trace 行为；
- 输出结构和工具调用稳定性；
- Soft-to-Hard 进化过程；
- 数据可见性和反馈泄漏风险。

## 数据划分

第一阶段数据划分按用途和可见性分为三类。

### Experience Set

Experience Set 是开发经验集，用于让 Adapter 进行 label-visible 失败分析和离线适配探索。

用途包括：

- 收集 Actor-only 轨迹；
- 分析失败模式；
- 进行 label-visible 诊断；
- 探索 Soft Intervention；
- 形成 Hardening Candidate；
- 支持 Compiler 形成 Patch 方向。

对 Adapter 的可见性：

- 可见输入样本；
- 可见 Golden Answer；
- 可见完整 Actor Trajectory；
- 可做深度失败分析。

限制：

- Experience Set 中看到的题目级信息不得进入 Adapter Long-term Memory；
- 题目文本、答案、实体、文档 ID、证据路径不得通过 Role Handoff 传给不应看到这些信息的角色；
- Experience Set 只能沉淀为抽象 Failure Pattern、输出结构问题、Harness Gap 和通用改进方向。

### Visible-ID Eval Set

Visible-ID Eval Set 是可见同分布评估集，用于检查 Patch 是否在非 label-visible 样本上有效。

用途包括：

- 每次 Patch 通过 Audit 后进行同分布验证；
- 检查 Patch 是否只对 Experience Set 有效；
- 提供有限反馈，辅助 Critic 作出 Patch Decision。

对 Adapter 的可见性：

- 可见输入问题；
- 可见 Actor Trajectory，但具体粒度待定；
- 可见 0/1 正误；
- 不可见 Golden Answer；
- 不可见结构化错误标签。

Visible-ID Eval Set 用于观察同分布泛化能力，但不向 Adapter 泄漏答案或详细错误类型。

### Blind-OOD Eval Set

Blind-OOD Eval Set 是盲测域外评估集，用于检查 Harness 是否过拟合已知分布。

用途包括：

- 检查 Harness 是否在分布外保持能力；
- 观察是否出现对 Experience Set 或 Visible-ID Eval Set 的过拟合；
- 为 Patch Decision 提供更严格的泛化信号。

对 Adapter 的可见性：

- 不可见样本；
- 不可见 Actor Trajectory；
- 不可见 Golden Answer；
- 只返回 aggregate score。

Blind-OOD Eval Set 不应成为 Adapter 可分析的样本集合。它提供的是整体泛化信号，而不是可用于继续调参的详细反馈。

### Final Holdout

Final Holdout 原则上应该存在，但第一阶段暂不作为阻塞项。

如果后续目标是形成更严谨的实验报告或论文式结果，建议增加一个最终只运行一次的完全盲测集。Final Holdout 不参与 Patch Selection，只用于最终评估。

## Baseline 与对照

评估至少需要比较以下系统形态：

- Actor-only Baseline：小模型 Actor + 固定 Core Loop + 初始 Harness；
- Current Hard Harness：小模型 Actor + Core Loop + 当前已接受 Registry Extensions；
- Actor + Soft Intervention：离线适配阶段外部强模型提供受控 Soft Guidance 的上界参考；
- Final Hard Harness：最终不调用外部强模型的 Actor Harness。

其中，最终可部署系统只能是 Hard Harness。Soft Intervention 结果只用于分析软干预上界和指导 Hardening，不代表部署性能。

## 每次 Patch 后的评估流程

每次 Patch 提交后，系统应按以下顺序处理：

1. Audit；
2. Experience Set 回放或抽样评估；
3. Visible-ID Eval Set 评估；
4. Blind-OOD Eval Set 评估；
5. Regression 检查；
6. Cost 统计；
7. Trace 统计；
8. Patch Result 填充；
9. Critic 执行 Patch Decision。

只有 Audit 结果为 `passed` 的 Patch 才能进入 Controlled Evaluation。Audit 结果为 `rejected` 的 Patch 不得进入当前 Harness。

## 主指标

第一阶段以正确率为主。

具体指标可以根据数据集和 Evaluator 选择：

- Exact Match；
- F1；
- answer accuracy；
- evidence-supported accuracy。

当前文档阶段不固定唯一正确率实现。实现时应在实验配置中明确 Evaluator 如何判定答案正确。

本文档中如无特别说明，“性能提升”默认指测试集和评估集上的正确率提升。

## Regression 指标

Regression 不只看总体分数，也应关注局部行为是否退化。

Regression 检查包括：

- 已成功样本是否变失败；
- 输出结构或工具调用格式错误是否上升；
- tool call 是否失控；
- token cost 是否大幅上升；
- premature answer 是否增加；
- 搜索次数是否异常增加；
- final answer 格式是否退化；
- 低级执行错误是否重新出现。

Regression 的具体阈值暂不固定，应在实验配置或后续文档中定义。

## 成本指标

成本初期权重较小，在正确率进入平台期后再重点优化。

成本指标包括：

- token count；
- model calls；
- tool calls；
- search calls；
- latency；
- average rollout length；
- cost per successful answer。

Patch Decision 时，成本上升不一定直接导致拒绝，但如果成本上升明显且正确率收益有限，应视为风险。

## 稳定性指标

稳定性指标用于观察 Actor 是否更容易被 Harness 稳定引导。

包括：

- pass@k over guidance；
- pass@k over actor sampling；
- invalid action rate；
- parser failure rate；
- output structure repair rate；
- retry rate；
- final answer format validity。

`pass@k over guidance` 用于比较同一 Prefix 下不同 Soft Guidance 的效果。

`pass@k over actor sampling` 用于评估同一 Guidance 下 Actor 成功是否依赖偶然采样。

具体 `k` 值暂不固定，记录在 `open-decisions.md` 或实验配置中。

## Harness 进化指标

Harness 进化指标用于判断“软干预是否逐步硬化为有效结构”。

建议重点报告：

1. Intervention Rate Decay：外部模型每条轨迹或每个 step 平均干预次数是否下降；
2. Soft-Hard Gap Closing：Hard Harness 是否逐渐接近 Soft-advised upper bound；
3. Patch Acceptance Rate：提出的 Patch 有多少通过 Audit 和 Evaluation；
4. Patch Effect Size：每类 Patch 对正确率、成本、稳定性的影响；
5. Failure Type Shift：失败类型是否从低级输出结构、parser、tool call 错误转向更高层语义错误；
6. Registry Growth Curve：Harness 扩展数量和性能提升之间的关系。

推荐绘制三条核心曲线：

- Actor-only with current hard harness；
- Actor + Soft Intervention；
- Final hard harness without external adapter。

理想现象是：

- Hard Harness 分数逐渐上升；
- Soft Intervention 额外收益逐渐下降；
- Intervention Rate 下降；
- Soft-Hard Gap 缩小。

## Failure Taxonomy

系统应维护可扩展 Failure Taxonomy，用于分析失败类型变化。

初始类别可以包括：

- query formulation failure；
- insufficient search；
- over-search；
- duplicate search；
- wrong document selection；
- evidence extraction failure；
- missing bridge entity；
- contradiction unresolved；
- premature final answer；
- hallucinated evidence；
- invalid tool call；
- parser failure；
- output structure violation；
- memory pollution；
- verifier failure；
- budget exhaustion；
- answer synthesis error；
- citation mismatch；
- unable to recover from empty result；
- context overflow。

Critic 可以提出新增类别，但新增类别应进入 taxonomy registry，并经过审计和版本化。

## 评估反馈可见性

评估反馈进入 Adapter 前必须经过数据可见性控制。

不同数据划分的反馈可见性如下：

| 数据划分 | 输入样本 | Golden Answer | Actor Trajectory | 正误结果 | 错误类型 | Aggregate Score |
| --- | --- | --- | --- | --- | --- | --- |
| Experience Set | 可见 | 可见 | 可见 | 可见 | 可分析 | 可见 |
| Visible-ID Eval Set | 可见 | 不可见 | 可见，粒度待定 | 可见 | 不可见 | 可见 |
| Blind-OOD Eval Set | 不可见 | 不可见 | 不可见 | 不可见 | 不可见 | 仅可见 |

这些限制用于防止 Adapter 利用评估集反馈逐步恢复答案、证据路径或样本级 shortcut。

## Patch Decision 中的评估使用

Critic 在 Patch Decision 中可以读取：

- Patch 变更摘要；
- Audit 结果；
- Controlled Evaluation 结果；
- Changelog；
- 必要的轨迹证据；
- 版本历史。

Critic 应根据评估结果决定：

- 接受 Patch 并在新 Harness Version 上继续迭代；
- 拒绝 Patch 并保留当前 Harness Version；
- 选择某个先前已接受 Harness Version 继续迭代；
- 要求 Compiler 修改方向或拆小 Patch。

具体接受阈值暂不固定。第一阶段可以先采用定性规则和简单指标组合，后续再根据实验稳定性细化。

## 成功判据

当满足以下前提时，实验结果才具有解释意义：

- 未发生数据泄漏、评估篡改或审计绕过；
- 实验状态、数据可见性和评估过程符合既定协议；
- Rollout、Prefix-Fork 和 Harness Version 具有可追踪性与可复现性。

在此前提下，如果观察到以下现象，则认为实验结果支持项目假设：

- Soft Intervention 能稳定改善 Actor 行为；
- 有效干预能够被硬化为 Registry Extension；
- 最终 Hard Harness 在不调用外部强模型的情况下，相比 Actor-only Baseline 获得正确率提升；
- Hard Harness 在测试集和评估集上整体正确率提升，同时 Blind-OOD Eval Set 不出现明显退化；
- 随着 Harness Patch 积累，外部干预率下降，Soft-Hard Gap 缩小；
- Actor 的低级失败减少，失败类型逐步转向更高层的语义问题。

如果后续开展多模型实验，还可以进一步验证：

- 针对不同基础模型进化出的 Harness 是否存在可识别差异；
- Model-specific Harness 是否比 Generic Harness 更适合对应模型；
- 不同模型的 Harness 是否能够相互迁移。

## 未决事项

以下事项仍需要后续确认或在实现中细化：

- 主正确率指标采用 Exact Match、F1、answer accuracy 还是 evidence-supported accuracy；
- Regression 阈值；
- Cost 阈值；
- Blind-OOD 退化容忍范围；
- pass@k 的具体 k 值；
- Visible-ID Eval Set 的 Actor Trajectory 可见粒度；
- Final Holdout 是否进入第一阶段；
- Failure Taxonomy 的初始最小集合；
- Patch Decision 的量化接受标准。
