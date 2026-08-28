# Researcher-facing Experience Products v2（草案）

状态：讨论草案，尚未替换现有协议或实现。

## 1. 产品目标

Experience Product 不是对一次 Trigger、Review 或 Evaluation 的摘要。它是经过 Evidence 约束、能够直接改变 Hypothesis Researcher 后续判断的可复用认识。

一条有效 Experience 必须同时回答：

1. 在什么语义判定或研究方向上获得了什么认识；
2. 该认识在什么条件下成立；
3. Researcher 因此不能再未经验证地依赖什么，或可以保留复用什么；
4. 哪些 Evidence 直接支持该认识。

经验只约束 Researcher 的 claim、方案选择和 evidence obligation，不指定具体 Prompt、Hook、Intervention 或实现方法。

## 2. Observation、Proposal 与 Experience

```text
Workflow Artifacts
    ↓ deterministic projection
Observation Ledger
    ↓ summarization
Experience Proposal
    ↓ deterministic settlement / merge
Settled Experience
    ↓ relevance projection
Researcher-facing Experience View
```

- **Observation**：一次运行、比较、决策或结果的可追溯事实。
- **Experience Proposal**：Summarizer 根据一组 Observation 提出的可复用认识；仍需校验、合并和限定范围。
- **Settled Experience**：程序已校验 Evidence、scope、重复计数、身份和 revision 的持久化经验。
- **Researcher-facing Experience View**：只向当前 Researcher 提供相关的语义结论、研究约束和紧凑 Evidence 概况。

当前 `evidence_update` 类输出若只复述单一事件，应称为 Observation Assessment 或 Experience Delta，不应直接视为 Experience。

## 3. Capability Experience Product

### 3.1 语义

Capability Experience 描述指定 Student 或 Hook-model 在一个明确语义判定上的可复用限制，不得把实现、可见性或数据问题伪装成模型能力。它只说明模型不能稳定完成什么区分，不替 Researcher 选择修复方式。

### 3.2 Summarizer Proposal 与最终产品

`decision_scope` 是 Packet 提供的冻结判定范围，由程序原样附加到最终产品；不要求 Summarizer 重新生成。Summarizer 只归纳语义限制并选择直接 Evidence：

```python
class CapabilityExperienceProposal:
    observed_limitation: str
    evidence_refs: list[int]


class CapabilityExperienceSummary:
    items: list[CapabilityExperienceProposal]
```

Settlement 后的 Researcher-facing 产品为：

```python
class CapabilityExperienceProduct:
    decision_scope: str            # program supplied
    observed_limitation: str
    evidence_summary: str          # program computed
    evidence_refs: list[str]       # program resolved stable refs
```

| 字段 | 职责 |
|---|---|
| `decision_scope` | 程序从来源 Artifact 原样提取的冻结 predicate 或其明确标注的规则正文；可以移除同字段内的内部路径前缀，但不得改写语义正文。 |
| `observed_limitation` | 说明模型不能稳定完成的具体语义区分；只在原始输出提供解释时陈述内部原因，仅有 label 时只陈述可观察误判边界。 |
| `evidence_summary` | 程序根据稳定 Evidence key 计算的 distinct cases、replicates、重复/翻转结构和必要 provenance 警告；不由模型生成。 |
| `evidence_refs` | Proposal 只选择 Packet 中的 Observation 编号；程序结算为稳定 Evidence key。 |

程序在 Settled Experience 外层维护而不要求模型生成：

- model/harness/prompt/dataset scope；
- `decision_scope_ref` 与 experience identity/revision；
- distinct examples、replicates、support pattern 和 maturity；
- 完整 provenance、supporting refs 与真实 contradiction；
- 当前 experience 是否被新证据 supersede。

### 3.3 Packet 最小语义输入

Capability Packet 不能只提供 case ID 与 expected/observed label。Hook Feasibility 默认按真实 prefix case 展开：

