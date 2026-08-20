# START-001 候选 IDEA 证据卡（审查前冻结版）

证据快照：`START-001-SNAPSHOT-v1`。以下候选共享同一文献注册表、问题状态矩阵、`0820_report.md`、当前代码和既有 runs。评分为启动阶段判断，不代表实验结论。

## IDEA-001：Evidence-Gated Harness Evolution（完整主线）

- 研究问题：能否把 Harness Evolution 的最小实验单位从“完整可执行 Candidate”前移为“冻结 Prefix 上的可撤销局部干预”，并在编译前分别验证机制证据与 Student 可实现性？
- 核心假设：相较直接 Candidate 生成，`hypothesis -> prefix-fork trial -> evidence gate -> mechanism IR -> Student feasibility -> compile` 能减少无效完整评估，并把负面结果更准确地归因到 research、mechanism、feasibility 或 implementation。
- 主要证据：P001 Sec.3/Alg.1、P002 Secs.3.2-3.4、P003 Sec.3.1 表明主流流程以 executable candidate/patch 为早期评估对象；P005 指出长轨迹高方差导致 credit assignment 困难；P006 Sec.4.3 证明弱模型存在 activation/adherence failure；P008 Sec.5.2 提供 fork/replay 先例。
- 精确新颖性边界：不主张 failure diagnosis、falsifiable hypothesis、fork/replay、guard/intervention、candidate gate 或 event sourcing 首创。主张的组合差异是：未持久化 intervention 的 pre-compilation evidence gate，加上 implementation-independent mechanism 和 per-mechanism Student realizability gate。
- 最强反证/邻近：P008 已从第一行为分歧点分叉验证 proposed fixes；P011 已对 Candidate 做 activation + paired significance screening；P010 已有 executable PF 与 teacher review。若正文或代码表明这些工作也在 Candidate 之前对未实现机制做 Student feasibility test，则核心新颖性失效。
- 可证伪条件：局部试验证据不能预测 Candidate 的方向性收益；gate 的 false rejection 过高；在预算匹配下 Candidate yield、最终 utility 或总成本不优于直接生成；归因路由的 reviewer agreement 不提升。
- 实验最小集：同一 failure pool、同一 Student、同一 evaluator、同一总 token/rollout budget，对比 Direct-Candidate、HarnessBank-style Candidate Screening、Evidence-Gated；报告候选数、完整评估数、有效候选率、最终效用、总成本、负面结果归因准确率。
- 项目可行性：高。主链、artifact、prefix fork、mechanism IR、feasibility gate、compiler/conformance 已有；主要缺口是 prospective budget-matched closed-loop evaluation 和统计审计。
- 风险：高新颖性竞争、高评测成本、局部 soft intervention 与最终 compiled realization 可能存在 transport gap。
- 初评分：novelty 4.3/5，importance 4.7/5，feasibility 4.3/5，evidence readiness 3.6/5。

## IDEA-002：Student-Realizability-Aware Harness Optimization（聚焦能力门）

- 研究问题：外部 Teacher 提出的合理机制，是否能在编译前通过真实 Prefix 上的责任级测试，判断固定小模型 Student 能否稳定执行其语义 guard、decision contract 和 fallback？
- 核心假设：逐职责的 realizability probe 能识别“机制正确但 Student 不会触发/不会遵循”的 failure，并通过简化 guard、下沉为 deterministic logic 或拒绝编译，提高 hook_model Candidate 的有效率。
- 主要证据：P006 Sec.4.3 的 activation/adherence failure；P013 Secs.1/3.1 的 backbone capability bound；P010 Sec.3.1 说明 executable PF 可以把判断外化，但其 self-improvement admission 依赖 executable validation/teacher review而非 Student feasibility。
- 精确新颖性边界：不主张“弱模型无法利用 Harness”这一观察；主张把该观察转化为 optimizer 内部、逐机制、真实状态、编译前的决策门，并允许 responsibility simplification/reassignment。
- 最强反证/邻近：P010 使用 Qwen2.5-7B 并测试 PF inference；P011 显示 model-specific harness；P003 让冻结 target 在 same-batch 执行 patch。若这些机制已有独立的 responsibility-level admission test，则差异缩小。
- 可证伪条件：feasibility score 与 hook activation/adherence、Candidate utility 无相关；简化后的机制并不优于原机制；gate 仅增加成本并错误拒绝可用机制。
- 实验最小集：从同一 mechanism pool 构造 deterministic、Student-semantic、Teacher-semantic 三类 realization；按模型规模分层，测触发识别、三向 decision、fallback、最终 utility 和 token overhead。
- 项目可行性：最高。现有 run 已真实展示一次 3/4 boundary 回流和修订后 4/4 通过，但两个 Candidate 退化，因此只能作为 gate-operability 证据，不能作为 utility 证据。
- 风险：单独成文可能被认为是 P006 的工程化延伸；需要跨模型规模与多类 semantic responsibility 才能形成一般性结论。
- 初评分：novelty 4.5/5，importance 4.5/5，feasibility 4.7/5，evidence readiness 3.8/5。

