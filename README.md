# PawCare · Pet Care Studio / 宠物洗护门店管理系统

## English guide

PawCare is a local application for one cat/dog grooming store. It uses React + TypeScript + Vite, Python + FastAPI + Psycopg, and PostgreSQL 16. The customer portal is friendly and playful; the staff workspace is clean and practical. The interface, messages and default data are in English. Existing Chinese demo text is translated once on upgrade; future user-entered text can use any language.

### First setup in Windows and VS Code

1. Install **Python 3.12**, **Node.js 22.12+**, **PostgreSQL 16** with command-line tools, and VS Code with the Microsoft Python extension. pgAdmin 4 is recommended. Browser tests additionally require Google Chrome.
2. Extract the ZIP fully into a writable local folder, such as `C:/Projects/pawcare`, or clone the GitHub repository using the commands below. Open the folder containing `run.py` in VS Code. Do not run inside the ZIP or overwrite another project containing `.runtime`.
3. Open a new PowerShell terminal, then run:

```powershell
python tools\check_environment.py
python run.py
```

Use `py -3.12` if `python` points to an older version or Microsoft Store. The launcher creates `.venv`, installs dependencies from lockfiles, initializes a project-owned PostgreSQL instance, seeds an empty database, builds the frontend and opens **http://127.0.0.1:8000**. First installation needs internet access. Wait for `Uvicorn running` and keep the terminal open.

To get the source from GitHub (Git must be installed), run the following in your chosen parent folder, then follow the setup steps above:

```powershell
git clone https://github.com/yao54714-collab/COMP9120_GROUP_ASSIGNMENT.git
cd COMP9120_GROUP_ASSIGNMENT
code .
```

Each clone creates its own local database on first launch. Git synchronizes source code, not database records or local passwords. The latest clean-install check is recorded in [delivery verification](docs/delivery-verification-2026-10-15.json).

**Managed mode does not require copying `.env.example` to `.env`.** The launcher generates local passwords. For a nonstandard PostgreSQL path, set the real bin folder in the same terminal before starting:

```powershell
$env:PG_BIN = 'C:\Program Files\PostgreSQL\16\bin'
python run.py
```

After first setup, select `.venv/Scripts/python.exe` with **Python: Select Interpreter**. Use **F5**, Run Python File on `run.py`, or the startup task. Do not use Live Server or open the frontend HTML directly. Press **Ctrl+C** in the startup terminal to stop the app and its managed database; data is retained.

The workspace clears inherited `PSModulePath` for new Windows terminals so PowerShell discovers modules for its own version. This prevents Windows PowerShell 5.1 from loading incompatible PowerShell 7 security modules during Python environment activation. After updating the workspace settings, close idle old terminals and create a new one. F5 explicitly uses the project's `.venv` interpreter. A `401` log for `/api/auth/me` before sign-in is expected; `Application shutdown complete` means the server has stopped normally. Keep the running terminal/debug session open while using the website.

Options: `--no-browser` avoids opening a browser; `--port 8001` changes only the website port; `--setup-only` prepares dependencies/database/frontend without starting the website and leaves the database available. For AI-assisted setup, give the assistant this project folder and [AI_SETUP.md](AI_SETUP.md).

The launcher opens a fresh `?launch=…` URL and HTML responses use `Cache-Control: no-store` to avoid older cached pages. If an already-open tab still shows Chinese, close that tab and use the newly opened page, or press **Ctrl+F5**. An anonymous or expired session opens the English sign-in form without a red authentication banner; incorrect submitted credentials still show a useful form error.

### Accounts and business workflow

All synthetic demo accounts use **`PawCare2026!`**, which is different from the database password.

| Role | Email | Main access |
|---|---|---|
| Customer | `customer@pawcare.local` | Own pets, bookings, care history and profile |
| Receptionist | `frontdesk@pawcare.local` | Customers, scheduling and payments |
| Groomer Emma | `groomer@pawcare.local` | Assigned tasks, care records and shifts |
| Groomer Mia | `mia@pawcare.local` | Separate groomer for task isolation |
| Manager | `manager@pawcare.local` | Reports, employees, resources, inventory, refunds and accounts |
| Second customer | `zhou@pawcare.local` | Separate customer for data isolation |

