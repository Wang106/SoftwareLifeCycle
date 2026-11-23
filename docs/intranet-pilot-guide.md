# 内网试点配置指南

这份指南对应 2026-11-23 已确认的试点决定：用 Microsoft 365 / Microsoft Entra ID 的公司邮箱登录，部署在公司内网，由你本人填写身份参数。仓库里的示例全部是占位符。不要把真实 tenant id、应用程序 ID 或客户端机密提交进 Git。

试点配置只在 `INTRANET_PILOT=true` 时生效。默认的 `docker-compose.yml` 和公网样例行为不变：公网样例仍应只读，并且不要打开这个开关。

## 你需要准备的参数

在 Entra 管理中心登记应用之后，把下面的值填进 `deploy/intranet-pilot.env.example` 的副本。空着或仍是 `00000000-0000-0000-0000-000000000000`、`example.invalid`、`REPLACE_ME` 时，API 进程会在启动时拒绝配置，不会对外服务。

| 变量 | 填什么 |
| --- | --- |
| `OIDC_ISSUER_URL` | `https://login.microsoftonline.com/<租户 ID>/v2.0`。租户 ID 是目录概述里的 Tenant ID，使用小写 GUID。不要用 `/common`、`/organizations` 或 `/consumers`。 |
| `OIDC_AUDIENCE` | 应用程序（客户端）ID，与 `OIDC_CLIENT_ID` 相同。 |
| `OIDC_CLIENT_ID` | 同一个应用程序（客户端）ID。 |
| `OIDC_JWKS_URL` | `https://login.microsoftonline.com/<租户 ID>/discovery/v2.0/keys`。这是该租户 v2.0 discovery 文档里的 `jwks_uri`。启动时不访问 Microsoft；真正校验令牌时才读取这个地址。 |
| `OIDC_AUTHORIZATION_URL` | `https://login.microsoftonline.com/<租户 ID>/oauth2/v2.0/authorize` |
| `OIDC_TOKEN_URL` | `https://login.microsoftonline.com/<租户 ID>/oauth2/v2.0/token` |
| `OIDC_EMAIL_DOMAINS` | 公司邮箱域名，例如 `contoso.com`。多个域名用逗号分隔。只用于限制邮箱，不作为用户主键。 |
| `INTRANET_PILOT_BOOTSTRAP_EMAIL` | 第一位管理员的公司邮箱，必须属于上面的域名。 |
| `BROWSER_SESSION_ORIGIN` | 内网 Web 的 HTTPS 源，例如 `https://slc.corp.example`。不要带路径。 |
| `CORS_ORIGINS` | 与 Web 源相同的一个 HTTPS 源。不要填公网样例域名。 |
| `BROWSER_SESSION_KEY` | 本机生成的 32 字节随机数，再做成 base64url。不要提交。 |
| `POSTGRES_PASSWORD` / `DATABASE_URL` | 内网数据库自己的口令。不要复用示例里的占位口令。 |

Discovery 文档地址是 `https://login.microsoftonline.com/<租户 ID>/v2.0/.well-known/openid-configuration`。只把它当作核对 `jwks_uri` 的说明，程序启动时不会请求它。

重定向 URI 固定为：

`https://<你的内网 Web 源>/auth/callback`

例如 Web 源是 `https://slc.corp.example` 时，登记 `https://slc.corp.example/auth/callback`。路径来自现有登录代码，不能改成别的路径。

## 在 Entra 管理中心登记

1. 打开 Microsoft Entra 管理中心，进入应用注册，新建一个应用。支持的账户类型选“仅此组织目录中的账户”。
2. 记录目录（租户）ID 和应用程序（客户端）ID。
3. 在身份验证里添加 Web 平台重定向 URI，值就是上面的 `/auth/callback`。不要登记公网样例域名。
4. 令牌配置里，为 ID 令牌和访问令牌都加上可选声明 `preferred_username` 和 `email`。登录范围使用 `openid profile email`。
5. API 权限保持最小。这个试点用应用程序自己的客户端 ID 作为 audience，不把 Microsoft Graph 当作本系统的 audience。
6. 如果应用是机密客户端，再创建客户端机密，只放在服务器环境变量 `OIDC_CLIENT_SECRET`，并把 `OIDC_CLIENT_AUTH` 设为 `client_secret_basic`。示例文件默认不使用机密。机密不要写入 Git。
7. 在“企业应用程序”里把需要登录的用户分配到这个应用。没有在本系统预先登记邮箱的人，即使能从 Entra 拿到令牌，也会被拒绝。

