# V1 Historical Archive

> **归档目录：本文档集不描述主分支当前实现，其中的命令、路径和接口不保证可用。**

本目录原样保留 V1 工程文档正文，仅用于追溯历史设计和行为。V1 最后一个完整
可运行源码版本位于 Git 分支 `archive/v1-final`，对应提交 `63c094c`。主分支不
保留 V1 可执行代码、模板、测试、命令入口或兼容层。

唯一保留的完整 V1 run 位于：

```text
runs/archive/v1/evolution/exp_03
```

该 run 未重写内部旧绝对路径；使用前需自行核实 provenance。当前实现文档请阅读
[`docs/manual_v2/`](../manual_v2/README.md)。目录级标记另见
[`_ARCHIVED_V1.md`](_ARCHIVED_V1.md)。

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
