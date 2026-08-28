# Shadow Conformance 真实 API 验证（2026-08-28）

## 验证范围

- Shadow Mechanism：`runs/experiments/20260828_0827_shadow_distiller_source_fix_v2/experiments_current/shadow/run_001/role.json`。
- Shadow Compiler Candidate：`runs/experiments/20260828_0827_shadow_compiler_manual_run/run_001/role.json`。
- Source Run：`runs/0827_debug`，包含 8 个不同 Trial Example。
- 最终运行：`runs/experiments/20260828_0827_shadow_conformance_final/`。

程序建立独立 Version Store，物化 Candidate，并对 8 个 Example 各运行 3 条 Student rollout。24 条 rollout 均完成且无 runner error；随后执行生产 Evaluation 和 8 个 Example-level Shadow Reviewer batch。上游 Artifact 哈希保持不变。

## 最终结果

- Suite decision：`revise`。
- Findings：22 条 `faithful`，2 条 `implementation_mismatch`。
- 两条 mismatch 均为 `evaluator`：在 guards 成立且可见输入满足 positive boundary 时，managed Hook model 返回 `negative`，导致未 defer。
- 两条 mismatch 均路由 `evidence`；`compiler_feedback` 为空，因为 Candidate 使用了正确 projection、adapter、target、state 与 action，Compiler 无权修改冻结 Prompt Product。
- 22 次实际 Hook-model 调用产生 13 个 negative 与 9 个 positive；共发生 9 次 defer，分布于 4 个 Example。
- 目标中间行为在 4 个 Example 中可见。negative/fallback 控制不再被计为目标行为。
- Local efficacy 为 23 neutral、1 harmful。harmful 轨迹中 Candidate 忠实 defer 并诱发后续检索，但 Student 从原本正确答案转为“证据不足”，生产分数由 1 降为 0；该事实必须随 evaluator 不稳定一起进入 evidence feedback。
- Conformance 总 token 为 317,441，包含 Candidate rollout、Teacher Judge 与 Reviewer。

## Reviewer 稳定性补充

针对 managed evaluator mismatch 的同一 batch 独立复验 3 次：3/3 将错误路由到 evidence，并明确要求补充 Prompt/Student capability evidence 或修改研究方向；其中 2/3 认定两条 replicate 都是 mismatch，1/3 只认定一条，说明近邻语义边界的判定仍有轻度不稳定。

针对明确 negative/fallback 控制的 batch 独立复验 3 次：3/3 将三条 rollout 判为 faithful，且 `target_behavior_observed=false`。

## 结论边界

Shadow Conformance fragment 已能直接消费新协议、运行真实 Candidate、持久化逐轨迹 Finding，并把实现问题与冻结 Prompt Product 的语义能力问题分开路由。本次 Candidate 不应进入全量 Candidate Evaluation：一方面 managed evaluator 在真实 replay 上出现可重复错判，另一方面至少一条忠实干预产生了局部任务伤害。

本实验只覆盖单 phase、无业务 state 的 Decision Task；未验证多 phase、Generation Task 或 structured edit 的 Conformance 稳定性。
