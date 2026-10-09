import {blankFields,prepare,confirm,validUuid,type Review} from './command-draft';
import {record,exactFields,readCommandResponse,type FirstError} from './first-command-transport';

export type EvidenceOperation='impact'|'acceptance';
export type EvidenceBody=Readonly<Record<string,string|null>>;
export type EvidenceCommand=Readonly<{operation:EvidenceOperation;target:string;body:EvidenceBody}>;
const bodyFields={impact:['request_id','actor_name','reason','release_id','snapshot_id','decision','evidence_ref'],
  acceptance:['request_id','actor_name','reason','criterion_id','dvp_item_id']} as const;
const id=(v:unknown):v is string=>typeof v==='string' && validUuid(v) && v===v.toLowerCase();
export function evidenceReview(command:EvidenceCommand):Review {
  const b=command.body;
  return confirm(prepare(command.operation,{...blankFields,target:command.target,actor:b.actor_name??'',reason:b.reason??'',
    release:b.release_id??'',snapshot:b.snapshot_id??'',decision:b.decision??'',evidence:b.evidence_ref??'',
    criterion:b.criterion_id??'',dvp:b.dvp_item_id??''},b.request_id as string),true);
}
/** Only two fixed append-only evidence commands; no caller URL, header or credential. */
export function parseEvidenceCommand(value:unknown):EvidenceCommand|null {
  const d=record(value),b=record(d?.body);
  if(!d || !b || !exactFields(d,['operation','target','body']) || !['impact','acceptance'].includes(d.operation as string) ||
    typeof d.target!=='string')return null;
  const operation=d.operation as EvidenceOperation;
  if(!exactFields(b,bodyFields[operation]) || !Object.entries(b).every(([k,v])=>
    k==='evidence_ref' && v===null || typeof v==='string' && !/[\uD800-\uDFFF]/u.test(v.replace(/[\uD800-\uDBFF][\uDC00-\uDFFF]/g,''))))return null;
  try {
    const r=evidenceReview({operation,target:d.target,body:b as EvidenceBody});
    const target=decodeURIComponent(r.draft.path.split('/')[4]);
    const command=Object.freeze({operation,target,body:r.draft.payload as EvidenceBody});
    return new TextEncoder().encode(JSON.stringify(command)).length<=8192?command:null;
  } catch {return null;}
}
export function evidencePath(command:EvidenceCommand):string {return evidenceReview(command).draft.path;}
export function evidenceEvent(command:EvidenceCommand):string {
  return (command.operation==='impact'?'EVT-IMPACT-':'EVT-AC-')+command.body.request_id;
}
export async function evidenceReferenceDigest(reference:string|null):Promise<string> {
  const digest=await crypto.subtle.digest('SHA-256',new TextEncoder().encode(JSON.stringify(reference)));
  return Array.from(new Uint8Array(digest),b=>b.toString(16).padStart(2,'0')).join('');
}
export type EvidenceReceipt=Readonly<{operation:EvidenceOperation;request_id:string;target:string;audit_event_no:string;
  result:Readonly<Record<string,string|null>>}>;
/** Only original assessment/assignment evidence; no current status, pass or release permission. */
export function projectEvidenceReceipt(value:unknown,command:EvidenceCommand):EvidenceReceipt|null {
  const d=record(value),r=record(d?.result),b=command.body;
  if(!d || !r || d.operation!==command.operation || d.request_id!==b.request_id || d.target!==command.target ||
    d.audit_event_no!==evidenceEvent(command) || r.id!==b.request_id)return null;
  const result:Record<string,string|null>={id:b.request_id};
  for(const k of bodyFields[command.operation].filter(k=>k!=='request_id')) {
    if(r[k]!==b[k])return null;result[k]=b[k];
  }
  if(command.operation==='impact') {
    if(!id(r.issue_id) || r.issue_no!==command.target || typeof r.snapshot_no!=='string' || !r.snapshot_no.trim() || r.snapshot_no.length>80)return null;
    Object.assign(result,{issue_id:r.issue_id,issue_no:command.target,snapshot_no:r.snapshot_no});
  } else {
    if(!id(r.change_request_id) || r.request_no!==command.target)return null;
    Object.assign(result,{change_request_id:r.change_request_id,request_no:command.target});
  }
  return Object.freeze({operation:command.operation,request_id:b.request_id as string,target:command.target,
    audit_event_no:evidenceEvent(command),result:Object.freeze(result)});
}
export type EvidenceError = Exclude<FirstError, 'first_submission_disabled' | 'version_conflict'> |
  'evidence_submission_disabled';
