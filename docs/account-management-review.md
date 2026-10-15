# 账号功能评审 / Account management review

评审日期 / Review date: 2026-10-15。此评审先于本轮账号迭代实施。

## 已有能力 / Existing functionality

- `frontend/src/main.tsx` 的 Login 组件已有顾客注册切换，但入口仅是登录表单底部文字链接，缺少清晰的注册导航与确认密码。
  Customer registration exists, but its entry is a small link below the sign-in form, with no prominent registration navigation or password confirmation.
- `backend/auth.py` 已有 `/api/auth/register`，以单事务创建账号、顾客与绑定关系，并自动登录。
  The registration endpoint creates the account, customer profile and binding atomically, then signs the customer in.
- `backend/catalog.py` 支持顾客档案及员工管理，员工可由店长修改角色、启停及密码；顾客登录账号没有统一管理页面。
  Customer profiles and employee management exist, including employee roles, status and password changes; there is no unified account administration page.

## 本轮迭代 / Planned iteration

1. 用户已确认找到注册入口，取消注册功能改造。本轮保留已有注册入口和流程，仅翻译界面文字，并保留注册回归验证。
   The user located registration and cancelled its redesign. Preserve the existing entry and workflow, translate its text only, and retain registration regression checks.
2. 仅店长可访问 User accounts：搜索姓名/邮箱、按角色与状态筛选、查看账号与档案状态、启停登录、重置密码。
   Add manager-only account search, role/status filters, account/profile status, login activation/deactivation, and password resets.
3. 员工创建和角色/资质调整保留在 Employees & shifts；自助注册只能创建顾客，不能选择店长或员工角色。
   Keep employee creation and role/qualification changes in Employees & shifts. Self-registration creates customers only.
4. 启停登录不删除顾客、宠物、预约、护理或资金记录。停用员工账号时检查未结束护理任务；禁止停用自己的管理账号，保护最后一个有效店长。
   Preserve all business history. Block deactivation of staff with unfinished care tasks, self-deactivation and removal of the last active manager.
5. 停用账号和重置密码撤销该账号的旧会话；接口不返回密码或密码哈希。员工登录与排程启用状态同步；停用的顾客档案需要先在档案页恢复，再启用登录。
   Revoke sessions on deactivation/reset and never expose passwords or hashes. Synchronize staff access with scheduling eligibility; inactive customer profiles must be restored before login is enabled.

## 验收 / Acceptance

保留原有注册验证；验证角色越权拒绝、启停效果、重置后旧会话失效、旧密码失效、新密码可登录，以及历史数据保留。

Retain existing registration tests. Test role restrictions, activation/deactivation, session revocation, password reset, and preservation of business records.

界面及默认演示数据使用英文；按用户确认，今后手动输入不限制语言。业务表结构不因本次账号界面扩展而改变。

The interface and default data use English. Future user-entered text remains multilingual as requested. This account UI extension does not require changes to business-table structure.
