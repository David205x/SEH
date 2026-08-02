# Candidate Attempt 术语与持久化格式统一

领域词汇已经明确用 Candidate Attempt 表示一次候选模板的事务性暂存、验证及接受或拒绝过程，因此活动类型、接口和新产物统一使用 `CandidateAttempt` 与 `candidate_attempt_id`，新 Journal 写入 `candidate_attempts.jsonl` schema v2。为保留既有 Version Store 和 Evolution Run 的 durable resume，读取边界继续识别 `iterations.jsonl`、schema v1 `iteration_id`、旧 Version Record、Control Event 和 Effect Artifact，但不提供旧接口别名、不重写历史文件，也不再生成旧名称。
