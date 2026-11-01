# PR172：官方 Chrome PKG 候选与验证边界

本包解决现有浏览器 CI 的候选来源阻塞，仍在 PR172 上继续。它不恢复已过期数据库，不改变真实身份/写入开关，也不增加业务验收完成数。

[项目所有者最新约定](https://github.com/Wang106/SoftwareLifeCycle/pull/172#issuecomment-6550487902)允许除新增付费外的项目内工作默认继续，每轮结束立即衔接下一个明确小包。旧文档的非付费单次许可、等待批准或等待“继续”要求已被覆盖；严格门禁、分支保护及实际证据要求保留。

## 已核对的失败与新来源

核验基线 main `00b92aa40860feaea4a712926fed56854be842cf`，PR172 前一 head `af27f608c0f2ddca88d8455df991e265f65ab7a1`。[CI41239803373](https://github.com/Wang106/SoftwareLifeCycle/actions/runs/41239803373) attempt1 已结束失败：57 项契约、2846 后端＋26 子测试（296 PG 无跳过）、2048 前端通过；CfT 严格验签报 `code has no resources but signature indicates they must be present`。六条浏览器用例未执行，聚合失败。PR 仍为草稿；同 head 的 Preview 成功不替代浏览器或生产验收。

本地只读静态检查取得与失败 CI 完全相同的 CfT ZIP：195027080 字节，SHA256 `8bc590d1b1acac042a000234c768f31830f25a3983a83ed5e067114c87c4cad1`。673 条归档记录中没有 CodeResources 或 `_CodeSignature` 目录；主 Mach-O 的签名 SuperBlob 仅含 CodeDirectory，flags `0x20002`（ad-hoc、linker-signed），没有 CMS 签名槽。这个确切包无法提供现有门禁要求的 Google Developer ID 证书签名；不再重试相同来源。该结果不解释旧 DMG 的 FinderInfo 来源，也不应推广为所有版本/平台 CfT 的结论。

新候选采用 Google 文档提供的普通 Chrome Universal PKG。固定下载入口为：

```text
https://dl.google.com/chrome/mac/stable/accept_tos%3Dhttps%253A%252F%252Fwww.google.com%252Fintl%252Fen_ph%252Fchrome%252Fterms%252F%26_and_accept_tos%3Dhttps%253A%252F%252Fpolicies.google.com%252Fterms/googlechrome.pkg
```

| 固定项 | 本次静态观察 |
| --- | --- |
| SHA256 | `cdbcf73ec1bea87cd30af84ac98456781f78fafcafdfa70aafffa0135713b00a` |
| 字节数 | `268605843` |
| 应用版本 | `156.0.8078.80`，CFBundleVersion `8078.80` |
| 应用标识 | `com.google.Chrome` |
| 安装包叶证书 | `Developer ID Installer: Google LLC (EQHXZ8M8AV)` |
| 证书链元数据 | Developer ID Certification Authority → Apple Root CA |
| 组件/负载路径 | `GoogleChrome.pkg/Payload/Google Chrome.app` |

该入口随 Stable 更新；代码同时固定本次摘要和版本。上游内容变化时必须失败并形成新的可核验候选，不能默默采用不同包。

静态读取 XAR、pbzx 和 cpio 数据，没有执行安装脚本或 Chrome：741 条 cpio 记录中有 23 个以 `/CodeResources` 结尾的路径（包括资源封印及其链接名），未发现 AppleDouble `._` 文件名。顶层 `Contents/_CodeSignature/CodeResources` 为24708字节，SHA256 `685d3ee1650c3b608759c322101d15b27691a3b008a1ded7319390fee5bb9179`。主程序为包含多架构切片的 Mach-O；Info.plist 与上表一致。包内确有安装脚本，仅作为归档数据读取。

证书文本、资源文件存在和摘要匹配都不是原生签名信任结果。未发现 AppleDouble 文件名也不证明展开后没有 xattrs；当前 Linux Work 环境不能执行 Apple 的原生信任检查。PKG 是否能原封展开并通过严格验签，必须由本包精确提交的 macOS CI 证明。

## 执行顺序与停止条件

正常 CI 使用 `scripts/ci/prepare_pkg_browser.py`。固定新目录为 `$RUNNER_TEMP/slc-pkg-chrome`；已有目录拒绝复用。

1. 校验 macOS ARM64 环境和临时目录。按固定 HTTPS URL 有界下载，拒绝重定向、重试和替代来源；校验固定字节数及 SHA256。
2. 先调用 `/usr/sbin/pkgutil --check-signature`，要求成功状态、系统信任及完整匹配的 Google Developer ID Installer / Apple 链。未签名、不可信、身份不符或未知输出均停止。
3. 仅调用 `/usr/sbin/pkgutil --expand-full` 展开到新目录。不得调用 `installer`、执行 Distribution JavaScript、preinstall/postinstall，或安装到系统 `/Applications`。
4. 只接受 `$RUNNER_TEMP/slc-pkg-chrome/expanded/GoogleChrome.pkg/Payload/Google Chrome.app`。检查成员所有权、写权限与链接范围；再对展开后的应用保留 `codesign --verify --deep --strict`、Apple anchor、Google Developer ID Application / Team `EQHXZ8M8AV` 和普通 Chrome 标识要求。资源封印存在性不能替代密码学验证。
5. 应用版本、固定可执行文件路径及 Playwright 配置一致后，才允许执行该二进制的 `--version`。随后仍使用原有隔离构建、六条只读合成浏览器用例和严格报告检查。

任一步失败都会使浏览器 job 和聚合验收失败。没有清除 xattr、chmod 修复、重签名、拷贝后修复、安装脚本或备用浏览器路径。浏览器 `chromiumSandbox=true`、`retries=0`，必需 browser/aggregate job 和分支保护保持。安装包信任不能替代内部应用的严格签名。

历史 `prepare_cft_browser.py` 及其合成回归保留，但不再是正常 CI 选用的来源。独立 `browser-diagnostics.yml` 仍仅手动触发且诊断后故意失败；本包不调度它，也不把它算作浏览器验收。

## 证据口径与后续

标准库契约通过 `python -m unittest discover -s scripts/ci/tests -v` 自动进入现有 backend CI。新增 PKG 契约仅使用合成文件和模拟原生命令，用于验证拒绝路径及执行顺序；本地通过不等于真实 Mac 签名或沙箱可运行。本包本地及独立复核84项契约通过（原57项＋新增27项）；工作流非候选 jobs 和 Playwright 除固定路径外的属性比对保持一致。本包精确 head 的完整 CI、Preview 结果仍须执行后分别记录，不能复用前一 head 的成功标识。

下一步先核对同一 PR 新提交的完整验收。失败时保留证据并处理明确原因，不盲重跑同一失败路径；全部必需检查通过并满足保护规则后才合并，再单独核对 main CI 与 provider 部署。然后立即衔接下一明确小包。总体36/44=82%、B1技术1/4、有限计划8/8不变，业务增量0；本包不自动进入 B2，不重建旧库，不启用真实身份或业务写入。

## 来源

- [Google：Mac Universal Installer](https://support.google.com/chrome/a/answer/9020580?hl=en)及[PKG 部署下载入口](https://support.google.com/chrome/a/answer/9915669?hl=en)。
- [Apple：Resolving common notarization issues](https://developer.apple.com/documentation/security/resolving-common-notarization-issues)，安装包签名与应用严格签名分别检查。
- [Chromium 固定版本打包源码](https://github.com/chromium/chromium/blob/fb096c0011f9d50f0a264a9376420cdea9c421e3/chrome/installer/mac/signing/pipeline.py)，包含已签名 app、组件布局、安装脚本及 installer identity 打包过程。源码支持候选布局判断，不代替本次包的原生验证。
- [pkgutil 手册镜像](https://keith.github.io/xcode-man-pages/pkgutil.1.html)，说明 `--check-signature` 与 `--expand-full`。镜像不是 Apple 官方托管；手册未承诺完整 xattr/ACL 保真，不能由此宣称 FinderInfo 问题已解决。
