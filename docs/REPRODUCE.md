# 复现指南

使用 Python3.12。`code/jiuwenswarm/` 是已应用十二层补丁的源码，依赖固定在 `uv.lock`。独立 RSI 回归为444个唯一测试：442通过、2项Windows符号链接权限跳过。

在 `code/jiuwenswarm/` 安装锁定依赖并运行源码回归：

```powershell
uv sync --frozen --group test
uv run --frozen --group test python -B -m pytest tests/unit_tests/rsi -o addopts= -p no:cacheprovider --asyncio-mode=auto -q
```

科学重算只依赖标准库，直接读取冻结请求和响应，不需要模型或网络。从团队目录执行，输出保存到包外。600题入口使用自身的本地audit包，因此采用普通脚本模式；其他重算入口支持隔离模式。

```powershell
$replayOutput = Join-Path (Split-Path (Get-Location).Path -Parent) 'replay-output'
New-Item -ItemType Directory -Path $replayOutput -Force
python -B -X utf8 evidence/reasoning-replication600-20261008/replay.py --output (Join-Path $replayOutput 'study600.json')
python -I -B -X utf8 evidence/tokenmatched-followup-20261008/replay.py --output (Join-Path $replayOutput 'study375.json')
python -I -B -X utf8 evidence/tokenmatched-holdout240-completed-20261009/replay.py --output (Join-Path $replayOutput 'study240.json')
python -I -B -X utf8 code/research_project/prepared-input/run.py --run-eval --output (Join-Path $replayOutput 'prepared-metrics.json')
```

240研究的主结果为237完整配对、3缺失、full104与neutral93正确、discordance12/1、双侧精确McNemar p=0.00341796875。600、375、240分别重算；输入Token匹配和bootstrap按原始协议验证。校准probe不计入科学求解样本。

真实模型入口位于 `code/research_project/`：`run_agent.py`、`pipeline.yaml`、`INSTRUCTION.txt`、`paper-input/`、`prepared-input/`、`iclr-template/`。Prepared重算支持 `--smoke-test` 和 `--run-eval`。Pipeline启用Design、PreparedCode、Execution、Reflection、Reporting；每次实际执行以模块报告为准。

模型运行需要复现者的私有env，字段为 `DEEPSEEK_API_KEY`、经确认的 `DEEPSEEK_API_BASE`、`DEEPSEEK_MODEL`。为全新复现环境从 `fresh-model-budget.template.json` 创建包外预算账本，并创建只含 `paused` 和 `stop_at_utc` 的请求策略文件；已有付费账本继续沿用，不能覆盖为零。截止时间采用UTC，私有文件不纳入提交。

在 `code/research_project/` 的已安装依赖环境中启动代理。三个变量分别指向实际私有env、包外预算账本与请求策略；端口19081与pipeline、launcher一致：

```powershell
python -B -X utf8 start_full_context_budget_proxy.py --env-file $privateEnv --ledger $budgetLedger --request-policy $requestPolicy --port 19081
```

另一终端在同一目录运行：

```powershell
$env:PYTHONPATH = (Resolve-Path ../jiuwenswarm).Path
python -B -X utf8 run_agent.py --source paper-input --pipeline pipeline.yaml --instruction INSTRUCTION.txt --tasks-root $externalTasksRoot
```

`$externalTasksRoot` 为包外任务目录。模型入口消耗API额度，应先设置预算并完成本地重算。冻结重算与模型调度、写作分别计量，资源明细位于 `evidence/resources/`。

安装可用LaTeX工具链，在 `paper/source/` 执行：

```text
latexmk -pdf -interaction=nonstopmode -halt-on-error main.tex
```

论文冻结源码包含14个作者输入文件，5条引用均已解析。身份见 `paper/paper-identity.json`；重新编译可能改变PDF字节，Reviewer Token须与实际交付PDF对应。当前Token已与交付PDF实际绑定，回执位于 `Agentic Reviewer/reviewer-binding.json`；评审结果状态见同目录 `review-status.json`。


SOURCE12 增量修复：静态检查所指出的条件、格式、异常捕获及运行时断言问题；模型用量超过预留契约时保留真实记录并停止后续准入；恢复流程保留并发合法状态；Reporting 区分原始模型实验与零调用复现。当前源码本地 442/444 通过，2 个权限跳过；新提交的平台 CI 必须以其自己的远端结果为准，先前 13,550 项 Linux 通过仅属于 SOURCE11。

完整240任务的可移植后续分析：在 evidence/tokenmatched-holdout240-completed-20261009/posthoc-analyses/ 执行 python replay_posthoc.py；只读冻结记录，禁止网络。
