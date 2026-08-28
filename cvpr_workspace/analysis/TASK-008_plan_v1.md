# TASK-008 Shadow Mechanism Distiller 实施计划 v1

## 当前状态

- 已完成：`docs/design/mechanism-distillation-protocol.md` 已定义并通过 sub-agent 字段审查，目标协议使用内嵌 `DistillationResult.mechanism`，区分 Decision/Generation Task，并将证据 provenance 与运行机制分离。
- 已完成：当前 Mechanism Distiller 的上游 `MechanismDistillerInput`、Distillation Evidence Dossier、Trial detail view 与现有真实 Run Artifact 均可复用。
- 正在进行：为新协议建立不替换主链路的 shadow Teacher Role 与真实 API 对照实验。
- 尚未完成：shadow Output Contract、Teacher Template、独立预算、实验入口与定向测试。
- 尚未验证：Teacher 能否在没有旧 Mechanism Draft 工具和 Student Model Experiment 的情况下稳定一次提交新协议；新协议是否保持 Evidence Review 的边界且减少重复和工具回合。
- 当前限制：仓库尚无协议要求的固定模型输入 Source Catalog projector 与 input projection digest；shadow 可以校验 source 身份和 phase 可见性，但不能验证 Probe 与 Candidate Hook 已使用同一实际投影。
- 工作区包含大量已有未提交修改；本任务只对下列计划文件做局部补丁，不覆盖或清理其他变更。

## 任务意图

本任务使用当前真实 Distillation Evidence Artifact 和真实 Teacher API，验证精简后的 Distillation Result/Mechanism Spec 是否能成为稳定、清晰且证据忠实的 Distiller 产品。Shadow Role 不接入 Controller，也不要求现有 Compiler、Feasibility 或 Reviewer 兼容新结构。

本任务与 Goal 中下列主张相邻，但本次历史 Artifact 实验只作开发验证，不构成正式 Claim 证据：

> CLAIM-H2A：对 Student-owned recognition、decision、adherence、fallback 与 parse responsibility 的独立 probe 能够预测未参与 probe 的真实 Prefix 上的 shadow/in-loop realizability。

Shadow Distiller 为后续 Prompt Research/Feasibility 提供冻结的 Hook-model Task 和输入来源；本任务不执行 capability probe，也不判断 Student realizability。

## 实施思路

- 保留当前正式 `mechanism_distiller@1`、旧 `MechanismDistillation`、旧 `MechanismSpec`、Controller 路由和正式 Teacher Template，不对主链路做迁移。
- 新增 `shadow_mechanism_distiller@1`，输入继续使用当前 `MechanismDistillerInput`，保证 Hypothesis、Evidence Review、Trial Reviews、Coverage、Budget 与 Capability Constraints 完全相同。
- Shadow Output 直接提交 `outcome + mechanism/obligation`，成功时内嵌新 Mechanism Spec；不使用旧 MechanismDraftStore、`mechanism_ref` 或 `validated_mechanisms`。
- Shadow Template 复用现有 `render_mechanism_distiller_input()`，只保留异常详情查询工具 `get_distillation_trial_detail`；移除全部旧 draft 工具与 `run_student_model_experiment`。
- Prompt 明确 Distiller 只负责从已结算 Intervention Evidence 提炼 Teacher-free Mechanism。Hook-model Prompt、thinking mode、parser 和 Student capability 由下游 Prompt Research/Feasibility 决定。
- Shadow 合同执行结构化校验：三分支互斥、phase 唯一和顺序、Decision/Generation Task 分支、phase-visible source、动态 `state.<name>`、state 类型与初值、Generation output 绑定、fallback 继承和 activation limit。
- 语义判断仍交给 Teacher 与最终 sub-agent 审查，不为 positive/negative/uncertain 互斥性、guard 确定性或 constraint 文本重复增加关键词门禁。
- 实验保存完整 Role Artifact、原始 transcript、usage、tool calls 和 shadow mechanism；不编辑任何模型输出。

## 计划实现

### 1. Shadow Output Contract

- 修改 `search_harness/evolution/research/roles/contracts.py`：
  - 增加带 `Shadow` 前缀的 Distillation Result、Mechanism、Effect、Phase、Task Input、Decision Task、Generation Task、Fallback 与 State 协议。
  - 为每个字段提供明确职责 docstring，并实现结构性 model validators。
  - 注册 `shadow_mechanism_distiller@1`，复用 `MechanismDistillerInput`，输出 contract 使用独立版本 `shadow_distillation_result@1`。
  - 不修改正式 `mechanism_distiller` 的定义或现有协议类。
- 修改 `search_harness/evolution/research/roles/role_execution.py`：只在确有需要时增加 shadow 输出的资源后置校验；不让 shadow 输出进入正式 MechanismDraftStore。

### 2. Shadow Teacher Template

