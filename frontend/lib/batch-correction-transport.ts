import { validUuid } from './command-draft';
import { record, exactFields, readCommandResponse } from './first-command-transport';
import { productionTime } from './production-command-transport';

export type BatchCorrectionTarget = Readonly<{ deployment_no: string; batch_no: string }>;
export type BatchCorrectionContext = Readonly<BatchCorrectionTarget & {
  batch_id: string; release_id: string; snapshot_id: string; history_state: string;
  expected_revision: number; predecessor_id: string | null; started_at: string | null;
  ended_at: string | null; changeover_id: string | null; note: string | null;
}>;
export type BatchCorrectionBody = Readonly<{
  request_id: string; expected_revision: number; predecessor_id: string | null;
  started_at: string | null; ended_at: string | null; changeover_id: string | null;
  note: string | null; correction_reason: string;
}>;
export type BatchCorrectionCommand = Readonly<{ operation: 'batch-correction'; target: BatchCorrectionTarget;
  context: BatchCorrectionContext; body: BatchCorrectionBody }>;
const id = (v: unknown): v is string => typeof v === 'string' && validUuid(v) && v === v.toLowerCase();
const nullableId = (v: unknown): v is string | null => v === null || id(v);
const text = (v: unknown, max: number): v is string => typeof v === 'string' && v.length <= max && !/[\u0000-\u001f\u007f]/.test(v);
const nullableNote = (v: unknown): v is string | null => v === null || typeof v === 'string' && v.length <= 8192 && !/[\u0000]/.test(v);
const nullableTime = (v: unknown): v is string | null => v === null || typeof v === 'string' && productionTime(v) !== null;
const revision = (v: unknown): v is number => Number.isSafeInteger(v) && (v as number) >= 0 && (v as number) < 2147483647;
const normalizedTime = (v: string | null) => v === null ? null : productionTime(v)!;
const contextFields = ['deployment_no','batch_no','batch_id','release_id','snapshot_id','history_state','expected_revision','predecessor_id','started_at','ended_at','changeover_id','note'];
const bodyFields = ['request_id','expected_revision','predecessor_id','started_at','ended_at','changeover_id','note','correction_reason'];
export function parseBatchCorrectionTarget(value: unknown): BatchCorrectionTarget | null {
  const d = record(value);
  if (!d || !exactFields(d,['deployment_no','batch_no']) || ![d.deployment_no,d.batch_no].every(v => text(v,120) && v.length > 0 && v.trim() === v)) return null;
  return Object.freeze({ deployment_no:d.deployment_no as string, batch_no:d.batch_no as string });
}
export function parseBatchCorrectionContext(value: unknown, target: BatchCorrectionTarget): BatchCorrectionContext | null {
  const d = record(value);
  if (!parseBatchCorrectionTarget(target) || !d || !exactFields(d,contextFields) ||
      d.deployment_no !== target.deployment_no || d.batch_no !== target.batch_no ||
      ![d.batch_id,d.release_id,d.snapshot_id].every(id) || !revision(d.expected_revision) ||
      !nullableId(d.predecessor_id) || (d.expected_revision === 0) !== (d.predecessor_id === null) ||
      !nullableId(d.changeover_id) || !nullableTime(d.started_at) || !nullableTime(d.ended_at) || !nullableNote(d.note) ||
      !['NOT_RECORDED','LEGACY','IMPORTED','FIRST_RECORD','LEGACY_CORRECTED','IMPORTED_CORRECTED','FIRST_RECORD_CORRECTED'].includes(d.history_state as string)) return null;
  return Object.freeze({ ...target, batch_id:d.batch_id as string, release_id:d.release_id as string,
    snapshot_id:d.snapshot_id as string, history_state:d.history_state as string, expected_revision:d.expected_revision,
    predecessor_id:d.predecessor_id, started_at:normalizedTime(d.started_at), ended_at:normalizedTime(d.ended_at),
    changeover_id:d.changeover_id, note:d.note });
}
/** Context is review evidence, never a capability: the backend reauthorizes the nested write. */
export function parseBatchCorrectionCommand(value: unknown): BatchCorrectionCommand | null {
  const d = record(value), b = record(d?.body), target = parseBatchCorrectionTarget(d?.target);
  if (!d || !target || !b || d.operation !== 'batch-correction' || !exactFields(d,['operation','target','context','body'])) return null;
  const context = parseBatchCorrectionContext(d.context,target);
  if (!context || !exactFields(b,bodyFields) || !id(b.request_id) || !revision(b.expected_revision) ||
      !nullableId(b.predecessor_id) || b.expected_revision !== context.expected_revision || b.predecessor_id !== context.predecessor_id ||
      b.request_id === b.predecessor_id || !nullableTime(b.started_at) || !nullableTime(b.ended_at) ||
      !nullableId(b.changeover_id) || !nullableNote(b.note) || typeof b.correction_reason !== 'string' ||
      !b.correction_reason.trim() || b.correction_reason.length > 2000 || b.correction_reason.includes('\0')) return null;
  const started_at = normalizedTime(b.started_at), ended_at = normalizedTime(b.ended_at);
  const effectiveStart = started_at ?? context.started_at, effectiveEnd = ended_at ?? context.ended_at;
  if (!effectiveStart || effectiveEnd !== null && effectiveEnd < effectiveStart) return null;
  const body = Object.freeze({ request_id:b.request_id, expected_revision:b.expected_revision, predecessor_id:b.predecessor_id,
    started_at, ended_at, changeover_id:b.changeover_id, note:b.note, correction_reason:b.correction_reason });
  const command = Object.freeze({ operation:'batch-correction' as const,target,context,body });
  return new TextEncoder().encode(JSON.stringify(command)).length <= 8192 ? command : null;
}
export const batchCorrectionPath = (c: BatchCorrectionCommand) => '/api/v1/deployments/' + encodeURIComponent(c.target.deployment_no) + '/batches/' + encodeURIComponent(c.target.batch_no) + '/correction';
export const batchCorrectionContextPath = (t: BatchCorrectionTarget) => '/api/v1/deployments/' + encodeURIComponent(t.deployment_no) + '/batches/' + encodeURIComponent(t.batch_no) + '/correction-context';
export const batchCorrectionEvent = (c: BatchCorrectionCommand) => 'EVT-BC-' + c.body.request_id.replaceAll('-','');
export type BatchCorrectionReview = Readonly<{ command: BatchCorrectionCommand; confirmed: boolean }>;
export function confirmBatchCorrection(input: unknown, confirmed: boolean): BatchCorrectionReview {
  const command = parseBatchCorrectionCommand(input); if (!command) throw Error('invalid_review');
  return Object.freeze({ command, confirmed:confirmed === true });
}
export type BatchCorrectionResult = Readonly<{
  batch_id:string; batch_no:string; release_id:string; snapshot_id:string;
  started_at:string; ended_at:string|null; changeover_id:string|null; note:string|null;
  correction_reason:string; revision:number; predecessor_id:string|null;
}>;
export type BatchCorrectionReceipt = Readonly<{ operation:'batch-correction'; target:BatchCorrectionTarget;
  request_id:string; audit_event_no:string; result:BatchCorrectionResult }>;
