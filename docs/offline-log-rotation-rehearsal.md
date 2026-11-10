# 隔离合成日志有限留存演练准备

本包只新增独立脚本、回归和本文档，不修改现有 Compose、工作流、镜像配方、依赖、
迁移、应用、数据库、权限或门禁。起点为 main `952299eef8b242cd0cd3082d7bf7cc69aae8fe4a`；
同时开放的草稿 [PR216](https://github.com/Wang106/SoftwareLifeCycle/pull/216) 的 11 个文件
与本包三个新文件无重叠。共享 START_HERE、DEVELOPMENT_STATUS、HANDOFF 和进度账本
保持不动，本文档记录本包检查点，不提高任何业务或运维验收百分比。

**当前没有运行真实 Docker 日志演练。** 本包是未来执行器准备，不能称日志轮转、
压缩率、磁盘容量、重启留存或公司环境已验收。既有配置依据和治理边界见
[日志有限留存配置](offline-log-retention.md)。

## 明确有限的观察目标

纯函数先比较 api/web 现有生成配置，必须都是 `local`、`max-size=10m`、
`max-file=3`、`compress=true`，类型和值都精确相等。不读取 operator/env/company 文件。
未来专用容器使用相同四项配置，并仅对该容器显式设 `mode=blocking`，避免 daemon
默认非阻塞丢弃使最旧标记缺失被误认作淘汰。这个附加项不修改正式 Compose。
对 Docker 实际生效的 HostConfig.LogConfig 再做精确校验。

未来成功只表示以下 API 可见现象同时成立：

1. 新建且完整 CID 绑定的单个容器，stdout 与 stderr 的 BEGIN 标记分别可见。
2. 初始标记确认之后才向同一 CID 发送一次 SIGUSR1。容器内 Python 只产生固定、
   可复算、无敏感数据的 8192 条 8192 字节记录，交替写 stdout/stderr，总数据
   64 MiB，外加四条短 BEGIN/END 标记。逐条生成，不在容器里拼装整份日志。
3. 退出码为 0，未 OOM、未重启、未暂停，最后通过无 `tail`、`since`、`follow`
   参数的完整 `docker logs <CID>` 分别读取 stdout/stderr。
4. 两条 BEGIN 均已不见，两条 END 都在；各自保留的数据是逐字节校验的连续末尾
   序列，没有洞、重复、乱序、错流、外来 token 或损坏。未发生淘汰、无法读取、
   退出失败、异常诊断、超时或超过输出预算都阻断，不补造成功。

这不是 Docker 内部文件取证。最旧内容消失与尾部保留是按当前配置得到的逻辑留存
观察，不能独立证明物理文件数量、压缩实现、精确轮转时刻或整个磁盘占用。
`10m × 3` 不是硬磁盘上限；元数据、记录边界、压缩/解压暂存和其他容器/文件均可
增加空间需求。报告中 hard_disk_bound_verified、compression_measured、
physical_rotation_files_verified、restart_retention_verified 和 company_acceptance
始终为 false。即使未来成功，也不改变这些字段。

## 执行与保管边界

默认调用和 `--help` 都不执行 Docker。只有未来获准隔离演练后，才可显式调用：

```text
python scripts/offline_log_rotation_rehearsal.py --run \
  --image-id sha256:<已独立核验的64位本地镜像ID> \
  --source-commit <当前干净检出与该镜像一致的40位提交>
```

本包不执行上面命令，也不新增自动运行工作流。现有常规 CI 只发现单元测试。
`--run` 是执行开关，不会替代用户/环境授权。公司环境、真实日志及资源/安全要求
变化不能凭本包取得授权。

复用现有 API-startup 工具的本地镜像和干净源检出一致性检查。操作者必须独立确认
镜像来源可信，CID、SHA 和 revision label 本身不是来源认证。镜像必须已经在本地；
没有 pull/build/load、依赖获取或网络下载。仅借用该镜像内已有 Python 3.12.14，
入口覆盖为隔离 `-I -B -u -c` 的固定生成器，不导入/启动 API、数据库或业务代码。

- Linux/amd64、已有 Python 3.12 和 Docker、至少 512 MiB 本地临时目录空闲空间，
  现有宿主检查不代表 daemon 数据根有足够空间，也不是容量测量或预留。
- 固定本地 Unix socket、私有空 Docker 配置、最小环境，拒绝 Docker endpoint/context
  覆盖；不连接远端 daemon，不更改 daemon.json、现有容器或安全设置。
- 新容器 network=none、无端口/宿主挂载、只读 rootfs、65532:65532、cap-drop=ALL、
  no-new-privileges、私有 IPC/cgroup namespace、内存/交换 256 MiB、1 CPU、32 pids、
  无 healthcheck、restart=no、无 TTY/交互 stdin。没有应用文件日志。
- Python 等待放行最多 45 秒；120 秒 SIGALRM 也覆盖阻塞写入。宿主使用原始
  240 秒截止时间，工作阶段保留最后 30 秒用于清理，不重置截止时间。每个命令
  还有阶段超时，子进程终止后最多等待 5 秒回收；调度/内核阻塞不能被当成绝对墙钟保证。
- 最终 docker logs stdout+stderr 共用 65 MiB 捕获上限；这限制读取量，不是 daemon
  存储上限或 Python 精确 RSS 上限。其他命令更小，外部原始输出不进入最终报告。
- 私有临时目录保留本次随机名称/label、来源和 CID。CID 来自本次 create 的文件，
  禁止符号链接、长度或内容变化；inspect 校验完整 CID、镜像、label、命令和隔离配置。
  不接受外部 CID，不按名称搜索，不使用 prune，不重试 create/start/trigger/remove。
- 结束时只在同一 CID 身份再次通过后执行一次 rm --force，**删除本次合成容器及其
  日志**。失败时保留原始错误和单独 cleanup_reason；身份或结果不确定则保留私有
  本地 custody/CID 供已授权操作者核查，不猜测清理成功。

此容器没有真实日志，仍须明确未来删除自身合成日志这一后果。程序不读取、编辑、
截断、删除或上传 Docker 内部日志文件，也不上传最终日志/原始输出。

## 验证记录与剩余边界

14 项初始能力回归在实现前全部失败。新增覆盖包括固定策略、流/字节/行界限、
保留尾部完整性、固定 CID、身份/隔离漂移、create 失败后的清理、原始截止时间、
不确定清理保管、错误优先级、无 opt-in 的非执行、信号恢复及双管道输出上限。
仓库回归通过 mocked Docker/进程/信号 I/O 验证，既有门禁没有删减。

独立审查另外运行过本地 Python 合成生成器及捕获小探针，观察双流、边界、超时和
64 MiB 固定输出；没有 Docker/API/数据库。它只是本地生成器检查，不能替代实际
Engine/local-driver 兼容性或轮转演练。最终本地 24 项新回归通过发现和直接运行，
808 项全离线、52 项自动化、126 项 CI 守卫、两份 Python 内存编译、进度与 diff
检查通过；独立最终审查复跑 24 项无阻断。新增测试的两处多行 with 语法错误在
具体告知并等待五秒后仅补括号修正，未删除断言。当地未安装 pytest，完整后端/
真实 PG/前端/浏览器仍待精确候选 CI，不能把本地标准库回归当成完整 CI。
PR216 发布前复核仍为草稿开放，main 未变；本包仅创建单独草稿 PR，不转审核、
合并或启动手动真实演练。精确候选 CI 的最终状态在 PR 检查记录中另核实。

重启同一容器、重建新容器、实际压缩占用、磁盘告警、敏感信息治理、固定时长留存、
备份恢复、物理断网以及公司安装继续待另行范围与验收。删除/recreate 不保证旧日志
存续。该合成工具不会自动启动这些后续项目。

业务 36/44=82%、增量 0；模块 100/100演示/100演示/100/89/60/17；
计划 100/100/20/33/40/40/0；浏览器阶段 1/4、有限计划 8/8 不变。
