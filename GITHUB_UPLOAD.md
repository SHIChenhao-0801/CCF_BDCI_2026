# GitHub 仓库同步

目标仓库：https://github.com/SHIChenhao-0801/CCF_BDCI_2026

本次从 SOURCE12 最终交付树生成发布副本，排除 Reviewer 私有目录；克隆目标仓库并保留其初始提交历史，再提交源码、论文、证据与双语 README。执行结果以远端提交回读为准。

## 以后获取远端更新（pull）

在已克隆的本机仓库执行：

~~~powershell
git status --short
git pull --ff-only
~~~

先处理自己的未提交改动。若分支已经分叉，应检查差异再决定合并方式，不强制覆盖。

## 以后上传自己的改动（push）

~~~powershell
git status --short
git add -- 你实际修改的文件
git diff --cached --stat
git commit -m "Describe your change"
git push origin main
~~~

上传前核对暂存范围，保持真实 API 凭据、Reviewer Token、私有环境文件和本机运行目录在 Git 之外。

本次导入时，code、docs、evidence、paper 中的已核验交付文件需要显式暂存，避免上游嵌套 .gitignore 忽略已提供的运行材料。后续开发按具体文件暂存，不批量强制加入运行目录。

EXPORT_MANIFEST.json 记录原交付文件哈希和发布排除项；双语 README、此说明、.gitignore 与 .gitattributes 属于发布时新增材料。原比赛目录保持原样，本仓库不代替包含 Reviewer Token 的比赛提交包。