export function projectBatchCorrectionReceipt(value: unknown, c: BatchCorrectionCommand): BatchCorrectionReceipt | null {
  const d=record(value), r=record(d?.result), t=parseBatchCorrectionTarget(d?.target), b=c.body, ctx=c.context;
  if (!d || !r || !t || d.operation !== c.operation || t.deployment_no !== c.target.deployment_no || t.batch_no !== c.target.batch_no ||
      d.request_id !== b.request_id || d.audit_event_no !== batchCorrectionEvent(c) ||
      r.batch_id !== ctx.batch_id || r.batch_no !== c.target.batch_no || r.release_id !== ctx.release_id || r.snapshot_id !== ctx.snapshot_id ||
      r.revision !== b.expected_revision+1 || r.predecessor_id !== b.predecessor_id ||
      r.changeover_id !== b.changeover_id || r.note !== b.note || r.correction_reason !== b.correction_reason ||
      !nullableTime(r.started_at) || r.started_at === null || !nullableTime(r.ended_at)) return null;
  const started_at=normalizedTime(r.started_at), ended_at=normalizedTime(r.ended_at);
  if (started_at !== (b.started_at ?? ctx.started_at) || ended_at !== (b.ended_at ?? ctx.ended_at)) return null;
  const result=Object.freeze({batch_id:ctx.batch_id,batch_no:c.target.batch_no,release_id:ctx.release_id,snapshot_id:ctx.snapshot_id,
    started_at:started_at!,ended_at,changeover_id:b.changeover_id,note:b.note,correction_reason:b.correction_reason,
    revision:b.expected_revision+1,predecessor_id:b.predecessor_id});
  return Object.freeze({operation:c.operation,target:c.target,request_id:b.request_id,audit_event_no:batchCorrectionEvent(c),result});
}
export type BatchCorrectionError = 'batch_correction_disabled'|'invalid_request'|'session_required'|'cross_origin_request'|'read_only_mode'|
  'submission_forbidden'|'request_conflict'|'submission_conflict'|'version_conflict'|'target_not_found'|'request_too_large'|'json_required'|'outcome_unknown';
