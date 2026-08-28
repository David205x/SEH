# TASK-007 Researcher-facing Experience 联调实验计划 v18

> 实施状态：待用户批准。本文取代 v17 作为下一轮实施基线；v17 保留为历史方案。下一轮只实现 shadow Experience Product、current-v2 controlled replay 和真实 Teacher API consumer A/B，不修改正式 Evolution 路由、Experience Store 或现有角色协议。

## 当前状态

- 已完成 Capability/Direction Summarizer、Source Adapter、Detail、三层 Research Direction 身份和 Controller 旁路挂载。
- 真实 API 验证证明现有 Summarizer 能形成结构合法、Evidence 可追溯的摘要，但 Capability 主要复述三值标签偏差，Direction 主要复述单次事件，尚未证明 Experience 能改变 Hypothesis Researcher 的后续决策。
- 已形成 [Researcher-facing Experience Products v2 草案](../../docs/design/experience-products-v2-draft.md)，作为本轮 shadow 协议的设计输入；该草案尚未成为正式 Role Contract。
- `research_constraint` 是否进入正式 Experience 尚未确定。首轮只测试事实型 Experience；只有事实被正确理解但不能转化为合理研究决策时，才启用独立的 constraint 对照。
- 单个未重复异常继续保留为 Observation，本轮不修改 Capability eligibility，也不从有目的选择的少量历史 Case 推断其总体频率。
- v17 选择的历史 Researcher Artifact 均为 `hypothesis_researcher@1`、`intervention_hypothesis@4`；当前代码只注册 `hypothesis_researcher@2`、`hypothesis_researcher_result@1`，并严格校验 Role scope、template root、输入、资源和 system instruction。历史 Artifact 不能被当前 Runner 原样 continuation。
- Candidate reject/promotion fail 已在 Controller 中生成 `candidate_reviewer` 或 `promotion_gate` feedback source，但正式 Hypothesis Researcher template 尚未注册这两个 continuation source。该缺口影响正式主链可执行性，但 shadow controlled replay 不依赖 continuation template，本轮不借实验修改正式路由。
- 2026-08-26 使用指定 Conda 环境执行全量 `unittest discover -s tests -t .`，共 369 项，结果为 1 failure、2 errors。其中两项与 v16 改动直接相关：Hook Feasibility 测试 fixture 缺少 `research_scheme_id`；另一个测试仍期望直接返回 Researcher，而当前设计会先调度 Capability side work。第三项是已排除 Visualizer 的旧导入错误，与 TASK-007 无关。
- 现有 Run 提供完整的 Hook Feasibility、Evidence Review 和 Candidate rejection Artifact。本轮不重新执行 Incumbent/Candidate Evaluation，不调用 Student 或 Intervention Worker。

## 任务意图

本任务验证“更新后的 Experience 是否能改变当前 Hypothesis Researcher 的证据使用和方案选择”，而不是继续验证 Summarizer 能否生成合法摘要。实验从真实历史 Artifact 确定性重建当时的问题、旧 Hypothesis 和下游反馈，再用当前 `hypothesis_researcher@2` 执行显式标记的 controlled replay，对比无 Experience、事实型 Experience，以及必要时带 Research Constraint 的 Experience。

本任务直接服务 Goal H3：

> “将已结算轨迹中的 typed verification verdict 与终态转为有 provenance、严格 consumer/scope、可失效和可复查的 role-scoped experience，能够减少跨 attempt/generation 的能力越界、同角色错误复发和方向重走，并提高单位总预算的 useful Candidate yield，同时控制 false pruning 与 held-out utility。”

本轮只验证 H3 中“Experience 是否改变 Researcher 决策”的开发期前提，不声称证明跨 generation yield、false pruning 或 held-out utility。

实验保持 H1/H2 的既有 Evidence 与 Hook Feasibility 语义：

> H1：“在持久化 Candidate 物化前，冻结真实 Student Prefix 上的 matched no-op 与不可部署 soft intervention 证据能够预测 downstream Candidate effect，并在预算匹配下提高 useful Candidate yield、减少无效完整评估。”

