# 问题重写与任务分解补充实验

## 结论

推荐模板更新为 `final_template_routed_adaptive/`。原 `final_template/` 保持不变，作为低成本对照。

新模板只使用项目配置中的本地 `qwen3:8b`：Question Router、Adaptive Decomposer 和主 Actor
均通过 `student` profile 调用同一个模型。Teacher Judge 只参与离线评分，不在模板清单、代码或运行时
依赖中出现。模板不读取数据集答案、样本 ID 或 metadata。

模板源码树 SHA-256：

```text
979afdc44d6073a169f5bb628dd9474bbfd9227173aa3b9dc8d4d69f57e230c2
```

可移植 ZIP SHA-256：

```text
6c56d7e8f160e67a61ad4be3163e4bd52fb92163e2ec8c7de285cd972dc164e3
```

## 最终机制

1. `[角色] Question Router`：同一个 qwen3-8b 只根据问题文本输出 `delegate` 或
   `decompose`，不回答问题、不读取检索证据。
2. `[机制] Delegate`：直接问题和比较/共享属性问题沿用冻结版 compact prompt 的自由检索循环；
   路由结果不会被注入 Actor 上下文。
3. `[角色] Adaptive Decomposer`：仅在 `decompose` 分支中，根据原问题和已返回证据逐步输出下一条
   answer-neutral 检索义务；最多两次检索，证据充分时可提前综合。
4. `[机制] Deterministic Projection`：检索阶段把 Actor 输出确定性投影为 planner 指定的
   `search(query, topk=5)`，隔离工具协议漂移；最终答案仍由 qwen3-8b Actor 根据原始证据生成。
5. `[机制] Runtime Guards`：保持 top-k=5，并只修复检索后短答案遗漏的 `<final_answer>` 标签，
   不改变答案语义。

## train24 消融

固定 selection seed `20260814`、sampling seed `42`、top-k=5；Teacher Judge 为语义主指标。

| 版本 | 控制机制 | Semantic | EM | Token F1 | Mean tokens | 决策 |
| --- | --- | ---: | ---: | ---: | ---: | --- |
| v6 | 冻结 compact prompt | 58.3% | 45.8% | 49.17% | 2,982 | 对照 |
| v7 | 问题摘要/结构重写 | 50.0% | 41.7% | — | 3,979 | 淘汰：0 gain / 2 loss |
| v8 | 一次性静态 1–2 子任务 | 58.3% | 45.8% | 49.17% | 4,714 | 淘汰：同分但更贵 |
| v9 | 证据后自适应分解，最多 2 搜索 | 62.5% | 54.2% | 59.88% | 4,997 | 保留 |
| v10 | 自适应分解，最多 3 搜索 | 62.5% | 50.0% | 53.33% | 6,534 | 淘汰：重复查询且更贵 |
| v11 | 路由 + v9 自适应分解 | 66.7% | 54.2% | 57.50% | 4,262 | 扩大验证 |

v9 的三次 Judge 多数票为 16/24，v6 为 14/24；真实配对为 3 gain / 1 loss。
v10 的第三次搜索没有提高语义正确率，平均检索从 1.42 增至 1.63，并出现重复查询。

## train100 扩展

固定 selection seed `20260815`。v11 路由为 `delegate=56`、`decompose=44`。

| 指标 | 冻结 v6 | 全量自适应 v9 | 路由自适应 v11 |
| --- | ---: | ---: | ---: |
| Teacher semantic | 61% | 60% | **68%** |
| Exact match | 47% | 50% | **56%** |
| Token F1 | 57.10% | 59.29% | **64.97%** |
| Mean tool calls | 1.06 | 1.66 | 1.32 |
| Mean Actor model calls | 2.07 | 2.66 | 2.33 |
| Mean total tokens | 2,926 | 5,439 | 4,789 |

v11 相对 v6 的语义配对为 13 gain / 6 loss / 81 tie，精确 McNemar 双侧
`p=0.1671`；EM 为 14 gain / 5 loss，`p=0.0636`。Teacher Judge 三次独立运行均为
v6 `61/100`、v11 `68/100`，没有判分不稳定样本。

分层结果：bridge `56.2% -> 60.3%`，comparison `74.1% -> 88.9%`；easy、medium、hard
语义正确率都上升。v11 的总 token 相对 v6 增加约 63.7%，因此它是准确率优先模板，而不是成本优先模板。

## 冻结 heldout100

固定 selection seed `20260816`，100 条均为 hard；v11 路由为 `delegate=50`、
`decompose=50`。看到该结果后不再调整模板。

| 指标 | 冻结 final | 路由自适应 v11 | 差值 |
| --- | ---: | ---: | ---: |
| Teacher semantic | 52% | **60%** | +8 pp |
| Exact match | 35% | **40%** | +5 pp |
| Token F1 | 44.85% | **51.09%** | +6.24 pp |
| Mean tool calls | 1.06 | 1.36 | +0.30 |
| Mean Actor model calls | 2.09 | 2.36 | +0.27 |
| Mean total tokens | 2,963 | 5,008 | +69.0% |

语义配对为 13 gain / 5 loss / 82 tie，精确 McNemar 双侧 `p=0.0963`；EM 为
11 gain / 6 loss，`p=0.3323`。三次 Judge 均稳定得到 final `52/100`、v11 `60/100`。
bridge 从 `45.9%` 升至 `56.5%`；comparison 从 `86.7%` 降至 `80.0%`，说明路由仍有
改进空间，但净收益在未参与调参的 hard heldout 上复现。

## 设计判断

1. `[机制] 摘要重写` 不应默认启用：它增加约 34% token，却在小样本中产生两条净语义损失。
2. `[机制] 静态分解` 能稳定执行，但未知 bridge 使第二 query 宽泛；准确率持平而成本增加约 58%。
3. `[机制] 自适应分解` 的有效收益来自第二 query 使用第一步识别出的实体，例如先找到 bridge，
   再查该实体的目标属性。
4. `[机制] 选择性激活` 是关键：全量 v9 在 train100 的 bridge 上提升，却严重损伤 comparison；
   v11 先路由再分解，恢复并提高总体表现。
5. `[角色] 同模型控制器` 仍不是独立 verifier。它只决定检索过程，不能覆盖主答案或读取 golden；
   这限制了错误放大的范围。

## 产物

- `final_template_routed_adaptive/`：自包含、可直接实例化的最终模板。
- `artifacts/as_you_can_routed_adaptive_template.zip`：不含缓存文件的可移植包。
- `templates/search_agent_v7_rewrite` 至 `search_agent_v11_routed_adaptive`：消融候选。
- `artifacts/benchmarks/train100_seed15_v11_routed_frozen/`：train100 rollout 与三次 Judge。
- `artifacts/benchmarks/heldout100_frozen_v11_routed/`：heldout rollout 与三次 Judge。
- `artifacts/benchmarks/train100_seed15_v11_vs_v6.json`：train100 配对统计。
- `artifacts/benchmarks/heldout100_frozen_v11_vs_final.json`：heldout 配对统计。
- `probe_question_router.py` 与 `artifacts/router_probe_train100_seed15.jsonl`：只看问题的路由 probe。

## 验证

```powershell
D:\ProgramData\miniconda3\envs\env_search_harness\python.exe -m search_harness template validate `
  experiments/as_you_can/final_template_routed_adaptive --env-file .env
```

ZIP 已解压到 `artifacts/package_validation_routed_adaptive/` 并再次通过相同模板校验。
