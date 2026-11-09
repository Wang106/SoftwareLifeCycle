# PG16有限目录观察准备

## 状态与范围

基线main `1e2f0f6ecb34ac7b35da52c0e84938e5d1d3a46c`，PR204。
新增仅标准库的目录采集函数、mock回归、独立真实PG16回归准备与本说明。
本地开发未连接数据库、执行SQL/DDL、启动容器或下载依赖；真实回归尚待明确获准的正常候选CI。
不修改workflow、依赖、迁移、应用源码、数据库权限或既有安全/汇总门禁。

PR204的120事实是固定public命名空间的源码有限投影，不是实测数据库结构。
本包不改该清单、不调用其MATCHED判断、不把随机测试schema换名为public。
目录观察与源码表达式映射分别记录，不能靠字符串规范化制造匹配。

## 采集接口与事务所有权

`scripts/offline_pg_catalog_evidence.py`仅提供`collect(connection, namespace)`。
connection必须是调用方已打开的可信psycopg连接，cursor返回普通单列JSONB字典结果。
入口和cursor正常关闭后的出口均核对libpq transaction_status为INTRANS，
仅设置默认只读GUC但处于IDLE/autocommit的连接不能冒充同一事务。调用方不得并发操作连接。
无URL、数据库凭据、环境配置、自动连接、CLI、SQL执行参数或替代清单接口。
导入不连接数据库；采集函数仅执行固定SELECT，不begin/commit/rollback、关闭连接或修改权限。

调用方必须先在已有获准连接开启READ ONLY、REPEATABLE READ事务，并设置
search_path精确pg_catalog、statement_timeout 1..5000ms、lock_timeout 1..1000ms、
idle_in_transaction_session_timeout 1..15000ms。采集器先观察这些条件与PG16版本，
按绑定的精确namespace读取唯一pg_namespace OID，再以该OID执行六组固定目录查询。
namespace只能是1..63字符的小写ASCII标识，拒绝系统schema；对象仍保留实际schema名称。
不存在的namespace、条件不符或任一异常均失败，不替换为public或其他同名对象。

调用方独占事务及最后的commit/rollback，采集器不得回滚调用方的既有事务。
成功输出`transaction_completed=false`，不证明事务已结束；SQL错误后调用方自行处理失败事务。
只有所有固定查询、类型/资源检查和cursor.close均成功才返回完整对象，异常只抛固定
`CATALOG_COLLECTION_FAILED`，不返回部分观察、不重试、不打印原始异常或连接信息。
进程中断或连接丢失不保证调用方事务已清理，不能使用旧结果充当本次完成回执。

READ ONLY事务不是安全沙箱，系统目录和内置反解析函数亦依赖可信服务器/扩展环境。
调用方应只用于明确批准的合成目标。此接口不会核实账户身份、授权、网络隔离、无并发DDL、
服务真实性或证据新鲜度，不应接任意不可信数据库。

## 输出是观察，不是放行

输出format为`slc-pg16-catalog-observation-v1`，状态恒为
`CATALOG_COLLECTED_NOT_ACCEPTANCE`，包含实际namespace/OID、PG版本及六组观察。
`database_verified=false`、`complete_schema_verified=false`始终保留。
空的观察集也是采集结果，不是迁移成功；缺失对象不填默认值。
结果只在调用进程内返回，不写文件或上传，不是经签名的来源证据。

固定选定对象：alembic_version、releases、release_snapshots、0029四张历史表；
3个0029函数；四张历史表及两个物理事实表上的6个固定触发器。

- tables：实际名称、relkind、持久性、访问方法和RLS标志；不支持的形状可能直接失败。
- columns：选定表实际列名/顺序、format_type原文、not-null、identity/generated。
- constraints：实际约束名、类别、有序列、FK目标真实namespace/表/列、
  validated/deferrable及pg_get_constraintdef原文。
- indexes：选定表实际索引名、访问方法、unique/valid/ready/live、
  pg_get_indexdef和pg_get_expr谓词原文，不只比较名称。
- functions：固定名字的实际签名、结果、语言、security-definer，
  pg_proc.prosrc原始UTF-8 SHA256与字节数。原函数体仅暂存内存，结果不输出函数体。
- triggers：固定名字和实际表/函数schema/签名绑定、tgtype位集、tgenabled、
  internal/constraint标志及pg_get_triggerdef原文。