> H2A：“对 Student-owned recognition、decision、adherence、fallback 与 parse responsibility 的独立 probe 能够预测未参与 probe 的真实 Prefix 上的 shadow/in-loop realizability。”

> H2B：“基于逐职责 realizability 证据在 reject、simplify、deterministic lowering 与 ownership reassignment 之间进行 adaptive routing，相对固定 ownership 策略能够提高可实现且有用的 Candidate 产出并减少浪费。”

实验不修改历史 Trial reference、Reviewer verdict、Candidate outcome、Promotion Gate 或正式路由判据。

## 实施思路

### 1. 使用 current-v2 controlled replay

每个 replay base 从历史 Artifact 确定性组装：

```python
class ResearcherExperienceReplayInput:
    problem_direction: dict[str, object]
    previous_hypothesis: dict[str, object]
    feedback_source: str
    feedback: dict[str, object]
    experience_view: list[dict[str, object]]
```

字段职责：

- `problem_direction`：历史 Failure Analyst 的冻结输出，限定仍在研究的问题范围。
- `previous_hypothesis`：下游反馈直接针对的历史 Hypothesis；它是待修订对象，不伪装成当前 session output。
- `feedback_source`：原始 typed 下游角色或 Gate 来源，用于解释 feedback 的职责边界。
- `feedback`：目标 event 当时实际可见的结构化 Reviewer/Gate 结果，不补写未来信息。
- `experience_view`：当前实验 arm 注入的 Researcher-facing Experience；control 为空数组。

Shadow replay 使用当前 `hypothesis_researcher@2` 的 system Prompt、tools、模型配置、预算和 `HypothesisResearcherResult` 输出协议；user message 明确说明这是从历史 Artifact 构造的 current-v2 replay，不恢复旧 transcript、role session 或 feedback history，也不声称复现历史调用。

所有 arm 克隆同一个 replay base，唯一差异是 `experience_view`。历史 Researcher 的实际 continuation 结果只用于实验后比较，不作为目标答案或 Prompt few-shot。

### 2. 先测试事实经验

首轮 Experience 只提供：

- 被测试的语义判定或 Research Direction；
- 已观察到的模型/机制行为边界；
- 条件和程序计算的 Evidence 结构；
- Direction 中已支持的局部效果与已证实阻碍。

不提供 `research_constraint`、Prompt 建议、Hook 设计或 route 命令。Researcher 自行决定 `revise_current`、`start_new` 或 `reanalyse_failure`，并自行调整 activation、intervention、scope、success/falsifier 和 evidence obligation。

只有 facts-only arm 中多数输出准确复述 Experience，却仍提交与已失败边界同质的方案，或没有把明确限制反映到 success/falsifier 与 evidence obligation 时，才在同一 replay base 上增加 `facts_with_constraint`。Constraint 只能说明“不能未经验证地依赖什么”或“哪项 claim 仍需直接证据”，不能指定解决方法。

### 3. 冻结单一 Experience，分离两层随机性

每个 Summarizer input 先独立运行三次，用于检查产品稳定性，不直接形成三套 Researcher treatment：

1. 三次原始输出全部保存，不修改内容；
2. `rep_01` 预先指定为候选冻结 Experience，不允许人工改选表现更好的 repetition；
3. 对 `rep_01` 执行固定 source-faithfulness audit；若不忠实或引用无效，该 Case 记为 Summarizer failure，不启动 Researcher A/B；
4. `rep_02/03` 只用于判断与 `rep_01` 是否保持相同核心 finding；出现实质结论分歧时，Case 记为 Experience product unstable，不以其中任一版本支持产品有效性；
5. 通过上述检查后，每个 Researcher arm 固定使用同一份 `rep_01` Experience，并独立运行三次。

不同产品 arm 使用各自冻结的单一 Experience，例如 Candidate Case 分别冻结一个 event Experience 和一个 lineage Experience。不存在 Summarizer × Researcher 笛卡尔积。

### 4. Capability 只投影 Artifact 原文

Capability Packet 的默认矩阵不包含实验人员撰写的 `semantic_boundary`。每行只由来源 Artifact 直接投影：

```text
| Observation ref | Decisive observation | Expected label | Thinking mode | Repetition | Raw output |
```

