# CLI Reference

根入口为：

```powershell
python -m search_harness <command>
```

| 命令 | 用途 |
| --- | --- |
| `run` | 执行一次 Agent Run |
| `evaluate` | 评估已有 Rollout JSONL |
| `evolve start` | 创建并执行新的 Evolution Run |
| `evolve resume` | 从持久化事件恢复 Evolution Run |
| `template validate` | 校验 Harness Template |
| `version-store init` | 从模板初始化 Template Version Store |

## `run`

```text
run [--env-file PATH] [--trace-file PATH] [--show-trace]
    [--model-role {student,teacher}] [--template-root PATH]
    QUESTION...
```

默认使用当前 Student Template（目录名为 `baseline`）和 `STUDENT_*` 模型配置。`--model-role` 只选择模型环境变量前缀，不把通用 Loop 变成角色专用实现。

## `evaluate`

```text
evaluate [--output-dir DIR] [--env-file PATH]
         [--teacher-judge] [--judge-workers N]
         INPUT_FILE
```

输入必须是 UTF-8 Rollout JSONL。`--teacher-judge` 为静态规则不能确定的项启用 `TEACHER_*` 二元判分。

## `evolve start`

必需参数是 `--run-dir` 和 `--version-store`。数据集可由 `--dataset-path`、可选
`--dataset-format` 指定；省略时使用运行时配置的数据集定位。CLI 还保留 `--limit`、
`--env-file`、`--no-teacher-judge` 与 `--no-progress`。

Generation、Trial、revision、work retry、work item、总 token、Promotion Gate、Student
步骤、Teacher 回合、Rollout/Judge 并发、重复 Rollout 数和 Candidate 错误熔断阈值均
从 `config/runtime.yaml` 的 `evolution.control` 或 `evolution.effects` 读取。新 Run 会将
实际配置冻结到 `run.json`，这些超参数不再提供同名 CLI 参数。

使用 `python -m search_harness evolve start --help` 获取完整参数与当前默认值。

## `evolve resume`

```text
evolve resume [--env-file PATH] [--no-progress] RUN_DIR
```

恢复时使用 `run.json` 中冻结的配置。只允许覆盖 `.env` 路径和进度显示；Version Store 稳定 ID 必须与 Run Artifact 匹配。

## 模板与版本存储

```text
template validate [--env-file PATH] TEMPLATE_ROOT
version-store init --template-root DIR --version-store DIR
                   [--env-file PATH] [--version-store-id ID] [--summary TEXT]
```

所有相对路径都相对于当前工作目录解析。项目约定在仓库根目录执行命令。
