# 模块调用与复现契约

| 模块 | 输入 | 可检查输出 |
| --- | --- | --- |
| Manager | 任务说明、pipeline、模块报告 | 调度决定与终态状态 |
| Design | 研究问题与协议 | 方法、约束、实验计划 |
| PreparedCode | 冻结 source、manifest、协议 | 受控准备目录与来源身份 |
| Execution | 已准备 runner 与数据 | 结果、stdout、状态、资源字段 |
| Reflection（可选） | 实验报告 | 对已有结果的诊断建议 |
| Reporting | 科学协议、原始证据、模块报告 | ICLR LaTeX、PDF 与引用辅助文件 |
| Artifact Provenance Gate | Manager、Reporting、产物和调用账本 | APG001–005 与 PASS/BLOCKED/SKIPPED |

配套研究重算的准备输入位于 `code/research_project/prepared-input/`，包含 `run.py`、`dataset.json`、`manifest.json`、`PROTOCOL.md`。manifest 绑定数据、协议及源码；runner 无模型或网络调用器。smoke 使用 `--smoke-test` 并报告 smoke_test=true；真实本地重算报告 smoke_test=false，二者均报告 model_call_count=0。`--run-eval` 是本地重算别名，不是网络触发器。

重算逐项恢复原任务 ID、共享初始回答、错误资格、终态回答、oracle 判断、配对 discordance、缺失类别和三研究独立分母。额外 usage 事件用于成本聚合，不能当作额外求解样本。600、375、240 三项研究分别保留，不合并样本或跨版本挪用统计结果。

研究输入配置及依赖按 `docs/REPRODUCE.md` 中固定入口运行。先执行零 API 的导入/身份检查与本地重算，再检查结果是否等于独立原始证据审计。源码回归的具体测试项和平台 SKIP 随独立验证证据保留。付费运行需要调用者另行配置本地私有凭据和明确预算；提交包不携带密钥、会话或在线账户状态。


SOURCE12 增量修复：静态检查所指出的条件、格式、异常捕获及运行时断言问题；模型用量超过预留契约时保留真实记录并停止后续准入；恢复流程保留并发合法状态；Reporting 区分原始模型实验与零调用复现。当前源码本地 442/444 通过，2 个权限跳过；新提交的平台 CI 必须以其自己的远端结果为准，先前 13,550 项 Linux 通过仅属于 SOURCE11。

交付源码的 SOURCE12 身份与论文冻结的科学实验身份分别记录。此轮源码修复和重算不重新获取模型回答；Reporting 显式标识原始模型实验与零 API 的证据复现。源码验证数量不能替代论文样本数量。
