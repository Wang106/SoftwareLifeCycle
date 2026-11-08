# 离线数据库证据检查 / Offline database evidence checklist

## 本包边界

此工具仅比较一个本地 JSON 文件与固定检查项。它不连接数据库，不读取环境配置，
不启动 Docker、应用或数据库，不运行迁移，不创建角色、授权或凭据，不上传文件。
`deploy/offline/database-readiness.sql` 是供**以后另行明确获准的操作员**使用的 psql 16
脚本，本包未运行。现在不得据此连接公司服务器、旧公共数据库或任何其他真实数据库。
现有生产、Compose、预检及 CI 工作流均未接入此检查器。

本包测试只使用合成 JSON、临时本地文件和 SQL 文本断言。没有 PostgreSQL 执行证据，
不能称 SQL 语法已验证、实际权限已验证、数据库只读安全、应用就绪或离线验收完成。
`READ_ONLY_MODE`、`PGOPTIONS`、操作员自报和本工具返回码都不能单独证明这些结论。

## 三种结果

- `CHECKLIST_MATCHED`，退出 0：输入结构有效，所报各项符合这一固定清单。
- `CHECKLIST_MISMATCH`，退出 1：输入结构有效，至少一个报告项不符合清单。
- `UNKNOWN`，退出 2：文件、格式、类型或报告内部关系不可用，不能判断。

退出 0 **不是准许启动或部署的门禁**。JSON 是不可信、自报证据，可伪造、复制、过期；
检查器不能核实数据库/角色身份、采集进程退出码、来源提交、时间、新鲜度或后续变更。
一个人为填好的全零危险项文件也会匹配，测试中的“通过”样例正是人工合成，不是真实证明。
报告不回显路径、未知键值、原始 JSON、SQL 错误、用户、数据库名、业务行或连接串。

## 固定清单及保守拒绝

证据格式为 `slc-offline-database-evidence-v1`，单一扁平 JSON 对象，只允许下面的键。
除固定格式字符串外均为布尔值或计数；迁移未读取时两个计数必须为 JSON null。

| 字段 | 类型及匹配要求 |
| --- | --- |
| `format` | 必须为上述固定字符串 |
| `server_version_num` | 整数，160000 ≤ 值 < 170000，即 PostgreSQL 16 |
| `transaction_read_only`, `session_role_unchanged` | 必须为 true |
| `role_count`, `app_schema_count` | 必须为整数 1 |
| `role_superuser`, `role_create_db`, `role_create_role`, `role_replication`, `role_bypass_rls` | 必须为 false |
| `database_create`, `database_temp` | 当前数据库有效 CREATE / TEMP 权限必须为 false |
| `role_membership_count` | 角色作为成员或被授予角色出现的直接成员关系数必须为 0 |
| `owned_object_count` | 当前数据库及共享对象中的角色所有权依赖数必须为 0 |
| `schema_create_count` | 对任何 schema 具有有效 CREATE 权限的数量必须为 0 |
| `table_write_count` | 当前数据库所有 schema 中有 INSERT/UPDATE/DELETE/TRUNCATE/REFERENCES/TRIGGER 任一有效表权限的适用关系数必须为 0 |
| `column_write_count` | 当前数据库所有 schema 中有 INSERT/UPDATE/REFERENCES 任一有效列权限的适用列数必须为 0；不能用表级检查代替 |
| `sequence_write_count` | 当前数据库所有 schema 中具有 USAGE 或 UPDATE 权限的 sequence 数必须为 0 |
| `routine_execute_count` | 非系统 schema 中有 EXECUTE 权限的 routine 数必须为 0，包括 PUBLIC 默认授权 |
| `unexpected_schema_count` | 除 public、pg_catalog、information_schema、pg_toast 外的 schema 数必须为 0 |
| `unsupported_relation_count` | 下面所述不支持关系的数量必须为 0 |
| `unsupported_type_count` | 非系统 schema 中除复合类型及其数组外的类型数量必须为 0 |
| `unsupported_object_count` | 下面列出的额外对象数量必须为 0 |
| `large_object_count` | large object 元数据记录数必须为 0；不读取其内容 |
| `migration_table_present`, `migration_table_supported`, `migration_select_permitted` | 三项必须为 true |
| `migration_row_count`, `migration_expected_head_count` | 均为整数 1；只检查最多两行 |

