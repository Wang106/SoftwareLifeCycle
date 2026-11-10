# 迁移后 API 镜像只读探针：未接线内部助手

## 已执行的基线，不是本包运行证据

正常 fetch 的基线为 PR210 合并后的 main
`36ca2292f8a23b7d6320d0342269a4dfd635ef61`。同一提交的两次联合演练
[42758822529](https://github.com/Wang106/SoftwareLifeCycle/actions/runs/42758822529) 与
[42758838506](https://github.com/Wang106/SoftwareLifeCycle/actions/runs/42758838506)
均 attempt 1 成功：0029 单头、版本列 varchar64、选定 7 表/3 函数/6 触发器、
4 张选定业务表计数均 0；各次原准备 2 容器及联合 2 容器确认清理。
这些运行的 application_started、readonly_role_verified、complete_schema_verified 均为 false。
旧交接的“联合未运行”是当时状态，以这两次有限证据更新，不改写成 API 已运行。

main [CI42755793330](https://github.com/Wang106/SoftwareLifeCycle/actions/runs/42755793330)
成功：后端 3538、2687 子测试、308 PG 零跳过；严格浏览器 16 Next + 16 组件。
Cloudflare 生产 build `758102b6-95a7-4ef2-960c-4eb13e619f91`、version
`750e6bb3-4054-441f-ac08-6fd1f581a6f6` 成功；Render 本轮未核验。
以上为父协调任务已核对的基线证据，不能代替当前候选 CI、API 镜像运行或业务验收。

## 本包不接线、不实际执行

新增 `scripts/offline_migrated_api_probe.py` 只准备内部 Python helper。
没有 main/执行 CLI，没有下载、镜像选择/构建、daemon 发现、数据库 URL、SQL 或外部目标入口。
普通 import、直接运行文件及附带 --help 都不执行 Docker、网络、数据库或 API。
现有 `offline_api_startup_rehearsal.py` 的无数据库 ready503 合同保持原样。
原迁移协调器、全部 workflow、迁移历史、依赖、生产代码与门禁不变。

本包只有标准库 mock 与合成文件测试。没有真实 Docker、HTTP/数据库监听、依赖下载、
镜像构建、迁移执行、权限变更、文件上传或部署。当前没有可直接完整运行的集成入口。

## 最小内部接口与可信调用者前置条件

`run_probe(*, pg, netns, image_id, source_commit, command, budget)`：

- `pg` 必须是原联合协调器的精确 `OwnedContainer` 活对象，kind=pg，尚未尝试清理。
  未来协调器必须在同轮新建 PG、原迁移完成且有限观测通过后、进入 PG finally 清理前调用。
  不能把旧运行已清理的 CID、名称、回执或字典当作活对象。
- `netns` 为该协调器实际读取的网络 inode；helper 重新读取，仅 lo 且必须一致。
- `image_id`/`source_commit` 为同轮可信构建得到的精确 API 镜像 ID 与完整提交。
  调用者负责核对受审 checkout/helper 字节、镜像构建链及来源；helper 的 image inspect
  只验证平台、固定安全入口、环境、精确 ID/commit 的一致性。
- `command` 是同一个可信协调器持有的本地 daemon 有界适配器，负责固定连接、本机 daemon
  信任、输出大小上限、stderr 不披露、超时、不重试及不执行 shell。
- `budget` 必须是原同轮的 `Budget`，沿用开始时间和 55 分钟截止，不创建第二窗口。
  调用者负责 SIGTERM/中断处理，并在自身 finally 中清理其 PG/迁移容器。

这是显式调用者信任，不是不可伪造 Python 能力。对象、随机标签、custody 文件、CID、
镜像摘要和返回回执都不能独立认证来源或授权，也不抵御同进程修改、同 UID 或 daemon 管理员。
当前原协调器不会调用 helper；未来接线必须单独审查并获得真实操作所需批准。
调用函数本身不构成授权，不接受“approved=true”等自报字段替代批准。

## 固定隔离与有限探针

借用的 PG 必须仍为原固定官方 PG16.15，none 网络、仅 127.0.0.1:5432、无宿主端口/持久卷。
重新校验原 CID/custody 文件、固定初始化参数、镜像、完整容器 inspect、PID 及网络 inode，
首次读取后保持 PG 对象字段、CID、PID 和 inode 一致。不会搜索名称、接触旧库或接管 PG 清理。

唯一新 API 容器共享 `container:<本次完整 PG CID>` 网络栈，不能等于 PG CID。
复用原安全 create/inspect/一次清理实现，在任何 create 前一次固定 API 专用参数。
非 root 65532:65532、只读 rootfs、drop ALL、no-new-privileges、private IPC/cgroupns、
无日志驱动、无重启/健康检查、无额外网络/端口/设备/目录绑定；1 CPU、1 GiB 内存及同量 swap、
128 PID、8 MiB shm、只有 16 MiB /tmp tmpfs。

API 固定 loopback 8000，READ_ONLY_MODE=true，AUTH_MODE=disabled、管理员/seed/telemetry 禁用。
数据库固定 127.0.0.1:5432/slc_migration，连接 5 秒、statement 5 秒、lock 1 秒、idle 15 秒，
会话 default_transaction_read_only=on。仍用获批临时 trust 的 postgres 超级用户，
**默认只读不等于 SELECT-only 角色**；不创建角色、不 GRANT/REVOKE、不改变数据库权限。

新独立进程探针核对 PID1 精确 uvicorn 命令、65532 身份、零 capabilities、NoNewPrivs/Seccomp、
仅 lo、同网络 inode；监听集合必须恰为 IPv4 loopback 5432 与 8000，无额外 IPv4/IPv6 监听。
不能直接使用旧无 DB 探针只允许 8000 的监听合同。两端 PID 在本阶段不得变化。

固定 5 个 HTTP 请求，均通过 API 容器内独立 Python 程序访问 127.0.0.1:8000：

1. GET /health/ready 必须 200，精确 ready、版本 0.18.50 和 0029 revision。
2. GET application release catalog?limit=1 必须精确空分页，含 kind=application。
3. GET audit/events?limit=1 必须精确空分页及空 event_type_counts。
4. POST /api/v1/deployments 只发空 JSON，必须 403/read_only_mode。
5. GET /api/v1/security/me 必须 401/oidc_not_enabled，并校验 private/no-store 等身份响应头。

HTTP 禁代理、跳转、压缩、chunked、不确定长度及重复 JSON/响应头键，正文最多 4096 字节；
连接超时 2 秒，整个 docker-exec 上限 8 秒并受共享剩余预算限制。
只返回固定小型通过回执，不输出响应原文。403/401 不是正常业务写入或真实身份验证。

## 生命周期、预算与结果限制

前置 PG 活对象/inspect/netns/固定只读 SQL 观测 → API image inspect → 创建/启动唯一 API →
固定进程与 HTTP 检查 → 再检查进程 → 一次精确 API CID 清理 → 重新核对 PG 与只读 SQL。
只有 API 已确认移除后才读取终态；清理失败绝不把“可能仍在运行”的快照当稳定终态。
固定 SQL 为原有限 READ ONLY/REPEATABLE READ 观察，结束 rollback；不接受自定义 SQL。
开始/结束要求原 0029、varchar64、选定 7 表/3 函数/6 触发器，以及 releases、release_snapshots、
audit_events、deployments 四表均 0，精确类型和值完全一致。这不证明全部 schema 或所有表没变化。

进入 helper 至少保留 330 秒原预算。工作最多 120 秒，并留 150 秒；只对同一次启动最多
20 次观察进程，不重复 create/start/HTTP 命令。API 清理最多 40 秒且保留 110 秒，
后置观察最多 30 秒且保留 70 秒，供协调器清理 PG 和输出摘要。所有单调用进一步收紧，
原 deadline 不得变化。结束没有刷新窗口，也不从本轮失败恢复/续跑。

失败与 KeyboardInterrupt 保留最初异常；API 清理或终态不确定附加固定标记。
无可靠 CID 不猜测删除；无名称扫描、prune、自动重试或镜像删除。
API 使用 rm --force 确认移除，不称为应用优雅关闭。CLI 终止不能证明 daemon 任务停止；
硬终止、CID 丢失或 runner 丢失可能留下本次资源，PG 仍由未来协调器负责。

成功只表示有限的已迁移合成库 API 读路径/拒写路径和清理，回执始终标记
readonly_role_verified=false、complete_schema_verified=false、provenance_authenticated=false。
目前没有真实执行此 helper；mock 通过不是这些运行结论。

## 本地验证

首 13 项缺能力合同全部先失败，再实现；新增 CID 漂移反例先失败，再按具体通知等待后固定首次 CID。
独立初审发现首次清理或后置观察的控制异常会被转为普通 Blocked。新增 4 项回归先 2 错误、
2 优先级对照通过，具体通知等待后只修两处首次非 Exception 控制异常传播；普通错误仍归一化，
先前工作异常与固定备注优先级不变。最终 27 项集中、702 全离线、52 自动化、126 守卫、
内存编译、进度账本及 diff 检查通过。
包含真实探针源码的内存执行、固定 HTTP 各正反例、PG/API PID 与身份稳定、缺 CID、
启动中断、失败清理、清理失败不读取终态，以及前后四表计数变化反例。
新测试 fixture 的完整目录字段、PGDATA、inspect 数组和分操作超时均按具体通知等待后纠正；
没有放宽生产属性、现有门禁或超时。独立终审通过，无剩余阻断：另 27 项新合同、28 项旧 ready503、
35 项联合合同通过；额外 8 项 KeyboardInterrupt/SystemExit × 清理/后置 × 已有工作错误，
另 2 项双阶段控制异常优先级反例全部通过，最初异常与两个固定备注保留，API 只移除一次、
PG 不触。14 项不安全 inspect 及预算/默认无执行独立反例通过。候选 CI 尚未运行。

## 后续范围

本包已完成独立审查与本地 mock 回归，下一步是获准上传后的常规候选 CI。之后另行设计并审查同轮 API 构建与迁移
协调器接线、完整生命周期预算和清理，再申请真实运行批准。不得把本包测试直接接成真实工作流。
业务仍为 36/44=82%、增量 0；模块 100/100演示/100演示/100/89/60/17；
计划 100/100/20/33/40/40/0；浏览器阶段 1/4、有限计划 8/8 不变。
