# CI合成PostgreSQL支持的只读API启动回归准备

## 当前范围

本包基于main `08dae2b6ca91a3d3b53843ac99725e3ce7a178b5`（PR205），新增标准库
API子进程/HTTP探针助手、本地API/HTTP mock回归和两项真实CI集成测试，不修改生产源码、迁移、依赖、
Dockerfile、workflow或既有门禁。本地没有连接数据库、执行DDL、绑定监听器或启动API。
真实测试须在针对本包上传/CI的明确批准之后，由现有完整CI运行；不能因文件存在自行执行。

已有health单元测试使用FakeEngine，已有离线API容器探针没有数据库且要求ready503。
本包补充的是源码uvicorn进程→实际HTTP→SQLAlchemy→CI合成PostgreSQL的连线；
不依赖尚未运行的手动迁移镜像演练，不冒充镜像、真实断网、公司安装或生产验收。

## 固定CI目标和数据库范围

真实模块复用PR205的`owned_catalog_schema` fixture。任何连接前要求Linux上的正常
GitHub Actions CI身份、仓库Wang106/SoftwareLifeCycle、明确现有
127.0.0.1:5432/software_lifecycle_ci/slc_ci目标，无URL选项、PG*环境覆盖或外部回退。
这只是防误用检查，不是抵御伪造环境、loopback隧道或恶意同UID进程的安全证明。

fixture为每项测试创建新的ci_catalog_<UUID>，在该schema实际执行原0001→0030，
不stamp、create_all、seed、不读写public。第二项额外创建本次ci_api_<UUID>空schema，
不通过手填版本号制造错误head。成功或失败均只在核对本次名字、OID及当前所有权后
清理自己的schema；不扫描前缀、删除数据库或自动重试不确定清理。

API使用同一CI角色的新连接，连接选项固定search_path为明确的本次schema，并开启
`default_transaction_read_only=on`、5秒statement/1秒lock/15秒idle超时和5秒连接超时。
这些是新连接参数，不是GRANT/REVOKE或持久数据库设置。CI角色仍拥有schema且能力较高，
默认只读事务不是SELECT-only角色、真实身份认证或不能主动更改会话设置的安全保证。
本包不建角色、不改变既有权限，不接触旧公共库或公司数据库。

## API进程与HTTP边界

`scripts/offline_pg_api_rehearsal.py`没有执行CLI，import只定义函数/类。只有真实CI测试显式
进入APIProcess时才运行。助手再次检查CI身份、PG*覆盖和精确原始数据库URL。

父进程先bind127.0.0.1随机端口0并保留socket，通过pass_fds把同一个FD交给单worker
uvicorn，避免先寻找空闲端口再释放的竞争。只使用该Popen实例管理本次子进程，不按进程名、
端口或前缀查杀。子进程用固定当前Python、-I、固定源码绝对路径和固定uvicorn程序。
新建空临时cwd避开backend/.env；环境白名单明确READ_ONLY_MODE=true、AUTH_MODE=disabled、
SEED_ON_STARTUP=false、ADMIN_OPERATOR_ENABLED=false、REQUEST_TELEMETRY_ENABLED=false，
不继承PYTHONPATH、OIDC配置、代理或其他宿主应用配置。stdout/stderr丢弃，不公开连接串。
这不是系统沙箱，CI进程仍运行于现有runner，不能推断出网络物理隔离。

直接import app.main而非生产entrypoint，不启动迁移/seed；SEED_ON_STARTUP也只是明确声明，
真正证据来自启动后空schema仍无表与已有schema有限观察保持一致。
HTTP只允许固定健康、两个有限目录、身份读取及一个业务POST路径，目标总是127.0.0.1
和本次FD的端口；使用http.client，不使用代理、不跟随重定向。响应最多64KiB，JSON重复键、
非对象和非有限常数拒绝。启动只轮询同一进程，不重新启动失败进程，不重试业务POST。

每次进程工作预算90秒、启动等待最多30秒；HTTP socket超时最多2秒，且同一次header/body交换用
SIGALRM整段截止，拒绝非主线程或已有ITIMER_REAL计时器，结束/异常恢复原处理器。
计时器取消失败仍仅尝试一次恢复原处理器；取消/恢复失败均保留固定失败，不重试或声称信号状态已恢复。
信号不能保证不可中断内核I/O、恶意扩展或runner丢失时的硬实时终止。退出发送一次terminate，
最多5秒后必要时一次kill并等待最多5秒。任何强杀、非预期退出或不确定退出均失败；
固定uvicorn0.34.0正常关闭会重发SIGTERM，故只有本次terminate后精确-SIGTERM且下面完整回执成立才接受。
只有正常确认API退出后才进行成功路径的后续目录/计数比较；启动期KeyboardInterrupt/SystemExit
也尝试一次拥有权清理并保留原中断语义，清理不确定加固定标记，不重启或重试清理。
复用的pytest fixture在失败后仍会尝试核对身份并清理本次schema，即便API退出未确认；
此时必须保留失败，不能宣称先停API再清schema的无条件顺序。强制信号/runner丢失仍不能保证清理。