```text
Decision scope: <verbatim frozen predicate from the source Artifact>
| Ref | Decisive reviewed observation | Expected | Observed by condition |
|---|---|---|---|
| 1 | Single-entity factoid; no second comparison entity exists | negative | disabled: positive, positive; enabled: negative, positive |
| 2 | Query explicitly names both comparison entities | negative | disabled: positive, positive; enabled: negative, negative |
```

`Decisive reviewed observation` 直接使用来源 Artifact 原文，不由实验人员或程序预写 Capability 结论。完整 prefix、label rules 和实际 model-visible input 仍通过 Detail 按需读取。

### 3.4 示例

```json
{
  "decision_scope": "Is this pre_final decision a two-entity comparative judgment being finalized on evidence that covers only the first entity?",
  "observed_limitation": "Hook model cannot reliably exclude clearly non-triggering inputs: single-entity fact questions, and cases where query history already covers both compared entities.",
  "evidence_summary": "thinking disabled: both expected-negative inputs were repeatedly labeled positive. thinking enabled: one input flipped negative→positive while the other remained negative.",
  "evidence_refs": [
    "hook_feasibility_probe#trial_6b6189fdef3a_002_pre_final",
    "hook_feasibility_probe#trial_6b6189fdef3a_003_pre_final"
  ]
}
```

这里的 `decision_scope` 是来源 Hook Feasibility Artifact 中
`decision_contract.predicate` 的原文；即使存在更简洁的转述，Product
Assembler 也不得替换它。

若原始模型输出明确解释内部误判原因，`observed_limitation` 才可以采用更强的成因表述。单个未重复异常仍只保留为 Observation。

## 4. Direction Experience Product

### 4.1 语义

Direction Experience 面向一个程序维护的 Research Direction：

```text
Failure Direction
└── Research Scheme
    └── optional Mechanism Scheme
```

三层身份、当前 summary 和 revision 由程序提供。Summarizer 不重新命名方向，也不从单次 Trigger 生成新的方向身份。Direction Experience 必须综合当前方向内已有 Attempt 的局部效果与下游终态，而不是只重述最新 Review。

### 4.2 Summarizer Proposal 与最终产品

```python
class DirectionExperienceProposal:
    learning: str
    reusable_parts: list[str]
    blocking_boundaries: list[str]
    retry_only_if: list[str]
    research_constraint: str
    evidence_refs: list[int]


class DirectionExperienceSummary:
    items: list[DirectionExperienceProposal]
```

Settlement 在最终产品外层附加程序维护的 `direction_context`、scope、identity、revision、`evidence_summary` 和解析后的稳定 Evidence refs；Summarizer 不重复这些字段。

| 字段 | 职责 |
|---|---|
| `learning` | 综合说明当前证据对该 Failure/Research/Mechanism Direction 建立了什么认识，必须区分 phase-local effect、evaluator feasibility、Candidate utility 和 cost。 |
| `reusable_parts` | 已有证据支持、可以在后续方案中保留的局部效果、判定边界或机制组成。 |
| `blocking_boundaries` | 使当前整体方案尚不可复用或晋升的已证实边界；不把未知写成失败。 |
| `retry_only_if` | 使下一次尝试实质不同于近义重复的可观察 Evidence 或条件变化；已晋升方向可以为空。 |
| `research_constraint` | 说明 Researcher 当前应如何限制 claim 或方案复用范围；不是 Controller route，也不指定具体实现。 |
| `evidence_refs` | 引用支持综合结论的 Observation；应覆盖被保留的局部效果和阻碍边界。 |

`failure_direction`、`research_scheme`、`mechanism_scheme`、scope、identity、revision 和 provenance 位于程序外层，不由模型重复生成。

### 4.3 示例

