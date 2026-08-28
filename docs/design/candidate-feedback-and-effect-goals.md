# Candidate 反馈回流与效果目标

## 已实施边界

Candidate 失败否定的是一次 Solution Attempt，而不是 Failure Analyst 诊断的
Failure Direction。Controller 先把失败结果交给 Hypothesis Researcher；Researcher
选择修订当前 Research Scheme、建立同一 Failure Direction 下的平行 Scheme，或通过
`reanalyse_failure` 请求 Analyst 建立新的 Failure Direction。一次失败不自动换向。

Controller 为每轮研究维护 `failure_direction_id`、`research_scheme_id`、
`mechanism_scheme_id` 及各层 revision。被拒 Candidate 的全量
Evaluation、rollout、Compiler、Mechanism、Conformance、Candidate Reviewer 与
Outcome Digest 都以 Artifact 引用回流，不把原始轨迹直接放进角色 Prompt。

## Mechanism Effect Goal

`MechanismSpec.effect_goal` 有两个取值：

- `task_outcome`：机制以最终任务结果提升为目标；局部 Conformance 必须观察到至少一项
  可归因任务收益，full Evaluation 必须满足非负准确率增量、至少一个可归因受益逻辑
  样本且没有可归因受害逻辑样本。
- `behavioral_intermediate`：机制只承诺一个可观察的中间行为；局部 Conformance 必须
  观察到该正向行为，full Evaluation 至少覆盖两个目标行为逻辑样本且没有可归因受害
  样本，准确率只作为回归安全下限。

旧 Mechanism Artifact 缺少该字段时按 `task_outcome` 读取。Distiller 创建新草稿时必须
显式选择目标；Conformance Reviewer、Candidate Reviewer 和 Promotion Gate 使用同一
目标，但承担不同证据范围，Conformance 通过不等于 Candidate 可晋升。

## Candidate Outcome Digest

Candidate Evaluation 后、Candidate Reviewer 前生成确定性
`candidate_outcome_digest.json`。它只保存：机制指纹与实现摘要、核心指标和准确率增量、
逻辑样本与 rollout 变化计数、Hook 决策/修改/可归因收益和伤害计数、以及高价值邻近
样本引用。Reviewer 与 Promotion Gate 完成后生成带审查结论的最终副本。底层 Evaluation
和 rollout Artifact 不删减。

邻近样本分为 `beneficial_activation`、`harmful_activation`、
`neutral_activation`、`missed_target`、`parse_failure`、
`false_positive`、
`unattributed_improvement` 与 `unattributed_regression`。Digest 只保存
`example_id/replicate_id`，详细 Case 和配对轨迹通过工具按需读取。

## 角色读取与 Trial Selection

Failure Analyst 和 Hypothesis Researcher 在存在上一 Candidate 时可调用：

- `get_recent_candidate_digest()`：读取紧凑总体效果与邻近样本索引；
- `list_recent_candidate_cases(category, page, page_size)`：列出某类邻近样本；
- `get_recent_candidate_case(example_id)`：读取逻辑样本的配对 Evaluation；
- `get_recent_candidate_trajectory(example_id, replicate_id)`：读取压缩后的配对行为轨迹；
- `get_recent_candidate_implementation()`：读取上一 Compiler 的方案摘要和未解决风险。

Analyst 只用这些信息复核行为模式是否仍成立以及范围是否应收窄，不设计新方案。
Researcher 必须感知上一方案；重复同一方案族时必须有新的边界、新证据或实质不同的
介入方法。Trial Selector 会将适用的邻近样本映射回对应 incumbent rollout prefix，
每批最多优先占用一半名额，其余名额仍按冻结 Hypothesis 和现有覆盖规则选择。

## 配置

`config/runtime.yaml` 分别提供两种效果目标的准确率、可归因收益/伤害与目标行为覆盖
阈值。`min_accuracy_delta` 保留为读取旧 Run 配置和无 Outcome Digest 的兼容下限；新
正式 Run 使用目标专用阈值。

## 2026-08-15 Artifact 与真实 API 验证

验证复用了 `20260815_qwen3-8b_hook_feasibility` 的 incumbent、两个 Candidate
Evaluation、Mechanism、Compiler、Conformance 和 Candidate Review Artifact；没有修改
原实验产物，也没有重新运行 Student。新增结果位于：

- `runs/experiments/20260815_candidate_feedback_roles_smoke/`
- `runs/experiments/20260815_candidate_feedback_roles_repeat/`

五个受影响角色各独立运行三次，15 次均通过输出协议。Failure Analyst 三次都读取
Candidate Digest，保留了“一侧实体未检索便完成双实体判断”的核心问题方向；两次主动
列出邻近案例，一次只用 Digest 后回到 incumbent 证据核查。它们在适用范围宽窄上仍有
自然波动，但没有因单次 Candidate 拒绝盲目换方向。

Hypothesis Researcher 三次都读取 Digest 与上一 Compiler 实现，并按需读取 Candidate
Case/Trajectory。三次均将上一方案的 `pre_final` 终答拦截改为 `post_tool` 的预防式
Student-visible 引导，同时保留自然恢复负样本义务，体现了“问题方向保留、方案尝试改变”。

Mechanism Distiller 三次都把现有 Trial 证据标为
`behavioral_intermediate`，没有把“促使 Student 继续搜索”升级成未经测量的任务正确率
收益。Candidate Reviewer 在旧 Mechanism 按 `task_outcome` 解释时三次均拒绝，且一致
指出 0 个可归因受益逻辑样本、1 个可归因受害逻辑样本、全量准确率下降和 Hook 成本
上升；每次仍读取必要的 changed cases 与 paired trajectories，没有只凭 Digest 下结论。

Conformance Reviewer 对同一负向控制批次三次都给出三条 faithful/neutral Finding，并将
`target_behavior_observed` 全部设为 `false`，说明正确 fallback 不再被误当成正向机制
行为。用旧 12 条 Finding 确定性回放两个 Candidate 时，两者均从旧逻辑的 `pass` 变成
`revise → evidence`，因为各自 12 条局部结果全为 neutral。若新逻辑当时已存在，可在
225 条 full Candidate rollout 前拦截后续评估；历史两次 full Evaluation 分别消耗
855,992 与 1,338,154 token。

Candidate Outcome Digest 对两个 Candidate 的回放结果分别为：Candidate 1 有 11/12/52
个逻辑样本 improved/regressed/unchanged，Hook 14 次修改涉及 11 个逻辑样本，0 个可归因
受益、1 个可归因受害；Candidate 2 为 7/13/55，Hook 7 次修改涉及 4 个逻辑样本，1 个
可归因受益、1 个可归因受害。Digest 的“修改且分数变化”只是确定性候选归因索引，不是
最终因果证明；Candidate Reviewer 仍必须用 paired trajectory 核实。

用烟测 Researcher 的新 `post_tool` Hypothesis 回放 Trial Selector 时，4 个名额中的前
2 个来自上一 Candidate 的 `harmful_activation` 和 `neutral_activation` 邻近样本，后
2 个回到 Analyst 原证据，符合“邻近样本至多占半批”的设计。

三次调用的平均 Teacher token 分别为：Failure Analyst 97,091、Hypothesis Researcher
141,910、Candidate Reviewer 219,436、Mechanism Distiller 166,660、Conformance
Reviewer 13,072。本次目标是语义稳定性而非压缩；前三类角色的高成本仍是后续独立优化
项，不能通过删除关键证据来掩盖。
