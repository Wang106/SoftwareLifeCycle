# 离线只读安装操作指南：从镜像交接到有条件启动

本指南把现有工具串成一条操作顺序，解决镜像交接清单与操作员清单不兼容的问题。
它不是一键安装器，也不附带可下载的完整离线安装包。当前可完成的是准备与配置校验；
真实导入、应用启动、数据库权限、断网运行及公司验收必须分别取得实际证据。
不要直接运行仓库根目录的 `docker-compose.yml`：它是开发配置，含构建、开发凭据及迁移/seed 行为。

## 1. 先确认执行位置与缺失项

- 已有镜像构建/导出路线只支持 Linux x86_64、Python 3.12、本地 Docker Engine 和
  Compose >=2.30.0。不是在 Windows Server 或 macOS 直接执行的安装方案。
  候选目标 Windows Server 2016 → Hyper-V → Ubuntu 24.04 amd64 VM 尚不等于已安装或已验收。
- 联网准备机必须有已批准的构建/下载条件；现有构建器检查临时目录及 Docker 文件系统
  各至少 20 GiB 可用空间。导出另有两镜像合计 16 GiB 上限及额外 1 GiB 余量检查，
  并不保证峰值空间足够。目标机容量、平台兼容性及运行时安装介质仍需独立确认。
- 目标必须已有获准的 PostgreSQL 16、真实迁移到 `0030_private_upload_sessions` 的
  合成数据库，以及非所有者、非超级用户的 SELECT-only 角色。这里只读运行应用，
  不提供数据库安装、迁移、seed、建角色、授权或修改 PUBLIC 权限的隐含步骤。
- 两个应用镜像不包含可安装的 Ubuntu/Hyper-V/Docker/Compose/PostgreSQL 套件。
  缺这些输入时停在准备阶段；不得在断网目标上临时拉镜像/包或连接公司、旧公共数据库。
- 仓库没有支持完整安装生命周期的 image loader；下文 Docker 导入命令只是尚未实测的
  人工操作例子。任何真实导入/启动都需要明确机器、daemon、合成目标及运行范围获准，
  不能从本指南、CI 成功或配置输出推导执行许可。

## 2. 联网准备：取得真正保留的镜像及可信回执

使用独立核对提交的受信、干净 checkout；以下路径变量由操作员设置为实际绝对路径，
没有默认值。`NEW_HANDOFF` 必须不存在，父目录必须已存在；不能复用空目录或失败目录。
本节命令会下载、构建及运行依赖烟测，**本指南编写时没有执行**，只在这些操作已获准后使用：

```sh
: "${NEW_HANDOFF:?填写不存在的镜像交接绝对路径}"
python scripts/offline_image_rehearsal.py --run --export-bundle "$NEW_HANDOFF"
```

成功后从本次可信构建进程的 `image_bundle` 回执，独立保存完整 `source_commit` 和
`manifest_sha256`；不能从收到的包计算一个摘要再称其为可信期望值。
镜像/标签/摘要一致性不是签名认证，仍需独立的来源、安全及许可证审核。
详细限制见[镜像准备](offline-image-rehearsal.md)和[镜像交接包](offline-image-bundle.md)。

手动 CI 的 `export_bundle=true` 只在临时 runner 导出并校验，**没有持久可下载制品**。
不能从历史成功运行恢复那些镜像；需要在获准、可保留输出的环境重新准备。
文件传输、介质/接收方和可信回执交付单独安排；本指南不执行上传或传输。
失败或完成状态不确定时保留原目录与可信回执，不覆盖、不删除、不盲目重复导出。

## 3. 收到包：先核验，原件始终保持五个文件

在目标侧使用独立取得的受信工具 checkout 和可信回执。设置 `HANDOFF` 为收到包的绝对路径，
`EXPECTED_COMMIT` 为回执中的 40 位小写十六进制提交，`EXPECTED_MANIFEST_SHA256`
为独立保存的 64 位小写十六进制摘要。不要把占位文字或旧运行值当作实际输入。

