const {createHash}=require('node:crypto');
const key='34567890-1234-1234-1234-123456789abc',principal='12345678-1234-1234-1234-123456789abc',target='56789012-1234-1234-1234-123456789abc',event='11111111-1234-1234-1234-123456789abc';
const fields=['request_id','entity_type','entity_id','title','location_kind','location','description','actor_name','reason'];
const command=()=>({operation:'resource',target,body:{request_id:key,actor_name:'Declared operator',reason:'Original reason 中文',entity_type:'RELEASE',entity_id:target,title:'原始标题',location_kind:'WEB_URL',location:'https://example.com/证据?q=1',description:'说明'}});
const eventNo=c=>'EVT-LK-'+c.body.request_id;
function audit(c,actor=principal){const b=c.body;return{id:event,event_no:eventNo(c),entity_id:b.request_id,entity_ref:b.request_id,
 actor_principal_id:actor,declared_actor_name:b.actor_name,event_type:'RESOURCE_LINK',entity_type:'RESOURCE_LINK',action:'REGISTER',detail:b.reason,
 payload:{actor_source:'AUTHENTICATED_PRINCIPAL',target_type:b.entity_type,target_id:c.target,target_ref:'原始版本',location_kind:b.location_kind,
 request_digest_version:1,request_sha256:createHash('sha256').update(JSON.stringify(fields.map(k=>b[k]))).digest('hex')},token:'private'};}
function receipt(c){const {request_id,...original}=c.body;return{operation:'resource',request_id,target:c.target,audit_event_no:eventNo(c),result:{id:request_id,entity_ref:'原始版本',...original}};}
module.exports={key,principal,target,event,command,eventNo,audit,receipt};
