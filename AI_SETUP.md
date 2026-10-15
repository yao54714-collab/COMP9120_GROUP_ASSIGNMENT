# PawCare 小组交接：AI 配置与验收指南

交接日期：2026-10-15。目标环境：Windows 10/11、VS Code、本机运行；无需云服务器。项目入口为根目录 `run.py`。

## 复制这段话给 AI 编程助手

先解压项目，并让 AI 打开含 `run.py` 的文件夹，然后发送：

```text
请帮我在这台 Windows 电脑上配置并运行 PawCare 宠物洗护门店管理系统。
先阅读项目根目录 README.md 和 AI_SETUP.md，再检查实际源码、环境和终端输出。

任务：
1. 检查 Python 3.12、Node.js 22.12+、npm、PostgreSQL 16、VS Code。
   用 python tools\check_environment.py 辅助检查。缺软件时说明实际缺项并协助安装；
   只有涉及安装器权限或需要我手动操作时再让我处理。安装后重新检查 PATH。
2. 默认使用 run.py 管理的独立数据库，端口 55432，应用端口 8000。
   首次运行不要复制 .env.example：run.py 应生成 .env 和随机密码。
   自定义 PostgreSQL 路径时，在当前 PowerShell 中设置 $env:PG_BIN 后启动。
3. 执行 python run.py，等依赖安装、数据库初始化与前端构建完成，
   打开 http://127.0.0.1:8000，并确认 /api/health 返回 ok、pawcare、version 4。
4. 运行 tools\pgadmin_setup.py，在 pgAdmin 4 中配置这台机器的连接；
   检查 pawcare 数据库下 pawcare schema 有 20 张表、3 个视图。
5. 在 VS Code 选择项目 .venv\Scripts\python.exe，验证 run.py 和 F5 的使用方式。
6. 按本指南执行后端与 Chrome 浏览器测试，记录实际通过/失败结果；
   不要把交接包里的旧测试报告说成本机新测试结果。
7. 最后告诉我启动和停止方法、网站地址、演示账号、pgAdmin 展开路径以及尚未解决的问题。

约束：
- 保留这台机器已有数据库、项目数据与 pgAdmin 连接，不重置或清空它们。
- 不修改其他项目的 PostgreSQL 服务；端口冲突先识别占用者，不自动终止未知进程。
- 不把数据库密码、.env 内容或 postgres-admin.json 发到聊天或上传。
- 不为配置环境重写业务逻辑或替换 PostgreSQL；依赖优先使用现有锁定文件。
- 如果确有兼容问题，先定位并说明，再做最小必要修复，保留 3NF/BCNF 结构和业务功能。
- 当前只要求本机演示，不发布到公网、不购买服务、不改系统防火墙。
```

## 文件与配置责任

| 文件或目录 | 用途 |
|---|---|
| `run.py` | 创建虚拟环境、安装依赖、准备数据库、构建并启动网站 |
| `backend` / `frontend/src` | 后端与前端完整源码 |
| `database/01_schema.sql`、`02_rules.sql`、`04_hardening.sql`、`05_care_roles.sql`、`06_english_demo_data.sql` | 初始化与增量保护规则，执行顺序与此一致；03 是查询示例 |
| `backend/seed.py` | 创建全新数据库的演示数据；非空数据库不重复填充 |
| `requirements-lock.txt` / `frontend/package-lock.json` | 经项目验证的依赖版本，先按锁文件安装 |
| `.env.example` | 外部数据库模式参考；默认托管模式不要直接复制 |
| `.env` / `.runtime` | 首次运行生成的私有配置、密码和真实数据，不在交接包里 |
| `.vscode` / `PawCare.code-workspace` | VS Code 启动与工作区配置 |
| `tests` / `test-results` | 自动化用例与交接前测试证据；后者运行后可能覆盖 |
| `docs` | 数据库设计、范式论证、事务说明、修复与测试记录 |
| `PACKAGE_MANIFEST.json` | 交接包中文件的 SHA-256 清单 |

交接包没有你的原电脑数据库备份。新机器会重新生成相同结构和演示账号，演示日期按首次运行当天生成。后续各成员数据独立；合并源码不等于合并数据库。

## Windows 手动配置顺序

### 1. 准备运行环境

安装 Python 3.12、Node.js 22.12+、PostgreSQL 16 及 VS Code。PostgreSQL 安装器可以创建自己的默认 5432 服务；PawCare 使用另一个 55432 实例，不使用安装时设置的 postgres 密码。pgAdmin 4 是查看数据库的图形工具，不能替代 PostgreSQL 服务与命令行工具。

在新打开的 PowerShell 中进入项目根目录：

```powershell
python --version
node --version
npm.cmd --version
python tools\check_environment.py
```

`python` 若指向 Microsoft Store 或旧版本，可先使用 `py -3.12 tools\check_environment.py` 和 `py -3.12 run.py`。安装后重开终端；不要只安装 Python 的 VS Code 扩展而漏装 Python 本身。

### 2. 启动整个项目

```powershell
python run.py
```

首次会安装 Python/npm 依赖，所以需要联网。项目自动发现 PATH 中的 PostgreSQL 或标准安装目录；若未找到，在同一个终端设置实际路径：

```powershell
$env:PG_BIN = 'C:\Program Files\PostgreSQL\16\bin'
python run.py
```

该目录应同时含 `initdb.exe`、`pg_ctl.exe`、`postgres.exe`、`psql.exe`。`PG_BIN` 指向 bin 文件夹，不是 pgAdmin 文件夹。第一次自动生成的 `.env` 会记住路径。

在 VS Code 中先用终端完成首次启动，再选择 `.venv\Scripts\python.exe` 作为 Python 解释器。之后运行 `run.py`、F5 或默认启动任务均可。不要用 Live Server，也不要直接双击 `frontend/index.html`。

