# Manual v2

本目录记录当前版本的工程原则和稳定接口。`docs/manual_v1/` 仅用于追溯旧实现，新增代码以本目录为准。

- [Teacher 角色定义](teacher-roles.md)：Teacher 控制面的职责、模型输入与语义输出。
- [Teacher Runtime](teacher-runtime.md)：Teacher 角色模板、协议绑定和可替换运行后端。
- [证据驱动 Evolution](evidence-driven-evolution.md)：能力画像、评估契约、证据义务和 iteration 产物。
- [Evolution Controller](evolution-controller.md)：八角色正式闭环、事件议程、恢复、门禁和运行入口。
- [V1 实现清理记录](v1-implementation-cleanup-plan.md)：V1 归档基线、删除范围、语义脱钩和验收结果。
- [Evolution Controller 闭环验证](../design/evolution-controller-v2-validation.md)：真实大规模运行、恢复场景、候选拒绝与验证边界。
- [Compiler](compiler.md)：新版 Compiler 的输入输出、内存候选事务和完整工具协议。
- [Mechanism Conformance Replay](mechanism-conformance-replay.md)：Compiler 后、全量评估前的机制实现保真度回放草案。
- [Compiler 上下文优化](compiler-context-optimizations.md)：精简 prompt、程序化 finalizer 和源码驱动 capability packet 的上下文变化与实验结果。
- [框架机制设计](framework-mechanisms.md)：跨 Harness 的框架机制、公开 API 与稳定边界。
- [Harness 插件](harness-plugins.md)：Actor Harness 的插件结构与装配边界。
- [Version Store](version-store.md)：Harness checkpoint 和版本存储。
- [Python 规范](python_style.md)：项目代码风格与验证要求。
