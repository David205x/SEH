# TASK-009 Shadow Compiler 实施计划 v1

## 当前状态

- 已完成：Shadow Mechanism Distiller 已输出精简的 `ShadowMechanismSpec`，Shadow Prompt Researcher 已为其中的 `hook_model` Task 产出经审查的独立 Prompt Product。
- 已完成：用户已确认 Compiler 不负责重写 Prompt、选择模型输入或解释原始模型响应；它负责生命周期、目标、作用域、状态、动作与 fallback。
- 正在进行：新增不替换主链路的 `shadow_compiler@1`，把上述两类 Shadow 产物降低为 Candidate extension。
- 尚未完成：角色模板、程序托管 Prompt Product、运行时调用接口、候选绑定校验、真实 API 编译与候选验证的完整收口。
- 尚未验证：Compiler 是否能在不读取 Prompt 文本的情况下稳定生成可装配实现，以及 Candidate 是否使用与 Prompt Research 阶段相同的输入投影、thinking mode 和响应适配器。

## 任务意图

本任务将已经通过 Prompt Research 的 Hook-model Prompt 作为程序托管产品交给 Candidate Runtime，并让 Compiler 只完成机制规定的工程固化。这样可以避免 Compiler 重复探索 Student 的语义能力或自行改写已经验证的 Prompt，同时保留其对实际修改目标和范围的实现责任。

本任务服务于 Goal 中以下主张的实现链，但当前 Shadow 实验不单独构成最终 Claim 证据：

> CLAIM-H2A：对 Student-owned recognition、decision、adherence、fallback 与 parse responsibility 的独立 probe 能够预测未参与 probe 的真实 Prefix 上的 shadow/in-loop realizability。

## 实施思路

- 增加 `HookPromptProduct` 运行时合同，冻结 Prompt、Task Input source、输入投影、thinking mode、响应适配器和 Student model profile。
- Prompt Research 与 Candidate Runtime 共同使用同一个确定性输入投影与 user-message envelope，避免研究输入和实际 Hook 输入漂移。
- `ShadowCompilerInput` 同时接收一个 `ShadowMechanismSpec` 和覆盖全部 Hook-model phase 的 Prompt Product；程序确定性核对 phase、Task digest、input projection digest、Task kind 与 adapter。
- Compiler capability packet 只公开 phase 到 Prompt Product ref 的绑定和调用接口文档，不公开 Prompt 正文。
- Compiler 注册目标 extension 后调用绑定工具，由程序在其组件目录写入不可读写的 Prompt Product 模块；Candidate 通过 `context.call_prompt_product` 调用。
- Prompt Product 只返回规范化 decision、generated text 或 structured edit operation；Compiler 根据 Mechanism 实现 guard、target、scope、state、action 和 fallback。
- Candidate 提交前确定性拒绝未绑定、改写托管模块、复制 Prompt、直接构造 Hook model 请求或没有真实消费绑定的实现。

## 计划实现

- 新增 `search_harness/framework/harness/prompt_products.py`，实现 Prompt Product、输入投影、模型调用和三类响应适配。
- 修改 Framework public API 与 Hook API Catalog，公开 `HookContext.call_prompt_product` 及只读结果类型。
- 新增 `ShadowCompilerInput` 和 `shadow_compiler@1` 角色注册，并实现 Shadow capability packet 与托管产品 lowering。
- 扩展 `CompilerWorkspaceStore` 和 Compiler tools，支持按 extension 绑定、保护、校验并随 Candidate Artifact 保存 Prompt Product 引用。
- 新增 `harness_templates/teacher/shadow_compiler/`，明确 Compiler 的实现责任和托管产品边界。
- 新增定向单元测试及 `experiments/validate_shadow_compiler.py`，使用现有 Shadow Distiller、Prompt Researcher Artifact 和真实 Teacher API 执行至少三次角色稳定性验证。
- 对成功 Candidate 执行静态、装配、完整 Pipeline smoke 和同 rollout lifecycle smoke；不修改模型输出或上游 Artifact。

## 盘点结果

- Shadow Mechanism 已确定 phase、guard、Task Input source、on-success、fallback、activation limit、state 与 constraints，可以为 Compiler 的生命周期和写入范围提供权威来源。
- Shadow Prompt Product 已确定 Prompt、thinking mode、Task digest、input projection digest 和 response adapter，可以由程序构造完整运行时调用，不需要 Compiler 阅读 Prompt。
- 现有 `HookContext.call_model` 和 `HookModelRequest` 能提供底层模型调用，但直接暴露给 Shadow Compiler 会允许其重写 Prompt 和输入，因此需要更窄的托管调用接口。
- 现有 `CompilerWorkspaceStore` 已有受控 workspace、API packet、静态验证和提交事务，适合局部增加程序托管文件及提交约束，无需建立第二套 Candidate Store。
- 当前上游只产生 Decision Prompt Product；Generation 与 structured edit 的运行时支持属于用户明确要求的提前兼容范围，其输入仍必须来自未来合法的 Shadow 协议产物。
