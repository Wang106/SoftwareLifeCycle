import 'server-only';
import {record,exactFields} from './first-command-transport';
import {validUuid} from './command-draft';
import {projectHistoricalAdminStatusReceipt,type AdminStatusRecoveryCommand,type HistoricalAdminStatusReceipt} from './admin-status-recovery';
/** Original immutable status occurrence, never current state or a replayed write response. */
export function projectAdminStatusAudit(value:unknown,c:AdminStatusRecoveryCommand,actorId:string):HistoricalAdminStatusReceipt|null{
 const d=record(value),p=record(d?.payload),principal=c.kind==='PRINCIPAL',global=c.kind==='GLOBAL';
 const event=principal?'PRINCIPAL_STATUS_CHANGED':global?'GLOBAL_ROLE_STATUS_CHANGED':'MEMBERSHIP_STATUS_CHANGED',entity=principal?'SECURITY_PRINCIPAL':global?'GLOBAL_ROLE':c.kind+'_MEMBERSHIP';
 const action=principal?(c.status==='DISABLED'?'DISABLE':'ENABLE'):(c.status==='SUSPENDED'?'SUSPEND':'RESUME');
 if(!d||!p||typeof d.id!=='string'||!validUuid(d.id)||!validUuid(actorId)||d.actor_principal_id!==actorId||d.declared_actor_name!==null||d.event_no!==c.event_no||d.event_type!==event||d.entity_type!==entity||d.entity_id!==c.id||d.entity_ref!==c.id||d.action!==action)return null;
 const expected={...(principal?{principal_id:c.id}:global?{grant_id:c.id,principal_id:c.principal_id,role:c.role}:{scope:c.kind,membership_id:c.id,principal_id:c.principal_id,scope_id:p.scope_id,role:c.role}),expected_status:c.expected_status,status:c.status,reason:c.reason,...(principal?{revoked_browser_sessions:p.revoked_browser_sessions}:{})};
 if(!exactFields(p,Object.keys(expected))||Object.entries(expected).some(([key,value])=>p[key]!==value))return null;
 return projectHistoricalAdminStatusReceipt({kind:c.kind,id:c.id,audit_event_no:c.event_no,expected_status:c.expected_status,applied_status:c.status,...(principal?{revoked_browser_sessions:p.revoked_browser_sessions}:{principal_id:c.principal_id,role:c.role,...(global?{}:{scope_id:p.scope_id})})},c);
}
