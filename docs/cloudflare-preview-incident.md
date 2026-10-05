# Cloudflare 邮件与预览失败排查 — 2026-10-05

模式：Codex云端。核对起点：main91ad0b55d3277656b91f05cca348dcbab0c77539。

| 范围 | 提交 | 独立证据 | 结果 |
| --- | --- | --- | --- |
| 邮件对应旧PR#1预览 | c156d1e01fa41ea8062f05c899bdeb47d95df5da | Workers build a3ca5368-556c-472e-94bd-f2a9222cc042 | 失败，无预览URL |
| main合并正式构建 | 479e0a292e921b1f325985038903d71edafa7a8c | Workers build ee4c0c93-57d4-4337-9579-d99e23580667 | 成功 |
| main交接正式构建 | 91ad0b55d3277656b91f05cca348dcbab0c77539 | Workers build31f3bd1d-82ad-4e62-8be0-1ded4c07f5b4；CI37248690400 | 全部成功 |
| 新配置修正草稿PR#2 | 40e23fe41c0d53336a7e2114711a9f02da329edc | CI37249193295；Workers build44a78aac-5dfa-49b7-8ca1-4f8ca2e6cf70 | CI成功，供应商预览失败，未合并 |

正式站点中英文发布目录HTTP200；APIready200、0.18.27/schema0018；空Deployment
写请求403 read_only_mode。没有提交业务写入。旧邮件不是当前main正式部署失败的证据。
不能以GitHub CI通过代替Cloudflare Preview上传成功。

## 已做工作

检出配置缺口：当前Worker Previews默认使用 `npx wrangler preview`，要求
Wrangler `previews`块，预览变量不继承生产变量。旧仓库配置缺少这两项。
PR#2补齐 `previews.vars.API_BASE_URL`，仅指向已有只读公共样例API；生产域名、
顶层OpenNext入口/assets及API保持。新增CI `npm run cf:check`及4项配置回归。
Cloud CI后端1204无跳过、前端469无跳过、Wrangler预检和OpenNext构建均成功。
该修正是独立验证的配置缺口修正，尚未验证它解决供应商预览失败。

PR#2：https://github.com/Wang106/SoftwareLifeCycle/pull/2
CI：https://github.com/Wang106/SoftwareLifeCycle/actions/runs/37249193295
官方契约：https://developers.cloudflare.com/workers/previews/configuration/
命令契约：https://developers.cloudflare.com/workers/ci-cd/builds/configuration/

## 阻塞与继续条件

Cloudflare构建详情需要登录。当前云端浏览器显示验证失败、登录按钮禁用；
仅重新加载一次，问题仍存在，未取得原始错误日志，也未变更控制台或访问权限。
未使用猜测的凭据或更换网络路径。实际预览命令、首个ERROR、权限或平台初始化
失败原因均未确认。新预览再次失败，证明补齐配置尚不足以确认整个预览问题已解决。

下一步需要失败构建 `44a78aac-5dfa-49b7-8ca1-4f8ca2e6cf70`（或原构建a3ca5368）
的首个ERROR及前后日志、实际命令。取得错误行后按真实原因修正，再触发新的
Cloudflare Preview，访问其返回URL并核验中英文/只读，之后再合并。PR#2保留草稿，
未声称修复完成或已部署。不要关闭预览/通知来把失败伪装成成功。

主线仅增加排查/交接记录，待验收修正仍在分支。API、schema、公开写保护、凭据
和提供方未改。7项计划保持100/100/20/33/40/20/0；ROADMAP36/44=82%，模块
100/100-demo/100-demo/100/89/60/17，消费者17/17及53=50退役+3有界维持。
预览配置草稿不完成环境隔离/恢复/部署回滚/公司数据验收。