- `decisive_observation` 原样来自 `probe.json.phase_probes[].case_references[]`；
- expected label 原样来自同一 case reference；
- thinking mode、repetition 和 raw output 原样来自 Probe observation；
- Decision Scope 由程序用固定模板组合 phase、`decision_inputs`、predicate 和三值 label rule；
- 完整 prefix 与实际 model-visible input 继续作为 Detail，不在默认矩阵中重复。

程序不把预期 Capability 结论提前写进 Packet。若冻结 contract 本身无法组成自足 Decision Scope，Source Adapter 报告输入不足，不由实验人员补写。

### 5. Direction 聚合只作为 shadow 对照

Candidate Case 使用三臂：

1. `control`：replay base，不注入 Experience；
2. `event_experience`：只注入末次 Candidate Review/Gate 形成的 Direction Experience；
3. `lineage_experience`：注入同一 Research Direction 截至目标 event 的 Trial、Evidence Review、Hook Feasibility、Conformance 与 Candidate terminal outcome 综合 Experience。

Lineage builder 只读取目标 event 之前、由 Control Journal 明确引用的 Artifact，不扫描未来结果。该对照只判断聚合是否有额外消费价值，不新增正式 WorkKind、Store merge、Generation terminal hook 或 Controller 调度。

若 lineage 相对 event 没有达到预注册增益条件，则不为同 session Researcher 增加自动聚合。若未来只在 fresh session/cross-run 场景受益，聚合应作为 Experience Store 的检索投影，而不是每次 continuation 的新 Role Run。

### 6. 单例保持为 Observation

本轮不新增 singleton 频率指标。若 Source Adapter 遇到未满足 Capability 门槛的单例，保持其 Observation 状态，不进入 Experience、Researcher view 或验收统计。实验报告可以在输入盘点中列出实际遇到的 singleton 及 Evidence ref，但不得从 Case A/B 推断总体发生率或修改 eligibility。

## 计划实现

### 1. 先修复 TASK-007 定向回归

在调用真实 API 前处理两项 v16 相关测试异常：

- 更新 `tests/evolution/test_hook_feasibility.py` 的 Distiller transition fixture，使其提供当前协议要求的 `failure_direction_id`、`research_scheme_id` 和 revision 上下文；
- 更新 Hook model boundary failure 的路由断言，验证 `SUMMARIZE_CAPABILITY` side work 与 resumable `RESEARCH_HYPOTHESIS` 的顺序，而不是继续断言直接返回 Researcher。

先运行：

```text
python -m unittest tests.evolution.test_hook_feasibility
python -m unittest discover -s tests/evolution -t .
```

随后运行完整 discover 记录真实状态。已排除 Visualizer 的旧导入错误单独报告，不在本任务修改。

### 2. Shadow Experience Product

新增实验专用资产：

```text
experiments/experience_products_v2/
├── capability_system.md
├── direction_system.md
├── researcher_replay_system.md
├── researcher_replay_user.md
├── capability.schema.json
├── direction.schema.json
├── experience_product_audit.schema.json
└── researcher_pair_review.schema.json
```

字段职责：

- Capability Proposal 使用 `capability_area`、`observed_limitation`、`conditions` 和局部 `evidence_refs`；Decision Scope 与 Evidence summary 由程序附加。
- Direction Proposal 使用 `learning`、`reusable_parts`、`blocking_boundaries`、`retry_only_if` 和局部 `evidence_refs`；三层 Direction Context 与 Evidence summary 由程序附加。
- 第一阶段 schema 不含 `research_constraint`；条件实验使用独立 Prompt/schema，不修改已冻结 Experience。
- Experience Product Audit 只判断 source faithfulness、Evidence 引用和三次输出的核心 finding 是否一致，不评价 Researcher 方案。
- Researcher Pair Review 对隐藏 arm 身份的两个 v2 输出进行固定维度比较。

### 3. 联调脚本

新增：

```text
experiments/validate_researcher_experience_consumption.py
experiments/analyze_researcher_experience_consumption.py
```

`validate` 脚本负责：

