# Candidate Reviewer 影子证据视图 A/B（2026-08-13）

状态：历史 A/B；配对 Case/Trajectory、按需长文本和证据程序已迁入正式 Candidate
Reviewer，影子角色与入口已于 2026-08-14 清理。本文引用的源码路径仅记录实验时环境。

## 1. 实验目的

本实验只改变 Candidate Reviewer 的模型可见输入、查询工具返回视图及已有证据义务的提示词对齐，不修改正式 Candidate Reviewer、底层 Evaluation/Rollout artifact、Candidate 内容、MechanismSpec、输出协议或 Promotion Gate。目标是验证：在保留晋升判断所需事实的前提下，能否降低重复上下文，并保持对目标正向行为、fallback、机制误触发、回归归因、成本和修订边界的判断能力。

## 2. 影子改动

1. 初始输入只呈现一次 Mechanism、Conformance 摘要和 incumbent/candidate/delta 指标；完整 Compiler ValidationReport 不再重复给模型，仅声明精确 Candidate 已通过静态校验。
2. `list_candidate_changes` 默认按绝对变化幅度列出 improved/regressed，unchanged 只给计数并可按 filter 展开。
3. `get_candidate_case` 改为 replicate 配对视图，直接给出 outcome 和 execution delta；删除 `model_calls`、Judge/provider metadata 和重复 token 字段。
4. `get_paired_student_trajectory` 改为自包含配对行为视图，保留 Student tool evidence、parsed action、Hook 决策、实际 context effect、fallback/defer/final/error；删除累计 model input、重复 raw output、reasoning、usage、provenance、`metadata.results` 和 `omitted`。
5. `get_candidate_trajectory_text` 支持按 side、event index、field 精确展开长 tool result、Hook model input/output 或 final answer；默认轨迹只给长度和预览。
6. Harness diff 小于阈值时完整内联，超过阈值时返回变化目录并按 path 展开；模型不可用的 digest 不再呈现。
7. 提示词与程序约束对齐：至少读取目标相关轨迹，存在 improved/regressed 时读取真实 score-changing replicate；`revise` 只能提出一个由现有 Mechanism 授权的有界义务，不得把多项独立重设计打包为一次 implementation 修订。

## 3. 验证素材与方法

- `20260809_base`：单阶段 POST_TOOL Hook，关注目标正例、Hook-model selectivity、非目标误触发和约 93% token 成本增长。
- `20260806_qwen3-8b`：POST_TOOL + PRE_FINAL 双阶段 Hook，关注 withhold/defer/grounded commit、目标改善和正确答案被阻断的伤害。
- 两个案例各完成三次 formal/shadow 配对调用；使用相同已保存 Role Input、Evaluation、Rollout、API 配置、turn budget 和正式输出协议。
- 历史 staging Candidate 目录已经被清理时，实验脚本从同一 Compiler artifact 的 `changed_files` 在实验目录物化只读 Candidate snapshot；不修改源 artifact。
- 另对最终影子提示词和分层长文本工具做了三次回归。

## 4. 结果

前两组配对实验共 6 次 formal 和 6 次 shadow：

| 指标（均值） | formal | shadow | shadow/formal |
| --- | ---: | ---: | ---: |
| total tokens | 340,272 | 172,165 | 50.6% |
| input tokens | 325,881 | 160,881 | 49.4% |
| requests | 7.00 | 6.33 | 90.5% |
| query tool calls | 16.00 | 13.17 | 82.3% |
| paired trajectory calls | 4.00 | 5.17 | 129.2% |
| query result characters | 459,901 | 147,141 | 32.0% |
| trajectory result characters | 398,370 | 101,227 | 25.4% |

Shadow 阅读的轨迹条数没有下降，反而略多；token 下降来自单条证据视图去重，而不是少查决定性案例。所有 12 次配对调用均完成，未出现工具输入错误或结构化提交失败。

`20260809_base` 中，formal 三次为 `reject/revise/revise`，初版 shadow 三次为 `revise/revise/revise`。两者都稳定识别目标正向行为、D.C. Cab 非目标误触发、总体准确率持平和约 93% 成本增长；分歧主要来自 `revise` 边界，而非证据缺失。收紧“一次有界义务”后，最终 shadow 回归三次为 `reject/reject/revise`：两次认为伤害与成本共同要求拒绝，一次认为只收紧已有分类条件即可修复。说明工具视图足以支撑核心判断，但 Candidate Reviewer 对“局部修订还是拒绝”的价值判断仍有模型采样不稳定性。

`20260806_qwen3-8b` 中，formal 三次为 `revise/reject/reject`，shadow 三次均为 `reject`。Shadow 每次都识别到 POST_TOOL withhold、PRE_FINAL defer、grounded commit、目标改善，以及正确答案被过严 grounding gate 转为拒答/错误的机制伤害；未因轨迹压缩丢失双阶段生命周期。

最终版 `get_candidate_trajectory_text` 回归中，模型 3/3 没有调用长文本展开工具，仍能从默认预览和实际 context effect 完成结论。这说明该工具目前主要作为证据可恢复性边界，而不是常规依赖。

## 5. 结论

影子视图在两个不同 Hook 机制上保留了 Candidate Reviewer 的核心证据阅读能力，并把总体 token 降至 formal 的约一半、轨迹返回文本降至约四分之一。它没有重现 Trial/Evidence Reviewer 中“为了结构化而拆碎上下文”的问题：Reviewer 仍一次获得完整的配对行为因果链，并能按案例主动扩大证据覆盖。

当前可接受的部分是输入去重、changed-first 列表、paired case、paired behavior trajectory、长文本按引用展开和 size-aware diff。尚不能仅凭本实验宣称 Candidate Reviewer 决策本身稳定；`revise` 与 `reject` 的边界在 formal 和 shadow 中都存在波动，应作为独立的角色判据问题处理，而不应回退到原始大轨迹。

实验入口为 `experiments/run_candidate_reviewer_ab.py`，影子模板位于 `experiments/teacher_query_views/templates/candidate_reviewer/`，源 artifact 哈希在每次实验摘要中均保持不变。
