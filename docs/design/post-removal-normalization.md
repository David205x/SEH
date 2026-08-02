# Post-removal Normalization

## 文档状态

本文记录 V1 实现删除后已经确认的目标架构。它描述边界和迁移方向，不把当前模块
布局误写成目标设计。具体代码迁移必须保留当前已验证的 V2 行为，并按可独立测试的
步骤推进。

## 已确认原则

- 保持一个 Python 包，在包内建立以后可抽取的 framework 边界；当前不创建独立
  发布的 framework 包。
- Student 与 Teacher Harness Template 都是外部模板资产；Role 实现不得嵌入 Prompt
  正文或具体组件装配。
- 通用 Agent/Harness runtime 不依赖 Student、Teacher、Evaluation 或 Evolution 概念。
- Student 与 Teacher Harness Template 共用一套 `HarnessManifest` schema 和一个
  `HarnessAssembler`。
- Teacher Role Definition 及其输入输出 Contract 属于 Evolution Research 应用；
  Harness Manifest 不保存 Role Contract 引用。
- 同一个 Role Runner 可以组合 Role Definition 与 Harness Template，并委托不同
  Agent Runner 执行。当前 OpenAI Agents SDK 路径与未来通用 Agent Loop 路径不得
  各自维护 Manifest 或 Component Loader。
- Template Version Store 与 Evolution Controller 是独立事实所有者，通过稳定身份
  相互引用，不重复写入 Journal 事实。

## 重构起点审计

重构开始时，V2 已具备可运行的 Controller、Teacher Role、Intervention、Evaluation 和
Template Versioning 语义，但代码边界仍保留迁移过程的形状：

- `core/` 实现 Agent Loop、Lifecycle、Tool Execution、Trace 和运行数据，
  `framework/` 只承载部分 Tool Definition 与 Prompt renderer，`registry/` 再负责
  Manifest、动态加载和 Assembly；三者共同组成了一个尚未物理闭合的 framework；
- `AgentLoop` 同时承担 Agent 容器、Harness 组合、Harness Instance 创建和循环驱动，
  `ModelClient.generate()` 只返回字符串，并通过“最近一次调用 metadata”旁路补齐
  Provider 信息；
- Student 与 Teacher 分别维护 `HarnessManifest`/`TeacherAgentManifest`、
  Assembly 与运行路径，Teacher Manifest 还保存 Role 与 Output Contract 引用，造成
  Harness 声明和应用角色声明耦合；
- `teacher/` 同时包含 Role Contract、Prompt 装配、Agents SDK 与原生 Chat Runtime、
  Resource Store、Intervention 分支执行、Mechanism Compiler 支持和独立 CLI；
- `evolution/control/effects.py` 将全部 Work Kind 的外部操作集中在一个文件中，成为
  Controller 与 Teacher、Evaluation、Versioning 之间的高扇出胶水；
- `versioning/validation.py` 同时验证通用 Harness Assembly 和 Evolution Policy，
  `versioning/journal.py` 仍使用已经废止的 Iteration 命名；
- `runners/` 混合 Agent 组装、批量 Rollout、Version Source、文件输出和 CLI，
  `runtime/` 则以过宽名称保存环境读取与并发辅助函数；
- 专用 Visualizer 仍处于活动包并被当前文档引用，和已经确认的归档目标不一致。

因此本阶段不是重新设计 Evolution Workflow，而是先让已经存在的行为语义归属到唯一
明确的边界。

## 最小有效抽象

只新增能够消除当前重复或建立真实依赖边界的抽象：

1. `Model` 与 `ModelResponse`：一次调用同时返回 Raw Model Output、usage 和 Provider
   metadata，删除 last-call metadata side channel；
2. `Agent`、`Harness`、`HarnessInstance` 与 Agent Runner 职责：分别表达组合、可复用
   机制、单次运行状态和执行方式；不同执行方式没有真实替换关系时不建立共同 Protocol；
3. `PromptComponent`、`OutputComponent`、`ToolComponent`、
   `ExtensionComponent`：形成共享 Manifest 与 Assembly 所需的最小组件闭集；
4. `ToolExecutor`：统一 Tool Call 到 Tool Result 的执行边界，不把 Tool Definition、
   Provider tool schema 或 Teacher Tool 另建平行模型；
5. `HarnessAssembler` 与 `ComponentLoader`：Student/Teacher 共享；只做声明解析、工厂
   加载、Contract 校验和装配；
6. `RoleRunner`：验证 Role Input/Output、准备 Role Resource 与 Role Continuation，
   再调用通用 Agent Runner，不自行实现模型循环；
7. 小粒度 `ControlEffect` handler 与 dispatcher：按 Work Kind 隔离外部操作，同时
   保持 Controller transition 和 Control Policy 为确定性代码。

以下抽象当前明确不建立：

- 通用 Workflow Engine、可配置状态机 DSL 或由模型自由选择的角色路由器；
- DI Container、全局 Service Locator 或只为减少构造参数而建立的 Repository 层；
- `StudentAgent`/`TeacherAgent` 继承树、角色专用 Agent Loop 或统一所有 Provider
  细节的超大 Runtime；
- 通用 Event Bus、跨所有 Artifact 的统一 Store、自动扫描式 Component Registry；
- 为未来独立发布预设的多包工程、同步/异步双份接口或长期 compatibility facade。

这些边界以后只有在出现第二个真实实现或重复调用方时再抽取。

## Teacher Agent 实例化

Teacher Agent 由三个可独立选择的输入组合而成：

```text
Teacher Role Definition
        +
Teacher Harness Template --HarnessAssembler--> Harness
        +
Teacher Model -----------ModelProvider-------> Model
        =
Teacher Agent
```

