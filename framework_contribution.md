# openJiuwen / JiuwenSwarm 框架贡献

本作品直接修改 JiuwenSwarm 官方源码，固定开发基线为 `f0a69728c96b5961d993449f1a901cbd2f4dac5b`。十二层补丁及源文件清单位于 `code/patches/source-identity.json` 和 `code/framework-source-manifest.json`，交付源码已包含全部改动。

贡献包括五项确定性产物完整性检查及 PaperProvider 集成、冻结 PreparedCode 输入、请求级暂停与截止控制、费用预留持久化、Worker 终态提交，以及 Reporting 的结构和事实约束。事实约束要求区分配置模块与实际执行模块、输入 Token 与输出或计算量控制、共享初始正确回答与真正的配对差，并禁止凭相同 p 值推断统计量没有重算。门禁检查产物结构，不代替科学真值验证。

已实际更新 [PR #7722](https://gitcode.com/openJiuwen/jiuwenswarm/pull/7722)。正常追加提交为 [dae143d9ac19cb5e05864d459b8cd89de96de908](https://gitcode.com/ShiChenhao0801/jiuwenswarm/commit/dae143d9ac19cb5e05864d459b8cd89de96de908)，Git tree 为 `e8e39118469a369717871cd8d7544defb39c6045`。发布树全部 4,925 个文件与交付候选身份一致：4,603 个 UTF-8 文本按 LF 一致，322 个二进制原始字节一致。

独立完整 RSI 回归包含 444 个唯一用例：442 PASS、2 项 Windows 符号链接权限 SKIP、0 FAIL/ERROR。官方基线十二层补丁重放的 24 条 check/apply 命令实际成功。验证摘要及 JUnit 位于 `evidence/framework-validation/`。

2026-10-09 19:25 北京时间官方回读确认 PR 为 OPEN、CLA 标签为 yes、AI-Reviewed，尚未合并；远端 HEAD 与 SOURCE12 提交一致，PR 正文也已核实包含该版本事实。19:18 的机器人汇总列出静态检查、开源合规和 PR size 为 FAILED，整体标签为 ci-failed。汇总没有提交 SHA，静态及合规链接复用较早任务，不能将其推断为 SOURCE12 的已确认具体缺陷。19:28 实际获取的 Linux 单元测试报告没有嵌入 SOURCE12 SHA；先前 13,550 PASS、25 SKIP、0 FAIL/ERROR 的报告属于 SOURCE11 提交 `3c1fa5e483060d211b2f2ce0267f995615de03e7`，不作为 SOURCE12 全 CI 通过的证据。公开发布、CI 范围和状态回执见 `evidence/framework-publication/`；快照不声称维护者已合并或全部 CI 已通过。

请求策略测试直接调用仓库现有代理 CLI，验证请求策略返回 HTTP423、上游零调用、费用零增加。完整回归在不存在本机 research_project 外部 fixture 的隔离仓库中通过。

Reporting 的结果表替换按实际 LaTeX 表格边界执行，兼容 SDK 显示标题差异，同时保留完整实验上下文和精确数值。新增回归覆盖标题差异和无表格时的证据保留。


SOURCE12 增量修复：静态检查所指出的条件、格式、异常捕获及运行时断言问题；模型用量超过预留契约时保留真实记录并停止后续准入；恢复流程保留并发合法状态；Reporting 区分原始模型实验与零调用复现。当前源码本地 442/444 通过，2 个权限跳过；新提交的平台 CI 必须以其自己的远端结果为准，先前 13,550 项 Linux 通过仅属于 SOURCE11。
