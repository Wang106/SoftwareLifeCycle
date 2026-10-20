# 生产追溯事实更正设计审查

2026-10-21，Codex / ChatGPT Work；实际基线 `c148c96a50a07167b714bf6b7649a55d96bd5eed`。本修订落实 PR85 的实现准备审查，替代原稿中“旧库当前值是首次值”“保留无键覆盖”“只靠锁保证一个更正成功”的不完整建议。它是设计，不是功能或真实验收完成。

本包只改本文件、DEVELOPMENT_STATUS、HANDOFF、进度证据；无后端、Migration、Seed、界面、测试、依赖、CI、身份、费用或提供方配置改动。公共只读，OIDC/真实提交关闭，内网未部署；API0.18.45 / 唯一 head0026_release_chain_revocation 不变。

## 1. 实际代码与业务边界

models/production.py 存 Deployment expected/actual/status/actual_version/deployed_at、Changeover from/to/changed_at/note、Batch expected软件/换型/起止时间/note。services/production.py::_report_actual 当前覆盖 actual_*、status、deployed_at 并递增 actual_version；keyed 更正已有版本、原因、actor 和原审计重放。_create_changeover/_create_batch 只有创建，后者按当前 Deployment.status 判断 MATCH。

更正记录“原录入有误或获得更准事实”，不撤销物理生产、不改许可链、不取消既有批次。撤销后仍可记录现场事实，但不能借更正绕过新批次的许可、配额及实际软件校验。

Deployment 只更正 actual release/snapshot/发生时间，不改 expected/authorization/line。Changeover 只更正 from/changed_at/note，不改 deployment/authorization/to。Batch 只更正 started_at/ended_at/changeover/note，不改 deployment/authorization/release/snapshot；换型仍须属于同一Deployment且目标软件一致、完成，ended_at不得早于started_at。软件归属重分配明确不在此方案，不保留隐含通道。

## 2. 旧库基线不是首次事实

旧库可能 actual_version>1；Seed 也可能 actual非空但version=0。旧业务行只是升级时记录的当前值，不能改名为“首次报告”。新增不可变 deployment_actual_baselines，每个已报告Deployment一行，保存原UUID对、原status/deployed_at、原actual_version、来源及捕获时间；不改旧行、旧审计或旧发生时间。

来源区分 LEGACY_CURRENT（迁移当前值）、IMPORTED_CURRENT（如样例导入）、FIRST_REPORT（新协议真正首次报告）。只有最后一种能显示“首次”；捕获时间不等于物理发生时间。部分UUID或状态矛盾保留原值，显示PARTIAL/UNRESOLVED，不补猜另一半或推断MATCH。

迁移只捕获旧行当前值，不从审计拼造更正行/actor。旧 before/after/request/actor 原样保留，作为旧历史和原请求证据，不自动升级为新账本。旧历史标记NOT_VERIFIED，不能显示为空或完整首次值。若以后声称旧历史完整，须核对版本连续、before/after衔接、target及末值一致；缺失、重复版本、legacy缺request/after均明示缺口。分页展示不等于全链验证。

未报告行升级时不创建已报告基线。升级后首次报告同事务建立FIRST_REPORT基线、写物理actual列一次并写原审计；之后actual_*、status、actual_version、deployed_at冻结。既有物理列成为“记录基线”，对外当前值/版本由投影派生。新安装Seed的非空actual只能标IMPORTED_CURRENT，不伪装真实操作员首次报告。

## 3. 更正链、前驱与数据库约束

选择三张类型明确的更正表 deployment_actual_corrections / changeover_corrections / batch_corrections，另加上述Actual基线表。字段/时间约束不同，不用只在Python校验的通用JSON账本。可放独立 models/production_history.py。

每表有 id=request_id、精确target FK、predecessor_id（根为null）、正整数revision、完整替代值、独立correction_reason（trim后1..2000）、可信actor、原规范请求、原审计引用、recorded_at。Actual再绑定baseline_id。原事实/基线/更正/审计不可UPDATE/DELETE；完整替代值明确区分清空和未提供，不能把用户原因替换为系统编造文字。

