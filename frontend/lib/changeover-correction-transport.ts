import { validUuid } from './command-draft';
import { record, exactFields, readCommandResponse } from './first-command-transport';
import { productionTime } from './production-command-transport';

export type ChangeoverCorrectionTarget = Readonly<{ deployment_no: string; changeover_no: string }>;
export type ChangeoverCorrectionContext = Readonly<ChangeoverCorrectionTarget & {
  changeover_id: string; from_release_id: string; to_release_id: string; history_state: string;
  expected_revision: number; predecessor_id: string | null; changed_at: string | null; note: string | null;
}>;
export type ChangeoverCorrectionBody = Readonly<{
  request_id: string; expected_revision: number; predecessor_id: string | null;
  from_release_id: string; changed_at: string;
  note: string | null; correction_reason: string;
}>;
export type ChangeoverCorrectionCommand = Readonly<{ operation: 'changeover-correction'; target: ChangeoverCorrectionTarget;
  context: ChangeoverCorrectionContext; body: ChangeoverCorrectionBody }>;
const id = (v: unknown): v is string => typeof v === 'string' && validUuid(v) && v === v.toLowerCase();
const nullableId = (v: unknown): v is string | null => v === null || id(v);
const text = (v: unknown, max: number): v is string => typeof v === 'string' && v.length <= max && !/[\u0000-\u001f\u007f]/.test(v);
const nullableNote = (v: unknown): v is string | null => v === null || typeof v === 'string' && v.length <= 8192 && !/[\u0000]/.test(v);
const revision = (v: unknown): v is number => Number.isSafeInteger(v) && (v as number) >= 0 && (v as number) < 2147483647;
const contextFields = ['deployment_no','changeover_no','changeover_id','from_release_id','to_release_id','history_state','expected_revision','predecessor_id','changed_at','note'];
const bodyFields = ['request_id','expected_revision','predecessor_id','from_release_id','changed_at','note','correction_reason'];
export function parseChangeoverCorrectionTarget(value: unknown): ChangeoverCorrectionTarget | null {
  const d = record(value);
  if (!d || !exactFields(d,['deployment_no','changeover_no']) || ![d.deployment_no,d.changeover_no].every(v => text(v,120) && v.length > 0 && v.trim() === v)) return null;
  return Object.freeze({ deployment_no:d.deployment_no as string, changeover_no:d.changeover_no as string });
}
export function parseChangeoverCorrectionContext(value: unknown, target: ChangeoverCorrectionTarget): ChangeoverCorrectionContext | null {
  const d = record(value);
  if (!parseChangeoverCorrectionTarget(target) || !d || !exactFields(d,contextFields) ||
      d.deployment_no !== target.deployment_no || d.changeover_no !== target.changeover_no ||
      ![d.changeover_id,d.from_release_id,d.to_release_id].every(id) || !revision(d.expected_revision) ||
      !nullableId(d.predecessor_id) || (d.expected_revision === 0) !== (d.predecessor_id === null) ||
      (d.changed_at !== null && (typeof d.changed_at !== 'string' || !productionTime(d.changed_at))) || !nullableNote(d.note) ||
      !['NOT_RECORDED','LEGACY','IMPORTED','FIRST_RECORD','LEGACY_CORRECTED','IMPORTED_CORRECTED','FIRST_RECORD_CORRECTED'].includes(d.history_state as string)) return null;
  return Object.freeze({ ...target, changeover_id:d.changeover_id as string, from_release_id:d.from_release_id as string,
    to_release_id:d.to_release_id as string, history_state:d.history_state as string, expected_revision:d.expected_revision,
    predecessor_id:d.predecessor_id, changed_at:d.changed_at === null ? null : productionTime(d.changed_at)!, note:d.note });
}
/** Context is review evidence, never a capability: the backend reauthorizes the nested write. */
export function parseChangeoverCorrectionCommand(value: unknown): ChangeoverCorrectionCommand | null {
  const d = record(value), b = record(d?.body), target = parseChangeoverCorrectionTarget(d?.target);
  if (!d || !target || !b || d.operation !== 'changeover-correction' || !exactFields(d,['operation','target','context','body'])) return null;
  const context = parseChangeoverCorrectionContext(d.context,target);
  if (!context || !exactFields(b,bodyFields) || !id(b.request_id) || !revision(b.expected_revision) ||
      !nullableId(b.predecessor_id) || b.expected_revision !== context.expected_revision || b.predecessor_id !== context.predecessor_id ||
      b.request_id === b.predecessor_id || typeof b.changed_at !== 'string' || !productionTime(b.changed_at) ||
      !id(b.from_release_id) || b.from_release_id === context.to_release_id || !nullableNote(b.note) || typeof b.correction_reason !== 'string' ||
      !b.correction_reason.trim() || b.correction_reason.length > 2000 || b.correction_reason.includes('\0')) return null;
  const body = Object.freeze({ request_id:b.request_id, expected_revision:b.expected_revision, predecessor_id:b.predecessor_id,
    from_release_id:b.from_release_id, changed_at:productionTime(b.changed_at)!, note:b.note, correction_reason:b.correction_reason });
  const command = Object.freeze({ operation:'changeover-correction' as const,target,context,body });
  return new TextEncoder().encode(JSON.stringify(command)).length <= 8192 ? command : null;
}
export const changeoverCorrectionPath = (c: ChangeoverCorrectionCommand) => '/api/v1/deployments/' + encodeURIComponent(c.target.deployment_no) + '/changeovers/' + encodeURIComponent(c.target.changeover_no) + '/correction';
export const changeoverCorrectionContextPath = (t: ChangeoverCorrectionTarget) => '/api/v1/deployments/' + encodeURIComponent(t.deployment_no) + '/changeovers/' + encodeURIComponent(t.changeover_no) + '/correction-context';
export const changeoverCorrectionEvent = (c: ChangeoverCorrectionCommand) => 'EVT-CC-' + c.body.request_id.replaceAll('-','');
export type ChangeoverCorrectionReview = Readonly<{ command: ChangeoverCorrectionCommand; confirmed: boolean }>;
export function confirmChangeoverCorrection(input: unknown, confirmed: boolean): ChangeoverCorrectionReview {
  const command = parseChangeoverCorrectionCommand(input); if (!command) throw Error('invalid_review');
  return Object.freeze({ command, confirmed:confirmed === true });
}
export type ChangeoverCorrectionResult = Readonly<{
  changeover_id:string; changeover_no:string; from_release_id:string; to_release_id:string;
  changed_at:string; note:string|null; correction_reason:string; revision:number; predecessor_id:string|null;
}>;
export type ChangeoverCorrectionReceipt = Readonly<{ operation:'changeover-correction'; target:ChangeoverCorrectionTarget;
  request_id:string; audit_event_no:string; result:ChangeoverCorrectionResult }>;
