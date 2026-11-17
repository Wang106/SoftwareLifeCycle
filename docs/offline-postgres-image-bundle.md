# PostgreSQL 固定官方镜像离线交付准备

## 范围和验收边界

本包基于 main `975e95c76b9d5757acf678b4fd220882ff8a5a4a`（PR237），适配并复用
未发布本地实现 `7748a16a601612242875fa835c685e6b914bb9b1`，只准备
固定官方 PostgreSQL 镜像的本地导出及接收侧只读核验。既有 API/Web 双角色协议、
应用镜像预检、迁移镜像工具、工作流、依赖、数据库迁移和分支门禁均不修改。
不依赖其他尚未发布的本地开发包。

导出入口默认关闭，未来另行获准执行时只使用已经存在的可信本地固定镜像；
不拉取、不构建、不加载、不启动容器或数据库、不联网下载、不上传、不自动重试。
独立核验只读取交付原件，不执行 Docker、git 或其他子进程，不联网、解压或提取层。

工具源码提交号只标识交付工具版本，不是 PostgreSQL 官方镜像的源码 revision。
摘要和本地 RepoDigest 不能代替签名、发布者身份认证、漏洞扫描或许可审查。
通过归档核验不等于允许执行 Docker load/start，更不等于数据库、迁移、备份恢复、
只读账户、物理断网或公司安装验收。

## 为什么先补这件材料

当前API/Web五文件交接和接收源码工具已完成开发；实际运行镜像仍未交付，
这些工具不包含PostgreSQL基础镜像。
本工具实际可将未来已获准取得的固定本地镜像保存为四文件包，并在接收侧验证真实归档字节，
不是永远返回BLOCKED的声明检查器。旧迁移包`b84604d`仍绑定29条迁移，旧运行时计划
`3ae830b`只检查声明，本轮均未移植；三个历史工作树保持不变。
本轮回归确认此处digest/ID与当前`offline_migration_database_rehearsal.py`完全一致，
不更新镜像pin，不把工具提交或API/Web固定源`e2038a94`当作PostgreSQL上游源码身份。

本包没有执行任何真实镜像下载、导出、构建或数据库启动。此前一次真实API/Web构建授权已用完，
也不涵盖PostgreSQL交付。现有媒体上传许可仅涉及原API/Web范围；本四文件包不能偷偷加入
原五文件交接或上传范围。实际取得、保存、传输此镜像需要独立明确执行范围及原费用/内容条件。
PR237版本的接收源码工具`.pyz`仅含原五个模块，不包含PostgreSQL工具；如需分发，
应使用已审源码及其`offline_image_bundle`、`offline_readonly_preflight`依赖，不声称旧工具包已包含它。

## 已核定的官方镜像合同

以下为旧包2026-11-12的历史官方元数据核对记录，不是本轮重新联网验证；未下载任何镜像层。manifest 与 config
原始字节的 SHA256 均重新计算，与 descriptor 和现有项目 pin 一致：

- linux/amd64 manifest：`sha256:5983db9a9c6ad225a48a46cfe2e03e6680b1826662befd0465eb05b34cb1c64e`，3641 字节。
- config/image ID：`sha256:cadebe7c08430c896edac883fa92f8de2c36e330805e770fbee8a7eae13f144f`，10133 字节。
- 版本：16.15-bookworm；固定上游源码 revision：`9d15534160ade17f2b6c455a39ee967c49b1937d`。
- 原始 manifest 的类型是 `application/vnd.oci.image.manifest.v1+json`，不是根据网页摘要猜测的 Docker MIME。
- config 明确 `linux/amd64`，rootfs 包含 14 个有序未压缩层 diff_id。
  固定原始 config 摘要约束整个配置及有序 diff_id，不重排或重新序列化官方 config。

官方 config 的入口是 `docker-entrypoint.sh`，默认命令 `postgres`，停止信号 `SIGINT`；
声明 `5432/tcp` 和 `/var/lib/postgresql/data` 数据卷，包含 PG16 专用环境变量，
未指定非 root 用户。这些是官方镜像事实，不是生产启动建议或已验证的运行隔离。
因此它必须使用独立数据库镜像合同，不能放宽应用镜像的 revision、环境变量、
无卷或非 root 规则来使其通过。

来源：

