# P7A：现有运维能力对账与外部验收清单

核对基线：`99deff49f262070bb2d5c44609e2e01d551ccb92`（2026-10-28）。
这是源码与既有契约的对账，不是本轮执行了探活、备份、恢复或目标环境验收的记录。

## 已选范围与完成边界

本轮选择 **P7A 文档收口**：不新增通知适配器、离线评估器、监控平台或脚本，不安装公司服务器，不执行外发、生产操作或真实配置变更。P7A 的交付物是下面可执行前审阅的能力清单、责任/决定清单与验收停止条件；通知渠道未选不阻止该有限文档包完成，但仍阻止真实监控/通知验收。

本文件不将代码存在、示例命令、CI 合成成功或历史部署成功计为当前生产健康、有效备份、通知送达或恢复达标。总体 `36/44=82%` 不因此提高；R15/Phase 7 的未验收项仍保留。详见 [有限非部署计划](nondeployment-completion-plan.md) 与 [集成收口](nondeployment-integration-closeout.md)。

## 一、能力对账：已有代码，不重复造工具

| 已有能力与源码 | 可验证的能力 | 不能据此声称 | 既有测试/契约 |
| --- | --- | --- | --- |
| `backend/app/main.py`：`/health`、`/health/live`、`/health/ready` | live 不依赖数据库；ready 查询 Alembic revision，数据库不可用或 revision 不符返回 503 | live200 不等于 DB/业务健康；ready200 只证明该时刻连接与声明 revision 检查，不证明数据完整、权限正确、完整 schema 无漂移、端到端或当前仍健康 | `backend/tests/test_health.py`；测试使用替代引擎，不是目标探活证据 |
| `backend/app/ops/request_telemetry.py`，由 `main.py` 挂载 | 默认关闭的结构化请求观察，固定路由模板、状态/结果与整次 ASGI 调用时长，写自身 stdout logger | 不是业务审计追踪、客户端送达/延迟保证、完整采集保证；不会轮转、存储、外发；其他日志源不自动获得其脱敏保证 | `backend/tests/test_request_telemetry.py`；[遥测契约](operational-telemetry-incident-evaluation.md) |
| `backend/app/ops/telemetry_window.py` | 对明确本地输入窗口做有界指标/参考告警评估，坏输入拒绝，无通知外发 | `clear` 仅指输入；缺样本不是健康；`triggered` 不是送达；进程退出 0 不是健康通过；参考阈值不是已批准 SLO | `backend/tests/test_telemetry_window.py`；输出 `coverage=input_only_not_proof_of_complete_collection`、`notifications_sent=false` |
| `backend/app/ops/postgresql_backup_restore.py` | 在隔离数字 loopback PostgreSQL 中创建/迁移合成源和目标，native dump/restore、校验清单/规范数据/关联/审计不可变性；按证明清理自身数据库 | 会创建、写入和删除数据库，不是只读诊断或生产备份程序；不能证明公司备份周期、留存、RPO/RTO 或真实灾难恢复 | `backend/tests/test_postgresql_backup_restore_rehearsal.py`；[合成恢复契约](isolated-synthetic-postgresql-backup-restore-rehearsal.md) |
| `backend/app/ops/retained_synthetic_restore.py` | 独立进程恢复自有可信合成备份，无需原进程/源库；校验旧输入不变、新目标/证据归属，成功目标保留供显式检查 | checksum 不是来源认证；dump 含可执行 SQL，不是任意外部文件沙箱；不支持任意跨版本迁移、不恢复真实公司库；保留目标不等于完成清理 | `backend/tests/test_retained_synthetic_restore.py`；同上契约“Retained synthetic package recovery” |
| `scripts/offline_readonly_preflight.py`、`deploy/offline-readonly/*.example.json` | 检查限定 docker-save 包的字节/层哈希、平台/修订/配置输入，输出只读 Compose JSON；不运行 Docker/联网/访问数据库 | `CONFIGURATION_ONLY` 不是 runnable image、可信来源、真实 DB 只读权限、无外网、离线部署或浏览器验收；合成 tar 测试不是可运行镜像 | `backend/tests/test_offline_readonly_preflight.py`；[离线预检契约](offline-readonly-config-preflight.md) |

