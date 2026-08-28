# TASK-007 Experience Summarizer v2 真实 API 归因质量审计

## 1. 审计结论

本批 28 个真实 `deepseek-v4-flash` Role Run 全部形成合法终态，预先冻结的 exact type rubric、Teacher subject、文本长度和工具协议均为 28/28 通过。人工复核确认本任务优先的 `student_capability` 与 `experiment_direction` 已达到可验收质量；TASK-007 可按 consumer-ready Experience Draft 范围通过。

这些历史 artifact 只用于角色行为开发验证，不构成 Experience Store、跨 Run 复用效果或 H3 正式实验结论。

## 2. 验证口径

- 角色：`experience_summarizer@2`，输出合同 `experience_summary@2`。
- 输入：真实负向 artifact 构造的结构化 outcome、comparison、typed boundary facts，以及程序维护的实际 Transition 和完整紧凑角色职责上下文。
- 重复：8 个重点 anchor 各 3 次，4 个补充案例各 1 次，共 28 次。
- 类型优先级：`student_capability >= experiment_direction > teacher_work`。
- 结构判据：exact type 顺序、Teacher subject、长度、授权证据引用、工具 view、失败/重复读取和 20 次硬熔断。
- 语义判据：主体、因果边界、决定性事实、consumer action、解除或重访条件，以及双输出独立性。

## 3. Student Capability

12 条 Capability Draft 均把主体限定为冻结 Student/Hook model，没有把 Compiler、Candidate、Reviewer、数据缺失或干预无效误写为模型能力。

- Hook Feasibility 三次均识别：thinking disabled 下两个显式负类重复判为 positive，thinking enabled 下相同负类跨重复翻转；同时保留有效 reference、真实 prefix 和 parse-clean probe 边界。
- Distillation 三次均识别：上游 intervention controls 通过不等于部署模型可实现边界；4/4 both-entity negatives 与 single-entity negative 的错误稳定落到 Hook model。
- Conformance semantic evaluator 三次均识别：结构和 deterministic wiring 忠实后，模型仍跨越 explicit-link negative 与 no-committed-value uncertain 两类边界。
- Candidate overlap 三次均识别：两个不同显式负类发生 Hook positive activation，形成狭窄 false-positive capability；没有扩大为通用推理能力不足。

所有 Capability Draft 都给出 `do not rely unchanged`、deterministic guard 或指定 recheck，并用模型、任务、输入、mode 与 decision boundary 限定适用范围。

## 4. Experiment Direction

17 条 Direction Draft 均包含可识别的方向 signature、处置和合法重访条件。

- no-differential 三次均以 matched source control 否定 generic verification context 的因果作用，没有生成 Capability。
- harmful-overtrigger 三次均同时保留 clean falsifier 与 complete-evidence regression，结论为 stop unchanged / narrow selective trigger，没有把通用 patch 的失败归因给 Student。
- corpus-confound 三次均把结论保持为 inconclusive，并要求 corpus 提供第二实体证据或拆分 search fidelity 与 evidence availability。
- strict single-passage grounding 三次均结合 regression balance、supported-answer harm 与约 5.6x cost，拒绝原方向不变复用。
- no-attributed-utility 与 selectivity/cost 案例分别区分 no-op variance、activation-attributed outcome、false positive 与成本。

Candidate overlap 的三组双输出使用了不同事实和动作：Capability 消费显式负类上的重复 Hook false positive，并要求 guard/recheck；Direction 消费无 intended positive、无 activation-attributed utility、accuracy/cost 结果，并要求停止或重设计机制。没有用同一结论填充两类。

## 5. Teacher Work

两个 Teacher-work sanity case 都只输出 `teacher_work`，且 `teacher_role_id=compiler`：

- empty-passage projection 要求把真实 trajectory passages 投影给 classifier，并给出零 mismatch 的完成条件；
- unchanged rejected Candidate 要求实际修改 query coverage 与 exactly-one-defer 两个缺陷，再通过 validation。

后一条 applicability 末句将新 Research Attempt 描述为会耗尽 compile-retry budget；真实 Transition 的权威事实是 unchanged rejected Candidate 直接开始新 Research Attempt、且不消费普通 validation revision。核心主体、修复义务、直接后果和完成条件正确，因此该措辞记为低优先级非阻断偏差，不影响 Capability/Direction 验收，也不作为后续路由事实消费。

## 6. 工具与终态

本批输入的 typed boundary facts 已解决归因硬门槛，因此 28 个 Run 均以零 evidence tool call 完成；这符合默认零调用、按需读取的策略。离线阶段检查已独立验证前 20 次 invocation 可执行、第 21 次拒绝，且非法调用计入。真实 API 批次没有失败调用、重复 `evidence_ref/view`、非法 view 或熔断触达。

45 个 provider requests 共使用 263,983 input tokens、80,324 output tokens、344,307 total tokens；28 个 Role Run 均完成，无 length exhaustion。

## 7. 最终判断

- `student_capability`：通过。
- `experiment_direction`：通过。
- Capability + Direction 独立性：通过。
- `teacher_work`：核心合同通过，保留一处非阻断路由预算措辞偏差。
- TASK-007：通过 consumer-ready Experience Draft 验收；不扩展为 Store、历史经验去重/修正、跨 generation 事实或 H3 正式效果结论。