Evolution Controller 根据 Work Item 选择 `role_id`。Evolution Research 解析 Role
Definition，应用配置选择外部 Teacher Harness Template。共享 Harness Assembler
装配组件，Model Provider 提供配置的 Model，Role Runner 使用 Role Input 和 Run
Context 执行组合后的 Agent。

Role Definition 拥有输入输出 Contract；Harness Template 拥有 Prompt、Output、Tool
和 Extension Component Declaration。Agents SDK Runner 把这些通用组件适配为 SDK
对象，Core Loop Runner 则通过通用 Agent Loop 使用同一组装配结果。更换 Runner
不会改变 Role Contract 或 Harness Manifest。

## 已确认的清理结果

- 用共享 `HarnessManifest` 取代平行的 `TeacherAgentManifest` parser。
- 用共享 Harness Assembly 路径取代 Teacher 专用组件加载。
- 用通用 `ComponentFactoryContext` 取代 `PluginContext` 和
  `TeacherPluginContext`。
- 将 `plugin_importer` 改为 `component_loader`，`plugins_root` 改为
  `template_root`，模板内 `plugins/` 目录改为 `components/`。
- Prompt 和具体 Tool Factory 保留在外部 Harness Template 下，不放入 Evolution
  Research Role 模块。
- 在使用通用 Agent Loop 执行结构化 Teacher Role 输出前，先完成通用 Model 与
  Final Output 协议规范化。

## 可抽取的 framework 边界

通用机制集中在一个物理父目录下，避免继续由顶层 `core/`、`framework/`、
`models/` 和 `registry/` 共同承担：

```text
search_harness/
  __main__.py
  cli/
    main.py
    run.py
    evaluate.py
    evolve.py
    template.py

  framework/
    agent/
      agent.py
      model.py
      runner.py
      loop.py
      types.py
    harness/
      components.py
      manifest.py
      assembly.py
      inspection.py
      lifecycle.py
      state.py
      validation.py
    tools/
      definitions.py
      execution.py
    prompting/
      tagged.py
    trajectory/
      events.py
      trace.py

  integrations/
    openai_compatible/
      configuration.py
      model.py
    openai_agents/
      runner.py

  datasets/
  evaluation/
    domain.py
    service.py
    rollouts.py
    hotpotqa.py
    judge.py
    reporting.py

  evolution/
    control/
      domain.py
      controller.py
      transitions.py
      policies.py
      journal.py
      effects/
        evaluation.py
        research.py
        intervention.py
        candidate.py
        versioning.py
    research/
      tools.py
      roles/
        definitions.py
        contracts.py
        runner.py
      resources/
        evaluations.py
        trials.py
        mechanisms.py
        candidates.py
      intervention/
        prefix.py
        bridge.py
        worker.py
        trial.py
      mechanism/
        capabilities.py
        authoring.py
        review.py
      conformance.py
    versioning/
      contents.py
      candidate.py
      policy.py
      validation.py
      store.py
      journal.py
    experience/
      sets.py

  _internal/
    env.py
    concurrency.py
```

树中的文件名表示职责落点，不要求迁移开始时一次性创建所有空文件。只有承载当前
行为或被第一条垂直链路需要的模块才创建；例如 `experience/` 当前只需要 Experience
Set 的物化和加载，不预建尚无实现需求的 Experience Repository。

`framework/` 不得导入 Dataset、Evaluation、Evolution 或具体 Provider。外部
Provider 和 SDK 适配放入 `integrations/`，实现 framework 定义的 Model 或 Runner
协议。Git 驱动的 Template Version Store、Candidate Attempt、Promotion 和
Rejection 属于 Evolution 应用，保留在 `evolution/versioning/`，不进入可抽取
framework。

依赖方向固定为：

```text
cli -> evolution/evaluation/datasets/integrations -> framework
evolution -> evaluation/datasets/integrations/framework
evaluation -> datasets/integrations/framework
integrations -> framework
framework -> Python 标准库及必要的底层类型依赖
```

`evolution/research/` 可以依赖 Role Contract 与 framework 接口，但外部 Teacher
Harness Template 仍位于仓库资产目录，不进入代码包。`control/` 通过 Effect handler
调用 Research、Evaluation 与 Versioning 的应用接口，不从 Transition 代码直接导入
具体 Provider、Template Loader 或文件格式实现。

Evaluation 保持为 framework 之外的应用模块。它可以消费 framework 提供的
`RunResult`、Trace、Trajectory 与 Model usage，但评分标准、Dataset 绑定、聚合统计、
Teacher Judgment 和 Evaluation Report 都属于 `evaluation/`。framework 不定义任务
正确性，也不导入 Evaluation；Evolution 通过 Evaluation 的应用接口取得评估结果，
再由自身的 Promotion Gate 作出控制决策。

现有专用 Web Visualizer 不进入目标应用架构。其实现、静态资源和专用测试整体移入
`archive/visualizer/`，不保证与重写后的 V2 数据结构兼容；活动包不保留 Visualizer
入口或兼容 adapter。历史文档可以描述归档界面，但当前 V2 文档不得继续把它写成
受支持的运行能力。以后若需要新的观测界面，应作为只读外部工具消费稳定的 Trace、
Trajectory 和 Artifact，而不是进入 framework 或 Evolution Controller。

当前顶层 `runtime/` 不再作为领域模块保留。环境配置和通用并发辅助函数分别移入
明确的配置或内部辅助模块，避免占用已经定义的 `Runtime` 术语。

## Manifest 与 Evolution Policy

通用 Harness 运行协议不携带进化治理概念。Template Root 使用两个职责独立的
文件：

```text
<template_root>/
  harness.json
  evolution.json
  components/
```

