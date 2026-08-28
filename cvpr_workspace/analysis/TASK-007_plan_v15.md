# TASK-007 修订实施方案 v15

## 1. 当前状态

- `experience_summarizer@2` 已具备 artifact-native 紧凑输入、按需 evidence view 和 20 次工具调用熔断；这些机制继续复用。
- 当前 `student_capability` 与另外两类经验共用 `lesson/applicability/evidence_refs`，Prompt 又要求固定写成 `Under X, the Student model cannot reliably Y`，输出因此倾向于复述实验边界，而不是形成可独立理解的 Student 行为画像。
- 当前 `ExperienceSummary` 限制每种 `experience_type` 最多一条，无法在同一合格来源中分别记录“显式证据支持判断”和“答案承诺判断”等不同能力偏差。
- 当前代码没有 Student Behavior Profile 聚合器、Experience Store 或 Hypothesis Researcher typed projection；这些属于后续生命周期与定向消费任务。当前 Capability 也没有记录 Prompt 探索强度，无法区分单一冻结提示下的失败与跨实质不同提示仍重复出现的偏差。
- TASK-007 现有实现与 API Run 已执行但尚未验收；本轮只形成 v15 方案，不修改代码、Prompt、配置或测试。

## 2. 任务意图

本版本把 `Student Capability` 从“实验总结/研究建议”修正为无策略倾向的原子行为观察，只回答：Student 在什么语义判断上、什么输入条件下，出现了什么有证据支持的重复偏差。

涉及的 H3 原文为：

> 将已结算轨迹中的 typed verification verdict 与终态转为有 provenance、严格 consumer/scope、可失效和可复查的 role-scoped experience，能够减少跨 attempt/generation 的能力越界、同角色错误复发和方向重走，并提高单位总预算的 useful Candidate yield，同时控制 false pruning 与 held-out utility。

Goal 还规定：

> Student capability boundary 与 experiment-direction map 只供 Hypothesis Researcher 消费；Teacher work experience 只供对应 role/model/base-prompt/contract 消费。

因此 Capability 必须向未来 Hypothesis Researcher 提供可复用的模型行为画像，同时不能越权替 Researcher 选择方案。当前案例真正测试的决策是：Student 根据问题、搜索历史、检索证据与候选答案，判断准备终答前是否仍需补充检索。v15 要将该决策中的局部偏差拆成可独立理解、可按语义键聚合的原子观察，并用一个短枚举说明该偏差是在单一 Prompt、有限 Prompt 变体还是定向 Prompt 探索后观察到的。该限定只约束结论强度，不携带 Prompt 内容或优化建议。

## 3. 实施思路

### 3.1 为 Capability 建立独立原子协议

`Student Capability` 不再继承通用的 `lesson/applicability` 表达，而使用六个业务字段：

| 字段 | 生产方式 | 预期消费者与用途 |
| --- | --- | --- |
| `decision_scope` | Summarizer 从受测决策合同中选择规范语义值 | 后续按同一语义决策分组；让 Researcher 无需知道 Hook、`pre_final` 等实现坐标也能理解观察发生在哪里 |
| `capability_area` | Summarizer 从当前四个允许值中选择 | 后续合并同类观察，并使压缩投影具有稳定标题 |
| `observed_limitation` | Summarizer 基于重复有效证据概括直接行为偏差 | 作为未来 Researcher 上下文的主体内容 |
| `conditions` | Summarizer 记录影响观察成立范围的输入形态、`thinking_mode` 与同输入是否稳定 | 限定行为发生条件；不得复制 Trial ID、完整 repetition matrix 或实验过程 |
| `elicitation_scope` | 程序按 `(evidence_ref, decision_scope, capability_area)` 提供派生值，Summarizer 必须原样输出 | 告知未来 Researcher 该观察是当前 Prompt 条件、跨有限提示重复，还是定向提示探索后仍出现；不暴露 Prompt 内容或策略 |
| `evidence_refs` | Summarizer引用已授权的顶层 evidence key，程序校验 | 回溯底层 Artifact，避免把完整实验过程复制进画像正文 |

