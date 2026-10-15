# English interface and account management / 英文化与用户管理

Date / 日期：2026-10-15。Target / 目标环境：Windows、Python 3.12、Node.js 22、PostgreSQL 16、Chrome。

## Changes / 更新

- Customer and staff interfaces, errors, date formatting and default database content use English. The README includes both English and Chinese instructions. Future user-entered names and notes remain unrestricted.
  顾客端、员工端、提示、日期格式及默认数据统一英文，README 提供中英文说明；今后的姓名和备注不限制语言。
- Existing registration was reviewed and retained at the user's request. Only its displayed text was translated.
  按用户最新要求保留原有注册入口与流程，仅翻译展示文字。
- Managers have **User accounts**: name/email search, role/status filters, account/profile status, activation/deactivation, and password reset. Other roles cannot use these endpoints. Employee creation and qualifications remain in **Employees & shifts**.
  店长新增用户管理，可搜索、筛选、启停与重置密码；其他角色不可调用。员工创建和资质管理仍在员工页面。
- Deactivation/reset revokes old sessions; passwords/hashes are never returned in the list. Staff status also controls scheduling eligibility. Unfinished staff tasks and manager self-deactivation are protected. Customer profiles/history are retained.
  停用或重置密码后旧会话失效；列表不返回密码或哈希。员工状态与排程资格同步，未结束任务与管理账号自停用受到保护，顾客档案和历史保留。

See the prior [account review / 功能评审](account-management-review.md).

### Follow-up: stale login pages / 旧登录页问题跟进

The user reported a Chinese login page with an English authentication banner, while a fresh browser visit to the running server showed the English page. The HTML response had no explicit cache policy. HTML now uses `Cache-Control: no-store`, and both normal and repeated launcher runs open a unique `?launch=…` URL to avoid previously cached entry pages. Authentication initialization uses HTTP status 401 to show the login form quietly; successful login/logout also clears any previous startup error. Invalid submitted credentials and actual server failures remain visible.

用户反馈中文登录页及英文红色提示；新打开运行中的服务则显示英文。发现首页未设置明确缓存策略，现已禁止 HTML 缓存，首次和重复启动均使用带唯一参数的新地址。初始化收到 401 时安静显示登录表单，登录成功或退出时清除先前启动错误。输错密码及实际服务故障仍正常提示。

Regression checks cover anonymous visits/reloads, invalid sessions, logout, wrong-password feedback, recovery from an initial service error, and HTML cache headers. Screenshot: `test-results/english-login.png`.

新增验证覆盖未登录首次访问/刷新、失效会话、退出登录、错误密码、服务恢复和首页缓存头；截图为 `test-results/english-login.png`。

### Follow-up: VS Code PowerShell / VS Code 终端修复

The Windows terminal error was reproduced: Windows PowerShell 5.1 inherited a PowerShell 7 module directory and attempted to load its incompatible `Microsoft.PowerShell.Security` module. Workspace terminal settings now remove the inherited `PSModulePath` so each new shell discovers its own modules. F5 also explicitly selects `.venv/Scripts/python.exe`. Fresh-shell module loading, environment activation and interpreter checks passed, followed by an actual VS Code F5 startup and HTTP health check. Global execution policy and application/database logic were not changed. Evidence: `test-results/powershell-verification.json`.

已复现错误：Windows PowerShell 5.1 继承 PowerShell 7 模块目录，误载不兼容的安全模块。工作区配置现已为新终端清除继承的 `PSModulePath`，让终端使用自身模块；F5 明确选择项目解释器。新进程模块加载、环境激活、解释器检查及 VS Code 实际 F5 启动、健康检查通过。全局执行策略及应用/数据库逻辑未修改，证据见 `test-results/powershell-verification.json`。

