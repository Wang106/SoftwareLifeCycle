import {validUuid} from './command-draft';
import {parseEvidenceCommand} from './evidence-command-transport';
import {record,exactFields,readCommandResponse,type FirstError} from './first-command-transport';

export type AcceptanceCorrectionCommand=Readonly<{
  operation:'acceptance-correction';target:string;
  body:Readonly<{request_id:string;actor_name:string;reason:string;criterion_id:string;dvp_item_id:string;action:'SUPERSEDE'|'WITHDRAW';supersedes_id:string}>;
  predecessor:Readonly<{id:string;criterion_id:string;dvp_item_id:string;action:'ASSIGN'|'SUPERSEDE'}>;
}>;
/** The predecessor is review context, never an extra backend payload field. */
export function parseAcceptanceCorrectionCommand(value:unknown):AcceptanceCorrectionCommand|null {
  const d=record(value),b=record(d?.body),p=record(d?.predecessor);
  if(!d || !b || !p || !exactFields(d,['operation','target','body','predecessor']) ||
    d.operation!=='acceptance-correction' || !exactFields(b,['request_id','actor_name','reason','criterion_id','dvp_item_id','action','supersedes_id']) ||
    !exactFields(p,['id','criterion_id','dvp_item_id','action']) ||
    !['SUPERSEDE','WITHDRAW'].includes(b.action as string) || !['ASSIGN','SUPERSEDE'].includes(p.action as string) ||
    !Object.values(p).every(v=>typeof v==='string') || typeof b.supersedes_id!=='string')return null;
  const original=parseEvidenceCommand({operation:'acceptance',target:d.target,body:{
    request_id:b.request_id,actor_name:b.actor_name,reason:b.reason,criterion_id:b.criterion_id,dvp_item_id:b.dvp_item_id}});
  if(!original || ![p.id,p.criterion_id,p.dvp_item_id,b.supersedes_id].every(v=>typeof v==='string' && validUuid(v) && v===v.toLowerCase()) ||
    b.supersedes_id!==p.id || original.body.request_id===p.id || original.body.criterion_id!==p.criterion_id ||
    (b.action==='WITHDRAW')!==(original.body.dvp_item_id===p.dvp_item_id))return null;
  const command=Object.freeze({operation:'acceptance-correction' as const,target:original.target,
    body:Object.freeze({...original.body,action:b.action,supersedes_id:b.supersedes_id}),
    predecessor:Object.freeze({...p})}) as AcceptanceCorrectionCommand;
  return new TextEncoder().encode(JSON.stringify(command)).length<=8192?command:null;
}
export const acceptanceCorrectionEvent=(c:AcceptanceCorrectionCommand)=>'EVT-AC-'+c.body.request_id;
export const acceptanceCorrectionPath=(c:AcceptanceCorrectionCommand)=>'/api/v1/changes/'+encodeURIComponent(c.target)+'/acceptance-dvp-links';
export type AcceptanceCorrectionReview=Readonly<{command:AcceptanceCorrectionCommand;confirmed:boolean}>;
export function confirmAcceptanceCorrection(input:unknown,confirmed:boolean):AcceptanceCorrectionReview {
  const command=parseAcceptanceCorrectionCommand(input);if(!command)throw Error('invalid_review');
  return Object.freeze({command,confirmed:confirmed===true});
}
export type AcceptanceCorrectionReceipt=Readonly<{operation:'acceptance-correction';request_id:string;target:string;audit_event_no:string;result:Readonly<Record<string,string>>}>;
/** Original correction evidence only. Successor/effectiveness/current status cannot establish a receipt. */
export function projectAcceptanceCorrectionReceipt(value:unknown,c:AcceptanceCorrectionCommand):AcceptanceCorrectionReceipt|null {
  const d=record(value),r=record(d?.result);
  if(!d || !r || d.operation!==c.operation || d.request_id!==c.body.request_id || d.target!==c.target ||
    d.audit_event_no!==acceptanceCorrectionEvent(c) || r.id!==c.body.request_id ||
    typeof r.change_request_id!=='string' || !validUuid(r.change_request_id) || r.change_request_id!==r.change_request_id.toLowerCase() || r.request_no!==c.target)return null;
  const {request_id,...body}=c.body;
  const original={id:request_id,...body,previous_dvp_item_id:c.predecessor.dvp_item_id,previous_action:c.predecessor.action,
    change_request_id:r.change_request_id,request_no:c.target};
  if(Object.entries(original).some(([k,v])=>r[k]!==v))return null;
  return Object.freeze({operation:c.operation,request_id,target:c.target,audit_event_no:acceptanceCorrectionEvent(c),result:Object.freeze(original)});
}
export type AcceptanceCorrectionError = Exclude<FirstError, 'first_submission_disabled' | 'version_conflict'> |
  'acceptance_correction_disabled';