- 通过 `run_dir + source_work_id` 解析 Control Journal；
- 按目标 event cutoff 保存完整 replay input snapshot、来源 Artifact refs 和字段来源 manifest，不生成新的 input digest；
- 从原 Artifact 字段生成 Capability raw matrix、Direction event view 和 Direction lineage view；
- 对每个 Summarizer input 并行执行三次真实 Teacher API；
- 按预注册规则冻结 `rep_01`，并在产品不忠实或不稳定时 fail fast；
- 对每个 Researcher arm 使用同一冻结 Experience 并行执行三次 current-v2 replay；
- 保存原始 Role/API artifact、Experience、replay input、usage 与结构化输出；
- 不覆盖 source Run，不修改模型中间产物，不把历史输出写成预期答案。

`analyze` 脚本负责：

- 计算 structured submission 成功率、turn/tool/token 和 `scheme_action` 分布；
- 计算 phase、activation、action、scope、success/falsifier 和 evidence obligation 相对 frozen previous hypothesis 的结构差异；
- 生成 arm-blind paired packet，左右顺序使用 manifest 中预先记录的固定 seed 随机化；
- 调用固定 Pair Reviewer 并按预注册规则结算；
- 字符串复述率只作为 bias 线索，不直接决定质量。

### 4. 实验 Case

#### Case A：Hook-model Capability

来源：`runs/evolution/20260815_qwen3-8b_hook_feasibility`。

- Failure Direction：`analyze_failure-f84a7c940bac3611/role.json`；
- frozen previous Hypothesis：`research_hypothesis-0b6880148b1b7567/role.json` 的 `output`；
- feedback：`verify_hook_feasibility-64ddfe9a2a85e492/role.json`；
- direct probe：`verify_hook_feasibility-64ddfe9a2a85e492/probe.json`；
- 历史 v1 continuation：`research_hypothesis-fa8c806083bfc37d/role.json`，仅供实验后描述，不进入 replay input。

首轮 arms：

- `control`：problem + previous hypothesis + feasibility feedback；
- `capability_facts`：同一 replay base + 冻结事实型 Capability Experience。

主要判断：Experience 是否使当前 Researcher 自行处理单实体题、双方已被 Query 覆盖等误判边界，并在 activation、scope 或 evidence obligation 中作出实质变化，而不是继续假定原 evaluator 可部署。

#### Case B：Candidate rejection 的 Direction 粒度

来源：`runs/evolution/20260815_qwen3-8b_fullchain_fix` 的首个 Candidate reject。

- Failure Direction 与 frozen previous Hypothesis 从目标 Candidate `work_scheduled` refs 解析；
- previous Hypothesis：`research_hypothesis-86ee92df7a9ee5ea/role.json` 的 `output`；
- Candidate Reviewer：`review_candidate-71fa2ca57fec5f9b/role.json`；
- Trial、Evidence Review、Distiller、Compiler、Conformance 与 Candidate Evaluation refs 从同一 Work Item 输入确定性解析。

arms：`control`、`event_experience`、`lineage_experience`。

主要判断：Researcher 是否保留已支持的局部 intervention effect，同时改变导致 Candidate 失败的 evaluator、适用范围或 evidence claim；以及 lineage Experience 是否比末次事件 Experience 提供可复现的额外增益。

#### Case C：重复 Evidence Review 修订

只有 Case A/B 结算为 `indeterminate` 且不确定性直接来自“session 历史是否已足够”时，才使用 `runs/evolution/20260807_debug2` 的后期 Evidence Review 回流构造第三个 controlled replay。Case C 不进入首轮必跑集合。

### 5. Experience Product Audit

冻结 `rep_01` 前使用固定合同：

```python
class ExperienceProductAudit:
    source_faithfulness: Literal["pass", "fail", "indeterminate"]
    evidence_refs_valid: bool
    core_finding_consistency: Literal[
        "consistent",
        "materially_different",
        "invalid",
    ]
    assessment: str
```

字段职责：

