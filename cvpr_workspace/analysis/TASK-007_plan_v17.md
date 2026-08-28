# TASK-007 Researcher-facing Experience 联调实验计划 v17

> 实施状态：待用户批准。本文只定义下一轮 shadow 实现与真实 API 实验，不修改正式 Evolution 路由、Experience Store 或现有角色协议。

## 当前状态

- 已完成 Capability/Direction Summarizer 的双角色实现、Source Adapter、Detail、三层 Research Direction 身份和 Controller 旁路挂载。
- 真实 API 验证证明现有角色能够稳定形成结构合法、Evidence 可追溯的摘要，但 Capability 主要复述三值标签偏差，Direction 主要复述单次事件，尚未证明可改变 Hypothesis Researcher 的后续决策。
- 已形成 [Researcher-facing Experience Products v2 草案](../../docs/design/experience-products-v2-draft.md)，其中 Capability 默认输入改为 Semantic Evidence Matrix，Direction 产品改为跨局部效果与下游终态的研究认识。
- `research_constraint` 是否应进入正式 Experience 仍未确定；下一轮先测试不含该字段的事实型经验，只有 Researcher 无法自行形成合理决策变化时才启用 shadow 对照。
- 单个未重复异常仍沿用当前 Observation/eligibility 规则，本轮不修改门槛。
- 当前同一 Research Scheme 内的 Evidence Review 与 Hook Feasibility 回流使用 `continue_researcher` 延续原 Role Session，历史 transcript 和最新结构化 feedback 已经存在；尚无证据支持每次回流前都额外运行一次完整 Direction 聚合。
- 当前 Candidate reject/promotion fail 已在 Controller 中指向 Researcher-first continuation，但正式 Hypothesis Researcher template 只声明 `evidence_reviewer` 与 `hook_feasibility_reviewer` 两个 continuation source；Candidate 场景的真实链路尚缺对应 Prompt template，不能把 transition 单测视为可执行验证。
- 现有 Run 提供多类可复用回流 Artifact；本轮不重新执行 Incumbent/Candidate Evaluation，不调用 Student 或 Intervention Worker。

## 任务意图

本任务验证“更新后的 Experience 是否真的能被 Researcher 使用”，而不是继续验证 Summarizer 能否复述 Evidence。实验以现有已发生回流的真实 Artifact 为冻结输入，对同一 Researcher continuation 比较无 Experience、事实型 Experience，以及在必要时带显式 Research Constraint 的 Experience，判断经验是否促使 Researcher作出证据一致、实质不同且不过度收窄的修订或新方向选择。

本任务直接服务 Goal H3：

> “将已结算轨迹中的 typed verification verdict 与终态转为有 provenance、严格 consumer/scope、可失效和可复查的 role-scoped experience，能够减少跨 attempt/generation 的能力越界、同角色错误复发和方向重走，并提高单位总预算的 useful Candidate yield，同时控制 false pruning 与 held-out utility。”

本轮只验证 H3 中“经验是否改变 Researcher 决策”的开发期前提，不声称证明跨 generation yield、false pruning 或 held-out utility。

实验保持 H1/H2 的现有 Evidence 与 Hook Feasibility 语义：

> H1：“在持久化 Candidate 物化前，冻结真实 Student Prefix 上的 matched no-op 与不可部署 soft intervention 证据能够预测 downstream Candidate effect，并在预算匹配下提高 useful Candidate yield、减少无效完整评估。”

> H2A：“对 Student-owned recognition、decision、adherence、fallback 与 parse responsibility 的独立 probe 能够预测未参与 probe 的真实 Prefix 上的 shadow/in-loop realizability。”

> H2B：“基于逐职责 realizability 证据在 reject、simplify、deterministic lowering 与 ownership reassignment 之间进行 adaptive routing，相对固定 ownership 策略能够提高可实现且有用的 Candidate 产出并减少浪费。”

实验不改变 Trial reference、Reviewer verdict、Candidate outcome、Promotion Gate 或既有路由判据。

## 实施思路

### 1. 先测试事实经验，不预设 Researcher 决策

Capability 和 Direction Experience 首轮只提供：

- 被测试的语义判定或 Research Direction；
- 已观察到的模型/机制行为边界；
- 成立条件、Evidence 结构和稳定引用；
- Direction 中已支持的局部效果与已证实阻碍。

