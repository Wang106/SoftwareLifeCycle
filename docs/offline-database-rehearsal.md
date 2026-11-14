# 手动合成 PostgreSQL 验证准备 / Synthetic PostgreSQL rehearsal

## 当前只开发，实际执行未获本包授权

新增独立的 `Manual synthetic PostgreSQL rehearsal` 手动工作流及
`scripts/offline_database_rehearsal.py`。导入、普通 pytest/unittest、无参数和 `--help`
均不会连接 Docker、数据库或网络。只有显式 `--run` 才执行下面的操作。
**本次只做代码、mock 失败回归、文档与官方镜像元数据只读核对，未拉取镜像层、未启动
容器、未连接 PostgreSQL、未创建角色/授权，也未触发手动工作流。**

实际执行必须另行明确批准，并覆盖：固定官方镜像下载；本次新容器的 `network=none`、
只读 rootfs、capability drop/no-new-privileges 等容器限制；容器内 Unix socket 的 local
trust；临时 NOLOGIN 角色、危险属性、成员关系、所有权和合成授权；移除本次自建容器。
开发批准不能代替这些执行批准。不得自动运行，也不能从工作流存在或 CI 通过推导授权。
容器网络隔离不是物理宿主断网；代码不修改宿主防火墙、网络、安全或 Docker 配置。

旧公共库不恢复，公司/生产/既有数据库都不访问。脚本不接受 URL、主机、角色、数据库、
容器 ID、镜像或 SQL 参数，不读应用环境配置，不启动应用，不跑业务迁移，不处理业务数据。
原 `database-readiness.sql`、离线证据检查器、预检、现有 CI/部署/镜像工作流保持不变。

## 固定可信输入与已有工具前置

元数据核对日期：2026-11-08。官方 `library/postgres:16-bookworm` 当时对应
`16.15-bookworm`。仅通过 HTTPS 读取 tag、manifest 和约 10 KiB config，没有读取 layer。
manifest 和 config 的原始字节分别重新计算 SHA256，与 descriptor 一致：

- tag index：`sha256:5264710be20f409750ac6dc4e5706dcef929c87e241605463f0f9aefa932a8d9`
- 固定 linux/amd64 manifest：`sha256:5983db9a9c6ad225a48a46cfe2e03e6680b1826662befd0465eb05b34cb1c64e`
- config/image ID：`sha256:cadebe7c08430c896edac883fa92f8de2c36e330805e770fbee8a7eae13f144f`

