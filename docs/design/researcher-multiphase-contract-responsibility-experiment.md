# Researcher 多 Phase Contract 职责 A/B 实验

## 目的

评估在不修改 `InterventionHypothesis` 协议的前提下，为 Hypothesis Researcher 增加两项条件式职责是否影响角色稳定性：

1. 同一 activation 同时需要 Trial state 和终态动作时，必须把指令写成“先单独更新 state 并等待成功，再在后续响应提交终态动作”的顺序。
2. 多阶段 readiness 只能由当前 phase 可观察的证据谓词建立，不能仅用检索次数、phase 到达或动作完成代替 evidence obligation 已满足。

这两项只约束 Researcher 已经选择的多 phase/stateful 方案，不要求其使用 Trial state，也不鼓励把足够的单 phase 假设扩成多 phase。

## 可插拔实现

正式 `harness_templates/teacher/hypothesis_researcher` 保持不变。实验脚本在 run 目录内复制正式 Teacher Template，并只向 shadow Template 的 `system.md` 插入 `Multi-phase contract discipline` 小节；Role Runner 通过 `template_root` 选择 baseline 或 responsibility 变体。

这样可以同时验证：

- Prompt 增量能否被标准 Assembly/Role Runner 直接加载；
- 较差变体可以整目录删除，不需要回滚正式角色；
- 两个变体使用相同输出协议、工具、模型配置、输入 artifact 和资源视图。

## 冻结输入

每个变体对每个输入独立运行三次：

1. `one_sided_comparison`：已有具体、边界清晰的比较失败。用于检查新增职责是否让合理的单 phase 假设无故复杂化。
2. `bundled_missing_relation`：一次 bundled query 未召回决定性关系后直接给出 cannot-determine。用于观察 Researcher 是否选择 decomposition、多 phase 或 stateful 方案；若选择，则审查顺序与 evidence predicate。

若六份 responsibility 输出均合理保持单 phase，则结论只能证明“未见简单职责回退”，不能证明新增多 phase 指导生效；是否追加 continuation 压力测试由首轮结果决定，不预先强迫 Researcher 选择复杂方案。

## 稳定性口径

- 协议：三次均完成并通过 `InterventionHypothesis` 校验。
- 边界：Failure Direction 的 decisive predicate、caveat 和纠正性/预防性时间边界不退化。
- 复杂度：简单输入不无故增加 phase、state 或 activation。
- 多阶段职责：若输出包含多个 phase 或 Trial state，则逐项检查 state-before-terminal 顺序、后续 state condition、基于真实结果的 evidence readiness 和 falsifier。
- 一致性：比较三次 strategy family、fork phase、phase count 和关键 activation boundary 的分歧。
- 成本：记录 requests、input/output/total token 和工具读取序列；成本不抵消语义失败。

程序只汇总结构和用量，不用关键词门禁替代语义审查。

## Fail-fast

- Shadow Template 无法通过正式 loader/contract 时停止，不修改正式 Researcher 迁就实验。
- 新职责导致具体 Failure Direction 边界稳定退化时，不迁移该 Prompt。
- 首轮没有产生多 phase 输出时，不把“未观察到回退”误报为复杂职责已经验证。

## 产物

- 脚本：`experiments/validate_researcher_multiphase_responsibility.py`
- run：`runs/experiments/20260816_researcher_multiphase_responsibility/`
- 结果报告：本文件的“执行结果”部分。

## 执行结果

### 静态与装配结果

可插拔实现已经完成。Baseline 和 responsibility Template 均通过正式 `prepare_role_run` 装配，二者共享 `intervention_hypothesis` 输出协议和 14 个查询/提交工具；仅 `harness_id` 与 system Prompt 不同。Baseline Prompt 为 10,265 字符，responsibility Prompt 为 11,483 字符，增量约 11.9%，没有新增输出字段。

### 预期稳定性影响

- 对单 phase 假设影响应较低：新增小节明确禁止仅为满足指导而增加 state、phase 或重复 activation，原有最小复杂度原则不变。
- 对多 phase 假设影响中等：Researcher 需要同时表达 phase-visible condition、state 更新顺序、terminal action、readiness predicate 和 unsupported-result 分支；这些本来属于“自包含 operational contract”，但会增加 instruction 长度与注意力竞争。
- 最大风险不是协议失败，而是策略偏置：模型可能因为新指导更常选择 multi-phase/stateful 方案，或把实现级工具顺序写得过细。A/B 因此把“简单输入不复杂化”列为独立门禁。
- 当前正式 Researcher 在同一 one-sided Failure Direction 的三次既有运行中，曾产生 1 次 preventive `post_tool` 与 2 次 corrective `pre_final`。三者边界均可解释，但 phase/strategy 本就存在波动；新 Prompt 不能只以协议通过率评价，必须看这种分歧是否扩大。

### 真实 A/B 结果

