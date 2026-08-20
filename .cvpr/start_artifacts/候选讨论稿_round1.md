# START-001 第一轮候选讨论稿

## 我们当前最需要做的选择

我们已经确认，项目的主要研究机会不是再增加一层 Reviewer，也不是把 fork、Candidate gate、typed trace 或 guard/action 重新命名。更有希望的边界是：我们能否把 **不可部署的局部干预** 规定为 Candidate 物化前的独立实验对象，并在编译前验证证据充分性以及固定 Student 对具体语义职责的可实现性。

我们也必须保留当前的负面结果。现有 Run 只证明 Hook Feasibility Gate 能在 Compiler 前工作；它没有证明 Candidate yield、总成本或最终 utility 得到改善。Incumbent accuracy 为 0.671111，两个 Candidate 分别为 0.653333 和 0.631111；第二个 Candidate 还使累计消耗从 7M soft budget 越界到 7.90M。复杂 Intervention 实验中，单 phase 为 30/30，但 multi-phase state 只有 2/6。这些结果构成研究动机和风险，而不是方法有效性的证据。

## 我们建议的主线组合

我们建议选择 **IDEA-001R 作为总研究问题**，把 **IDEA-002R 作为最核心、最有辨识度的机制贡献**，把 **IDEA-004R 作为证据门的实验与统计协议**，并把 **IDEA-005R 作为支持性系统贡献**。我们只在愿意承担明显更大的实现与实验成本时，才把 **IDEA-003R** 保留为独立贡献；否则它应降级为 IDEA-001R 的实现组件。

这个组合并不把五个候选机械相加。它形成一条可检验的主张：我们先用不可部署的 intervention 检验机制，再用责任级 feasibility 判断 Student 能否执行，随后才生成 Candidate；我们用 matched-prefix evidence 检验局部证据能否预测全局 Candidate effect，并用 typed routing 解释失败应返回哪个层级。

## 五个可选方向

### IDEA-001R：Pre-Materialization Evidence-Gated Harness Evolution

我们研究 Candidate 物化之前的证据门是否真的提高有效 Candidate 产出率、最终 utility 或错误归因质量。最重要的新颖性边界是 Trial 必须不可部署、不能进入 Candidate pool，也不能携带完整的 reusable guard/action implementation。若它实质上只是 provisional patch，或在严格预算匹配下不优于 Direct、Shepherd/CRO、HarnessBank screening 与简单 parallel/sequential baselines，我们就应否定主张。

它与当前代码最贴合，适合作为主课题，但必须补齐严格预算、数据拆分、gate-reject 抽检和至少第二个 task family，或者主动把结论限定为 retrieval/search harness。

### IDEA-002R：Responsibility-Level Student Realizability Gate

我们研究固定 Student 能否承担机制要求的 recognition、decision、fallback 和 adherence，并在 Student、deterministic logic、Teacher 与 reject 之间重新分配职责。它比一般的 activation test 更窄，也更容易形成清晰的独立贡献。

若 feasibility score 不能预测 runtime adherence 或 utility，或 false rejection 与成本抵消收益，我们就应否定该 gate。实验必须使用确定性规则或多方盲审形成独立 reference labels，并隔离 calibration、feasibility、conformance 与 Candidate test prefixes。

### IDEA-003R：Mechanism-to-Realization Transport and Student-Aware Lowering

我们研究同一机制在 prompt、deterministic hook、hook_model、tool/parser 等 realization 之间的 transport drift，以及 Student-aware lowering 是否优于固定 surface。

这个方向风险最高。我们只有在每个机制至少实现三种真实 executable lowering、预先定义语义等价与允许差异、并完成 conformance、activation、utility、token 和 latency 对比时，才能保留其独立贡献。如果做不到，我们应把它降级为主线的 supporting component。

### IDEA-004R：Matched Prefix Evidence for Candidate-Effect Prediction

我们研究 repeated paired prefix trial 能否稳定预测 compiled Candidate 的方向和幅度，而不是只让 Reviewer 更有信心。核心验证包括随机执行顺序、同 prefix 多次双臂 continuation、嵌套实验单位和预注册的 process/task endpoints。

这个方向方法上很干净，但独立新颖性较弱。我们更建议把它作为 IDEA-001R 的核心证据协议和消融，而不是单独承担整篇工作的主贡献。

### IDEA-005R：Attribution-Grounded Typed Revision Routing

我们研究 typed routing 在具有多标签故障真值时，能否比 flat retry 更准确地定位 failure layer，并减少重做、tokens 和重复失败。

我们需要注入 false hypothesis、insufficient evidence、underspecified mechanism、Student-infeasible responsibility、implementation nonconformance 和 global regression，再用 organic failures 检查外部有效性。这个方向适合成为系统与可追溯性贡献，但不宜单独承担主要算法新颖性。

## 无论选择哪条主线，我们都必须锁定的条件

1. 我们要冻结可复现的 commit/tree、环境、数据 digest、Student、Teacher、Judge 版本与配置。
2. 我们要隔离 train、validation 与 held-out，不能让同一 75 题贯穿研究、门禁和最终评估。
3. 我们要统一 token、step、wall-clock 和完整 rollout 预算，并预留预算，不能再用可超支的 soft limit 证明公平。
4. 我们要预注册主次终点、实验单位、重复、聚类、不确定性区间与多重比较。
5. 我们要抽样编译 gate-rejected mechanisms，估计 false rejection，并测量 local intervention 到 Candidate effect 的 transport。
6. 我们要增加第二个 task family，或把所有结论明确限定在 retrieval/search harness。

## 我们的建议

如果目标是形成一项边界清楚、能最大化复用当前实现、又能经受近期工作的优先权审查的研究，我们建议确认以下组合：

> **主 IDEA：IDEA-001R；核心机制：IDEA-002R；实验协议：IDEA-004R；支持系统：IDEA-005R；IDEA-003R 暂不作为独立贡献。**

这个选择仍然是一个待证伪的研究计划，不是对性能提升的预先承诺。