不向 Researcher提供 `research_constraint`、Prompt 建议、Hook 设计或 route 命令。Researcher 必须自行决定修订当前 Research Scheme、开始平行方案或请求重新分析 Failure Direction。

若事实型 Experience 已能稳定促使 Researcher 避免重复已失败假设、同时保留有证据支持的局部效果，则不增加 `research_constraint`。只有 Researcher 明确复述了经验事实但仍无法把它转化为合理 hypothesis/evidence obligation 时，才在同一冻结输入上增加 shadow `research_constraint` 变体进行补充 A/B。

### 2. 单例门槛保持现状

实验 Packet 可以保留单个未重复异常作为 Observation 或 Detail，但 Summarizer 不因本轮联调改变 Capability eligibility。实验报告单独统计“有价值但被门槛排除的单例”出现次数和语义类型；只有多个案例中频繁出现且影响 Researcher 选择时，再提出门槛修订。

### 3. Direction 聚合采用分层对照，不先进入 Controller

“Researcher 决策前聚合”在消费时点上合理，但不等于必须新增一个正式 Controller WorkKind 或每次 continuation 都调用 Summarizer。当前 session 已保存同一方案的历史对话与 Reviewer feedback，重复聚合可能只增加 token 和措辞偏置。

Candidate rejection 案例使用三臂对照：

1. `control`：原 Researcher session + 原 Candidate feedback；
2. `event_experience`：在 control 基础上增加只由末次 Candidate Review/Gate 形成的更新后 Direction Experience；
3. `lineage_experience`：在 control 基础上增加同一 Research Direction 截至该时点的 Trial、Evidence Review、Hook Feasibility、Conformance 与 Candidate terminal outcome 综合经验。

若 `lineage_experience` 相对 `event_experience` 没有稳定提高证据响应、方案新颖性或局部效果保留，则正式实现继续采用事件 Observation + Researcher 现有 session，不增加自动 Direction 聚合。若只有新 session/cross-run 消费受益，则未来只在 Experience Store 检索时物化聚合视图，不挂入每个同 session continuation。

Generation terminal 聚合不进入本轮实现；它与本次 Researcher consumer A/B 没有直接调用链。

### 4. 使用真实 session continuation，而不是重新拼接 Researcher Prompt

每个实验 case 固定：

- 上一版 Hypothesis Researcher `role.json`；
- 当时实际 feedback source 与结构化 feedback；
- 当时可用的 Trial、Probe、Candidate digest 和查询资源；
- 同一正式 Researcher system Prompt、tools、output contract 和 role budget。

实验脚本从 source Artifact 创建只读副本，在 continuation 前插入一条独立的 `Historical experience evidence` user message；原 Artifact 不修改。随后仍调用 `NativeChatRoleRunner.continue_researcher`，由正式 continuation template 追加当前 Reviewer feedback。Experience message 明确是 Evidence，不是指令或 authoritative route。

Candidate feedback source 当前缺少正式 continuation template。实验在输出目录内生成 Hypothesis Researcher template 副本，只补充 `candidate_reviewer`/`promotion_gate` continuation 文本并保持 system Prompt、tools 与 output contract 不变。该 shadow template 验证通过前不迁移到正式模板。

## 计划实现

### 1. Shadow Experience Product

新增实验专用目录：

```text
experiments/experience_products_v2/
├── capability_system.md
├── direction_system.md
├── researcher_experience_message.md
├── capability.schema.json
└── direction.schema.json
```

字段职责：

- Capability Proposal 使用 `capability_area`、`observed_limitation`、`conditions` 和局部 `evidence_refs`；`decision_scope` 与 Evidence summary 由程序附加。
- Direction Proposal 使用 `learning`、`reusable_parts`、`blocking_boundaries`、`retry_only_if` 和局部 `evidence_refs`；三层 Direction Context 与 Evidence summary 由程序附加。
- 第一阶段 schema 不含 `research_constraint`；可选 constraint 变体使用独立 schema/prompt，不修改第一阶段产物。

实现 shadow Packet builder：