```sh
: "${HANDOFF:?填写交接包绝对路径}"
: "${EXPECTED_COMMIT:?填写独立可信提交}"
: "${EXPECTED_MANIFEST_SHA256:?填写独立可信清单摘要}"
python scripts/offline_image_bundle.py verify "$HANDOFF" \
  --expected-commit "$EXPECTED_COMMIT" \
  --expected-manifest-sha256 "$EXPECTED_MANIFEST_SHA256"
```

只有退出 0 且返回 `IMAGE_BUNDLE_VERIFIED_NOT_OFFLINE_ACCEPTANCE` 才继续。
原件严格包含 `api.tar`、`web.tar`、`manifest.json`、`evidence.json`、`COMPLETE`。
不要在里面加 `operator.json`、密码、Compose、日志或验证回执；不要修改 `manifest.json`。
`COMPLETE` 本身不证明完整性；校验通过也不证明来源认证、数据库可用或可安全运行。
工具只读、不解包、不调用 Docker；原件与后续副本须留在受信且无并发修改的本地存储。

## 4. 单独组装操作员目录：不是更名原清单

操作员预先准备三个互不嵌套的私有绝对目录，均位于受信本地 Linux 文件系统：

- `HANDOFF`：上节五文件原件，保持不变。
- `OPERATOR`：全新工作目录，只放两个独立普通文件镜像副本、新操作员清单、操作员声明和私密数据库输入。
- `OUTPUT`：另一私有输出目录，用于渲染、解析、运行记录；不能在原件内，也不能有旧配置可被误用。

镜像复制不是解包：将已核验的 `api.tar`、`web.tar` 逐字节复制到 `OPERATOR`，
不得覆盖旧文件、用链接代替副本或移动原件。用源清单中的 size/SHA256 核对副本，
之后配置预检还会重新检查实际镜像字节；复制、任何校验或来源状态不确定就停止。

在 `OPERATOR/manifest.json` 新建 JSON，按如下**完整字段映射**填写，不添加其他键：

| 新操作员清单字段 | 唯一取值来源 |
| --- | --- |
| `format` | 固定字符串 `slc-offline-readonly-v1` |
| `source_commit` | 已核验交接清单的 `source_commit`，必须与独立可信提交一致 |
| `required_db_revision` | 固定字符串 `0030_private_upload_sessions` |
| `images.api` | 原清单的整个 `images.api` 对象，字段及值不变 |
| `images.web` | 原清单的整个 `images.web` 对象，字段及值不变 |

每个 image 对象恰有 `archive`、`size`、`sha256`、`image_id`、`platform`、`source_commit`。
`size` 保持 JSON 整数，两个 `archive` 分别保持 `api.tar`/`web.tar`；镜像 ID 是完整
`sha256:` 加配置摘要，不用标签替代。不复制交接清单的 `evidence_sha256` 到新清单，
也不复制/改写 `evidence.json` 或 `COMPLETE` 来伪装新的交接包。

交接清单 `slc-image-handoff-v1` **不能直接交给 Compose 预检**；
新清单也不能拿去冒充原交接清单通过 handoff verifier。映射只是格式转换，
不会认证来源、增加权限、证明数据库状态或批准部署。

将 [operator.example.json](../deploy/offline-readonly/operator.example.json) 内容复制为
`OPERATOR/operator.json`。保留默认两个 `false`；不要为了通过预检直接改为 `true`。
[manifest.example.json](../deploy/offline-readonly/manifest.example.json) 仅供对照结构，
其中占位提交、零尺寸、假摘要不能使用。

## 5. 数据库与秘密输入是单独的停止点

只有针对明确合成目标/现有角色的独立准备与验证已完成、获准并记录后，操作员才可如实
填写 `database_preprovisioned` 和 `database_readonly_role`。预检要求它们为 true，
但声明本身不证明事实。当前联合演练的临时 PostgreSQL 超级用户只读事务，
**不是**本安装配置要求的 SELECT-only 角色证据。

