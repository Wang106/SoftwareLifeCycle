# 身份与授权新增请求准备
更新：2026-10-08（Asia/Shanghai）；模式：Codex。

/account/grants/new 复用当前加密会话和后端管理员私有读取复核，不从前端grant count推断管理权限；禁用/过期/拒绝/故障均不显示准备表单。只有管理员读取成功才呈现。目录页在ready分支提供入口。公开默认OIDC关闭，无身份表单；页面private/no-store。本页只准备/确认/复制，没有HTTP发送、浏览器持久存储或真实对象创建。

## 对接现有契约
| 操作 | POST目标 | 正文特有字段 | 初始状态 |
| --- | --- | --- | --- |
| 本地身份 | /api/v1/security/admin/principals | principal_id, subject, principal_type, display_name | DISABLED |
| 全局授权 | /api/v1/security/admin/global-roles | grant_id, principal_id, role | SUSPENDED |
| 项目授权 | /api/v1/security/admin/memberships/PROJECT | membership_id, principal_id, scope_id, role | SUSPENDED |
| 软件授权 | /api/v1/security/admin/memberships/SOFTWARE | membership_id, principal_id, scope_id, role | SUSPENDED |

所有正文另含event_no与reason；不含issuer、actor、status、token或其他额外字段。issuer仅来自后端配置。USER/SERVICE注册不会创建提供方账号、激活身份或自动授予角色；身份激活需要另行审计操作，新授权生效需要另行resume。GLOBAL默认选择AUDITOR，PLATFORM_ADMIN须明确选择；首次管理员/恢复仍遵循已有离线operator政策，不通过此表单自动创建。

## 校验和确认
UUID必须精确、规范化小写；subject保持大小写/内部空格/Unicode原值，拒绝前后Python strip空白及C0/DEL，不偷偷trim或替换提供方标识。subject1–500、display_name1–200均按Unicode码点计数；原因按后端strip语义整理后5–500可打印码点。审计键1–50允许ASCII字符且首字符字母数字。
角色表对应backend/app/security_roles.py：GLOBAL两角色，PROJECT七角色，SOFTWARE两角色；拒绝跨作用域角色。接收身份存在/ACTIVE/issuer、目标存在、管理员接收方保护、唯一性、actor绑定重放和原子审计最终仍由API检查，预览不是授权/资格证明。
修改任何操作/字段撤销预览和勾选；确认后复制固定UUID/事件编号/正文。剪贴板失败保留可选中JSON。不要把密码、token、Cookie或机密放入subject/name/reason；仅填写经批准的真实提供方身份标识。

## 验证和缺口
回归覆盖USER/SERVICE、全部11作用域角色及与真实后端常量对账、精确字段/无额外字段、Unicode/空白/长度、UUID与角色错配、冻结确认/重复导出和中英文SSR。生产禁用认证检查新增此页双语private/no-store且没有身份表单。
尚未实现注册代理/受控发送、身份目录/详情及激活/禁用界面、跨会话恢复；实际提供方/管理员/浏览器与内网部署尚未验收。公共只读/OIDC和写入默认关闭，内网服务器尚未开始部署。未创建真实账号、角色授权或配置秘密。本包不增加14项业务命令，也不提升两套里程碑。