## IDEA-003：Mechanism IR 与多实现编译搜索

- 研究问题：同一个经证据支持的行为机制，能否先表达为与代码解耦的 runtime contract，再在 prompt/tool/parser/deterministic hook/hook_model 多种 realization 中选择最符合 Student 能力和成本约束的一种？
- 核心假设：`guard + decision contract + runtime inputs + state + action + fallback + attachment + ownership + observability + invariants` 的 IR 能降低语义意图到代码的实现漂移，并避免把机制有效性与某一种 realization 绑定。
- 主要证据：P010 Sec.3.1 的 Program Function 是最接近的 guard/intervention 表示；P004 Sec.4.4 报告组件非加性；P015 的 component-wise optimization 说明跨组件干扰真实存在；P003 Appendix C 展示四类 lifecycle hooks。
- 精确新颖性边界：不能把 `should_activate + intervene` 当作贡献；差异应是同一 evidence-backed mechanism 的 implementation-independent contract、可比较 realization portfolio 与 Student-aware lowering。
- 最强反证/邻近：HASP 的 PF 已经是可执行机制对象，HarnessCompass 已拆分组件优化，Harness-R1 已有 typed hook interface。若 IR 只换名而没有跨实现一致性测试与 lowering 策略，则无科学贡献。
- 可证伪条件：IR 不降低 conformance failure；多实现搜索不优于固定 deterministic-first 规则；不同 realization 的语义一致性不可测或成本过高。
- 实验最小集：固定一组 mechanism，人工/Teacher 生成多个 realization；盲审语义一致性，测 conformance、Student feasibility、utility、tokens/latency，并分析 transport gap。
- 项目可行性：中高。当前 mechanism contract 已接近，但 attachment/ownership/observability/invariants 与多 realization compiler 尚未系统实现。
- 风险：容易落入 DSL/软件工程论文；必须用实验展示 IR 带来的归因与选择收益。
- 初评分：novelty 4.0/5，importance 4.0/5，feasibility 3.7/5，evidence readiness 3.2/5。

## IDEA-004：Matched Prefix Trial Design for Harness Hypotheses

- 研究问题：如何用跨 case、跨 prefix、重复 continuation 和配对不确定性估计，可靠判断局部 intervention 是否改变失败机制，而非偶然改变最终答案？
- 核心假设：确定性 trial selection、同 prefix baseline/intervention 配对和重复试验，能比单 rollout 或非配对 Candidate score 更好地区分有效机制、无效机制和 context-sensitive effect。
- 主要证据：P008 Sec.5.2 的 counterfactual replay；P009 的 same-prefix continuation recovery；P011 Sec.3.3 的 paired-significance gate；P005 的 sparse/high-variance failure attribution 问题。
- 精确新颖性边界：prefix fork 和 paired statistics 都不是新颖点；可能的新意仅在把这些设计组成“hypothesis evidence before compilation”的统计协议，并定义 cross-prefix generalization。
- 最强反证/邻近：Shepherd 最接近且已验证 proposed fixes；HarnessBank 已用配对显著性。独立论文的新颖性风险高。
- 可证伪条件：重复 prefix trial 的结论稳定性不优于 Candidate subset screening；局部 effect 与完整 Candidate effect 相关性弱；成本节约不足。
- 实验最小集：对同一 hypothesis 分别使用 single trial、unpaired repeats、paired same-prefix repeats、cross-prefix/cross-case gate，比较 decision stability 与 downstream prediction。
- 项目可行性：高，现有 prefix-fork 与 receipts 可复用。
- 风险：更适合作为 IDEA-001 的方法/消融，而非独立主线。
- 初评分：novelty 3.2/5，importance 4.2/5，feasibility 4.5/5，evidence readiness 3.7/5。

