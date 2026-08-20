# START-001 v4 主线重构增量审查

冻结输入：START-001-SNAPSHOT-v4

审查对象：

- 0820_report.md
- .cvpr/start_artifacts/第二轮解释与主线修订_v4.md
- .cvpr/literature/文献注册表.jsonl
- docs/audits/ref.md
- 当前 typed routing、CandidateReviewerInput 和 research_role_effects 代码

## 独立审查结论

| Agent | 审查轴 | 初审 | 修订后 |
|---|---|---|---|
| v3_problem_evidence | source_recency, problem_evidence | revise | pass |
| v3_novelty | novelty_related_work | revise | pass |
| v3_method_feasibility | method_falsifiability, feasibility_review_risk | revise | pass |

## 已解决问题

- IDEA-001R 与 IDEA-002R 已合并为不可拆分的双门主线，恢复 0820_report.md 的论文 identity。
- Prefix 已明确来自真实 Student rollout，由确定性 Trial Selector 在观察分支结果前按适用范围和 falsifier 选择。
- Trial 已明确不可部署、不可进入 Candidate pool、不得包含完整 reusable patch。
- 经验系统已从潜在 novelty 收缩为 planned and evaluated supporting subsystem。
- 经验系统三类视图都标注了当前 artifact 种子、尚未实现能力和归因边界。
- 已加入 DREvo-like historical-evidence baseline、stale/corrupted stress test、bypass/recheck 和 false-suppression 指标。
- 已补齐双门因子消融、Gate 预注册门槛、matched-prefix 统计单位、local-to-global transport、信息泄漏防线、thinking-off 主配置、复现冻结和 task-family 外推边界。

## 保留意见与后续条件

1. 经验系统不得进入标题或与双门并列为主 novelty，除非专项文献检索与独立消融支持提升。
2. DREvo-like baseline 必须按 P012 锁定具体输入、recalibration 时机和输出契约，不能退化为宽泛的结构化摘要。
3. historical_experience 当前仍由 Controller 固定传空列表；Experience Candidate、Curator、Store、Projection、Attempt Ledger 和 usage receipt 均是待实现能力。
4. 当前 Trial 和 Hook Feasibility 仍未满足修订稿中声明的完整 matched-prefix 与 in-loop realizability 协议；这些是后续 Goal 的硬条件。

最终结论：pass。无未解决启动 blocker。
