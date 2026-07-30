# 工程手册

本目录记录维护 Search Harness 代码库所需的工程原则、当前代码说明和稳定接口约定。

与 `../design/` 的分工如下：

- `design/` 记录研究目标、系统设计、实验思路和待决问题。它用于指导架构方向，部分内容可以先于实现或与当前代码存在差异。
- `manual/` 记录已确认的工程原则和当前实现事实，用于维护、入门和代码变更时的快速核对。

当两者描述不一致时，不应静默假定设计已经落地：先确认当前任务是维护现状还是实施某项设计，再同步更新相应文档。

## 文档索引

- [Python 代码规范](python_style.md)
- [当前代码架构](current-codebase.md)
- [Artifact Layout](artifact-layout.md)
- [Harness Plugins](harness-plugins.md)
- [Harness Checkpoint Store](version-store.md)
- [Offline Evaluation](evaluation.md)
- [Read-only Critic Agent](critic-agent.md)
- [Standalone Compiler Agent](compiler-agent.md)
- [Standalone Intervention Worker 与 Coordinator](intervention-worker.md)
- [Evolution Runner](evolution_runner.md)
- [Evolution 主体数据流](evolution-dataflow.md)
- [工程稳定性修复备忘录](engineering-stability-backlog.md)

## 开发与验证入口

当前仓库尚未提供 `pyproject.toml`、lockfile 或独立依赖清单，开发环境以根目录
`AGENTS.md` 记录的 Conda Python 为准。标准测试入口为：

```powershell
& 'D:\ProgramData\miniconda3\envs\env_search_harness\python.exe' `
  -m unittest discover -s tests -v
```

基础语法检查可运行：

```powershell
& 'D:\ProgramData\miniconda3\envs\env_search_harness\python.exe' `
  -m compileall -q search_harness harness_templates
```

`tqdm` 是 rollout 与 evaluation 进度显示所需的运行时依赖。`ruff`、`mypy` 和 `pytest`
不是当前环境或仓库配置保证提供的工具；使用前应先确认环境。
