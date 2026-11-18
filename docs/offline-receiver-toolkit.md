## Joint media verification entry

`media-set-verify` validates all three actual handoffs with their independent
trusted commits/digests and emits a four-image index. It forces verify mode and
has no runtime or upload path. See [joint media verification](offline-joint-media.md)
for the nine input arguments and distinct tool/image commit meanings. The current
toolkit contains eight source modules; no new toolkit archive was delivered by
this code change. Existing individual verification commands remain available.

## Migration verification integration

The toolkit now includes eight source modules. `migration-verify` forces pure
file verification of the [fixed-source migration handoff](offline-migration-image-bundle.md).
It needs an independently trusted tool commit and handoff manifest SHA-256;
image source remains e2038a94/schema0030. Builder/fetch/context modules are not
included, and export/run/source-directory arguments are rejected. This is source
code preparation only; no updated toolkit archive or runtime media was uploaded.

# 接收端源码工具包：完整脚本依赖，不是运行时安装包

`offline_receiver_toolkit.py` 把现有接收端八个模块及全部仓库内导入依赖封装为一个
`.pyz`。接收端无需 Git、pip、项目 checkout 或工具包解压步骤，使用已有的
Linux/Python 3.12+ 标准库直接运行。需要已有 `/proc/self/fd` 与受信本地文件系统；
不声称支持 Windows 原生运行、恶意并发修改或公司机器安装。

包含的原样模块：`offline_image_bundle`、`offline_media_transport`、
`offline_media_retention`、`offline_operator_assembly`、`offline_readonly_preflight`、`offline_postgres_image_bundle`、`offline_migration_image_bundle`、`offline_joint_media`。
此外只有固定入口、README 和逐文件大小/SHA256清单。标准库不是打进包里的 Python；
Python、Linux、Docker、Compose、PostgreSQL、API/Web 镜像、数据库、凭据和公司文件均不包含。
原来的49KB源码ZIP不能作为本工具包完整性或当前版本的证据。

## 在受信开发环境生成源码工具包

以下仅打包已审核源码，不构建镜像、不下载依赖、不运行容器或上传文件。
`TOOL_COMMIT` 是独立核对的完整工具提交，必须等于指定源码 checkout 的 HEAD；
与固定镜像提交 `e2038a9462770a29254674dd86c0e7b26b26a221` 不同。
生成器从该提交的八个固定 Git blob 读取，不读取工作区的未提交脚本、凭据或其他文件。
它验证普通文件、大小、静态导入闭包及唯一源/schema0030映射；这不是任意代码安全分析。
工具源码本身须先经过审查，不能仅相信包内自报提交或哈希。

```sh
: "${TOOL_SOURCE:?填写已审核工具源码checkout绝对路径}"
: "${TOOL_COMMIT:?填写独立核对的40位工具提交}"
: "${NEW_TOOLKIT:?填写尚不存在的工具包绝对路径}"
python3 -B scripts/offline_receiver_toolkit.py --run \
  --source-root "$TOOL_SOURCE" --expected-tool-commit "$TOOL_COMMIT" \
  --destination "$NEW_TOOLKIT"
```

父目录必须已存在，路径不能经过符号链接；输出只允许全新文件，最大4MiB。
生成器固定ZIP成员与元数据，使用ZIP_STORED；同一生成器版本及同一工具提交的原始脚本
得到相同字节。入口和README来自生成器，清单中的工具提交只标识八个原始模块的来源；
须同时审查生成器版本，并独立保留整个输出摘要。
只有写入、回读比较、fsync及关闭成功才给出 `RECEIVER_SOURCE_TOOLKIT_CREATED_NOT_RUNTIME`
回执。单独保留回执中的工具提交、实际字节数、SHA256。失败/中断/回执丢失可能留下输出，
先核查，不覆盖、不删除、不盲目重跑。成功并不代表已传输、已安装或获准部署。

## 传输与接收