数据库要求(target_id,revision)唯一、每目标一个根（partial unique）、每前驱一个后继（partial unique），同目标复合FK排除跨target前驱；Actual同时绑定同baseline。根revision=1，后继=前驱+1；FK/检查/trigger拒绝跳号、自指、环、断链。不能用created_at或随机UUID定义因果。索引至少(target_id,revision DESC)及前驱唯一索引；完整性异常返回UNRESOLVED，不随意选最新值。

Actual公共版本为baseline.recorded_actual_version + current_revision（基线revision=0），未报告版本为0。既有keyed body的expected_version精确匹配此版本，插入行记录锁内实际前驱；不悄悄给旧body增加必填字段。Changeover/Batch新更正body必须有request_id、expected_revision、predecessor_id（根显式null）、完整新值、correction_reason，禁止extra字段。两个请求审核同一版本/前驱时，第一条成功，第二条409；要再更正须重新读取并显式提交新判断。

request_id是命令族命名空间，不宣称全系统UUID唯一。Actual保留EVT-DA-{hex}，另两族拟用EVT-CC-{hex}/EVT-BC-{hex}。同族不同target同UUID必冲突回滚；跨族同UUID是不同命令，回执必须核对固定族、target、action、正文、actor，不能用其他族事件证明成功。每表request_id与对应event_no唯一是最终竞争防线。

## 4. 兼容写入、原重放与原子审计

既有POST /api/v1/deployments/{deployment_no}/actual的keyed结构保留：首次expected_version=0，之后新更正必须request_id、当前expected_version和原因，统一追加账本。服务内部保留ActualReportResult，现有POST响应仍是deployment_no/status/actual_version三字段；不能把内部结果误称成当前API完整回执。actual_version=expected_version+1，原EVT-DA的before/after是当次生效值而非今天基线；浏览器严格回执仍由原审计构造，不凭POST成功确认。账本/前驱信息如要暴露须作为明确新增契约，不改变旧ID/版本含义。

无键调用仅允许真正未报告目标的首次报告；新无键覆盖返回明确409，要求key、版本和原因。这是下一API版本需要记录的兼容收紧，本轮尚未改变行为。不能静默覆盖、关闭guard或编造“系统原因”假装兼容。旧keyed原请求继续按原EVT-DA审计精确重放，不受后来更正影响。

执行顺序：精确资源授权并解析可信actor→锁目标→查原命名空间证明→精确核对target/规范正文/actor/action/result并重放→新请求才验证当前版本/前驱、新值/关系/原因→业务/基线/更正/审计一次提交。缺失、损坏、legacy非证明审计或账本/审计矛盾不能确认成功；已占用key返回冲突/原结果未知，不再执行。恢复只查询原证明，不改key、不重发。旧完整审计after是原ActualReportResult来源，禁止借今天的有效值重建。

flush/审计/commit任一失败必须全部回滚。FIRST_REPORT基线绑定精确EVT-DA事件；提交时数据库deferred完整性检查验证事件存在且与target/基线值一致，不依赖应用口头承诺或可随意设置的session/GUC标记。实现复用atomic_command/commit_with_audit/actor校验，不能禁用原审计约束适配新表。

数据库旧写者guard拒绝已报告Deployment非no-op的actual/status/version/deployed_at覆盖，拒绝删除原Deployment；创建时的expected/authorization/line/编号/created_at不可改写。未报告→报告只允许一次与FIRST_REPORT基线和原子审计匹配的转换。导入/插入已报告行在同一事务捕获IMPORTED_CURRENT，迁移捕获LEGACY_CURRENT，不能留“先覆盖后补基线”的窗口。以后引入Changeover/Batch更正时分别冻结其原事实列。相等no-op不是新事实；不提供关闭trigger/维护模式绕过口。

seed.py约500–560行即使找到DEP-0081/CO-0032/PB-1005-A仍重新赋值，不能假设insert-only。下一实现必须把相应正式记录改为只创建缺失行，既有原记录/更正/审计不更新；验证连续Seed两次及发生更正后重跑，不能只比总数。本设计包不改Seed，当前幂等性不受影响。

## 5. 锁与下游边界

当前report_actual/create_changeover只锁Deployment；create_batch先锁Deployment再lock_chain，后者内部Release→Package→Distribution→Authorization；create_deployment先锁许可链再Site/Line并创建新Deployment。原稿笼统“Deployment→必要时Authorization”不能代替完整锁图。

