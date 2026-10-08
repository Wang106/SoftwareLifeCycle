'use strict';
const key='34567890-1234-1234-1234-123456789abc',release='12345678-1234-1234-1234-123456789abc',
 snapshot='45678901-1234-1234-1234-123456789abc',deployment='56789012-1234-1234-1234-123456789abc',
 authorization='67890123-1234-1234-1234-123456789abc',event='78901234-1234-1234-1234-123456789abc';
const command=operation=>({operation,target:operation==='snapshot'?release:'DEP-no',body:
 operation==='snapshot'?{request_id:key}:operation==='actual'?{request_id:key,actual_release_id:release,
 actual_snapshot_id:snapshot,expected_version:4,correction_reason:'  Original correction reason  ',deployed_at:null}:
 {request_id:key,batch_no:'BATCH-原始',changeover_id:null,started_at:null,note:'Exact note\n原文'}});
const eventNo=c=>'EVT-'+({snapshot:'SN',actual:'DA',batch:'PB'}[c.operation])+'-'+c.body.request_id.replaceAll('-','');
const time=value=>value===null?null:new Date(value).toISOString().replace(/\.000Z$/,'+00:00').replace(/(\.[0-9]{3})Z$/,(_,fraction)=>fraction+'000+00:00');
function audit(c,principal=release){
 const b=c.body,result={id:event,event_no:eventNo(c),actor_principal_id:principal,
  payload:{actor_source:'AUTHENTICATED_PRINCIPAL'},subject:'private',token:'private'};
 if(c.operation==='snapshot')return {...result,event_type:'SNAPSHOT',entity_type:'RELEASE_SNAPSHOT',action:'FROZEN',entity_id:b.request_id,
  entity_ref:'SNAP-0002-'+c.target.slice(0,8),payload:{...result.payload,release_id:c.target,snapshot_number:2,
   content_hash:'a'.repeat(64),request:{release_id:c.target}}};
 if(c.operation==='actual')return {...result,event_type:'DEPLOYMENT',entity_type:'DEPLOYMENT',action:'ACTUAL_CORRECTED',entity_id:deployment,
  entity_ref:c.target,payload:{...result.payload,correction_reason:b.correction_reason,
   request:{deployment_no:c.target,actual_release_id:b.actual_release_id,actual_snapshot_id:b.actual_snapshot_id,
    deployed_at:time(b.deployed_at),expected_version:b.expected_version,correction_reason:b.correction_reason},
   before:{actual_version:b.expected_version},after:{actual_version:b.expected_version+1,status:'MISMATCH',
    actual_release_id:b.actual_release_id,actual_snapshot_id:b.actual_snapshot_id}}};
 return {...result,event_type:'PRODUCTION_BATCH',entity_type:'PRODUCTION_BATCH',action:'STARTED',entity_id:b.request_id,
  entity_ref:b.batch_no,payload:{...result.payload,deployment_id:deployment,authorization_id:authorization,
   deployment_no:c.target,changeover_id:b.changeover_id,release_id:release,snapshot_id:snapshot,status:'ACTIVE',
   request:{deployment_no:c.target,batch_no:b.batch_no,changeover_id:b.changeover_id,started_at:time(b.started_at),note:b.note}}};
}
function receipt(c){const e=audit(c);return {operation:c.operation,request_id:c.body.request_id,target:c.target,audit_event_no:eventNo(c),result:
 c.operation==='snapshot'?{id:c.body.request_id,release_id:c.target,snapshot_no:e.entity_ref,status:'FROZEN',snapshot_number:2,content_hash:'a'.repeat(64)}:
 c.operation==='actual'?{id:deployment,deployment_no:c.target,status:'MISMATCH',actual_release_id:c.body.actual_release_id,
 actual_snapshot_id:c.body.actual_snapshot_id,actual_version:c.body.expected_version+1}:
 {id:c.body.request_id,batch_no:c.body.batch_no,deployment_no:c.target,status:'ACTIVE',release_id:release,snapshot_id:snapshot}};}
module.exports={key,release,snapshot,deployment,authorization,event,command,eventNo,audit,receipt};
