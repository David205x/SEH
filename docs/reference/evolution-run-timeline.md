# Evolution Run 事件时间线

`evolution_observer.timeline` 将新格式 Evolution Run 的 Control Journal 投影为简洁、
可持续更新的行为时间线。它只支持 `run.json.schema_version = 2`，不读取或兼容 V1
产物。

Evolution Controller 的 `start` 与 `resume` 会按 `config/runtime.yaml` 的 `timeline`
配置自动挂载该投影。每批 Control Journal 事件完成持久化后立即增量更新，无需另行启动
命令；下面的手动命令仅用于重建、诊断或独立跟随已有 Run。

## 输出

生成器只写入 Run 自身的 `timeline/` 子目录：

```text
timeline/
  state.json       # 已消费的 Control Journal sequence 与投影计数
  entries.jsonl    # 语义时间线条目及其 Control Journal 来源关系
  summaries.jsonl  # 通过 entry_id 关联的确定性概要与可选模型概要
```

`entries.jsonl` 是 Experiment Observer 使用的数据源，不生成 Markdown 阅读报告。每个
条目的 `source_event_sequences` 保存它所依据的一条或多条 Control Journal sequence；
`source_refs` 保存相关 artifact。条目的身份、顺序、角色/机制分类、结论字段和来源
引用均由确定性代码生成。

`summaries.jsonl` 与 `entries.jsonl` 按稳定的 `entry_id` 关联，保存确定性 `summary`、
可选 `model_summary`、模型 provenance、usage 与失败信息。概要不是 Control Journal
逐行转述，也不改变语义条目或来源关系。
`work_started`、`work_transitioned` 等维护事件不会进入阅读时间线；角色完成/失败、
确定性机制完成、重试和 Run 状态变化会进入时间线。Evidence Review 的一次 Work
可依据新写入的 artifact 引用生成 Trial Reviewer 条目与一个 Evidence Reviewer 条目；
生成 Trial Reviewer 激活记录时不读取体积较大的完整角色 transcript，复用的旧 Trial
Review artifact 也不会被重复记为一次角色激活。

## 使用

生成一次当前投影：

```powershell
python -m evolution_observer.timeline update `
  --run-dir runs/evolution/<run-name>
```

持续跟随追加中的 Journal：

```powershell
python -m evolution_observer.timeline follow `
  --run-dir runs/evolution/<run-name> `
  --interval 2
```

使用 `--model-summary` 时，生成器从 `config/runtime.yaml` 的 `models.summary`
读取 provider 与生成参数。模型只接收已经投影出的简短事实并改写 summary；模型输出
和非敏感 provenance 会持久化在 `summaries.jsonl`。调用失败时保留确定性 summary，
并在 `summary_error` 中记录错误，不影响增量游标和后续事件生成。已有条目不会再次
调用模型。

`--rebuild` 会仅重建 `timeline/` 投影，不修改原始 Journal 和 artifact。