事实更正只锁既有Deployment（随后才是对应Changeover/Batch，如需要），不新增许可链锁。范围授权仍用既有检查；不能为证明现场事实新增反向等待。Actual更正、相关换型/批次更正及新批次校验共享Deployment线性化锁。若未来必须加父锁，先复核完整图并用PG双顺序证明。

新批次持锁读取有效actual判断MATCH，维持许可/配额检查；更正先提交则重验，批次先提交则原事实/审计保留。Changeover更正不改to或既有Batch原绑定；Batch更正不制造新批次或重耗配额。撤销许可后记录更准事实，不产生新生产许可。

## 6. 已定位消费者与读取契约

以下均为基线真实路径/符号；不存在独立batch_detail或deployment_profile文件，不能虚构迁移路径。路径以下均相对backend/app，前端除外。

| 消费者 | 要求 |
| --- | --- |
| services/production.py::_report_actual/_create_batch | 原证明重放；CAS与新批次使用同一有效actual；_create_changeover仍绑定expected |
| api/production_catalog.py::observed/production_catalog | 三目录actual、software_observation、changeover_binding、batch_actual_binding用投影；recorded状态单列 |
| api/production.py::_deployment_detail/deployment_profile/get_batch/list_sites/get_site | 实际值、时间/版本、匹配及产线MATCH计数用投影；_deployment_provenance原许可来源不改 |
| api/manufacturing_views.py::line_rows/sites | SQL alias/join用有效actual/状态/时间/版本，分页聚合固定形状 |
| api/dashboard.py::application_release_downstream_summary/application_release_downstream | 当前实际发布计数、快照、匹配用投影；Batch.release_id和原记录数量不改算成actual |
| api/issue_views.py::candidates、api/impact.py::issue_impact | 当前部署影响计数用有效actual；仅迁移仍启用路由，不复活tombstone |
| api/distribution.py::_authorization_detail | deployment状态及actual匹配用投影；authorization_profile原数量不变 |
| api/search.py::search_records | Deployment status摘要分清有效/记录；Batch原status不改 |
| api/distribution_catalog.py | 只有Deployment/Batch原数量，不改成更正数、不加载历史 |
| frontend/lib/production.ts、lib/manufacturing-views.ts、app/deployments/[id]/page.tsx、components/manufacturing-profile.tsx | 双语区分记录基线/当前更正/发生和记录时间/历史缺口，正文原文转义 |
| frontend/lib/command-draft.ts、components/command-workbench.tsx、lib/first-command-transport.ts、lib/first-command-audit.ts、lib/browser-session.ts | 原actual body、expected_version和EVT-DA before/after证明兼容；不借新详情反推成功，不开新通道 |
| seed.py、write_contracts.py、models/production.py | 正式记录生成、写契约与物理列不成为当前有效值的第二来源 |

已核对装饰器与compatibility_reads清单：生产profile、单Batch、downstream-summary、三个production catalog、manufacturing views、issue views、authorization profile及search是保留入口。旧Deployment目录/详情/provenance、旧sites、旧Issue impact及完整downstream是退役入口；其遗留函数即使仍存在也不是新增路由授权。_deployment_detail等仍被保留profile以有界选项调用的helper要迁移；_authorization_detail的嵌套历史、issue_impact等仅在存在实际调用方时修改，不能为清理死分支复活旧GET。下一包用实际路由集合和消费者回归证明覆盖，不以文本匹配命中数量当已迁移数量。

resolver必须提供可join/filter/count的有界SQL子查询及批量详情投影，不能只给单对象Python helper。按target/revision索引取唯一头，先在SQL应用有效值再过滤/分页/计数，禁止取一页后Python过滤。历史独立cursor分页默认50、最大200，主详情不加载全部审计/更正链；缺表/断链/矛盾明确UNRESOLVED，不回退基线伪装MATCH。本轮尚未发布这些GET/POST。

## 7. 升级、旧审计恢复与拒绝降级

编码前重新确认唯一head；若仍0026，Actual小包才新增0027并更新required_db_revision/API版本。升级捕获旧reported/partial/seed版本0当前值；不改旧发生时间/actor/审计，不按时间排序生成历史。事务/表写锁建立捕获与旧写者guard的单一切换点，无旧进程写入空窗；超时/回填失败全部回滚，重启无重复基线。