`harness.json` 由 framework 读取，只声明 Component、entrypoint、Configuration
和启用状态。`evolution.json` 由 Evolution 应用读取，声明哪些 Component 允许由
Mechanism Compilation 修改。Teacher Harness Template 不参与进化时可以不提供
`evolution.json`；可进化的 Student Harness Template 必须由 Evolution 应用验证该
文件存在且与 Harness Manifest 一致。

Validation 相应拆分：

- `framework/harness/validation.py` 检查 Manifest schema、Component Loader、
  Harness Assembly 和 Lifecycle Contract；
- `evolution/versioning/validation.py` 检查 Parent Version 的 Evolution Policy、
  Candidate File Edit、父子差异及版本事务；
- Candidate Validation 组合上述两层结果，形成最终 Validation Report。

`HarnessAssembler` 和通用 `ComponentDeclaration` 不依赖 `EvolutionPolicy`。

外部模板目录相应规范化为：

```text
harness_templates/
  student/
    <template_id>/
      harness.json
      evolution.json
      components/
        prompts/
        outputs/
        tools/
        extensions/
  teacher/
    <role_template_id>/
      harness.json
      components/
        prompts/
        outputs/
        tools/
        extensions/
```

当前 `actor/` 机械改名为 `student/`，`plugins/` 机械改名为 `components/`。Student
模板增加与现有 `TaggedOutputParser` 等价的固定 Output Component；Teacher 模板增加
与当前 structured output/tool submission 等价的 Output Component。Teacher Manifest
删除 `role` 和 `output_contract` 字段，Evolution 应用配置负责 `role_id` 到
`template_root` 的选择，Role Definition 自身拥有 Output Contract。

上述迁移只允许修改目录、Manifest schema、factory signature 和必要 import。Prompt
正文、Tool 行为、Hook/Intervention 机制、Model Settings 与 Evolution Policy 的行为
含义必须保持不变；从 `harness.json` 提取到 `evolution.json` 的策略应逐项等价。

## Teacher Runner 收敛

目标架构保留两种真正不同的运行方式：

- framework 的通用 Agent Loop 与 OpenAI-compatible Model 组合，提供
  provider-neutral 执行；
- `integrations/` 中的 OpenAI Agents SDK Runner adapter，把同一通用 Harness
  组件适配为 SDK 对象。

`NativeChatRoleRunner` 已不再实现 Chat Completions 消息循环、Tool Call 分派、
结构化终态、transcript 与 usage 汇总；这些 provider-native 职责已归入角色无关的
`OpenAICompatibleToolRunner`。Role Runner 只保留 Role Contract、Role Resource、
Continuation 与 Role Artifact 应用职责。`AgentsSdkRoleRunner` 也已把 SDK Agent、Tool、
Model binding 与 `Runner.run` 委托给角色无关的 `AgentsSdkRunner`，自身保留相同的
Role 应用职责。

当前同步 `LoopRunner` 只支持文本 `Model.generate` 和 tagged tool call；原生 function
calling 则是异步消息循环。两者尚无经过验证的共同 `AgentRunner` 调用 Contract，因而
本阶段不通过扩宽 `Model`、把异步伪装成同步或改变 Teacher Tool 协议来强行合并。
先隔离 provider adapter 的事实边界，再基于 Student/Teacher parity 决定共同 Runner
接口，是当前最小迁移路径。

删除过渡 Runtime 前必须同时满足：

- Student Agent 保持现有 Prompt、Tool、Hook phase、最大步数、tagged output parser
  和 Final Output 行为，并通过定向回归及代表性 Rollout；
- Teacher Agent 通过相同 Role Contract、Role Continuation 和真实 API parity 测试；
- `ModelResponse` 只把 raw output、usage 和 metadata 纳入同一返回对象，不改变
  Student 当前看到的生成文本；
- 不为了统一概念而强制把同步 Student Agent Loop 改成异步。

## Agent、Harness 与 Runner

当前 `AgentLoop` 同时保存 Model 与 Harness 组件、创建运行状态并驱动循环。目标设计
把组合对象与执行机制分离：

```text
Harness Template --Harness Assembly--> Harness
Harness + Model ----------------------> Agent
Agent + Run Input ----Agent Runner----> Run Result
```

- `Harness` 是装配完成、可复用且不含单次运行状态的 Prompt、Tool、Output Parser、
  Extension 与 Lifecycle 组合对象；
- `HarnessInstance` 在一次 Agent Run 开始时创建，持有 Harness State 与 Extension
  State；
- `Agent` 只组合 Harness 与 Model；
- `LoopRunner` 是通过 Agent Loop 驱动 Harness Lifecycle 的通用 Agent Runner；
- Agent Loop 保留为角色无关的内部控制机制，不再同时充当 Agent 容器；
- 当前 `HarnessComponents` 被真正的 `Harness` 对象取代。

Student 和 Teacher 不建立各自的 Agent Loop 类型。二者通过不同 Harness、Model、
Run Input、Run Context 与 Output Contract 表达差异。

## Output Component 与可进化边界

Output 是 Harness 的正式 Component，与 Prompt、Tool、Extension 并列。它把
`ModelResponse` 转换为 `ParsedModelOutput`，识别 Tool Call、Final Output Candidate
和解析失败，并按稳定的 Output Contract 校验结果。Student 的 tagged output 与
Teacher 的 structured output 使用同一协议，可以分别采用不同 Output Component
实现。

Output Component 属于 Harness Template，因此在能力上可以成为自进化对象，但不会
因为被纳入 Harness 就自动可变。`evolution.json` 必须显式授权 Mechanism Compilation
修改具体 Output Component 或其配置；未授权时保持只读。

即使允许 Output Component 进化，Candidate Attempt 也只能改变解析、纠错、格式引导
等实现行为，必须继续满足同一个 Output Contract。Output Contract 是 Evaluation、
Controller 和下游消费者依赖的稳定接口；改变 Contract 属于显式架构或数据迁移，
不能伪装成一次普通 Harness 自进化候选。

