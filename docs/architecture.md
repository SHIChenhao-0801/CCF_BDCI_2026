# 科研 Agent 架构

系统在 JiuwenSwarm 官方基线 f0a69728c96b5961d993449f1a901cbd2f4dac5b 上修改源码，保留 Manager 统一调度。交付源码采用十二层补丁的固定版本（SOURCE12），运行配置、依赖和复现入口随包提供。

```text
Manager → Design → PreparedCode → Execution → Reporting
                          ↘ 可选 Reflection ↗
Manager 终态 → Artifact Provenance Gate → 审计与产物打包
模型调用 → 请求级暂停/截止门禁 → 共享成本账本 → usage 结算
```

Design 负责设计任务和实验协议；PreparedCode 导入已冻结、含来源清单的研究输入，并验证路径与身份；Execution 执行本地实验或重算；Reflection 是可选诊断模块；Reporting 汇总实际报告并使用 ICLR 模板写作。工作流提供 Design、PreparedCode、Execution、Reporting 和可选 Reflection，配套本地入口对冻结科学记录做零新增求解调用的重算。架构支持某个模块不等于本次评估调用了它。

Artifact Provenance Gate 是零模型调用的确定性门禁。APG001 检查 PDF 是非空普通文件；APG002 检查 Manager 状态及成功终态 Reporting；APG003 检查报告声明的产物存在且处于允许根目录；APG004 检查唯一调用 ID 与非负整数 Token；APG005 仅在可靠 AUX 存在时比较 citation/bibcite，缺失则 SKIPPED。存在 blocker FAIL 才 BLOCKED。此门禁核查产物完整性，不保证答案正确、科学结论成立或每条论文事实正确。

请求级控制在准入前及排队后检查暂停与硬截止，已发出的请求按实际状态结算。未知调用保留成本占用，不自动重传、不虚构退款。资源账本与科学观察分开：论文写作调用不计为新的求解样本。

当前已验证源码12为 444 个唯一 RSI 测试，442 PASS、2 个 Windows 符号链接权限 SKIP、0 FAIL/ERROR；十二补丁真实 check/apply 共 24 步，最终 4925 文件身份一致。这些是源码及离线回归证据，不等同于付费全流程完成证明。


SOURCE12 增量修复：静态检查所指出的条件、格式、异常捕获及运行时断言问题；模型用量超过预留契约时保留真实记录并停止后续准入；恢复流程保留并发合法状态；Reporting 区分原始模型实验与零调用复现。当前源码本地 442/444 通过，2 个权限跳过；新提交的平台 CI 必须以其自己的远端结果为准，先前 13,550 项 Linux 通过仅属于 SOURCE11。