New customers use **New here? Create a customer account** on the sign-in page. The existing registration flow is retained. Public registration creates customers only; managers create employees in **Employees & shifts**.

**Manager → User accounts** provides search by name/email, role/status filters, activation/deactivation and password resets. Deactivation/reset revokes old sessions; passwords and hashes are never listed. Employee login and scheduling status change together. Staff with unfinished care tasks cannot be deactivated, and managers cannot deactivate themselves. Inactive customer profiles must be restored in **Customers & pets** before login can be enabled. Business history is retained. Other roles cannot administer accounts. See the [account review](docs/account-management-review.md).

**Pet removal:** In **My pets** (customer) or **Customers & pets** (reception/manager), choose **Delete** beside a pet without booking history and confirm. Pets with any booking history show **Deactivate** instead; finish or cancel unfinished bookings first. Pet lists show active pets by default. Choose **View inactive pets** to see saved inactive profiles and their care history; they cannot be selected for new bookings. To restore a profile, edit it and select **Active profile**. Customers can only remove their own pets.

Workflow: customer adds pets and requests services → reception confirms qualified staff, stations, times and prices → groomer starts/completes care and records actual consumables → reception records offline payments → manager handles eligible refunds, inventory and reports. Care completion and stock deductions commit together; insufficient stock rolls everything back. Historical prices are retained.

Amounts use **AUD**, and business dates use **Australia/Sydney**. The scope excludes boarding, retail, loyalty points, real card charging, SMS/email sending and compensation after completed services. For demonstrations, confirmed future tasks may start early; actual start/end timestamps still reflect real operations.

### Database and pgAdmin

Managed connection: **127.0.0.1:55432**, database **pawcare**, user **pawcare_app**. Existing PostgreSQL services on 5432 are not changed. Keep the project running, then execute:

```powershell
.\.venv\Scripts\python.exe tools\pgadmin_setup.py
```

The helper generates this machine's `database/pgadmin-servers.json` and attempts automatic registration. If manual import is needed, use **Tools → Import/Export Servers**, without replacing existing servers. Alternatively register the connection manually and copy `DB_PASSWORD` locally from `.env`. Expand **Databases → pawcare → Schemas → pawcare → Tables**; the tables are not in `public`. Expect **18 business tables + 2 technical tables, 3 views, schema version 4**. Moving the project requires regenerating the connection and updating the old passfile path.

Never share `.env`, `.runtime/postgres-admin.json`, `.runtime/pgadmin.pgpass` or actual database backups in the handoff. Each member generates their own credentials and an independent English demo database. Operations are not synchronized across members.

For an external PostgreSQL instance, an administrator must create the database/application role, apply **01 → 02 → 04 → 05 → 06**, grant schema/table/sequence access, then configure `.env` with `MANAGED_POSTGRES=0`. Seed an empty database only if demo data is wanted. The managed test/backup helpers depend on project cluster metadata and are not generic external-database utilities.

### Validation, design and troubleshooting

