# 20260809_base：Candidate 被 Evaluation 打回的原因分析

分析日期：2026-08-09
运行：`runs/evolution/20260809_base`（`search_base` / student = `qwen3:8b`）
被打回的对象：`research_attempt=2` 的 Candidate
`candidate_attempt_20260809T061904511316Z_ab5a5f50`，digest `30592fd2…`

---

## 0. 打回的形式与实质

| 关卡 | 结果 |
|---|---|
| `stage_candidate` 校验 | passed（新增 `extensions/second_entity_retrieval/component.py`） |
| `verify_conformance` | **pass**，12/12 faithful |
| `evaluate_candidate` | accuracy 0.6711 → 0.6711（完全持平），token 579,635 → 1,118,002 |
| promotion safety gate | **passed**（`accuracy_delta=0.0 ≥ -0.02`；`total_token_ratio=1.93 ≤ 5.0`） |
| `review_candidate` | **reject** |
| promotion effect gate | failed —— 唯一理由是 "Candidate Reviewer did not recommend acceptance" |

**注意：数值门禁放过了这个 Candidate。** 一个把总 token 提高 93%、准确率一点不变的方案，仅靠 Candidate Reviewer 的语义判断被拦下。这是 gate 配置本身的问题（下文 §6）。

Reviewer 给出的三条 reject 理由（selectivity 失败并造成实害、聚合效果中性偏负、成本与收益不成比例）在轨迹里都能被逐一复现和量化。下面把它们落到**方案的具体设计位置**上。

---

## 1. 方案是什么

Mechanism（`distill_mechanism-ddd6d5dc4c4fb458/mechanism.json`）：

- 目标：两实体比较题里，学生只搜了第一个实体、返回段落里没有第二个实体时，让它在给出比较之前先补一次第二实体检索。
- 结构性 guard：`post_tool` + 已完成的 `search` 且有 `tool_result` + 本 rollout activation_count == 0。
- 语义谓词：`decision_evaluator: "hook_model"`，三条件合取
  1. 问题恰好命名两个不同实体，且问"哪一个在**计数**或**持有**属性上更多/有"；
  2. 刚执行的 query 只命名了其中第一个实体；
  3. 返回段落里没有提到第二个实体。
- 动作：把一段通用 note **追加进 `stage.tool_result`**，然后 `activation_count = 1`。
- negative / uncertain / 预算耗尽：不改上下文。

实现（`compile_candidate-3a3f216dd03e3bfe` 的 `component.py`）忠实照搬：结构 guard 之后一次 `context.call_model`，`model_profiles={"student"}`，解析 `{"label": ...}`，只有 `positive` 才改写 `tool_result`。

---

## 2. 缺陷一（最致命）：谓词的裁判换人了

| | 取证阶段（4 个 Trial） | 上线阶段（225 个 rollout） |
|---|---|---|
| 谁判定 activation_condition | Intervention Worker = `deepseek-v4-flash`，`thinking_mode: enabled`，temp 0.2，seed 42 | Hook 的 `student` profile = `qwen3:8b`，`ollama_think: false`，temp 0.65，max_tokens 4096 |

Mechanism 里那三条合取条件（尤其条件 1「是不是 count/possession 比较题」）是**需要推理的语义判断**。它在证据阶段由一个开了 thinking 的强模型、低温、固定 seed 做出；上线后交给被改造的那个 8B 模型、高温、无 thinking、单次采样。

**这不是推测，轨迹里有直接反证：**

`5abd9054`（"Fast Cars, Danger, Fire and Knives includes guest appearances from which hip hop record executive?"）是**取证阶段的 negative 控制样本 trial 002**，deepseek 正确判为不适用；`verify_conformance` 重放它也是 3/3 faithful（正确 no-op）。但在 `evaluate_candidate` 的 225 rollout 里，**同一个 example 被 qwen3:8b 判成 positive 并插入了 note（1/3）**。

同时，真正的目标样本 `5a81ff1d`（possession 比较，取证阶段 trial 004 的 positive）在评估里只触发 2/3。

所以这个分类器**既有偏，又不稳定**：同一输入在 temp 0.65 下 3 次采样给出不同标签。方案把一个三元决策契约实现成"单次随机采样、无自一致性检查、无确定性"，而 `verify_conformance` 只跑了 3 个副本、恰好全部 no-op，所以没暴露出来。

---

## 3. 缺陷二：结构性 guard 太弱，基率完全不匹配

代码里 LLM 调用之前的全部过滤条件是：

```python
activation_count < 1
tool_call.name == "search" and isinstance(tool_result, ToolResult)
query 非空 and question 非空
```

这几条对**每个 rollout 的每次搜索都成立**。于是：

- 分类器在 225 个 rollout 全部被调用（搜索次数分布：1 次 179 个、2 次 45 个、3 次 1 个，共 272 次搜索 → 约 270 次分类调用）。
- note 实际插入 30 个 rollout / **18 个 distinct example（75 个中的 24%）**。
- 而机制的适用类在这个数据集上只有 **2 个 example**。

命中明细（18 个触发 example）：