不读取业务表行或alembic_version内容，不验证全量schema、数据、权限、函数行为、
触发器会话行为或真实部署。真实测试fixture另外读取自己新建版本表确认迁移头；
该操作不是采集函数的一部分，也不应推广到未经许可的目标。

表达式保留PG反解析原文，不删除括号、cast、schema或条件，不将其伪装成迁移源码字面量。
函数摘要不strip/改换行。首次真实CI将独立比较prosrc和0029源码SQL的原始$$内字节；
在此之前该映射仍是待验证假设。即使字节相同也不证明search_path、依赖或函数执行安全。

## 资源与失败边界

固定7条SELECT；每组SQL LIMIT为预算+1，客户端fetchmany取同一上限，多一条即失败，
不把截断数据当完整观察。预算分别tables8、columns512、constraints256、indexes128、
functions16、triggers32。标识与固定组的重复记录、结构/类型错误均拒绝。
动态文本在SQL端取至16385字符，客户端再要求UTF-8不超过16384字节；多字节文本超限拒绝。
数组最多32个标识，字段类型严格，不接受bool代整数。累计JSON观察不超过512KiB。

固定每条SQL的statement timeout限制数据库执行，不能保证驱动、恶意服务器、网络中断或
内核I/O的严格总时限；调用方必须另外管理连接/进程生命周期。客户端预算不声称
PostgreSQL反解析函数内部或驱动缓冲零开销。原始表达式可能包含schema标识，
仅返回给获准调用方，不应公开原始观察或凭据。固定错误不会回显这些内容。

## 真实CI回归的限定执行范围

新模块`backend/tests/test_pg_catalog_evidence_postgres.py`不在本地mock命令中执行。
普通导入只加载定义；fixture在任何连接之前要求GITHUB_ACTIONS=true、CI=true、
GITHUB_REPOSITORY=Wang106/SoftwareLifeCycle，且TEST_POSTGRES_URL精确使用
postgresql+psycopg、127.0.0.1:5432、software_lifecycle_ci、slc_ci、非空密码、无URL选项。
每次连接前拒绝任何PG*环境覆盖（包括空值），防PGHOSTADDR、service/options等覆盖固定连接目标；
不静默清除后重试，不提供本地或外部目标回退；不满足时失败而非跳过，现有完整CI零跳过门禁保持。
这些环境检查是防误用边界，不是对恶意伪造环境/loopback隧道的安全证明。

只复用现有标准runner自带的一次性PG16服务，不新增付费资源或容器。
每个case生成新的ci_catalog_<随机UUID>，CREATE后记录OID，原样执行现有
0001→0029链（固定Python模块命令、90秒上限、无seed/stamp/create_all）。
迁移连接search_path仅该自有schema；不操作public、旧公共数据库或公司数据库。
只在本次schema构造反例，不GRANT/REVOKE、不建角色、不改数据库权限。
结束时精确核对本次namespace/OID/当前所有者后仅DROP该schema，身份改变即停；
不按前缀搜索删除、不重试、不删数据库。迁移失败仍尝试有已确认身份的本次清理；
进程/runner丢失不能保证清理完成，必须保留失败结果，不能宣称无条件清理成功。

准备8个真实测试：原链和prosrc/复合FK/部分索引映射；禁用触发器；函数体变更；
列类型变化与缺表；partial index取消唯一性；不存在精确namespace；错误事务与IDLE/autocommit默认GUC拒绝。
断言只描述该合成schema实测结果，不生成public清单的MATCHED或真实只读角色认证结论。
后续迁移镜像执行、完整目录证明、物理断网、备份恢复和公司部署仍需独立设计及许可。

## 本地验证记录

首批16项缺能力回归全部先失败，再实现。独立初审发现INTRANS与PG*环境覆盖两项阻断，
在具体通知并等待后新增4测试方法先得到8失败，再收紧新采集器/fixture。
最终26集中、594全离线零跳过、52自动化、126守卫及Python编译、进度账本、diff检查通过。
8项真实PG测试只准备尚未执行；完整后端/PG/前端/严格浏览器待精确候选CI。
独立复审通过，无新阻断：另26项mock及12种非INTRANS/错类型状态拒绝验证通过；
各真实fixture连接前PG*拒绝已检查。未提交或上传，仍未实测PG。
