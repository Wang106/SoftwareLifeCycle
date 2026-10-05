# Cloudflare Preview / 正式部署核验

## 2026-10-05 邮件事件

PR#1 c156d1e 的 Cloudflare 构建 a3ca5368-556c-472e-94bd-f2a9222cc042 失败；
同一提交的 GitHub CI、465项前端测试和 OpenNext 构建通过。CI通过与供应商
预览上传通过是独立事实。该失败记录没有预览URL。

随后 main 合并479e0a2及交接91ad0b5的正式 Workers Builds 均成功；91ad0b5的
完整 main CI run37248690400也成功。公共正式站点中文/英文发布目录200，API
ready200、0.18.27/schema0018，空Deployment写请求403 read_only_mode。
不能将旧分支邮件误判为当前 main 正式部署失败。

原构建日志页要求Cloudflare登录，并显示浏览器验证问题，未获得该次构建的
错误行或实际预览命令。其准确根因待日志确认；不将推断记为远端日志事实。

## 本轮修正

当前Worker Previews默认命令是 `npx wrangler preview`；它要求Wrangler配置
有 `previews`，预览变量不继承生产变量。旧配置缺少该块和显式API绑定。
本轮增加 `previews.vars.API_BASE_URL`，仅指向已有只读样例API；生产域名、
API、OpenNext入口和顶层assets保留。没有增加公司数据、身份秘密、存储资源
或自定义域名预览路由。官方参考：

- https://developers.cloudflare.com/workers/ci-cd/builds/configuration/
- https://developers.cloudflare.com/workers/previews/configuration/

`npm run cf:check`使用仓库锁定Wrangler解析器验证生产/预览配置，CI在测试和
构建前运行。回归覆盖缺失预览块/变量、错误API、未审查资源/路由及错误生产
入口。配置修正不等于该次历史失败已重跑成功；新PR预览需取得独立供应商结果。

## 核验顺序

1. 对照邮件的commit与当前main；分别检查GitHub CI、Cloudflare Preview及正式
   Workers Builds。每个结论绑定完整SHA，旧失败不会被最新成功覆写。
2. 预览失败时读取对应构建日志的首个错误与实际命令；不因CI绿色而跳过供应商检查。
3. 检查root目录、`npm ci`/`npm run cf:build`、预览命令及显式API变量；仅验证
   公共只读样例，不将预览当成公司或受控写入环境。
4. 新PR预览成功后确认返回URL与commit，访问中英文页面，再合并并核验main。
5. 若旧Workers仍用 `wrangler versions upload`，其Version URL模型与新Worker
   Previews不同；先确认实际设置。当前缺少日志，未改供应商控制台设置。

7项计划维持100/100/20/33/40/20/0，ROADMAP36/44=82%。预览配置修正不完成
环境隔离、恢复、回滚或公司上线验收，不增加固定里程碑勾选。