不得将既有开发 `docker-compose.yml` 直接当成公司只读部署方案。候选 Hyper-V→Linux→Docker 路线不等于已经安装或获准执行。网络 host 模式也不阻断外发；任何实际网络、权限或镜像运行另行审批。

## 二、命令索引（仅示例，本轮未执行）

以下命令用于明确入口，不构成执行、安装、授权、凭据提供或数据披露许可。先读对应契约和当前参数，依赖使用仓库既有版本；不要把真实日志、连接串、operator 文件、dump 或公司资料贴进聊天、提交或公开 CI。不得为了跑示例修改权限、安装缺失系统组件或绕过沙箱。

**本地合成遥测评估**，工作目录 `backend/`；输入必须是自有合成且仅包含本工具 logger 的 JSONL：

```sh
python -m app.ops.telemetry_window own-synthetic-requests.jsonl \
  --start-ms 1792980000000 --end-ms 1792980300000
```

窗口半开且最长一小时；最多 100000 行，每行最多 2048 字节。有效评估即使触发告警也退出 0；无效输入退出 2。不得据此接入自动恢复或发送通知。

**本地离线配置预检**，仓库根目录；只检查经批准、私有保存的 operator-owned bundle：

```sh
python scripts/offline_readonly_preflight.py /path/to/operator-owned-bundle
```

有效输入 stdout 为 Compose JSON、stderr 为 `CONFIGURATION_ONLY`；无效输入退出 2、无 Compose 输出。输出包含本地路径，仍须留在获准范围。示例 manifest/operator 有意不满足实际验证，不应伪造校验值或把 readiness 声明改成真来获取“通过”。

**隔离合成数据库演练入口**，工作目录 `backend/`；仅在独立批准的 disposable loopback PostgreSQL、native client、最小必要控制权限及安全配置 `TEST_POSTGRES_URL` 已具备时考虑执行：

```sh
python -m app.ops.postgresql_backup_restore --evidence-dir /private/new-synthetic-evidence
```

