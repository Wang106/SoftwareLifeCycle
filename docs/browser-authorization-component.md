## 当前检查点 — 2026-11-04 PR175 已合并，B3恢复设计

PR175已合并至 main `43cbcc18d8020d892853d4fae30166fe274b7fef`。[main CI41655534460](https://github.com/Wang106/SoftwareLifeCycle/actions/runs/41655534460)全部成功：2098前端、2846后端＋26子测试、296 PostgreSQL无跳过、86守卫、0029迁移往返；原8条Next＋新5条组件浏览器实际通过，两份严格报告均通过，sandbox=true、零重试。Cloudflare生产build `9ecdcef7-f2a0-4715-b715-770cc7ddb4f4` / version `9697d179-ead4-476e-a5e7-360d8983e6c3`成功。Actions部署/continuation仍skipped，不代表线上数据库或业务健康验收。

下方“仅本地/未执行/CI未接入”等为PR175发布前历史，不能据此重复开发或否认已通过的组件证据。组件套件已接入同一受信runner，仍不证明真实Next会话、FastAPI授权或真实双人身份链。本包仅收口证据并限定B3刷新后手动审计恢复设计，详见[证据与B3范围](browser-authorization-b3-recovery-design.md)。不修改生产代码、身份、CI或测试，不把设计当执行；整体36/44=82%、业务增量0、浏览器阶段保守维持1/4，待B2跨层边界收口再独立判定。

当前新文档包尚未发布，不能把以上基线CI当成本包CI。后续按精确head核验；真实身份/业务写入继续关闭，旧库不重建。此记录取代旧入口中的一次性等待步骤，不恢复历史授权。

---

# B2-C：隔离组件浏览器测试（本地实现，浏览器未执行）

基线 main `c5e38dc20b8ba7f44c1fd7b1481932aef832300e`，PR174设计已合并。新main CI41631030015与Cloudflare生产build `6e196f9f-972e-4cb5-9d8c-9f6a8238c5ca`、version `b0c3c9c7-e34c-4c6c-9689-a69a357e9a6b`成功；Actions deploy/continuation skipped，未据此验收线上数据库或业务健康。

本包实现[已审阅设计](browser-authorization-b2-design.md)的组件层候选，不启用真实身份或业务写入。工作分支 `test/b2-component-browser`，仅本地修改，上传需另获明确批准。B2仍未完成，技术阶段1/4、总体36/44=82%、业务增量0；七模块100/100演示/100演示/100/89/60/17，七计划100/100/20/33/40/40/0不变。

## 结构与隔离

- `frontend/component-browser/entry.tsx`只在测试bundle挂载现有真实React工作台、LanguageProvider和Next Link。三条固定页面选择合成能力props，不是用户身份，不是Next路由，也不传入真实principal或凭据。
- `harness.cjs`使用已锁定TypeScript与Next内置webpack，把编译和bundle产物放到拥有的系统临时目录并清理。没有新依赖、生产源修改或`.next`/Worker产物注入。模块清单验证实际workbench、transport、i18n、React、Next Link存在，未引入browser-auth/session。
- 静态server仅IPv4 loopback、三页面及单一脚本；错误路径/方法/host/WebSocket拒绝。没有API转发，未拦截的请求直接失败。浏览器拦截只允许同源固定资源及三个精确组件代理POST，拒绝外域、真实凭据和未知路径。仅语言偏好cookie被允许。
- 合成响应由测试进程生成，固定目标、17项scope及Python兼容digest，无真实FastAPI、数据库、提供方。批准POST可保持挂起，用于同步重复点击检查，清理时释放。

## 五条固定场景

1. 合成创建者403：明确不可加载私有context，不形成批准命令，不发送批准POST。只验证拒绝响应的UI处理，不证明后端自批判断被浏览器调用。
2. B合成context：显式加载17事实，冻结UUID/digest/target/reason，确认前无提交，确认后原文保持且编辑锁定。
3. 挂起批准时连续DOM点击：单一组件批准POST、原始字节一致；合法200回执后直接confirmed，没有组件自动receipt请求。
4. 合成原始回执的英文/中文切换和raw reason转义；不会把历史批准说成当前可部署/生产许可。
5. 默认关闭和只读能力不提交；另一个合成unknown结果仅经显式恢复请求查询，复用原始命令字节且不再批准。

组件回执校验不传principalId，只校验结构、目标/UUID/digest/reason、creator和不同于creator的合成approver UUID。真实认证actor校验及批准后receipt GET属于现有服务端协议，不由本fixture证明。真实OIDC、会话和权限端到端仍待另定受控目标。扩展刷新、取消、后退、跨页面恢复与完整权限矩阵仍属后续B3/B4。

## 原门禁不变与执行方式

独立`component-browser/playwright.config.cjs`继承原e2e配置：固定已验证Chrome路径、sandbox=true、零重试、forbidOnly、单worker及资源策略不变，只选新文件并使用独立输出。原八条Next用例及原报告校验器没有改动。

独立report校验器严格要求五个固定title/file组合、每项一次实际通过、无错误/跳过/重试、Chromium运行注解及`component-only-not-authentication`层次标记；拒绝原八条Next报告冒充组件结果，也不替换原报告。

在已有受信候选准备成功的同一执行环境，先跑原八条，再独立运行（从frontend目录）：

```
node node_modules/@playwright/test/cli.js test --config=component-browser/playwright.config.cjs
node scripts/check-component-browser-report.cjs component-browser-results/results.json
```

两条命令必须都成功，发现列表不能作为执行证据。当前CI工作流未改：既有frontend Node tests会运行新harness/report契约，但现有browser job仍只跑原八条。**发布后既有CI绿色也不会自动证明这五条新组件旅程执行。** 若需要接入CI，应另界定固定同runner步骤、独立报告/artifact和失败汇总范围，不修改原八条或安全门禁。

本地环境没有原固定、原生验签的Chrome候选。未使用系统Chromium替代，未关闭沙箱、忽略证书、伪造签名或重试曾被限制的浏览器路径。新增五条旅程当前仅发现，尚未执行，不能计B2通过。

## 本地验证与限制

- 使用`npm ci --ignore-scripts --cache /tmp/slc-b2-npm-cache`安装锁定依赖，未改package或lockfile。第一次默认cache路径不可写/不存在导致安装失败，切换到允许写入的临时cache后成功；未改变权限或安全设置。
- Harness契约5/5通过，包括实际React/Next Link bundle与临时清理；独立report契约24/24通过（含真实CLI及负向拒绝）。
- 既有审批transport/recovery/proxy/UI＋原browser-report＋新report focused123/123通过。
- TypeScript noEmit通过；Playwright发现新5条/1文件；84项现有浏览器守卫契约通过。
- 完整前端2098/2098通过，0失败/取消/跳过（65.63秒）。随后加强的spec逐字段/中文断言经TypeScript及五场景发现再次通过，新harness/report契约复跑。独立初审提出的scope/回执字段对应与中文正向断言缺口已修正，待最终复审；这些spec尚未真实执行。
- 真实B2浏览器未执行，后端PG/生产构建未在本包重跑。未上传、未触发远端CI、未合并。