`experience_type` 只作为 tagged union 的解析与路由判别字段保留，不属于画像正文。Student 身份不重复写入；它已经由 Harness/Run 绑定。Capability 不新增建议、处置、复检、成本、效果或 release 字段。

`elicitation_scope` 使用三个受控值：

- `fixed_prompt`：只验证了一个固定且可比的 Prompt–decision-contract 组合；结论只能理解为当前提示条件下的行为观察；
- `limited_variants`：至少存在两个实质不同的 Prompt/contract 表述，但没有针对已发现混淆点形成完整的定向探索；
- `targeted_variants`：Artifact 明确记录了针对该混淆点的提示对照，例如改变判定分解、label 的可操作定义、正负对照或需核对的输入关系，并且偏差仍重复出现。

普通同义改写、格式修复、重试提交或 thinking mode 切换不单独构成 Prompt 变体。thinking mode 继续进入 `conditions`；它与 Prompt 探索强度是两个不同维度。多种变体只有在保持同一 `decision_scope`、输入语义、label 语义和评价目标时才可比较；改变被测合同本身不增加原能力观察的 Prompt 覆盖。`targeted_variants` 必须有绑定到当前 `capability_area` 的显式探索事实，程序不得根据“调用次数较多”或模型自由文本自行提升等级。

程序不从任意 Prompt 文本判断“实质不同”或“定向”。每个可比较变体必须由可审计的 typed declaration 描述：`variant_id`、`variant_kind`、`comparison_group`、`preserves_decision_scope`、`decision_scope`、`targeted_capability_areas`、Artifact pointer 和键级 `capability_result_refs`。每条 result ref 绑定 `variant_id`、`decision_scope`、`capability_area`、typed limitation verdict 及其 Artifact pointer，用来证明该变体上是否复现同一能力偏差。只有同一 `comparison_group` 中 `preserves_decision_scope=true` 且 scope、输入/label 语义和评价目标一致的不同 `variant_id` 才计入覆盖；`targeted_variants` 还要求当前 `capability_area` 出现在 `targeted_capability_areas`，并且定向该能力项的可比变体都有有效的 limitation-reproduced result ref。缺少变体声明时保守记为 `fixed_prompt`；有可比变体但缺少定向复现证据时最多为 `limited_variants`。

### 3.2 固定当前任务的验证 vocabulary

v15 只支持当前已验证决策范围：

- `decision_scope = additional_retrieval_need_before_final_answer`：判断准备终答前是否仍需补充检索。

`capability_area` 只允许当前 Artifact 已实际支持的四项：

- `question_entity_structure`：识别问题是单实体事实题还是多实体比较题；
- `query_coverage`：判断搜索 query 是否覆盖全部相关实体；
- `explicit_evidence_support`：判断 Passage 是否已明确支持候选答案及所问关系/属性；
- `answer_commitment`：判断候选终答是否已经承诺具体实体或结论。

“偏向仍需补搜”是多条原子观察汇总后的跨能力模式，不作为第五个原子 `capability_area`。没有 Artifact 支持的新决策范围或新能力项不由模型自由命名。

上述一个 `decision_scope` 和四个 `capability_area` 是 TASK-007 当前真实 Artifact 验证 vocabulary，用于检查原子观察能否稳定归类；它们不是最终通用 Student Capability taxonomy。v15 尚未接入 Controller、Experience Store 或正式 Researcher 消费，因此本轮允许以封闭枚举形成可验证的 v3 合同。进入正式经验生命周期前，必须另行决定生产 taxonomy 的扩展方式，不能把“新增一种能力偏差就升级整个角色合同”默认为长期机制。

### 3.3 每条观察只表达一个可证偏差