旧完整EVT-DA请求/actor仍返回原after，后来更正不让原重放变成当前版本冲突。缺request/actor/after或矛盾证据仅保留为旧历史，不升级为可确认回执；旧审计永不改删。测试必须先由真正旧0026路径写入多次报告再升级，不能只在新schema造假旧数据。

任何更正行或升级后FIRST_REPORT基线存在时拒绝downgrade，旧代码无法保留新增冻结/追加语义。只有纯导入基线、无新业务历史才可移除结构，旧值/版本/审计逐项不变。拒绝必须在拆trigger/表前发生，失败后head/数据/guard仍在；没有force/drop-history后门。备份恢复另行验收。

## 8. 真实PostgreSQL最低矩阵

| 场景 | 必须证明 |
| --- | --- |
| 双连接不同key审核同一头；同key双连接 | 一个成功另一409；同key一个事实/审计另一原结果；barrier和真实连接，不用SQLite替代锁 |
| 原key重放/换target/正文/actor/跨族审计 | 原证明先于当前头；原结果不漂移；占用冲突全回滚、族不混淆 |
| Actual更正与新Batch、换型/批次更正与关联创建，双顺序 | Deployment锁线性化、配额不超、不死锁、不回写原事实；lock/statement timeout内完成 |
| 首次/更正flush、审计、commit失败 | domain/baseline/correction/audit全回滚，无孤儿首次证明 |
| 旧SQL/无键覆盖及直接INSERT/UPDATE/DELETE | 只允许一次有证明首次和no-op；冻结后拒绝覆盖删除；跳号/分叉/跨target前驱拒绝 |
| 真0026旧库：version0样例/未报告/1/>1多更正/部分值 | 当前值原样、来源准确，不伪造首次；原审计原字节/原结果重放，缺失legacy矛盾显式 |
| 升级并发旧写者、超时/失败重启 | 无捕获/guard窗口，失败全回滚，重跑唯一基线 |
| 空新历史/有更正/有新FIRST_REPORT降级 | 纯导入无损往返；新历史在拆对象前拒绝且guard有效 |
| 1/1000/10000历史、同时间戳/逆序UUID | 跨消费者一致、页长有界；EXPLAIN/索引和既有SQL timeout证据，不仅查询次数 |
| Seed两次及更正后再Seed | 原行/更正/旧审计不变且不重复，不仅比较数量 |
| 双语只读与原回执 | 来源/缺口/有效值明确、原因原文转义不翻译、精确审计链接、无新发送入口 |

## 9. 下一实施包的精确边界

原production-trace-correction-backend-read拆成更小的production-actual-history-backend-read：只做Actual基线、追加更正、全部actual消费者和双语只读历史。Changeover/Batch自身更正账本随后另包，不因Actual完成勾完三类里程碑。

下一包新增backend/app/models/production_history.py、services/production_history.py及实际head后的唯一迁移；修改models/__init__.py、services/production.py、api/production.py、api/production_catalog.py、api/manufacturing_views.py、api/dashboard.py、api/issue_views.py、api/impact.py、api/distribution.py、api/search.py、seed.py、write_contracts.py、core/config.py和main.py中APP_VERSION（基线定义于第58行）。新增backend/tests/test_production_actual_history.py、test_production_actual_history_postgres.py、test_production_actual_history_migration_postgres.py；保留既有回归意图，必要更新字段契约并扩展覆盖，不删除失败断言目的。前端限§6只读类型/详情/制造页、必要词条和只读历史测试；原actual协议只验兼容，不新增发送能力。

详情/目录保留既有actual/actual_version响应字段但改用有效投影，明确另加recorded_baseline/effective_actual/history_state及cursor历史契约；先核对实际路由注册，不复活退役路由。验收覆盖§8所有Actual相关行、§6全部actual消费者、完整后端/真实PG/前端CI、迁移SQL/升降级、Seed重复/更正后重跑、Next/OpenNext/双语只读。任何消费者仍把物理基线当当前值，不能发布“统一读取完成”。

真实批准提供方、多用户/桌面/手机验收仍待定；不改身份、秘密、CI/调度、依赖或真实开关，不实现生产运营。设计不提高业务验收：36/44=82%；七模块100/100演示/100演示/100/89/60/17；七计划100/100/20/33/40/20/0。
