# 项目目录读取超时：隔离真实浏览器包

本包在 `test/project-catalog-timeout-browser` 上验证已经合并的项目目录15秒读取预算。新增两条真实浏览器用例，分别让合成 API 在响应头和响应体阶段真实停住，检查加载、不可用和显式重读。生产页面、API客户端和超时配置不变；这是既有只读可靠性修复的浏览器补充，不是B2、数据库恢复或真实身份验收。

## 已核验基线

PR172已保护合并并关闭，main为 `baa9b53f2d9e331f620083fe3f3dadcb0493f7ac`。[main CI41312475850](https://github.com/Wang106/SoftwareLifeCycle/actions/runs/41312475850) attempt1已全部成功：

- 后端2846项＋26子测试、296 PostgreSQL模块用例无跳过；84项浏览器守卫契约；0029单迁移头与SQL/PG往返。
- 前端2048项、0失败/取消/跳过，Next/OpenNext、Worker配置和禁用认证双语SSR。
- 原六条真实Chromium用例，0失败/跳过/重试；聚合验收成功。

固定官方Chrome PKG的摘要、字节数、Google Installer/Apple链和原展开应用深度严格验签均通过。实际候选为156.0.8078.80，734个成员检查通过，`chromiumSandbox=true`；没有修改安全设置。详情见[PKG候选记录](browser-pkg-candidate.md)及HANDOFF最新证据。

Cloudflare生产build `b63d3f48-8510-4b68-ba6e-1f4cd629d1a8`、provider报告version `70ba6d0e-7c1e-4808-8d92-4c4804d216b9`成功。Actions deploy/wake为skipped。构建和版本记录不证明当前线上健康、过期数据库可用或真实身份/公司验收。

## 两条用例的可观察行为

固定查询为：

```text
q=A+%26+B&status=ACTIVE&customer_id=customer-one&limit=10&offset=20
```

应用页面是 `/projects?` 加此查询；合成API是 `/api/v1/organization-views/projects?` 加同一查询。`customer-one`、查询值与所有返回数据仅用于合成测试。

| 阶段 | 合成API行为 | 必须取得的浏览器证据 |
| --- | --- | --- |
| 响应头挂起 | 收到精确GET后不发送headers、不结束响应 | 原生文档以commit开始观察，加载status可见；应用超时后出现不可用，summary为“—”，无伪造空表或0；原请求被终止 |
| 响应体挂起 | 发送200和JSON开头`{`，保持body未结束 | 同样由真实应用读取预算终止；不展示原始解析/Abort错误；失败后切换English，仍无新增目标GET |
| 健康恢复但未点击 | 仅改变未来GET的fixture状态，不完成原响应 | 800ms观察期内仍显示不可用和“—”，目标GET保持一次 |
| 用户显式重读 | 点击保持精确查询的原生链接，新GET返回有效空目录 | 同URL真实文档导航、旧文档标记消失；目标GET恰好增加一次；summary成为可信的0，空结果提示出现，不可用/重试/loading消失 |

header用例保持中文；body用例在不可用后切换英文并核对英文恢复。既有15000ms应用读取预算不变，fixture没有自行超时返回错误或延迟成功。25秒断言期限只限制测试等待；观测时间、800ms无重读窗口和本地耗时均不是生产延迟保证，也不额外界定连接建立或整页总耗时。

同URL不使用 `waitForURL` 作为唯一新导航证据：先等待主frame的真实GET文档响应，再检查文档标记和两次精确目标API读取。首次挂起响应的`finishedAt`必须为空、`closedAt`必须出现，防止把fixture自动结束当成应用取消。

## 隔离、预取和报告门禁

应用、API和流式proxy只使用新建loopback端口；没有外部服务、真实数据库、凭据或业务写入。API只接受固定目标和有限first/reset查询形式的匿名GET；未知路径、重复/额外查询、不同序列化、凭据、body和写请求拒绝并记录脱敏违规。恢复是测试进程内方法，不增加应用或API控制端点；已挂起响应不会因调用恢复方法而结束。

proxy保持未选择新功能时的原默认行为；新调用须显式提供唯一固定查询选项。业务查询不能改写、重新排序或增加参数。浏览器仅允许目标原生文档、静态资源和有限已知Next RSC预取路径；预取读取独立记录，不能冒充目标原生重读。唯一允许的浏览器cookie是合成语言偏好，API fixture独立拒绝任何cookie。外部/private请求、WebSocket、重定向和变更方法均不能成为有效证据。

真实流式响应通过proxy直接转发，不用缓冲后的`fetch/fulfill`替代。每条用例保存脱敏的请求/关闭/完成时间、浏览器读取及阶段观察；失败另附合成Next日志。清理即使proxy关闭失败也继续停止测试拥有的Next/API，fixture关闭会终止未完成响应。

原六条用例及其title/file映射不变，新增：

```text
project catalog header stall becomes unavailable; native retry preserves the exact query
project catalog body stall becomes unavailable; native retry preserves the exact query
```

两条均属于 `project-catalog.spec.ts`。报告严格要求八条唯一用例实际各通过一次；缺失、仅旧六条、未知/错文件、重复、skipped、失败、flaky或retry均拒绝。沙箱、零重试、禁用only、必需browser/aggregate jobs及原签名守卫不变，不接受发现列表代替执行报告。

## 代码范围与验证

| 文件 | 作用 |
| --- | --- |
| `frontend/e2e/project-catalog-fixture.cjs`、`frontend/tests/project-catalog-fixture.test.cjs` | 真实header/body挂起、新GET恢复、严格输入及清理回归 |
| `frontend/e2e/project-catalog.spec.ts`、`frontend/e2e/playwright.config.cjs` | 两条浏览器旅程及发现范围 |
| `frontend/e2e/streaming-proxy.cjs`、`frontend/tests/streaming-proxy.test.cjs` | 固定查询显式选择、保留默认行为及流式/拒绝路径回归 |
| `frontend/scripts/check-browser-report.cjs`、`frontend/tests/browser-report.test.cjs` | 八条精确报告门禁及负向回归 |

本地实际结果：完整前端2069/2069，0失败/取消/跳过（128.18秒）；focused66/66，其中fixture8、proxy7、report51，包含真实报告CLI子进程检查；84项浏览器守卫契约；TypeScript；八条用例/三文件发现；独立审查通过。早期本地EPERM限制不再是这些合并验证的未完成项：root使用平台支持的命令权限完成检查，没有降低断言或浏览器沙箱。基于已验证main衔接时保留了上述源码内容。

这些是合成协议/报告及静态发现证据，**本包八条真实浏览器尚待精确提交CI**。已验证main只有六条，不证明新两条已运行。后续head、CI、合并和新main/provider结果必须在执行后分别记录，不通过反复提交状态记录来宣称自身未来CI通过。

## 下一包与不变边界

先发布本包并验证精确head完整CI；全绿且满足分支保护后合并，再核对新main CI和provider。随后按[浏览器阶段计划](browser-validation-stage-plan.md)进入B2有界设计，明确合成身份、真实后端授权规则和各自证据边界；设计不引入生产身份旁路、不配置真实账号或放开写入。

[项目所有者持续开发约定](https://github.com/Wang106/SoftwareLifeCycle/pull/172#issuecomment-6550487902)授权普通非付费工作默认继续，新增付费仍须批准。总体36/44=82%、B1技术阶段1/4、原有限计划8/8不变；七模块100/100演示/100演示/100/89/60/17，七计划100/100/20/33/40/40/0，业务验收增量0。公共样例只读，旧数据库不保留、不重建，真实OIDC和业务提交关闭。参照[隔离浏览器基础](isolated-browser-foundation.md)与[项目加载优先级](priority-page-loading.md)区分当前扩展和历史验收。
