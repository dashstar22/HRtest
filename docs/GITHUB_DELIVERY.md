# GitHub 面试交付记录

日期：2026-10-21。

上传已完成：通过 GitHub CLI 创建 `dashstar22/HRtest` 私有仓库，配置 `origin`，普通推送 `main` 成功（未使用 force）。首次推送后查询确认仓库为私有、默认分支为 `main`，远端分支 SHA 与本地提交 `1df80be7a5a15dfe6b8266e6bbe5ad50c99839ae` 一致，GitHub API 可读取本交付记录。本段通过后续文档提交补记，不改写任何已有提交。

交付仓库：https://github.com/dashstar22/HRtest 。私有仓库，面试官需要被授予访问权限才能查看；本次交付为源码仓库，不包含在线部署服务。

## 仓库检查与整理

- 整理前工作区干净，分支为 `main`，有4个已有提交，无 remote；GitHub CLI 当前账号为 `dashstar22`，查询未发现该账号下已有 `HRtest` 仓库。
- 保留已有提交、源码、测试、依赖清单、`.env.example`、样例、截图和历史验证记录；没有改写历史或覆盖演示数据。
- 扩充 `.gitignore`：忽略环境文件（保留 `.env.example`）、虚拟环境、数据库及伴随文件、本地上传、私有资料和临时目录。
- 补充 `samples/README.md`，说明样例、关联截图和导出记录均为虚构数据；简历业绩数字不是系统效果评估。
- README 增加获取代码、无 Key 运行、环境变量优先级、样例与当前验证入口。业务代码没有改动。

## 安全检查范围

推送前扫描全部可见历史：4个已有提交、91个历史 blob，包括 DOCX 文本和 PDF 文本；检查常见 API Key、GitHub token、私钥、云访问标识、密钥赋值，以及本地配置中的真实密钥是否出现在 Git 内容中。扫描未发现匹配；不输出密钥原文。新整理的待提交文件再次检查。

检查实际跟踪文件，不包含 `.env`、虚拟环境、本地数据库或上传目录；`.env.example` 的 API Key 为空。相关截图和导出对应仓库内虚构样例。此检查是模式扫描和已知本地密钥比对，不代表对所有形式的未知敏感信息作绝对保证。

最终待提交的77个文件已再次完成常见密钥模式和本地已知密钥比对，未发现匹配；`git diff --cached --check` 通过。

## 本次独立目录启动验证

- 在系统临时目录复制待交付文件，不复制原 `.env`、虚拟环境或 `data/`。
- 使用 Python 3.12.10 新建虚拟环境，从 `requirements.txt` 重新安装依赖，复制空 Key 的 `.env.example`，显式清空子进程的 `DEEPSEEK_API_KEY`。
- 以 uvicorn 启动独立端口；首页、静态 JS、交互式 API 文档均返回200；`/api/status` 为 `rule` 且 `configured=false`；首次数据库岗位为空。
- 仅在临时库载入4份虚构样例并完成筛选，4份结果均为规则模式；真实模型调用为0。验证后已停止临时服务。
- 原项目数据库的逻辑快照 SHA-256 在验证前后相同，未覆盖或重筛原演示数据。

复现（Windows PowerShell，需 Python 3.10+，本次验证3.12）：

```powershell
git clone https://github.com/dashstar22/HRtest.git
cd HRtest
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env
$env:DEEPSEEK_API_KEY=""
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

打开 http://127.0.0.1:8000 ，可载入示例数据，或按 README 的3分钟路径上传测试甲、测试乙。若8000已占用，可改用8001并打开相应地址。

## 沿用的测试证据与验证边界

本次只改交付文档和忽略规则，没有修改业务代码，故沿用已有日志，没有重新运行整套回归：

| 验证 | 已有结果 | 证据 |
| --- | --- | --- |
| 规则端到端 | 47通过，0失败 | `experience-2026-10-21/fixed/test-rule.log` |
| 本地 mock AI | 15通过，0失败 | `experience-2026-10-21/fixed/test-ai-mock.log` |
| 可信度回归 | 19测试通过 | `experience-2026-10-21/fixed/test-credibility.log` |

此前真实 DeepSeek 调用和浏览器交互（修改条件后的过期提示、重筛后人工标注与备注保留）见 [修复验证](experience-2026-10-21/修复验证.md)。本次交付验证没有再次调用真实模型，没有新增浏览器端到端验证，也没有将 mock 验证当作真实模型质量验证。

历史截图、旧版分数与当前规则输出须分开理解；没有人工标注招聘评估集，未评估准确率、生产并发、长期稳定性。规则模式仍是关键词初筛；模型引用定位只确认原文存在，支持程度与候选人经历真实性仍需人工复核。SQLite 仍可能遇到写锁和超时。依赖使用版本范围而非完整锁文件；本次成功安装不保证未来所有版本组合都兼容。Docker 本次未构建验证。

仓库保持私有；不包含账号体系、BOSS抓取、OCR或线上托管。模型模式会向配置的服务发送JD和完整解析简历文本，当前无自动脱敏，演示请继续使用虚构数据。
