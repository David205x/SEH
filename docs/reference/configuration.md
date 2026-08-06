# 配置 Reference

非敏感运行参数统一保存在 UTF-8 YAML 文件 `config/runtime.yaml`；`.env` 只保存
API Key。默认配置文件相对当前 `.env` 所在目录解析，因此项目根 `.env` 对应项目根
`config/runtime.yaml`。进程环境变量仍可作为临时覆盖层，但不应把非敏感参数重新写回
`.env`。

`runtime.yaml` 使用标准 YAML `#` 注释；当前只为本项目特有或语义不直观的参数保留就地短注释，通用模型、路径和并发字段不重复解释。

## 模型配置

`models.student`、`models.teacher` 与 `models.summary` 共享模型参数字段：

| 字段 | 必需 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `provider` | `summary` 必需 | — | Provider adapter；概要模型当前支持 `openai_compatible` |
| `credential_profile` | `summary` 否 | `summary` | 复用哪个 profile 的 API Key，例如 `teacher` |
| `base_url` | 是 | — | OpenAI-compatible API 根 URL |
| `model_id` | 是 | — | 模型 ID |
| `max_tokens` | 否 | `1024` | 该模型 profile 的默认单次输出预算 |
| `request_timeout` | 否 | `60` | 请求超时秒数 |
| `temperature` | 否 | `0.6` | 采样温度 |
| `seed` | 否 | 空 | 可选整数 seed |
| `thinking_mode` | 否 | 自动 | `enabled` 或 `disabled`；只向明确支持的 provider 发送扩展字段 |

API Key 从 `.env` 或进程环境读取，名称为 `STUDENT_API_KEY` 与
`TEACHER_API_KEY`。Hook model profile 继续使用 `<PROFILE>_API_KEY`；其非敏感模型
参数应放在 `models.<profile>`。

`models.summary` 供 Evolution Run 事件生成器的可选概要渲染使用。生成器的事件
身份、顺序、角色/机制分类和来源引用均由确定性投影产生；概要模型只改写已经生成的
简短 summary，不参与事件取舍或 Controller 路由。默认配置通过
`credential_profile: "teacher"` 复用 `TEACHER_API_KEY`，无需在 `.env` 中复制密钥。

## Evolution Timeline

`timeline` 控制 Evolution Controller 自动维护的 Experiment Observer 投影：

| 字段 | 默认值 | 说明 |
| --- | --- | --- |
| `enabled` | `true` | 在每次 Control Journal 成功提交后自动更新 `timeline/` |
| `model_summary` | `false` | 使用 `models.summary` 为新增语义条目生成概要 |

当前项目配置显式设置 `enabled: true` 与 `model_summary: true`，因此新启动或恢复的
Evolution Run 会自动生成两层投影并调用概要模型。

Timeline 是非决策性派生状态。投影错误会记录 warning 并在后续事件提交或 resume 时
再次对账，不会回滚 Control Journal、重复执行 WorkItem 或改变 Controller 路由。

## Evolution 运行超参数

Evolution 的预算、重试、并发和评估门限统一放在 `evolution.control` 与
`evolution.effects`。两个 section 都要求字段集合完整且精确：缺少字段或出现未知字段
都会在启动时失败，避免拼写错误被默认值掩盖。

### `evolution.control`

| 字段 | 说明 |
| --- | --- |
| `max_generations` | 一个 Run 最多推进的 Generation 数 |
| `max_trials_per_hypothesis` | 一个冻结 Hypothesis 最多允许产生的成功 Trial 数 |
| `max_trial_assignments` | 为得到 Trial 最多允许选择的 Assignment 数 |
| `max_hypothesis_revisions` | Hypothesis 的最大修改次数 |
| `max_mechanism_revisions` | Mechanism 的最大修改次数 |
| `max_compiler_revisions` | Compiler 输出的最大修改次数 |
| `max_candidate_revisions` | Candidate 的最大修改次数 |
| `max_work_retries` | 单个 WorkItem 失败后的最大重试次数 |
| `max_work_items` | 一个 Run 最多执行的 WorkItem 数 |
| `max_total_tokens` | Run 总 token 上限；`null` 表示不设置该上限 |
| `min_accuracy_delta` | Promotion Gate 允许的最低准确率变化 |
| `max_total_token_ratio` | Promotion Gate 允许的最大总 token 比率 |

`max_trial_assignments` 不得小于 `max_trials_per_hypothesis`。

### `evolution.effects`

| 字段 | 说明 |
| --- | --- |
| `student_max_steps` | 单次 Student Run 的最大步骤数 |
| `teacher_max_turns` | 缺少角色专用配置时的 Teacher Role Session 回合上限 |
| `rollout_workers` | Rollout 并发数 |
| `rollouts_per_example` | 每个样本的 Rollout 次数 |
| `judge_workers` | Judge 并发数 |
| `candidate_error_streak_limit` | Candidate 连续出现相同运行错误时提前停止评估的阈值 |

`evolve start` 和专用 research-to-candidate 实验入口在创建 Run 时读取这些值，并分别
冻结到 `run.json.control_config` 与 `run.json.effects_config`。`evolve resume` 只使用 Run
内已经冻结的值；修改全局配置不会静默改变进行中的实验。上述字段不再提供同名 CLI
参数，CLI 只保留数据选择和 `--no-teacher-judge`、`--no-progress` 等本次启动行为开关。

## Teacher Role 预算

`teacher_roles` 必须为每个活动 Teacher Role 独立声明：

```yaml
evidence_reviewer:
  max_tokens: 12288
  max_turns: 20
```

- `max_tokens`：该角色每次模型响应可使用的最大 token 数，会覆盖
  `models.teacher.max_tokens`。
- `max_turns`：一次角色调用在没有合法终态输出前最多允许的模型回合数。

当前活动角色为 `failure_analyst`、`hypothesis_researcher`、
`intervention_worker`、`trial_reviewer`、`evidence_reviewer`、
`mechanism_distiller`、`compiler`、`candidate_reviewer` 和
`conformance_reviewer`。Role Artifact 的 `role_budget` 记录实际采用的两项预算。

`evolution.effects.teacher_max_turns` 是缺少角色配置时的通用后备值；活动角色配置存在
时以 `teacher_roles.<role_id>.max_turns` 为准。

## 其他配置

| section | 字段 | 说明 |
| --- | --- | --- |
| `agent` | `max_steps` | 通用 Agent Run 默认最大步数 |
| `retriever` | `url`、`timeout`、`top_k` | 检索服务连接与返回规模 |
| `dataset` | `path`、`output_dir`、`file`、`jsonl_path` | 默认数据集定位 |
| `dataset` | `train_path`、`heldout_path` | 训练与留出数据路径 |
| `evaluation` | `workers`、`save_batch_size` | 评估并发与保存批量 |
| `timeouts` | `<profile>` | 特定旧入口的请求超时覆盖 |

结构化配置由公共读取层投影给尚未迁移接口使用；这只是配置来源兼容，不会把非敏感
值重新写入 `.env`。

## 路径约定

- 当前 Student Template：`harness_templates/student/baseline`
- 默认 Version Store：`harness_checkpoints/search_student`
- 运行产物根：`runs/`
- 单组件调试运行：`runs/components/<component>/<UTC timestamp>/`

Evolution Run 的 `--run-dir` 与 `--version-store` 应显式给出，避免把实验状态与组件
调试产物混在一起。