- Capability 默认视图提供冻结 Decision Scope、predicate 和 Semantic Evidence Matrix；matrix 每行包含经审阅的 semantic boundary、expected label 与各 thinking/repetition 的 observed label。
- Direction event view 只包含当前 terminal/revision event 的 typed outcome 与必要对照。
- Direction lineage view 按 Research Direction identity 读取截至目标 event 的已结算 Artifact，区分 phase-local effect、Hook feasibility、implementation fidelity、Candidate utility 和 cost，不读取目标 event 之后的信息。

### 2. 联调脚本

新增：

```text
experiments/validate_researcher_experience_consumption.py
experiments/analyze_researcher_experience_consumption.py
```

`validate` 脚本负责：

- 通过 `run_dir + source_work_id` 解析 Control Journal，不硬编码散落 Artifact 路径；
- 冻结目标 event 之前可见的 Artifact 范围，生成 manifest 与 input digest；
- 对每个 Summarizer 输入并行执行三次真实 Teacher API；
- 为每个有效 Experience 建立 paired Researcher continuation；
- 每个 arm 对同一冻结输入并行执行三次；
- 保存原始 role artifact、Experience view、注入后的 transcript 副本、usage 和结构化输出；
- 禁止覆盖 source Run 或人工修改模型中间产物。

`analyze` 脚本只计算确定性指标并生成盲审输入：

- structured submission 成功率、turn/tool/token；
- `scheme_action` 分布；
- phase、activation、action、success/falsifier 和 evidence obligation 相对旧 Hypothesis 的结构差异；
- 与 Experience 的字符串复述率只作为偏置线索，不作为质量结论；
- 输出去除 arm 标签的 paired comparison，供独立 Teacher Reviewer 与人工审阅。

### 3. 实验 Case

#### Case A：Hook-model Capability 回流

来源：`runs/evolution/20260815_qwen3-8b_hook_feasibility`。

- previous Researcher：`research_hypothesis-0b6880148b1b7567/role.json`；
- feedback：`verify_hook_feasibility-64ddfe9a2a85e492/role.json`；
- direct probe：`verify_hook_feasibility-64ddfe9a2a85e492/probe.json`；
- 历史 continuation 结果：`research_hypothesis-fa8c806083bfc37d/role.json`，只用于事后对照，不作为新调用的目标答案。

首轮 arms：

- `control`：原 feasibility feedback；
- `capability_facts`：原 feedback + 不含 `research_constraint` 的 Capability Experience。

主要观察：Researcher 是否自行把单实体题、双方已被 Query 覆盖等误判边界转化为新的 activation scope、evidence obligation 或平行 Research Scheme，而不是继续假定原 evaluator 边界可部署。

#### Case B：Candidate rejection 的 Direction 粒度

首选来源：`runs/evolution/20260815_qwen3-8b_fullchain_fix` 的首个 Candidate reject。

- previous Researcher：`research_hypothesis-86ee92df7a9ee5ea/role.json`；
- Candidate Reviewer：`review_candidate-71fa2ca57fec5f9b/role.json`；
- 其 Trial、Evidence Review、Distiller、Compiler、Conformance 与 Candidate Evaluation refs 从对应 `work_scheduled` event 确定性解析。

arms：`control`、`event_experience`、`lineage_experience`。

主要观察：Researcher 是否保留已有证据支持的局部 intervention effect，同时改变导致 Candidate 失败的 evaluator、适用范围或 evidence claim；以及 lineage 聚合是否比末次事件经验提供稳定增益。

#### Case C：重复 Evidence Review 修订（条件扩展）

若 Case A/B 的结果对 Direction 聚合仍不明确，再使用 `runs/evolution/20260807_debug2` 中同一 Research Attempt 的多次 Evidence Review → Researcher continuation。选择一个后期 revision，使 control 已经拥有多轮原始 feedback，用于检验聚合是否只是重复 session 内容。

Case C 不作为首轮必跑项目。

### 4. `research_constraint` 条件实验

满足以下观察之一才启用：

- Researcher 能准确复述 Capability/Direction 事实，但三次中多数仍提交与已失败边界同质的方案；
- Researcher 没有把明确模型限制反映到 success/falsifier 或 evidence obligation；
- facts arm 与 control 在语义决策上无差异，但不是因为 Experience 与原 feedback 完全重复。

启用后只在触发该条件的 case 上增加 `facts_with_constraint` arm。Constraint 只能表述“不能未经验证地依赖什么”或“哪项 claim 仍需直接证据”，不能提出具体干预、Prompt、Hook 或 route。

