# Qwen3-8B 能力画像与混合 Workflow 补充实验

## 结论

本轮没有发现可稳定超过 `final_template_routed_adaptive/`（v11）的候选，因此不晋升新模板。
v11 继续作为准确率优先的推荐版本。本轮新增的 v12、v13 均保留为可复核负结果，不覆盖既有
模板、代码、文档或 artifact。

最重要的新认识是：本地 Qwen3-8B 的能力高度不对称。它很擅长遵循短 JSON 协议和生成下一条
检索查询，但不擅长在噪声 passage 中稳定判断证据充分性、逐字提取支持句，或作为自己的独立
answer verifier。因此，更复杂的 workflow 只有在把模型自由度限制在“规划查询”时才有召回
信号；一旦让同一模型覆盖已有答案或生成新的事实层，错误会被放大。

## 数据与边界

- 开发数据仍只来自 train `supported.jsonl`；本轮没有重新查看或调参已冻结的 heldout100。
- Student 运行时模型固定为项目 `.env` 中的 `qwen3:8b`。
- Golden answer 和 supporting quote 只在生成结束后用于离线指标，不进入任何 Student prompt。
- Teacher Judge 只做离线语义评分，不属于候选模板的组件或运行时依赖。
- 新增代码、模板、split 和 artifact 全部位于 `experiments/as_you_can/`。

## 公开工作映射

