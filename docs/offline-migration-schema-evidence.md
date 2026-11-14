# 当前0030有限结构证据检查

## 2026-11-14 compatibility update

Current code pins `0030_private_upload_sessions`, exactly 30 migrations, and
`deploy/offline/migration-schema-0030.json` with checklist
`0030-core-history-upload-subset-v1`. Its 147 facts retain the historical 119
non-version facts, advance the version fact, and add 27 private-upload table,
column, constraint and index facts. Repository hashes bind the unchanged older
sources and the new 0030 migration. The fixed 160-fact bound is unchanged.

The old 0029 manifest remains byte-for-byte preserved; it is historical evidence,
not accepted as a current-schema document. Old input with its old checklist is
UNKNOWN; relabeling it current still mismatches. Existing live PG catalog guard
collection remains its original selected 7 tables/3 functions/6 triggers. It does
not collect the new upload table. Dedicated synthetic CI migration tests check
upload constraints separately. No current database or deployment is established.

The following 0029 description and example are historical. For current offline
comparison, use the current checklist and all 147 facts from the new manifest;
never relabel an old observation as new evidence. Real migrations or rehearsals
still require their existing authorization and isolation boundaries.

# 固定0029有限结构证据检查

## 状态和严格边界

基线为 PR203 合并后的 main `44e307a71a22f93f8c2ae611cf10678b0420499f`。
本包新增固定清单、标准库本地 JSON 检查器、合成回归及本说明；不修改迁移、应用、
依赖、Dockerfile、原只读数据库检查器、工作流或门禁。
没有连接数据库、执行 SQL/DDL、import 应用/迁移、运行容器或启动服务。
正常运行只读取指定本地文件及仓库中的固定清单，不获取输入、安装依赖或上传任何内容。

证据是**不可信自报的有限结构投影**，可以伪造、过期或由不同数据库拼接。
复制清单的 facts 就能构造匹配的文档，测试正是这样创建合成样本。
本工具没有实际采集器，不核实提交、身份、执行退出状态、新鲜度或事实来源。
匹配不证明真实迁移运行、完整 schema、函数行为、权限隔离、应用就绪、物理断网或公司部署。
不得把它接成自动准许启动、放行权限或部署的门禁。

## 固定120事实的范围

`deploy/offline/migration-schema-0029.json` 是维护者审核的固定清单，版本标识为
`0029-core-history-subset-v1`，不是任意输入规则。脚本内固定该文件原始字节 SHA256，
摘要或文件不符即 UNKNOWN；调用方不能提供替代清单或期望 head。
清单列出实际来源文件和摘要，测试核对这些源码字节；摘要只绑定一致性，不是来源认证。
清单维护或迁移变化需单独审核和测试，不自动重新生成或接受新版本。

- `version`：固定 public.alembic_version、version_num VARCHAR(64) NOT NULL、
  单行、head `0029_changeover_batch_history`。这是自报值，不读取版本表。
- 6个表描述：releases、release_snapshots 和0029四张历史表；固定 public 普通持久heap表，
  row security / force row security 均为 false。
- 0001只选 releases 的 id/software_id/release_type/version/status，及 release_snapshots
  的 id/release_id/snapshot_number/content_hash，和这些列相关的选定主键、外键、
  release_type check及 snapshot(release_id,snapshot_number)唯一约束。
  **不包含0001原 releases 三列唯一约束**：它已由0024删除并改为客户范围表达式唯一索引。
  本清单不检查该新索引/customer_scope_id或其他后续核心表结构，不以0001原状冒充0029全貌。
- 0029 changeover_baselines、changeover_corrections、batch_baselines、batch_corrections
  的全部声明列及其类型/nullable，全部声明PK/FK/check/unique约束。
  predecessor均检查(target_id, predecessor_id)至同表(target_id, id)复合FK，
  保留顺序、NO ACTION、SIMPLE、validated、非deferrable等选定属性。