### 5. 评价协议

每个 paired output 由独立 Reviewer 按以下维度盲审：

1. `evidence_responsiveness`：是否真正处理 Experience 指出的证据边界；
2. `material_novelty`：是否产生实质不同的 activation、intervention、scope 或 evidence obligation，而非措辞改写；
3. `supported_part_preservation`：是否保留仍由 Trial/Candidate Evidence 支持的局部效果；
4. `false_pruning_risk`：是否因单次实现失败过早放弃整个 Failure Direction 或可行局部机制；
5. `experience_bias`：是否机械照抄 Experience、把限制误读为指定解法或压缩方案多样性；
6. `submission_stability`：三次调用的 schema 成功率、scheme action 与语义方向是否稳定。

验收判断：

- Capability facts 至少在 Case A 中提高 evidence responsiveness，且不增加 false pruning 或显著降低提交稳定性；
- Direction lineage 只有在相对 event experience 产生稳定、可解释的增益时才进入后续正式设计；
- `research_constraint` 只有在 facts-only 不能被 Researcher 自行转化、且 constraint arm 改善该问题而不造成明显偏置时才保留；
- 单例 Observation 门槛不由本轮直接改变，只报告频率和影响。

### 6. 输出与文档

实验产物：

```text
runs/experiments/<date>_researcher_experience_consumption/
├── manifest.json
├── packets/
├── experiences/
├── researcher/<case>/<arm>/rep_*.json
├── comparisons/
└── summary.json
```

实验后形成独立报告，记录每个 Case 的原始事实、paired 差异、token、稳定性和设计结论。根据结果只更新 [experience-products-v2-draft.md](../../docs/design/experience-products-v2-draft.md) 中得到支持的字段与触发方式；正式 Summarizer、Researcher template 和 Controller 的迁移另行提交实施计划。

### 7. 测试

- 新增实验 builder 的定向单元测试：event cutoff、semantic matrix、lineage projection、stable refs、source Artifact 不可变。
- 验证 shadow template 与 schema 可加载、三种 arm 只在 Experience message 上存在预期差异。
- 真实 API 默认每个输入三次；分歧明显时单独扩展到五次。
- 不运行 Student、Intervention Worker、Incumbent/Candidate Evaluation 或完整 Evolution。

## 盘点结果

- `HypothesisResearcherInput` 当前只包含 `problem_direction`；continuation 通过原 `role.json`、`feedback_source` 与结构化 feedback 延续同一 session，没有正式 Experience 输入字段。
- `NativeChatRoleRunner.continue_researcher` 会恢复原 transcript、resource state、output history 和 feedback history，再追加对应 continuation message；同一 Research Scheme 内的 Review 回流已经具有历史上下文。
- `20260815_qwen3-8b_hook_feasibility` 至少包含一次 Hook Feasibility → Researcher 回流和多次 Evidence Review → Researcher 回流，且相关 Trial、Probe、Review Artifact 完整，可直接构造 Capability consumer A/B。
- `20260815_qwen3-8b_fullchain_fix` 包含两个 Candidate reject；对应 Candidate Review 调度事件保存 previous hypothesis、Trial、Distiller、Compiler、Conformance 和 Candidate Evaluation refs，可构造 event/lineage Direction 对照。
- `20260807_debug2` 在同一 Research Attempt 中包含四次 Evidence Review → Researcher continuation，适合检验 Direction 聚合是否重复已有 session 信息。
- Controller 当前为 Candidate reject/promotion fail 生成 `candidate_reviewer` 或 `promotion_gate` feedback source，但正式 Researcher manifest 未注册这两个 continuation source；Candidate consumer 实验必须在 shadow template 中补齐，正式链路需在后续迁移时修复。
- 当前 Experience side work 在每个 typed trigger 后立即运行并形成单事件 Draft；没有 Settlement、跨事件 merge 或 Researcher consumer projection。直接在 Controller 中增加“每次决策前聚合”会同时引入新调度、合并和消费语义，超过本轮判断必要性的最小实验范围。
- 先前 Minimal Curator 设计要求经验改变 future Researcher decision；当前真实 API 验证只检查 Draft 结构、归因和稳定性，因此下一步必须采用 consumer A/B，而不是继续扩大 Summarizer 自身重复次数。
