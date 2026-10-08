# 管理员授权详情和状态历史 UI — 2026-10-08
模式：Codex。新增 /account/grants/[scope]/[id]，目录授权UUID链接进入。
支持GLOBAL/PROJECT/SOFTWARE精确UUID详情及独立10条历史分页。每次复核服务器会话，再由后端对详情和历史各自进行PLATFORM_ADMIN授权。错误scope/UUID/offset在私有请求前拒绝；401/403/404/不可用独立呈现；错误详情不再查询历史。
响应验证scope、授权UUID、coverage和分页；白名单投影详情与事件，凭据/任意payload不传UI。详情保持16KiB、10条历史使用32KiB流式限制、超时、无缓存/无重定向。允许历史旧值null并显示未知，500字符原因和截断标记。
详情和历史是独立读取，不强制两次current_status相等以误判并发。页面显示两个状态及提示。只展示状态事件；零历史不代表从未修改，不宣称完整管理历史或固定时点导出。
默认中文/English；React转义记录文本；没有管理写入。新增6行为回归及页面本地化覆盖，完整CI/Worker构建证据另记录。角色人员由用户自行指定，SSO待定，内网无外网；见internal-browser-acceptance.md。
身份管理里程碑仍不完整，所有百分比保持；下一包受控管理请求/确认和后续真实内网身份验收。