VS Code supports removing inherited terminal environment variables with `null`: [official terminal profile documentation](https://code.visualstudio.com/docs/terminal/profiles).

## Existing data / 既有数据

Schema version 4 applies `06_english_demo_data.sql` once. It translates exact known legacy values and preserves all other values. A private PostgreSQL dump was created before migration. The package contains no live data or local credentials.

版本 4 仅执行一次精确映射翻译，迁移前已保存私有数据库备份；交接包不含实际数据库或本机密码。

Verification compared every row in all **18 business tables** with an expected copy that changed only the mapped text: **58 text cells translated**, **0 remaining Chinese text cells** at delivery verification. Counts remained unchanged, including **15 appointments, 6 pets, 8 payments and 9 care records**. IDs, foreign keys, amounts, timestamps, statuses and password hashes were preserved. This statement concerns the migration snapshot, not later manual edits.

逐行对比 18 张业务表，只有 58 处指定文本发生翻译，检查时无剩余中文文本；15 条预约、6 只宠物、8 条收款、9 条护理记录均保留。编号、关联、金额、时间、状态和密码哈希未变；此结论针对迁移快照，不包括之后的人工操作。

An upgrade test exposed pending deferred constraint events when re-enabling history guards. The migration now completes those integrity checks before restoring the guards. All business triggers were confirmed enabled after commit. Failure rolls back the text updates and trigger changes together.

已修复旧护理数据升级时延迟约束检查阻止恢复触发器的问题；先完成完整性检查，再恢复保护。提交后确认业务触发器全部启用；失败时数据与触发器变更整体回滚。

Evidence / 证据：`test-results/english-data-verification.json`、[schema inventory / 结构清单](schema-inventory.json)。The business schema and functional dependencies are unchanged; the existing 3NF/BCNF analysis still applies.

## Regression / 回归测试

All **46 backend and 14 browser cases passed**, with results in `test-results/english-backend.xml` and `test-results/browser.json`. Coverage includes the earlier six fixes, dog/cat booking and prices, qualification/shift/resource conflicts, care and stock transactions, payment/refund limits, reporting, role isolation, mobile navigation, existing registration, account controls, password/session invalidation, unrestricted multilingual input and migration of completed history. Tests use disposable databases.

46 项后端与 14 项浏览器用例全部通过，覆盖原六项缺陷、猫狗预约与价格、排班与资源冲突、护理库存事务、收退款、报表、角色隔离、移动端、原注册流程、账号启停、密码会话失效、多语言输入及旧护理记录迁移。测试使用独立临时数据库。

TypeScript checking and production frontend build passed. A Starlette/httpx deprecation warning remains in the test dependency integration; it does not cause test failures. These checks establish the tested flows and do not claim that every possible defect is absent.

TypeScript 检查与前端构建通过。测试依赖仍有一条 Starlette/httpx 弃用提醒，不影响用例结果；验证范围为已覆盖流程。

## Team package / 小组交接

Use the bilingual [README](../README.md) and [AI setup guide](../AI_SETUP.md). The ZIP includes source, SQL, dependency locks, VS Code configuration, tests and verification evidence. Each teammate generates independent credentials and English seed data. Do not overwrite an existing `.runtime` directory or distribute private backups.

请使用中英文 README 和 AI 配置指南。压缩包含源码、SQL、锁文件、VS Code 配置、测试与验证证据；每位成员生成独立密码和英文样例数据。不要覆盖既有 `.runtime`，也不要分享私有备份。

Fresh-copy verification **passed**: a new virtual environment, locked Python/frontend dependency installation, frontend build, independent PostgreSQL initialization, English seed scan, schema version 4 health check, static assets, four-role login/read access, manager account listing, and repeated startup. The original business database fingerprint remained unchanged throughout this check. Results are recorded in `test-results/package-verification.json`; its source hashes identify the tested executable/configuration files even though the final package includes this updated report and evidence.

全新目录验证全部通过：新虚拟环境、锁定依赖安装、前端构建、独立 PostgreSQL 初始化、英文种子数据扫描、版本 4 健康检查、静态资源、四角色登录、用户管理查询、重复启动。此检查期间原业务库指纹完全一致。结果写入 `test-results/package-verification.json`，文件哈希用于确认最终包内运行代码与配置和已验证版本一致。
