# 离线目录与磁盘余量只读诊断

本工具补充目录/磁盘余量观察，不替代已有 `offline_readonly_preflight.py` 的输入校验或 `offline_npm_inventory.py` 的依赖清单。仅使用 Python 标准库，不需要安装依赖、启动应用、数据库或容器。无网络请求，不接触公司服务器。

## 操作者输入

在已有本地目录上手动执行，例如：

```sh
python scripts/offline_directory_diagnostics.py \
  --logs /srv/example/logs \
  --backups /srv/example/backups \
  --software /srv/example/software \
  --minimum-free-bytes 1073741824
```

这些路径仅为示例，不会自动创建。三个角色必须全部显式提供，可以指向同一目录或同一文件系统。最低可用字节阈值由操作者确定，统一用于三个角色，不能推断业务所需容量或替操作者批准阈值。零阈值允许，但仅表示不要求正余量。

仅支持具备 `dir_fd`、`O_DIRECTORY`、`O_NOFOLLOW`、`fstat`、`fstatvfs` 能力的 POSIX 环境（Linux）；缺失能力时拒绝观察，不降级为按路径检查。Windows、实际内部服务器平台及容器映射仍未验收。权限不足时也不会尝试提升权限。

输入限于四组完整选项，不接受重复、缩写、未知选项、额外位置参数或配置文件。整数必须为规范十进制 `0` 或非零数字开头，范围 `0..9223372036854775807`；不接受符号、前导零、小数或异常大整数。路径必须为绝对路径，最多4096字符、256分量；拒绝空分量、`.`、`..`、尾斜杠（根目录 `/` 除外）、反斜杠、控制字符。不会展开 `~` 或环境变量。输入无效时在任何目录打开前拒绝。

## 输出及退出码

除单独 `--help` 外，标准输出始终为单个结构化 JSON 对象，标准错误不输出路径或异常。格式为 `slc-offline-directory-diagnostics-v1`，`directories` 固定依次列出 `logs`、`backups`、`software`。每条仅有固定角色、状态、`available_bytes` 和 `minimum_free_bytes`。未知值为 `null`，不伪装为零。CLI输入错误时三角色均为 `INVALID_INPUT`，阈值为 `null`。

- 退出0：顶层 `OBSERVATION_ONLY`，三个角色均为 `DIRECTORY_OBSERVED`，当次可用字节达到阈值。
- 退出1：顶层 `BLOCKED`，至少一角色未达条件，其他角色仍保留独立观察结果。
- 退出2：顶层 `BLOCKED`，输入无效。不会回显原始输入。
- `--help` 单独执行返回固定说明文本和退出0，不做任何目录观察。

角色状态：`DIRECTORY_OBSERVED`（成功观察且达到阈值）、`BELOW_MINIMUM`（不足）、`PATH_UNAVAILABLE`（缺失、访问失败、符号链接、非目录或目录描述符检查失败）、`CAPACITY_UNKNOWN`（容量调用失败或数据缺失/异常）、`UNSUPPORTED`（缺少所需能力）、`INVALID_INPUT`（输入无效）。状态不推断失败路径、用户名、文件名或精确权限原因。

可用容量只取 `f_bavail × f_frsize`，不使用含root保留块的 `f_bfree`。缺失、负数、零fragment、非整数或超过有界整数范围的容量为未知。真正零可用容量仍是有效观察，在正阈值下为不足。没有跨目录总计；同一文件系统的多个角色共享容量，不能相加或认为备份与软件处于独立故障域。

## 只读及竞态边界

从根目录描述符开始逐级 `open`，每级必须携带 `O_DIRECTORY | O_NOFOLLOW`，并对打开的描述符 `fstat` 校验目录。叶目录通过同一描述符执行 `fstatvfs`；所有描述符在成功及失败路径关闭。不先检查字符串路径然后按同一路径重开，因此已打开父目录即使被重命名/替换也不会把后续观察转移到替代路径。任何打开时遇到的符号链接、普通文件、FIFO等均拒绝。

此保证仅针对已打开的目录对象。并发者可在打开前替换真实目录，挂载变化或之后的路径替换也不在身份保证内；输出不能证明路径在工具结束后仍指向该对象。不输出路径、inode、设备标识、异常文本或用户/文件名。

不列目录、不读取目标文件内容、不计算目录大小，不写目标、不创建目录、不chmod、不删除/轮转日志、不备份或恢复文件。操作系统的访问审计等行为不等于本工具主动写入目标。本工具成功打开目录仅证明当次允许该操作，不证明可以写入、创建日志/备份、应用身份可访问、容器映射正确、磁盘健康、备份有效/可恢复或生产验收完成。容量是逐角色、不同时刻的快照，不预留空间，也不保证后续操作成功。

## 本地回归

```sh
python -m unittest discover -s backend/tests -p 'test_offline_directory_diagnostics.py'
python -m unittest discover -s backend/tests -p 'test_offline*.py'
python -m py_compile scripts/offline_directory_diagnostics.py backend/tests/test_offline_directory_diagnostics.py
```

真实临时目录与合成容量/故障覆盖：低余量、异常容量、符号链接父/叶、普通文件/FIFO、缺失目录、能力不足、逐级与叶目录重命名替换、描述符关闭、无内容读取/目录枚举/目标写入、CLI脱敏和拒绝输入。模拟容量不代表真实内部磁盘或备份验收。完整原有CI及严格浏览器门禁不变，本地定向通过不能替代新提交的完整CI。

最终本地验证：新增26项、全部offline56项、完整后端2081项＋97子测试通过；824项因缺少TEST_POSTGRES_URL跳过，不是完整PG验收。前端2116项、类型检查、Python编译、52自动化/126守卫和进度检查通过。独立最终审查无阻断。实际PG和固定签名8＋16浏览器仍由候选完整CI验证，尚未声称内部服务器验收或离线部署完成。
