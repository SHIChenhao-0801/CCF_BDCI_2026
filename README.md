# CCF BDCI 2026 · 可追溯科研 Agent

[English](README.en.md)

本项目基于 **openJiuwen / JiuwenSwarm**，面向 CCF BDCI 2026 科研论文自动生成赛题，构建一个能够在准备好的研究材料上执行实验、分析结果并生成英文 ICLR 论文的半自动科研 Agent。本仓库保存 **SOURCE12** 框架源码、研究配置、已评审论文和可离线复核的实验记录。

## 我们做了什么

- **科研流程**：配置 Design、PreparedCode、Execution、Reflection、Reporting 等环节，组织研究输入、实验执行和论文生成；各环节是否真正执行以运行报告为准。
- **产物完整性门禁（APG）**：直接修改 JiuwenSwarm 源码，在完成状态发布前检查 PDF、Reporting 终态、声明产物的路径与存在性、模型调用账本及可用 AUX 中的引用键。门禁本身不调用模型或网络；缺少可靠 AUX 时该项标记为 SKIPPED。
- **运行与费用保护**：加入请求级暂停、截止时间与预算准入检查，记录真实模型用量及结算状态；结果未知的调用不自动重发。
- **可追溯证据**：保存论文源文件、框架补丁、运行记录、资源统计及冻结请求/响应，支持不重新调用模型的科研结果重算。

APG 验证的是产物完整性，不能替代论文事实核验。当前证据支持准备好输入后的半自动研究流程，尚不能证明独立选题、从零实现实验和跨主题自主科研。

## 仓库内容

| 路径 | 内容 |
| --- | --- |
| code/jiuwenswarm/ | 已应用 12 层补丁的 SOURCE12 框架源码、依赖锁和测试 |
| code/research_project/ | 研究入口、pipeline、冻结输入和预算模板 |
| code/apg_pilot/、code/patches/ | APG 试验材料与框架修改补丁 |
| paper/ | 7 页英文 ICLR PDF 和 LaTeX 源文件 |
| docs/ | 架构、模块调用、创新点与复现指南 |
| evidence/ | 运行证据、资源统计和离线重算脚本 |
| EXPORT_MANIFEST.json | 文件 SHA256、发布排除项和本次核验记录 |

## 怎么使用

### 1. 获取代码

推荐使用 Windows PowerShell 7、Python 3.12；安装锁定依赖时需要 uv。先克隆仓库并进入根目录：

~~~powershell
git clone https://github.com/SHIChenhao-0801/CCF_BDCI_2026.git
Set-Location CCF_BDCI_2026
~~~

### 2. 先做离线重算：无需模型 API

下面的命令只读取冻结记录，将结果写到仓库外，不产生新的模型调用：

~~~powershell
$replayOutput = Join-Path (Split-Path (Get-Location).Path -Parent) 'ccf-bdci-replay'
New-Item -ItemType Directory -Path $replayOutput -Force | Out-Null
py -3.12 -I -B -X utf8 evidence/tokenmatched-holdout240-completed-20261009/replay.py --output (Join-Path $replayOutput 'study240.json')
~~~

本次发布副本实测结果为 **237 个完整配对、3 个缺失、0 次模型调用、0 次网络请求**。更多重算入口见 [复现指南](docs/REPRODUCE.md)。

### 3. 安装框架依赖并运行回归

~~~powershell
Set-Location code/jiuwenswarm
uv sync --frozen --group test
uv run --frozen --group test python -B -m pytest tests/unit_tests/rsi -o addopts= -p no:cacheprovider --asyncio-mode=auto -q
~~~

SOURCE12 冻结时的历史本地结果为 **442 PASS、2 Windows 权限 SKIP、0 FAIL**。此次 GitHub 整理验证了文件复制身份及上述离线重算，没有重新运行完整回归。

### 4. 运行 Agent 生成新论文

按 [复现指南](docs/REPRODUCE.md) 准备自己的私有模型配置、包外预算账本及请求策略，启动预算代理，再运行 code/research_project/run_agent.py。配置字段包括 DEEPSEEK_API_KEY、经确认的 DEEPSEEK_API_BASE 和 DEEPSEEK_MODEL。此步骤会消耗模型 API 额度，应先设置预算；不要将真实凭据加入 Git。

需要重新编译论文时，在 paper/source/ 使用 LaTeX 工具链执行 latexmk -pdf -interaction=nonstopmode -halt-on-error main.tex。重新编译可能改变 PDF 字节；仓库保留的 paper.pdf 是已评审版本。

## 论文与发布边界

- 论文是 *Artifact Gates and Bounded Verifier Feedback in a Traceable Research Agent*，采用 ICLR 模板，共 7 页；历史 Reviewer 分数为 6.3，不是比赛最终得分。
- 冻结论文报告 24 任务试验与较早的 102/240 检查点。237/240 完整结果等属于后续独立补充证据，不声称已写入该 PDF。
- 本仓库是从最终交付树整理的源码与证据快照；不含上游完整 Git 提交历史，也不含 Reviewer Access Token、私有评审回执和本机工作过程目录。原比赛提交说明中的相关路径仅用于保留来源说明。
- 框架贡献提交标识为 dae143d9ac19cb5e05864d459b8cd89de96de908；贡献详情见 [框架贡献说明](framework_contribution.md)，费用与用量见 [资源报告](resource_report.md)。PR 合并、当前 CI 和赛事接收状态应以对应平台记录为准。

保留上游及第三方许可文件，各目录按现有许可处理；本仓库不额外声明整个材料包采用统一新许可证。
