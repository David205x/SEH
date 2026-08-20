# START-001 修订候选复核结论

三位原独立审查 Agent 在不改变文献快照的前提下复核 `候选IDEA证据卡_v2.md`。

## Candidacy verdict

| Candidate | source/problem | novelty | method/feasibility | 进入用户讨论 |
|---|---|---|---|---|
| IDEA-001R | pass | pass | conditional | 是，主候选 |
| IDEA-002R | pass | pass | conditional | 是，主候选 |
| IDEA-003R | conditional | conditional | conditional | 是，高风险条件候选 |
| IDEA-004R | conditional | conditional | pass | 是，方法型窄候选 |
| IDEA-005R | conditional | conditional | conditional | 是，supporting systems 候选 |

`conditional` 表示后续 Goal 必须锁定相应验证条件，不表示候选在启动讨论阶段被阻断。三位审查者一致认为五项均可进入正式用户讨论；IDEA-006 则一致延期。

## 已解除的启动阶段 blocker

- IDEA-001R 已用不可部署、不可入 Candidate pool、无完整 reusable implementation 的 artifact invariant 区分 Shepherd 的 executable edit replay。
- IDEA-001R 已显式加入 Direct、Shepherd/CRO、HarnessBank 以及 budget-matched parallel sampling/sequential refinement。
- IDEA-002R 已加入独立 reference-label adjudication、责任分解和 gate-reject 抽检。
- IDEA-003R 已从“字段更多的 IR”改为“同机制多 lowering 的 transport 与选择”，并明确未满足实现条件即降级。
- IDEA-004R/005R 已分别收缩为可测的 downstream prediction 与 attribution-grounded routing，不再主张 fork/typed trace 首创。

## 必须传递到 cvpr-goal 的条件

1. 冻结可复现 commit/tree、环境、数据 digest、模型/Judge 版本与配置。
2. train/validation/held-out 隔离；禁止同一 75 题贯穿全部阶段。
3. 严格预算预留和统一成本口径；不能使用可超支的 soft limit 证明公平。
4. 预注册主/次终点、实验单位、重复、聚类、区间与多重比较。
5. 抽样编译 gate-reject，估计 false rejection；校准 local intervention 到 Candidate effect 的 transport。
6. Student feasibility 使用独立标签且各阶段 prefix 不复用。
7. 至少增加第二 task family，或把 claim 限定为 retrieval/search harness。