`observed_limitation` 直接写“输入中的什么语义关系被怎样误解，导致什么判断偏差”，不得使用未解释的流程坐标或实现术语。下列表达不进入 Capability：

- `Hook evaluator`、`pre_final`、三路 Hook 决策、positive/negative contract 等只有当前实现上下文才能理解的标签；
- Student 模型名称或固定身份；
- Researcher、guard、Prompt、缩小范围、release/recheck 等方案动作；
- Candidate 准确率、成本、activation utility 或完整 Run 过程。

`observed_limitation` 目标不超过 240 字符，硬上限 300 字符；它只写“输入中的什么语义关系被怎样误解，导致什么判断偏差”。`conditions` 目标不超过 160 字符，硬上限 220 字符；它只保留解释该观察边界所必需的输入形态、`thinking_mode`、同输入是否翻转及“单次观察/重复出现”等定性支持。具体次数、Trial ID、完整 label matrix 和 Prompt 内容由 `evidence_refs` 回溯，不进入画像正文。两个字段都不承担策略建议。

`elicitation_scope` 不并入 `conditions`。前者限定 Prompt 探索覆盖，后者限定模型行为发生条件；分开保存使后续聚合能够区分“换 Prompt 后行为改变”和“相同 Prompt 下 thinking mode 或输入形态不同”。

同一 Capability 可以覆盖多个 thinking mode，但 `conditions` 必须按模式分别给出紧凑观察，例如“disabled：重复误判；enabled：同输入翻转”，不得只写“enabled/disabled 已测试”而遗漏模式差异。单次总结不因 thinking mode 不同拆成多个相同语义键的 Capability。

### 3.4 允许同一来源产生多个不同能力观察

同一合格 evidence ref 可以支持多个 `student_capability` 项，但每项必须拥有不同的 `(decision_scope, capability_area)`，且各自有独立的 `observed_limitation` 和键级 `elicitation_scope`。这使 Conformance 来源中的“显式证据支持判断”和“答案承诺判断”不再被合并，也避免只针对其中一项完成的 Prompt 探索被错误赋给同一 ref 下的其他能力项。

`ExperienceSummary.items` 继续最多三条，以控制单次总结规模；允许多条 Capability，但 `experiment_direction` 与 `teacher_work` 仍各最多一条。输出排序为 Capability 在前、Direction 其次、Teacher Work 最后，仍受总数三条与优先级截断约束。若证据同时支持更多内容，按 `Student Capability >= Experiment Direction > Teacher Work` 保留前三条，不扩容协议。

### 3.5 Capability 与 Direction 保持不同消费语义

Capability 只记录模型语义判断偏差。效果、选择性、成本、机制是否应停止或缩小等内容继续由 `Experiment Direction` 承担，Direction 的现有 `lesson/applicability` 合同暂不改动。一个来源同时输出两类内容时，两者必须使用不同的结论主体和决定性证据。

### 3.6 原子观察与聚合画像分阶段实现

v15 只负责生成可聚合的原子观察，不实现 Student Behavior Profile、重复合并、冲突修订、证据增减、Store 写入或正式 Researcher 投影。后续任务以 `(decision_scope, capability_area)` 为合并键：同类新证据增强或削弱已有结论，`thinking_mode` 差异合并到条件，Prompt 变体带来的差异更新 `elicitation_scope`，冲突改写为“对提示表述敏感”或“不稳定”，而不是保存多个近义画像。

未来 Researcher 投影只显示短限定，不展开枚举解释或 Prompt 历史。例如：

```text
[Query 覆盖判断｜thinking enabled｜limited_variants（跨有限提示重复）]
Query 已同时命名两个比较实体时，仍可能被判断为只命名第一实体。
```

该投影不包含下一步方案、Prompt 调整建议、guard 或复检要求。

本版本验证时可以在分析报告中按语义键展示归并结果，用于检查 12 次重复输出是否收敛到当前四类能力项；该分析不成为生产聚合器或可消费 Store。

