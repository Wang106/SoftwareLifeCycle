# 独立迁移镜像准备演练

## 当前状态

本包只有独立手动工作流、协调器、合成回归和本文，以及四份维护检查点。
**开发时没有下载实际wheel/镜像、构建镜像、启动容器、连接数据库或运行Alembic/SQL。**
普通测试全部mock这些外部动作；本地合成Git仓库、受控tar和有限Python子进程是实际验证。
没有触发新工作流，不能把已有API/web镜像运行成功当作迁移镜像成功。

基线为PR202已保护合并的main `65e2b90e016f1d8c571cf7269cdf1017046db49e`。
[main CI42541454395](https://github.com/Wang106/SoftwareLifeCycle/actions/runs/42541454395)
成功：3357后端＋1516子测试、296项PostgreSQL零跳过（836秒）、2116前端、
8＋16严格浏览器，签名Chrome157、sandbox=true及汇总门禁。
Cloudflare build `480f3fed-e0e1-4a74-80bf-ffbbfb0ee5f1` / version
`00907107-816f-4fb5-a872-f30367768f51`成功；Render
`dep-dbohctp42hec73deiqcg` update_failed，不称后端恢复。以上为父任务核验的基线，非本候选CI。
此前实际API运行[42536231169](https://github.com/Wang106/SoftwareLifeCycle/actions/runs/42536231169)
（导出true/API true）和[42536267359](https://github.com/Wang106/SoftwareLifeCycle/actions/runs/42536267359)
（导出false/API true）在精确 `fde3270d1248514c827b2fd377696348e2d56a84` 成功。
它们没有验证本包迁移镜像、数据库迁移、物理断网或公司部署。

## 执行授权和入口

工作流只有workflow_dispatch，没有push/PR/schedule触发、矩阵、services或自动部署。
使用标准ubuntu-24.04、contents: read、固定版本checkout且不保留凭据、独立并发组且不取消前次。
不安装宿主工具，不增加付费runner、缓存、镜像上传/推送或可下载制品。
标准runner不构成整个账户所有资源均免费的保证。

未来运行前，必须另行明确批准本次固定30项官方wheel下载、固定Python基础镜像获取、
本地BuildKit构建、两个隔离短命容器启动，以及本次拥有权容器清理。
这不授权数据库、SQL、角色/权限、目标安装、既有容器清理、主机安全设置、上传或新增费用。

```sh
python3 -B scripts/offline_migration_image_rehearsal.py --run \
  --expected-commit <independently-verified-40-hex-commit>
```

CLI只有该明确运行入口；不提供任意URL、数据库连接、镜像、命令、context目录或恢复失败运行参数。
导入、帮助、普通测试不运行Docker。缺少--run或精确commit直接拒绝。
工作流将其实际GITHUB_SHA传入，不从待验镜像、目录清单或历史runner猜测期望值。

## 来源、wheel及完成状态

先在固定受信、有总时限的子进程使用原context工具读取干净checkout的精确Git对象，并核对实际文件字节。
只返回64KiB以内的严格commit/requirements/inventory/探针期望回执；父进程再次校验键、类型、锁关系和源码路径/摘要预算。
原源码白名单、30份单链AST检查、requirements和30项wheel锁全部保留。
新BUILD_SOURCES另核对当前协调器、工作流以及实际使用的context、下载工具和传递依赖的Git字节。
这不扩大原context清单白名单；原api/web流程和严格双角色协议完全不变。

只复用原官方锁和单件fetch，不调用原同时获取399项npm的acquire或完整api/web run。
最多4件并发，使用原固定官方HTTPS URL、大小/SHA、无重定向、无代理绕行和排他写入规则。
不解析新版本、不用镜像站、不传凭据、不重试。代理配置即使为空也拒绝，不静默绕过。
整个下载阶段放入固定受信Python子进程，外层有共享期限，避免线程池等待越过整轮截止。

真实prepare子进程必须正常返回完整、强类型的MIGRATION_INPUTS_PREPARED_NOT_EXECUTED回执。
它的commit必须匹配已核实HEAD，migration_count为29，database_connected/image_built均为false。
只有此回执中的摘要可以作为后续独立verify进程的期望值。
**migration-inputs.json存在不是完成证明**：原工具可能在最终复核或关闭失败后保留它。
本协调器不从该文件自读期望、不续跑旧目录、不因已有清单绕过prepare成功门槛。

## 构建输入与镜像结构

独立verify成功后，协调器在另一个有总时限的固定受信子进程再次核对并将精确白名单字节复制成新的本地tar。
只有该子进程成功返回严格commit/context/tar摘要回执才采纳输出，失败时已有tar不是完成证明。
读取使用原no-follow和目录描述符边界，核对文件大小/SHA及前后完整目录身份。
归档固定普通文件、mode0644、uid/gid/mtime0，禁止额外文件和任意Dockerfile；不提取输入归档。
完成后再次验证原context，记录tar摘要。构建时保持该受检普通文件描述符，
从同一文件向本地Docker标准输入发送，构建前后核对摘要，每块读取前后检查共享预算；不让Docker重新扫描可变源目录。
这些是受信临时runner上的一致性检查，不保证抵御具有同UID写权限的攻击者。

固定Python linux/amd64 manifest来自原migration.BASE；pull后必须匹配原BASE_CONFIG。
不新增基础镜像锁、依赖或Dockerfile。固定BuildKit和
--platform=linux/amd64、--pull=false、--no-cache、--network=none，
仅SOURCE_COMMIT来自已验证HEAD，保留配方原RUN --network=none及无索引hash锁安装/pip check。
基础镜像获取仍需要网络；构建RUN隔离不等于宿主物理断网。

使用本次排他iidfile取得精确image ID，后续只按该IDinspect/create，不凭标签选择镜像。
独立migration镜像schema要求linux/amd64、当前commit、用户65532:65532、/app工作目录、
默认/bin/false、空CMD、无卷/端口/健康检查/OnBuild及有限的原基础环境字段。
不改变slc-offline-readonly-v1，不增加第三角色，不执行docker-save、load、push或Compose。
镜像标签、Git对象和SHA只证明一致性，不是发布者签名、来源认证、安全或许可审计。

## 两个固定运行探针

1. 默认拒绝：不覆盖入口，实际启动并要求退出1、无输出、State已退出、无OOM/daemon error。
   创建成功、运行超时或普通Docker失败都不能冒充默认拒绝通过。
2. 依赖及源码：只允许固定Python -I -B程序。核对Python3.12.14、30项分发版本、
   原生依赖导入、psycopg binary后端和pip check；检查Python模块入口存在，不依赖未复制的console script。
   镜像/app必须只有精确原始app、alembic.ini、env.py和30份迁移文件/目录；逐项检查大小/SHA、
   编译语法和AST单链。编译不执行模块。

探针不import应用、模型或env.py，不调用Alembic current/heads/history/upgrade，不生成SQL，
不设置DATABASE_URL、不启动API、数据库或seed。原env.py连接后会写版本表，current不是只读探针。
本包没有解决离线SQL版本列32/64字符风险，没有验证实际数据库schema或迁移链运行。

两个容器顺序创建，各自固定network=none、无端口/绑定卷、只读根、nonroot、drop全部capabilities、
no-new-privileges、无Docker日志、无重启，512MiB内存和同值memory-swap、1CPU、64PID、8MiB shm。
只有固定16MiB nonexec/nosuid/nodev /tmp tmpfs，env不继承宿主DB/身份/凭据。
inspect必须核对本次CID、随机拥有权label、精确image ID、入口/参数及所有安全属性。

创建前持久化本次私有拥有权记录。只在CID文件和inspect身份可靠时启动或删除，
每个容器最多一次create/start/rm；禁止按名字寻找、prune和重试清理。
失败或中断仍尝试有凭据的本次清理；缺CID、身份变化或删除结果不确定均失败并保留记录。
不删除输入目录、镜像或daemon构建缓存；普通临时runner结束不等于取得可下载交付包。

## 预算和失败回执

共享55分钟软截止从checkout前开始，工作流60分钟硬限。时间戳是本机计时记录，不是来源凭证。
临时目录和本地Docker数据目录均要求至少20GiB空闲。只检查现有宿主，不改设置或自动扩容。
原wheel上限单个128MiB、总512MiB；context沿用529MiB/544文件，构建tar最多额外8MiB元数据。
基础镜像锁未记录层总字节，故不声称精确下载流量上限。

源码整段最多600秒、整轮下载1200秒、prepare600秒、独立verify180秒、tar快照180秒、pull600秒、build1800秒；
构建前后保留FD的摘要扫描各最多120秒，逐块检查截止；
每次实际期限取共享剩余预算中的较小值并为探针/摘要预留，不是把各段上限累加延长运行。
每个探针工作180秒＋拥有权清理35秒，第一项开始前留足两项430秒，第二项前留足215秒；
另保留30秒摘要。余额不足不创建新容器。SIGTERM转换为中断，finally清理后恢复原处理器。
Git/context原工具仍有其独立文件/输出/CPU等限制。原Git子工具可另建session，终止外层不证明所有已开始子工具停止；
此类超时保留为不确定，不自动重试，也不声称所有后代进程都已终止。

外部命令无shell，stdout先限长，stderr丢弃不公开。下载子进程组超时停止，不自动重试。
Docker CLI停止不能证明daemon侧pull/build已停止；超时、取消或宿主丢失必须标记不确定，
硬限或重复信号也可能阻止清理，不宣称无条件成功清理。

成功回执为独立slc-offline-migration-image-rehearsal-v1，包括精确commit、context/tar摘要、
image ID、平台、30依赖/30迁移源码数量、默认退出1及两个容器已清理；
database_connected=false、migrations_executed=false。
状态为MIGRATION_IMAGE_SMOKE_PASSED_NOT_DATABASE_ACCEPTANCE。
公开步骤摘要只列固定安全信息，不发布原始日志、路径、数据库URL、凭据或大制品。

## 开发验证与下一边界

先14项能力缺失回归全部失败，再实现。集中回归覆盖真实合成本地Git、context tar和有限Python子进程，
以及全部网络/Docker mock阶段、强类型回执、默认拒绝、安全属性、CID清理和截止时间。
初版一项测试由于宿主代理未从合成fixture清除而被保护逻辑拒绝，已仅隔离mock测试环境；
没有绕过实际代理限制或重试实际下载。独立审查发现源码及tar同步阶段缺少整段共享时限，新增两项回归先失败；具体通知并等待后，
仅在新驱动加受信有界子进程和构建前后hash逐块deadline，原context等工具不改。修后39集中、547全离线零跳过、52自动化、126守卫和Python/JSON/YAML/bash语法、进度/diff检查通过；
独立复审待完成。最终统计与审查结果以最新检查点为准。

上一包本地前端npm test被平台以依赖联网风险拒绝，本包不重试该命令，也不换入口规避。
本候选前端、完整后端、真实PG和严格浏览器以正常精确CI为准，不沿用基线成功。
公司部署、备份恢复、物理断网、实际数据库schema、安全审计与真实身份均未验收。
后续空库迁移必须独立设计和获准，不能手填版本表、stamp、create_all或静默改变权限来获得通过。
业务验收增量0；模块/计划/浏览器阶段百分比不变。