## 实施策略

Normalization 在当前仓库和当前 Python 包内完成，不另建长期并行的新项目，也不对
现有目录做逐文件、逐名称的原地修补。新实现直接建立在已经确认的目标目录中，以
当前 V2 行为和测试证据作为迁移输入。

采用“选择性重写、垂直切换”的方式：

- 直接重写边界已经明确且当前重复严重的通用部分，包括 Agent/Harness framework、
  `ModelResponse`、Tool Execution、共享 Manifest/Assembly 和 Provider adapter；
- 保留并迁移已经形成有效领域语义的部分，包括 Evolution Controller 状态转换、
  Teacher Role Contract 与 Resource、Intervention/Evaluation 语义以及 Template Version
  Store；
- 最终删除 Teacher 专用 Manifest/Loader、过渡 `NativeChatRoleRunner`、旧
  `registry/`、旧 `runners/` 及只为旧命名存在的类型。

迁移按可运行的垂直链路推进，而不是先一次性搭完所有空接口：

1. 建立最小 framework 与 integrations 边界；
2. 迁移一条最小 Student Agent Run，并验证现有行为；
3. 接入 Dataset Evaluation；
4. 切换共享 Harness Manifest 与 Assembly；
5. 通过 SDK Runner 迁移一个 Teacher Role；
6. 迁移全部 Teacher Role、Role Continuation 与资源交接；
7. 接入 Evolution Controller effect、Candidate Attempt 与 Template Version Store；
8. 运行完整 V2 Evolution Run，随后删除被取代的旧目录。

## 当前实施进度（2026-08-02）

已完成第一组可运行垂直切换：

- `framework/agent/` 已承载角色无关的 `ModelResponse`、`Agent`、`Harness`、
  `HarnessInstance`、`LoopRunner` 与 Agent Loop；OpenAI-compatible Model 已移入
  `integrations/`，usage 不再通过 last-call side channel 传递；
- Tool Execution、Lifecycle State、Tagged Output 与 Trajectory 已进入 framework，
  `core/` 中对应文件仅保留单向迁移入口；
- framework 已提供唯一的 `HarnessManifest`、`ComponentDeclaration`、
  `ComponentLoader` 与共享 Component Assembly，Manifest 明确要求 Prompt、Output、
  Tool 和 Extension 四类声明且拒绝 `evolution_policy`；
- `harness_templates/student/baseline/` 已采用 `harness.json + evolution.json +
  components/`，并把原 tagged parser 物化为固定 Output Component；默认单次 Student
  Run 已切换到该模板；
- 9 个 Teacher Harness Template 已全部改为同一 Manifest 和 `components/` 结构，Role
  Definition 与 Output Contract 由调用方绑定；旧 `TeacherAgentManifest`、专用解析器及
  `teacher/*/plugins` 已删除；
- 正式 Controller、standalone research cycle、Teacher CLI、Native Chat Role Runner、
  Agents SDK Role Runner 和专用 Intervention Worker 均已接入共享 Teacher
  Assembly。

第一批验证包括当时的 125 项全量单元测试、一次真实 Student Run，以及三种真实
Teacher 路径：Failure Analyst 的多轮证据工具循环、Conformance Reviewer 的结构化终态
提交、Intervention Worker 的真实 Teacher/Student 分支。第二批又完成以下切换：

- `versioning` 已提供独立 `EvolutionPolicy` 解析；Candidate Workspace 新增 Extension
  时同时事务化修改 `harness.json`、`evolution.json` 与 `components/extensions/`；
- Candidate Validation 已改用共享 Manifest/Assembly，并分别校验装配声明、演化策略
  覆盖、固定边界、Component 目录归属和 Hook Contract；
- Template Version Store 的活动树由 `plugins/` 改为 `template/`，公开属性改为
  `template_dir`，不保留 `plugins_dir` 别名；
- 本机 `search_actor` Checkpoint Store 的两个 accepted 版本已逐版本迁移到
  `search_student`，保留版本号、摘要、评估元数据和 accepted iteration ID；旧 Git
  历史位于新 store 的 `archive/layout-v1` 分支，旧 iteration journal 只读归档，不把
  旧 digest 的 pending 事务带入活跃 journal；
- Student Runner 的旧 Manifest 分支、旧 `registry/` 实现及测试、
  `harness_templates/actor/` 已删除；只读 topology projection 已进入
  `framework/harness/topology.py`；
- 单次运行入口已由 `run_actor_once` 改为角色无关的 `run_agent_once`，直接输入改为
  `--template-root`，Dataset Harness 来源字段同步使用 `template_root`；
- Compiler authoring/capability packet 已升至 v5，明确把 Assembly 声明写入
  `harness.json`、把 mutable 策略写入 `evolution.json`。

第二批验证包括迁移后 accepted checkpoint 的真实 Student Run、真实 Compiler 的 8 次
Teacher API 请求和候选提交，以及删除旧 registry 后的 119 项全量剩余测试。Compiler
在入口命名规范化前，该次 Compiler 实际生成
`components/extensions/defer_first/plugin.py`，分别更新 Manifest 与 Evolution Policy，
并通过确定性 Validator。该路径只记录当时事实，不是当前 Component Factory 的命名
规范。真实验证只证明运行边界可用，不据单次结果声称角色行为稳定或准确率提升。

第三批已完成以下接口与术语规范化：

- 活跃源码、Student Template 与 Teacher Template 中的 `Actor` 术语已统一为
  `Student`；Teacher 工具和角色协议使用 `get_student_trajectory`、
  `next_student_action` 等名称；
- 运行与资源配置统一使用 `student_template_root`、`student_max_steps` 以及
  `parent/incumbent/candidate_template_root`，不保留旧字段兼容；