所有整数必须是 JSON 整数字面量、非 bool、非负且 ≤ 2^63−1；迁移计数还必须 ≤ 2，
匹配头计数不能超过行数。拒绝缺失/额外字段、重复键、错误版本、null 代替普通字段、
浮点/指数形式、NaN、Infinity、指数溢出及不合法编码。错误信息不包含原输入。

权限使用限定名称的 `pg_catalog.has_*_privilege` 内置函数观察当前有效权限，
不只读取 ACL 文本。**所有成员关系均拒绝**，不尝试证明 PG16 的递归 INHERIT、SET ROLE、
ADMIN OPTION 等复杂权限图安全，也不切换角色。当前角色必须等于会话角色。
所有权通过 `pg_shdepend` 的 owner 依赖观察，不把 ACL 中无写授权误认为无所有权能力。
全 schema 写权限检查可能因系统 view 的 PUBLIC 授权而保守不匹配，例如安装中存在
`pg_settings` 的 PUBLIC UPDATE 授权时；数据库默认 PUBLIC TEMP 也会不匹配。
本包未实测任何 PostgreSQL 安装的默认 ACL，不承诺新建普通只读账号就能匹配。
不得静默豁免这些权限，也不得为取得匹配而改权限；需要单独获准的权限方案与真实验证。

支持固定 public 应用 schema 中持久的普通 heap 表、内置访问方法索引和 sequence。
view、materialized view、foreign table、partition/inheritance、临时/不记录日志关系、
RLS 或 rewrite rule 等均拒绝。额外空 schema 和其他会话遗留的临时 schema 也拒绝，
这可能造成保守的误拒绝；不得为了匹配静默删除对象或放宽规则。
额外对象包括非 plpgsql 扩展、FDW/server、event trigger、publication、非内置语言、
非系统 schema 的 collation、conversion、operator、operator class/family。
这不是所有 PostgreSQL 对象类别或所有系统函数副作用的完整审计。

允许报告数为 0 不代表已证明无未来授权、无默认 ACL 影响、无扩展漏洞、无系统函数风险、
无外部权限或其他数据库权限。真实隔离需要单独设计、审核并在获准目标验证。
新对象或后续 GRANT/REVOKE、DDL、角色变更会使证据失效；不得自动“修复”这些条件。

## 迁移 bookkeeping 的读取保护

脚本先只查系统目录，核实 `public.alembic_version` 是持久普通 heap 表，无继承/分区、
RLS、rewrite rule 或非内部触发器；唯一用户列必须为非空、无默认/生成/identity 的
`version_num VARCHAR(64)`，符合当前 `backend/alembic/env.py`。
附属索引仅允许有效、ready/live、无表达式/部分谓词且使用 pg_catalog operator class 的
内置 btree 索引，包括正常 Alembic 主键；自定义访问方法可能在规划/读取时调用代码，
故先拒绝而不是仅在读完版本后报告。此保护仍以受信、未篡改的系统目录为前提。
随后检查该列有效 SELECT 权限。只有这两道检查成立才让 psql 发送版本查询；
否则两计数为 null，检查结果不匹配。不是用 SQL CASE 包住一个缺失表查询来假装可执行。

版本查询仅 `FROM ONLY public.alembic_version LIMIT 2`，使用固定 C collation，
只返回总数及等于 `0029_changeover_batch_history` 的数量，不输出版本原文。
0 行、错误头、多行（包括两个相同头）全部拒绝。此匹配并不证明迁移实际全部运行、
业务表完整、约束/数据正确或 schema 未被改动；它只是固定 bookkeeping 检查。
版本表不是业务数据表，本脚本不读取其他非系统表的任何行。

## 以后另行获准时的操作员顺序（当前不执行）

1. 取得针对**明确隔离的合成 PostgreSQL 16 目标和现有只读账号**的执行许可。
   操作员独立确认目标/账号和受信 server/catalog，确认只有合成数据、无并发 DDL/授权变更。
   不使用业务/公司库，不使用超级用户、迁移账号或通过 SET ROLE 伪装账号。
   本包不授权配置账号、撤权、上传、安装工具或修改任何权限。
