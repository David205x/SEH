# Compiler Shadow Authoring View A/B 实验记录

状态：历史 A/B；验证有效的 native API 视图、packet 去重、continuation 和实验交接设施已
选择性迁入正式 Compiler，影子角色与入口已于 2026-08-14 清理。

## 1. 目标与边界

本实验比较正式 Compiler 与 shadow Compiler 在相同 `CompilerInput`、父模板或续编
workspace、Teacher API、输出协议和确定性候选校验下的表现。Shadow 只调整：

- 初始输入如何组织完整 Mechanism、约束、父模板注册信息和 capability packet；
- `query_hook_api` 结果如何避免同时重复展示 structured contract 与 native reference；
- 对常见的 model-gated `post_tool` / `pre_final` 组合提供完整通用参考实现。

正式 Compiler 模板、正式 packet、底层 artifact、候选 workspace 工具以及 Validator
均不修改。稳定性优先于 token 压缩：信息有疑义时保留，只有可以证明同义重复的表示才
在 shadow 视图中折叠。

## 2. Shadow 设计

初始输入改为一份分层 Implementation Brief，依次包含完整 Mechanism、按主题导航但保留
原始编号的全部 implementation constraints、确定性 validation feedback、父模板的精确
`harness.json` / `evolution.json`、extension 索引、续编 changed files、packet 选择依据、
runtime-input native 文档、尚未被 topic 文档覆盖的 public contracts，以及按机制形态选择的
reference pattern。

Packet 的底层内容不裁剪。模型视图仅在一个 runtime-input topic 的 `native_reference` 已经
覆盖同一 symbol 时，不再并列重复其 structured contract；未覆盖 contract 仍全部保留。
`query_hook_api` 继续允许任意白名单精确查询，已解析结果优先显示 native 签名、类型、
docstring 与使用约束。

## 3. 验证矩阵

实验分三层进行：

1. 静态/离线：模板装配、工具面一致、信息完整性、续编文件投影、正式文件无修改；
2. Teacher A/B：历史 artifact 与人工构造机制各重复至少 3 次，比较完成率、候选提交率、
   首次 finalize 通过率、API/文件查询、修订次数、工具错误与 token；
3. 候选行为：所有已提交候选先做确定性 Candidate Validation；对具有可复用 Trial 的历史
   代表案例调用 Conformance Reviewer，对人工机制使用与机制行为相匹配的 deterministic
   semantic smoke。

人工机制覆盖简单和复杂设施，而不以检索准确率为目标：deterministic `post_prompt`、
deterministic `post_tool`、Hook-model `post_tool` 语义改写、`pre_final` defer，以及需要
rollout-local state 的一次性或跨 phase 行为。

## 4. 进行中结果

### 2026-08-13 静态阶段

- Shadow 模板已隔离在 `experiments/teacher_query_views/templates/compiler`，对正式模板零改动。
- Shadow 工具面与正式 Compiler 一致：只替换 `query_hook_api` 的返回视图，写入、删除和
  finalize 仍直接委托正式实现。
- 以 `20260809_base/compile_candidate-0f15228acedeb67a` 离线装配，Implementation Brief
  约 30,280 字符；历史正式首轮 user prompt 约 42k 字符，且 shadow 额外提供该案例缺失的
  通用 model-gated `post_tool` reference。
- 历史该正式运行执行 7 次文件读取、6 次 API 查询，其中 3 次为自由文本式未知查询；这将
  作为真实 A/B 中“是否减少无效探索”的基准，而不直接视作 shadow 已经改善。

真实 API、语义 smoke 与 Conformance 数据将在每批完成后继续追加。本节只记录已经执行的
结果，不提前写入结论。

### 2026-08-13 历史 artifact A/B

输入为 `20260809_base` 中同一机制的 fresh compile 与第一次 continuation repair，formal /
shadow 每组各重复 3 次。所有 12 次运行均完成、提交候选、通过确定性 Candidate Validation，
且均在第一次 `finalize_candidate` 通过；源 artifact 与 continuation 文件哈希前后相同。

| 状态 | 方案 | 首次 finalize | 平均 API 查询 | 平均 rejected 查询 | 平均文件读取 | 平均 tokens |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| fresh | formal | 3/3 | 7.67 | 4.33 | 6.00 | 342,743 |
| fresh | shadow | 3/3 | 1.33 | 0.00 | 4.67 | 150,801 |
| continuation | formal | 3/3 | 0.00 | 0.00 | 5.00 | 145,025 |
| continuation | shadow | 3/3 | 0.00 | 0.00 | 2.00 | 89,160 |

历史 fresh case 的 shadow token 比为 0.44，continuation 为 0.615。Shadow 第二次 fresh
运行仍按需执行 4 次 API 查询，第三次仍完整读取父文件，因此降低探索不是通过禁用核实工具
获得。Fresh formal 的未知自由文本查询较多；shadow 精确查询均命中。

### 2026-08-13 通用机制 A/B

旧研究夹具只承担机制内容来源；A/B 输入复制层显式迁移其已过期的 parent path 和旧单 phase
字段到当前协议，迁移记录在 summary，源夹具哈希保持不变。四种机制的 formal / shadow 各
3 次，共 24 个候选全部首次 finalize，并全部通过机制专用 deterministic semantic smoke：

| 机制 | formal semantic | shadow semantic | shadow/formal tokens | shadow/formal requests |
| --- | ---: | ---: | ---: | ---: |
| deterministic `post_tool` append | 3/3 | 3/3 | 0.991 | 1.236 |
| one-shot `post_prompt` append | 3/3 | 3/3 | 1.114 | 1.310 |
| Hook-model `post_tool` result rewrite | 3/3 | 3/3 | 0.676 | 0.874 |
| deterministic `pre_final` defer | 3/3 | 3/3 | 0.878 | 1.107 |

