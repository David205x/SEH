# 开发路线

本文只记录当前阶段顺序，不承诺具体日期。已落地接口和运行方式以 `../manual/` 为准。

## 已完成的基础能力

1. Actor core loop、结构化消息、串行工具调用和 Hook 生命周期。
2. 外部 plugins root、manifest、fixed/mutable 边界和动态装配。
3. 数据集 rollout、重复采样、静态与 Teacher evaluation。
4. Git-backed Harness Checkpoint Store 与 iteration journal。
5. Critic、Intervention Coordinator/Worker、Compiler 和线性 Evolution Runner MVP。

## 当前工程加固

1. 绑定 evaluation report 与 source rollout digest，并补齐 artifact provenance 校验。
2. 固定 Evolution iteration 的 parent 和语义配置，明确可覆盖的恢复参数。
3. 加固 Version Store 的提交恢复、journal 尾部损坏处理和孤立 transaction 对账。
4. 将 Coordinator 的选中方案与跨案例正向 trial 做强绑定。
5. 补齐独立 CLI smoke、依赖声明、静态检查和运行产物清理规则。

## 后续研究方向

1. 在失败方向之间进行有界回退，而不只处理最高优先级方向。
2. 比较 Intervention 中教师指导与最终学生 Hook 实现的迁移一致性。
3. 引入独立 validation split，降低 Experience Set 上反复迭代造成的过拟合。
4. 在证据充分后再扩展长期 memory、更多 intervention 分支和候选搜索策略。
