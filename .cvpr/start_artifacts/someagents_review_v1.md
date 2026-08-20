# START-001 多 Agent 独立审查综合

输入快照：`START-001-SNAPSHOT-v1`。模式 B；三位 Agent 互不交流，均未修改冻结包。

## 原始角色与轴

- `source_problem_review`：`source_recency=pass`，`problem_evidence=revise`。
- `novelty_review`：`novelty_related_work=revise`；IDEA-002 通过，IDEA-001 需收紧，IDEA-003 原形态阻断。
- `method_feasibility_review`：`method_falsifiability=revise`，`feasibility_review_risk=revise`；IDEA-006 延期。

## 共识

1. 文献身份与时效通过：P001-P016 均为截止日前可核验的 2026 年工作；但大多为预印本，不能写成稳定共识。
2. IDEA-001 不能用“未持久化”区分 Shepherd；必须用“尚未物化为 reusable executable edit”的 artifact 类型边界。
3. Shepherd/CRO 与 HarnessBank 必须进入强基线：前者覆盖 source-edit + prefix replay + targeted preflight，后者覆盖 Candidate activation + paired significance screening。
4. IDEA-002 是最锐利主轴，但 feasibility 必须与 activation 分开，并以独立责任标签、negative/uncertain/hard-boundary、跨 Student 层级和 false accept/reject 验证。
5. 任何效率/效用结论必须遵循 P016：matched feedback/inference budget、parallel sampling、sequential refinement、held-out tasks。
6. 当前 run 只证明 gate、回流与 artifact plumbing 可运行；两个 Candidate 退化、soft budget 超支和全分布误触发是 transport-gap 负面证据。

## 少数意见

- 严厉解释：若 soft intervention 实质是临时 prompt/source patch，则 IDEA-001 与 Shepherd/CRO 的差异可能只剩命名。
- 支持解释：Shepherd 先生成 executable `Δ_i`，而本方案可以在任何 reusable edit 形成前验证 implementation-independent mechanism，并增加 responsibility reassignment；组合后仍可能构成新 protocol。
- IDEA-002 可独立收缩成“mechanism complexity × Student capability”的测量论文，但外部证据目前主要是动机，不是该 optimizer 已有效的直接证据。
- IDEA-004 新颖性较弱，却是最容易形成可信实证的切入点，适合作为 IDEA-001 的核心实验设计。

## 硬约束与解除方式

- H1：证明 Trial artifact 不是 provisional executable Candidate。解除方式：形式化 artifact type/invariants，并审计其不可部署、不可入 Candidate pool、无 reusable implementation。
- H2：证明 local intervention 到 compiled Candidate 的 transport。解除方式：方向预测、校准、false promotion/false rejection 及抽样编译 gate-reject。
- H3：防止 Teacher 循环自证 Student feasibility。解除方式：独立标签/确定性判据/盲审，隔离 recognition、fallback、adherence、utility。
- H4：冻结可复现实现。解除方式：将当前未跟踪功能纳入明确 commit/tree，锁定环境、数据 digest、模型与预算协议。
- H5：避免单一 HotpotQA 过度泛化。解除方式：至少增加一个 task family，或将 claim 明确限定为 retrieval/search harness。

## 综合路由

- IDEA-001：修订后保留为首选综合主线。
- IDEA-002：保留为首选核心子问题，也可独立收缩。
- IDEA-003：原形态阻断；仅在升级为真实多 realization lowering + transport study 后保留为条件候选。
- IDEA-004：保留，定位为主线实验方法候选。
- IDEA-005：保留，定位为 supporting systems/attribution 候选。
- IDEA-006：本轮延期，不进入正式五候选。