- 活跃 Template 的 Component Factory 文件统一为 `component.py`，Manifest 入口与
  Candidate Workspace 默认入口同步改为 `component.py:build`；历史实验 Template 和
  已接受 Template Version 不被静默改写；
- Compiler authoring guide、工具参数说明和错误信息统一使用 Component、Component
  Factory 与 Template Root；因默认文件名和 authoring packet 字段发生不兼容变更，
  authoring guide 与 capability packet 同步升至 v6；
- 三份仍指向已删除目录的 Compiler 矩阵实验入口已切换到现行 Student/Teacher
  Template Root，其中语义 smoke 使用共享 Component Assembly，不再导入已删除的
  `registry`；
- `models.openai_compatible` 迁移期转发层及 `OpenAICompatibleTextModel` 旧别名已删除，
  实验与运行代码直接使用 `integrations.openai_compatible.OpenAICompatibleModel`；
  `models` 暂只保留仍有独立职责的 `ProfiledHookModelBackend`。

第三批验证包括 119 项全量可发现单元测试、32 项 Evaluation/Controller/Intervention
定向测试、全仓 Python 编译检查，以及同一输入并行 3 次真实 Hypothesis Researcher
运行。三次均调用 `get_student_trajectory` 并提交有效的
`intervention_hypothesis@3`；一次选择 `post_tool`、两次选择 `pre_final`，因此只确认
新协议和真实链路可用，不声称 Teacher 判断稳定。另一次真实 Compiler v6 运行读取
capability packet v6，生成
`components/extensions/pre_final_defer/component.py`，分别更新 `harness.json` 与
`evolution.json`，并通过确定性 Candidate Validator。

第四批完成了 framework 公开边界及迁移壳清理：

- `search_harness.framework` 成为 Component Factory 与角色无关 Agent 运行的稳定公开
  导入面；Hook authoring API、guide 与 Compiler capability packet 升至 v7，公开
  `HookContext.trajectory` 与 `TrajectoryEvent`；
- Student 单次运行、Dataset Rollout、Evaluation Controller 与两条 Intervention
  分支运行路径均改为显式组合 `Harness + Model = Agent`，再交给 `LoopRunner`，不再以
  旧 `AgentLoop` 构造器隐式装配 Harness；
- 非 Visualizer 的活动源码、Template 与测试均已脱离 `search_harness.core`，旧
  `core/` 迁移壳和 `tests/core/` 已删除；Agent Loop 作为 framework 内部、角色无关的
  驱动机制继续保留；
- 顶层 `runtime/` 已按既定设计拆为 `_internal/env.py` 与
  `_internal/concurrency.py`；顶层 `models/` 的唯一剩余实现
  `ProfiledHookModelBackend` 已归入 `integrations/openai_compatible/`；
- Teacher 两种执行路径已共享角色无关的 `ToolCallCollector` 与
  `OutputCollector`，Continuation checkpoint 使用既定的 `RoleSession` 与
  `RoleContinuation` 术语，不再把短生命周期 Collector 命名为 Session；
- Template Versioning 已从顶层 `versioning/` 归入
  `evolution/versioning/`，Controller、Compiler、Rollout 与测试均直接依赖新的事实
  所有者位置，不保留旧 import facade；
- Experience Set 已归入 `evolution/experience/sets.py`，Mechanism Conformance 逻辑已
  进入 `evolution/research/conformance.py`；framework 内旧 `tooling/` 转发层和
  `prompting/renderers/` 多余层级已删除；
- 新增 architecture test，确定性阻止 framework 反向导入 Dataset、Evaluation、
  Evolution、Integration 或 Teacher 应用模块。
- 为避免把内部术语规范化伪装成持久化格式迁移，当前仍保留 `RunResult.trace` 与既有
  rollout JSON 的 `trace` 字段；新 Hook 运行接口已使用 `trajectory`。若以后修改持久化
  字段，必须单独定义 Artifact schema 迁移。

第四批验证包括非 Visualizer 活动源码与 Template 的编译检查、208 项非 Visualizer
单元测试，以及一次真实 Compiler v7 运行。真实 Compiler 发起 7 次 Teacher API 请求，
读取新版公开能力，生成 `components/extensions/defer_once/component.py`，更新
`harness.json` 与 `evolution.json`，并通过确定性 Candidate Validator。该验证只证明
公开接口、真实角色链路与候选事务可用，不声称机制效果或 Teacher 判断稳定。

第五批完成 Evolution Research 应用边界与 Role Runner 命名收敛：

- 原顶层 `teacher/` 活跃实现已按职责直接迁入 `evolution/research/roles/`、
  `resources/`、`intervention/` 与 `mechanism/`，不保留 import compatibility facade；
- 两条普通 Teacher Role 执行路径共享 `prepare_role_run`、输出 Contract 校验和 Role
  Artifact 构建，避免 SDK 与原生 Chat 路径继续复制应用协议；
- 新增角色无关的 `RoleRunner` 协议；实现命名统一为 `AgentsSdkRoleRunner`、
  `NativeChatRoleRunner` 与 `InterventionRoleRunner`，Controller 和独立 Research Cycle
  不再把完整 Role 执行边界称为 Runtime；
- Research 测试目录镜像新的源码职责；同时为仓库原有 `research/` 忽略规则增加精确
  例外，确保正式源码与测试可被版本控制，而不放宽其他 Research Artifact 的忽略范围。

第五批验证包括 85 项 Evolution Research 测试、三个受改名影响的 Controller 定向
回归，以及一次真实 Compiler Role Run。真实运行经
`evolution.research.cli -> NativeChatRoleRunner` 完成 `compiler@1`，输出 `submitted`，
执行 9 次工具调用并产生 1 个资源制品。非 Visualizer 的 208 项回归中，其余 205 项
通过；三个失败均由测试仍向旧 `effects.runtime` 属性注入 fake 引起，改用
`effects.role_runner` 后三个原失败用例全部通过。

