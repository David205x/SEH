# Search Harness 设计记录

本目录同时保存当前设计状态与历史研究记录。旧专题正文可能描述 Actor、Critic、
Coordinator、Adapter Harness 或线性 Evolution Runner；这些名称只代表当时的研究阶段，
不得覆盖当前统一术语和活动实现。

## 当前入口

1. [Post-removal Normalization](post-removal-normalization.md)：当前已确认架构、迁移结果与验收。
2. [治理与审计](governance.md)：当前权限和确定性决策边界。
3. [开发路线](roadmap.md)：已完成工程状态与后续独立任务。
4. [未决事项](open-decisions.md)：不阻塞当前主体的未来研究问题。
5. 仓库根目录 `CONTEXT.md`：统一术语。
6. `docs/adr/`：已生效且需要追溯的架构决策。

其余文件作为研究、实验和迁移来源保留，不批量改写历史正文。新架构、参考和操作文档
将在 `docs/architecture/`、`docs/reference/` 与 `docs/guides/` 中以独立任务撰写。