- 4个0029显式索引：目标/revision普通索引和两个single_successor部分唯一索引；
  检查btree、列顺序、unique、predicate及valid/ready/live。
- 3个0029函数：无参数、trigger返回、plpgsql、非security-definer及函数体摘要。
- 6个触发器：四历史表append-only，加software_changeovers和production_batches的物理写guard；
  检查精确表和函数绑定、BEFORE/ROW、DELETE/UPDATE、无WHEN/参数、非internal/constraint、
  enabled=`O`（origin）。这不是“任何会话复制角色下都启用”的保证。

清单不是全量目录。未覆盖列默认值、collation、生成列/identity、全部索引或约束内部属性、
所有函数属性、其他表/触发器/扩展/权限、业务数据和0024客户范围唯一性。
它也不证明数据库中没有额外对象或额外列。facts严格键集合约束只针对本投影文档，
不是实际数据库对象集合。不能靠隐藏未采集对象获得完整schema验收。

## 表达式、名称与函数体表示

facts以维护者固定的标识为键。匿名PK/unique/FK的键按类型和有序列标识，`name=null`表示
**不比较数据库生成的约束名称**，不是要求数据库约束没有名称；显式命名约束比较原名。
所有字符串区分大小写；数组保持列顺序，events固定DELETE后UPDATE。对象键顺序无关。

check的expression和部分索引predicate采用迁移源码中的精确表达式字面量。
它们不是原始pg_get_constraintdef/pg_get_indexdef/pg_get_expr输出；PG可能添加括号、
类型转换或改变空白。当前没有表达式解析器或已验证的映射器，不能将任意目录输出
直接称为符合该投影。等价但不同的字符串会保守不匹配，不做正则删除/弱化条件来追求匹配。

函数body_sha256取0029实际传给op.execute的常量SQL中、对应CREATE FUNCTION两端
`$$`之间的**原始UTF-8字节**，保留前后空白、缩进和换行，不strip、不换行正规化。
`body_encoding=pg_proc.prosrc-utf8-exact-v1`约定未来比较pg_proc.prosrc原文的UTF-8 SHA256；
它不表示摘要来自实际数据库，亦不是pg_get_functiondef整段DDL摘要。
本包用AST读取字面量独立复核，不执行迁移；尚未实证PG采集回来的字节映射。
函数体文本匹配不证明函数解析上下文、search_path、引用对象、依赖或执行行为安全。

## 输入、状态与操作

仅接受一个UTF-8 JSON对象，精确三个顶层键：

```json
{
  "format": "slc-offline-migration-schema-evidence-v1",
  "checklist": "0029-core-history-subset-v1",
  "facts": {}
}
```

上例只演示缺证据文档，会返回不匹配。实际facts的结构由固定清单中同名facts规定，
不得把清单复制品当作已采集证据。本包不提供数据库连接、SQL或采集命令。
缺失/无法观察的事实应省略，不填假默认值；缺少任何预期事实均为MISMATCH。
已有事实的字段缺失、未知字段/事实、错类型和不合法文档为UNKNOWN。
类型和字段成立但值不同为MISMATCH；null改其他类型仍为UNKNOWN。

在支持的现有本地环境，只读比较：

```sh
python scripts/offline_migration_schema_evidence.py --evidence /absolute/private/new-evidence.json
```

- 退出0 `STRUCTURE_CHECKLIST_MATCHED`：固定有限投影全部自报匹配。
- 退出1 `STRUCTURE_CHECKLIST_MISMATCH`：至少一个事实缺失或报告值不匹配。
- 退出2 `UNKNOWN`：输入/清单/文件/能力不可用，不能比较。

输出只有固定状态、固定清单事实名及matched布尔值，不回显原始值、路径、连接信息或异常。
所有结果均有database_verified=false及限制声明。无参数/错误参数不读输入而返回UNKNOWN；
--help仅显示帮助。不接收URL、数据库、SQL、Docker或运行选项，不读取应用环境变量。

## 文件与资源边界

