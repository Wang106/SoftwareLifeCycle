'use strict';
const key='34567890-1234-1234-1234-123456789abc',principal='12345678-1234-1234-1234-123456789abc',
 packageId='23456789-1234-1234-1234-123456789abc',distribution='45678901-1234-1234-1234-123456789abc',
 release='56789012-1234-1234-1234-123456789abc',snapshot='67890123-1234-1234-1234-123456789abc',
 customer='78901234-1234-1234-1234-123456789abc',project='89012345-1234-1234-1234-123456789abc',
 artifact='90123456-1234-1234-1234-123456789abc',artifact2='01234567-1234-1234-1234-123456789abc',event='11111111-1234-1234-1234-123456789abc';
const command=operation=>({operation,target:operation==='delivery'?release:operation==='distribution'?packageId:distribution,
 body:operation==='delivery'?{request_id:key,release_id:release,package_no:'PKG-原始',revision:2,recipient_type:'CUSTOMER',
  recipient_code:'  CUST-原始  ',purpose:'  PRODUCTION  ',snapshot_artifact_ids:[artifact2,artifact],created_by:'  Declared creator  '}:
 operation==='distribution'?{request_id:key,delivery_package_id:packageId,distribution_no:'DS-原始',recipient_type:'CUSTOMER',recipient_code:'  CUST-原始  '}:
 {request_id:key,release_id:release,distribution_id:distribution,authorization_no:'PA-原始',customer_id:customer,project_id:project,
  site_code:'  SITE-原始  ',line_code:'  LINE-原始  ',purpose:'  PRODUCTION  ',batch_limit:2,restriction_note:'Original restriction\n原文'}});
const eventNo=c=>'EVT-'+(c.operation==='delivery'?'DP':c.operation==='distribution'?'DS':'PA')+'-'+c.body.request_id.replaceAll('-','');
function audit(c,actor=principal){const b=c.body,{request_id,...request}=b,p={actor_source:'AUTHENTICATED_PRINCIPAL',request,release_id:release,snapshot_id:snapshot};
 const e={id:event,event_no:eventNo(c),actor_principal_id:actor,entity_id:b.request_id,action:'CREATED',token:'private',subject:'private'};
 return c.operation==='delivery'?{...e,event_type:'DELIVERY',entity_type:'DELIVERY_PACKAGE',entity_ref:b.package_no,payload:{...p,
  revision:b.revision,snapshot_no:'SNAP-0001-'+release.slice(0,8),decision_no:'RD-原始',approval_no:'APR-原始',recipient_type:b.recipient_type,
  recipient_code:b.recipient_code,purpose:b.purpose,status:'READY',snapshot_artifact_ids:[...b.snapshot_artifact_ids]}}:
 c.operation==='distribution'?{...e,event_type:'DISTRIBUTION',entity_type:'DISTRIBUTION',entity_ref:b.distribution_no,payload:{...p,
  delivery_package_id:b.delivery_package_id,package_no:'PKG-原始',revision:2,recipient_type:b.recipient_type,recipient_code:b.recipient_code,status:'READY'}}:
 {...e,event_type:'AUTHORIZATION',entity_type:'SOFTWARE_AUTHORIZATION',entity_ref:b.authorization_no,detail:b.restriction_note,payload:{...p,
  distribution_id:b.distribution_id,distribution_no:'DS-原始',delivery_package_id:packageId,package_no:'PKG-原始',revision:2,
  customer_id:b.customer_id,project_id:b.project_id,site_code:b.site_code,line_code:b.line_code,purpose:b.purpose,batch_limit:b.batch_limit,status:'DRAFT'}};
}
function receipt(c){const b=c.body,p=audit(c).payload,common={id:b.request_id,status:p.status,release_id:p.release_id,snapshot_id:p.snapshot_id};
 return{operation:c.operation,request_id:b.request_id,target:c.target,audit_event_no:eventNo(c),result:
 c.operation==='delivery'?{...common,package_no:b.package_no,revision:b.revision,snapshot_no:p.snapshot_no,decision_no:p.decision_no,approval_no:p.approval_no,
  recipient_type:b.recipient_type,recipient_code:b.recipient_code,purpose:b.purpose,snapshot_artifact_ids:[...b.snapshot_artifact_ids]}:
 c.operation==='distribution'?{...common,distribution_no:b.distribution_no,delivery_package_id:b.delivery_package_id,package_no:p.package_no,revision:p.revision,
  recipient_type:b.recipient_type,recipient_code:b.recipient_code}:
 {...common,authorization_no:b.authorization_no,distribution_id:b.distribution_id,distribution_no:p.distribution_no,delivery_package_id:p.delivery_package_id,
  package_no:p.package_no,revision:p.revision,customer_id:b.customer_id,project_id:b.project_id,site_code:b.site_code,line_code:b.line_code,
  purpose:b.purpose,batch_limit:b.batch_limit,restriction_note:b.restriction_note}};
}
module.exports={key,principal,packageId,distribution,release,snapshot,customer,project,artifact,artifact2,event,command,eventNo,audit,receipt};
