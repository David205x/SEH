# TASK-007 Student Capability v3 真实 API 验证

## 结论

本轮 v3 原型实现了原子 Capability 字段和程序维护的 `elicitation_scope`，但真实 API 结果未达到迁移到 Experience Store 或 Researcher 输入的稳定性要求。12/12 Run 均形成合法终态，所有实际生成的 Capability 都保持 `fixed_prompt`，说明保守覆盖边界有效；然而预设能力键只通过 6/12，四个 anchor 的类型集合均不稳定，总消耗达到 2,295,463 tokens。当前应保留为开发期原型和负向证据，不应把输出解释为稳定模型画像。

## 实验协议

- Role：`experience_summarizer@3`，输出合同 `experience_summary@3`。
- Teacher：`.env` 中当前 `TEACHER_*` OpenAI-compatible API 配置。
- 输入：四个历史 Artifact anchor，各独立运行 3 次，共 12 Run。
- Anchor：Hook Feasibility、Mechanism Distiller、Conformance Reviewer、Candidate Reviewer 各一组。
- Prompt 覆盖：四组 Artifact 均未提供满足 v15 要求的 typed Prompt variant declaration，因此程序预期一律为 `fixed_prompt`。
- 原始产物：`runs/experiments/20260824_task007_capability_v3_api/`。
- 本轮属于开发检查，不支持 H3 Claim，也未写入 Experience Store 或正式 Researcher 输入。

## 总体结果

| 项目 | 结果 |
|---|---:|
| 合法终态 | 12/12 |
| 输出字段与字符硬上限 | 12/12 |
| Capability 禁止内容结构检查 | 12/12 |
| 预期 Capability 语义键 | 6/12 |
| exact type rubric | 4/12 |
| 无失败、无重复读取且未触及 fuse | 11/12 |
| Provider requests | 87 |
| Input tokens | 2,038,767 |
| Output tokens | 256,696 |
| Total tokens | 2,295,463 |

所有实际 Capability 均使用 `fixed_prompt`，没有把 thinking-mode 切换、重复次数或自由文本误当作 Prompt 探索证据。`observed_limitation` 与 `conditions` 均满足硬长度上限，也没有写入模型身份或直接的 Researcher 策略建议。不过多条内容仍包含 `2/2`、`4/4` 等实验计数，说明“正文只保留定性支持”的软指导尚未稳定生效。

## 分 anchor 观察

### Hook Feasibility

3/3 均生成 Capability，但预期的 `question_entity_structure` 只有 2/3；另一次选择 `query_coverage`。这不是纯随机标签错误：该 Artifact 的两个负例分别涉及单实体问题和已经覆盖双实体的 query，证据本身跨越两个能力区域。当前四项封闭 vocabulary 没有表达“组合激活谓词/多条件边界”的原子类别，模型只能在实体结构与 query coverage 之间择一。因此该 anchor 不能在不扩展 taxonomy 或收窄证据的情况下稳定支持一个键。

### Mechanism Distiller

`query_coverage` Capability 为 3/3，且三次都描述“query 已包含双方实体，却被判断为只覆盖第一实体并要求继续检索”，是本轮最稳定、最符合预期的能力观察。Direction 为 2/3，说明同一来源是否还应生成研究方向仍有抑制边界波动，但不影响 Capability 语义键本身。

### Conformance Reviewer

三次分别为：`explicit_evidence_support`、仅 Direction、`explicit_evidence_support + Direction`。预设的第二项 `answer_commitment` 从未生成。查看三条 finding 后发现，显式证据支持错误有两个独立有效案例，而“终答没有承诺任何实体”只有一个案例；后者不满足当前 Capability 的重复或两例门槛。因此“两项 Capability 都应出现”的 rubric 过强，不应通过 Prompt 强制实现。另一次完全未查 evidence view，只基于紧凑输入生成 Direction，表明初始投影不足以稳定暴露 Capability 所需的重复证据。

### Candidate Reviewer

Direction 为 3/3，`question_entity_structure` Capability 仅 1/3。当前输入的 boundary facts 缺少 `input_validity=confirmed`，而 Capability 合同明确要求该硬门槛；因此 2/3 抑制 Capability 是更保守的行为，唯一生成 Capability 的 Run 反而属于证据门槛执行不一致。若底层 Candidate Review 原文足以确认两条真实 prefix 输入有效，应在程序投影中补充可审计的 input-validity fact，而不是要求模型忽略门槛。

## 运行稳定性与成本

请求成本高度长尾：Candidate 三次分别消耗 222,744、147,478、954,060 tokens；Conformance 第三次消耗 515,049 tokens。主要直接原因是模型多次耗尽 4096 completion budget 而未提交工具、Direction 的 500/300 字段反复超长、一次无效 JSON 工具参数，以及完整对象修复重试。Candidate 第三次达到 20 provider requests，并重复读取同一 evidence view。

这些数据不能证明六字段 Capability schema 单独造成成本上升，因为多数校验失败发生在既有 Direction 字段，且 Teacher thinking 会在无工具调用时消耗完整 completion budget。但它证明“在同一个终态中同时判断多经验类型并撰写长 Direction”仍会造成严重上下文累积，当前 Role 的真实运行成本不可接受。

## 对 v15 设计的判定

已得到支持的部分：

- 原子字段比 `lesson/applicability` 更容易读出具体语义偏差。
- 模型身份可以由 Harness 绑定而不写进正文。
- `thinking_mode` 能留在条件中，且不污染 `elicitation_scope`。
- typed declaration 缺失时默认 `fixed_prompt`，以及 Store 侧保守下界校验，均可确定性工作。
- Distiller anchor 表明在证据同质且充分时，能力键和描述可以 3/3 稳定。

未得到支持或被反证的部分：

- 当前四项封闭 taxonomy 不能稳定覆盖组合谓词证据。
- 同一个 evidence ref 可拆多个 Capability 在协议上可行，但现有 Conformance Artifact 不足以支撑预设的两项都达到 Capability 门槛。
- 仅靠现有紧凑初始投影和“必要时查工具”的指导，不能稳定保证模型发现重复能力证据。
- 当前整体角色提交过程成本和重试长尾不可接受。

## 后续边界

在继续接入前，应先把预期 rubric 与能力证据门槛对齐：为每个 anchor 明确哪些能力键有至少两条同质有效证据；对缺少硬 boundary fact 的来源补充可审计投影；为四个 capability area 写出互斥的语义定义，并决定组合谓词是新增类别、拆成多个证据单元，还是不形成 Capability。之后只需复测受影响 anchor，不应再次无差别运行全部历史 case。运行成本问题需要单独处理 Teacher completion 未提交工具和 Direction 长字段修复循环，不能靠放宽 Capability 文本上限掩盖。
