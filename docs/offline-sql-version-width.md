# 离线迁移SQL版本列兼容

## 范围和证据

基线main `3f34222734634f6a86ee4d83bebc91c7e4877221`（PR208），开放PR为0。
基线CI42624219335完整成功，Actions deployment42626540037与continuation42626540008均skipped。
这些是基线证据，不是本包CI；后端线上健康与公司部署不由本包证明。

现有online env.py在遍历前将版本列建为/扩为VARCHAR(64)，offline SQL原来仍由Alembic默认
VARCHAR(32)生成，而0008_authorization_distribution_link有35个字符。现有CI只检查生成SQL非空，
实际往返走online路径。本轮先以标准库AST/受控stub回归得到3失败1通过，再实现；本机没有
Alembic/SQLAlchemy/psycopg，未执行真实SQL生成或DB操作，不能把stub失败称作真实SQL报错。

只在env.py注册继承固定PostgresqlImpl的扩展，使用Alembic1.14.0公开version_table_impl hook。
先取得super生成的完整Table，仅as_sql为真时把version_num类型设为String(64)。
名称、schema、PK、nullable及其他PG行为保留；不更改29份历史迁移、online建表/扩列流程、
依赖、workflow或门禁。注册在进程内持续，后续online使用该子类，但hook返回原始32型Table；
online既有64列维护逻辑不变，不宣称全局registry身份没有变化。重复加载始终继承固定上游类，
不累积继承链。不访问context._version、不替换输出SQL文本。

已只读核对官方固定版本源码：
- https://github.com/sqlalchemy/alembic/blob/rel_1_14_0/alembic/ddl/impl.py
- https://github.com/sqlalchemy/alembic/blob/rel_1_14_0/alembic/runtime/migration.py

## 真实生成回归（尚未运行）

两个不连接DB的依赖型测试由正常完整CI执行：实际生成0001→0030 SQL，确认宽度/PK/30步（另保留0001→0029的29步历史回归）及事务边界；
重复加载公开hook，在offline→online→offline之间核对宽度、schema、PK和固定继承关系。
生成器用固定Python独立子进程、空临时cwd及明确合成不可用DSN，不读开发者.env。
禁止engine_from_config/psycopg.connect；stdout为临时文件，RLIMIT_FSIZE限制1MiB，60秒整段截止，
stderr不公开。生成产物仅内存用于测试，不提供公司执行入口或保存凭据。

## CI真实SQL执行回归（尚未运行）

两项PG测试只接受既有repository/CI身份、精确127.0.0.1:5432/software_lifecycle_ci/slc_ci及PG16，
拒绝任何PG*覆盖。复用已有ci_url/观察函数，但不复用会先online迁移的fixture。
各自新建ci_sql_<UUID>空schema，记录OID；不读取旧业务数据，不建角色或GRANT/REVOKE。
所有SQL只来自本提交现有30迁移生成内容，不接受任意SQL文件或远端输入。

1. 将未经改写的完整SQL一次交给psycopg simple query（prepare=False），不按分号拆分，保留
   $$函数/DO块及BEGIN/COMMIT。确认子进程成功、事务IDLE、唯一0030头、版本列64/NOT NULL，
   并读取有限7表/3函数/6触发器观察；不是全schema认证或公司数据验收。
2. 仅负向测试把唯一版本列64声明改为32，要求实际SQLSTATE22001（子进程专用退出32），
   并确认失败事务未留下已提交表。这个人为反例不是生产转换逻辑，也不冒充历史数据库实测。

执行器仅新连接search_path指向本次schema；固定受信子进程不继承应用环境，连接信息经stdin，
stdout/stderr不发布，90秒整段截止及每语句/锁/idle/连接限制。超时结束并等待本次子进程，
但不宣称服务器必然已停止或清理必然成功。无重试、seed、stamp、create_all、自动downgrade。

finally再次核对本次精确namespace/OID/current owner后，只DROP本次schema；身份不符、连接故障、
锁等待或其他清理不确定均失败。不按前缀扫描、不删数据库；生成SQL自身COMMIT，不能用外层rollback
假定撤销。本包不触碰旧库/公司库，不启动容器/镜像/API，不获取依赖或增加资源费用。
真实执行须本包具体发布/CI批准，不将本地代码准备视为运行授权或通过证据。

## 未覆盖范围

不提供已部署库修复、增量/任意范围SQL升级、离线迁移镜像实测、最小权限角色、物理断网、
签名来源、备份恢复或公司安装验收。业务36/44=82%、所有模块/计划比例和浏览器阶段不变。
后续应在独立审查及准确候选CI通过后记录真实生成与PG结果，再规划镜像执行边界。

## 来源摘要同步

全离线回归发现env.py新字节与原固定清单来源摘要不符。具体通知并等待后，先增加v2元数据回归，
得到来源字节、v2接受、旧格式错误接受共3失败，再更新固定清单与摘要校验器。
明确分离facts_baseline_commit历史事实基线和repository_file_sha256当前四源码绑定；
完整keys/固定基线/四路径/摘要格式严格验证，整体manifest SHA绑定、四源码字节绑定保留。
120事实以固定canonical SHA证明未改，输入证据与判定语义不变。详见原[结构证据说明](offline-migration-schema-evidence.md)。
超时修正的新增合同先失败，再只把新fixture连接statement_timeout设为5秒，符合既有观察器上限。

最终本地9集中、24结构证据、639全离线零跳过、52自动化、126守卫及Python编译/进度账本/diff通过。独立终审通过无新阻断（另33项及事实/online/历史迁移对照），真实2生成/hook与2PG仍未运行。未提交或上传。

## PR209真实执行后的百分号修正

首轮CI42644528445在生成SQL正例报deployment_actual_baselines%%ROWTYPE语法错误，
32宽反例成功捕获实际截断错误，整体3501通过1失败。固定依赖SQLAlchemy的pyformat方言
把源码%编译成%%；offline文件作为完整SQL直接交给无参数simple query时不应保留DBAPI转义。
只在offline configure设dialect_opts={"paramstyle":"named"}，与Alembic1.14官方模板一致：
https://github.com/sqlalchemy/alembic/blob/rel_1_14_0/alembic/templates/generic/env.py#L46
不改历史迁移、不后处理生成文本、不改online或URL的ConfigParser转义。
标准库参数合同先1失败9通过，修后10通过；实际生成测试追加准确单%ROWTYPE与禁%%ROWTYPE。
同步env SHA/manifest SHA但不改120事实。只读环境下通过正规编辑/临时测试许可执行，
没有本地安装依赖、真实生成SQL或连接PG；修后实际PG正例仍须新精确CI。本地640全离线、52自动化、126守卫及内存编译/进度/diff通过；独立复审另15项只读检查通过，无新阻断，online AST/29迁移/120事实及来源绑定均复核。