该入口有数据库副作用，不属于只读操作；缺少条件即停止。不要在命令行写入连接串/密码，不把生产 URL 改写为 loopback 后冒充隔离环境。保留合成包恢复的完整 `--archive`/`--manifest`/`--baseline`/`--trusted-own-synthetic` 命令及精确新 run ID 的清理条件见[原契约](isolated-synthetic-postgresql-backup-restore-rehearsal.md#retained-synthetic-package-recovery-2026-10-25)。清理是删除操作，不能自动针对任意名称、旧证明或别的环境执行；失败保留检查点，先审阅后另行授权处理。

**源码级回归入口**，只指向既有测试；本轮不借此启动目标数据库或服务：

```sh
# 在 backend/，项目测试依赖已安装；native PostgreSQL 用例缺环境时的 skip 不是通过
python -m pytest tests/test_health.py tests/test_request_telemetry.py tests/test_telemetry_window.py -q
python -m pytest tests/test_postgresql_backup_restore_rehearsal.py tests/test_retained_synthetic_restore.py -q
# 在仓库根目录，无 Docker/数据库/网络的标准库合成预检回归
python backend/tests/test_offline_readonly_preflight.py -v
```

完整精确 head CI/产物仍按原门禁验证，不为文档包降低或跳过。不得把本地被跳过的 native 测试替换成生产恢复证据。

## 三、外部验收：决定、责任、证据与停止条件

下表责任是待指定的角色，不代表已任命人员或授予权限。用户可自行承担服务器操作责任，无须虚构 IT 审批；实际高权限执行仍须明确获准。各项默认 **未验收**，不能由本文件自动勾选。

| 验收项 | 用户/责任人须先决定 | 可接受的目标证据 | 必须停止/保留的边界 |
| --- | --- | --- | --- |
| 目标与运营责任 | 选择独立测试/公司目标、数据分级、维护窗口、操作人/接收人、升级路径 | 目标身份、获准操作范围、精确部署修订与 UTC 记录 | 无目标/负责人/许可不执行；公司部署继续推迟不妨碍文档收口 |
| 健康与版本 | 探测来源/频率、维护期解释、可用性准则 | 同一目标/时间窗的 live/ready、精确 commit/provider deployment、独立功能 smoke 及失败样本 | revision 不符只报告；不自行迁移、seed、重启；历史200不替代当前检查 |
| 日志采集与隐私 | 是否启用遥测、全来源日志脱敏、采集组件、授权读者、加密、保留/删除期限、容量 | 本工具及代理/Uvicorn/platform 日志分别审阅；丢日志/进程崩溃/背压/时钟偏移实验及性能开销 | 默认关闭保持；公司日志不外传；缺记录标记 insufficient/unknown，不能标绿 |
| 指标/SLO | 错误率、整次调用时长与客户端体验各自口径、采样/探活占比、窗口与阈值 | 批准的定义，足量正常/错误/慢请求/ready失败/缺数据窗口及预期评估 | 参考20样本、5%、1000ms等阈值不自动成为公司SLO；触发不自动修复 |
| 通知与响应 | 将来是否需要适配器、渠道、接收/值班责任人、去重/重试/升级/确认策略 | 选定目标中触发→生成→送达→接收者确认的独立时间戳/关联证据；失败/重复/超时演练 | P7A 不实现或配置外发；未知送达不冒充失败后安全重发；送达不等于确认或正式发布 |
| 备份与保留 | 公司数据库备份工具/访问范围、可信来源、存储位置/加密/保留、RPO/RTO、恢复目标 | 新鲜备份产物/哈希/版本/时间，隔离恢复完整性、关系/审计检查，测得时间与数据损失量对照批准目标 | 合成 fixture 不能替代公司数据恢复；无许可不接触真实库；失败不覆盖旧备份、不无限重试 |
| 离线运行 | 授权 Linux/Docker 构建测试环境、可信镜像 provenance、离线依赖、网络/数据库只读权限 | 真正镜像构建与 Compose 兼容、无pull/seed/migration、实际监听/外发策略、拒绝DB写入、健康及双语页面 | 预检输出不是部署；缺客户端/权限/镜像即阻塞，不安装或改服务器配置来绕过 |
| 故障恢复与关闭 | 获准 containment/回滚动作、schema兼容、停止标准、人工验收者 | 授权动作日志、恢复后健康+功能+足量观察窗口、未决影响与人工接受 | 不自动重启/回滚/改身份或门禁；告警确认、审批通过不等于正式发布 |

## 四、验收记录最小模板

每次获准目标演练分别记录：范围与数据分级、操作者/审批者、目标与精确修订、UTC 起止、工具版本、预期结果、实际结果、产物及哈希、结果状态（成功/失败/跳过/阻塞/未验收）、残留资源及安全检查点、下一责任人。秘密、真实身份详情及业务内容留在批准的私有记录；对外仅披露经批准的最少摘要。

不得把不同目标、不同 commit 或旧时间窗拼成一次成功，也不得用“配置存在”“CI通过”“provider live”替代通知、保留或恢复测试。任何真实验收失败只记录已知原因与待核实项；未授权操作不得因等待超时自动开始。

## 五、P7A 的停止条件

完成现有入口/契约/测试路径核对、责任与依赖清单、独立审查以及本轮既有发布验证后，P7A 文档工作停止。不会自动追加通知适配器或递归离线小工具。后续只有用户选择具体目标/渠道并批准对应执行范围后，才进入相应真实验收或另定功能包。

P7A 可与其余有限工程包一道完成既定非部署计划；这只表示本次选定有限范围交付完成，不表示所有需求完成、生产运维验收完成或整个系统100%。真实身份/浏览器/多用户、公司数据与部署，以及单独延期的 VIN、实际 AI 服务、二进制文件存储仍按各自契约保留边界。