2. 独立核对获准 checkout 提交及该 SQL 的原始内容；不要从证据自报摘要推导可信来源。
   使用已安装的 psql 16 和此前获准的连接方式，明确选定目标。不要依赖隐含默认库、
   `PGHOST` 或其他遗留连接环境，不把凭据、URL 写入命令记录或证据。
3. psql 必须带 `--no-psqlrc --quiet --tuples-only --no-align --no-password`、
   `--set=ON_ERROR_STOP=1`、`--file=deploy/offline/database-readiness.sql`，并通过获准
   的安全方式明确指定目标；连接超时设置为 5 秒。此处不提供可直接误连默认库的连接命令。
   操作员设置整个采集进程不超过 30 秒的外部截止时间，不在本工具中启动该进程。
4. 标准输出与错误输出分别保存到**新建、私有、本地普通文件**，禁止覆盖旧证据。
   SQL 内部再次启用 ON_ERROR_STOP，设置只读 REPEATABLE READ 事务、5 秒 statement timeout、
   1 秒 lock timeout、15 秒 idle-in-transaction timeout 和固定 pg_catalog search_path。
   通过 psql 的 `\gset` 暂存有限结果，在 ROLLBACK 成功后才输出一个 JSON 文档。
5. **先检查真实 psql 退出码为 0**，并确认没有超时/中断/连接丢失，再使用新证据文件。
   SQL 错误、权限不足或任一步失败不得当作 0 计数，不得复用旧文件或手工补齐字段。
   即使因断线等原因已有一份完整输出，非零退出或不确定退出仍不得使用。
   原始 stderr 可能含路径/目标信息，留在私有诊断中，不上传、不复制到报告。
6. 对该文件仅运行以下离线命令，替换成实际的新文件绝对路径：

   ```sh
   python scripts/offline_database_readiness.py --evidence /absolute/private/new-evidence.json
   ```

7. 输出只是自报内容的比较结果。把执行许可、独立确认的目标/角色、checkout、采集时间、
   psql 真实退出状态及采集文件来源保留在获准私有操作记录中，不填入本 JSON、公开报告或
   仓库。清单不匹配时停止并单独审核，不创建权限、不自动重试、不降低门禁。

只读事务不是沙箱：恶意 view、RLS、类型/函数、扩展和外部系统副作用可能不受它限制。
限定系统函数与版本表形状是减少风险的设计，不能替代对 server/目标的信任。
目录检查与版本查询间仍有 DDL/权限并发及解析时序限制，本脚本没有锁定整个数据库，
不得在恶意或并发变更的库上执行并称其无副作用。未来真实执行验证需另行获准。

## 本地读取与测试边界

只支持具备 `dir_fd`、`O_DIRECTORY`、`O_NOFOLLOW`、`O_NONBLOCK` 的 POSIX 环境。
要求不含 `..`、`.`、空分量、控制字符或反斜杠的绝对路径，长度 ≤4096、分量 ≤256。
逐级固定目录描述符，拒绝父/叶 symlink；非阻塞打开后仅接受大小 1..16384 字节的普通文件。
读取不超过初始大小+1，并比较读取前后 inode/device/size/mtime/ctime；不重开路径。
替换路径仍只可能读到原打开对象，观察到变更时保守拒绝。硬链接不被识别为恶意，
恶意文件系统或同时拥有文件控制权的进程仍可能伪造稳定内容；这不是来源认证或防篡改证明。
原生 Windows 等不满足能力要求时返回 UNKNOWN，不使用跟随链接的降级方式。

本包可运行的检查均不需网络、数据库或额外安装：

```sh
python -m unittest discover -s backend/tests -p test_offline_database_readiness.py -v
python -m unittest discover -s backend/tests -p 'test_offline*.py' -v
python -m unittest discover -s scripts/automation/tests -v
python -m unittest discover -s scripts/ci/tests -v
python -m py_compile scripts/offline_database_readiness.py backend/tests/test_offline_database_readiness.py
git diff --check
```

合成测试覆盖各危险权限、成员/所有权/列授权、未知对象、迁移缺失/错误/多行、严格 JSON、
超限/重复键/非有限值、文件路径/链接/并发变更及诊断不泄露。SQL 测试只检查文本契约，
不证明 PostgreSQL 能执行或权限观察正确。后续必须单独验证真实 PG16 正反例与失败流程，
再讨论获准的应用启动、备份恢复和物理断网；本包不增加业务/部署验收百分比。
