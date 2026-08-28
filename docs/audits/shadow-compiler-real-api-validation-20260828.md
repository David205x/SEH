# Shadow Compiler 真实 API 验证（2026-08-28）

## 验证对象

- Shadow Distiller Artifact：`runs/experiments/20260828_0827_shadow_distiller_source_fix_v2/experiments_current/shadow/run_001/role.json`。
- Shadow Prompt Researcher Artifact：`runs/experiments/20260828_0827_shadow_prompt_research_source_fix/run_001/role.json`。
- Parent Template：`harness_checkpoints/0827/template`。
- 本次真实机制是单 phase、无业务 state 的 `pre_final` Hook-model Decision；Prompt Product 固定为 `hook_prompt_e5e8e638bd1e98eb`，thinking enabled，`tri_label` adapter。

## 结果

1. 初版在 1 次真实调用中提交并通过 Candidate Validation，但经历 23 次模型请求、3 次 finalize，共 546,035 token。主要冗余来自重复查询 packet 已提供的 API，以及相对导入和源码审计规则的机械修复。
2. 补充完整 packet 与禁止重复查询后，3/3 次均提交，模型请求降至 10–12 次，总 token 为 159,356–190,441；但三份实现都把预期 Student 后续行为误当成 activation limit，未持久记录成功 activation，因此不视为语义合格。
3. 明确 `activation_limit` 是每 rollout 的成功 `on_success` 次数，并要求 extension-local `StateRef` 后，3/3 次均声明私有整数计数，在 Prompt 调用前检查上限，并在同一 Hook 事务中提交计数递增与 defer。三次 Candidate 均通过静态、装配、完整 Pipeline 和同 rollout lifecycle validation。
4. 补充 `StateRef` key 规则、Component Factory 规则和 Shadow 查询硬上限后的最终回归首次提交：8 次模型请求、128,455 token、0 次 API 查询、1 次 finalize。Candidate 未构造 `HookModelRequest`、未直接调用模型、未复制 Prompt，并保存准确 Product Reference。
5. 对最终真实 Candidate 执行定向生命周期 smoke：恰好一次 search 且托管模型返回 positive 时，首次 `pre_final` 将 accept 改为 defer，并写入 `extension.defer_unsupported_final.activation_count=1`；同一 rollout 第二次直接作答保持 accept，托管模型总调用次数为 1。

## 结论边界

Shadow Distiller → Shadow Prompt Researcher → Shadow Compiler 的现有单 phase、无业务 state 路线已经协议对齐，能够生成可装配且实际消费托管 Prompt Product 的 Candidate。Compiler 不再承担 Prompt、thinking mode、输入投影或响应解析的重新设计，只负责 Mechanism 的生命周期和写入语义。

本次真实 API 证据不覆盖多 phase、Mechanism state、Generation Task 或 structured edit 的角色稳定性。Framework 单元测试已覆盖 `raw_text` 和数字 `block_id` 的 insert/replace/delete 结构解析，但上游 Prompt Researcher 尚不产生 structured-edit Product，不能据此声称完整编辑路线已经通过真实角色联调。

## 产物

- 初版：`runs/experiments/20260828_0827_shadow_compiler_run1/`。
- 查询优化 A/B：`runs/experiments/20260828_0827_shadow_compiler_v2/`。
- activation 修正三次复验：`runs/experiments/20260828_0827_shadow_compiler_activation_fix/`。
- 最终回归：`runs/experiments/20260828_0827_shadow_compiler_final_smoke/`。