- 新增 `harness_templates/teacher/shadow_mechanism_distiller/`：
  - `harness.json` 只装配 `get_distillation_trial_detail`、Prompt 和通用 role-contract output；
  - `prompt/system.md` 按新协议完整说明三分支、字段边界、Decision/Generation Task、state/source、fallback、activation、constraints 与提交前检查；
  - `prompt/user.md` 保持 Evidence Dossier 是默认完整证据视图；
  - `prompt/component.py` 复用正式 Distillation Evidence Dossier renderer，并追加从现有 Hook API Catalog 派生的受控 core/stage source 目录；
  - `tools/runtime/component.py` 和 `output/component.py` 复用当前中立组件边界。
- 修改 `config/runtime.yaml`：增加 `shadow_mechanism_distiller` 独立预算，保持与正式 Distiller 相同的 max tokens、max turns 与 thinking mode，避免 A/B 因配置差异失真。

### 3. 实验入口

- 新增 `experiments/validate_shadow_mechanism_distiller.py`：
  - 接收一个或多个已保存正式 Distiller `role.json`；
  - 对主案例并行执行正式/Shadow 各 3 次，对辅助边界案例执行 Shadow 各 3 次；
  - 复用每个 Artifact 的原始 `input` 和 `resource_config`，只把 `hook_probe_env_file` 解析到当前 `.env`；
  - 运行前后记录源 Artifact 与 Trial 文件 SHA-256，证明输入材料未修改；
  - 保存每次 Role Artifact、单独的 shadow mechanism JSON、结构校验结果和汇总；
  - 汇总合法终态、首次提交、turn/request、tool names、usage、输出字符数、outcome、phase/task/evaluator/source/state/action 一致性。
- 默认真实案例：
  - 主 A/B：`runs/evolution/20260815_qwen3-8b_fullchain_fix/artifacts/distill_mechanism-778114760dc22eaf/role.json`；
  - 简洁单 phase：`runs/evolution/20260815_qwen3-8b_hook_feasibility/artifacts/distill_mechanism-dd28a6457d02800d/role.json`；
  - 责任迁移边界：`runs/evolution/20260815_qwen3-8b_fullchain/artifacts/distill_mechanism-8b67fa0ec40359af/role.json`。
- 实验输出写入 `runs/experiments/<run_id>_shadow_mechanism_distiller/`，并在同目录维护 UTF-8 `report.md`。

### 4. 测试与验证

- 新增 `tests/evolution/research/roles/test_shadow_mechanism_distiller.py`：
  - 覆盖三个 outcome 的互斥关系；
  - 覆盖 Decision/Generation Task 字段排斥；
  - 覆盖 phase 顺序、Task Input、公开 source、`state.<name>`、state 初值、output binding、fallback 与 activation limit；
  - 覆盖 shadow Template 装配、工具集合和 Dossier 渲染；
  - 使用合成 Generation Task 只验证协议设施，不把它描述为真实 Artifact 行为证据。
- 运行受影响的角色合同、loader、Prompt 与 shadow 专用测试；不运行全量测试，除非定向结果表明公共 Role Runner 或合同注册发生回归。
- 使用真实 Teacher API 执行计划实验，全部成功、失败与重试 Artifact 均保留。
- API 结束后调用 sub-agent：去除 arm 标签后审查 Evidence fidelity、implementability、boundary completeness、responsibility leakage、redundancy 和三次稳定性；同时审查代码是否影响正式 Distiller。
- 若 sub-agent 发现协议、角色职责或 Reviewer 判据需要改变，停止实验解释，不用 Prompt 临时放宽或编辑产物推进。

## 盘点结果

- 当前正式 Distiller 已使用完整 Distillation Evidence Dossier，模型默认无需逐条查询 Trial；该输入视图可直接复用，避免把本实验变成输入压缩 A/B。
- 当前正式模板暴露 7 个工具，其中 5 个构造旧 MechanismDraftStore、1 个运行 Student Model Experiment；直接复用会重新产生已删除字段和职责，因此 Shadow 只保留 Trial detail query。
- 当前所有成功历史 Mechanism 均使用 `hook_model` Decision Task；真实 Artifact 可验证新 Decision 分支和单/多 phase 结构，但不能验证 Generation Task 的真实语义质量。
- 当前 Hook API Catalog 提供 core/stage state key 和 phase 可见性，能够校验 source 身份；它不提供统一 projector 或 projection digest，因此本次结果不能直接证明下游可复现模型输入。
- `20260815_qwen3-8b_fullchain_fix` 主案例保存 8 个 Trial、5 个 positive 与 3 个 negative，适合检查精简协议是否丢失近邻负例、应用范围和安全 fallback。
- `20260815_qwen3-8b_fullchain` 的旧 `not_distillable` 受 Distiller 自身 Student Probe 影响；Shadow 不再承担该职责，因此 outcome 不一致不自动视为回归。
- `contracts.py`、`config/runtime.yaml` 及相关测试已有用户未提交修改；实施必须只追加 shadow 内容并逐段核对 diff。