| 触发 example | 题型 | 是否在适用类内 | incumbent → candidate |
|---|---|---|---|
| `5a7e3604` Which tennis player won **more** Grand Slam titles, Leconte or Stark | count 比较 | ✅ | 0/3 → **3/3** |
| `5a81ff1d` **Who was inducted** into RRHoF, David Lee Roth or Cia Berg | possession 比较 | ✅ | 3/3 → 3/3（本来就对，无空间） |
| `5a822d46` What actor in **D.C. Cab** also had a role in **Barney Miller** | bridge/交集 | ❌ | 3/3 → **1/3** |
| `5a7a5274` **Who was born first**, Nethersole or Elizabeth Stuart | 日期比较 | ❌ | 3/3 → **2/3** |
| `5abd9054` …guest appearances from which hip hop record executive | 单实体（取证期 negative 控制） | ❌ | 3/3 → 3/3 |
| `5a8efd3c` / `5abb1f74` / `5ae3918b` / `5ab5a2f8` Are both X and Y …? / 共同点 | 共享属性 yes-no | ❌ | 持平 |
| `5ac2a912` / `5a736bfa` Which band was founded **first** / Who is **older** | 日期比较 | ❌ | 持平 |
| `5a74f2ff` / `5a71458e` What **city** are X and Y … | 位置 | ❌ | 持平 |
| `5ae3345f` Are both Tim McIlrath and Spike Slawson American punk musicians | 共享属性 yes-no | ❌ | 2/3 → 3/3（误触发而**碰巧**帮上） |
| 其余 4 个 | bridge / 多跳 | ❌ | 持平 |

**precision ≈ 2/18 ≈ 11%**。适用类只占 2.7% 的样本，而门控在 24% 的样本上放行 —— 假阳性数量必然远超真阳性数量，方案在设计上就没有留任何余量。

关键点在于：Mechanism 的 `negative_rule` **写对了**（"the question is not a two-entity count/possession comparison"），Reviewer 也明确指出这是 "a visible positive misclassification by classification/control logic, not an applicability gap"。问题不是机制描述错了，而是**实现把 100% 的判别负担压给了一次 8B 采样，没有任何便宜的前置收窄**。而三条件里有两条其实是可以用代码判的（一旦拿到两个实体名，"query 是否只含第一个"、"段落里是否出现第二个"都是字符串包含检查）；真正需要语义的只有条件 1。方案选择了最贵且最不可靠的划分方式。

---

## 4. 缺陷三：假阳性不是 no-op，而是主动的错误引导

`fallback` 只覆盖了 negative / uncertain / 预算耗尽三种"不动手"的情形。**没有任何一条设计考虑"positive 判错了会发生什么"** —— 而这个动作在判错时的破坏力很大，因为它做了两件事：

1. 把 note 写进 `stage.tool_result`，让一条**指令**伪装成检索到的证据；
2. note 的内容是一条祈使句："the second entity is absent from every returned passage. Before producing the comparison, run the second per-entity retrieval for the other entity."

`5a822d46` 的完整链条（`evaluate_candidate` 的 r000 rollout）：

```
问题：What actor in the film D.C. Cab also had a role in the TV series Barney Miller?
search1: "cast of D.C. Cab"
  → 返回 D.C. Cab 演员表（含 Max Gail, Adam Baldwin, Mr. T, Gary Busey, Marsha Warfield…）
  → 分类器判 positive（看到两个专名，且 "Barney Miller" 不在段落里）
  → note 被追加进 tool_result
search2: "cast of Barney Miller"        ← 学生完全照 note 执行
final_answer: "Gary Busey"              ← 正确答案是 Max Gail
```

incumbent 在同题上是 **stable_correct 3/3（Max Gail）**：只看 D.C. Cab 演员表时它答对了；被机制推去补拉 Barney Miller 演员表之后，它在交集里挑错了人 → 3/3 变 1/3。

**机制让它"多检索了证据"，然后答错了。** 这说明「补一次第二实体检索」这个动作本身只在"两实体各自属性需要独立取证"的题型下有益；在 bridge/交集题上，扩大证据面反而增加了干扰项。方案把一个**题型专属**的动作装在了一个**题型判别不可靠**的门控后面。

---

## 5. 缺陷四：成本结构与预算语义错位

`activation_budget: 1` 被实现成"最多改一次上下文"，而**不是"最多分类一次"**：

```python
if context.state.get(ACTIVATION_KEY, 0) >= 1: return   # 先查预算
...
response = context.call_model(request)                  # 再调模型
if parsed.get("label") != "positive": return            # negative 不消耗预算
```

negative 标签**不消耗预算**，所以下一次搜索还会再付一次分类。结果：

- Hook token = **496,967**，占总量 44%，几乎等于整个 incumbent student 运行（579,635）的 86%；
- 约 270 次分类调用，平均每次约 1,840 token（prompt 里带了完整的 5 条返回段落）；
- 总 token 579,635 → 1,118,002，**+93%**；
- 换来的**可归因**收益：1 个 example（`5a7e3604`，+3 rollout）。

