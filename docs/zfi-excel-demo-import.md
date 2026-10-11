# ZFI Excel 演示导入检查点

用户授权2026-10-12导入脱敏Excel。清单按已读取并核对的单元格恢复，2供应商/2产品/2客户/4项目/4SSR/16ASR。A7 z按cBMS-24x/v3.8.7更正SSR02；无主体M22忽略。运行目录恢复后原附件字节不可用，未伪造原Excel文件哈希；清单另有规范化哈希用于事务幂等性。

公开测试库保持只读，OIDC与真实提交关闭，保持免费。导入尚未执行；既有0023唯一性不支持同产品同版本不同客户，必须增量迁移和真实PG/完整CI后再合并上线。不能改版本号或虚构额外产品绕过约束。

组件/测试空白不造证据；仅审批合成已明确授权。15审批通过/3处理中/1退回/1拒绝，20条Release仍DRAFT，不生成正式RELEASE。发布日期保存为用户给定的元数据，不冒充导入/签署时间。原审批/快照/审计不改写。

下一步：客户scope迁移、事务幂等导入、固定20UUID只读回执，PG并发/升级降级/原历史保留测试；通过精确head三个CI后合并，再在免费测试API显式opt-in启动导入，核验健康/数量/UUID目录和页面。


## 执行与核验

```sh
python -m alembic upgrade head
python -m app.seed_zfi_demo --sample-only
```

免费Render服务通过已有entrypoint运行：合并通过CI后设置SEED_ZFI_DEMO=true及READ_ONLY_MODE=true（保留其他变量），触发部署；迁移后先导入再启动API。不需要收费Shell/one-off job。默认开关关闭；重复启动验证回执与完整家族、不覆盖历史。

GET /health/ready必须0024 ready；GET /api/v1/demo/zfi-import必须initialized=true/20items。已有 /releases/standard、/releases/application、/suppliers、/customers、/projects、/approvals读取实际领域对象。各ASR详情使用精确UUID，不能仅凭重复版本选择客户。检查20审批/80节点和独立原始审计；空组件/测试保持NOT_READY。

迁移仅补新字段，旧NULL唯一性保留；scopedASR验证客户/项目/同产品STANDARD，scope不可改。有scoped记录拒绝降级，不删除历史规避。完整精确CI/main/provider分别核验，skipped不等于成功。