## IDEA-005：Attribution-Aware Revision Routing

- 研究问题：能否通过类型化 artifact、conformance 与 effect receipt，将失败明确路由到 hypothesis、evidence、mechanism、Student feasibility、implementation 或 global utility，而不是统一回到 proposer？
- 核心假设：分层责任边界和 revision obligation 能提高负面结果归因一致性，减少无关阶段重做与重复失败。
- 主要证据：P004 Sec.3.3 的 edit manifest 与 regression blindness；P012 的 function-level evidence anchoring 和 state-dependent recalibration；P014 的 versioned snapshots/structured traces；P008 的 typed reversible trace。
- 精确新颖性边界：event-driven controller、receipt、versioning、typed trace 不是主创新；可检验贡献只能是“路由是否提高归因正确率和修订效率”。
- 最强反证/邻近：AHE/DREvo 已有细粒度证据归属；VeRO/Shepherd 已有系统基础设施。没有可量化 routing benefit 就只是工程实现。
- 可证伪条件：独立审查员对 failure layer 的一致性低；typed routing 不减少无效重跑；错误路由造成更高延迟或掩盖跨层交互。
- 实验最小集：冻结相同 failure set，比较 flat proposer retry 与 typed routing；测 attribution agreement、修订轮数、重复 failure、tokens、最终修复率。
- 项目可行性：高，代码已有主要路由与 receipt。
- 风险：算法新颖性偏低，适合作为 IDEA-001 的 supporting systems contribution。
- 初评分：novelty 3.0/5，importance 3.8/5，feasibility 4.6/5，evidence readiness 3.6/5。

## IDEA-006：Budget-Aware Evidence Acquisition for Harness Evolution

- 研究问题：Evidence Gate 应何时追加 prefix/repeat、何时编译、何时拒绝，才能在固定总预算下最大化最终 useful-candidate yield？
- 核心假设：基于证据不确定性、预计完整评估成本和机制价值的 sequential decision policy，优于固定 trial 数与固定阈值。
- 主要证据：P011 的 subset screening 与 full-evaluation budget；P016 要求预算匹配并显示简单 scaling baseline 很强；P012 说明有限预算下历史证据有效性会变化；P007 显示 search budget 效果非单调。
- 精确新颖性边界：early screening 与预算控制已有；差异必须是对“未编译机制证据”的 value-of-information 决策，而不是又一个 Candidate scheduler。
- 最强反证/邻近：HarnessBank 已高效筛 Candidate；DREvo 已在有限预算下调度证据；TTHE 已分析 batch/branch budget。需要正式决策目标和可复现实验才能区分。
- 可证伪条件：自适应策略不优于简单固定小样本；不确定性估计未校准；policy overhead 抵消节约。
- 实验最小集：固定总预算，对比 fixed-1、fixed-k、threshold gate、sequential VOI；报告有效候选率、regret、总成本与最终效用。
- 项目可行性：中。需要在当前 Evidence Reviewer 上增加统计状态和预算策略，现有 run 数量不足以训练复杂 policy。
- 风险：容易扩展范围，建议作为后续增强或 IDEA-001 的预算消融。
- 初评分：novelty 3.8/5，importance 4.3/5，feasibility 3.1/5，evidence readiness 2.8/5。

## 审查前排序建议

1. IDEA-001：最完整地承接项目已有实现与报告主张，但必须用预算匹配实验兑现。
2. IDEA-002：最锐利、最可执行的核心创新，可作为 IDEA-001 的主轴或更窄论文。
3. IDEA-003：表示层贡献有潜力，但必须证明多 realization lowering 的实验收益。
4. IDEA-006：研究价值高，当前实现与数据基础较弱。
5. IDEA-004：重要但邻近工作太强，更适合作为实验协议。
6. IDEA-005：适合作为 systems contribution，不宜单独主导论文。
