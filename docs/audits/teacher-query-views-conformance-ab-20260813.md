# Shadow Conformance Reviewer A/B 实验

状态：历史 A/B；Example Batch 与独立 replicate 边界已迁入正式 Conformance Reviewer，
影子模板和运行入口已于 2026-08-14 清理。本文路径仅记录实验时环境。

## 1. 目的与边界

本实验只优化 Conformance Reviewer 的模型可见输入和调用粒度，不修改正式 Controller、正式角色协议、Candidate、Mechanism、保存的 Candidate replay 或聚合门禁，也不执行新的 Student rollout。

影子方案保持 Reviewer 无查询工具、一次性读取完整证据的工作方式，将同一 Example 的 3 个 replicate 合并到一次 Teacher 调用。Mechanism 与 reference observation 在批次中只出现一次；每条 `candidate_trajectory_view` 仍完整保留，输出仍是逐 replicate 的独立 finding。

实验分为两个可区分的变量：

- `batch_full_reference`：只合并 3 个 replicate，reference observation 保持正式输入原样；
- `batch_compact_reference`：在批处理基础上，将 reference observation 投影为 phase、激活次数、action kind、是否修改、后续 Student action 和上下文块变化类型，不再重复案例专用 patch 正文与 reason。

## 2. 实现

- 影子输入、输出协议与 reference projection：`experiments/teacher_query_views/conformance.py`；
- 影子提示词：`experiments/teacher_query_views/templates/conformance_reviewer_batch/prompt/`；
- 保存 replay A/B 入口：`experiments/run_conformance_batch_ab.py`；
- 单元测试：`tests/experiments/test_conformance_batch_ab.py`。

程序要求输出中的 `replicate_id` 与输入严格同序且不重复。每个 finding 复用正式 `ConformanceReview` 的全部语义校验，身份字段仍由程序拥有。批处理只改变调用包装，不降低单条 finding 的诊断要求。

## 3. 主要实验

主要素材来自正式 Compiler Candidate 的 8 个 Example、24 条已保存 replay。正式结果为 22 条 `faithful` 和 2 条 `implementation_mismatch/evaluator`。

两种影子方案各重复执行 3 轮，共分别生成 72 条 finding：

- 两种方案的 verdict、failure layer 和 recommended route 均为 72/72 与正式结果一致；
- 每批都返回完整 3 条 finding，没有跨 replicate 漏报；
- 每批均一次 structured submission 完成，没有出现结构化校验重试；
- `batch_full_reference` 平均约为正式保存结果总 token 的 43%；
- `batch_compact_reference` 平均约为正式保存结果总 token 的 42%–43%。

主素材中，reference projection 只带来很小的额外 token 节约；主要收益来自 Mechanism、提示词和 reference evidence 不再为 3 个 replicate 重复输入，以及 3 次独立推理合并为一次。

## 4. 补充实验

补充素材来自另一份 8 个 Example、24 条 replay 的 Candidate，其中正式结果包含 4 条 implementation mismatch，并覆盖 action 与 evaluator 归因。

`batch_compact_reference` 一轮完成 24 条 finding：

- 23/24 的 verdict、failure layer 和 route 与正式结果一致；
- 平均总 token 为正式保存结果的约 60%；
- 平均请求数由正式每 Example 约 3.5 次降为 1.38 次；部分批次发生 structured submission 修订，但均完成。

唯一分歧中，正式 finding 判为 `faithful`，影子判为 `implementation_mismatch/action`。保存轨迹显示 Hook-model 输出和 Student-visible patch 使用了字面占位描述 “the specific connection the question requires”，而 Mechanism 要求 patch 明确说明具体缺失实体或连接。影子判断有直接 trace 证据，属于发现正式审查漏掉的 action 语义缺陷，不能据此认定批处理质量下降。

## 5. 结论

按 Example 合并 replicate 是当前最有价值的优化。它保持一次性完整上下文与逐 replicate 判断，同时消除最主要的重复输入和重复推理，在两个 Candidate 素材上均完成所有批次，并保留或加强了失败归因。

紧凑 reference observation 没有造成已观察的系统性信息损失，但相对“只批处理”的额外收益很小。若迁入正式路径，建议先采用 `batch_full_reference` 作为低风险改动；将 compact reference 作为独立后续变更继续用跨 Mechanism replay 验证，避免把两项优化绑定发布。

尚未验证的边界包括多 phase Mechanism、`not_observed`、`inconclusive`、`runtime_error` 和 `ambiguous_spec`。因此当前结果支持继续扩大 shadow 覆盖，不足以直接替换正式 Conformance 实现。