## 4. 计划实现

### 4.1 输出合同

- 修改 `search_harness/evolution/research/roles/contracts.py`：将 `StudentCapabilityDraft` 改为独立模型，字段为 `experience_type`、`decision_scope`、`capability_area`、`observed_limitation`、`conditions`、`elicitation_scope`、`evidence_refs`。
- 在同一文件中为 `decision_scope`、`capability_area` 和 `elicitation_scope` 定义当前 v3 合同的封闭字符串枚举；不接受模型自由生成分类名。为 `observed_limitation` 设置 300 字符硬上限，为 `conditions` 设置 220 字符硬上限。
- 扩展 `ExperienceEvidenceObservation`，由程序侧携带键级 `elicitation_scopes`，每项包含 `decision_scope`、`capability_area` 和 `scope`。同一 evidence ref 可以为不同能力键提供不同覆盖等级；未声明的键不得继承同 ref 其他能力项的等级。
- 增加最小 typed variant declaration，字段为 `variant_id`、`variant_kind`、`comparison_group`、`preserves_decision_scope`、`decision_scope`、`targeted_capability_areas`、Artifact pointer 和键级 `capability_result_refs`。result ref 记录当前变体在一个能力键上的 typed limitation verdict 与证据位置。构造请求时只接受这些显式字段推导覆盖：单一可比组合为 `fixed_prompt`；同组多个实质变体为 `limited_variants`；只有同组多个可比变体都定向当前能力项，且每个定向变体都有有效 limitation-reproduced result ref 时，才为 `targeted_variants`。缺失、跨 scope、改变输入/label 语义或评价目标的变体均不提升等级；只有定向声明而没有复现证据时至多为 `limited_variants`。
- 资源后处理校验每条 Capability 的 `elicitation_scope` 等于其引用 ref 在当前 `(decision_scope, capability_area)` 上覆盖等级的保守下界。多个 ref 等级不同时取 `fixed_prompt < limited_variants < targeted_variants` 的最低值；模型不能用较强 ref 覆盖较弱 ref 的范围限制。
- 修改 `ExperienceSummary` 校验：允许多个 Capability；按 `(decision_scope, capability_area)` 禁止同一响应内重复；Direction 和 Teacher Work 仍各最多一条；保持 `items` 最多三条及类型优先顺序。
- 将 `experience_summarizer` role version 从 2 升级为 3，输出合同同步升为 v3；不保留 v2 输出兼容解析。

### 4.2 Prompt 与模板

- 修改 `harness_templates/teacher/experience_summarizer/prompt/system.md`：删除固定句式、Student/Hook 身份措辞和 Capability 中的策略性内容要求，改为六个业务字段定义、四个能力区域的语义边界及一项观察只描述一个偏差。
- 在 Prompt 中明确将实现术语翻译为自足语义：例如用“判断准备终答前是否仍需补充检索”替代 `pre_final Hook decision`，用“query 已同时命名两个比较实体”替代 positive/negative contract 标签。
- 在 Prompt 中说明 `elicitation_scope` 是程序维护的结论强度限定，模型只能按输入保持；不得把 `fixed_prompt` 扩写成能力本质判断，也不得从 thinking mode、重试次数或措辞相似的改写推断更高等级。
- 保留现有归因前置条件、角色责任图、evidence tool 使用方式和 20 次硬熔断；不增加工具、不放宽 Artifact 可见范围。
- 修改 `harness_templates/teacher/experience_summarizer/output/component.py` 与 `harness.json` 所引用合同信息，使模板只接受 v3 输出。

### 4.3 运行入口与配置