With PostgreSQL running, execute from the project root:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/api/health
.\.venv\Scripts\python.exe -m pytest -q --junitxml=test-results/member-backend.xml
.\.venv\Scripts\python.exe tools\check_browser.py
```

Health must return `status=ok`, `database=pawcare`, `version=4`. The English/account-management regression includes **46 backend and 14 browser tests**, including legacy-data migration checks. See the [current verification report](docs/english-and-accounts-2026-10-15.md) for results. Each member must run their own acceptance checks. Tests create disposable databases and preserve the business database. Build the frontend with `npm.cmd run build` inside `frontend`. Offline API documentation is at `/api/docs`.

Source: `backend` and `frontend/src`; SQL: `database`; tests/helpers: `tests` and `tools`; dependency locks: `requirements-lock.txt` and `frontend/package-lock.json`. [Database design](docs/database-design.md) explains entities and 3NF/BCNF; [transaction notes](docs/transactions-and-demo.md) explain concurrency and demonstrations. Translation/account management do not change the business tables or functional dependencies. The translation transaction temporarily bypasses two text-history guards and restores them before commit; later startups do not retranslate user input.

- Data lives in `.runtime/postgres-data`; normal restarts retain it. Do not reinitialize existing data or switch PostgreSQL major versions without a supported upgrade.
- Use pgAdmin Backup or `tools/backup_database.py` with the project interpreter; keep real backups private.
- Port 55432 occupied: identify its owner first, without terminating unknown services. Website port 8000 occupied: use `--port 8001`.
- No available groomer: check active access, qualifications, shifts and resource conflicts. Seeded shifts cover 14 days before to 45 days after first setup; add later shifts as needed.
- If PowerShell blocks `npm.ps1`, use `npm.cmd`. Reopen terminals after installing runtimes.
- The ZIP contains source, SQL, tests, guides and a checksum manifest, excluding credentials, live data, `.venv`, `node_modules` and machine-specific pgAdmin files.

Follow course requirements for AI-assistance disclosure and ensure every member understands the code, database design and their actual contribution.

---

## 中文说明

顾客端：奶油白、鼠尾草绿、圆角与小狗插画。商户端：灰白工作区、清晰表格与状态标签。

这是一个真实连接 PostgreSQL 的本地应用。前端 React + TypeScript + Vite；后端 Python + FastAPI + Psycopg；数据库 PostgreSQL 16。界面不依赖在线字体、图片或云服务。

## 小组成员首次接收项目

本交接包针对 **Windows 10/11 + VS Code**。先完整解压到可写的本地文件夹，例如 `C:\Projects\pawcare`，再用 VS Code 打开含 `run.py` 的 `pawcare` 文件夹。不要直接在压缩包中运行，也不要把新的交接包覆盖到已有 `.runtime` 的项目中。

也可以安装 Git 后，在准备存放项目的父文件夹中执行下面的命令，再按首次安装步骤启动：

```powershell
git clone https://github.com/yao54714-collab/COMP9120_GROUP_ASSIGNMENT.git
cd COMP9120_GROUP_ASSIGNMENT
code .
```

GitHub 仓库根目录就是项目目录，打开后可以直接看到 `run.py`。每位成员首次启动会创建独立数据库；Git 只同步代码，不同步业务记录或本机密码。本次全新目录安装验证见 [交付验证记录](docs/delivery-verification-2026-10-15.json)。

1. 安装 **Python 3.12**（勾选加入 PATH）、**Node.js 22.12 或以上**、**PostgreSQL 16**（含命令行工具，建议同时安装 pgAdmin 4）。VS Code 安装 Microsoft Python 扩展。浏览器自动化另需 Google Chrome。
2. 安装后重新打开 VS Code，在 PowerShell 终端执行 `python tools\check_environment.py`，按提示处理缺失项。
3. 首次启动执行 **`python run.py`**。程序会创建自己的 `.venv`，安装锁定依赖，建立项目独立数据库，执行 SQL 并填入演示数据，构建前端，然后打开网站。首次需要联网，请等待终端出现 Uvicorn running。
4. 启动成功后，在 VS Code 的 “Python: Select Interpreter” 中选 `.venv\Scripts\python.exe`；以后可使用 F5 或运行 `run.py`。
5. 需要在 pgAdmin 查看表时，保持网站运行，另开终端执行 `.\.venv\Scripts\python.exe tools\pgadmin_setup.py`，再按下文连接。

**希望 AI 帮忙配置：** 打开 [AI 配置与验收指南](AI_SETUP.md)，把其中的提示词连同本项目文件夹交给 AI 编程助手。指南包含执行顺序、成功标准和常见故障处理。

默认独立数据库模式**不需要提前创建数据库，也不要复制 `.env.example` 成 `.env`**。程序会生成本机专属密码。若 PostgreSQL 不在默认路径，先设置实际安装路径，再启动：

```powershell
$env:PG_BIN = 'C:\Program Files\PostgreSQL\16\bin'
python run.py
```

压缩包包含完整源码、SQL、演示数据生成脚本、前后端依赖锁定文件、VS Code 配置、测试与设计文档。`.env`、真实数据库、备份、`.venv`、`node_modules` 和本机 pgAdmin 连接文件不在包内。每位成员首次运行会创建独立的演示数据，不会自动同步其他成员的操作记录。

## 在 VS Code 运行

1. 用 VS Code 打开本文件所在的 **pawcare 文件夹**。
2. 打开 `run.py`，点击 Python 扩展的 **Run Python File / 运行 Python 文件**，或按 F5 选择“PawCare · 启动整个项目”。
3. 启动程序会检查数据库和前端，然后自动打开 **http://127.0.0.1:8000**。
4. 停止时在运行终端按 **Ctrl+C**。数据库文件保留，再运行即可恢复。

也可以在 VS Code 终端执行：

```powershell
python run.py
```

可选参数：`--no-browser` 不自动打开浏览器；`--port 8001` 使用其他网站端口；`--setup-only` 准备依赖、启动数据库、初始化并构建前端，但不启动网站。

首次安装需要联网下载 Python / npm 依赖。以后依赖与源代码未改变时不会重复安装或构建。Python 使用项目内 `.venv`；依赖版本保存在 `requirements-lock.txt` 和 `frontend/package-lock.json`。已验证的 Python 版本为 3.12，数据库为 PostgreSQL 16；Node.js 需要 22.12 或以上。

**不要用 Live Server 打开前端 index.html。** `run.py` 同时提供 API 与构建后的前端，二者使用同一地址。另行开发前端时，可在 `frontend` 运行 `npm run dev`，其 `/api` 代理指向本地 8000 端口。

项目配置会为新 Windows 终端清除继承的 `PSModulePath`，让 PowerShell 使用自身版本的模块，避免 5.1 误加载 7 的安全模块而在自动激活环境时出错。更新配置后关闭闲置旧终端，再新建终端；F5 已明确使用本项目 `.venv` 解释器。未登录时 `/api/auth/me` 返回 401 属正常现象；`Application shutdown complete` 表示服务正常停止，使用网页时请保留运行中的终端/调试会话。

启动器会打开带 `?launch=…` 的新地址，首页禁止缓存，避免继续加载旧页面。若原标签页仍显示中文，请关闭旧标签页，使用启动器新打开的页面，或按 **Ctrl+F5**。正常未登录或会话过期只显示英文登录表单，不显示顶部红色登录提示；主动提交错误密码时仍保留表单错误说明。

## 演示账号

以下均为人工构造的本地演示账号，统一密码：`PawCare2026!`。

| 角色 | 邮箱 | 主要功能 |
|---|---|---|
| 顾客 | customer@pawcare.local | 多宠物档案、预约、取消未开始服务、护理记录、联系方式 |
| 前台 | frontdesk@pawcare.local | 顾客与宠物、预约确认/调整、可用资源查询、未到店、分次收款 |
| 护理师 Emma | groomer@pawcare.local | 自己的任务、护理开始/完成、实际耗材、护理记录、排班 |
| 店长 | manager@pawcare.local | 经营报表、所有预约、员工/资质/班次、服务/标准耗材、工位、库存、退款 |
| 护理师 Mia | mia@pawcare.local | 第二位护理师，方便验证任务隔离 |
| 第二位顾客 | zhou@pawcare.local | 方便验证顾客数据隔离 |

登录页“本地演示账号”可填入上述账号。也可自行注册新顾客。员工由店长新增。

网站现在全部使用英文：登录页演示账号入口为 **Demo accounts**，顾客注册入口为 **New here? Create a customer account**，原注册流程保留。

店长新增 **User accounts** 页面，可搜索账号、按角色和状态筛选、启停及重置密码。停用/重置会撤销旧会话，不展示密码和哈希。员工登录与排程启用状态同步；存在未结束护理任务时不能停用，也不能停用自己。顾客、宠物、预约及财务历史保留；已停用的顾客档案需先在 Customers & pets 恢复。员工创建、角色和资质仍在 Employees & shifts 管理，其他角色不能使用账号管理。详见 [功能评审](docs/account-management-review.md)。

## 在 pgAdmin 4 中查看

首次运行后执行 `tools\pgadmin_setup.py`，生成本机连接配置；自动导入成功后将显示：

```text
PawCare
└── PawCare 本地项目
    └── Databases
        └── pawcare
            └── Schemas
                └── pawcare
                    ├── Tables（18 张业务表 + 2 张技术表）
                    └── Views（3 个视图）
