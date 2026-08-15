# qwen3-8b 检索推理 Harness 实验报告

> 2026-08-14 补充：问题路由 + 自适应分解在 train100 与 frozen heldout100 上均提升
> Teacher semantic、EM 和 Token F1。准确率优先的最新推荐已更新为
> `final_template_routed_adaptive/`；完整证据见 `ROUTED_DECOMPOSITION_EXPERIMENT.md`。
> 下文 `final_template/` 结论保留为原低成本阶段记录。

## 结论

最终冻结模板位于 `final_template/`，digest 为：

```text
515afd66017c6c88cdc6418044fce71cdaa522e90ba8d80f8f4cfe9386dd5579
```

它仅使用项目配置中的本地 qwen3-8b 作为 Agent Model；Extension 不调用模型，不依赖任何外部 API 模型。Teacher Judge 只用于离线评估，不属于模板运行时。

最终机制由四个组件组成：

1. Prompt：强调多跳 bridge 与最终 answer slot 的区别、关系方向、候选消歧和最小答案契约。
2. Output：沿用稳定的 tagged action parser。
3. Tool：检索 top-k 固定为 5，避免模型随意改变召回宽度。
4. Extension：只做两项确定性守卫：强制 top-k=5；对检索后短纯文本答案补 `<final_answer>` 标签。它不修改答案语义。

## 数据边界

- 开发与消融：train `supported.jsonl`。
- 冻结后验证：heldout/dev `supported.jsonl`。
- 未将任何正确答案、样本 ID 或数据集特定实体写入模板。
- 正确答案只用于离线 static/Teacher Judge 评估和错误分析。
- Teacher Judge 使用项目既有严格二元评判协议，只处理非 exact-match 答案。

## 主要结果

### 独立训练抽样 100 条（selection seed 20260815）

| 指标 | Baseline | Final | 差值 |
| --- | ---: | ---: | ---: |
| Teacher semantic accuracy | 59% | 61% | +2 pp |
| Exact match | 31% | 47% | +16 pp |
| Token F1 | 42.32% | 57.10% | +14.78 pp |
| Mean tool calls | 1.17 | 1.06 | -0.11 |
| Mean model calls | 2.18 | 2.07 | -0.11 |
| Mean total tokens | 2786.08 | 2925.90 | +5.0% |

配对语义：14 胜 / 12 负 / 74 平，精确 McNemar 双侧 p=0.845；语义提升不能视为显著。

配对 EM：25 胜 / 9 负 / 66 平，精确 McNemar 双侧 p=0.0090。

### 冻结 heldout 抽样 100 条（selection seed 20260816）

| 指标 | Baseline | Final | 差值 |
| --- | ---: | ---: | ---: |
| Teacher semantic accuracy | 53% | 52% | -1 pp |
| Exact match | 21% | 35% | +14 pp |
| Token F1 | 37.37% | 44.85% | +7.48 pp |
| Mean tool calls | 1.15 | 1.06 | -0.09 |
| Mean model calls | 2.16 | 2.09 | -0.07 |
| Mean total tokens | 2714.03 | 2963.45 | +9.2% |

配对语义：8 胜 / 9 负 / 83 平，精确 McNemar 双侧 p=1.0；可解释为语义表现与 baseline 持平，而不是提升。

配对 EM：20 胜 / 6 负 / 74 平，精确 McNemar 双侧 p=0.0094。

heldout 全部是 hard 样本。其中 comparison（15 条）语义由 80.0% 到 86.7%，EM 由 20.0% 到 86.7%；bridge（85 条）语义由 48.2% 到 45.9%，EM 由 21.2% 到 25.9%。这表明最终 Prompt 对比较题和答案规范化很有效，但 hard bridge 仍是后续研究重点。

## 消融记录

| 版本 | 机制 | 结果与决定 |
| --- | --- | --- |
| baseline | 项目现有 Prompt + top-5 | train24 semantic 58.3%，EM 37.5% |
| v1 | 详细多跳 Prompt | train24 semantic 持平，EM 45.8%，token +61%；过重 |
| v2 | 最终答案自校验与 retry | 失败探针 2/10；会把证据缺失误判为 `no`，放弃 |
| v3 | Search-o1 风格 Reason-in-Documents + top-10 | 失败探针 2/10；文档分析偶有正确但主模型仍会丢失答案 |
| v4 | 结构化证据硬控制与强制补检索 | 失败探针 2/10，成本继续升高；同模型错误被放大，放弃 |
| v5 | top-10 原始证据 + 关系 Prompt | train24 semantic 54.2%，低于 baseline；检索噪声过大 |
| v6/final | compact Prompt + top-5 + deterministic guards | train100 semantic 61%、EM 47%；冻结 |

## 失败景观与设计判断

观察到的主要失败不是单一的召回问题：

- 语义正确但答案过长，导致 EM 失败。
- 艺名/本名、国家/形容词、地点粒度不一致。
- 把 bridge entity 当作最终 property answer。
- 并列补语或关系方向解析错误。
- 多个候选同时出现在 passage 中时选择最显眼者。
- qwen 已经产生短答案但遗漏 action tag，触发一次额外格式修复调用。
- top-10 虽提高候选覆盖，却给 8B 模型带来更多干扰。
- 同一个 8B 模型作为 verifier/reasoner 并不独立，容易认可自身错误；硬控制反而放大错误。

最终模板因此选择“低风险、低自由度”的组合：Prompt 负责语义策略，Extension 只维护可验证的不变量，不让同模型的二次判断覆盖主答案。

## 公开工作映射

- IRCoT：采用“先根据已得事实决定下一跳检索”的思想，但不强制额外模型控制器。
- Search-o1：实测 Reason-in-Documents 在本地 qwen3-8b 上成本高且收益不稳，因此未进入最终模板。
- Self-RAG：保留按需检索与证据反思的 Prompt 思路；没有可用的专门 reflection-token 训练，因此不伪造其完整算法。
- FLARE：采用“只在知识不足时检索”的原则；短答案任务不适合逐句 forward-looking retrieval。

参考：

- Trivedi et al., [*Interleaving Retrieval with Chain-of-Thought Reasoning for Knowledge-Intensive Multi-Step Questions*](https://arxiv.org/abs/2212.10509), 2022.
- Li et al., [*Search-o1: Agentic Search-Enhanced Large Reasoning Models*](https://arxiv.org/abs/2501.05366), 2025.
- Asai et al., [*Self-RAG: Learning to Retrieve, Generate, and Critique through Self-Reflection*](https://arxiv.org/abs/2310.11511), 2023.
- Jiang et al., [*Active Retrieval Augmented Generation*](https://arxiv.org/abs/2305.06983), 2023.

## 产物索引

- `final_template/`：最终可移植 Harness Template。
- `templates/search_agent_v1..v6/`：候选与消融版本。
- `run_benchmark.py`：固定抽样、本地 qwen 限制和 rollout/evaluation 生成。
- `analyze_rollouts.py`：失败报告生成。
- `compare_runs.py`：配对与分层统计。
- `artifacts/benchmarks/`：rollout、static evaluation、Teacher Judge 报告和比较 JSON。

最重要的机器可读比较：

- `artifacts/benchmarks/train100_seed15_comparison.json`
- `artifacts/benchmarks/heldout100_frozen_comparison.json`