第六批开始拆分 Evolution Control Effect 边界：

- Candidate 的 stage、promote、reject 事务已从单体 `LocalControlEffects` 提取为
  `CandidateVersionEffects`；新边界只依赖 Version Store 和确定性的 Candidate
  生命周期输入，不导入 Teacher Role、Evaluation 或 Conformance；
- `LocalControlEffects` 保留 WorkItem 到应用输入的映射和 dispatcher，Candidate
  事务行为、幂等规则、Validation、Promotion Receipt 与 Rejection Evidence 保持不变；
- Candidate Conformance 已提取为 `ConformanceEffects`，独立负责 Candidate replay、
  并发 Conformance Reviewer、finding 校验和聚合、缺失/失败 replay 投影及 token 统计；
- Incumbent 与 Candidate Evaluation 已提取为 `EvaluationEffects`，两者共享同一个
  Experience Set 和结果投影，Candidate Artifact 的选择仍由 Controller 映射层负责；
- Trial prefix 选择和 Intervention Worker 分支执行已提取为 `InterventionEffects`；
  注册的 Trial Objective 仍严格使用 `primary_signal | success_condition | falsifier |
  prior_obligation`，没有用新的自然语言概括替换既有协议输入；
- Trial Reviewer 与 Evidence Reviewer 已提取为 `EvidenceReviewEffects`，保持先逐条审阅、
  再聚合审阅以及恢复时复用已持久化且与冻结假设匹配的 Trial Review；
- Failure Analyst、Hypothesis Researcher/Continuation、Mechanism Distiller、Compiler 与
  Candidate Reviewer 已提取为 `ResearchRoleEffects`；该边界拥有 Role Contract、Role
  Resource 和 Role Artifact，不拥有 Controller transition 或 promotion 决策；
- 修正 standalone Research Revision Cycle 将包目录误作仓库根目录的问题，并增加默认
  Teacher Template 存在性测试；单角色 CLI 的 Template 与 Request 参数改为显式必填；
- `LocalControlEffects` 的角色数量说明从历史遗留的八个修正为当前九个角色。

本批确定性验证包括 86 项 Evolution Research 测试，以及 13 项 Evaluation、
Conformance、Intervention、Evidence Review、Research Role、Candidate Version 与
Controller 定向回归；Candidate
完成事务重试、三次独立 Conformance Review、Trial Objective 和共享 Experience Set
均有明确断言。没有启动模型调用或完整 Evolution Run。单体 `effects.py` 已由 1430 行
降至 637 行，当前只保留 WorkItem 解析、应用输入映射、Effect 构造与 dispatcher，不再
直接执行 Teacher Role、Evaluation Backend 或 Version Store 生命周期事务。

第七批随后开始收敛 provider-native 与 SDK Agent 执行边界，第八批建立新的根 CLI。
Visualizer 按用户当前要求暂时排除，不在本批读取、修改或验证；以上工作仍不得改变
Template 行为文本、Teacher Role 机制或 Evolution 策略。

第七批开始收敛 provider-native Agent 执行边界：

- 新增角色无关的 `OpenAICompatibleToolRunner`，负责异步 Chat Completions 请求、
  provider-native Tool schema、Tool Call 执行、终态提交、transcript 和 usage；
- `NativeChatRoleRunner` 改为委托上述集成层，只拥有 Role 准备、Resource、
  Continuation、Output Contract 校验和 Role Artifact 构建；
- 终态 Tool 的描述及未提交终态时的反馈仍由 Role Runner 原样提供，因此抽取未修改
  模型可见的 Teacher 行为文本；
- 没有把现有同步 `LoopRunner` 扩展为未经验证的同步/异步混合接口，也没有声称
  provider-native Tool Runner 已经等同于最终通用 `AgentRunner`；
- 新增角色无关的 `AgentsSdkRunner`，负责 SDK Agent、Function Tool、Model binding、
  结构化终态、usage 与 transcript；`AgentsSdkRoleRunner` 不再直接导入 SDK transport
  或实现 SDK Tool adapter。

最终收尾进一步删除了只覆盖同步 `LoopRunner` 的 `AgentRunner` Protocol。Agent Runner
继续作为统一职责术语；`LoopRunner`、`OpenAICompatibleToolRunner` 与
`AgentsSdkRunner` 保留与各自输入、结果和同步模型一致的明确调用接口。只有未来出现
真实可替换调用方时，才从共同用例中提取共享 Protocol。

standalone `ResearchRevisionCycle` 及其独立 workflow、参数解析和测试也已删除。正式
研究闭环只由 Evolution Controller 编排；Controller 仍需要的确定性 Trial Evidence
聚合已迁入 `evolution/research/evidence.py`，不再依附第二套 workflow。历史
`manual_v2/` 对 standalone Cycle 的说明按归档约定保留，不代表当前公共实现。

本批验证包括 12 项 Integration 测试、86 项 Evolution Research
测试和 23 项受影响的 Research Effect、Conformance 与 Controller 回归。没有调用真实
模型，也没有运行完整 Evolution；本批只验证边界抽取与既有离线行为一致。

第八批建立统一公共命令入口：

- 新增 `python -m search_harness` 根入口，提供 `run`、`evaluate`、
  `evolve start|resume` 与 `template validate`；
- 根命令只分派到既有应用函数；`template validate` 调用共享 Assembly，不实现另一套
  Template Loader 或 Validator；
- `run`、`evaluate` 与 Evolution Controller 的解析函数改为接收显式 argv，便于根命令
  组合和离线测试；
- 非 Visualizer 子模块的 `python -m ...` 入口已移除，应用函数仍供根命令和测试调用。

