import {validUuid} from './command-draft';
import {record,exactFields,readCommandResponse,type FirstError} from './first-command-transport';

const decisions=['AFFECTED','NOT_AFFECTED','NEEDS_REVIEW'] as const;
type Decision=typeof decisions[number];
export type ImpactWithdrawalCommand=Readonly<{
  operation:'impact-withdrawal';target:string;
  body:Readonly<{request_id:string;actor_name:string;reason:string;release_id:string;snapshot_id:string;
    supersedes_id:string;correction_reason:string}>;
  predecessor:Readonly<{id:string;release_id:string;snapshot_id:string;decision:Decision}>;
}>;

const text=(value:unknown,max:number)=>typeof value==='string'&&!!value.trim()&&value.length<=max&&
  !/[\uD800-\uDFFF]/u.test(value.replace(/[\uD800-\uDBFF][\uDC00-\uDFFF]/g,''));

export function parseImpactWithdrawalCommand(value:unknown):ImpactWithdrawalCommand|null {
  const d=record(value),b=record(d?.body),p=record(d?.predecessor);
  if(!d||!b||!p||!exactFields(d,['operation','target','body','predecessor'])||d.operation!=='impact-withdrawal'||
    !exactFields(b,['request_id','actor_name','reason','release_id','snapshot_id','supersedes_id','correction_reason'])||
    !exactFields(p,['id','release_id','snapshot_id','decision'])||!decisions.includes(p.decision as Decision)||
    typeof d.target!=='string'||d.target!==d.target.trim()||!text(d.target,50)||!text(b.actor_name,120)||!text(b.reason,4000)||!text(b.correction_reason,4000))return null;
  if(![b.request_id,b.release_id,b.snapshot_id,b.supersedes_id,p.id,p.release_id,p.snapshot_id]
    .every(v=>typeof v==='string'&&validUuid(v)&&v===v.toLowerCase())||b.request_id===p.id||b.supersedes_id!==p.id||
    b.release_id!==p.release_id||b.snapshot_id!==p.snapshot_id)return null;
  const command=Object.freeze({operation:'impact-withdrawal' as const,target:d.target.trim(),body:Object.freeze({
    request_id:b.request_id as string,actor_name:(b.actor_name as string).trim(),reason:(b.reason as string).trim(),
    release_id:b.release_id as string,snapshot_id:b.snapshot_id as string,supersedes_id:b.supersedes_id as string,
    correction_reason:(b.correction_reason as string).trim()}),predecessor:Object.freeze({...p})}) as ImpactWithdrawalCommand;
  return new TextEncoder().encode(JSON.stringify(command)).length<=8192?command:null;
}
export const impactWithdrawalEvent=(c:ImpactWithdrawalCommand)=>'EVT-IMPACT-'+c.body.request_id;
export const impactWithdrawalPath=(c:ImpactWithdrawalCommand)=>'/api/v1/issues/'+encodeURIComponent(c.target)+'/impact-withdrawals';
export type ImpactWithdrawalReview=Readonly<{command:ImpactWithdrawalCommand;confirmed:boolean}>;
export function confirmImpactWithdrawal(input:unknown,confirmed:boolean):ImpactWithdrawalReview {
  const command=parseImpactWithdrawalCommand(input);if(!command)throw Error('invalid_review');
  return Object.freeze({command,confirmed:confirmed===true});
}
export type ImpactWithdrawalReceipt=Readonly<{operation:'impact-withdrawal';request_id:string;target:string;audit_event_no:string;
  result:Readonly<Record<string,string|number|null>>}>;