POSIX且具备dir_fd、O_DIRECTORY、O_NOFOLLOW、O_NONBLOCK才支持；原生Windows缺能力即拒绝。
绝对路径不超过4096字符/256分量，拒绝空分量、点段、反斜杠、控制字符和代理码点。
逐级固定目录描述符、不跟随父/叶符号链接；最终只接受单硬链接普通文件，拒绝FIFO/设备/目录。
文件1..256KiB；从同一FD最多读取初始大小+1，比较前后dev/inode/mode/nlink/size/mtime/ctime。
不按路径重开文件、不重试读/关闭错误、不删除或改写输入。路径并发替换仍可能读取已打开的旧文件，
不是防同UID攻击保证。恶意/网络文件系统或阻塞内核I/O不受Python字节预算保证；仅用于受信本地文件系统，
没有进程/主机安全沙箱或硬实时截止保证。

JSON拒绝重复键、BOM、非UTF8、浮点/指数/NaN/Infinity、负数或超过2^63−1整数；bool不能代替int。
解析后最多10000节点、12层、160对象项、32数组项、512字符字符串，拒绝控制/代理码点。
预解析总字节上限约束json.loads的输入；深度异常或预算不符均UNKNOWN，不公开错误内容。

## 后续验收依赖

后续独立包需设计经审核的只读系统目录采集、可信执行来源、完整退出状态、受控映射与
采集时点；另行明确获准的一次性合成PG16空库必须真实运行当前0001→0030，不能stamp、
手填版本表或create_all替代。不得因本清单匹配而取消原数据库权限检查或追求MATCHED改权限。
真实函数/约束行为、完整schema、只读角色、API连接、恢复和公司部署仍分别待验收。
本包不提高36/44总体、七模块、七计划或浏览器阶段比例。

## 本包验证记录

先18项缺能力回归全部失败，再实现。最终21项集中、568项全离线零跳过、52项自动化、
126项CI守卫通过；Python编译、进度账本及diff空白检查通过。
独立审查另跑21项集中回归及8147次字段/数组/类型变异，没有错误匹配；独立AST核对
0029四表约束分别6/10/7/11项及关键复合FK、部分唯一索引，未发现阻断问题。
这些均为本地合成/静态验证，没有真实数据库、目录采集或运行验收。
历史前端测试启动被平台拒绝，本包未重试或换入口；完整前端、后端、真实PG和严格浏览器
仍待精确候选CI。本包未提交或推送时不得称PR/CI已通过；后续以最新检查点为准。

## v2来源字段分离（离线SQL版本列包）

env.py公开hook的合法变化使原来源字节摘要回归失败。为避免把新字节冒充旧提交的文件，
固定内部manifest升级为slc-offline-migration-schema-manifest-v2：
`facts_baseline_commit`仅标识120事实建立时的历史基线44e307a71a22f93f8c2ae611cf10678b0420499f；
`repository_file_sha256`分别绑定当前随仓库检入的原四个来源文件字节，不宣称来自上述历史commit。
不以自由备注重新解释source_commit。旧模糊source_commit/sources字段移除。

校验器除完整manifest字节SHA之外，严格检查顶层字段全集、固定格式/清单/基线、固定四路径及
64位小写十六进制摘要；未知、缺失或错误字段拒绝。回归保留四源码当前字节绑定，并加入
120事实canonical JSON SHA恒定检查：bc754be5abbb1386f6c6872303c1e9e238a9f5a11315bff91ab7412daf0f4cdc。
canonical形式为JSON sort_keys=True、separators=(',', ':')、ensure_ascii=True后UTF-8。
事实内容、用户证据v1输入、检查输出格式和UNKNOWN/不可信自报边界均不变。
SHA只绑定内容，不是发布者签名/认证；运行校验器不会额外读取这四源码或连接数据库。
新回归覆盖即使测试重绑整体manifest SHA，错误来源元数据仍拒绝。真实SQL/PG验收独立于该JSON清单。
