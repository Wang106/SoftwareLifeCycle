# CI 后云端部署
更新：2026-10-08；Codex。

## 实现
已有 ci.yml 在PR/main push验证后端、PostgreSQL16、迁移、前端及Cloudflare生产构建。deploy.yml 仅响应成功的 main push CI；拒绝PR CI触发；固定 checkout 到通过测试的 SHA，忽略启动时已经落后于 main 的提交；GitHub ubuntu runner 执行。Cloudflare部署保留运行变量；Render API请求指定 commitId，输出部署ID，不将请求接受误报为上线成功。失败时Actions变红，禁止忽略失败。跨提供方部署不是原子事务；Cloudflare成功而Render失败需要按目标版本回滚或修复。

## 启用前配置
GitHub Settings → Environments → demo：
- secrets：CLOUDFLARE_API_TOKEN（目标Worker最小部署权限）、CLOUDFLARE_ACCOUNT_ID、RENDER_API_KEY。
- repository/environment variables：RENDER_SERVICE_ID（当前测试API的srv- ID）、SLC_DEPLOY_ENABLED=true。
变量启用与凭据可用性本次未核验；默认不开启，缺失凭据时启用后的工作流失败，不伪报成功。不得把公司数据库密钥写入GitHub代码/报告。
确认Render服务链接本仓库，commitId为同一仓库可部署提交。保持测试服务只读、样例数据、OIDC关闭及离线operator关闭。

## 避免绕过门禁
现有 Render/Cloudflare 提供方 Git自动部署与Actions独立。迁移到Actions主导前，关闭对应生产自动部署，或配置等价CI后部署规则；先确认Actions凭据和部署可用，再切换，避免中断。Cloudflare PR Preview可以保留但不能当生产验收。
本次没有更改提供方控制台设置、branch protection或创建云端Codex任务，故不能称全部部署已受CI门禁保护。

## 验收与回滚
1. 新main提交CI失败时，deploy不得运行；PR即使CI通过也不得生产部署。
2. main push CI通过后，核对checkout SHA、Cloudflare version和Render deploy commitId。
3. 等Render状态live，确认 /health/ready 的版本/schema；核对前端中英文及禁用认证路由，验证公共写入仍403。
4. 保存run链接、版本、探针日期；失败/1010分开记录客户端与应用状态，不削弱访问规则来获取绿灯。
5. 回滚使用已验证旧commit，重新走测试后部署；数据库迁移回滚需先核对兼容性/备份，不自动破坏数据。
本流程当前尚缺真实凭据运行、提供方门禁切换、live轮询与自动探针、恢复演练。ops-release里程碑不因此完成。