2026-08-16 在冻结 Template 和原实验目录上完成真实 A/B。两个 case、两个 variant 各运行三次，共 12 次；全部形成完整 artifact，并通过当前 `InterventionHypothesis` 结构校验。12 次使用完全相同的 DeepSeek 模型配置；同一 case 在两个 variant 间的角色输入和 resource config digest 相同，Template 的语义差异仅为 responsibility system Prompt 增量。

| Case | Variant | 完成 | fork anchor → phase plan | 首次提交通过 | 平均 requests | 平均 total tokens |
| --- | --- | ---: | --- | ---: | ---: | ---: |
| `one_sided_comparison` | baseline | 3/3 | 3 × `pre_final → pre_final` | 2/3 | 3.0 | 50,573 |
| `one_sided_comparison` | responsibility | 3/3 | 2 × `pre_final → pre_final`, 1 × `post_tool → post_tool` | 0/3 | 4.3 | 104,393 |
| `bundled_missing_relation` | baseline | 3/3 | 3 × `pre_final → pre_final` | 1/3 | 4.0 | 73,667 |
| `bundled_missing_relation` | responsibility | 3/3 | 2 × `pre_final → pre_final`, 1 × `post_tool → pre_final` | 0/3 | 4.0 | 88,892 |

所有 12 份输出实际上都是单 phase、单 activation，均未设计 Trial state。`summary.json` 将 baseline 的一份结果标记为 `mentions_trial_state=true` 是关键词误报：原文只出现了普通动词 `states` 和短语 `state precisely`，没有 Trial state、状态读写或跨 phase 传递。因此本轮没有直接测试新增指导所针对的 state-before-terminal 顺序和 evidence-based readiness；只能检查该指导是否干扰原本足够的单 phase 方案。

两套方案都保留了 Failure Direction 的核心边界：不把单次未召回当作语料不存在，不虚构真实属性值，并区分纠正性 `pre_final` 与预防性 `post_tool`。Baseline 六份输出全部选择纠正性 `pre_final`；responsibility 有一份 `one_sided_comparison` 选择可解释的预防性 `post_tool`，其余仍为纠正性 `pre_final`。这说明新增指导没有诱发无必要的多 phase/state 复杂度，但 strategy/phase 一致性也没有改善。

Responsibility 的一份 `bundled_missing_relation` 使用 `post_tool` fork anchor，但唯一干预 phase 为后续 `pre_final`。这不是内部矛盾：正式协议明确 `fork_phase` 是恢复执行的锚点，可以早于首个实际干预 phase；运行时会从 `post_tool` prefix 恢复，并在到达 live `pre_final` 时激活 Worker。该方案只是比直接从 `pre_final` 恢复得更早，增加了分支重放范围。按协议与人工语义口径，两套 variant 均为 6/6 合格。

格式稳定性同样下降。Baseline 共发生 4 次提交校验失败，3/6 首次提交成功；responsibility 六份输出全部至少因长度上限失败一次，共发生 6 次失败，0/6 首次提交成功。主要超限字段为 `applicability`，部分结果还同时超出 `activation_condition` 或 `special_evidence_obligations[].obligation`。Responsibility 相比 baseline 的平均 requests 从 3.5 增至 4.2；六次运行总 token 从 372,719 增至 579,855，增加约 55.6%。其中 `one_sided_comparison` 平均 token 增加约 106.4%，`bundled_missing_relation` 增加约 20.7%。样本量较小且角色调用轮数波动较大，不能把全部差额精确归因于 Prompt 增量，但当前没有观察到足以抵消该成本的语义收益。

### 结论

本轮证明 responsibility Prompt 可被正式装配和执行，也没有把简单方案普遍推向过度设计；但它没有触发任何真正的多 phase/state 合同，因而没有验证目标职责。与此同时，它带来了更频繁的长度修复和更高的调用与 token 成本，且没有观察到相应的语义收益。**当前证据不足以把该 shadow Prompt 迁移至正式 Researcher。** 若继续验证，应使用确实需要跨 phase/state 的冻结 Failure Direction 或 continuation 压力输入，并先减少字段长度修复造成的额外轮次；不能用本轮 12/12 completed 代替目标职责已经验证的结论。

## Stateful 定向复验

为避免把自然的单 phase 选择误当成多 phase 指导失败，脚本新增 `stateful_delayed_control` 受控压力 case。它复用 `one_sided_comparison` 的真实 Failure Direction、轨迹和资源，但在两套 shadow Template 的 user Prompt 中加入相同实验约束：

1. `post_tool` 只记录 `one_sided_result_observed` 和 `missing_entity_name` Trial state，不修改 Student-visible context，以保留自然恢复机会；
2. `pre_final` 同时检查上述 state 和当前可见证据，仅当 Student 没有搜索缺失实体且仍从单侧证据完成比较时才 defer；
3. `post_tool` activation 内必须先单独更新 state、等待成功，再在后续 Worker response 调用 `continue_without_change`。

这个 case 测试 Researcher 能否写清 state hand-off、当前证据复查、自然恢复分支及完整 falsifier，不用于证明生产方案应优先采用 Trial state。Baseline 与 responsibility 仍使用相同输入、资源和 case addendum，只相差 `Multi-phase contract discipline` system Prompt。