这组结果不支持“shadow 对所有机制都省成本”。它对 Hook-model 重写的帮助明显；对简单固定
机制可能因完整 packet 诱发更多逐项复核。确定性 `post_tool` 中，shadow 查询数并未降低，
但 resolved rate 从 formal 的低命中变为 100%。

### 2026-08-13 补充设施覆盖

人工构造当前协议的 `pre_tool` 参数改写与 `post_tool -> pre_final` 跨 phase 状态交接，
formal / shadow 各 3 次。12 个候选全部首次 finalize，并通过专用 semantic smoke：前者只
清除首个 search query 的首尾空白、保留工具名和其他参数；后者在空 search result 后只
defer 一次，非空 result 不误触发。

| 机制 | formal semantic | shadow semantic | shadow/formal tokens | shadow/formal requests |
| --- | ---: | ---: | ---: | ---: |
| deterministic `pre_tool` rewrite | 3/3 | 3/3 | 0.919 | 1.200 |
| two-phase state handoff | 3/3 | 3/3 | 1.052 | 1.406 |

目前共得到 36 次 shadow/formal Teacher compile、36/36 首次 Candidate Validation 通过，
其中具备专用行为测试的 36 个通用/设施候选为 36/36 semantic smoke 通过。历史候选的真实
Trial replay 与 Conformance Review 仍在进行；在该结果完成前，不把静态与 stub 行为通过
等同于端到端机制忠实。

### 2026-08-13 真实 Trial replay 与 Conformance Review

从历史 fresh A/B 各取一个候选，分别在独立 Version Store 中 stage，再复用源 run control
journal 所引用的同一组 8 个完整 Intervention Trial；每个候选运行 24 条 replay。未修改
trial、candidate 或 reviewer 输入内容。

| Candidate | decision | faithful | mismatch | failure layer | reviewer tokens |
| --- | --- | ---: | ---: | --- | ---: |
| formal fresh #1 | revise | 22/24 | 2 | evaluator ×2 | 293,717 |
| shadow v1 fresh #1 | revise | 20/24 | 4 | evaluator ×4 | 317,476 |
| shadow v1 fresh #2 | revise | 21/24 | 3 | evaluator ×3 | 297,240 |

Formal 与 shadow 都没有 integration、state、lifecycle 或 registration 失败；不忠实项集中在
Hook-model 对明确正负边界的分类。Shadow v1 使用 reference 引导出的 JSON label，真实模型
出现过近似 JSON 尾部损坏，并更频繁把明确 positive 判为 uncertain。由此将 shadow reference
改为单行 label，并在 brief 中明确本地 Hook prompt 必须保留完整 Mechanism decision
contract 与 evidence boundary。

两轮 reference 修订均先重新编译 3 次，6/6 首次 Validation 通过，且新候选均采用单行协议。
真实 replay 结果如下：

| Candidate | decision | faithful | mismatch | failure layer | reviewer tokens |
| --- | --- | ---: | ---: | --- | ---: |
| shadow v2 | revise | 21/24 | 3 | action ×2, evaluator ×1 | 300,428 |
| shadow v3 | revise | 20/24 | 4 | action ×2, evaluator ×2 | 326,329 |

单行协议消除了 malformed JSON / parse 类失败，并把明确正例的 uncertain 错误从本次样本中
移除；但 Compiler 对 “POSITIVE `<detail>`” 的具体 detail 仍可能生成泛化描述，且 Hook model
仍会把回答实体的描述性限定误当成缺失证据。继续给 reference 增加本案例边界会变成对单一
检索机制的定向调参，因此实验在此停止，不修改正式 Compiler 或 Conformance 判据。

## 5. 结论与处置

Shadow 已证明以下工程价值：

- Compiler 工具设施未被破坏：全部 54 次本轮 compile（历史 A/B 12 次、通用/设施 A/B
  36 次、reference 修订 6 次）均能提交并首次通过确定性 Candidate Validation；六类通用设施
  的 36 个候选全部通过专用 semantic smoke；
- 续编 changed files 的初始投影有效，历史 continuation 的平均文件读取从 5 降至 2；
- native API 文档视图把所有 shadow `query_hook_api` 查询变为 resolved，消除了正式条件中
  大量自由文本 unknown query；
- 对历史复杂 fresh compile 和 Hook-model 结果重写，Compiler token 分别下降约 56% 和 32%。

但当前证据不支持将 shadow 直接替换正式 Compiler：

- 简单确定性机制的请求数可能增加 20%–41%，token 可能增加 5%–11%；完整 packet 会诱导
  逐项复核，不能视作恒定成本优化；
- 历史真实 Conformance 中 formal 为 22/24 faithful，shadow 的多个版本为 20–21/24，未达到
  “稳定性不下降”的接受条件；
- reference source 不只是 API wiring，它会隐式规定 Hook-model 的输出协议与语义 prompt。
  这类行为模板不能仅凭静态 Validator 或 stub smoke 验证，必须经过真实 Hook-model replay。

因此保留 shadow 实现、A/B 驱动、设施请求与全部实验 artifact 供后续研究；正式 Compiler、
正式 capability packet 与生产路由不变。若继续优化，应把“API 接线 reference”和“决策语义
示例”显式分离，并用多种 Hook-model 机制的真实 replay 作为接受门，而不是继续在本案例上
追加 prompt 规则。
