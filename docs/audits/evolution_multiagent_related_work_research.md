# 进化 Harness 与多智能体相关工作调研

> 调研范围：`research/` 下的 A-Evolve、Adaptive Auto-Harness、ADAS、AgentSquare、Argus、Continual Harness、DGM、GEPA、Meta-Harness、Self-Harness、SIA、SearchOS 以及两篇随附论文。  
> 调研目标：针对当前五项设计局限，寻找可复核的思想与实现参照；同时分析任务设计、角色、I/O、状态转移、确定性机制、协作稳定性和 token 成本。  
> 结论性质：这是设计调研，不是已批准的 ADR。文中的新名词和路线仍需在实现前固化到领域模型与决策记录中。

## 1. 执行摘要

最值得采用的不是某一个项目的完整架构，而是四组互补机制：

1. **GEPA 的按案例验证与 Pareto 视图**：把“平均分”拆成每个案例、每个目标的证据向量，保留局部有效的候选，并用独立 validation set 检查泛化。
2. **Self-Harness 的 Candidate Queue 与 Branch State**：Candidate reject 只是一次 Attempt 的终态，不是 Generation 或 Evolution Run 的终态。
3. **SearchOS 的外部事实状态与中间件治理**：Coverage、Evidence、Failure、Frontier、Budget 不靠角色记忆，而由 Harness 持有并确定性更新。
4. **Argus 的唯一状态裁决者与确定性 Gate**：角色只建议，Controller 校验 artifact、合法转移、预算和恢复条件。

对当前项目，推荐的总体形态是：

```text
Accepted Version
  └─ Generation
      ├─ SearchRound
      │   ├─ DirectionAttempt
      │   │   └─ HypothesisAttempt
      │   │       ├─ EvidenceCoverageState
      │   │       ├─ MechanismDraft
      │   │       └─ CandidateAttempt
      │   │           ├─ staged validation
      │   │           ├─ ConformanceManifest
      │   │           └─ AttemptOutcome
      │   └─ Direction Portfolio / Candidate Queue
      ├─ Experience Store
      └─ Normalization Queue
```

其中模型负责开放性的假设、机制和实现内容；Controller 必须拥有 artifact 身份、覆盖计数、数据 split、预算、状态转移、去重、缓存、晋升和恢复语义。

### 五项局限的建议优先级

| 局限 | 可靠性影响 | 首选模式 | 修改规模 |
|---|---:|---|---:|
| 1. 证据覆盖不足 | 高 | `EvidenceCoverageContract` + 正例/负控/边界/phase cell | M |
| 2. Conformance 过窄 | 高 | 持久化 Manifest + paired baseline/candidate + 分层验证 | M–L |
| 3. Reject 后停止 | 高 | SearchRound/DirectionAttempt + durable Candidate Queue | M |
| 4. 无研究经验系统 | 中高，随 Generation 增长而升高 | 事实层 + 结构化 Experience Card + role projection | M–L |
| 5. 固定基线补丁叠加 | 中期为中、长期为高 | Normalization Run + baseline epoch + complexity gate | L |

## 2. 调研方法和证据强度

本报告区分三类证据：

- **代码级证据**：实际存在的数据结构、状态机、gate、队列、缓存或预算逻辑，可信度最高。
- **文档/论文级证据**：设计明确但未必由当前快照完整实现，作为架构参照。
- **迁移推论**：根据当前项目语义作出的组合设计，均标明约束和副作用。

重点源码证据包括：