## 两项真实场景及有限结论

1. 真实迁移后的新schema：ready200和固定0030 head；release/audit目录200、total0及空items；
   业务部署POST403 read_only_mode；身份读取401 oidc_not_enabled。API正常退出后，PR205有限
   目录观察、releases/release_snapshots/audit_events/deployments四表计数及版本头保持不变。
   不等于全库/所有数据未变，也不是验证全部写路由或真实OIDC。
2. 本次额外空schema：进程live正常、ready503 database_unavailable、release目录500而非
   伪造空数据、业务POST仍403；正常退出后该schema的pg_class计数仍0，没有启动迁移或seed。

真实fixture拥有迁移权限，API默认只读不是最小权限证明。即使这两项将来通过，也只证明
对应提交在CI自有合成目标的源码API/PG行为，不证明镜像可移交、120事实public清单匹配、
物理断网、备份恢复、角色隔离、公司数据或公司部署。所有业务/模块/计划百分比保持不变。

## 本地验证

首批12项缺能力回归全部先失败，再实现；后续mock/静态回归覆盖明确环境、URL/schema、FD、
空cwd、HTTP预算、进程退出、禁止隐式执行及真实测试范围。两项真实PG测试仅准备，未在本地运行。
完整统计与独立审查结果以最新检查点为准；完整后端/真实PG/前端/严格浏览器需本包精确CI。

自查HTTP总时限缺口及独立初审启动中断清理问题，均在具体通知等待后先增失败回归再修复；
分别新增3项先错误和2项先失败。复审发现timer取消失败跳过handler恢复，具体通知等待后
新增2项先错误再修；最终23集中、617全离线零跳过、52自动化、126守卫及编译通过。
最终独立复审通过无新阻断：另行将四个signal函数全部mock后23项通过。原本地套件API/HTTP/PG及子进程启动均mock，但部分用例确实短暂设置/取消当前测试进程timer；没有真实API、DB连接、网络监听或uvicorn子进程运行。
真实PG/HTTP尚未在本包执行。

## PR206首次CI失败与关闭证据修正

[CI42577445085](https://github.com/Wang106/SoftwareLifeCycle/actions/runs/42577445085)中
2个新API案例失败、3474项通过。两栈均进入stop的固定异常；原代码只接受退出0且未记录退出码，
__exit__的清理异常还可能遮蔽with块的断言，因此不能把该运行称为HTTP通过或已经观察到-15。

锁定uvicorn0.34.0的[官方Server源码](https://github.com/Kludex/uvicorn/blob/0.34.0/uvicorn/server.py#L312-L331)
说明正常shutdown之后会恢复处理器并重新发出SIGTERM。这解释了退出0假设不成立的机制；
本机安装0.52.1不是本项目精确版本证据，未用其运行API或替代CI。

具体通知等待后，新增4项回归先1失败/3错误再修。只修改本包助手、mock及记录，不改生产/依赖/门禁。
子进程固定检查uvicorn版本0.34.0，显式lifespan=on，ObservedServer沿用原信号处理和shutdown。
只有super._wait_tasks_to_complete正常返回才记录drained；超时或取消不记录。
shutdown只能进入一次，返回后要求started/should_exit、无force_exit、恰好一次SIGTERM、
startup/shutdown事件完成、无lifespan error/startup_failed/shutdown_failed/should_exit、
无剩余任务/连接以及所有server停止监听，才通过本次继承的独占pipe写固定单字节S。
write必须返回1，写端关闭失败也不成功；不会仅因super.shutdown返回就签发回执。

父进程只传本次socket和pipe写端，Popen后立即关闭自己的写端。读端nonblocking；只有本次
terminate之后wait完成、精确-SIGTERM、最多2字节读出恰好S且后续一次读为EOF才接受。
退出0、其他码、早退、超时/强杀、缺失/额外回执、写端仍持有、读/关闭不确定均失败，不重试。
回执仅证明该受信CI子进程走完上述检查，不是来源签名或抵御同UID进程的证明。

with块原异常/中断遇到清理失败时保留原异常，并附固定PG_API_SHUTDOWN_UNCONFIRMED，
避免再次只看到stop错误而误判HTTP已通过。成功块遇清理错误仍失败。
本轮本地API/DB/HTTP/子进程均mock；部分用例真实使用匿名pipe和短暂signal timer，
没有启动API、连接数据库或网络监听。新精确CI仍需验证两案例整体成功，旧CI不能改判通过。

独立终审无阻断：完整核对官方0.34.0 server/lifespan源码及对应blob，确认关闭顺序、超时不置drained、error_occured字段及finally外重发信号；33项全信号mock及独立异常检查通过。终审未运行真实API/DB，修正后的两项真实PG/API案例仍须新精确CI验证。