不需要创建 Entra App Roles。组声明也不是主方案。用户属于太多组时，Entra 会省略 `groups` 并给出 overage（超额）标记；把“没有组声明”当成“没有权限”或“有全部权限”都不安全。因此试点不读取 App Roles 或组来发角色。若以后要用作额外限制，必须单独设计，并且在出现 overage 时直接拒绝，不能把缺省组列表当成授权结果。

## 邮箱如何对应到角色

用户主键不是邮箱，也不是可变的 UPN。令牌里的 `oid` 和 `tid` 才是绑定身份。邮箱只用来把第一次登录对上管理员已经登记的那一行。

1. 用下面的操作员命令建立第一位管理员。配置里的 `INTRANET_PILOT_BOOTSTRAP_EMAIL` 就是这位管理员的邮箱。命令不会在请求文件里再写一遍邮箱，避免两处不一致。
2. 该管理员用这个邮箱从 Entra 登录。第一次成功登录把这一行绑定到令牌中的 `tid` 和 `oid`。
3. 之后每次登录都先核对是不是同一个 `oid`。邮箱被重新分配给另一个 `oid` 时，新的 `oid` 不能继承原来的角色。原来的 `oid` 如果改了邮箱，也不会自动改登记邮箱，需要管理员另行处理。
4. 管理员在系统里为其他同事登记邮箱。接口是 `POST /api/v1/security/admin/principals/email`。新登记的身份是停用状态，没有角色。
5. 用现有的主体启用接口把它改为 `ACTIVE`，再用现有的项目/软件成员接口分配角色。成员登记最初是 `SUSPENDED`，需要再按现有状态接口启用。未登记的邮箱一律拒绝。角色仍然是数据库里的项目角色和软件角色，不是 Entra 目录角色。

`INTRANET_PILOT` 关闭时，上述邮箱接口返回 404，原来的主体登记和 `sub` 登录方式保持原样。

## 启动与第一位管理员

在仓库根目录：

```bash
cp deploy/intranet-pilot.env.example /secure/intranet-pilot.env
# 编辑 /secure/intranet-pilot.env，替换全部占位符
docker compose -f docker-compose.yml -f docker-compose.intranet-pilot.yml --env-file /secure/intranet-pilot.env up --build
```

API 容器里的 `ADMIN_OPERATOR_ENABLED` 保持 false。第一位管理员用一次性进程，不要把操作员开关留在 Web 进程里：

```bash
cd backend
ADMIN_OPERATOR_ENABLED=true INTRANET_PILOT=true python -m app.admin_operator plan
```

`plan` 在试点模式下会多给出 `bootstrap_email_fingerprint`。把该指纹写进请求文件的 `email_fingerprint`，不要把邮箱本身写进请求文件。然后：

```bash
ADMIN_OPERATOR_ENABLED=true INTRANET_PILOT=true python -m app.admin_operator bootstrap-email --request /secure/first-admin.json
```

请求文件仍使用现有操作员字段：`event_no`、`reason`、`approval_ref`、`target_fingerprint`、`acknowledge_privileged_change`、`expected_effective_admin_count`、`principal_id`、`grant_id`，外加 `display_name` 和 `email_fingerprint`。不要添加 `subject`。执行前数据库里还不能已有平台管理员。

业务命令的提交开关（快照、交付、更正等）继续默认关闭。试点配置只打开身份校验，不自动打开那些写入开关。

## 备份与回滚

这不是已经验收过的灾难恢复。在创建第一位管理员或导入任何内网数据之前：

1. 确认这是空的内网库，`SEED_ON_STARTUP=false`，没有连接公网样例库。
2. 用你们自己的 PostgreSQL 规程做一次 `pg_dump`，把 dump 放在内网、限制访问，并记下文件校验和。
3. 如果试点要退回，停止 API，用这次 dump 恢复该库，并停用试点环境变量。不要用公网样例数据覆盖内网库。
4. 回滚后，已经发出的浏览器会话应视为失效。恢复的是绑定前或绑定后的那一份 dump，不能混用两套。

## 验收清单

- 占位符配置启动 API 时进程失败，并且没有监听业务端口。
- `SEED_ON_STARTUP=true` 或 `AUTH_MODE=disabled` 配上 `INTRANET_PILOT=true` 时启动失败。
- 其他租户、`/common` 发行方，或 `tid` 与配置租户不一致的令牌被拒绝。
- 未登记邮箱被拒绝，即使令牌签名有效。
- 已登记、已启用、并已分配项目/软件角色的邮箱可以登录；第一次登录后数据库主题变为 `entra-oid:<tid>:<oid>`。
- 同一邮箱配上另一个 `oid` 被拒绝，原角色不被带走。
- 公网样例域名不在 CORS 里。App Roles 不是登录条件。
