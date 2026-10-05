# Cloudflare 1010 与部署邮件处理

更新时间：2026-10-06（Asia/Shanghai）；本轮模式：Codex。

## 本次核对结果

PR #6 邮件时间是 2026-10-06 07:03:24（北京时间），当时构建中。
同一条机器人评论已更新：07:05:28 构建和 Preview 部署成功。
提交为 `1f9f828cc84c0f9f9ad2fa364a5e0cbbf9948692`；main 合并提交
`a9e4765a7f8ed60e7abf70342cc0265a7e03f79a` 的 CI 和正式发布也成功。
旧通知不等于最新状态，也不等于访问策略已验收。

2026-10-06 07:14 左右，从同一执行环境只改变 User-Agent，并保持
GET /account、Accept: text/html 和 URL 不变，得到以下结果。
这是 HTTP 客户端对照，未修改 Cloudflare 设置，未模拟真实浏览器验收。

| 地址 | Python 默认 User-Agent | 项目自动检查 User-Agent |
| --- | --- | --- |
| 正式站 softwarelifecycle.whf969.com/account | 403；CF-Ray a4601f646f60daec-DFW | 200；CF-Ray a4601f63add2daec-DFW |
| PR #6 immutable Preview bbddba4c-softwarelifecycle.whf969.workers.dev/account | 403；CF-Ray a4601f794c58daec-DFW | 200；CF-Ray a4601f782a96daec-DFW |

项目标识为 `SoftwareLifeCycle-DeploymentCheck/1.0`，没有冒充浏览器、发送
登录凭据或响应挑战。此结果说明之前的探针受客户端特征影响；是否由你管理
的 BIC 规则命中，仍需控制台事件确认，尤其 Preview 的 workers.dev 不是
whf969.com 的 DNS zone，不能假设一个 zone 设置同时控制两类地址。

## 如果你的手机/电脑浏览器可以正常访问

无需因上述自动检查失败修改安全规则。本轮增加了明确声明客户端身份的检查器，
正式站中文、英文账户页均返回200；禁用态 /auth/session、/auth/callback 返回
503 login_not_configured，GET /auth/login 返回405 method_not_allowed。
这些拒绝是应用在未配置身份提供方时的预期行为，不是1010。

## 如果真实浏览器也出现1010

Cloudflare 官方将1010解释为客户端浏览器签名被拒绝，并列出 Browser
Integrity Check（BIC，浏览器完整性检查）的处理方法。先确认实际错误码；
1020、自定义WAF拦截、挑战页面和应用401/403需要按各自事件处理。

1. 登录 Cloudflare，打开 **whf969.com** 这个站点的 zone。
2. 进入 **Security → Analytics → Events**（旧版界面称 Security Events），
   按发生时间、Host `softwarelifecycle.whf969.com`、路径和 User-Agent 筛选。
   展开事件确认实际 Service/Action，保存 Ray ID。日志可能采样，未查到事件
   不等于请求未被拦截；缩小时间范围后再试。
3. 如果事件确认是 BIC 误拦截，进入 **Security → Security rules → Create rule
   → Custom rules**。规则名可用 `SoftwareLifeCycle BIC exception`。
   在表达式编辑器填入：

   ```text
   http.host eq "softwarelifecycle.whf969.com"
   ```

4. 动作选择 **Skip**，仅选择 **Browser Integrity Check**，保留日志记录，部署。
   这是针对这个子域的 BIC 例外；其他产品和其他子域保持原配置。
   也可使用按此 Host 匹配的 Configuration Rule，将 BIC 设为 Off。
5. 用刚才被拦截的真实浏览器重新打开正式地址，并核对新事件。
   若无改善，查看实际匹配规则，不要扩大例外范围来猜测原因。

直接在 Security → Settings 关闭 BIC 会作用于整个 zone；whf969.com 的其他
站点也会受到影响。正常浏览器已可访问时，不需要执行上述例外操作。
不把关闭全部WAF、暂停Cloudflare、更换DNS或关闭应用认证作为1010的修复。
本轮没有创建上述规则；目前没有可调用的 Cloudflare zone 管理连接。

## 持续开发新增的检查器

```bash
python scripts/check_frontend.py https://softwarelifecycle.whf969.com --output ci-results/frontend-access.json
python scripts/check_frontend.py https://bbddba4c-softwarelifecycle.whf969.workers.dev --output ci-results/frontend-preview-access.json
```

检查器仅允许已批准的正式站或本项目 Preview origin，HTTPS、无账号/查询参数，
拒绝公司/其他站点及重定向。只发5个GET请求，除了语言偏好不带任何Cookie，
不发送Authorization、不调用提供方、不发业务写入。512KiB响应上限和网络
超时限制；报告仅保存状态、分类、CF-Ray等白名单元数据，排除响应正文、
Set-Cookie和凭据。返回值0为全部通过，1为访问/契约失败，2为输入错误。

分类区分 cloudflare_1010、cloudflare_1020、其他边缘拒绝、重定向、请求失败、
响应超限、语言/登录状态错误与缓存错误。返回200还必须满足HTML正文文本（排除script/style）、
正确语言和关闭态登录表单约束；脚本内的文字不能冒充页面证据。
JSON禁用态必须准确匹配错误码、private/no-store及Vary: Cookie。

GitHub新增 `.github/workflows/frontend-access.yml`，在 Actions 中选择
**Read-only frontend access → Run workflow**，填写正式站或返回的完整Preview
origin；任务保存14天JSON证据，失败不能伪装成绿灯。它只在手动触发时运行，
不会在构建尚未完成时自动探测旧版本。Cloudflare部署状态仍从精确提交的
Workers检查/机器人评论单独核对。HTTP/SSR检查不是真实浏览器/提供方验收，
也不能当作身份会话或生产运营里程碑完成的证据。

## 官方依据

- 1010：https://developers.cloudflare.com/support/troubleshooting/http-status-codes/cloudflare-1xxx-errors/error-1010/
- BIC及选择性例外：https://developers.cloudflare.com/waf/tools/browser-integrity-check/
- Skip仅选BIC产品：https://developers.cloudflare.com/waf/custom-rules/skip/options/
- 安全事件：https://developers.cloudflare.com/waf/analytics/security-events/
- 自定义规则界面：https://developers.cloudflare.com/waf/custom-rules/create-dashboard/

## PR #7 最终验收

访问检查与47项新回归测试已合入main：PR #7，代码合并提交
`95ba4077ba3ce6b51e0b0739fccbabacd93fbd8c`。PR CI37388684638和main
CI37389097842全部通过：后端1332、前端541、PostgreSQL模块107项无跳过。
PR Preview于07:30:30、main Cloudflare于07:34:52（北京时间）部署成功；
正式站07:36的5项HTTP/SSR探针全部通过。API健康检查200，0.18.29/0019。
手动访问工作流未触发；脚本本地、真实Preview和正式站执行已验收。
这些结果不代表真实浏览器/身份提供方验收，也未修改任何Cloudflare安全规则。