const denials: Readonly<Record<number, readonly AcceptanceCorrectionError[]>> = {
  400:['invalid_request'], 401:['session_required'], 403:['cross_origin_request','read_only_mode','submission_forbidden'],
  409:['request_conflict','submission_conflict'], 413:['request_too_large'],
  415:['json_required'], 422:['invalid_request'], 503:['acceptance_correction_disabled'],
};
export type AcceptanceCorrectionState = Readonly<{ phase:'idle'|'sending'|'checking'|'unknown'|'rejected'|'confirmed';
  review:AcceptanceCorrectionReview; command:AcceptanceCorrectionCommand; error:AcceptanceCorrectionError|null; receipt:AcceptanceCorrectionReceipt|null }>;
/** Memory-only original bytes; audit recovery never repeats a write. */
export class AcceptanceCorrectionSubmission {
  private current: AcceptanceCorrectionState;
  private uncertain = false;
  private readonly body: string;
  constructor(review: AcceptanceCorrectionReview) {
    if (review.confirmed !== true) throw Error('Confirm the exact request before sending.');
    const command = parseAcceptanceCorrectionCommand(review.command);
    if (!command || JSON.stringify(command) !== JSON.stringify(review.command)) throw Error('invalid_review');
    const canonical = confirmAcceptanceCorrection(command,true);
    this.body = JSON.stringify(command);
    this.current = Object.freeze({ phase:'idle', review:canonical, command, error:null, receipt:null });
  }
  get state(): AcceptanceCorrectionState { return this.current; }
  private update(phase:AcceptanceCorrectionState['phase'], error:AcceptanceCorrectionError|null, receipt:AcceptanceCorrectionReceipt|null = null) {
    this.current = Object.freeze({ ...this.current, phase, error, receipt }); return this.current;
  }
  send(enabled:boolean, fetcher:typeof fetch = fetch): Promise<AcceptanceCorrectionState> { return this.run('submit',enabled,fetcher); }
  recover(enabled:boolean, fetcher:typeof fetch = fetch): Promise<AcceptanceCorrectionState> { return this.run('recover',enabled,fetcher); }
  private async run(mode:'submit'|'recover', enabled:boolean, fetcher:typeof fetch): Promise<AcceptanceCorrectionState> {
    if (['sending','checking','confirmed'].includes(this.current.phase)) return this.current;
    if (mode === 'recover') this.uncertain = true;
    if (enabled !== true) return this.update(this.uncertain ? 'unknown' : 'rejected','acceptance_correction_disabled');
    this.update(mode === 'submit' ? 'sending' : 'checking',null);
    try {
      const response = await fetcher(mode === 'submit' ? '/auth/acceptance-correction' : '/auth/acceptance-correction-receipt', {
        method:'POST', body:this.body, headers:{'Content-Type':'application/json',Accept:'application/json'},
        credentials:'same-origin', redirect:'error', cache:'no-store', signal:AbortSignal.timeout(15000) });
      const value = await readCommandResponse(response);
      const receipt = response.status === 200 ? projectAcceptanceCorrectionReceipt(value,this.current.command) : null;
      if (receipt) { this.uncertain = false; return this.update('confirmed',null,receipt); }
      const error = record(value)?.error;
      if (typeof error === 'string' && denials[response.status]?.includes(error as AcceptanceCorrectionError))
        return this.update(this.uncertain ? 'unknown' : 'rejected',error as AcceptanceCorrectionError);
    } catch { /* Lost responses and missing audit records do not prove absence. */ }
    this.uncertain = true; return this.update('unknown','outcome_unknown');
  }
}