来源：[Docker Hub tag 元数据](https://hub.docker.com/v2/repositories/library/postgres/tags/16-bookworm)、
[官方 registry manifest](https://registry-1.docker.io/v2/library/postgres/manifests/sha256:5983db9a9c6ad225a48a46cfe2e03e6680b1826662befd0465eb05b34cb1c64e)、
[固定来源 Dockerfile](https://github.com/docker-library/postgres/blob/9d15534160ade17f2b6c455a39ee967c49b1937d/16/bookworm/Dockerfile)。
Dockerfile 明确 postgres uid/gid 为 999；tmpfs ownership 使用该固定值。
摘要是完整性和来源定位，不是签名、安全漏洞审核、许可审核或未来版本更新机制。
不自动切换 tag、平台或版本，拉取失败停止，修改 pin 要单独审查。

未来运行要求现有 Linux x86_64、Python 3.12、Docker，临时目录和 Docker 数据目录
各至少 20 GiB 可用空间。只接受空白隔离 Docker 配置下的 default context，且其 endpoint
必须是 `unix:///var/run/docker.sock`；拒绝 DOCKER_HOST/CONTEXT/TLS/CERT/API 覆盖。
不安装、升级、切换 daemon、不登录 registry、不使用保存的凭据。缺前置直接阻断。
先核对本地 git HEAD，在 Actions 中还必须等于 GITHUB_SHA。随后只拉取上述固定 manifest，
再次核对 image ID、平台和 RepoDigests；不能只相信 tag 或拉取退出码。

工作流只有 workflow_dispatch，`contents: read`、固定 SHA checkout（不保留凭据）、
ubuntu-24.04 标准 runner、30 分钟限制和 cancel-in-progress=false。没有定时、PR/push
触发、付费 runner、上传制品/日志、持久缓存或新的已有 CI 门禁。
公开仓库标准 runner 的一般计费规则不保证账户全部用量无费用；若实际新增费用需另批。

## 一次性容器及角色边界

只 create 一个唯一新容器，使用 `--pull=never`、不发布端口、`network=none`、只读 rootfs、
postgres 非 root 用户、ALL capability drop、no-new-privileges、1 CPU/1 GiB/128 PID 上限。
PGDATA（512 MiB）、socket 和 /tmp 仅 tmpfs，不挂宿主目录，不创建持久卷。
官方 image 的 VOLUME 被同路径 tmpfs 覆盖。日志驱动 none，不读取 `docker logs`。

初始化显式 `POSTGRES_HOST_AUTH_METHOD=trust` 配合
`POSTGRES_INITDB_ARGS=--auth-local=trust --auth-host=reject`；服务器
`listen_addresses=''`，只有容器内 Unix socket。host reject 规则先于 entrypoint 追加的
host trust 规则，且该容器不开放 TCP。这不是可复用的生产认证方案：有宿主 Docker 权限
或容器内执行能力的人仍能用 local trust 访问超级用户，因而需要明确的隔离/执行批准。
不创建或保存密码、令牌、LOGIN 测试账号。强制退出或主机故障不能保证 tmpfs立即回收。

先 create 写入新私有 cidfile，记录完整 64 位 CID，inspect 同时核对 image、唯一 name/label、
网络、端口、mount 和只读设置，随后才 start。等待最终 PID 1 postgres，避免误用 initdb
临时服务器。每个固定 case 在该新容器中创建独立合成 database 和唯一 NOLOGIN subject。
每次 psql 都由 docker exec 新建连接，指定固定 Unix socket、postgres 和固定数据库名，
带 no-psqlrc、quiet、tuples-only、no-align、no-password、ON_ERROR_STOP=1、5 秒连接超时。

固定 fixture 由容器内 postgres 创建，collector 的新连接先做
`SET SESSION AUTHORIZATION <固定合成角色>`，然后逐字执行原 SQL。session/current user
因此相同，不使用 SET ROLE 绕过原检查。这只测试目录与权限观察逻辑，**不是证明真实
只读登录、认证链或不能 RESET SESSION AUTHORIZATION 的权限隔离**。初始化的管理员
身份仍与真实只读账号验证不同，不能冒充公司只读账号验收。

## 21 个固定案例与准确结果解释

所有 fixture 只在本次新容器中创建。普通 baseline 保留 PostgreSQL PUBLIC 默认 ACL，
不 REVOKE PUBLIC、不改变生产/全局授权来制造 MATCHED，也不放宽原检查器。
[PG16.15 官方 system_views.sql](https://github.com/postgres/postgres/blob/REL_16_15/src/backend/catalog/system_views.sql)
对 pg_settings 授予 PUBLIC UPDATE；baseline 必须观察到数据库 TEMP 和非零系统表/列写权限。
这些 ACL 未在本包真实执行中测量；不能把 mock 中的 1/17 称为观察结果。

- baseline：标准 `version_num VARCHAR(64) NOT NULL PRIMARY KEY`，唯一正确头
  `0030_private_upload_sessions`，预期 CHECKLIST_MISMATCH，而不是 MATCHED。
- 表 INSERT 与单列 UPDATE：分别要求相对 baseline 的表/列计数精确增加 1/2 与 0/1。
  PUBLIC 已有危险项不能掩盖没有检测到新增授权。
- 直接成员关系、表所有者：精确检查成员/所有权与写计数。
- SUPERUSER、CREATEDB、CREATEROLE、REPLICATION、BYPASSRLS 五个独立 NOLOGIN 角色：
  各对应 flag 必须为 true；superuser 的 CREATE 及系统权限计数还必须扩大。
- 错误头、多头：精确要求行/正确头为 1/0、2/1。
- 迁移 view、表达式索引、部分索引：必须拒绝形状，禁止读取版本，计数为 null。
- 缺 SELECT、缺迁移表：精确检查各 shape/access flag 和 null 计数。
- sequence USAGE、PUBLIC routine EXECUTE、额外 schema、enum 及其数组：精确拒绝对应计数。

每项要求 psql 真正退出 0，输出最多 16 KiB 且只有一个严格 JSON；重复键、多文档、非整数、
不一致关系和未知字段都拒绝。完整 typed 字段必须与 baseline + 明确 case 变化一致；
superuser 的三个系统权限计数要求严格增大，不能伪造为普通角色计数。其余字段变化也阻断。
原离线检查器再用独立 Python -I 进程读取本次独占新建的 0600 证据文件；要求退出 1 且
完整报告与预期精确一致。CHECKLIST_MISMATCH 只有伴随这些证据与目标字段才是反例成功。

psql 非零、超时、输出超限或中断均是 COLLECTOR_ERROR/采集失败，**不是“预期拒绝通过”**。
UNKNOWN、错误 checker 返回码、错字段、缺案例、清理不确定都会使演练失败。不复用旧证据，
不补写 JSON，不手工把失败当成功。每个子进程输入/输出/运行时间有上限；脚本总工作预算
25 分钟，另留一次有限清理时间。公开输出只有固定状态码、阶段、案例计数、固定镜像和来源
commit，不含原始 SQL/stderr/server log、连接参数、业务行、用户目标或凭据。

## 清理与未确认结果

仅对本次已记录完整 CID 且 inspect 再次确认 image/name/own-label 的容器执行一次
`docker rm --force <本次 CID>`。不通过名称删除、不扫描/删除既有容器、不 prune、不删镜像、
不恢复或复用旧容器。只在 rm 返回 0 且返回相同完整 CID 时记录移除成功。
创建响应丢失但 cidfile 有可靠 CID 时，只能核实该 CID 后清理；没有可靠 CID 或身份不符
则停止，绝不猜测。清理失败不重试，也不将之前通过的案例汇总为成功。

本次私有临时目录（系统临时目录下 slc-pg16- 前缀，0700）中保存 custody.json 和 cidfile，
便于人工核对不确定结果；没有 raw server log 或密码。正常确认移除后删除自己的临时文件。
创建/移除不确定时保留本次记录，人工基于该次记录核对，不能只按模糊前缀批量删除。
脚本处理普通中断/SIGTERM，但强制 kill、runner 取消或 daemon 丢失仍可能使清理未完成。
自动或人工重试之前必须先解决上一轮的不确定容器，不能自动补跑整轮。

成功状态仅是 `SYNTHETIC_PG16_REHEARSAL_PASSED_NOT_OFFLINE_ACCEPTANCE`。
它不意味着清单 MATCHED、数据库生产安全、应用就绪、物理断网、备份恢复或公司验收完成，
不增加业务/部署百分比。默认 ACL 对实际只读方案的影响仍要独立设计与批准。

## 本包可执行的本地检查（不运行 Docker/psql）

```sh
python -m unittest discover -s backend/tests -p test_offline_database_rehearsal.py -v
python -m unittest discover -s backend/tests -p 'test_offline*.py' -v
python -m unittest discover -s scripts/automation/tests -v
python -m unittest discover -s scripts/ci/tests -v
python -m py_compile scripts/offline_database_rehearsal.py backend/tests/test_offline_database_rehearsal.py
git diff --check
```

mock 通过只能证明编排契约，不证明 Docker/psql 参数、entrypoint、SQL 语法或真实 PostgreSQL
权限结果。未来获得上述明确执行批准后，才可在获准 checkout 手动启动新工作流；失败时
保留准确阻断和未验证范围，不宣称实际验证已完成。