- [Docker Hub 的 16-bookworm 元数据](https://hub.docker.com/v2/repositories/library/postgres/tags/16-bookworm)
- [固定官方 registry manifest](https://registry-1.docker.io/v2/library/postgres/manifests/sha256:5983db9a9c6ad225a48a46cfe2e03e6680b1826662befd0465eb05b34cb1c64e)
- [固定官方 config](https://registry-1.docker.io/v2/library/postgres/blobs/sha256:cadebe7c08430c896edac883fa92f8de2c36e330805e770fbee8a7eae13f144f)
- [固定上游 Dockerfile](https://github.com/docker-library/postgres/blob/9d15534160ade17f2b6c455a39ee967c49b1937d/16/bookworm/Dockerfile)

不跟随可变 tag、自动更新 pin 或替换平台。新版本需重新核对合同和独立审查。

## 独立归档合同与有限支持布局

交付目录只有 `postgres.tar`、`manifest.json`、`evidence.json` 和空普通文件 `COMPLETE`。
清单携带工具源码提交、固定官方镜像合同、归档大小/摘要及证据摘要；证据只包含固定的
核验声明和限制，不写入主机环境、Docker 配置、原始日志、业务数据或凭据。
接收方必须从独立可信渠道取得期望工具提交号及清单 SHA256，不能自读包内值充当期望。

归档仅接受未压缩、单镜像、无 tag 的 docker-save 合同。原始 config 必须完整匹配
固定10133字节及 SHA256，14个未压缩层的实际字节摘要、顺序和 tar 结构都要通过。
外层路径穿越、重复成员、链接、设备、稀疏扩张、超限元数据、尾部垃圾、未知文件和
未引用目录均拒绝，不提取任何文件。层内部合法链接等结构不等于镜像内容安全审查。
主清单只支持 `Config/RepoTags/Layers`，或再加严格 `LayerSources`；RepoTags必须null或空列表。

现有仓库记录曾使用 Docker 28.0.4。本包另核对了其固定版官方 classic exporter 源码，
定义**受限 UTC 布局**：单一完整镜像ID导出包含33个普通文件，即主manifest、OCI index/layout、
固定config、14层、1个OCI manifest和14个兼容配置blob，以及必要目录。

- OCI index只能引用一个无tag、无额外字段的manifest；它必须引用同一个固定config及
  完全相同顺序、摘要、实际大小的未压缩层。所有blob名称须与原始字节摘要一致。
- 14个兼容配置每个不超过16KiB，只接受官方Config/V1Image结构的精确零值或固定PG配置投影，形成一条
  无分叉、无孤立节点的完整parent链。前13个时间必须为 `1970-01-01T00:00:00Z`，
  最后一个使用固定官方config时间和配置。
- 兼容配置内的v1 ID只做格式、唯一性和链关系检查，**没有重算Moby CreateID**，不作为
  镜像或层来源证明。内容身份始终由固定原始config及其14个有序diff_id约束。
- 非UTC epoch变体、其他存储后端、未知附加字段、其他Docker布局、压缩层描述、外部URL、
  多镜像、Parent和repositories不在该合同内。未知格式直接阻断，不重写或“修复”归档。

这是源码核对及合成测试支持范围，不是实际Docker28.0.4导出通过证据；也未运行Go原生
序列化交叉验证。最小classic布局的测试同样只用不可运行的合成tar，不声称覆盖所有旧版Docker。

固定源码依据：[save.go](https://github.com/moby/moby/blob/v28.0.4/image/tarexport/save.go)、
[Config字段](https://github.com/moby/moby/blob/v28.0.4/api/types/container/config.go#L44-L72)、
[V1Image字段](https://github.com/moby/moby/blob/v28.0.4/image/image.go#L32-L85)、
[CreateID定义](https://github.com/moby/moby/blob/v28.0.4/image/v1/imagev1.go#L42-L69)。

## 将来获准后的入口

以下命令本包开发中未真实执行；固定镜像须已通过独立获准方式存在于可信Linux本地daemon。
没有镜像、配置不符或Docker布局不支持时停止，不自动拉取、安装或更换daemon。

```sh
# EXPECTED_COMMIT 必须由独立可信交接提供，不能任意使用未知 checkout 的当前值。
python scripts/offline_postgres_image_bundle.py export --run \
  --expected-commit "$EXPECTED_COMMIT" --destination "$NEW_HANDOFF"

# 在接收侧以可信工具源码和独立取得的期望值，只读核验。
python scripts/offline_postgres_image_bundle.py verify \
  --expected-commit "$EXPECTED_COMMIT" --directory "$HANDOFF" \
  --expected-manifest-sha256 "$EXPECTED_MANIFEST_SHA256"
```

导出前后都绑定干净工具提交及三个运行源码文件。只连接固定Unix socket，使用新建空白
私有Docker配置和环境白名单，不继承登录凭据；先核对固定image ID、RepoDigest和平台，
再按不可变ID执行一次save。不会读取或接受任意镜像/tag/URL参数。

目标必须是新目录，父链与文件以no-follow描述符固定身份；硬链接和特殊文件拒绝。
归档上限2GiB，目标文件系统预留3GiB，属于保守支持界限，不是已测镜像大小。
输出流式写入，不将大归档读进内存。子进程循环save截止600秒、导出整体SIGALRM预算1200秒，
独立核验预算600秒，包含最终截止检查；不是阻塞内核I/O、清理或宿主故障下的硬墙钟保证。
既有活动timer不覆盖。失败不自动重试save、load、删除目标或扩大清理。

全部payload核验、关闭、同步后才尝试创建COMPLETE。标记或后续收尾/输出中断使结果不确定时，
保留可用的工具commit及清单摘要用于独立核验；不将空标记本身当可信成功回执，不盲目重跑。

## 历史未发布包验证检查点（不代替当前候选）

2026-11-12 本地验证：最初19项缺能力回归全部失败，最终53项集中、976项全离线回归通过；
52项自动化、126项CI守卫、编译、文档shell语法、进度和diff检查通过。
另在实际新进程中检查help、默认调用、缺少--run均保持不执行。
官方config的原始摘要/大小、14个diff_id及精确辅助配置投影已独立核对。

开发中发现的合法git status空stdout和直接CLI的__main__源码绑定问题，均先加失败回归，
具体告知并等待后修正；预算注释也按通知改为准确的SIGALRM限制。没有降低文件、容量、
内容或原应用门禁。16KiB/helper的新增支持上限保留先失败反例。独立终审另发现成功导出后
stdout抛SystemExit会丢失回执，新增4项回归先复现，再按具体通知和等待修正；只在已有
完成回执时报告不确定，无回执、help及verify的SystemExit仍原样传播。

独立终审重跑53项并通过，另核对官方元数据、14节点辅助配置及86种突变拒绝、7种源码
绑定场景、受限进程流和实际短timer的恢复、三种最终stdout中断状态，无剩余代码阻断。
干净本地提交上的实际源码只读绑定已单独通过。本地缺pytest和真实PostgreSQL环境，
完整后端、前端、浏览器及精确候选CI未运行。全部tar夹具不可运行，未执行真实
pull/build/save/load、数据库、HTTP服务或新的工作流，也未上传文件。

业务 36/44=82%、增量0；模块100/100演示/100演示/100/89/60/17；
计划100/100/20/33/40/40/0；浏览器阶段1/4、有限计划8/8不变。

## 当前候选验证 — 2026-11-17

先将53项既有合成回归移到当前main，因缺少实现全部失败；再移植原实现，53项通过。
新增当前固定pin对齐、真实临时Git源码绑定、缩写参数拒绝、回执短写和诊断流故障五项；后三项先失败，再修复。
成功输出使用检查写入长度与flush的回执；输出失败保留不确定状态和可用可信摘要，不自动重试。
命令行禁止长参数缩写；诊断输出本身失败仍返回失败，不打印未过滤异常。
归档合同、预算、原件不可变、COMPLETE最终创建和原API/Web规则保持不变。
当前58项集中回归通过；全离线、自动化、CI守卫与独立复审结果记录于HANDOFF。
全部测试镜像是不可运行合成tar，进程探针只验证受控输出/超时，不执行Docker或数据库。
上述PR238导出/验证包未执行虚拟机或服务器操作，也未修改接收源码工具；
后续接收入口扩展见下节。

## 独立接收端工具入口

包含本模块的新版本[接收端源码工具包](offline-receiver-toolkit.md)提供
`postgres-verify`，固定为文件验证模式；保留相同的独立可信工具提交、清单摘要、
四文件目录及原件不变要求。它不能通过该入口导出镜像或执行数据库操作。
旧五模块工具包不包含此能力，不能仅凭文件名判断接收端版本。
工具来源提交、API/Web镜像源e2038a94及PostgreSQL官方固定镜像ID是不同身份。