export function projectChangeoverCorrectionReceipt(value: unknown, c: ChangeoverCorrectionCommand): ChangeoverCorrectionReceipt | null {
  const d=record(value), r=record(d?.result), t=parseChangeoverCorrectionTarget(d?.target), b=c.body, ctx=c.context;
  if (!d || !r || !t || d.operation !== c.operation || t.deployment_no !== c.target.deployment_no || t.changeover_no !== c.target.changeover_no ||
      d.request_id !== b.request_id || d.audit_event_no !== changeoverCorrectionEvent(c) ||
      r.changeover_id !== ctx.changeover_id || r.changeover_no !== c.target.changeover_no || r.to_release_id !== ctx.to_release_id ||
      r.from_release_id !== b.from_release_id || r.revision !== b.expected_revision+1 || r.predecessor_id !== b.predecessor_id ||
      r.note !== b.note || r.correction_reason !== b.correction_reason || typeof r.changed_at !== 'string' ||
      productionTime(r.changed_at) !== b.changed_at) return null;
  const result=Object.freeze({changeover_id:ctx.changeover_id,changeover_no:c.target.changeover_no,
    from_release_id:b.from_release_id,to_release_id:ctx.to_release_id,changed_at:b.changed_at,note:b.note,
    correction_reason:b.correction_reason,revision:b.expected_revision+1,predecessor_id:b.predecessor_id});
  return Object.freeze({operation:c.operation,target:c.target,request_id:b.request_id,audit_event_no:changeoverCorrectionEvent(c),result});
}
export type ChangeoverCorrectionError = 'changeover_correction_disabled'|'invalid_request'|'session_required'|'cross_origin_request'|'read_only_mode'|
  'submission_forbidden'|'request_conflict'|'submission_conflict'|'version_conflict'|'target_not_found'|'request_too_large'|'json_required'|'outcome_unknown';
