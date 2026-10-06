# 管理员授权目录、详情与状态历史 — API0.18.31

本包为后续中英文授权管理界面提供私有、有界读取。它不创建或停用身份，
不新增角色或管理员，不配置提供方，不开启公共写入。schema仍0019。

## 身份与访问

三个GET仅允许OIDC认证成功且当前本地身份为ACTIVE的PLATFORM_ADMIN。
每次查询在读取事务内复核身份UUID/issuer/subject及管理员分配；AUDITOR、
普通项目角色和软件角色不具有管理读取权限。可在READ_ONLY_MODE=true下
读取，但OIDC禁用态仍返回401 oidc_not_enabled，不回退到演示数据。

如提供X-Browser-Session，需属于同一身份、绑定同一Bearer且未过期/撤销。
该读取不要求必须来自浏览器；正常API Bearer调用可不带该标头。认证、
授权、验证、404及正常响应均private,no-store、Pragma:no-cache，并按
Authorization隔离；成功/应用响应也Vary:X-Browser-Session。

## 授权目录

`GET /api/v1/security/admin/grants?scope=PROJECT`

| 参数 | 限制 |
| --- | --- |
| scope | 必填GLOBAL/PROJECT/SOFTWARE |
| principal_id | 可选精确身份UUID |
| scope_id | 可选精确项目/软件UUID；GLOBAL禁止 |
| role | 可选角色名，必须属于所选scope；空值/错误角色拒绝 |
| status | 可选ACTIVE/SUSPENDED；GLOBAL没有此状态列，禁止该参数 |
| principal_status | 可选ACTIVE/DISABLED |
| limit | 默认50，1–100 |
| offset | 默认0，0–100000 |

额外参数、名称/邮箱/subject筛选等不受支持，返回422，不静默忽略。
目录默认包含ACTIVE和SUSPENDED授权、ACTIVE和DISABLED身份；全量计数与
分页使用同一筛选条件。按授权UUID升序，返回scope、total、limit、offset、
next_offset和items；末页及超出范围next_offset=null，保留准确total。

每个item仅包含id、scope、role、status、created_at、effective、principal、
target、status_history_supported。principal为id/principal_type/display_name/status；
target为项目/软件id/code/name，GLOBAL为null；GLOBAL的status为null，不能
伪造为一个可暂停的状态。effective仅说明该行与目标身份当前是否生效，不
等于用户最终综合权限；其其他角色或全局管理员覆盖需单独查看。

查询使用存储的UUID连接，不能将同名对象或客户端文字当作授权关联。
只投影标量；不序列化ORM关系、邮箱、issuer、subject或凭据字段。

## 单条详情

`GET /api/v1/security/admin/grants/{scope}/{grant_id}`

scope为GLOBAL/PROJECT/SOFTWARE；grant_id是对应分配/成员行UUID。
响应与目录item一致，无子历史数组。错误scope或不存在UUID返回404；
附带筛选参数返回422。先检查管理员权限，再查目标，普通用户不得借详情
接口区分一个合法UUID是否存在。schema参数错误不包含对象存在性证据。

## 项目／软件授权状态历史

`GET /api/v1/security/admin/grants/{scope}/{grant_id}/history?limit=50&offset=0`

仅PROJECT/SOFTWARE支持；GLOBAL返回422，因为当前没有全局角色变更接口。
只允许limit/offset，与目录相同边界。先核对精确授权行存在，然后使用
entity_type、entity_id、canonical entity_ref及MEMBERSHIP_STATUS_CHANGED联合
过滤；复用既有entity_type/entity_ref索引，不混入业务事件或其他对象。

响应scope、grant_id、current_status、coverage、total、分页字段及items。
coverage固定MEMBERSHIP_STATUS_CHANGED_ONLY；零条记录不证明此授权从未
由维护SQL建立/更改，也不是完整身份管理历史。只展示此类状态事件。

items包含id/event_no/action/occurred_at、历史actor_principal_id和
actor_display_name快照、expected_status/status/reason/reason_truncated。
按occurred_at降序、UUID降序打破同时间并列。状态只投影ACTIVE/SUSPENDED，
未知历史值返回null；reason在SQL中限制500字符并标记截断。整个payload_json、
声明姓名、未列出的JSON字段和令牌不进入响应。历史原因/显示名是已记录的
业务文本，操作人员不得向这些字段写入秘密。

## 一致性与验证边界

读取不写入授权、身份或审计，也不锁定整个管理目录。PostgreSQL默认
READ COMMITTED下身份检查、parent/current_status、计数和分页是各自的
语句快照；并发授权变更/新增事件时可能跨快照，不能宣称固定时间点导出。
继续翻页需保留相同筛选；offset上限不是所有规模下的无限浏览承诺。
将来的稳定导出/游标是另行开发范围。已通过授权的在途读取不会被追溯取消。

回归以签名Bearer在SQLite和真实PostgreSQL执行，覆盖所有scope、角色/状态/
UUID筛选、认证和管理员拒绝、私有缓存、精确详情及状态历史关联、并列排序、
JSON字段裁剪。分别增加110条角色和110条大payload审计，验证完整计数、
固定页面长度及固定SQL次数；目录/详情/历史总15次（含每次middleware身份
查询及事务内管理员复核），无ORM授权或历史图加载。

完整身份/角色新增、全局管理员恢复、管理界面和真实提供方验收仍未完成；
本包不将审计授权管理的整体里程碑勾选完成。
