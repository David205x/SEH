# START-001-SNAPSHOT-v5.1 多 Agent 独立审查汇总

- 冻结对象：`第三轮经验系统定位_v5.md`、`start.yaml` 中 `IDEA-001R3`、文献 P017-P022 与 Q6。
- 模式：cvpr-someagents Mode B；三位审查者互不交流，仅侧重点不同。
- 初审：三位均为 `revise`；v5.1 按全部 blocker 修订后复审。
- 最终结论：`pass`；无未解决 blocker。

## 问题证据与实验识别审查

最终 `pass`。确认以下问题已解决：

- Attempt Ledger 记录 support/pass、reject/revise、feasibility、conformance、promotion 与 global regression；reject/revise 仅即时触发 provisional Experience Candidate。
- 三类经验不是互斥标签，同一轨迹可形成多个独立 evidence/consumer projection。
- H1、H2 独立比较；H2a 的 probe 预测效度与 H2b 的 adaptive routing 增益分离。
- H1 明确为 matched no-op 与 soft-intervention 两臂，原始 rollout 仅提供 Prefix；对预注册比例的 Gate-rejected mechanism 做盲编译/完整评估以估计 false rejection。
- H3 固定同一 H1/H2 pipeline、配置、预算、种子和 split firewall；任一 H 失败时只撤回对应主张。

## 新颖性与相关工作审查

最终 `pass`。确认：

- 已加入 DREvo-like、Auto-Robotist-like、G-Memory/Intrinsic/LLMA-Mem-style role-local、ExpeL-style 和基础 memory baselines。
- 已加入普通轨迹摘要、移除 verification-stage provenance、移除 invalidation/recheck/bypass 的归因消融。
- H3 仅被称为 integrated empirical hypothesis；只有击败最近邻、保持 held-out utility 且控制 false pruning 后，才可提升为并列方法贡献。
- 不主张 role-aligned memory、三类 taxonomy、experience extraction、evidence-grounded search memory 或 exploration path 首创。

## 方法可行性与风险审查

最终 `pass`。确认以下合同可执行：

- 经验在 settled optimizer decision episode 之间生效，避免与当前 Controller 的 promotion-only generation 计数混淆。
- Student capability experience 仅由 Researcher 消费；下游只接收 Researcher 形成的正常设计合同或本次 feasibility revision obligation。
- `base_prompt_digest` 与 experience projection digest 分离；Student/Teacher scope 区分 hard mismatch 与 soft drift。
- blinded proposal shortlist、配对 memory audit、固定概率 bypass/recheck 形成 false-pruning 反事实估计。
- provisional Curator、确定性 evidence grade、settled opportunities、hard budget reservation/commit/refund、H1/H2 freeze 和独立 Store 均进入最小合同。

## 保留边界

1. H3 当前尚未实现，也没有本地效果证据；`pass` 只表示研究假设与验证路径成立。
2. 正式多 episode/generation 比较前必须先验证并冻结 H1/H2 verdict pipeline。
3. held-out non-inferiority margin、false-pruning 上限、override/recheck recovery、exploration 比例和最低 settled opportunities 需在 `cvpr-goal` 预注册。
4. 当前 soft token check 必须升级为 hard budget ledger；所有 Curator、检索和经验上下文成本计入总预算。