```

先运行 `run.py`，再刷新 pgAdmin 的服务器树。数据库地址 `127.0.0.1`，端口 **55432**，数据库 **pawcare**，用户 **pawcare_app**。这是项目独立实例，原有 5432 端口的 PostgreSQL 未改变。

项目数据库密码自动生成，保存在本地 `.env`；不要与网站演示密码混淆。执行连接配置脚本后，pgAdmin 连接使用项目 `.runtime/pgadmin.pgpass` 自动读取数据库密码。若 pgAdmin 弹出密码输入框，可从 `.env` 的 `DB_PASSWORD` 本地复制。数据库管理账户的配置位于 `.runtime/postgres-admin.json`，不进入源代码版本控制。

如果连接树没有即时更新，刷新或重新打开 pgAdmin。重新注册可运行：

```powershell
.\.venv\Scripts\python.exe tools\pgadmin_setup.py
```

脚本若提示手动导入，使用 pgAdmin 菜单 **Tools → Import/Export Servers** 导入刚生成的 `database/pgadmin-servers.json`，不要勾选删除现有服务器。也可手动 Register Server，填写上面的 host、port、database、username，并从本机 `.env` 填密码。换电脑或移动文件夹后应重新生成连接文件；旧连接若已存在，还需在 Properties → Parameters 中更新 passfile 路径。

Query Tool 示例：

```sql
SET search_path TO pawcare, public;
SELECT * FROM appointment_overview;
SELECT * FROM appointment_financials;
SELECT * FROM inventory_balance;
```

## 完整业务流程

1. 顾客注册 / 登录，建立宠物档案，选择一只或多只宠物及服务，提交期望时间。
2. 前台确认所有服务项的护理师、工位、起止时间和报价。请求阶段不占用资源。
3. 护理师开始任务，完成时填写观察、给主人的建议、体重与实际耗材。
4. 护理记录、库存扣减、服务状态、最新体重在同一事务内提交；缺货时全部回滚。
5. 前台按实际收到的钱登记分次收款。重复请求不会生成第二张同样的收款记录。
6. 未开始服务可取消，已付款部分形成可退余额；店长选择原收款记录登记退款。
7. 店长查看真实 SQL 汇总的经营报表和低库存，维护人员、资质、班次、服务及工位。

宠物删除：顾客在 **My pets**、前台／店长在 **Customers & pets** 点击宠物旁的 **Delete**，确认后可删除没有预约历史的档案。有预约历史时显示 **Deactivate**，需先完成或取消未结束的预约；宠物列表默认隐藏已停用宠物；点击 **View inactive pets** 可查看档案及护理历史，但不能用于新预约。重新启用可编辑档案并勾选 **Active profile**。顾客只能操作自己的宠物。

金额均为 AUD，时间显示与业务日界均使用 Australia/Sydney。过去护理记录不可覆写。档案使用停用状态，不删除有历史关联的数据。

范围为单店洗护 / 造型：不含寄养、零售、会员积分、在线支付、短信和邮件发送。网站收退款功能登记线下资金实际流动，不会自动扣银行卡。完成后的服务不走“取消退款”流程；售后赔偿不在这一版范围内。

## 数据库与技术资料

- `database/01_schema.sql`：18 张业务表、主外键、基本检查、索引、3 个视图。
- `database/02_rules.sql`：排除约束、业务触发器、库存/财务保护、登录会话。
- `database/04_hardening.sql`：历史记录保护、身份保护、账户类别分离。
- `database/05_care_roles.sql`：护理角色、资质与任务分配保护；增量升级，不清空既有数据。
- `database/06_english_demo_data.sql`：一次性翻译既有演示文本，保留记录 ID、关联、金额、时间与状态，结构版本升至 4。今后用户输入不限制语言；后续启动不会重复翻译。
- `database/03_queries.sql`：7 个代表性 SQL 查询。
- `docs/database-design.md`：实体、关系、候选键、函数依赖、3NF/BCNF 说明。
- `docs/transactions-and-demo.md`：事务边界、失败回滚、并发、3 分钟演示脚本与测试证据。
- `docs/schema-inventory.json`：从实际 PostgreSQL 导出的表、列、约束和数据行数清单，不含密码。

结构：`backend` 后端，`frontend/src` 页面，`database` SQL，`tests` 自动化测试，`tools` 连接与检查工具。

## 验证

本轮英文版与用户管理包含 46 项后端测试、14 项 Chrome 浏览器测试，新增旧数据迁移检查，结果见 [本轮验证报告](docs/english-and-accounts-2026-10-15.md)、`test-results/english-backend.xml` 和 `test-results/browser.json`。测试使用独立数据库。上轮六项缺陷的修复保留在 [历史报告](docs/fix-report-2026-10-14.md)，其“内容完全一致”描述仅对应当时修复；本轮按要求翻译既有文本，保留所有非翻译字段。

先让本项目 PostgreSQL 运行，然后执行：

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe tools\check_browser.py
```