- 修改 `cvpr_workspace/configs/task_007_attribution_cases.json`：为真实 Artifact case 声明预期 `decision_scope`、`capability_area` 和可审计的 typed variant declaration，不手写 `observed_limitation` 答案。声明必须逐个引用 Artifact 中的 Prompt/contract 位置、键级 limitation verdict 位置并显式确认可比 scope；不得只给 JSON Pointer 后要求程序分析任意 Prompt 文本，也不得在缺少各定向变体复现证据时宣称 `targeted_variants`。
- 修改 `cvpr_workspace/entrypoints/run_task_007_attribution_validation.py`：使用 role/output contract v3；继续从 Artifact 投影原文和确定性程序字段构造输入，不改变五字段 Summary Input。
- 修改 `cvpr_workspace/analysis/analyze_task_007_attribution_validation.py`：按语义键核对四类能力归因、检查同一来源的多能力拆分、检查 Capability 禁止内容和 `elicitation_scope` 保真，并生成分析侧的去重视图。

### 4.4 测试与开发检查

- 更新 `tests/evolution/research/test_experience_summary.py`：覆盖六个业务字段 Capability、封闭语义键、三个 `elicitation_scope` 值、thinking mode 不提升 Prompt 覆盖、同 ref 不同能力键的独立覆盖、跨 scope/label 语义变体不提升覆盖、定向变体缺少复现 verdict 时不得升级、混合 ref 取保守下界、同源多 Capability、同键重复拒绝、三条上限、类型顺序、字符上限、evidence ref/覆盖等级校验，以及 v2 字段拒绝。
- 更新 `cvpr_workspace/checks/check_stage_002_experience_summary.py`：验证模板、role version、输出合同与真实入口一致，并验证最终 Model Input 仍不包含完整 Artifact、transcript、reasoning 或未授权工具结果。
- 保留 Direction/Teacher Work 的既有合同回归检查，确认此次拆分未改变其字段和消费边界。

### 4.5 真实 API 验证

- 使用已有 artifact-native case 重新调用真实 Teacher API，重点覆盖问题实体结构、Query 覆盖、显式证据支持和 Answer commitment 四类语义判断。
- 固定使用四个代表性 anchor case，每个独立调用三次，共 12 个 Run；四个能力区域各至少由一个 anchor 覆盖，其中包含两能力同源的 Conformance anchor。12/12 必须完成合法终态并保持预期 `decision_scope`、`capability_area` 和 `elicitation_scope`；每个 anchor 的三次 `observed_limitation` 必须由人工语义复核确认描述同一输入关系与同一偏差，文本可以不同。
- 对同时包含两类有效边界的 Conformance case，要求输出两条独立 Capability，不能合并成模糊的“补搜判断失败”。
- 检查 Capability 原文不含策略建议、Candidate 效果/成本、未解释的内部术语或完整实验复述；`thinking_mode` 差异只进入 `conditions`，Prompt 覆盖强度只进入 `elicitation_scope`。
- 真实 Artifact 当前只覆盖 `fixed_prompt` 和 `limited_variants` 时，只对这两类进行真实 API 语义验证；`targeted_variants` 先由合同与确定性测试验证，不得为了填满枚举手工伪造定向探索事实。未来出现合格 Artifact 后再补真实 API 覆盖。
- 将重复 Run 的 Capability 按语义键在分析报告中临时归并，检查现有案例是否收敛为四类局部画像，而不是按 Run 生成近义经验。
- 增加一次盲读可用性检查：只向独立审阅角色提供压缩后的 Capability 观察，不提供原 Artifact，要求其准确复述“正在判断什么、什么输入关系被误判、观察在哪些条件下成立，以及结论是当前 Prompt 条件还是跨有限提示重复”。该检查只验自足性，不声称证明 Researcher 方案或 H3 效果。

### 4.6 产物与任务状态

- 保存 v3 原始 API 输出、逐条忠实中文翻译、带 `elicitation_scope` 的语义键归并视图与盲读检查结果。归并视图只是当前验证 Run 的报告附件，不写入任何可消费经验接口，也不作为 Hypothesis Researcher 输入。
- 更新 `cvpr_workspace/入口清单.yaml` 及追加式 Run/Task 账本。
- TASK-007 在确定性测试、真实 API 语义检查和用户审阅均通过前保持未验收；不以 schema 测试通过代替输出质量验收。