const denials: Readonly<Record<number,readonly ChangeoverCorrectionError[]>> = {
  400:['invalid_request'],401:['session_required'],403:['cross_origin_request','read_only_mode','submission_forbidden'],
  404:['target_not_found'],409:['request_conflict','submission_conflict','version_conflict'],413:['request_too_large'],
  415:['json_required'],422:['invalid_request'],503:['changeover_correction_disabled'],
};
export type ChangeoverCorrectionState=Readonly<{phase:'idle'|'sending'|'checking'|'unknown'|'rejected'|'confirmed';
  review:ChangeoverCorrectionReview;command:ChangeoverCorrectionCommand;error:ChangeoverCorrectionError|null;receipt:ChangeoverCorrectionReceipt|null}>;
/** Frozen original bytes; recovery reads the actor-bound original audit, never current history. */
export class ChangeoverCorrectionSubmission {
  private current:ChangeoverCorrectionState;
  private uncertain=false;
  private readonly body:string;
  constructor(review:ChangeoverCorrectionReview) {
    if (review.confirmed !== true) throw Error('Confirm the exact request before sending.');
    const command=parseChangeoverCorrectionCommand(review.command);
    if (!command || JSON.stringify(command) !== JSON.stringify(review.command)) throw Error('invalid_review');
    this.body=JSON.stringify(command);
    this.current=Object.freeze({phase:'idle',review:confirmChangeoverCorrection(command,true),command,error:null,receipt:null});
  }
  get state():ChangeoverCorrectionState { return this.current; }
  private update(phase:ChangeoverCorrectionState['phase'],error:ChangeoverCorrectionError|null,receipt:ChangeoverCorrectionReceipt|null=null) {
    this.current=Object.freeze({...this.current,phase,error,receipt});return this.current;
  }
  send(enabled:boolean,fetcher:typeof fetch=fetch) { return this.run('submit',enabled,fetcher); }
  recover(enabled:boolean,fetcher:typeof fetch=fetch) { return this.run('recover',enabled,fetcher); }
  private async run(mode:'submit'|'recover',enabled:boolean,fetcher:typeof fetch):Promise<ChangeoverCorrectionState> {
    if (['sending','checking','confirmed'].includes(this.current.phase)) return this.current;
    if (mode === 'recover') this.uncertain=true;
    if (enabled !== true) return this.update(this.uncertain?'unknown':'rejected','changeover_correction_disabled');
    this.update(mode === 'submit'?'sending':'checking',null);
    try {
      const response=await fetcher(mode === 'submit'?'/auth/changeover-correction':'/auth/changeover-correction-receipt',{
        method:'POST',body:this.body,headers:{'Content-Type':'application/json',Accept:'application/json'},credentials:'same-origin',
        redirect:'error',cache:'no-store',signal:AbortSignal.timeout(15000)});
      const value=await readCommandResponse(response);
      const receipt=response.status === 200?projectChangeoverCorrectionReceipt(value,this.current.command):null;
      if (receipt) { this.uncertain=false;return this.update('confirmed',null,receipt); }
      const error=record(value)?.error;
      if (typeof error === 'string' && denials[response.status]?.includes(error as ChangeoverCorrectionError))
        return this.update(this.uncertain?'unknown':'rejected',error as ChangeoverCorrectionError);
    } catch { /* Lost replies do not prove the correction was not committed. */ }
    this.uncertain=true;return this.update('unknown','outcome_unknown');
  }
}