按[数据库证据清单的操作员顺序](offline-database-readiness.md#以后另行获准时的操作员顺序当前不执行)
在已获准目标采集新证据：包括真实 psql 退出状态、来源/目标/角色和时效确认。
不要自行填 JSON，不使用旧证据，不把 `CHECKLIST_MATCHED` 当作启动授权。
默认 PUBLIC 权限可能导致不匹配；停止并独立审核，不降低清单、不悄悄撤权或改授权。
已有证据文件的本地比较命令为：

```sh
: "${DB_EVIDENCE:?填写本次真实采集的私有证据绝对路径}"
python scripts/offline_database_readiness.py --evidence "$DB_EVIDENCE"
```

获准操作员通过已有安全方式在 `OPERATOR/database.env` 提供一行 `DATABASE_URL`。
这里不提供可复制的凭据或默认密码，也不让秘密经过命令参数、shell 历史、聊天或标准输出。
文件须已为 0600 或更严格的普通文件；本指南不修复权限或生成凭据。
URL 必须使用 `postgresql+psycopg`、明确只读角色/密码、`127.0.0.1:5432` 和合成库，
无额外选项/注释/环境变量；密码分隔符须正确编码。完整限制见
[现有配置预检说明](offline-readonly-config-preflight.md)。任何缺项都停在这里。

## 6. 渲染配置：输出文件存在不等于成功

从受信工具 checkout 根目录运行。`OPERATOR`、`OUTPUT` 已是上文审核的私有目录，
以下仅限制新输出的权限，不改变现有文件/目录权限；已有目录不私有则停止。
在一个专用 Bash 会话中执行，禁止命令追踪 `set -x`，所有输出名必须全新。

```sh
: "${OPERATOR:?填写操作员目录绝对路径}"
: "${OUTPUT:?填写私有输出目录绝对路径}"
umask 077
set -C
if ! python scripts/offline_readonly_preflight.py "$OPERATOR" \
    > "$OUTPUT/compose.json" 2> "$OUTPUT/preflight.stderr"; then
  printf '%s\n' 'STOP: 配置预检失败，输出不可用于启动。' >&2
  exit 1
fi
```

`set -C` 拒绝覆盖已存在的普通输出文件；仍需受信目录和无并发修改。
shell 重定向先创建文件，所以必须检查退出 0，再核对 stderr 的 `CONFIGURATION_ONLY`
以及配置内容。失败时保留诊断，不把空/部分/旧文件当有效配置，不直接重跑覆盖。
配置含本地秘密文件路径，诊断和稍后的解析/运行输出均只留私有本地，不能贴到聊天、PR 或 CI。

## 7. 后续人工运行例子：本包未执行

**本节不是继续执行许可。** 仅在准确机器、独立操作员拥有的隔离本地 daemon、
镜像加载、两个应用进程及人工验收已获准后逐步使用。这里固定本地 socket
`unix:///var/run/docker.sock`，不支持自动改用远程 context、rootless socket 或其他主机。
权限或路径不符则停止，不 sudo、不加组、不改安全设置。

先独立检查该 daemon 没有既有业务部署、冲突镜像标签或同名 Compose 项目，
主机 8000/3000 端口空闲、5432 是已批准的合成数据库。`docker image load` 会恢复镜像及标签，
可能影响已有标签；不能在任意共用 daemon 上安全照抄。存在冲突或归属不明就停止。
`PROJECT` 是此次已确认未被占用的明确项目名，不沿用别人的项目或开发项目。

以下 Bash 函数仅缩短示例中的重复参数，不是仓库新增工具；承接上节同一专用会话。
限定子进程环境、明确单一文件/项目/项目目录、使用 `/dev/null` 阻止默认 `.env` 加载，
不合并 ambient Compose override。受信 PATH/HOME 及其中 Docker CLI/plugin 配置须事先审核。

```sh
: "${PROJECT:?填写本次获准且未占用的Compose项目名}"
slc_docker() {
  env -i PATH="$PATH" HOME="$HOME" docker \
    --host unix:///var/run/docker.sock "$@"
}
slc_compose() {
  slc_docker compose --env-file /dev/null --project-directory "$OUTPUT" \
    --project-name "$PROJECT" --file "$OUTPUT/compose.json" "$@"
}
if ! slc_compose config --format json --no-env-resolution \
    > "$OUTPUT/compose.project.json" 2> "$OUTPUT/compose.project.stderr"; then
  exit 1
fi
if ! slc_compose config --format json --no-env-resolution --no-interpolate \
    > "$OUTPUT/compose.model.json" 2> "$OUTPUT/compose.model.stderr"; then
  exit 1
fi
```

两个解析视图均须成功并复核：只有 api/web、精确本地 image ID、`pull_policy: never`、
无 build/数据库服务/自动迁移/seed；全部身份与提交开关关闭；非 root、只读根目录、
cap_drop、no-new-privileges、原 tmpfs/日志限额、无重启、两个 loopback 监听保持。
`--project-name` 明确覆盖渲染文件的固定 name，两个视图的有效 name 应为本次 `PROJECT`。
不要运行裸 `compose config`、`--environment` 或去掉 `--no-env-resolution`：
这可能将 `database.env` 的 DATABASE_URL 展开到输出。两个安全视图都保留私有本地。
解析仅证明配置可解析，不是授权、真实启动或健康检查。

每条加载都只执行一次，前一条退出正常并确认结果后才进入下一条；
失败/超时/响应丢失时状态可能不确定，先只读核对，不重复 load、不删除现有镜像。

```sh
if ! slc_docker image load --input "$OPERATOR/api.tar" \
    > "$OUTPUT/load.api.stdout" 2> "$OUTPUT/load.api.stderr"; then exit 1; fi
```

```sh
if ! slc_docker image load --input "$OPERATOR/web.tar" \
    > "$OUTPUT/load.web.stdout" 2> "$OUTPUT/load.web.stderr"; then exit 1; fi
```

从已核验的两个 manifest image 记录分别取出完整 ID，填写 `API_IMAGE_ID`、`WEB_IMAGE_ID`，
不用 load 输出里的标签推导可信 ID。然后只读检查实际本地镜像：

```sh
: "${API_IMAGE_ID:?填写已核验api精确image_id}"
: "${WEB_IMAGE_ID:?填写已核验web精确image_id}"
if ! slc_docker image inspect "$API_IMAGE_ID" "$WEB_IMAGE_ID" \
    > "$OUTPUT/images.inspect.json" 2> "$OUTPUT/images.inspect.stderr"; then exit 1; fi
```

逐个核对实际 `.Id`、linux/amd64 和 `org.opencontainers.image.revision` 与可信清单相符，
并复核禁用设置/权限及数据库条件。缺镜像或不匹配就停止，不改标签、不 pull、不 build。
原镜像默认 `/bin/false` 是有意拒绝直接启动；必须用经审查的渲染配置，不用裸 `docker run`。
再次确认项目/端口无冲突、配置/镜像/数据库自检查后未改变，才可执行一次：

```sh
if ! slc_compose up --detach --no-build --pull never --no-recreate api web \
    > "$OUTPUT/start.stdout" 2> "$OUTPUT/start.stderr"; then exit 1; fi
```

`--no-recreate` 不能替代启动前无冲突检查，也不证明既有容器属于本次操作。
启动成功只是进程操作返回成功，healthcheck 在本配置中禁用，不能当作就绪或业务验收。
发生不确定结果时保留本次记录并核对准确容器归属；不重复 up，不自动 down/rm/prune，
不按模糊名称清理、不移除孤儿。停止/清理须由操作员按本次已确认资源与批准范围处理。

## 8. 启动后的验收边界与停止条件

- 应用与 Web 分别仅监听 Linux 主机的 `127.0.0.1:8000` 和 `127.0.0.1:3000`。
  Compose 使用 `network_mode: host`，共享宿主网络，**不是网络隔离或物理断网**。
  没有阻断外连或保护其他宿主服务。不得将无认证只读配置公开到其他机器或真实公司数据。
- 浏览器须在同一 Linux 主机访问 `http://127.0.0.1:3000`，不是在 Windows 宿主或远程电脑
  用同一个 localhost 地址。无本机浏览器则该项未验收；转发、代理、监听地址、HTTPS、
  防火墙或网络调整需要单独方案与许可，本指南不启用它们。
- 操作员核对实际监听、`/health`、`/health/live`、`/health/ready` 及双语页面、禁用登录/写入。
  `/health/ready` 的数据库检查只覆盖所需迁移版本，不证明 SELECT-only 权限、完整 schema、
  数据未改动或外连受阻；必须结合独立数据库证据与实际验收。503/错误/未知即未就绪。
- 新 Web 单独探针使用 `network=none` 且拒绝 API 的 8000 监听；不能原样接到共享 API/PG
  namespace 来声称整套联合验证。其 mock 成功不证明上述 host-network 配置能运行。
- 物理断网、禁止外连/隐含下载、真实 Web/API 集成和公司验收仍须独立执行。
  只看到页面、依赖烟测、镜像摘要或超级用户只读事务成功，都不能关闭这些验收项。

本指南参数依据现有脚本及 Docker 官方
[Compose 全局参数](https://docs.docker.com/reference/cli/docker/compose/)、
[config](https://docs.docker.com/reference/cli/docker/compose/config/)、
[up](https://docs.docker.com/reference/cli/docker/compose/up/)、
[image load](https://docs.docker.com/reference/cli/docker/image/load/)、
[image inspect](https://docs.docker.com/reference/cli/docker/image/inspect/)和
[Docker CLI](https://docs.docker.com/reference/cli/docker/)文档核对。
官方当前参数文档不是本机版本实测；目标版本不支持任何必要参数时停止，不删除安全参数迁就。

## 本文候选的验证记录

基线 main `a66d20b2eab8d7949a67d14a8ca32f6ff1fec5fc`（PR221），
[CI43011453078](https://github.com/Wang106/SoftwareLifeCycle/actions/runs/43011453078)
通过 3777 tests、3045 subtests、309 PostgreSQL cases 无跳过及现有完整门禁。
已核验同一 main 的 Cloudflare `db1bc924` 成功；Actions
[deploy43013280579](https://github.com/Wang106/SoftwareLifeCycle/actions/runs/43013280579)与
[continuation43013280666](https://github.com/Wang106/SoftwareLifeCycle/actions/runs/43013280666)
跳过，Render 未核验。以上均为基线，不是本文候选 CI 或离线安装证据；没有新手动 API 运行。

本文仅整理已有步骤与明确停止点，无新安装器/探针、生产代码、测试、工作流、依赖或门禁变更。
本地909既有离线、52自动化及126CI守卫测试全部通过、零跳过；微型合成export/verify→精确字段映射与副本→false声明拒绝→
fixture-only预检渲染→原件字节/mtime不变并再次核验通过。9段shell仅语法检查、本地链接、
进度及diff检查通过；不新增测试。合成镜像不可运行，合成声明/凭据不是实际数据库证据。
真实镜像导出/传输/加载、Docker/Compose 解析与启动、HTTP、数据库及公司机器均未执行。
本地验证与独立复审均通过，无阻断；未提交/发布，待发布及新候选完整CI。业务 36/44=82%、增量0；模块100/100演示/100演示/100/89/60/17；
计划100/100/20/33/40/40/0；浏览器阶段1/4、有限计划8/8不变。
