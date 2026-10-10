import {validUuid} from './command-draft';
import {parseEvidenceCommand} from './evidence-command-transport';
import {record,exactFields,readCommandResponse,type FirstError} from './first-command-transport';
const decisions=['AFFECTED','NOT_AFFECTED','NEEDS_REVIEW'] as const;
type Decision=typeof decisions[number];
export type ImpactCorrectionCommand=Readonly<{
 operation:'impact-correction';target:string;
 body:Readonly<{request_id:string;actor_name:string;reason:string;release_id:string;snapshot_id:string;
   decision:Decision;evidence_ref:string|null;supersedes_id:string;correction_reason:string}>;
 predecessor:Readonly<{id:string;release_id:string;snapshot_id:string;decision:Decision}>;
}>;
/** Predecessor context is review evidence, never an extra backend field. */
export function parseImpactCorrectionCommand(value:unknown):ImpactCorrectionCommand|null {
 const d=record(value),b=record(d?.body),p=record(d?.predecessor);
 if(!d||!b||!p||!exactFields(d,['operation','target','body','predecessor'])||d.operation!=='impact-correction'||
   !exactFields(b,['request_id','actor_name','reason','release_id','snapshot_id','decision','evidence_ref','supersedes_id','correction_reason'])||
   !exactFields(p,['id','release_id','snapshot_id','decision'])||!decisions.includes(p.decision as Decision)||
   typeof b.correction_reason!=='string'||!b.correction_reason.trim()||b.correction_reason.length>4000||
   /[\uD800-\uDFFF]/u.test(b.correction_reason.replace(/[\uD800-\uDBFF][\uDC00-\uDFFF]/g,'')))return null;
 const original=parseEvidenceCommand({operation:'impact',target:d.target,body:{
   request_id:b.request_id,actor_name:b.actor_name,reason:b.reason,release_id:b.release_id,snapshot_id:b.snapshot_id,
   decision:b.decision,evidence_ref:b.evidence_ref}});
 if(!original||![p.id,p.release_id,p.snapshot_id,b.supersedes_id].every(v=>typeof v==='string'&&validUuid(v)&&v===v.toLowerCase())||
   b.supersedes_id!==p.id||original.body.request_id===p.id||original.body.release_id!==p.release_id||
   original.body.snapshot_id!==p.snapshot_id)return null;
 const command=Object.freeze({operation:'impact-correction' as const,target:original.target,
   body:Object.freeze({...original.body,supersedes_id:b.supersedes_id,correction_reason:b.correction_reason.trim()}),
   predecessor:Object.freeze({...p})}) as ImpactCorrectionCommand;
 return new TextEncoder().encode(JSON.stringify(command)).length<=8192?command:null;
}
export const impactCorrectionEvent=(c:ImpactCorrectionCommand)=>'EVT-IMPACT-'+c.body.request_id;
export const impactCorrectionPath=(c:ImpactCorrectionCommand)=>'/api/v1/issues/'+encodeURIComponent(c.target)+'/impact-assessments';
export type ImpactCorrectionReview=Readonly<{command:ImpactCorrectionCommand;confirmed:boolean}>;
export function confirmImpactCorrection(input:unknown,confirmed:boolean):ImpactCorrectionReview {
 const command=parseImpactCorrectionCommand(input);if(!command)throw Error('invalid_review');
 return Object.freeze({command,confirmed:confirmed===true});
}
export type ImpactCorrectionReceipt=Readonly<{operation:'impact-correction';request_id:string;target:string;audit_event_no:string;
 result:Readonly<Record<string,string|null>>}>;