测试会创建随机命名的独立测试数据库，结束后仅删除自己创建的测试库，不改动演示库。浏览器测试使用本机 Google Chrome；测试结果与截图在 `test-results`。前端构建命令：`cd frontend` 后执行 `npm run build`。

API 接口目录在 `/api/docs`。写入接口需要同源请求和 `X-PawCare-Client: web`，可使用前端操作或测试脚本调用。

## 数据保存与故障排查

- 实际数据位于 `.runtime/postgres-data`，正常退出和重启不会清空。初始演示数据只在空数据库中插入一次。
- 演示排班以首次初始化日期生成，覆盖其前 14 天至后 45 天。后续日期请由店长添加班次。
- 缺少可用护理师：检查服务资质、班次是否覆盖整个服务，以及相同员工/工位/宠物是否已占用该时间。
- 重复运行时会自动打开已在运行的 PawCare；若 8000 被其他程序占用，可指定 `--port 8001`。
- pgAdmin 连接失败：确认项目数据库已经启动，端口是 55432，密码文件路径有效。
- PostgreSQL 启动信息在 `.runtime/postgres.log`；程序只绑定本机回环地址。
- 备份可使用 pgAdmin 对 `pawcare` 执行 Backup，或运行 `.\.venv\Scripts\python.exe tools\backup_database.py`，生成 `.runtime/backups` 中的 PostgreSQL 备份和业务数据校验文件。备份包含实际数据；分享源码不应包含 `.env`、`.runtime`、`.venv` 或 `node_modules`。

使用已有 PostgreSQL 时：管理员创建空数据库和应用角色，依次执行 `01_schema.sql`、`02_rules.sql`、`04_hardening.sql`、`05_care_roles.sql`、`06_english_demo_data.sql` 并授权；复制 `.env.example` 为 `.env`，设置 `MANAGED_POSTGRES=0` 及真实连接信息。用后端 `seed()` 按需填充空库。外部实例启停由使用者管理；当前托管模式的测试和备份工具依赖项目管理配置，不是通用外部库工具。

作业展示时，请按课程要求说明 AI 辅助范围，并由小组成员理解、验证并能够解释提交的代码与数据库设计。贡献记录、最终视频和教学团队的贡献模板需由小组按实际情况完成。