仅在传输范围另行落实后复制工具包，接收前后比对独立可信回执的完整SHA256。
不能只计算收到文件的摘要再当作可信值，也不要先运行收到的工具来证明它自己可信。
Windows准备机可使用既有 `Get-FileHash -Algorithm SHA256`，Linux可使用既有
`sha256sum`；这些只计算摘要，操作员仍须比较完整可信值，任何不一致都停止。
无需USB；既有计划可由笔记本经内网复制到服务器，但本工具不访问网络或修改安全设置。
不要将源码工具包夹进严格五文件镜像交接目录。工具包摘要、媒体传输包摘要和内层
可信交接清单摘要是三个不同值，不能互换。

核验工具包本身后，在已满足条件的Linux接收端使用隔离模式：

```sh
: "${TOOLKIT:?填写已核验工具包绝对路径}"
python3 -I -S "$TOOLKIT" --help
python3 -I -S "$TOOLKIT" transport --help
python3 -I -S "$TOOLKIT" bundle --help
python3 -I -S "$TOOLKIT" assembly --help
python3 -I -S "$TOOLKIT" retention --help
python3 -I -S "$TOOLKIT" preflight --help
python3 -I -S "$TOOLKIT" postgres-verify --help
```

无命令只显示帮助；未知命令拒绝。上述帮助不读取媒体或创建操作员目录。
现有指南中的 `python scripts/offline_media_transport.py ...` 可以替换为
`python3 -I -S "$TOOLKIT" transport ...`；其余模块分别对应 `bundle`、`assembly`、
`retention`、`preflight`，后续参数完全相同，不能省略可信期望值或拒绝条件。
遵循[传输包核验](offline-media-transport.md)、[组装器](offline-operator-assembly.md)及
[安装操作顺序](offline-operator-installation.md)。组装目标必须不存在、父目录已存在；
默认数据库声明仍为false，预检拒绝是预期停止点，不应改成true来绕过验证。

本包测试在仓库之外、禁用site-packages及PYTHONPATH的子进程中执行归档入口，使用不可运行
的合成镜像验证传输解包→交接校验→组装→默认预检拒绝，保持原件不变。它不证明真实
镜像、Python/系统安装介质、物理离线运行或公司验收。未执行新的真实镜像构建或上传；
原构建一次授权已使用，实际媒体保留仍需零新增费用、内容检查、16GiB及七天条件全部满足。

## PostgreSQL 独立接收验证

新增 `postgres-verify` 固定调用 PostgreSQL 模块的 verify 模式；不接受 export、
`--run` 或 `--destination`。打包原始模块并不授予运行其中导出函数的权限；
该入口不连接 Docker、不创建数据库、不解压镜像，也不执行 Git 或安装依赖。

```sh
: "${PG_HANDOFF:?填写独立的四文件PostgreSQL交接目录}"
: "${PG_TOOL_COMMIT:?填写独立可信PG交接回执中的完整工具源码提交}"
: "${PG_MANIFEST_SHA256:?填写独立可信PG交接清单摘要}"
python3 -I -S "$TOOLKIT" postgres-verify \
  --directory "$PG_HANDOFF" --expected-commit "$PG_TOOL_COMMIT" \
  --expected-manifest-sha256 "$PG_MANIFEST_SHA256"
```

PostgreSQL交接仍严格为 postgres.tar、manifest.json、evidence.json、COMPLETE；
不要混入API/Web五文件交接或源码工具包。PG_TOOL_COMMIT是导出工具来源，
不是上游PostgreSQL源码，也不是API/Web固定源e2038a94。PostgreSQL仍验证其独立
固定官方镜像ID/配置/层链；API/Web的e2038a94/schema0030映射完全不变。
当前生成器需要包含全部八个模块的已审核提交；旧提交缺少任一模块时在输出前拒绝。

合成测试只在测试仓库替换不可运行镜像的配置摘要和层数，验证隔离归档入口的
成功、错误摘要拒绝和原件不变。生产模块的官方固定值没有修改；测试不是实际
PostgreSQL媒体、数据库或安装验收。源码工具包的生成/交付与运行镜像交付仍分开。