- `source_faithfulness`：`rep_01` 是否只陈述输入 Artifact 支持的语义与边界。
- `evidence_refs_valid`：程序校验 Proposal refs 是否均能解析到当前 Packet。
- `core_finding_consistency`：`rep_02/03` 是否与 `rep_01` 保持同一核心经验结论；措辞和原子拆分差异不自动视为 material difference。
- `assessment`：简短说明失败或分歧对应的具体字段与 Evidence。

只有 `pass + true + consistent` 才进入 Researcher A/B。任何其他结果都保存为 Summarizer 产品失败或不确定，不改选其他 repetition。

### 6. Arm-blind Pair Reviewer

固定输出：

```python
Preference = Literal["left", "right", "tie", "invalid"]


class ResearcherPairReview:
    pair_id: str
    validity: Literal[
        "both_valid",
        "left_invalid",
        "right_invalid",
        "both_invalid",
    ]
    evidence_responsiveness: Preference
    material_novelty: Preference
    supported_part_preservation: Preference
    false_pruning_risk: Preference
    experience_bias: Preference
    overall: Preference
    assessment: str
```

字段职责：

- `validity`：两侧是否均形成合法、完整的 `HypothesisResearcherResult`。
- `evidence_responsiveness`：哪侧更准确处理 feedback/Experience 中已经建立的证据边界。
- `material_novelty`：哪侧产生更实质的 hypothesis 变化，而非表面改写。
- `supported_part_preservation`：哪侧更好保留已有 Evidence 支持的局部效果。
- `false_pruning_risk`：哪侧更少发生无依据地放弃 Failure Direction 或可复用局部机制；返回值表示表现更好的一侧。
- `experience_bias`：哪侧更少机械照抄 Experience 或把 Evidence 误作指定解法；返回值表示表现更好的一侧。
- `overall`：综合上述维度后更适合作为下一 Researcher 输出的一侧。
- `assessment`：不超过 900 字符，必须引用两侧具体字段，不能根据 arm 名称判断。

每个 repetition 按相同编号配对；Reviewer 不看到 arm 名称。左右映射由脚本使用固定 seed 生成并保存在 Reviewer 不可见的 manifest section。无效结构由程序先标记，Reviewer 不负责修复。

### 7. 预注册结算规则

每个 contrast 有三组 paired judgments。对每个维度：

- 某一侧在至少 2 个有效 pair 中获胜，则该维度结算为该侧；
- 至少 2 个有效 pair 为 `tie`，或左右均未达到 2 胜，则结算为 `tie`；
- 少于 2 个 pair 可评价，则结算为 `invalid`。

`facts` 相对 `control` 的结论：

- `supported`：`evidence_responsiveness=facts`，且 `material_novelty` 或 `supported_part_preservation` 至少一项为 facts；`false_pruning_risk` 与 `experience_bias` 均不为 control；facts 的合法提交数不少于 control 且至少 2/3。
- `not_supported`：`evidence_responsiveness=control`，或 `false_pruning_risk=control`，或 `experience_bias=control`，或 facts 没有任何主要维度增益且合法提交率更低。
- `indeterminate`：关键维度为 `invalid`，或其余结果混合而无法满足上述两类。

`lineage_experience` 相对 `event_experience` 的结论：

- `aggregation_justified`：evidence responsiveness 为 lineage，material novelty 或 supported-part preservation 至少一项为 lineage，且风险维度不劣于 event。
- `aggregation_not_justified`：event 在主要或风险维度占优，或 lineage 没有任何主要维度增益。
- `indeterminate`：关键维度无足够有效判断或结果混合。

本轮不计算统计显著性，不把 `scheme_action` 的某个枚举值预设为更优。

### 8. `research_constraint` 条件实验

只有 facts-only contrast 满足以下全部条件时启用：

1. Experience Product Audit 已通过；
2. Researcher 多数输出能准确复述 Experience 事实；
3. facts-only 结算为 `not_supported` 或 `indeterminate`；
4. 失败表现是没有把事实转化到 hypothesis claim、success/falsifier 或 evidence obligation，而不是 Experience 与原 feedback 完全重复。

启用后在同一冻结 replay base 上增加 `facts_with_constraint`，重新运行三次并与原 facts arm 配对。Constraint 不修改事实字段或 Evidence refs。

### 9. 输出与文档

