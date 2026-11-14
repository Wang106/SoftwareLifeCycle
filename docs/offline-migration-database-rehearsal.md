# 迁移镜像与自有空数据库联合演练准备

Current integration update (2026-11-10): an internal, default-false same-run lifecycle
path is prepared in the coordinator. CLI/workflow remain migration-only and no new
actual API runtime has been performed. See [current lifecycle scope](offline-api-lifecycle-integration.md).
The earlier future/unwired statements below describe the original package.

## 已核实的基线与本包边界

基线main `4624e01fbf832d741cad5fc474354511436f4597`（PR209）完整CI42651157761成功：
3503后端、2611子测试、308项PG零跳过；Cloudflare生产build
`6e0eae23-4db8-4011-951c-2ccccfed7a58` / version
`79eae26b-4553-44b3-a60a-5408ca670b73`成功。Render未核验。
[单次迁移镜像准备42660395986](https://github.com/Wang106/SoftwareLifeCycle/actions/runs/42660395986)
在同提交成功，attempt1：30依赖、29迁移、146源码文件、默认入口exit1、两容器清理；
database_connected=false、migrations_executed=false，无下载制品。
这些是已完成的准备证据，不是本包联合数据库执行证据。

本包新增独立协调器、mock合同及独立手动工作流，不改原准备工作流/构建器、Dockerfile、
依赖、29份迁移、生产代码或已有CI/浏览器/分支保护门禁。普通导入、测试、帮助和缺参数
不运行Docker、下载、DB或DDL。本地仅合成文件/mock，实际联合执行尚未发生。

## 将来执行必须另行具体批准

实际批准应覆盖固定输入重新获取及同轮镜像构建、固定PG16.15镜像获取、两新联合容器、
共享网络命名空间、临时超级用户trust、原迁移DDL、有限目录/计数读取及本轮容器清理。
本次开发不授权执行，也不能沿用上一轮仅镜像准备批准。无外部目标、URL、数据库名、
容器ID、SQL或镜像参数，无公司/旧公共/现有数据库访问，无角色GRANT/REVOKE、API或seed。
不购买资源、升级配额或更换付费runner；标准runner并不保证账户总用量无费用。

手动工作流仅workflow_dispatch、contents:read、固定checkout且不保留凭据、ubuntu-24.04、
60分钟硬限、不并发取消；不新增push/PR/schedule触发、不上传镜像或原始日志制品。
调用必须带--run和独立核实的精确commit；共享开始时间必须由工作流在checkout前设置。

## 同轮构建与固定目标

先复用原迁移镜像准备器，在同一run完成已锁定wheel/基础镜像获取、构建、源码/依赖及
默认拒绝两探针。旧run镜像没有留存，不能只传旧image ID。新协调器和新工作流字节另与
所选commit的Git对象绑定，原构建器仍独立绑定其工具/输入和干净checkout。
后续只使用本次返回的精确migration image ID；再次inspect平台、commit和原安全镜像契约。

PG复用已审核固定官方linux/amd64 manifest
`postgres@sha256:5983db9a9c6ad225a48a46cfe2e03e6680b1826662befd0465eb05b34cb1c64e`，
image ID `sha256:cadebe7c08430c896edac883fa92f8de2c36e330805e770fbee8a7eae13f144f`。
不以浮动tag或pull成功代替身份核验，不回退镜像/平台。摘要不是签名或安全审计。
依赖/镜像获取需要联网，构建RUN隔离不等于宿主物理断网。

## 网络、trust与容器资源

PG容器network=none、无宿主端口/宿主卷/持久卷，listen_addresses=127.0.0.1。
迁移容器使用container:<本次完整PG CID>共享同一个网络栈，无hostname/DNS/publish/expose等
不兼容选项，不使用host/bridge网络。PG最终PID1必须是postgres，/sys/class/net只能有lo；
捕获网络命名空间inode，迁移子进程检查自己同inode及仅lo，然后才加载迁移。
inspect前后核验完整CID、image、唯一label/name、入口/参数、环境、网络、挂载、资源和安全属性。
这些依赖受信宿主/daemon及checkout，不抵御同UID/daemon管理员，更不是物理断网认证。

PG为999:999，migration为65532:65532；均只读rootfs、dropALL、no-new-privileges、
无Docker日志、无重启、1CPU/1GiB内存及相同swap/128PID/8MiB shm、private IPC/cgroupns。
PGDATA仅512MiB tmpfs，socket及/tmp各16MiB；migration仅原16MiB /tmp。无目录绑定或持久数据。

初始化使用POSTGRES_HOST_AUTH_METHOD=trust与
POSTGRES_INITDB_ARGS='--auth-local=trust --auth-host=trust'。
官方entrypoint还会追加host all all all trust；**HBA并非仅loopback规则**，隔离依赖上面的
none网络/无外接口/无端口及loopback监听。具有该namespace或Docker权限的人仍可作为postgres
超级用户连接。这是单独批准的短时合成执行，不是生产认证、SELECT-only角色或权限安全证明。
不创建/保存密码、令牌或新持久凭据。

## 原链执行及有限观察

只在新容器初始化的固定slc_migration空数据库中执行；先检查public的关系与函数均为0。
原镜像默认仍/bin/false。只有该协调器明确覆盖为固定Python -I -B bootstrap，先检查身份/网络，
显式加入/app到sys.path，再用Alembic公开command.upgrade调用固定0030目标。
不调用未复制console脚本，不stamp、不手填版本、不create_all、不降级、不seed、不修改历史迁移。

连接只指向127.0.0.1:5432/slc_migration，服务器固定5秒statement、1秒lock、15秒idle超时，
连接超时5秒。观察由新连接在READ ONLY/REPEATABLE READ事务中执行，rollback结束；
原迁移独立事务已经提交，不能把观察rollback称为撤销迁移。
成功要求迁移进程exit0、固定完成回执、无OOM/daemon错误，以及精确0030单头、版本列64、
7张选定表/3个函数/6个启用触发器、4张选定业务表行数0。
只检查这些有限关系和计数，不证明全部schema、所有数据、函数行为或权限。

## 总预算与失败清理

55分钟软预算从checkout前开始，原构建器和新联合阶段使用同一timestamp，不重置。
构建完成后至少留1030秒才继续后续host/PG获取；PG pull最多600秒并预留400秒。
创建PG前再要求430秒，联合工作最多300秒且始终预留清理/摘要；初始化轮询最多90秒，
迁移start/attach最多180秒，观察最多15秒，任一步按共享剩余时间进一步收紧。
不足则不创建新容器，不能另起续跑。轮询只检查同一PG初始化，不重新start或重试DDL。

每个create前以排他文件持久化拥有权，finally读取cidfile；无可靠CID不按名称寻找或删除。
cleanup只inspect确认身份后按精确CID执行一次rm --force，顺序migration再PG；前者失败也尝试
后者已确认身份的一次清理。记录清理未确认并保留最初错误，绝不把普通失败/强杀当正常迁移。
清理共享最多90秒且不能越过总预算预留；不删除镜像、构建缓存、输入目录或其他run资源。
不自动重试、prune、按前缀扫描或清理旧容器。

Docker CLI结束不能证明daemon侧pull/build/start已经停止；丢失CID、超时、硬终止、重复信号
和runner丢失可能使清理不完整。失败保留为blocked/uncertain，不声称无条件清理或事务恢复。
成功回执只在两个联合容器确认移除之后生成，另单列原准备阶段两容器已移除。

## 当前验证与后续

首批13项缺能力合同先全部失败，再实现。缺CID回归误捕获异常类，具体通知等待后仅补既有safe_read异常类。最终35次集中执行（22不同方法、13继承重复）、675全离线、52自动化、126守卫、内存编译/账本/diff通过；包含安全inspect反例及完整编排/失败清理mock。
没有实际下载、构建、Docker操作、DB连接、DDL或API运行。独立终审通过，无新增阻断：另35次集中、3种内存bootstrap及1种迁移启动中断探针通过，中断保留且两已知CID各清理一次。精确候选CI尚未运行。
未来真正运行须另行批准，不能从普通CI通过推导联合演练已执行。
业务36/44=82%、增量0；模块100/100演示/100演示/100/89/60/17；计划100/100/20/33/40/40/0；
浏览器阶段1/4、有限计划8/8保持不变。
