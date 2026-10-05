# Cloudflare Preview / 正式部署核验

## 2026-10-05 邮件事件

PR#1 c156d1e 的 Cloudflare 构建 a3ca5368-556c-472e-94bd-f2a9222cc042 失败；
同一提交的 GitHub CI、465项前端测试和 OpenNext 构建通过。CI通过与供应商
预览上传通过是独立事实。该失败记录没有预览URL。

随后 main 合并479e0a2及交接91ad0b5的正式 Workers Builds 均成功；91ad0b5的
完整 main CI run37248690400也成功。公共正式站点中文/英文发布目录200，API
ready200、0.18.27/schema0018，空Deployment写请求403 read_only_mode。
不能将旧分支邮件误判为当前 main 正式部署失败。

用户提供的00:35日志已确认PR#1实际执行 `npx wrangler preview`，首个ERROR为
缺少 `previews` 块。根目录安装只添加35个依赖且没有前端构建步骤进入日志，
结合根目录Wrangler配置，说明该错误在进入OpenNext构建前发生。
PR#2 00:53失败的日志尚未提供，不能直接将其错误行归因于旧日志。
但此前补丁只修改frontend配置，根目录配置仍缺少该块，是已确认的修复遗漏。

## 本轮修正

当前Worker Previews默认命令是 `npx wrangler preview`；它要求Wrangler配置
有 `previews`，预览变量不继承生产变量。旧配置缺少该块和显式API绑定。
本轮在根目录和frontend两份配置中增加 `previews.vars.API_BASE_URL`，仅指向已有只读样例API；生产域名、
API、OpenNext入口和顶层assets保留。没有增加公司数据、身份秘密、存储资源
或自定义域名预览路由。官方参考：

- https://developers.cloudflare.com/workers/ci-cd/builds/configuration/
- https://developers.cloudflare.com/workers/previews/configuration/

`npm run cf:check`使用仓库锁定Wrangler解析器验证根目录和frontend生产/预览配置，CI在测试和
构建前运行。回归覆盖缺失预览块/变量、错误API、未审查资源/路由及错误生产
入口。配置修正不等于该次历史失败已重跑成功；新PR预览需取得独立供应商结果。

## 核验顺序

1. 对照邮件的commit与当前main；分别检查GitHub CI、Cloudflare Preview及正式
   Workers Builds。每个结论绑定完整SHA，旧失败不会被最新成功覆写。
2. 预览失败时读取对应构建日志的首个错误与实际命令；不因CI绿色而跳过供应商检查。
3. 检查root目录、`npm ci`/`npm run cf:build`、预览命令及显式API变量；仅验证
   公共只读样例，不将预览当成公司或受控写入环境。
4. 区分构建失败与已构建但预览主机未启用。若主机已启用，先核验返回URL与commit、中英文页面，再合并。若提供方明确报告No Preview URL / Enable，先在两份配置显式设置preview_urls=true，通过CI与Preview构建后合并，以main正式部署应用该主机开关；随后重新核验分支返回URL与中英文页面。不得把待激活状态写成已访问成功。
5. 若旧Workers仍用 `wrangler versions upload`，其Version URL模型与新Worker
   Previews不同；先确认实际设置。旧日志已确认使用新Preview命令，未改供应商控制台设置。

7项计划维持100/100/20/33/40/20/0，ROADMAP36/44=82%。预览配置修正不完成
环境隔离、恢复、回滚或公司上线验收，不增加固定里程碑勾选。

## Preview URL activation — 2026-10-05

PR#2 `3a349b2` now has successful Actions run37304274627 and Cloudflare Preview
794eff35-0645-4262-a9a4-d0bee4fbf185; its bot comment reports No Preview URL / Enable.
Both configs now set `preview_urls: true`; preflight rejects absent/false/non-boolean
values. Cloudflare applies this setting through `wrangler deploy`, not by merely
uploading a branch Preview. Current official references:

- https://developers.cloudflare.com/workers/previews/custom-domains/#enable-workersdev-preview-urls
- https://developers.cloudflare.com/workers/wrangler/configuration/#inheritable-keys

The opt-in applies to Version URLs as well as workers.dev Worker Previews. These
previews serve the existing public sample frontend/API; no custom-domain wildcard
route is added. Successful upload and accessible runtime are separately verified.