- Self-Harness 的 durable candidate queue、branch、reject continuation 和 accepted merge/re-evaluation：[`run_self_harness_loop.py`](../../research/self-harness/workflow/scripts/run_self_harness_loop.py#L437)。
- GEPA 的 per-instance state、validation Pareto、cache 和预算：[`state.py`](../../research/gepa/src/gepa/core/state.py#L46)、[`api.py`](../../research/gepa/src/gepa/api.py#L48)。
- A-Evolve Meta-Harness 的 propose/evaluate/select 三阶段、archive 和 rollback：[`engine.py`](../../research/a-evolve/agent_evolve/algorithms/meta_harness/engine.py#L108)。
- Argus 的 deterministic research gates 与唯一 stage transition：[`research_gates.py`](../../research/Argus-main/argus_skill/skills/research_gates.py#L1)、[`stage_machine.py`](../../research/Argus-main/argus_skill/skills/stage_machine.py#L175)。
- SearchOS 的 SOCM、Coverage、Failure Memory、中间件和调度器；源码位于 [`SearchOS-main.zip`](../../research/SearchOS-main.zip)，论文为 [`SearchOS-V1`](<../../research/SearchOS-V1_Towards Robust Open-Domain Information-Seeking Agent Collaboration.pdf>)。

当前项目自身的直接证据：

- EvidenceReview 只有 decision、phase findings 和文字义务，没有跨案例/polarity/scope coverage contract：[`contracts.py`](../../search_harness/evolution/research/roles/contracts.py#L150)。
- Conformance 固定每例 3 次，只要求每题至少一次 faithful，且 `not_observed` / `inconclusive` 在已有 faithful 时不会使其失败：[`conformance.py`](../../search_harness/evolution/research/conformance.py#L159)。
- Candidate reject 在没有 revision route 时直接结束：[`transitions.py`](../../search_harness/evolution/control/transitions.py#L543)。
- Candidate Reviewer 虽有 `historical_experience` 字段，调用方始终传空列表：[`research_role_effects.py`](../../search_harness/evolution/control/research_role_effects.py#L231)。
- Fixed Component 的目录和 manifest 都禁止修改，新 Component 必须 mutable：[`validation.py`](../../search_harness/evolution/versioning/validation.py#L192)。

## 3. 相关工作的机制地图

| 工作 | 任务/搜索设计 | 状态与 I/O | 稳定性机制 | Token/成本机制 | 对当前项目的主要价值 |
|---|---|---|---|---|---|
| Self-Harness | 同一 parent 下多 proposal、独立评估、accepted sibling merge | queue、branch state、proposal/eval/gate artifacts | reject 局部化、merge 后重评估、baseline/candidate 可比性检查 | 复用 case diagnosis；先逐候选 gate | 3，兼顾 1/2/4/5 |
| GEPA | 反思、变异、per-instance Pareto、merge | score + ASI；candidate lineage；可恢复 state | validation Pareto、overlap floor、state assertions | evaluation cache、minibatch、metric/reflection budget | 1/2/3/4 与降本 |
| A-Evolve | propose k → isolated eval → Pareto select/apply | read-only archive、snapshot、score/cost/trace | 先 validation、失败归档、低于 incumbent 回滚 | selective skill load、便宜 gate 前置 | 3/4/5 |
| Adaptive Auto-Harness | whole-store/tree/retrieval/agentic filter | catalog → retrieve → materialize | filter 解析失败 deterministic fallback；worktree 隔离 | top-k 注入；filter 512 tokens | 4/5 与运行时降本 |
| SearchOS | Coverage gap 驱动的 pipeline-parallel frontier | SOCM：frontier/evidence/coverage/failure/budget | locked RMW、dispatch revalidation、loop sensor、atomic promotion | role projection、动态裁剪、分层技能、连续调度 | 1/2/3/4/5、协作控制面 |
| Argus | 线性 stage + gate/repair/rollback | 稳定 failure ID、checklist hash、transition history | 唯一裁决者、非法转移 fail-closed、原子状态写 | 调用前预算 reservation、局部角色预算 | 确定性状态与预算 |
| DGM | archive population，从任意祖先继续分叉 | parent-child lineage、patch chain | small → extended/full eval；continue-from | early screen、阈值式 full eval | 2/3 与评估降本 |
| Continual Harness | 窗口内对 prompt/agents/skills/memory CRUD | 分层 store、checkpoint、trajectory history | schema/caps、恢复、局部窗口 | overview + 按需读取、tool-less local role | 4/5 与上下文控制 |
| ADAS | archive 驱动的代码架构搜索 | JSON 方案、fitness/generation | 有限 debug retry；valid/test 分离 | 并行 eval；但全 archive prompt 会膨胀 | portfolio 和 split 的弱参照 |
| AgentSquare | reasoning/memory/planning/tool 模块重组 | 模块固定 I/O | 有限模块空间、step/task 边界 | 记录 token，但无硬门禁 | 5 的模块接口与冲突声明 |
| SIA | generation → execute → feedback | code/log/rationale/context | sandbox、失败仍反馈、输入截断 | bounded previews、低 turn summarizer | 4 的二级摘要材料 |

## 4. 局限一：证据覆盖要求不足

### 4.1 成因：设计思路

当前协议把 Evidence Review 主要建模成“这条 Trial 是否支持 Hypothesis”，而不是“Hypothesis 的每个可泛化主张覆盖了哪些案例和反例”。因此：

- Trial 是证据的最小单位，但缺少更高一层的 **claim × case-role × phase** 覆盖单元；
- “至少一条证据”容易被误读成“足够蒸馏”；
- MechanismSpec 能表达触发条件和适用范围，但协议没有强制其 scope 不得宽于证据；
- Reviewer 的语言判断承担了本应由程序完成的 distinct-case、polarity、phase 和 counterexample 计数。

### 4.2 成因：架构实现

[`EvidenceReview`](../../search_harness/evolution/research/roles/contracts.py#L168) 只有 phase finding、assessment、risk 和 obligation；没有：

- distinct example count；
- positive trigger / negative control / boundary 角色；
- required vs observed phase path；
- contradictory evidence；
- scope claim 与 coverage 的机器可验证对应。

因此 Mechanism Distiller 得到的是一组语义材料，不是可判定的 coverage report。

### 4.3 对可靠性和稳定性的影响

影响为 **高**：它会制造系统性假阳性，而不只是偶发错误。单案例成功可能来自题面偶合、随机采样、特定 prefix、Hook-model 偶然输出或其他 phase 的污染；一旦被蒸馏成通用 Mechanism，就会放大到多个任务和后续 Candidate。

该问题还会污染 Experience Store：如果过宽结论先被写成历史经验，后续角色会将未经证实的推论当成先验。

### 4.4 相关工作的解决方式

#### GEPA：per-instance/objective Pareto

GEPA 不只保留总分，而是记录每个 validation example 上的 Candidate 表现和 Pareto 前沿；局部 specialist 可以保留，但不会被误称为全局最优。[`state.py`](../../research/gepa/src/gepa/core/state.py#L159) 还为 candidate/example cache 和 validation state 提供了一等结构。

可迁移点是：**coverage 必须是 evaluator/controller 的输出，不是 Reviewer 的自述。**

#### SearchOS：Coverage Map + Evidence Graph

SearchOS 论文第 5–6 页把 evidence 原子化，并让 Coverage Map 显式区分 `missing / filled / uncertain / unreachable`；冲突证据保留 conflict，而不是以后到者覆盖前者。Evidence Graph 中 rejected/superseded finding 仍可审计，但不计入覆盖。

#### A-Evolve Navigation：记录 does-not-cover

A-Evolve 的 navigation 研究日志要求记录 coverage、`does_not_cover`、works、latency 和 error，而不是只保留成功摘要：[`research.md`](../../research/a-evolve/agent_evolve/algorithms/navigation/templates/prompts/research.md#L10)。这提示适用边界应是经验和机制的一等字段。

### 4.5 可选方案与规模

#### 方案 A：只提高数量阈值（S）

- 要求至少 N 个不同 example 的支持证据；
- 每个 Mechanism phase 至少一条 reached evidence。

优点是改动小；缺点是 N 条同质正例仍不能验证不误触发，且无法约束 scope。适合作为临时止血，不应作为终局。

#### 方案 B：Evidence Coverage Contract（M，推荐）

新增程序持有的覆盖结构：

```json
{
  "claim_id": "phase-rule-1",
  "required_cells": [
    {"role": "positive_trigger", "min_distinct_examples": 2},
    {"role": "negative_control", "min_distinct_examples": 2},
    {"role": "boundary", "min_distinct_examples": 1}
  ],
  "observed_cells": [],
  "contradicting_refs": [],
  "status": "missing|supported|conflicted"
}
```

Controller 负责引用存在性、distinct count、phase reached 和 polarity；Reviewer 只解释矛盾和提出下一条最有信息增益的 Trial。

#### 方案 C：Coverage Frontier + 主动选例（L）

在方案 B 上增加：

- 以未覆盖 cell 为 Trial planner 的 frontier；
- 按信息增益选择正例、负控或边界；
- 多机制并存时用 bounded Pareto archive 保留 specialist；
- scope 自动收窄到已观察区域，扩 scope 必须补证据。

它最接近 GEPA + SearchOS 的组合，但需要新的 planner、archive pruning 和 coverage-aware stop policy。

## 5. 局限二：Conformance 验证范围过窄

### 5.1 成因：设计思路

当前 Conformance 的目标被限定为“Candidate 是否复现 Intervention 中观察到的机制”，没有同时承担：

- 正确触发的稳定性；
- 应当不触发时的 selectivity；
- 适用边界；
- 不同 Hook-model/采样设置下的一致性；
- 相对 parent 的回归风险。

它更像局部 implementation witness，而不是机制行为契约。

### 5.2 成因：架构实现

[`aggregate_conformance`](../../search_harness/evolution/research/conformance.py#L159) 固定构造每例三次 replay；每例 `faithful_count >= 1` 即通过，只把 `runtime_error` 和 `implementation_mismatch` 视为全局 hard failure。因此一条 faithful 加两条 `not_observed` 仍可通过。

同时 case 来源只由 Intervention Trial 组成，缺少独立 manifest、negative cases、held-out cases 和 parent-paired runs。

### 5.3 对可靠性和稳定性的影响

影响为 **高**。问题通常不会在便宜的 Conformance 阶段暴露，而会延迟到完整 Candidate Evaluation：

- Hook trigger recall 低导致机制偶尔生效；
- false activation 破坏原本正确的任务；
- Hook-model 对 wording/model config 敏感；
- Candidate 在原案例有效但跨案例退化。

这不仅降低可靠性，也显著浪费 Student/Teacher token 和评估资源。

### 5.4 相关工作的解决方式

#### Self-Harness：paired baseline/candidate gate

Self-Harness 默认检查 train 和 heldout，并要求 baseline/candidate 的 repeat 数、repeat ID 和样本分母一致；接受规则要求 split 不退化且至少一个 split 改善：[`run_acceptance_gate.py`](../../research/self-harness/acceptance/scripts/run_acceptance_gate.py#L77)。这解决“比较对象不一致”和“只看 Candidate 绝对表现”的问题。

#### DGM：分层评估

DGM 先做小规模 screen，再对有希望的候选扩展评估，最后才进入 full evaluation：[`self_improve_step.py`](../../research/dgm/self_improve_step.py#L125)。可借其 cascade，但不能照搬其弱统计阈值和单次评估默认值。

#### GEPA：validation case 不被 aggregate 掩盖

GEPA 持久化 per-example validation 表现，使 Candidate 无法用一组案例的收益遮蔽另一组案例的遗忘。其 `merge_val_overlap_floor` 还阻止在共同验证样本不足时盲目合并：[`api.py`](../../research/gepa/src/gepa/api.py#L134)。

### 5.5 可选方案与规模

#### 方案 A：收紧现有 3-repeat 聚合（S）

- 从 `>=1 faithful` 改为多数或比例阈值；
- 给 `not_observed` 设置最大比例；
- 单独报告 Wilson/Beta-binomial 区间。

这可减少偶然通过，但仍没有验证负控和跨案例泛化。

#### 方案 B：Conformance Manifest（M，推荐）

把 suite 从 Intervention Trial 推导物升级为持久化 manifest：

```text
positive_trigger
negative_control
boundary
historical_regression
hook_model_variant
```

每个 case 固定 `case_id / split / role / expected_phase_path / expected_action / seed / repeat_id / parent_digest / candidate_digest`。聚合分别计算：

- trigger recall；
- correct abstention；
- false activation；
- phase-path completion；
- runtime/implementation failure；
- parent-candidate delta；
- token/latency delta。

#### 方案 C：五层验证级联（M–L）

```text
1. static/schema/API validation
2. targeted Conformance：原 Trial + 必需负控
3. coverage-completion replay：边界与历史 regression
4. promotion-validation：未参与 discovery 的 heldout
5. full Candidate Evaluation / final test
```

每层有稳定 reason code 和 early exit。最终 test 必须永不注入角色、永不参与方向选择；否则它会被自适应过拟合。

## 6. 局限三：Candidate 拒绝后无法继续探索

### 6.1 成因：设计思路

当前状态机把 Hypothesis、Mechanism、Candidate 与 Evolution Run 近似建模成一条线性链。`revise` 表示链内回流，`reject` 则被解释为整个方向乃至 Run 的终态，缺少更高一层的 portfolio/search-round 概念。

### 6.2 成因：架构实现

Promotion Gate 失败时，只有 Reviewer 给出 `revise` 且 revision budget 尚存才设置 `after_rejection`；其他情况会把它清空。[`on_reject_candidate`](../../search_harness/evolution/control/transitions.py#L543) 遇到空 route 就返回 `complete_reason`。

状态机没有：

- DirectionAttempt；
- Candidate Queue；
- rejected attempt ledger；
- next unexplored direction；
- Generation 级 no-progress/budget stop policy。

### 6.3 对可靠性和稳定性的影响

影响为 **高**。一次不可修复的局部失败会使搜索召回率骤降；同时激励 Reviewer 把本应 reject 的方向标成 revise，以避免整个 Run 终止，反而造成无效修订和 token 浪费。

### 6.4 相关工作的解决方式

#### Self-Harness：队列和分支

Self-Harness 将 proposal 持久化入 queue，逐个 materialize/evaluate/gate。Reject 只把当前 item 标为 rejected；其余 pending item 继续。全拒绝时也继续下一 round：[`run_self_harness_loop.py`](../../research/self-harness/workflow/scripts/run_self_harness_loop.py#L478)。多个 accepted sibling 先 merge，再独立重评估；merge 失败不污染 parent。

#### A-Evolve Meta-Harness：同 cycle 多候选

同一 cycle 先提多个 Candidate，再隔离评估，最后 Pareto select；invalid candidate 归档但跳过昂贵评估，最佳者低于 incumbent 时 rollback：[`engine.py`](../../research/a-evolve/agent_evolve/algorithms/meta_harness/engine.py#L213)。

#### DGM：开放祖先 archive

DGM 可以从 archive 中较早祖先再次分叉，而不是永远沿最后一条链：[`DGM_outer.py`](../../research/dgm/DGM_outer.py#L50)。这提高探索多样性，但其 `keep_all` 策略会造成 archive 膨胀，不宜原样采用。

### 6.5 可选方案与规模

#### 方案 A：Reject 后直接回到 Research Hypothesis（S）

保持单队列，只在 reject 时重启 hypothesis。改动小，但无法去重、保存方向边界或区分同方向 revision 与新方向。

#### 方案 B：SearchRound + Attempt Ledger（M，推荐）

新增层级：

```text
Generation
  SearchRound
    DirectionAttempt
      HypothesisAttempt
        CandidateAttempt
```

Candidate 的终态包括：

```text
rejected_validation
rejected_conformance
rejected_promotion
abandoned_mechanism
stalled
superseded
accepted
```

局部终态写入 reason code、evidence、fingerprint 和 parent version，然后调度下一方向。只有 Generation budget、全局 no-progress 或不可恢复基础设施错误能结束 Run。

#### 方案 C：bounded portfolio / branch search（L）

允许多个 promising Direction 并存，并从 accepted、specialist 或较老 parent 选择下一父本。必须同时实现：

- archive capacity；
- dominance/novelty pruning；
- duplicate mechanism fingerprint；
- isolated workspace；
- stale attempt revalidation；
- 并发预算。

## 7. 局限四：缺少可复用研究经验系统

### 7.1 成因：设计思路

当前持久化面向恢复和审计，默认“角色需要时可以读历史 artifact”。但原始事件、轨迹和版本差异不是可直接使用的经验：它们缺少适用边界、反证、可信状态、版本 epoch 和角色投影。

### 7.2 成因：架构实现

[`CandidateReviewerInput`](../../search_harness/evolution/research/roles/contracts.py#L607) 已有 `historical_experience`，但调用方固定传 `[]`。系统没有：

- Experience extractor；
- 结构化 schema；
- applicability filter；
- retrieval/index；
- role-specific projection；
- feedback/usage ledger；
- supersede/expire 语义。

### 7.3 对可靠性和稳定性的影响

影响为 **中高**，且随 Generation 数增长。直接后果是重复假设、重复编译错误、重复误触发和历史退化重现。若简单把全量历史塞入 prompt，又会产生 token 膨胀、过时经验污染和错误自我强化。

### 7.4 相关工作的解决方式

#### SearchOS：Failure Memory + role projection

Failure Memory 记录失败类型、scope signature、纠正建议、重复次数和最近时间；下一 agent 只接收匹配当前范围的内容。完整 SOCM 留在对话外，角色获得职责相关投影。

#### A-Evolve：archive 是事实层，不只是胜者榜

Meta-Harness archive 保存 snapshot、score、cost、metadata、trace 和 validation error；Navigation 使用结构化 `research_log.jsonl`/`insights.jsonl` 避免重测。可借其“失败也保留”的事实层，但不应让模型自行扫描全 archive。

#### Continual Harness：概览 + 按需读取

Prompt 只注入按 path 分组的 `[id] title` 概览，正文通过工具按需读取：[`PokeAgent.py`](../../research/continual-harness/agents/PokeAgent.py#L2300)。Memory entry 有 path、tag、importance、source 和 mutation history：[`memory.py`](../../research/continual-harness/utils/stores/memory.py#L17)。

#### SIA：bounded preview 只能作导航

SIA 截断 execution log，并只预览少量 trajectory 给 Feedback Agent。这适合生成 brief，不适合作为 Promotion 证据，因为摘要可能遗漏反例。

### 7.5 可选方案与规模

#### 方案 A：生成每代摘要并注入下一代（S）

实现快，但容易产生无证据、不可失效的叙事记忆。只适合短期导航。

#### 方案 B：Evidence-backed Experience Store（M–L，推荐）

建议记录：

```json
{
  "id": "...",
  "kind": "mechanism_boundary|rejection|compiler_failure|student_behavior|role_procedure",
  "fingerprint": "...",
  "claim": "...",
  "applicability": {
    "student_model": "...",
    "task_family": "...",
    "baseline_epoch": "...",
    "hook_phase": "..."
  },
  "coverage": [],
  "does_not_cover": [],
  "supporting_refs": [],
  "contradicting_refs": [],
  "outcome": "provisional|confirmed|refuted|superseded",
  "reason_code": "...",
  "created_by": {"run": "...", "attempt": "..."}
}
```

写入流程应为：

```text
immutable facts/artifacts
  -> deterministic extraction where possible
  -> LLM draft for semantic fields
  -> evidence/reference validation
  -> provisional card
  -> repeated support or independent verification
  -> confirmed card
```

读取流程应为：

```text
baseline/model/task/phase metadata filter
  -> contradiction and expiry filter
  -> FTS/embedding top-k
  -> role-specific compact projection
  -> optional get_experience(id)
```

#### 方案 C：事实库与 Role Playbook 双库（L）

借鉴 Argus 的 role-owned memory，但加强治理：

- `ExperienceRecord`：跨角色只读的事实、边界和失败签名，必须带 evidence；
- `RolePlaybook`：Compiler/Reviewer 等角色的可复用工作程序，不得包含具体任务结论；
- 角色不能直接写全局库，只能提交 draft，由 extractor/verifier 晋升。

## 8. 局限五：固定基线资产造成长期补丁叠加

### 8.1 成因：设计思路

Fixed 边界很好地保护了初始能力，却把“安全隔离”与“永不重构”绑定在一起。普通 Evolution 只能通过 mutable Extension 改行为；成熟修复无法回收到基础 Component，也无法删除已被替代的间接 Hook。

### 8.2 成因：架构实现

[`_fixed_path_errors`](../../search_harness/evolution/versioning/validation.py#L192) 禁止 fixed root 下任何文件变更；fixed component 的 manifest 也不可改变，新 component 必须 mutable。系统没有：

- baseline epoch；
- maintainer/normalization authority；
- Extension 冲突/重叠图；
- complexity/call-count gate；
- mature Extension 的 merge/delete/migration；
- normalization 后的历史 Mechanism lineage。

### 8.3 对可靠性和稳定性的影响

短期影响为 **中**，长期为 **高**：

- 同一行为被多层 Hook 重复判断；
- precedence 和 side effect 发生冲突；
- 每层增加 prompt、Hook-model 调用、延迟和失败面；
- Component 已修正但旧 Extension 仍继续覆盖；
- Reviewer 难以判断实际生效路径。

### 8.4 相关工作的解决方式

#### Continual Harness：全资产分层 CRUD

它允许 Refiner 对 prompt、sub-agents、skills、memory 做 CRUD，而不是只追加 Hook：[`README.md`](../../research/continual-harness/README.md#L47)。这证明“可删除/可合并”对长期演化重要，但其强依赖模型能力，不适合让小模型直接修改 foundation。

#### Adaptive Auto-Harness：按任务选择而非全量执行

`RetrievalAdaptation` 和 `AgenticFilterAdaptation` 只 materialize 当前 task 的 top-k skill/tool/memory；filter 失败时 deterministic fallback：[`operators.py`](../../research/adaptive-auto-harness/agent_evolve/protocol/adaptation/operators.py#L32)、[`harness_filter.py`](../../research/adaptive-auto-harness/agent_evolve/protocol/adaptation/harness_filter.py#L20)。这能先降低补丁同时激活的冲突和 token 成本。

#### A-Evolve SkillForge：draft 到多任务 promotion

新技能先进入 `_drafts`，达到多个任务的 promotion threshold 后才进入主库：[`skillforge.md`](../../research/a-evolve/docs/algorithms/skillforge.md#L219)。可以把这一路径升级为 mature Extension 的归一化准入条件。

#### AgentSquare：显式模块接口

AgentSquare 把 reasoning、memory、planning、tool-use 模块定义为固定 I/O：[`modules/README.md`](../../research/agent-square/modules/README.md#L1)。当前可以进一步让 Extension 声明 owned input/output、phase、effect、conflict/exclusive group，使冲突可静态分析。

### 8.5 可选方案与规模

#### 方案 A：只做 Extension activation 与冲突治理（M）

新增 `activation_scope`、phase、task family、priority、exclusive group、owned outputs、max calls 和 estimated cost；运行时只加载相关 Extension。

它能缓解成本和冲突，但不消除长期堆积。

#### 方案 B：独立 Normalization Run（L，推荐）

采用双平面权限：

- **Evolution Run**：仍只能创建/修改 mutable Extension；
- **Normalization Run**：由 maintainer/strong teacher 发起，可修改 foundation、合并/删除 mature Extension，产生新 `baseline_epoch`。

归一化必须在 isolated workspace 中执行：

```text
mature Extension set
  -> temporary assembly
  -> semantic overlap/conflict analysis
  -> rewrite foundation + migration map
  -> historical Conformance replay
  -> negative controls + heldout + full evaluation
  -> complexity/token/latency comparison
  -> atomic baseline epoch promotion or rollback
```

#### 方案 C：可组合 Component Graph（L+）

将基础 Prompt/Tool/Output 和 Extension 统一为 typed component graph，每个节点声明输入输出、owned state、effects 和 precedence。普通 Evolution 操作 graph 的 mutable 区域，Normalization 重写 graph 边界。长期最干净，但迁移成本最高。

## 9. 任务设计、拆解和角色设计

### 9.1 什么应串行，什么可并行

随附论文 *Capable language models can outgrow the benefits of collaboration* 表明：多智能体收益取决于自然可分解性、单 agent baseline 和协调开销；强顺序任务被人为拆分后可能明显退化。论文在受测域内观察到约 45% 的 capability-saturation 分界，但 leave-one-domain-out 泛化很差，不能把这个数值直接变成当前系统的硬阈值。

当前角色链应保持串行：

```text
Evidence review -> Mechanism distillation -> Compilation -> Candidate review
```

适合并行的只有冻结输入后的独立工作：

- 同一 Hypothesis digest 下的不同 Trial / negative controls；
- 同一 Candidate digest 下的独立 Conformance case；
- frozen candidate 的 evaluation shard；
- 不改状态的经验检索和静态检查。

默认拓扑应是 **单 Controller + 并行纯执行 worker + 集中聚合/验证**，而不是 peer debate。

### 9.2 推荐角色职责

| 角色 | 只负责 | 不应负责 |
|---|---|---|
| Direction Planner | 从 coverage gap、失败签名和 portfolio 提新方向 | 决定状态转移、直接修改 Accepted Version |
| Trial Planner | 选择最高信息增益的 case role/cell | 自报 coverage 已满足 |
| Evidence Reviewer | 解释观察、矛盾和边界 | 计算 distinct count、引用合法性 |
| Mechanism Distiller | 生成受 coverage 约束的 Mechanism Draft | 扩大 scope 超过证据 |
| Compiler | 在 isolated workspace 实现候选 | 写 Experience Store、直接晋升 |
| Conformance Reviewer | 对语义难以程序判断的 rollout 分类 | 选择 suite、修改阈值 |
| Candidate Reviewer | 汇总机制、性能、成本风险 | 绕过 deterministic gate |
| Experience Extractor | 从已落盘事实生成 provisional cards | 将未引用叙事直接标 confirmed |
| Evolution State Decider | 校验合法 transition/reason code | 生成开放性研究内容 |
| Normalization Maintainer | 合并成熟 Extension、迁移 baseline epoch | 在普通 Evolution 中静默改 fixed assets |

### 9.3 推荐 I/O 原则

1. 每个角色只接收 artifact ref、digest、active obligation 和角色相关 projection。
2. Coverage count、case role、phase reached、token total、diff fingerprint 均由程序计算。
3. 角色输出为 schema 化 recommendation + reason code + evidence refs；Controller 决定状态。
4. 长轨迹和完整 diff 作为按需资源，不默认拼入 prompt。
5. 每个 artifact 带 `baseline_epoch / parent_version / model_config / dataset_digest / seed`。

## 10. 多智能体协作稳定性设计

### 10.1 单一事实源和原子状态变更

SearchOS 最关键的经验是：共享状态属于 Harness，不属于 conversation。Trial 完成时应在一个 effect/transaction 内共同落盘：

```text
rollout result
evidence finding
coverage delta
attempt status
usage settlement
```

否则恢复时容易出现“Evidence 已写但 coverage 未更新”或“调用已花费但 usage 未记账”的半状态。

### 10.2 唯一状态转移权威

Argus 的 Manager 是唯一 transition authority；非法或模糊建议 fail-closed 到 HOLD。当前应进一步用纯程序 transition table 实现：

```text
coverage insufficient       -> plan_coverage_trial
evidence conflicted         -> resolve_conflict
mechanism refuted           -> close_attempt / next_direction
implementation mismatch     -> revise_implementation
candidate rejected          -> next_direction
promotion passed            -> accept_version
global budget exhausted     -> finish_generation
```

### 10.3 稳定 ID、去重和 stale revalidation

- 每个 failure/coverage cell/attempt 使用稳定 ID；
- Hypothesis、Mechanism 和 candidate diff 生成 canonical fingerprint；
- dispatch 前重新验证依赖、输入 digest 和目标 cell 是否已被同伴完成；
- 恢复时以 effect idempotency key 防止重复 LLM/Trial 调用。

SearchOS 的 scheduler 使用 lock 防止并发 tick 超卖 slot，并在 dispatch 前跳过已被其他 worker 填充的任务；内部证据位于 `SearchOS-main.zip :: searchos/agents/orchestrator/scheduler.py:47-51,324-396`。

### 10.4 失败分层和可恢复性

不要把所有失败都归为 revise/reject：

| 原因 | 正确路由 |
|---|---|
| `not_observed` | 补触发证据或降低稳定性置信度 |
| `inconclusive` | 改善观测/Reviewer，不应算 implementation mismatch |
| `implementation_mismatch` | Compiler revision |
| `mechanism_refuted` | abandon DirectionAttempt |
| `false_activation` | trigger/scope revision，必要时 reject mechanism |
| `runtime_error` | 隔离实现/环境问题，有限 retry |
| `promotion_regression` | archive Candidate，探索新方向 |
| `global_budget_exhausted` | 顶层结束 |

### 10.5 循环和停滞检测

SearchOS 的 loop sensor 同时检查重复 query、无实质结果和 coverage/evidence delta 不增长；先 nudge，重复后写 `looped` 状态，由 Controller 重分配。当前可定义：

```text
same direction fingerprint repeated
same deterministic failure repeated
coverage missing cells unchanged
no new evidence refs
no score/cost frontier change
```

停滞应关闭局部 attempt，而不是立即结束全 Run。

## 11. Token 和调用成本设计

### 11.1 优先采用的七项机制

1. **Candidate × example evaluation cache**（GEPA）  
   Cache key 至少包含 candidate/template digest、Student model/config、example/dataset digest、seed/temperature 和 Hook runtime version。随机 rollout 的单次结果不能无条件复用。

2. **调用前 budget reservation**（Argus）  
   采用 `reserve -> call -> settle/release`，覆盖 Teacher、Student、Hook-model 和 Reviewer，而不只是事后累计。当前 Trial Reviewer token 漏记也应在此一并修正。

3. **静态门禁前置**（A-Evolve）  
   schema、manifest、API、fixed boundary、重复 diff 和明显冲突先检查，失败者归档但不进入昂贵评估。

4. **分层评估和 early exit**（DGM）  
   targeted Conformance 先于 heldout/full evaluation；但阈值应包含绝对稳定性和误触发硬约束，不应只与 archive 第二高分比较。

5. **role-specific top-k Experience Cards**（Adaptive Auto-Harness / Continual Harness）  
   先 metadata hard filter，再检索 top-k；完整 Trial、trace 和 diff 按需展开。

6. **coverage-gap minibatch reflection**（GEPA）  
   Reviewer/Distiller 只读取当前缺口相关的少量案例，不读取全历史。多任务 reflection minibatch 可小到 3 个案例。

7. **delta-triggered role wakeup**（SearchOS）  
   只有 coverage/evidence/score frontier 发生足够变化时才唤醒 Reviewer/Writer；格式和计数交给程序。

### 11.2 并行不是天然降本

随附协作论文在 matched compute 下仍观察到明显协调开销，并发现固定 token budget 下超过约 3–4 个 agent 后每 agent reasoning 变薄。对当前系统，应记录：

```text
tokens_by_role
tool/model calls
coordinator tokens
message bytes
rework count
error propagation path
coverage gain per 1k tokens
```

只有当前 task family 的本地数据证明并行带来净收益，才增加 worker 数。

### 11.3 预期收益与新增成本

| 机制 | 主要节省 | 新增成本/风险 |
|---|---|---|
| eval cache | 重复 rollout/evaluator | cache key 错误会复用污染结果 |
| top-k cards | prompt token | retrieval miss 可能漏掉关键经验 |
| staged gates | full eval 调用 | gate 过严会损失探索召回 |
| portfolio | 减少从零探索 | archive/pruning 本身有维护成本 |
| selective Extension | 运行时 prompt/Hook calls | selector 必须进入 Conformance 审计 |
| deterministic checks | Reviewer token | 需要维护 schema 和 reason codes |

## 12. 不应照搬的设计与反例

1. **无界 Pareto/archive**：GEPA/DGM 的开放 archive 若不限制容量，会增加 parent selection、检索和上下文成本。必须按 mechanism family 设容量、dominance 和 novelty pruning。
2. **反复消费 valset**：搜索中多次根据 validation 选方向会产生自适应过拟合。至少保留一个永不注入、永不用于选择的 final test。
3. **无 heldout 自动接受**：A-Evolve 某些 gate 在 holdout 缺失时自动接受，当前必须 fail-closed 或明确标记 `validation_unavailable`。
4. **全 archive 拼 prompt**：ADAS 的 archive 会随代数线性增长；经验系统必须检索和投影。
5. **单次/弱阈值评估**：DGM 多处默认 `num_evals=1`，不能支撑随机小模型的稳定性判断。
6. **自由 peer debate**：协作论文表明独立/去中心化 agent 容易放大错误；当前强依赖链不应并行辩论。
7. **LLM 摘要作证据**：SIA 式 context summary 适合导航，不适合 Promotion。
8. **直接让小模型重写 foundation**：Continual Harness 的效果强依赖模型能力；Normalization 应由强 maintainer + deterministic regression 控制。
9. **两个单独通过就直接 merge**：Self-Harness 会对 merge 后候选重新评估；当前也必须如此，因为 Hook 交互不是可加性的。

## 13. 建议落地顺序

### 阶段 0：先修复现有正确性缺口（S）

- 校正当前 Accepted Template 的路径/validator 一致性；
- 修复 Trial Reviewer usage 漏计；
- 明确文档 `evolvable` 与代码 `mutable` 的术语差异；
- 让已有 heldout 配置真正进入 Controller 数据边界。

这些问题不属于五项长期架构局限，但会使后续实验结果不可信。

### 阶段 1：Evidence 与 Conformance 控制面（M）

- `EvidenceCoverageContract / CoverageReport`；
- `ConformanceManifest` 和 case roles；
- positive/negative/boundary/historical cases；
- paired parent/candidate、稳定 seed/repeat/digest；
- reason codes 和分层 early exit。

这是最高优先级，因为它决定后续 archive 和 experience 中的数据是否可信。

### 阶段 2：Reject continuation 与 attempt ledger（M）

- `SearchRound / DirectionAttempt / CandidateAttempt`；
- durable queue；
- Candidate/Mechanism fingerprint 与去重；
- 局部终态、recoverable flag、Generation stop policy；
- 暂时保持顺序执行，不急于引入并发 branch。

### 阶段 3：成本、恢复和经验（M–L）

- effect idempotency；
- pre-call budget reservation；
- candidate/example cache；
- Experience Store schema、extractor、top-k role projection；
- usage ledger、supersede/expire 和 contradiction。

### 阶段 4：Extension 治理与归一化（L）

- Extension activation/conflict/cost metadata；
- Normalization Queue；
- isolated assembly、historical replay、complexity gate；
- `baseline_epoch` 与 migration/lineage；
- atomic promote/rollback。

## 14. 建议的验收指标

不能只比较任务总分。建议至少跟踪：

| 维度 | 指标 |
|---|---|
| Evidence | distinct supporting examples、negative coverage、boundary coverage、conflict count |
| Conformance | trigger recall、correct abstention、false activation、phase completion、uncertainty rate |
| 搜索 | directions explored、duplicate rate、reject-continuation rate、coverage gain/attempt |
| 稳定性 | recovery duplicate-call rate、stale dispatches、illegal transition count、merge regression |
| 泛化 | discovery/validation/final-test delta、跨 Student/Hook-model variance |
| 成本 | token/call/latency by role、coverage gain per 1k tokens、full-eval avoided |
| 维护性 | active Extension count、Hook-model calls/task、overlap/conflict count、baseline complexity |

## 15. 最终建议

优先组合应是：

```text
GEPA：coverage / per-case validation / cache
+ Self-Harness：SearchRound portfolio / reject continuation
+ SearchOS：externalized state / frontier / middleware invariants
+ Argus：single transition authority / deterministic gates / budget reservation
```

先建立可信证据与 Conformance，再保存和复用经验；先实现顺序 portfolio，再考虑并行；先给 Extension 加激活与冲突治理，再开放独立 Normalization 权限。这样可以同时解决五项局限，又不会把当前系统一次性改造成难以控制的无界 population search。