即约 497k token 买了 1 个 example。Reviewer 说的 "the cost structure is inherent to per-event Hook-model classification" 是准确的 —— 这不是调参能解决的，是"每个事件都要过一次 LLM"这个架构决定的。

---

## 6. 为什么前面的关卡没挡住

**`verify_conformance` pass 12/12 是真的，但它的检验范围太窄。** 它只重放了 4 个 Trial example × 3 副本：

```
5a7e3604: 3/3 faithful    5abd9054: 3/3 faithful
5a8b6375: 3/3 faithful    5a81ff1d: 3/3 faithful
```

它回答的是"实现是否忠实于机制在**自己那 4 个证据样本**上的行为"，而不是"这个门控在全量分布上的选择性如何"。所以 conformance 对 §2 的不稳定性和 §3 的假阳性率完全没有观察力 —— 甚至 `5abd9054` 在 conformance 里 3/3 no-op、在评估里却触发了。

**promotion safety gate 也放过了**：`accuracy_delta = 0.0 ≥ min_accuracy_delta(-0.02)`，`total_token_ratio = 1.93 ≤ max_total_token_ratio(5.0)`。这个 gate 允许"零收益 + 近两倍成本"通过，只要 Reviewer 说好就能晋级。**`max_total_token_ratio: 5.0` 对一个只想修一小类失败的干预来说过于宽松**，而且 gate 没有任何"成本必须与收益成比例"的联合条件。

**证据阶段的问题（更上游）**：这次的 evidence 只有 1 个批次 4 个 Trial（2 positive + 2 negative），第一次 Evidence Review 就 `ready_to_distill`。两个 negative 是"单实体属性题"和"query 已含两实体的位置题"—— 都是**一眼就不适用**的远距离负例。真正危险的近邻类型（日期比较 "who was born first"、共享属性 yes-no "are both X and Y…"、bridge/交集题）**一个都没被取证**，而评估集上的假阳性正是全部来自这三类。`known_limits` 里也承认了 "Only 2 distinct positive examples support the mechanism"，Reviewer 仍然放行了。

---

## 7. 结论：方案不合适的位置

按对打回的贡献排序：

1. **谓词的裁判从强推理模型换成被测的 8B 模型**（`decision_evaluator: hook_model` + `model_profiles={"student"}`）。取证时的判别力不可能转移到上线时，而机制没有任何机制来补偿这个落差。取证期的 negative 控制样本上线后被判 positive，是这一条的直接证据。
2. **门控的基率完全失配**：结构 guard 只排除了"不是 search"，等于不过滤；语义门在 24% 的样本上放行，而适用类只有 2.7%。precision 11%。三条件里两条可以用代码确定性判定，却一起交给了 LLM。
3. **假阳性代价没被设计**：动作是往 `tool_result` 里塞祈使指令，学生一定会照做；在 bridge 题上这会主动破坏原本正确的答案（D.C. Cab 3/3 → 1/3）。`fallback` 只写了"判负不动手"，没写"判正错了怎么办"。
4. **`activation_budget` 只约束动作不约束推理**，negative 不消耗预算，导致成本随搜索事件线性增长，497k Hook token 换 1 个 example。
5. **证据基础与上线分布不同**：4 个 Trial、2 个 positive（其中一个本来就 3/3 正确 → 真实可得上限只有 1 个 example），negative 只覆盖远距离反例，近邻题型零覆盖。

---

## 8. 如果要救这个方向，改哪里

1. **把条件 1 的判别从 LLM 里拿出来**，或至少加一道便宜的确定性前置门：问题里必须出现比较框架标记（`more/most/fewer/-er than/which one ... or`）**且**属性是 count/possession 类；`or` 分隔的两个专名跨度必须存在。条件 2、3 直接用字符串包含在代码里判，不进 prompt。这一条同时压掉 §3 和 §5。
2. **不要用 `student` profile 做判别**，或者把判别做成低温 + 自一致（k=3 多数票）+ 解析失败即 no-op。若必须用 student profile，就必须承认它的不稳定性并用多数票兜住。
3. **把 note 从 `stage.tool_result` 里挪出去**，改成明确标注来源的系统侧提示，且措辞从祈使句改为条件句（"如果比较还缺少另一实体的证据，则…"），降低假阳性时的强制力。
4. **给分类调用本身设预算**（例如每 rollout 最多 1 次分类，无论标签），把 Hook 成本从 O(搜索事件) 降到 O(rollout)。
5. **上游**：Evidence Reviewer 在 `ready_to_distill` 前应要求 negative 覆盖**近邻**反例（同为两专名比较但属性类型不同：日期、共享属性 yes-no、bridge），而不是任意两个明显不适用的样本；conformance 也应在一个负样本子集上抽查选择性，而不是只重放 4 个证据样本。
6. **门禁**：把 `max_total_token_ratio` 调到与"局部干预"相称的量级（如 1.2–1.5），并加一条联合条件 —— 成本增幅超过阈值时必须有统计上可辨的 accuracy 增益，否则不进入 Reviewer 判断。这次是 Reviewer 单点兜住的，不应该依赖它。
