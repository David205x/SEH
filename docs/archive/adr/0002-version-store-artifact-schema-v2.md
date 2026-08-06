# Version Store 术语与持久化格式统一

新的 Template Version Store 元数据和 Evolution Run Artifact 统一使用 `version_store` 术语及 schema v2，不再生成 `checkpoint_store` 字段或 `checkpoint.json`；源码和公共 CLI 同步使用 `TemplateVersionStore` 与 `--version-store`。为保留 durable resume，读取边界继续识别既有 schema v1 Run Artifact 和 `checkpoint.json`，但旧名称不得扩散回领域代码或新产物。