const denials: Readonly<Record<number,readonly BatchCorrectionError[]>> = {
  400:['invalid_request'],401:['session_required'],403:['cross_origin_request','read_only_mode','submission_forbidden'],
  404:['target_not_found'],409:['request_conflict','submission_conflict','version_conflict'],413:['request_too_large'],
  415:['json_required'],422:['invalid_request'],503:['batch_correction_disabled'],
};
export type BatchCorrectionState=Readonly<{phase:'idle'|'sending'|'checking'|'unknown'|'rejected'|'confirmed';
  review:BatchCorrectionReview;command:BatchCorrectionCommand;error:BatchCorrectionError|null;receipt:BatchCorrectionReceipt|null}>;
/** Frozen original bytes; recovery reads the actor-bound original audit, never current history. */
export class BatchCorrectionSubmission {
  private current:BatchCorrectionState;
  private uncertain=false;
  private readonly body:string;
  constructor(review:BatchCorrectionReview) {
    if (review.confirmed !== true) throw Error('Confirm the exact request before sending.');
    const command=parseBatchCorrectionCommand(review.command);
    if (!command || JSON.stringify(command) !== JSON.stringify(review.command)) throw Error('invalid_review');
    this.body=JSON.stringify(command);
    this.current=Object.freeze({phase:'idle',review:confirmBatchCorrection(command,true),command,error:null,receipt:null});
  }
  get state():BatchCorrectionState { return this.current; }
  private update(phase:BatchCorrectionState['phase'],error:BatchCorrectionError|null,receipt:BatchCorrectionReceipt|null=null) {
    this.current=Object.freeze({...this.current,phase,error,receipt});return this.current;
  }
  send(enabled:boolean,fetcher:typeof fetch=fetch) { return this.run('submit',enabled,fetcher); }
  recover(enabled:boolean,fetcher:typeof fetch=fetch) { return this.run('recover',enabled,fetcher); }
  private async run(mode:'submit'|'recover',enabled:boolean,fetcher:typeof fetch):Promise<BatchCorrectionState> {
    if (['sending','checking','confirmed'].includes(this.current.phase)) return this.current;
    if (mode === 'recover') this.uncertain=true;
    if (enabled !== true) return this.update(this.uncertain?'unknown':'rejected','batch_correction_disabled');
    this.update(mode === 'submit'?'sending':'checking',null);
    try {
      const response=await fetcher(mode === 'submit'?'/auth/batch-correction':'/auth/batch-correction-receipt',{
        method:'POST',body:this.body,headers:{'Content-Type':'application/json',Accept:'application/json'},credentials:'same-origin',
        redirect:'error',cache:'no-store',signal:AbortSignal.timeout(15000)});
      const value=await readCommandResponse(response);
      const receipt=response.status === 200?projectBatchCorrectionReceipt(value,this.current.command):null;
      if (receipt) { this.uncertain=false;return this.update('confirmed',null,receipt); }
      const error=record(value)?.error;
      if (typeof error === 'string' && denials[response.status]?.includes(error as BatchCorrectionError))
        return this.update(this.uncertain?'unknown':'rejected',error as BatchCorrectionError);
    } catch { /* Lost replies do not prove the correction was not committed. */ }
    this.uncertain=true;return this.update('unknown','outcome_unknown');
  }
}
