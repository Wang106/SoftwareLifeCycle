# 离线迁移镜像输入准备

## 状态与边界

本包只新增独立迁移镜像配方、本地受控构建上下文准备/复核工具及合成测试。
**没有构建镜像、启动容器、连接数据库或执行SQL。** 不修改现有API/web配方、
镜像工作流、原wheelhouse校验器、生产源码或29份迁移；不接入自动执行。
输入准备成功不代表镜像可运行、迁移成功、数据库安全、真实断网或公司部署验收。

基线为main `fde3270d1248514c827b2fd377696348e2d56a84`，PR201。
[main CI42502128909](https://github.com/Wang106/SoftwareLifeCycle/actions/runs/42502128909)
成功：3324后端＋1435子测试，296项PostgreSQL零跳过（791.76秒）、2116前端、
8＋16严格浏览器及汇总门禁。Cloudflare同提交build
`a34cb9ba-c873-45c3-9362-b531ee2915f2` / version
`e6ad0ca3-dbe6-44f2-bc45-4ac437760302`成功；Render
`dep-dboahqi9lscs73cq3ii0` update_failed，不称后端恢复。
这些是已有基线，不是本包候选CI。

另行获准的[手动运行42536231169](https://github.com/Wang106/SoftwareLifeCycle/actions/runs/42536231169)
于2026-11-08 23:39:40至23:42:31 UTC成功，RUN_API_STARTUP与EXPORT_IMAGE_BUNDLE均为true。
112＋28合同回归及主机92,147,126,272字节前置通过。协调器成功门槛严格要求同次构建
精确ID/commit、10/10真实API检查、拥有权容器清理、database_ready=false及独立临时镜像包复核。
具体镜像ID/归档SHA只写步骤摘要，本次未读取，不补造数值，也不把日志源码打印当回执。
该运行没有验证生产数据库、物理断网或公司部署；无需为本准备包重复运行。

## 为什么需要独立工具

离线API镜像只复制site-packages及app，现有源码快照白名单不含alembic.ini/迁移目录。
生产entrypoint会自动迁移并可能seed，不能复用作只读API或准备工具入口。
新镜像复用已核对的Python linux/amd64平台摘要、现有完整30项wheel锁和安装校验，
额外复制原始配置、env.py及全部0001至0030迁移，不新增依赖。

配方默认ENTRYPOINT为/bin/false、CMD为空、用户65532:65532，不公开端口/卷。
构建安装RUN明确network=none；现有wheel验证、no-index、require-hashes、only-binary和pip check保留。
准备脚本不会调用Docker，也没有pull/build/run/load/export/upload操作。
未来实际构建还须核对BuildKit能力、已有基础镜像ID、磁盘/时间预算及无网络构建设置。

原alembic.ini保留其历史开发URL字节，仅为源码一致性。它不是操作员配置、真实凭据或经过批准的目标。
backend/alembic/env.py会从应用settings覆盖URL；online分支一连接就先CREATE/ALTER版本表，
即使alembic current也不是只读探针。READ_ONLY_MODE等应用开关不约束迁移DDL。

本包不提供数据库执行命令。site-packages复制不保证存在alembic console script，
未来入口须显式设计固定Python模块加载、工作目录、环境和目标，不能随意覆盖镜像入口直接操作。
独立verify只做字节、清单与AST检查，不import包内模型/迁移，不执行包内Python或Alembic。

## 本地接口

需要Linux、CPython3.12、支持no-follow的POSIX文件系统、/usr/bin/git（支持--no-lazy-fetch）
及本机已有pip。工具不会安装这些条件，不会寻找替代下载或远程Git目标。

```sh
python scripts/offline_migration_context.py prepare \
  --repository /approved/clean/checkout \
  --expected-commit <independently-verified-40-hex-commit> \
  --wheelhouse /approved/existing/wheelhouse \
  --destination /approved/parent/new-context
```

仅允许已存在的本地wheelhouse及不存在的新目标目录。缺失或不符合固定30项清单时拒绝，
不下载、不调用联网依赖解析、不覆盖旧目录。源码包括准备工具自身，来自干净checkout的精确Git对象字节，
并与工作树no-follow读到的字节核对。源码中未知的迁移文件、缺链、多头、重复/动态revision、
非空branch_labels/depends_on、配置head不一致均拒绝。AST读取元数据不会执行迁移。

准备阶段先验证现有wheel元数据/大小/SHA，再安全复制并调用原wheelhouse验证器的独立子进程，
验证复制后的完整依赖闭包。执行的是**本机受信checkout中的校验器**，不是上下文副本；
两份本机工具字节必须与所选commit一致。新工具在此独立子进程内适配原校验器的目录读取依赖，保留原校验器源码不变；每个目录描述符仅关闭一次，关闭不确定时不重试。原校验器使用pip的离线hash-locked dry-run，无安装。
原pip内部仍有全量输出缓存，故外层另外限制验证子进程及后代：1GiB地址空间、120秒CPU、
128MiB单文件，整次150秒、stdout/stderr合计64KiB。只收紧子进程限制，不修改主机配置。
这些限制不是恶意代码沙箱，也不替代物理网络隔离或授权。

Git每次命令20秒、stdout/stderr合计至多8MiB，blob至多4MiB。
禁继承系统/用户Git配置、交互凭据、lazy-fetch、replace、fsmonitor和hooks；
检查包含worktree/include配置的filter驱动并拒绝，避免status触发可执行过滤器。
不获取Git远端；未知/缺失对象或不支持能力均拒绝，不回退。

成功返回MIGRATION_INPUTS_PREPARED_NOT_EXECUTED、commit、manifest_sha256、迁移数量29，
database_connected=false、image_built=false。没有数据库ready或迁移通过字段。

```sh
python scripts/offline_migration_context.py verify \
  --context /approved/parent/new-context \
  --expected-commit <independently-verified-40-hex-commit> \
  --expected-manifest-sha256 <independently-retained-64-hex-digest>
```

独立复核不运行子进程，核对精确文件/目录集合、大小、SHA、29单链、配置head、锁与清单关系。
保留context根及全部祖先目录描述符，退出前核对路径与目录身份；文件/子目录的dev、inode、mode、
链接数、大小、mtime/ctime前后必须一致，同名替换亦拒绝。AST声明仅允许指定作用域的一次简单
字面量声明，其他受保护字段写入/删除、global/导入/同名定义、异常/模式匹配绑定和星号导入拒绝。
只检查字面声明及可识别语法绑定；globals/exec等反射和任意Python执行后的head不变性，仍依赖受信commit，
本工具不是通用Python安全分析器，不执行迁移来验证这些语义。
期望commit及清单摘要由受信调用方独立提供，不能从待验包自读充当期望。
复核不重新执行pip；清单里的closure_report_sha256只记录先前校验回执的一致性。
成功只返回MIGRATION_INPUTS_VERIFIED_NOT_EXECUTED。SHA、Git标签及清单都不是发布者签名，
无法自行证明来源真实；受信checkout、调用方期望值和本机执行环境是前提。

## 文件与失败边界

- 单源码文件≤4MiB；源码总量≤16MiB、≤512文件。
- 清单≤1MiB；30个wheel单个≤128MiB、总量≤512MiB。
- 全context≤544文件、总字节≤529MiB（16＋512＋1）；目录数量≤544、路径深度≤16。
- 拒绝路径穿越、隐藏路径、敏感命名、符号链接、硬链接、FIFO/设备等特殊文件及额外空目录。
- 写入用排他创建和目录文件描述符，不覆盖既有文件；写后flush/fsync并检查关闭，再独立复核。
- 错误输出固定MIGRATION_INPUTS_BLOCKED，不回显输入、连接配置或原始异常。
- 创建、写入、fsync、关闭、中断或最终复核失败均不得返回成功。保留整个可能部分写入的新目录，
  不自动删除、重试或扩大清理；后续处理须先核对实际结果与拥有权。
- 未实现对有权并发修改同一用户文件的攻击者的完全防护；复核是当时的字节一致性观察，
  不证明之后构建读取的字节不变。未来构建协调器需独立处理此边界。

## 真实空库迁移的后续独立包

1. 另行批准本次新建、可销毁、只含合成数据的PostgreSQL16目标、容器隔离/连接和本次拥有权清理。
   拒绝公司库、既有数据库、非空应用schema及任意外部连接串。不复用迁移权限启动只读API。
2. 单独核验迁移镜像精确ID/commit及输入摘要，设计有限时间、无并发、固定目标和固定head的执行入口。
   必须真实运行现有0001→0030链，不stamp、不手填版本号、不以create_all替代。
3. 除唯一head和VARCHAR(64)版本列外，核对实际目录中的业务表、列、FK/check、唯一/部分索引、
   函数及触发器；至少覆盖0001核心表和0029四张历史表。仅版本匹配不证明schema完整。
4. 不自动downgrade、seed、重试、不为追求CHECKLIST_MATCHED改权限或放宽原检查。
   真实迁移含函数，PUBLIC EXECUTE/TEMP及系统默认ACL仍可能使现有只读检查保守拒绝。
   迁移角色、只读角色、DDL、角色/GRANT/REVOKE以及API连接验收须另行设计、明确批准和实测。
5. 实际构建/镜像获取、网络、容器/数据库执行、上传、目标安装、费用逐项按实际范围另批。
   公司部署、恢复/RPO/RTO、物理断网及生产安全审计仍未验收。

## SQL工件的另一个未验证风险

当前env.py仅online分支将alembic_version.version_num扩为VARCHAR(64)。offline生成SQL没有该处理，
0008 revision已超过Alembic默认32字符。现有CI只检查生成SQL非空，真实迁移往返走online分支，
没有执行生成SQL。本包不修改迁移，不输出可执行SQL、不宣称已复现或修复该风险。
未来若选择SQL交付路线，必须独立修复并在获准空库实际执行生成SQL后才能验收。

## 本包验证记录

先添加16项集中回归，能力缺失时16项失败，再实现并通过；独立审查复现目录替换、fd关闭重试及AST重绑问题，
新增回归先得到8个失败，经具体修复通知及等待后修正。第二轮针对异常/模式绑定及星号导入的6项失败亦在具体通知并等待后修正。最终33集中、508全离线零跳过、52自动化、
126守卫、TypeScript、Worker配置、Python编译及进度检查通过。独立复审待完成。
完整前端测试仅前15项记录通过，工具以依赖获取网络风险为由拒绝，未取得完成结果；
只读复核未见原测试进程，日志无下载URL/安装记录，不能声称没有任何网络发生或完整前端通过。未重试。
合成wheel由测试mock元数据/闭包验证器，不是实际wheel下载、安装或真实镜像构建证据。
最终本地统计和独立审查记录见最新检查点。完整后端、真实PG及浏览器仍须候选精确CI；
本包业务增量0，模块/计划/浏览器阶段百分比保持原值。