```json
{
  "learning": "一次性验证提示在目标 count 型桥接案例上能稳定诱发第二次定向检索并得到有证据终答；但当前 Hook evaluator 在非目标、非数值问题上过度激活，Student-visible 指令还会诱发拒答，因此局部干预效果成立而完整 Mechanism Scheme 尚未成立。",
  "reusable_parts": [
    "在已确认缺少终值的目标案例上，一次性验证反馈能够诱发后续定向检索。"
  ],
  "blocking_boundaries": [
    "当前 evaluator 不能稳定排除不需要终值验证的近邻负例。",
    "泛化的‘不要凭记忆回答’反馈可能把可回答案例推向拒答。"
  ],
  "retry_only_if": [
    "新的尝试对目标正例和近邻负例分别提供直接激活证据，并证明拒答退化不再出现。"
  ],
  "research_constraint": "后续可以复用‘缺少终值时追加一次验证反馈’这一局部效果，但不能把当前 evaluator 与反馈措辞作为已验证整体重复提交。",
  "evidence_refs": [1, 2, 3]
}
```

## 5. 触发与聚合

### Capability

直接模型行为证据产生时追加 Observation。达到重复、跨案例或稳定翻转门槛时可以生成 Capability Proposal；同一 Decision Scope 的新证据由 Settlement 更新既有经验，而不是创建表面近义的新记录。

### Direction

Evidence Review、Hook Feasibility、Compiler、Conformance、Candidate Review 和 Promotion Gate 只向 Direction Ledger 追加事实。Direction Summarizer 在以下时点运行：

1. Researcher 因下游回流即将重新决策前；
2. 当前 Research Direction 获得 Candidate terminal outcome 后；
3. Generation 结束且该 Direction 有新增 Evidence 时。

这样 Summarizer 能看到完整 Attempt history，而不是为每个事件生成一条孤立摘要。

## 6. Settlement 与 Researcher View

Settlement 至少负责：

- 校验所有 Evidence refs 与 scope；
- 确定性计算 distinct examples、replicates 和 support pattern；
- 根据 `decision_scope_ref`、Research Direction identity 和语义相似性执行 merge/update/keep-separate；
- 保留 revision，不覆盖历史 Evidence；
- 新证据与同范围旧结论冲突时收窄、标记 superseded 或保留 contradiction；
- 将程序 metadata 与模型语义结论组合为 Settled Experience。

默认 Researcher View 每个 Failure Direction 只投影最相关的少量记录，并始终保留：

- Capability 的 `observed_limitation + research_constraint`；
- Direction 的 `learning + reusable_parts + blocking_boundaries + retry_only_if + research_constraint`；
- 程序计算的紧凑 Evidence 概况；
- 可按引用读取详细 Evidence 的入口。

## 7. 验收方式

Schema 合法、引用有效和重复调用同向只是基础检查。产品验收必须增加 Researcher consumer A/B：

1. Baseline Researcher 只看当前 Failure Evidence；实验组额外看到 Experience View。
2. 两组使用相同模型、Prompt、预算和当前 Artifact。
3. 评估实验组是否：
   - 正确识别已证实的模型或机制边界；
   - 减少没有新 Evidence 的近义重复方案；
   - 保留仍有证据支持的局部效果，而不是因一次 Candidate 失败放弃整个 Failure Direction；
   - 不把 Experience 中的边界误读为指定修复方案；
   - 提出与 `retry_only_if` 一致、但实现方式仍具多样性的 Hypothesis。
4. 只有在语义质量不下降且 Researcher 决策出现上述有益变化时，才能认为 Experience Product 可用。

## 8. 调研依据

- Reflexion 将自然语言反馈保存在 episodic memory 中，目的明确是影响后续 trial 的决策，而不是保存一份归档摘要：<https://arxiv.org/abs/2303.11366>。
- ExpeL 从多项训练 experience 中抽取 insight，并在 inference 时召回这些 insight；其 insight extraction 是跨 experience 的维护过程，不是每个事件各写一条不可变摘要：<https://arxiv.org/abs/2308.10144>，<https://github.com/LeapLabTHU/ExpeL>。
- Generative Agents 区分完整 observation stream 与更高层 reflection，再按当前规划需要检索 reflection：<https://arxiv.org/abs/2304.03442>。
- 本项目先前 Minimal Curator 已采用 `researcher_scheme_summary`、`student_capability_summary`、Observation/Attempt Ledger 和显式 `researcher_decision_change`；v2 应恢复其“改变 Researcher 决策”的产品目标，同时保留当前实现更严格的 provenance 与 typed routing。
