# JiuwenSwarm 科研Agent代码

`jiuwenswarm/`为官方固定基线上十二补丁源码。核心包括产物完整性门禁及Provider集成、冻结输入路径与来源验证、请求级暂停及预算结算、Reporting事实约束。直接修改框架源码，交付树已应用补丁。

PR：https://gitcode.com/openJiuwen/jiuwenswarm/pull/7722 。实际已发布提交dae143d9ac19cb5e05864d459b8cd89de96de908，回读OPEN、未合并。SOURCE12已推送，新提交平台CI结果待回读；详情见framework_contribution.md。

独立回归444唯一测试：442 PASS、2权限SKIP；实际check/apply24步，4925文件身份匹配。安装、测试、科学零API重算和论文编译见 `../docs/REPRODUCE.md`。模板、配置与研究输入按各自manifest使用。产物门禁检查PDF、Reporting、安全路径、usage与可靠AUX，不代替科学事实或答案正确性验证。

论文主证据采用240三段研究，完整配对237/240；600与375研究分别保留独立身份。资源按原始usage和结算分类。凭据、邮箱会话和本机私有状态不进入源码。


SOURCE12 增量修复：静态检查所指出的条件、格式、异常捕获及运行时断言问题；模型用量超过预留契约时保留真实记录并停止后续准入；恢复流程保留并发合法状态；Reporting 区分原始模型实验与零调用复现。当前源码本地 442/444 通过，2 个权限跳过；新提交的平台 CI 必须以其自己的远端结果为准，先前 13,550 项 Linux 通过仅属于 SOURCE11。