1. `[机制] Adaptive-RAG` 用问题复杂度在无需检索、单步和迭代检索之间路由，且论文使用实际
   下游表现构造复杂度标签；这支持继续保留 v11 的选择性路由，而不是让所有题统一进入重型
   workflow。[Jeong et al., 2024](https://arxiv.org/abs/2403.14403)
2. `[角色] Decomposed Prompting` 将 decomposer 与子任务 handler 分离；`Least-to-Most` 和
   `Self-Ask` 也强调先解决较简单的中间问题，再把结果用于后续问题。这些工作支持 v11 的
   bridge-first 自适应分解，但不意味着自由摘要一定可靠。
   [Khot et al., 2022](https://arxiv.org/abs/2210.02406)、
   [Zhou et al., 2022](https://arxiv.org/abs/2205.10625)、
   [Press et al., 2022](https://arxiv.org/abs/2210.03350)
3. `[机制] ReAct` 与 IRCoT 都让推理和检索交错；本项目的 adaptive controller 已是这一思想的
   低自由度实现：controller 只决定下一查询，最终答案继续使用原始证据。
   [Yao et al., 2022](https://arxiv.org/abs/2210.03629)、
   [Trivedi et al., 2022](https://arxiv.org/abs/2212.10509)
4. `[角色] CRAG` 使用 retrieval evaluator 触发 corrective retrieval；DRAGIN 依据实时信息需求
   决定何时及检索什么。本轮 v12 是这一类机制在当前框架和 8B 模型上的最小化测试。
   [Yan et al., 2024](https://arxiv.org/abs/2401.15884)、
   [Su et al., 2024](https://arxiv.org/abs/2403.10081)
5. `[机制] Self-Consistency` 通过多条推理路径投票，但会显著增加本地推理成本；本轮能力探针
   又显示同一证据下输出只有 55.6% 的案例三次完全一致，且错误证据选择具有系统性，所以没有
   把高成本多数投票直接写入最终模板。
   [Wang et al., 2022](https://arxiv.org/abs/2203.11171)

## 冻结基线错误分解

对 `train100_seed15_v11_routed_frozen` 的 32 个 Teacher 语义错误重新分析：

- 21/32 的原始检索结果中不含规范化 golden answer，主要是召回/查询问题；
- 11/32 的证据中已经出现 golden answer，但最终仍选错，主要是关系方向、候选消歧、粒度或
  过宽列表问题；
- decompose 分支错误 20 条，delegate 分支错误 12 条；
- 失败答案中有 11 条直接输出 `no`，而这些问题并不是 yes/no 问题；
- 这说明剩余错误不能靠单一更长 synthesis prompt 解决，召回和证据选择都需要改进。

## Qwen3-8B 证据决策能力探针

`probe_qwen_evidence_decision.py` 在 18 个冻结案例上运行 3 个 seed，共 54 次调用。输入只含问题、
第一条查询和第一轮原始检索证据；golden 只用于事后评分。

| 指标 | 结果 |
| --- | ---: |
| JSON 可解析率 | 100.0% |
| 证据充分/不足动作代理准确率 | 59.3% |
| gold 不在证据时选择继续搜索 | 83.3% |
| gold 在证据时选择合成 | 47.2% |
| gold 在证据时 answer EM | 30.6% |
| gold 在证据时逐字 quote 有效 | 22.2% |
| 选择搜索时 next query 非空 | 100.0% |
| 选择搜索时 next query 不重复 | 100.0% |
| 三次 action/answer/query 完全一致案例 | 55.6% |

这里的“gold 是否在证据”只是规范化字符串代理，不等价于完整蕴含判断，因此动作准确率不能当成
正式 QA 指标；但两个结论很稳健：协议和下一查询生成很强，答案抽取与 quote 复制较弱。

## 多查询召回探针

`probe_qwen_multiquery_recall.py` 对全新 train40 中 13 个 v11 失败案例各生成两种互补视图：

- `anchor_query`：问题中最短、最有辨识度的实体/标题/事件；
- `relation_query`：保留关系与限定条件、但不同于已有查询的独立改写。

每例运行 3 个 seed，共 39 次 Qwen 调用和 78 次 top-5 检索：

- JSON 可解析率 100%；
- 原证据缺少 golden 的 7 个案例中，新增查询至少一个 seed 恢复 5 个；
- 其中 3 个案例在三个 seed 下全部恢复；
- 两条查询文本跨三个 seed 完全相同的案例为 0%，说明查询具有有效多样性但不稳定。

该结果证明 query diversification 能提高召回，但也说明必须有可靠的稀疏触发器，否则会把更多
passage 噪声交给只有 8B 的合成模型。

## v12：选择性 Corrective Retrieval

1. `[角色] Invalid-answer detector` 只在非二元问题输出 `no`、`unknown` 或无法判断时触发一次。
2. `[角色] Corrective query planner` 由同一个 Qwen3-8B 根据原问题和历史查询生成一条新查询。
3. `[机制] Deterministic recovery` 固定执行一次 top-5，再使用全部原始证据重新合成，最多一次。

全新固定 train40，selection seed `20260818`：

| 指标 | v11 | v12 |
| --- | ---: | ---: |
| Teacher semantic | 67.5% | 62.5% |
| Exact match | 60.0% | 57.5% |
| Token F1 | 61.55% | 60.17% |
| Mean model calls | 2.425 | 2.875 |
| Mean tool calls | 1.425 | 1.650 |
| Mean total tokens | 4,731 | 6,269 |

配对语义为 1 gain / 3 loss / 36 tie。v12 共触发 8 次；触发案例没有语义 gain，出现 1 次 loss。
三次独立 Teacher Judge 均稳定得到 v11 `27/40`、v12 `25/40`，0 个判分不稳定案例。v12 淘汰。

失败原因不是 JSON 或查询生成失败，而是“已有答案无效”不能推出“再检索一次后同一模型就能正确
选答案”；新 passage 会增加噪声，同一模型也会延续原关系误判。

## v13：Comparison Evidence Matrix

1. `[角色] Three-way router` 在一次 JSON 调用中输出 `delegate`、`decompose` 或 `comparison`；
   comparison 同时生成两个对象针对同一属性的查询。
2. `[机制] Symmetric retrieval` comparison 固定执行两次 top-5，形成 side A / side B 原始证据列。
3. `[角色] Comparison synthesizer` 只允许先建立两侧相同属性，再执行大小、先后、相等或共享属性
   判断；非 comparison 继续沿用 v11。

结果：

- train40 中固定 9 条 comparison targeted probe：v11 与 v13 均为 Teacher `9/9`、EM `8/9`；
- train100 seed15 的固定 27 条 comparison：v11 为 `24/27`（88.9%），v13 为 `23/27`
  （85.2%），0 gain / 1 loss；
- v13 EM `20/27`（74.1%），低于 v11 的 `21/27`（77.8%）；
- v13 三次独立 Teacher Judge 均为 `23/27`，0 个判分不稳定案例。

固定两列能规范工作流，但 v11 actor 本来就在多数比较题上主动执行一到两次检索；强制第二次检索
没有新增语义收益。v13 淘汰。

## 最终设计边界

1. `[机制] 保留选择性激活`：继续使用 v11 的 `delegate/decompose` 路由；全量重型流程会增加噪声。
2. `[角色] Qwen 适合作查询控制器`：短 JSON、下一查询、bridge 后续查询是目前最可靠的局部能力。
3. `[机制] 原始证据保持权威`：不新增自由摘要、事实账本或 quote 作为独立事实层；探针显示这些
   中间表示容易遗漏或改写关键关系。
4. `[角色] 不让同一模型覆盖自己的答案`：通用 verifier 和回答后 corrective retry 都会放大相关
   错误；除非有独立、可靠的触发信号，否则只允许它控制检索，不覆盖 final answer。
5. `[机制] 不晋升仅召回改善的方案`：多查询探针有召回收益，但 v13 表明更多证据不自动变成更高
   QA 准确率；晋升必须经过 end-to-end Teacher 配对测试。

## 推荐与后续优先级

推荐模板保持为 `final_template_routed_adaptive/`。若继续研究，优先级如下：

1. 用 train 上 `delegate` 与 `decompose` 的真实配对胜负作为离线路由标签，搜索更可靠、仍完全
   answer-neutral 的 router prompt；运行时依旧只调用 Qwen3-8B。
2. 研究不增加 passage 数量的 query fusion，例如多个查询召回后用确定性去重并只保留总计 top-5，
   从而利用召回多样性而不增加 synthesis 噪声。
3. 在新的 train seed 上先做固定困难子集 gate；只有出现语义净 gain 后再跑 train100。
4. 不再优先投入通用 verifier、自由问题摘要、第三次无条件检索或固定 comparison 双检索。

## 新增产物

- `probe_qwen_evidence_decision.py`
- `probe_qwen_multiquery_recall.py`
- `templates/search_agent_v12_corrective_recovery/`
- `templates/search_agent_v13_comparison_matrix/`
- `artifacts/qwen_capability_probe_seed15.jsonl` 及 summary
- `artifacts/qwen_multiquery_probe_seed18.jsonl` 及 summary
- `artifacts/benchmarks/train40_seed18_v11_frozen/`
- `artifacts/benchmarks/train40_seed18_v12_corrective/`
- `artifacts/benchmarks/train27_seed15_comparison_v13/`

## 验证

- 两个 probe 脚本均通过 `py_compile` 并完成真实本地 Qwen3-8B 调用；
- v12、v13 模板均通过 `search_harness template validate`；
- 所有 benchmark 均 100% completed、0 runner error、0 retriever error；
- v11 train40、v12 train40、v13 comparison27 的 Teacher Judge 均重复三次，判分完全稳定。
