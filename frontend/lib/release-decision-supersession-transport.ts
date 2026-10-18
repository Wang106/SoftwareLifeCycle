import {validUuid} from './command-draft';
import {record,exactFields,readCommandResponse,type FirstError} from './first-command-transport';

export type ReleaseDecisionSupersessionCommand=Readonly<{
  operation:'release-decision-supersession';target:string;
  body:Readonly<{request_id:string;decision_no:string;decided_by:string;readiness_status:string;decision:string;
    notes:string|null;supersedes_id:string;correction_reason:string}>;
  predecessor:Readonly<{id:string;release_id:string;snapshot_id:string;decision_no:string;decision:string;readiness_status:string}>;
}>;
const scalar=(value:unknown,max:number,nullable=false):value is string|null=>
  nullable&&value===null||typeof value==='string'&&value===value.trim()&&value.length>0&&value.length<=max&&!/[\u0000-\u001f\u007f]/.test(value);
const uuid=(value:unknown)=>typeof value==='string'&&validUuid(value)&&value===value.toLowerCase();
export function parseReleaseDecisionSupersessionCommand(value:unknown):ReleaseDecisionSupersessionCommand|null{
  const d=record(value),b=record(d?.body),p=record(d?.predecessor);
  if(!d||!b||!p||!exactFields(d,['operation','target','body','predecessor'])||d.operation!=='release-decision-supersession'||
    !exactFields(b,['request_id','decision_no','decided_by','readiness_status','decision','notes','supersedes_id','correction_reason'])||
    !exactFields(p,['id','release_id','snapshot_id','decision_no','decision','readiness_status'])||
    !scalar(d.target,50)||!uuid(b.request_id)||!scalar(b.decision_no,50)||!scalar(b.decided_by,120)||
    !scalar(b.readiness_status,30)||!scalar(b.decision,30)||!scalar(b.notes,4000,true)||!uuid(b.supersedes_id)||
    !scalar(b.correction_reason,4000)||!uuid(p.id)||!uuid(p.release_id)||!uuid(p.snapshot_id)||
    !scalar(p.decision_no,50)||!scalar(p.decision,30)||!scalar(p.readiness_status,30)||
    b.request_id===p.id||b.supersedes_id!==p.id)return null;
  const command=Object.freeze({operation:'release-decision-supersession' as const,target:d.target as string,
    body:Object.freeze({...b}) as ReleaseDecisionSupersessionCommand['body'],
    predecessor:Object.freeze({...p}) as ReleaseDecisionSupersessionCommand['predecessor']});
  return new TextEncoder().encode(JSON.stringify(command)).length<=8192?command:null;
}
export const releaseDecisionSupersessionEvent=(c:ReleaseDecisionSupersessionCommand)=>'EVT-RD-'+c.body.request_id.replaceAll('-','');
export const releaseDecisionSupersessionPath=(c:ReleaseDecisionSupersessionCommand)=>'/api/v1/approvals/'+encodeURIComponent(c.target)+'/release-decision';
export type ReleaseDecisionSupersessionReview=Readonly<{command:ReleaseDecisionSupersessionCommand;confirmed:boolean}>;
export function confirmReleaseDecisionSupersession(input:unknown,confirmed:boolean):ReleaseDecisionSupersessionReview{
  const command=parseReleaseDecisionSupersessionCommand(input);if(!command)throw Error('invalid_review');
  return Object.freeze({command,confirmed:confirmed===true});
}
export type ReleaseDecisionSupersessionReceipt=Readonly<{operation:'release-decision-supersession';request_id:string;target:string;
  audit_event_no:string;result:Readonly<Record<string,string|null>>}>;