const denials: Readonly<Record<number, readonly EvidenceError[]>> = {
  400:['invalid_request'], 401:['session_required'], 403:['cross_origin_request','read_only_mode','submission_forbidden'],
  409:['request_conflict','submission_conflict'], 413:['request_too_large'],
  415:['json_required'], 422:['invalid_request'], 503:['evidence_submission_disabled'],
};
export type EvidenceState = Readonly<{ phase:'idle'|'sending'|'checking'|'unknown'|'rejected'|'confirmed';
  review:Review; command:EvidenceCommand; error:EvidenceError|null; receipt:EvidenceReceipt|null }>;
/** Memory-only original bytes; audit recovery never repeats a write. */
export class EvidenceSubmission {
  private current: EvidenceState;
  private uncertain = false;
  private readonly body: string;
  constructor(review: Review) {
    if (review.confirmed !== true) throw Error('Confirm the exact request before sending.');
    const command = parseEvidenceCommand({ operation:review.draft.operation, target:decodeURIComponent(review.draft.path.split('/')[4]), body:review.draft.payload });
    if (!command) throw Error('invalid_review');
    const canonical = evidenceReview(command);
    if (canonical.draft.path !== review.draft.path || canonical.draft.trace !== review.draft.trace ||
        canonical.draft.audit !== review.draft.audit || JSON.stringify(canonical.draft.payload) !== JSON.stringify(review.draft.payload)) throw Error('invalid_review');
    this.body = JSON.stringify(command);
    this.current = Object.freeze({ phase:'idle', review:canonical, command, error:null, receipt:null });
  }
  get state(): EvidenceState { return this.current; }
  private update(phase:EvidenceState['phase'], error:EvidenceError|null, receipt:EvidenceReceipt|null = null) {
    this.current = Object.freeze({ ...this.current, phase, error, receipt }); return this.current;
  }
  send(enabled:boolean, fetcher:typeof fetch = fetch): Promise<EvidenceState> { return this.run('submit',enabled,fetcher); }
  recover(enabled:boolean, fetcher:typeof fetch = fetch): Promise<EvidenceState> { return this.run('recover',enabled,fetcher); }
  private async run(mode:'submit'|'recover', enabled:boolean, fetcher:typeof fetch): Promise<EvidenceState> {
    if (['sending','checking','confirmed'].includes(this.current.phase)) return this.current;
    if (mode === 'recover') this.uncertain = true;
    if (enabled !== true) return this.update(this.uncertain ? 'unknown' : 'rejected','evidence_submission_disabled');
    this.update(mode === 'submit' ? 'sending' : 'checking',null);
    try {
      const response = await fetcher(mode === 'submit' ? '/auth/evidence-command' : '/auth/evidence-command-receipt', {
        method:'POST', body:this.body, headers:{'Content-Type':'application/json',Accept:'application/json'},
        credentials:'same-origin', redirect:'error', cache:'no-store', signal:AbortSignal.timeout(15000) });
      const value = await readCommandResponse(response);
      const receipt = response.status === 200 ? projectEvidenceReceipt(value,this.current.command) : null;
      if (receipt) { this.uncertain = false; return this.update('confirmed',null,receipt); }
      const error = record(value)?.error;
      if (typeof error === 'string' && denials[response.status]?.includes(error as EvidenceError))
        return this.update(this.uncertain ? 'unknown' : 'rejected',error as EvidenceError);
    } catch { /* Lost responses and missing audit records do not prove absence. */ }
    this.uncertain = true; return this.update('unknown','outcome_unknown');
  }
}
