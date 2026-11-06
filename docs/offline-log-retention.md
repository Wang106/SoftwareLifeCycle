# 离线容器日志有限留存配置

本包仅修改 `scripts/offline_readonly_preflight.py` 的 Compose JSON 生成结果，
不执行 Compose、不启动 Docker、不修改运行中的服务或 daemon，也不读取、上传、
删除真实日志。仍是预检及配置生成，不是离线安装、部署或日志验收完成。

## 固定策略与输入边界

`api`、`web` 各自生成独立的 `logging` 对象：

```json
{
  "driver": "local",
  "options": {
    "max-size": "10m",
    "max-file": "3",
    "compress": "true"
  }
}
```

驱动和全部选项值均为字符串，两个服务及不同生成调用之间不共享可变日志对象。
manifest、operator、images 及每个 image 条目仍使用精确字段白名单，不增加日志
覆盖参数、环境配置、卷或命令。无全局 Docker 配置变更。

既有 root filesystem 只读、非 root 用户、cap_drop、no-new-privileges、tmpfs、
禁用 healthcheck、pull_policy=never、固定入口/回环监听、数据库只读约束及所有
身份/写入门禁保持不变。`NEXT_TELEMETRY_DISABLED=1` 继续生效，不新增遥测或外发。

依据 Docker [local logging driver 官方文档](https://docs.docker.com/engine/logging/drivers/local/)
的 `max-size`、`max-file`、`compress` 选项；本包只读核实了官方
[源文档](https://raw.githubusercontent.com/docker/docs/main/content/manuals/engine/logging/drivers/local.md)。

## 应用后的后果与安全边界

- 只有操作者以后在授权环境实际应用配置，Docker 才会按策略保存容器 stdout/stderr。
  达到大小阈值后轮转，超过保留文件数量会删除最旧日志。**旧日志会被自动淘汰**，
  不保证无限或固定时长留存，不是备份、审计归档或合规保留方案。
- `10m × 3` 是每个容器的日志轮转配置，不是整个磁盘的硬上限，也不是两个服务合计
  磁盘占用保证。元数据、压缩/解压、轮转过程、并发容器及其他文件均会影响实际用量。
  容器删除或重建可能丢失旧容器日志，不保证跨容器生命周期持久留存。
- 容器 rootfs 只读不等于 Docker daemon 日志不可写；日志由 daemon 在其存储位置
  管理，不因本配置变成应用内只读文件。不新增宿主挂载或应用写日志目录。
- 只覆盖 stdout/stderr，不覆盖应用文件日志、数据库文件/日志、宿主系统日志或软件
  文件与备份。已有目录/磁盘诊断不能替代轮转和恢复验收。
- 现有 uvicorn access/error 输出可能包含敏感 URL、参数或异常信息。`local` 不会
  自动脱敏或加密。应用前操作者必须决定日志收集授权、敏感信息处理、查看权限和
  留存/淘汰策略；本包不引入真实数据，也不代表这些治理决定已经完成。
- 外部查看仅通过受支持的 `docker logs` 接口并遵守环境授权。Docker 内部日志文件
  应仅由 Docker daemon 访问，不直接读取、编辑、截断或删除这些文件，不接入文件
  tail/采集工具。这里描述接口边界，不授权读取任何真实日志。

## 验证及后续验收

新增回归先在旧实现失败，再最小实现：整份 Compose 输出精确比较（含 CLI JSON），
保护既有安全设置及精确输出键；校验字符串类型、两个服务双向修改隔离及跨调用
隔离；拒绝 manifest/operator/images/api/web 的日志覆盖字段。既有测试断言不删减。
测试使用本地合成归档和合成数据库 URL，不连接数据库或公司服务器。

本地没有 Docker。配置/标准库单元测试通过不等于真实日志持久化、轮转、容量、
Compose/Engine 兼容性或断网运行已验收。后续需另行在批准的隔离环境使用合成日志：
确认实际有效 driver/options、stdout/stderr 可见性、触发轮转及最旧日志淘汰、压缩后
实际磁盘占用、服务重启与容器重建的留存边界，以及断网启动。演练必须遵守已授权
范围，不连接公司服务器、不使用真实敏感日志、不以测试结果替代备份恢复验收。

最终本地验证：59项离线测试＋114子测通过；完整后端2084项＋114子测通过，824项因缺TEST_POSTGRES_URL跳过（非完整PG验收）；前端2116项、类型检查、Python编译、52自动化/126守卫及进度检查通过。独立审查确认移除新增logging后整份Compose与基线完全一致，无阻断。真实PG与固定签名8＋16浏览器仍待候选完整CI；真实Docker日志轮转和磁盘验收未执行。