/** Original receipt only; current judgment/readiness and successor flags are excluded. */
export function projectImpactCorrectionReceipt(value:unknown,c:ImpactCorrectionCommand):ImpactCorrectionReceipt|null {
 const d=record(value),r=record(d?.result);
 if(!d||!r||d.operation!==c.operation||d.request_id!==c.body.request_id||d.target!==c.target||
   d.audit_event_no!==impactCorrectionEvent(c)||r.id!==c.body.request_id||
   typeof r.issue_id!=='string'||!validUuid(r.issue_id)||r.issue_id!==r.issue_id.toLowerCase()||r.issue_no!==c.target||
   typeof r.snapshot_no!=='string'||!r.snapshot_no.trim()||r.snapshot_no.length>80)return null;
 const {request_id,...body}=c.body;
 const original={id:request_id,...body,previous_decision:c.predecessor.decision,issue_id:r.issue_id,
   issue_no:c.target,snapshot_no:r.snapshot_no};
 if(Object.entries(original).some(([k,v])=>r[k]!==v))return null;
 return Object.freeze({operation:c.operation,request_id,target:c.target,audit_event_no:impactCorrectionEvent(c),result:Object.freeze(original)});
}
export type ImpactCorrectionError = Exclude<FirstError, 'first_submission_disabled' | 'version_conflict'> |
  'impact_correction_disabled';
const denials: Readonly<Record<number, readonly ImpactCorrectionError[]>> = {
  400:['invalid_request'], 401:['session_required'], 403:['cross_origin_request','read_only_mode','submission_forbidden'],
  409:['request_conflict','submission_conflict'], 413:['request_too_large'],
  415:['json_required'], 422:['invalid_request'], 503:['impact_correction_disabled'],
};
export type ImpactCorrectionState = Readonly<{ phase:'idle'|'sending'|'checking'|'unknown'|'rejected'|'confirmed';
  review:ImpactCorrectionReview; command:ImpactCorrectionCommand; error:ImpactCorrectionError|null; receipt:ImpactCorrectionReceipt|null }>;
/** Memory-only original bytes; audit recovery never repeats a write. */
export class ImpactCorrectionSubmission {
  private current: ImpactCorrectionState;
  private uncertain = false;
  private readonly body: string;
  constructor(review: ImpactCorrectionReview) {
    if (review.confirmed !== true) throw Error('Confirm the exact request before sending.');
    const command = parseImpactCorrectionCommand(review.command);
    if (!command || JSON.stringify(command) !== JSON.stringify(review.command)) throw Error('invalid_review');
    const canonical = confirmImpactCorrection(command,true);
    this.body = JSON.stringify(command);
    this.current = Object.freeze({ phase:'idle', review:canonical, command, error:null, receipt:null });
  }
  get state(): ImpactCorrectionState { return this.current; }
  private update(phase:ImpactCorrectionState['phase'], error:ImpactCorrectionError|null, receipt:ImpactCorrectionReceipt|null = null) {
    this.current = Object.freeze({ ...this.current, phase, error, receipt }); return this.current;
  }
  send(enabled:boolean, fetcher:typeof fetch = fetch): Promise<ImpactCorrectionState> { return this.run('submit',enabled,fetcher); }
  recover(enabled:boolean, fetcher:typeof fetch = fetch): Promise<ImpactCorrectionState> { return this.run('recover',enabled,fetcher); }
  private async run(mode:'submit'|'recover', enabled:boolean, fetcher:typeof fetch): Promise<ImpactCorrectionState> {
    if (['sending','checking','confirmed'].includes(this.current.phase)) return this.current;
    if (mode === 'recover') this.uncertain = true;
    if (enabled !== true) return this.update(this.uncertain ? 'unknown' : 'rejected','impact_correction_disabled');
    this.update(mode === 'submit' ? 'sending' : 'checking',null);
    try {
      const response = await fetcher(mode === 'submit' ? '/auth/impact-correction' : '/auth/impact-correction-receipt', {
        method:'POST', body:this.body, headers:{'Content-Type':'application/json',Accept:'application/json'},
        credentials:'same-origin', redirect:'error', cache:'no-store', signal:AbortSignal.timeout(15000) });
      const value = await readCommandResponse(response);
      const receipt = response.status === 200 ? projectImpactCorrectionReceipt(value,this.current.command) : null;
      if (receipt) { this.uncertain = false; return this.update('confirmed',null,receipt); }
      const error = record(value)?.error;
      if (typeof error === 'string' && denials[response.status]?.includes(error as ImpactCorrectionError))
        return this.update(this.uncertain ? 'unknown' : 'rejected',error as ImpactCorrectionError);
    } catch { /* Lost responses and missing audit records do not prove absence. */ }
    this.uncertain = true; return this.update('unknown','outcome_unknown');
  }
}


