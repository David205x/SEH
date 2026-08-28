## Prompt Researcher

### 当前实现状态

Shadow Prompt Researcher 已作为独立 Template 和 Role Contract 实现，但尚未接入正式 Evolution Controller。当前实现边界为单 phase、无 Mechanism state、`evaluator="hook_model"`；多 phase state 重放尚未实现。Shadow Compiler 已能消费其 Prompt Product，并以 standalone 角色完成 Candidate 编译与验证。

程序从 Shadow Distiller 的完整 Role Artifact、Mechanism Artifact、Trial Reviews、Trial files 和原始 rollout 确定性组装输入。每个 Prompt Researcher run 只研究一个冻结 Phase Task。Task Input 通过与未来 Hook 相同的 Source Catalog projector 生成，不向 Student 暴露 Trial ID、expected label 或 Teacher Review。

模型只提交：

```python
class ShadowPromptResearchSubmission:
    outcome: Literal["ready", "not_feasible"]
    prompt: str | None
    thinking_mode: Literal["enabled", "disabled"] | None
    selected_probe_ref: str | None
    obligation: str | None
```

程序将受支持的选择确定性物化为：

```python
class HookPromptProduct:
    phase: HookPhaseName
    task_digest: str
    input_projection_digest: str
    prompt: str
    thinking_mode: Literal["enabled", "disabled"]
    response_adapter: Literal["tri_label", "raw_text", "structured_edit"]
```

`ready` 必须引用一次实际 Probe；候选 Prompt 的独立 fidelity Review 必须逐边界确认语义等价，并且所选 thinking mode 的全部逐样本语义 Review 必须仅依据实际投影判为 supported。Reviewer 不得使用 Trial 的隐藏事实补全投影，也不得接受通过重定义缺失值或标签边界获得的表面一致。`not_feasible` 同样必须已有 Probe evidence。程序不使用固定 label match 形成语义判定。

当前 Prompt Researcher 对 Decision Task 产生 `tri_label`，对 Generation Task 产生 `raw_text`。`structured_edit` 是 Shadow Compiler Runtime 已实现的前向兼容 adapter；在上游协议能够定义编辑目标与作用域前，Prompt Researcher 不生成该产品。

- 仅当 Mechanism Distiller 产生的 `MechanismSpec` 至少包含一个 `decision_evaluator="hook_model"` 的 phase 时触发。
- Prompt 包含角色职责、任务说明、可调用工具、输出格式，以及如何撰写和递进改进 Prompt 的固定指导。
- 角色研究的对象是冻结 Hook-model phase 的 Prompt，不修改 Mechanism Spec 中的语义任务、输入边界、干预动作或状态行为。
- 输入包含当前 Hook-model phase 的语义场景、模型可见输入，以及希望 Student 完成的目标语义能力。
- 目标语义能力描述 Student 应当完成的正确判断或生成任务及其输出质量要求，不限定为选择 `positive`、`negative` 或 `uncertain`。
- 目标语义能力可以是实体数量判断、证据覆盖判断、关系识别、内容概括、内容压缩或语义重写。
- 角色只使用一个工具：
  - `run_hook_prompt_probe()`。
  - 程序从已经执行的 Intervention Trial 中确定性选择多条模型可见输入和对应轨迹片段。
  - 程序使用当前候选 Prompt，在 thinking enabled 和 thinking disabled 两种模式下重复调用 Student。
  - Student 调用只产生当前语义任务的输出，不恢复后续 Student 轨迹。
  - Student 输出不包含 reasoning 内容。
  - thinking token 和整体调用开销保留在 Usage 摘要中。
  - 每条 Student 输出由独立 Teacher 按类似 Trial Reviewer 的方式进行语义审阅。
  - Teacher 审阅输入包含目标语义能力、实际模型可见输入、Student 输出，以及存在且语义可比时的 Intervention Teacher 输出。
  - Teacher 根据任务要求判断 Student 输出是否正确或达到所需质量，不执行固定值匹配。
  - Teacher 输出不包含 reasoning 内容，只保留结构化判断和简短事实依据。
  - 工具返回各轨迹片段的 Student 输出、Teacher 语义判断、可用的 Intervention Teacher 参考输出，以及按 thinking mode 汇总的开销信息。
  - 工具完整保存每次 Prompt、Student 原始输出、Teacher 审阅和 Usage Artifact。
- Prompt Researcher 根据工具返回的失败类型和质量判断递进修改候选 Prompt。
- Prompt Researcher 可以多次调用同一个工具测试新的 Prompt。
- 当前 standalone Shadow 首版尚未截断旧 Probe 工具结果；所有 Probe 均完整保存在运行 Artifact，活动 Role Session 受独立 `max_turns` 预算限制。是否增加模型可见结果窗口由多 Probe 实验中的上下文增长决定。
- 角色最终提交本次 Hook-model phase 的最终版 Prompt。
- Prompt Researcher 完成接入后，Mechanism Distiller 不再调用 Student Model Experiment 探索 Hook model 能力。
- Prompt Researcher 完成接入后，Mechanism Compiler 不再调用 Student Model Experiment 探索或调整 Hook model Prompt。
- Shadow Compiler 不读取 Prompt 正文。程序把准确 Prompt、thinking mode、Task Input projector、response adapter 与 Student profile 物化为不可修改的托管模块；Compiler 只引用产品，并实现 guard、activation limit、目标、作用域、状态、action 与 fallback。
- Hook-model Feasibility 保留为 Distiller 与 Compiler 之间的整体阶段，Prompt Researcher 是该阶段内部负责 Prompt 探索的 Teacher Role。