export function projectReleaseDecisionSupersessionReceipt(value:unknown,c:ReleaseDecisionSupersessionCommand):ReleaseDecisionSupersessionReceipt|null{
  const d=record(value),r=record(d?.result),b=c.body,p=c.predecessor;
  if(!d||!r||d.operation!==c.operation||d.request_id!==b.request_id||d.target!==c.target||
    d.audit_event_no!==releaseDecisionSupersessionEvent(c)||r.id!==b.request_id||r.approval_no!==c.target||
    r.decision_no!==b.decision_no||r.decision!==b.decision||r.readiness_status!==b.readiness_status||
    r.release_id!==p.release_id||r.snapshot_id!==p.snapshot_id||r.supersedes_id!==p.id||
    r.correction_reason!==b.correction_reason||!uuid(r.approval_id)||!scalar(r.snapshot_no,80)||
    typeof r.content_hash!=='string'||!/^[0-9a-f]{64}$/.test(r.content_hash))return null;
  const result={id:b.request_id,approval_id:r.approval_id as string,approval_no:c.target,decision_no:b.decision_no,
    decision:b.decision,readiness_status:b.readiness_status,release_id:p.release_id,snapshot_id:p.snapshot_id,
    snapshot_no:r.snapshot_no as string,content_hash:r.content_hash as string,supersedes_id:p.id,
    correction_reason:b.correction_reason,predecessor_decision_no:p.decision_no};
  return Object.freeze({operation:c.operation,request_id:b.request_id,target:c.target,
    audit_event_no:releaseDecisionSupersessionEvent(c),result:Object.freeze(result)});
}
export type ReleaseDecisionSupersessionError=Exclude<FirstError,'first_submission_disabled'|'version_conflict'>|'release_decision_supersession_disabled';
const denials:Readonly<Record<number,readonly ReleaseDecisionSupersessionError[]>>={400:['invalid_request'],401:['session_required'],
  403:['cross_origin_request','read_only_mode','submission_forbidden'],409:['request_conflict','submission_conflict'],
  413:['request_too_large'],415:['json_required'],422:['invalid_request'],503:['release_decision_supersession_disabled']};
export type ReleaseDecisionSupersessionState=Readonly<{phase:'idle'|'sending'|'checking'|'unknown'|'rejected'|'confirmed';
  review:ReleaseDecisionSupersessionReview;command:ReleaseDecisionSupersessionCommand;
  error:ReleaseDecisionSupersessionError|null;receipt:ReleaseDecisionSupersessionReceipt|null}>;
export class ReleaseDecisionSupersessionSubmission{
  private current:ReleaseDecisionSupersessionState;private uncertain=false;private readonly body:string;
  constructor(review:ReleaseDecisionSupersessionReview){if(review.confirmed!==true)throw Error('Confirm the exact request before sending.');
    const command=parseReleaseDecisionSupersessionCommand(review.command);if(!command||JSON.stringify(command)!==JSON.stringify(review.command))throw Error('invalid_review');
    const canonical=confirmReleaseDecisionSupersession(command,true);this.body=JSON.stringify(command);
    this.current=Object.freeze({phase:'idle',review:canonical,command,error:null,receipt:null});}
  get state(){return this.current;}
  private update(phase:ReleaseDecisionSupersessionState['phase'],error:ReleaseDecisionSupersessionError|null,receipt:ReleaseDecisionSupersessionReceipt|null=null){
    this.current=Object.freeze({...this.current,phase,error,receipt});return this.current;}
  send(enabled:boolean,fetcher:typeof fetch=fetch){return this.run('submit',enabled,fetcher);}
  recover(enabled:boolean,fetcher:typeof fetch=fetch){return this.run('recover',enabled,fetcher);}
  private async run(mode:'submit'|'recover',enabled:boolean,fetcher:typeof fetch):Promise<ReleaseDecisionSupersessionState>{
    if(['sending','checking','confirmed'].includes(this.current.phase))return this.current;if(mode==='recover')this.uncertain=true;
    if(enabled!==true)return this.update(this.uncertain?'unknown':'rejected','release_decision_supersession_disabled');
    this.update(mode==='submit'?'sending':'checking',null);
    try{const response=await fetcher(mode==='submit'?'/auth/release-decision-supersession':'/auth/release-decision-supersession-receipt',
      {method:'POST',body:this.body,headers:{'Content-Type':'application/json',Accept:'application/json'},credentials:'same-origin',
        redirect:'error',cache:'no-store',signal:AbortSignal.timeout(15000)});
      const value=await readCommandResponse(response);const receipt=response.status===200?projectReleaseDecisionSupersessionReceipt(value,this.current.command):null;
      if(receipt){this.uncertain=false;return this.update('confirmed',null,receipt);}const error=record(value)?.error;
      if(typeof error==='string'&&denials[response.status]?.includes(error as ReleaseDecisionSupersessionError))
        return this.update(this.uncertain?'unknown':'rejected',error as ReleaseDecisionSupersessionError);
    }catch{}this.uncertain=true;return this.update('unknown','outcome_unknown');
  }
}
