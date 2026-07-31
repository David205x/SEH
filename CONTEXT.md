# Search Harness

本项目研究并运行由 Teacher 引导 Student Harness 自进化的闭环。

## Language

**V2 Active Implementation**:
当前唯一可执行的 Teacher 角色、Evolution Controller、模板、测试与命令入口。清理完成后，项目运行时只允许依赖这一实现。
_Avoid_: 新版、当前版

**V1 Historical Archive**:
只用于追溯旧设计与历史行为的文档和由 `runs/experiments/evolution/exp_03` 整体移入 `runs/archive/v1/evolution/exp_03` 的一份完整 V1 实验记录；不得跨 run 拼接，也不得包含可执行入口或被 V2 运行时依赖。归档 run 内的旧绝对路径允许失效，需要使用时再核实 provenance。`docs/manual_v1/` 只在目录层标记为 archive，并由目录 README 说明，不改写各篇历史正文。V2 实验记录不属于本次清理范围。
_Avoid_: V1 implementation、legacy compatibility layer

**Semantic Detachment**:
仅重建 V2 当前实际使用的行为语义，使 V2 不再依赖 V1 实现；不在这一阶段决定全项目最终接口、名称或扩展架构。
_Avoid_: V1 module migration、compatibility rewrite

**Post-removal Normalization**:
V1 实现完全删除后开展的独立整理阶段，用于统一仍存模块的接口与名称；具体方案不属于 V1 清理阶段的预设结论。
_Avoid_: cleanup prerequisite、V1 compatibility