本批已验证根帮助、各命令帮助、Student Template Assembly 和 4 项 CLI/Agent Runner
定向测试；未执行 Student 模型请求或 Evolution Run。

本阶段最终验收补充如下：

- 非 Visualizer 的 224 项测试全部通过，其中 Evolution 133 项、其余 91 项；非
  Visualizer 活跃源码编译通过，旧
  `core/teacher/models/registry/runtime/versioning` import、旧 Actor Runner、非根
  `__main__` 与 Role 层 transport import 扫描均无残留；
- 真实 Compiler smoke 经 `NativeChatRoleRunner -> OpenAICompatibleToolRunner` 完成
  `compiler@1`：8 次模型请求、11 次 Tool Call、76,756 token，生成的 Candidate
  通过确定性 Validation；
- 使用迁移前旧 Version Store 启动时，Controller 在模型调用前因
  `harness_v0001` digest 不匹配而暂停；该 Store 未被修改。随后从当前 Student
  Template 初始化隔离 Store，版本完整性检查通过；
- 第一条 6 样本真实 Evolution Run 完成 incumbent evaluation、Failure Analyst、
  Hypothesis Researcher、两次 assignment、一次有效 Trial 与 Evidence Review，最终因
  assignment budget 耗尽正常结束；第二次 assignment 是 `unsuitable_assignment`，没有
  跳过尚未审阅的有效 Trial；
- 第二条 6 样本真实 Evolution Run 覆盖 13 个 Work Item，完成 Research、Intervention、
  Evidence Review、Distillation、Compilation、Candidate Stage、三次 Conformance
  Review、Candidate Evaluation、Candidate Review、Promotion Gate 与 Version Store
  提交；总计 1,037,232 token，最终接受 `harness_v0002`；
- 该 Run 的 incumbent 与 candidate 已评分 accuracy 均为 `1.0`；candidate 总 token
  从 `12,375` 增至 `24,813`，Conformance 为 `pass`，Candidate Reviewer 建议
  `accept`，确定性门禁随后允许晋升。此结果只证明闭环与决策边界可运行，不声称新
  Template 已在广泛数据上证明更优。

真实 Run 生成的 Candidate 只存在于隔离 Template Version Store；本次代码重构没有把该
Candidate 的 Template 修改合并回仓库基线。

最终公共命名统一为 `TemplateVersionStore`、`version_store`、`version_store_id` 与
`--version-store`，根 CLI 新增 `version-store init`。新初始化 Store 只写
`version_store.json` schema v2，新 Evolution Run 只写 `run.json` schema v2；既有
schema v1 Run 与 `checkpoint.json` 只在专用读取迁移器中识别，不作为新产物或领域接口
继续传播。该持久化决策记录于 ADR 0002。

Batch Rollout 已从旧 Runner 目录迁入 `evaluation/rollouts.py`，并移除不再公开的独立
参数解析和 `main`。它现在是 Evaluation 应用服务；统一根 CLI 与 Evolution Controller
按需组合该服务。静态扫描确认旧 `run_dataset` 名称无活跃引用。后续新建 Version Store、
Evolution Run 和 rollout Harness Source 只生成 `version_store` 系列名称；旧名称仅保留
在 schema v1 读取器、迁移测试及历史说明中。

Candidate Attempt 术语也已落实到 Version Store、Controller、Evaluation 与新运行产物：
公开类型使用 `CandidateAttempt`、`CandidateAttemptState`、`CandidateAttemptEvent` 和
`CandidateAttemptJournal`，稳定引用统一为 `candidate_attempt_id`。新 Version Store 只写
`candidate_attempts.jsonl` schema v2；旧 `iterations.jsonl`、Version Record、Control
Event 与 Effect Artifact 中的 `iteration_id` 仅在持久化读取边界中迁移，不提供活动接口
别名，也不重写历史文件。该决策记录于 ADR 0003。

真实 Failure Analyst 验证还观察到语义输出可能在 caveat 中带入案例标识；这是既有
Prompt/角色语义校验问题，不属于结构迁移，当前按行为冻结要求保留证据而未修改。

迁移期不建立长期 import compatibility layer。确有需要的临时 adapter 只能单向依赖
新 framework，必须有明确删除点，并在 Normalization 完成前移除。新 framework
不得反向导入旧实现。

## 现有模块迁移映射

