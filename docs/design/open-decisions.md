# 未决事项

Post-removal Normalization 主体没有尚未确认且会阻塞当前实现的架构决策。以下问题属于
未来研究，不作为当前代码的隐含 TODO：

1. 不同 Agent Runner 何时具备真实可替换的输入与 Result Contract，从而值得建立共同
   Protocol；在此之前保持 `LoopRunner`、provider-native Tool Runner 与 SDK Runner 的
   真实接口。
2. Research Experience 的最小有效内容、审查、版本绑定与跨 Evolution Run 检索策略；
   在证据充分前不预建通用长期 memory framework。
3. validation split、跨 Failure Direction 回退和多 Candidate 搜索如何避免对固定
   Evolution Set 过拟合。

新的未决事项必须说明影响边界与需要用户决定的具体问题；已确认结果应写入对应专题或
`docs/adr/`，不得长期留在本文件。
