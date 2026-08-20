# START-001 修订后五候选（复核输入）

本版吸收 `someagents_review_v1.md` 的全部硬约束。共同事实锁：当前结果只证明 operability；不证明成本、Candidate yield 或最终 utility。

## IDEA-001R：Pre-Materialization Evidence-Gated Harness Evolution

- 问题：在所审查的近期代表性方法中，行为验证通常发生在 materialized executable candidate/patch 之后；能否在任何 reusable executable edit 形成前先验证 implementation-independent mechanism，并再做 Student responsibility admission？
- 假设：类型化的 `Hypothesis -> Non-deployable Trial Intervention -> Evidence -> Mechanism -> Responsibility Feasibility -> Realization -> Candidate` 能比 Direct-Candidate、Shepherd/CRO-style localized candidate replay、HarnessBank-style candidate screening 更准确预测有用 Candidate，并改善预算匹配下的 yield/utility 或 attribution。
- 类型边界：Trial artifact 不得进入 Candidate pool、不得部署、不得包含完整 reusable guard/action implementation；失败后只产生 evidence，不产生 patch lineage。
- 文献证据：P001 Sec.3/Alg.1；P002 Secs.3.2-3.4；P003 Sec.3.1；P005 abstract/introduction；P006 Sec.4.3；P008 Sec.5.2/App.F Alg.1；P011 Sec.3.3；P016 Secs.3-4。
- 反证与现有解：Shepherd 已有 executable edit replay；HarnessBank 已有 Candidate gate；HASP 已有 PF；AHE 已有 falsifiable edit manifest。若 Trial 等价于 provisional executable patch，或去掉 Mechanism/Student gate 后与 CRO 等价，则新颖性失败。
- 关键验证：以 Evidence-Gated、Direct-Candidate、Shepherd/CRO-style localized replay、HarnessBank-style Candidate screening 为机制臂，并加入 P016 要求的 budget-matched parallel sampling 与 sequential refinement 简单基线；冻结 train/validation/held-out；统一 Student/Teacher/environment/token/step/wall-clock 预算；按 optimizer run 推断；抽样编译 gate-reject；测 local-to-global effect calibration 与 transport。
- 风险：高。当前同一 75 题贯穿多阶段、soft budget 可超支、代码未冻结、只有单 task family。
- review_verdict：`pass_after_revision`。

## IDEA-002R：Responsibility-Level Student Realizability Gate

- 问题：固定 Student 是否能在真实 prefix 上承担机制所要求的 semantic recognition、three-way decision、fallback 与 adherence；失败时应由 Student、deterministic logic、Teacher 还是 reject 承担？
- 假设：逐职责 admission 与 reassignment 能预测 runtime activation/adherence 和 Candidate utility，并减少 mechanism-correct-but-student-infeasible 的 false promotion。
- 文献证据：P006 Sec.4.3；P013 Secs.1/3.1；P010 Sec.3.1/App.B/C；P011 Sec.3.3；P003 Sec.3.1/App.C。
- 反证与现有解：activation beacon、mock execution、Teacher review 和 frozen-target rerun 都已存在；本候选只主张独立责任标签下的 pre-compilation semantic capability test 与 ownership reassignment。
- 关键验证：由确定性规则或多方盲审形成独立 reference labels；独立 calibration/test prefix；positive/negative/uncertain/hard-boundary；隔离 recognition/fallback/adherence/utility；至少两个 Student 层级与多个责任复杂度；no-gate/reject/deterministic/Teacher 四种处置；抽样评估 gate-reject。
- falsifier：feasibility score 对 runtime adherence/utility 无预测效度，或 gate 的 false rejection/overhead 抵消收益。
- 风险：Teacher 循环自证；当前 4-prefix 结果仅为 operability，Hook token 占 Candidate token 约 50%-70%。
- review_verdict：`pass_after_revision`。

## IDEA-003R：Mechanism-to-Realization Transport and Student-Aware Lowering

- 问题：同一 evidence-backed mechanism 在 prompt、deterministic hook、hook_model、tool/parser 等 realization 间是否发生可测 transport drift；Student-aware lowering 能否优于固定 surface？
- 假设：含 ownership、attachment、observability、state、fallback、invariants 的 contract，加上同机制多 lowering 与盲法 conformance，可降低实现漂移并选出更低成本/更可执行的 realization。
- 文献证据：P010 Sec.3.1/App.B/C；P003 App.C；P004 Secs.3.1-3.3/4.4；P015 introduction/main results。
- 反证与现有解：PF、typed lifecycle hook、component substrate 与 component-wise optimization 都已存在；字段更多不构成贡献。
- 关键验证：每机制至少三种真实 executable lowering；定义语义等价与允许差异；比较 direct patch、fixed surface、deterministic-first、Teacher-choice、Student-aware lowering；以 conformance、activation/adherence、utility、tokens/latency 检验。
- falsifier：IR 不降低 conformance/transport failure，或选择策略不优于简单固定策略。
- 条件：当前尚无 portfolio compiler，且单 Compiler WorkItem 约 0.76M-1.40M token；必须先限制上下文/portfolio。未满足条件时降级为 IDEA-001 supporting component。
- review_verdict：`conditional_pass_after_reframing`。

## IDEA-004R：Matched Prefix Evidence for Candidate-Effect Prediction

- 问题：怎样的 paired/repeated prefix trial 才能稳定预测 compiled Candidate 的效应，而不只提高 Reviewer 自信？
- 假设：同 prefix 多次 baseline/intervention continuation、跨 prefix/case test 和层级统计，能提高 gate decision 的重复稳定性及 Candidate effect 方向预测。
- 文献证据：P005 abstract/introduction；P008 Sec.5.2/App.F；P009 trap-aware recovery pipeline；P011 Sec.3.3。
- 反证与现有解：fork、same-prefix continuation、paired statistics 均不是新颖点；贡献仅可能是 pre-materialization mechanism evidence 对 downstream Candidate 的预测协议。
- 关键验证：随机执行顺序；同 prefix 多次双臂 continuation；prefix 嵌套 case、case 嵌套 hypothesis 的层级 bootstrap/model；预注册 process/task outcome；与 single/unpaired/Candidate subset screening 做同预算对比。
- falsifier：严格配对并不提升 decision stability 或 local-to-global prediction。
- 风险：独立新颖性较低，优先作为 IDEA-001 的核心方法与消融。
- review_verdict：`pass_as_method_candidate`。

## IDEA-005R：Attribution-Grounded Typed Revision Routing

- 问题：类型化路由能否在具有可审计多标签真值的故障上，比 flat retry 更准确定位 failure layer 并减少重做？
- 假设：在受控 fault-injection 与 organic failures 上，typed routing 可提高 route precision/recall、降低重复失败/修订轮数/tokens，同时支持跨层多标签归因。
- 文献证据：P004 Sec.3.3/4.4；P012 function anchoring/recalibration；P014 Sec.1/Fig.1；P008 typed trace。
- 反证与现有解：versioning、typed trace、manifest、evidence anchoring 均为先例；agreement 不是 attribution accuracy。
- 关键验证：注入 false hypothesis、insufficient evidence、underspecified mechanism、Student-infeasible responsibility、implementation nonconformance、global interaction/regression；盲审；比较 flat retry；再以 organic failures 做外部有效性。
- falsifier：route precision/recall、修订效率或最终修复率无改善，或错误路由增加跨层遗漏。
- 风险：独立算法新颖性有限，优先作为 supporting systems contribution。
- review_verdict：`pass_as_supporting_candidate`。