```text
runs/experiments/<date>_researcher_experience_consumption/
├── source_manifest.json
├── replay_inputs/
├── packets/
├── summarizer/<case>/<product>/rep_*.json
├── frozen_experiences/
├── researcher/<case>/<arm>/rep_*.json
├── pair_reviews/
└── summary.json
```

`source_manifest.json` 保存 exact source paths、target event sequence、字段来源和 replay cutoff；不增加无消费者的 input digest。

实验后形成独立报告，记录 Summarizer audit、每个 paired judgment、确定性结算、token 和设计结论。只把实验支持的字段和触发方式更新到 [experience-products-v2-draft.md](../../docs/design/experience-products-v2-draft.md)；正式 Summarizer、Researcher consumer 和 Controller 迁移另行提交实施计划。

### 10. 测试与执行顺序

1. 修复两项 v16 相关 Hook Feasibility 测试回归。
2. 为 raw Capability Matrix、Direction cutoff、controlled replay input、arm isolation、fixed Experience 和 blind mapping 增加定向单元测试。
3. 验证所有 shadow schema 和 Prompt 可加载。
4. 运行 Case A 的 Summarizer 3 次；audit 通过后运行 control/facts 各 3 次及 blind review。
5. 运行 Case B 的 event/lineage Summarizer；audit 通过后运行三臂各 3 次及两个预注册 contrast。
6. 仅按条件启动 `research_constraint` 或 Case C。
7. 运行受影响测试、`tests/evolution` rooted discover 和全量 discover，分别报告 TASK-007 回归与已排除 Visualizer 遗留错误。

## 盘点结果

- Case A 的 `research_hypothesis-0b6880148b1b7567/role.json` 与后续历史 continuation 都是 `hypothesis_researcher@1`、`intervention_hypothesis@4`；Case B 的 `research_hypothesis-86ee92df7a9ee5ea/role.json` 同样是 v1。
- 当前 `TeacherRoleDefinition` 只注册 `hypothesis_researcher@2`；`NativeChatRoleRunner.continue_researcher` 沿用 Artifact version，随后 `_validate_continuation_artifact` 比较 Teacher Role scope、template root、role input、resource config 和 system instruction。因此历史 v1 Artifact 无法作为当前 v2 continuation checkpoint。
- current-v2 controlled replay 可以忠实复用历史 problem、Hypothesis、feedback 和查询资源，但它不包含原 v1 hidden reasoning、session feedback history 或当时 Prompt 行为；实验结论必须限定为当前 v2 Researcher 对历史 Evidence 的消费表现。
- `probe.json.phase_probes[].case_references[]` 已保存 `decisive_observation` 与 expected label，Probe observations 已保存 thinking mode、repetition 和 raw output；Capability Matrix 无需人工语义总结。
- 同一旧 Research Scheme 的历史 continuation 已包含 session transcript 与 Reviewer feedback，这使“正式每次决策前聚合”存在重复输入风险；Case B 的 event/lineage shadow 对照足以先判断额外价值。
- Candidate reject/promotion fail 的 Controller feedback source 与正式 Researcher continuation template 不一致，正式主链仍需后续单独修复；controlled replay 不依赖该未注册 source。
- 2026-08-26 全量测试实际结果为 369 项中 1 failure、2 errors。TASK-007 相关异常位于 `tests.evolution.test_hook_feasibility`：一个 fixture 缺少 Research Scheme identity，另一个仍断言旧的直接 Researcher 路由。`tests.visualizer.test_trace_store` 的旧 `search_harness.versioning` 导入错误是已知历史问题。
- v17 的 Summarizer 与 Researcher 重复描述会混合两层随机性；v18 预注册 `rep_01` 冻结规则，其他 Summarizer repetition 只用于产品稳定性检查。
- 完整 replay input snapshot、Artifact refs 与字段来源 manifest 已足够支持本实验复查；新增 input digest 没有当前消费者。
- 先前 Minimal Curator 设计要求 Experience 改变 future Researcher decision；当前真实 API 验证只检查 Draft 结构、归因和稳定性，因此 consumer A/B 是下一步必要的开发期验证。