终端保持运行，浏览器打开 http://127.0.0.1:8000。停止使用该启动终端的 Ctrl+C；项目托管的 PostgreSQL 也会正常停止，数据保留。下次再次运行即可。`--setup-only` 只做准备并保持数据库可用，适合测试前使用；它不启动网站。

### 3. 登录与 pgAdmin

演示账号统一密码为 **`PawCare2026!`**：

| 角色 | 邮箱 |
|---|---|
| 顾客 | `customer@pawcare.local` |
| 前台 | `frontdesk@pawcare.local` |
| 护理师 Emma | `groomer@pawcare.local` |
| 护理师 Mia | `mia@pawcare.local` |
| 店长 | `manager@pawcare.local` |
| 第二位顾客 | `zhou@pawcare.local` |

网站密码和数据库密码不同。pgAdmin 连接在数据库已运行时配置：

```powershell
.\.venv\Scripts\python.exe tools\pgadmin_setup.py
```

脚本能识别打包随 PostgreSQL 安装的 pgAdmin 时尝试追加连接；独立安装或未初始化的 pgAdmin 会提示手动导入。使用 Tools → Import/Export Servers 导入本机生成的 `database/pgadmin-servers.json`，不要替换其他连接。也可手工填写：Host `127.0.0.1`，Port `55432`，Maintenance database `pawcare`，Username `pawcare_app`，Password 从本机 `.env` 的 `DB_PASSWORD` 复制。

展开 `Databases → pawcare → Schemas → pawcare → Tables`。表在 `pawcare` schema 下，不在 `public`；应看到 18 张业务表、2 张技术表，以及 Views 中的 3 个视图。移动文件夹后重新生成连接配置，并更新已有连接的 passfile 路径。

### 4. 验收与测试

```powershell
Invoke-RestMethod http://127.0.0.1:8000/api/health
.\.venv\Scripts\python.exe -m pytest -q --junitxml=test-results/member-backend.xml
.\.venv\Scripts\python.exe tools\check_browser.py
```

健康检查预期：`status=ok`、`database=pawcare`、`version=4`。当前完整测试为 **46 项后端 + 14 项浏览器**；浏览器测试要求安装 Google Chrome。两套测试会建立随机命名的独立测试库并在结束时清理，不在成员的实际业务库中写入测试预约。

可另在 `frontend` 文件夹执行 `npm.cmd run build` 验证 TypeScript 和构建。用项目解释器运行 `tools\inspect_database.py` 可导出本机表与约束清单。

手动演示：顾客选 Luna/猫咪服务 → 前台安排有资质的护理师和工位 → 对应护理师开始与完成 → 前台登记收款 → 店长看库存和报表。业务时间以悉尼时区显示。

## 常见故障

| 现象 | 处理 |
|---|---|
| `.venv\Scripts\python.exe` 不存在 | 新机器正常；先用系统 Python 在终端运行 `python run.py`，成功后再选择虚拟环境 |
| 找不到 node/npm 或 PowerShell 拒绝 npm.ps1 | 安装 Node 后重开终端；手动命令使用 `npm.cmd`；启动脚本已使用 npm.cmd，无需全局放开脚本策略 |
| 找不到 PostgreSQL | 确认安装了服务及 bin 工具，设置实际 `$env:PG_BIN`；环境检查脚本会显示找到的路径 |
| 提示 55432 被占用 | 先识别占用进程和项目；不要直接结束或覆盖。正在运行的另一份 PawCare 需要先由其启动终端正常停止。默认托管端口固定为 55432 |
| 8000 被其他程序占用 | 执行 `python run.py --port 8001`；浏览器使用新端口。数据库端口仍是 55432 |
| 网页打不开 | 保持启动终端运行，检查是否已出现 Uvicorn running；先访问 /api/health，再查看终端报错 |
| Set-ExecutionPolicy 提示无法加载 Microsoft.PowerShell.Security | 检查 Windows PowerShell 5.1 是否继承了 PowerShell 7 的模块目录；项目设置已用 `terminal.integrated.env.windows.PSModulePath: null` 为新终端清除继承路径。关闭闲置旧终端后新建，再 F5 运行；无需修改全局执行策略 |
| 日志出现 /api/auth/me 401 或 shutdown complete | 未登录的 401 是预期响应；shutdown complete 表示服务已正常停止，重新 F5 启动后保持运行 |
| 默认模式复制示例 .env 后认证失败 | 若确认该文件只包含示例占位符且没有自定义配置，将其备份改名后让 run.py 生成；不要删除已有数据库、真实凭据或 `.runtime` |
| pgAdmin 连接失败/没有表 | 保持项目数据库运行，核对 55432 与本机密码；刷新 pawcare schema，不要只看 public |
| 新机器依赖下载失败 | 检查网络、证书或学校代理配置；保留锁文件，先重试。若确实不能获取锁定版本，应明确记录调整和重新测试结果 |
| 更换 PostgreSQL 主版本后无法启动旧数据 | 使用创建该数据目录的原主版本，或走备份恢复/升级流程；不要对旧 `.runtime/postgres-data` 重新 initdb |

项目是本地单店演示系统，支持猫狗洗护，不包括真实在线支付、短信发送或公网部署。Windows 为本交接包目标环境；macOS/Linux 未作为本次交付的安装验证平台。


## 英文版与用户管理更新

界面与默认演示数据已统一英文；现有注册入口和流程保留。店长的 User accounts 页面支持账号搜索、角色筛选、启停与重置密码。今后用户输入不限制语言。结构版本 4 的 06 脚本只在升级时翻译既有默认文本，不重复改写后续输入。具体说明见中英文 README。