同时将本协议中最常触发无意义修复的三个硬上限适度放宽：`activation_condition` 从 350 到 400 字符，`applicability` 从 400 到 500 字符，evidence obligation 的 `obligation`/`rationale` 从 240 到 300 字符。其他字段保持不变；正式 Prompt 中更低的建议目标长度也保持不变，继续鼓励简洁表达。

将上一轮 12 份 artifact 的第一次 `submit_intervention_hypothesis` 参数离线重放到新协议后，12/12 均一次通过；旧协议下对应结果为 3/12，说明本轮已观察到的提交修复可由这次有界放宽消除。该离线结果不预测新复杂 case 的语义质量，也不替代真实 A/B。

只运行定向 A/B 的命令为：

```powershell
D:\ProgramData\miniconda3\envs\env_search_harness\python.exe -m experiments.validate_researcher_multiphase_responsibility --case stateful_delayed_control --repetitions 3 --output-dir runs/experiments/20260817_researcher_multiphase_stateful --env-file .env
```

该命令产生六次真实 Researcher 调用。`summary.json` 只记录预期 phase shape、明确 Trial-state marker 和两个状态键是否出现在输出中，不把关键词匹配当作语义门禁；最终仍需逐份检查 state-before-terminal 顺序、后续 evidence predicate、自然恢复 no-op 分支及 success/falsifier 是否一致。

### Stateful 定向复验结果

2026-08-17 完成 baseline 与 responsibility 各三次真实调用。六次使用同一模型配置、同一 `FailureDirection` 输入和同一 resource config；全部形成有效 `InterventionHypothesis`，并均选择 `post_tool` fork、`post_tool → pre_final` 两个 phase、两个预期状态键和 answer-neutral delayed control。两套方案 3/3 都在 `pre_final` 同时检查先前 state、后续是否搜索缺失实体，以及当前 candidate 是否仍从单侧证据完成比较；自然恢复路径均可不 defer。

| 检查项 | Baseline | Responsibility |
| --- | ---: | ---: |
| 完成并通过最终结构校验 | 3/3 | 3/3 |
| 精确双 phase shape 与两个状态键 | 3/3 | 3/3 |
| 当前证据与 state 联合 readiness | 3/3 | 3/3 |
| state update 与 terminal 的同 activation 顺序正确 | 2/3 | 3/3 |
| `post_tool` 保持一次 activation | 2/3 | 3/3 |
| 首次提交通过 | 1/3 | 1/3 |
| 提交修复次数 | 4 | 3 |
| 平均 requests | 4.0 | 4.3 |
| 平均 total tokens | 79,002 | 100,589 |

Baseline 第 2 份把 `post_tool.max_activations` 设为 2，并写成 state 更新成功后“在这个 phase 的下一次 activation”调用 `continue_without_change`。当前 Worker runtime 的正确语义是：`update_trial_state` 为非终态工具，Tool Result 返回后仍处于同一次 activation，Worker 必须在后续 response 提交 terminal action 才能结束本次 activation。该 baseline 指令会让 Worker 不清楚当前 activation 如何终止，也可能把一次 state hand-off 错拆成两次 Hook activation。Responsibility 三份均明确写成“单独更新、等待 `TRIAL_STATE_UPDATED`、在后续 Worker response 调用 terminal”，且 phase budget 均为 1。因此新增指导在其目标场景上把操作协议稳定性从 2/3 提升到 3/3。

有界放宽消除了上一轮已观察到的长度失败，但没有让新的复杂方案稳定一次提交。Baseline 的新失败分布到 `evaluation.primary_signal`、`success_condition` 和略超 500 的 `applicability`；responsibility 有一份略超 400 的 condition、明显超 300 的 obligation，另一次是原生工具参数 JSON 损坏后又错误包装 `arguments`。两组首次提交率同为 1/3，说明在当前复杂 case 下，responsibility Prompt 没有继续表现出更差的提交通过率，但复杂自由文本协议本身仍有明显修复负担。

Responsibility 的三次总 token 为 301,767，baseline 为 237,007，均值高约 27.3%，中位数高约 17.5%。Responsibility 的提交修复反而少一次，因此差额不能只归因于校验重试；更长 system Prompt、更多分步推理和单次运行波动共同参与。三次样本不足以给出稳定成本比例，但目前没有节约成本的证据。

定向复验改变了首轮“目标职责未被触发”的证据状态：现在已经观察到 responsibility 指导对 state-before-terminal 顺序的正向作用，而且没有损害 phase readiness 或自然恢复边界。该证据支持保留并进一步压缩这段职责指导，但还不能证明实际 Worker 执行稳定，因为本脚本只评估 Researcher 合同、没有运行 Intervention Worker。正式迁移前应使用这六份 hypothesis 中的代表输出做一次 Worker 联调，核实单工具响应、state 持久化和自然恢复 no-op；提交格式稳定性应作为独立问题处理，不应通过继续无限提高所有字符串上限掩盖。