| 当前位置 | 目标位置或处理方式 |
| --- | --- |
| `core/protocols.py`、`types.py`、`loop.py` | 拆入 `framework/agent/`；以 `Model`、`ModelResponse`、`Agent`、`RunResult` 和 `LoopRunner` 替换当前混合接口 |
| `core/hooks.py`、`hook_state.py` | 迁入 `framework/harness/lifecycle.py` 与 `state.py`，保持现有 phase 和 state access 行为 |
| `core/parser.py` | 迁为 Student tagged `OutputComponent`，解析行为不变 |
| `core/tools.py` 与 `framework/tooling/` | 合并到 `framework/tools/definitions.py` 和 `execution.py` |
| `core/trace.py` 与 Trace/Trajectory 数据 | 迁入 `framework/trajectory/`，区分观测 Span/Event 与行为 Trajectory Event |
| `registry/manifest.py`、`assembler.py`、`plugin_importer.py` | 以共享 `framework/harness/manifest.py`、`assembly.py`、`ComponentLoader` 重写 |
| `registry/topology.py` | 迁为只读 `framework/harness/inspection.py`；不因此建立 Registry |
| `models/openai_compatible.py` | 迁入 `integrations/openai_compatible/`，返回完整 `ModelResponse` |
| `models/hook_backend.py` | 用通用 Model Provider 和 Component Factory Context 重组，不保留 Hook 专用模型协议旁路 |
| `runners/run_actor_once.py` | 删除 Actor CLI；单次 Agent 组装由根 CLI 调用通用 Assembly 与 Runner |
| `runners/run_dataset.py` | Batch Rollout 迁入 `evaluation/rollouts.py`；Version Source 解析交回 Evolution Versioning |
| `runtime/env.py`、`concurrency.py`、`paths.py` | 移入 CLI composition 或 `_internal/`；不得被包装成公共 Runtime domain |
| `teacher/contracts.py` | 迁入 `evolution/research/roles/contracts.py` 与 `definitions.py`，保持 schema 和版本行为 |
| `teacher/manifest.py`、`loader.py`、`spec.py` | 被共享 Manifest/Assembly 与 Role Runner 取代，迁移完成后删除 |
| `teacher/runtime.py` | 已迁为 `evolution/research/roles/agents_sdk_runner.py`；Role 验证与资源准备已共享，SDK 调用保留其真实异步接口 |
| `teacher/native_runtime.py` | Role 应用职责已迁入 `evolution/research/roles/native_chat_runner.py`，provider-native 循环已迁入 `integrations/openai_compatible/tool_runner.py`；两条路径在具备真实可替换关系前不建立共同 Runner Protocol |
| `teacher/resources.py`、`role_resources.py`、`builtin_tools.py` | 按 Evaluation、Trial、Mechanism、Candidate 事实所有者拆入 `evolution/research/resources/` 与 `tools.py` |
| `teacher/_intervention/`、`intervention_runtime.py` | 迁入 `evolution/research/intervention/`，保留 prefix、branch、activation 和 trial 语义 |
| `teacher/compiler_*`、`hook_api.py`、`hook_authoring.py` | 迁入 `evolution/research/mechanism/`，保持 Compiler capability 与安全审查语义 |
| `teacher/research_cycle.py` | Controller 使用的 evidence aggregation 迁入 Research；独立 workflow 与 CLI 删除 |
| `evolution/control/` | 保留 domain/controller/transitions/policies/journal；将单体 `effects.py` 按外部职责拆分 |
| `evolution/conformance.py` | 迁入 `evolution/research/conformance.py` |
| `evolution/experience.py` | 迁入最小 `evolution/experience/sets.py`，不预建经验检索框架 |
| `versioning/` | 整体迁入 `evolution/versioning/`；拆分 framework validation 与 evolution validation，并把 Iteration 命名改为 Candidate Attempt |
| `evaluation/`、`datasets/` | 保持应用级兄弟包；移除 env/CLI 反向耦合并改用通用 Run Result |
| `visualizer/` 及其 tests | 按明确范围暂时排除；后续作为独立历史程序归档，不要求与当前主体兼容 |

测试目录已镜像目标代码边界，并包含只检查依赖方向和公共入口的 architecture tests。
模板测试继续独立验证 Manifest、Assembly 和既有 Prompt/Tool/Hook 行为；不得
把模型准确率断言写成 framework 单元测试。

## 公共命令入口

当前已建立一个轻量的统一根 CLI，作为唯一受支持的公共命令入口：

```text
python -m search_harness run ...
python -m search_harness evaluate ...
python -m search_harness evolve start|resume ...
python -m search_harness template validate ...
python -m search_harness version-store init ...
```

根 CLI 只负责参数解析、配置装载、错误呈现和调用对应应用服务，不实现 Agent Loop、
Evaluation、Evolution Control 或 Version Store 业务逻辑。Teacher Role、Versioning、
Evaluation 和旧 `runners/` 不再各自提供受支持的公共入口。必要的开发诊断命令放入
`scripts/`，明确视为内部工具而非公共 CLI Contract。

这些命令已经直接组合迁移后的应用服务，没有为旧模块建立兼容转发层。

## 文档分层与本次范围

目标文档结构按职责分层：

```text
docs/
  README.md
  architecture/
  reference/
  guides/
  research/
  adr/
  manual_v1/
  manual_v2/
```

- `architecture/` 只描述已确认的目标架构与边界；
- `reference/` 只描述当前实现的接口、配置和数据格式；
- `guides/` 保存面向使用与维护流程的操作说明；
- `research/` 保存实验、审计、候选方案和未采纳结论；
- `adr/` 保存已经生效且需要长期追溯的架构决策；
- `manual_v1/` 与 `manual_v2/` 都作为对应历史版本的独立档案保留。

本次代码重构不把 `manual_v2/` 正文迁移、复制或改写到新结构中，也不借重构机会
补写完整的新文档。新文档目录只建立导航骨架、预定标题和状态说明；正文撰写作为
后续独立任务。`manual_v1/` 正文同样保持不变，并继续保留醒目的历史档案标记。

## 迁移验收门

迁移以代码正确性、边界正确性和现有 V2 行为保持为目标，采用四级门禁：

1. 每完成一条垂直迁移链路，运行对应单元测试、Contract Test 和 import-boundary
   检查；
2. 验证 Student Lifecycle、Tool、Hook、Output 行为，以及全部 Teacher Role
   Contract 与 Role Continuation；随机模型输出不要求逐字一致；
3. 使用真实 Teacher API 完成至少一次 V2 Evolution Run，验证 Candidate Attempt
   创建、Evaluation、Review 以及接受或拒绝终态；另一条 Promotion 分支由确定性测试
   覆盖；
4. 删除旧实现前运行完整剩余测试集、代表性 Student Evaluation、真实 API smoke 和
   残留扫描，确认旧目录、旧 import、临时 adapter 与旧公共入口已经消失。历史档案
   中的旧术语不计为运行时代码残留。

Normalization 不以提升任务准确率作为验收条件，但不得出现可归因于重构的行为、
Contract 或 Evaluation 退化。未经单独明确授权，不得为改善运行效果修改 Harness
Template、Prompt、Teacher Role 机制、Evolution Policy 或其他进化策略；这些资产在
本阶段作为行为基线输入，而不是优化对象。