## 5. 盘点结果

### 5.1 当前通用合同导致能力画像失焦

`StudentCapabilityDraft` 当前继承 `_ExperienceDraftBase`，主体只有 `lesson` 和 `applicability`。Prompt 要求 `lesson` 同时容纳条件、主体与能力判断，`applicability` 又承担范围描述，模型容易把重复次数、实验流程和后续使用建议混入同一条文本。拆为 `decision_scope/capability_area/observed_limitation/conditions/elicitation_scope` 后，每个字段都有明确消费者；其中 `elicitation_scope` 只是一项受控的结论强度限定，不承载审查说明或 Prompt 历史。

### 5.2 当前唯一类型约束会合并不同语义问题

`ExperienceSummary` 当前按 `experience_type` 去重，因此一次响应只能有一条 Capability。现有 Conformance Artifact 同时暴露“明示证据仍被判不足”和“拒答/未承诺实体仍被解释为证据缺口”两个不同决策边界；继续保持类型唯一会迫使模型生成无法直接复用的宽泛总结。

### 5.3 当前四类语义键已有真实 Artifact 支持

已有 Hook feasibility、distillation、conformance 和 candidate-review 轨迹分别包含：单实体被误识为比较问题、both-entity query 被误述为只覆盖一个实体、Passage 明示支持仍被判需补搜、未承诺答案被当作实体证据缺口等行为。它们足以支持当前四项封闭能力区域，无需为 v15 引入开放 taxonomy。

### 5.4 聚合与正式消费尚无现成实现

当前活动代码中没有 Student Behavior Profile 聚合器或 Experience Store，Hypothesis Researcher 也尚未接收 typed Capability；正式定向投影已由计划安排在 STAGE-003。v15 若同时实现聚合、修订生命周期和 Researcher 接入，会把原子提炼质量、存储语义与消费效果混在一个任务中，因此本版本只保证原子观察具备稳定合并键和自足表达。

`experience_summarizer@3` 在本轮只由 TASK-007 验证入口启用；其他入口在生产 vocabulary 扩展机制确定前不得把当前一个决策范围和四个能力区域解释为全域 taxonomy。盲读检查和临时归并只验证未来消费所需的信息是否自足，不构成正式 Researcher 接入或消费效果验证。

### 5.5 保留的现有机制

artifact-native 输入投影、紧凑五字段 Summary Input、授权 evidence view、角色责任上下文和 20 次工具熔断都直接服务于归因质量与上下文控制，本次无需改造。它们只为模型提供判断依据，不应出现在最终 Student 行为画像正文中。

### 5.6 Prompt 探索覆盖不能从失败次数推断

现有 Hook feasibility Artifact 比较了 thinking mode，部分 Distillation Artifact 使用两种 contract wording，但它们并不自动构成针对错误原因的系统 Prompt 探索。若不单独记录 `elicitation_scope`，未来 Researcher 会无法区分“当前提示下失败”“跨有限提示重复”和“定向提示探索后仍失败”。因此 v15 只增加一个短枚举限定结论强度；完整 Prompt、变体内容和探索过程继续留在底层 Artifact。

### 5.7 当前语义键不是最终通用 taxonomy

当前一个决策范围与四个能力区域直接来自本批真实 Artifact，适合作为 TASK-007 的稳定验证闭集。项目后续还可能观察工具选择、检索停止、Query 构造、跨 Passage 证据整合或不确定性表达等不同能力偏差。v15 不提前设计这些 taxonomy，也不宣称当前枚举覆盖整个 Student Harness；正式 Store 与 Researcher 投影接入前需要单独确定 vocabulary 的扩展边界。