export function projectImpactWithdrawalReceipt(value:unknown,c:ImpactWithdrawalCommand):ImpactWithdrawalReceipt|null {
  const d=record(value),r=record(d?.result),b=c.body;
  if(!d||!r||d.operation!==c.operation||d.request_id!==b.request_id||d.target!==c.target||
    d.audit_event_no!==impactWithdrawalEvent(c)||r.id!==b.request_id||r.action!=='WITHDRAW'||r.decision!==null||r.evidence_ref!==null||
    r.after_withdrawal_id!==null||r.superseded_by_id!==null||typeof r.context_seq!=='number'||!Number.isSafeInteger(r.context_seq)||r.context_seq<1||
    typeof r.issue_id!=='string'||!validUuid(r.issue_id)||r.issue_id!==r.issue_id.toLowerCase()||r.issue_no!==c.target||
    typeof r.snapshot_no!=='string'||!r.snapshot_no.trim()||r.snapshot_no.length>80)return null;
  const expected={release_id:b.release_id,snapshot_id:b.snapshot_id,supersedes_id:b.supersedes_id,actor_name:b.actor_name,
    reason:b.reason,correction_reason:b.correction_reason,previous_decision:c.predecessor.decision};
  if(Object.entries(expected).some(([k,v])=>r[k]!==v))return null;
  const result:Record<string,string|number|null>={id:b.request_id,action:'WITHDRAW',context_seq:r.context_seq as number,
    after_withdrawal_id:null,decision:null,evidence_ref:null,superseded_by_id:null,issue_id:r.issue_id as string,issue_no:c.target,
    snapshot_no:r.snapshot_no as string,...expected};
  return Object.freeze({operation:c.operation,request_id:b.request_id,target:c.target,audit_event_no:impactWithdrawalEvent(c),result:Object.freeze(result)});
}
export type ImpactWithdrawalError=Exclude<FirstError,'first_submission_disabled'|'version_conflict'>|'impact_withdrawal_disabled';
const denials:Readonly<Record<number,readonly ImpactWithdrawalError[]>>={400:['invalid_request'],401:['session_required'],403:['cross_origin_request','read_only_mode','submission_forbidden'],409:['request_conflict','submission_conflict'],413:['request_too_large'],415:['json_required'],422:['invalid_request'],503:['impact_withdrawal_disabled']};
export type ImpactWithdrawalState=Readonly<{phase:'idle'|'sending'|'checking'|'unknown'|'rejected'|'confirmed';review:ImpactWithdrawalReview;command:ImpactWithdrawalCommand;error:ImpactWithdrawalError|null;receipt:ImpactWithdrawalReceipt|null}>;

export class ImpactWithdrawalSubmission {
  private current:ImpactWithdrawalState;private uncertain=false;private readonly body:string;
  constructor(review:ImpactWithdrawalReview){if(review.confirmed!==true)throw Error('Confirm the exact request before sending.');const command=parseImpactWithdrawalCommand(review.command);if(!command||JSON.stringify(command)!==JSON.stringify(review.command))throw Error('invalid_review');const canonical=confirmImpactWithdrawal(command,true);this.body=JSON.stringify(command);this.current=Object.freeze({phase:'idle',review:canonical,command,error:null,receipt:null});}
  get state(){return this.current;}
  private update(phase:ImpactWithdrawalState['phase'],error:ImpactWithdrawalError|null,receipt:ImpactWithdrawalReceipt|null=null){this.current=Object.freeze({...this.current,phase,error,receipt});return this.current;}
  send(enabled:boolean,fetcher:typeof fetch=fetch){return this.run('submit',enabled,fetcher);}
  recover(enabled:boolean,fetcher:typeof fetch=fetch){return this.run('recover',enabled,fetcher);}
  private async run(mode:'submit'|'recover',enabled:boolean,fetcher:typeof fetch):Promise<ImpactWithdrawalState>{
    if(['sending','checking','confirmed'].includes(this.current.phase))return this.current;if(mode==='recover')this.uncertain=true;
    if(enabled!==true)return this.update(this.uncertain?'unknown':'rejected','impact_withdrawal_disabled');
    this.update(mode==='submit'?'sending':'checking',null);
    try{const response=await fetcher(mode==='submit'?'/auth/impact-withdrawal':'/auth/impact-withdrawal-receipt',{method:'POST',body:this.body,headers:{'Content-Type':'application/json',Accept:'application/json'},credentials:'same-origin',redirect:'error',cache:'no-store',signal:AbortSignal.timeout(15000)});const value=await readCommandResponse(response);const receipt=response.status===200?projectImpactWithdrawalReceipt(value,this.current.command):null;if(receipt){this.uncertain=false;return this.update('confirmed',null,receipt);}const error=record(value)?.error;if(typeof error==='string'&&denials[response.status]?.includes(error as ImpactWithdrawalError))return this.update(this.uncertain?'unknown':'rejected',error as ImpactWithdrawalError);}catch{}
    this.uncertain=true;return this.update('unknown','outcome_unknown');
  }
}
