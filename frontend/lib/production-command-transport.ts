import { blankFields, prepare, confirm, validUuid, type Review } from './command-draft';
import { record, exactFields, readCommandResponse, type FirstError } from './first-command-transport';

export type ProductionOperation = 'test-release' | 'deployment' | 'changeover';
export type ProductionBody = Readonly<Record<string, string | null>>;
export type ProductionCommand = Readonly<{ operation: ProductionOperation; target: string; body: ProductionBody }>;
const fields = {
  'test-release': ['request_id','release_id','snapshot_id','test_release_no','purpose_scope','actor_name','reason'],
  deployment: ['request_id','authorization_id','production_line_id','deployment_no'],
  changeover: ['request_id','changeover_no','from_release_id','changed_at','note'],
} as const;
const id = (value: unknown): value is string => typeof value === 'string' && validUuid(value) && value === value.toLowerCase();
const text = (value: unknown, max: number): value is string => typeof value === 'string' &&
  value.trim().length > 0 && value.length <= max && !/[\u0000-\u001f\u007f]/.test(value);
export function productionReview(command: ProductionCommand): Review {
  const b = command.body;
  return confirm(prepare(command.operation, { ...blankFields, target: command.target,
    snapshot:b.snapshot_id ?? '', testReleaseNo:b.test_release_no ?? '', purposeScope:b.purpose_scope ?? '',
    actor:b.actor_name ?? '', reason:b.reason ?? '', productionLine:b.production_line_id ?? '',
    deploymentNo:b.deployment_no ?? '', changeoverNo:b.changeover_no ?? '',
    fromRelease:b.from_release_id ?? '', timestamp:b.changed_at ?? '', note:b.note ?? '' }, b.request_id as string), true);
}
/** Only fixed existing commands; no caller URL, headers, credential or inferred previous release. */
export function parseProductionCommand(value: unknown): ProductionCommand | null {
  const d = record(value), b = record(d?.body);
  if (!d || !b || !exactFields(d,['operation','target','body']) ||
      !['test-release','deployment','changeover'].includes(d.operation as string) ||
      typeof d.target !== 'string' || typeof b.request_id !== 'string' || !validUuid(b.request_id)) return null;
  const operation = d.operation as ProductionOperation;
  if (!exactFields(b,fields[operation]) || !Object.entries(b).every(([key,item]) =>
      ['changed_at','note'].includes(key) ? item === null || typeof item === 'string' && item !== '' : typeof item === 'string')) return null;
  const target = operation === 'changeover' ? d.target.trim() : d.target.trim().toLowerCase();
  if (operation !== 'changeover' && (!validUuid(target) ||
      typeof b[operation === 'test-release' ? 'release_id' : 'authorization_id'] !== 'string' ||
      (b[operation === 'test-release' ? 'release_id' : 'authorization_id'] as string).trim().toLowerCase() !== target)) return null;
  try {
    const review = productionReview({ operation, target, body:b as ProductionBody });
    if (operation === 'changeover' && review.draft.payload.changed_at !== null && !productionTime(review.draft.payload.changed_at)) return null;
    const command = Object.freeze({ operation, target, body:review.draft.payload as ProductionBody });
    return new TextEncoder().encode(JSON.stringify(command)).length <= 8192 ? command : null;
  } catch { return null; }
}
export function productionPath(command: ProductionCommand): string { return productionReview(command).draft.path; }
export function productionEvent(command: ProductionCommand): string {
  const key = command.body.request_id as string;
  return command.operation === 'test-release' ? 'EVT-TR-' + key :
    'EVT-' + (command.operation === 'deployment' ? 'DPLOY' : 'CO') + '-' + key.replaceAll('-','');
}
/** Validate calendar/zone and preserve all six backend microsecond digits. */
export function productionTime(value: unknown): string | null {
  if (typeof value !== 'string') return null;
  const m = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})(?:\.(\d{1,6}))?(Z|[+-]\d{2}:\d{2})$/.exec(value);
  if (!m) return null;
  const [,y,mo,d,h,mi,s,f = '',z] = m;
  const days = new Date(Date.UTC(Number(y),Number(mo),0)).getUTCDate();
  if (Number(y)<100 || Number(mo)<1 || Number(mo)>12 || Number(d)<1 || Number(d)>days ||
      Number(h)>23 || Number(mi)>59 || Number(s)>59 || z !== 'Z' && (Number(z.slice(1,3))>23 || Number(z.slice(4))>59)) return null;
  const time = new Date(value);
  if (!Number.isFinite(time.getTime())) return null;
  const iso = time.toISOString();
  if (iso.length !== 24) return null;
  return iso.slice(0,-1) + f.padEnd(6,'0').slice(3) + 'Z';
}
export type ProductionReceipt = Readonly<{ operation: ProductionOperation; request_id: string; target: string;
  audit_event_no: string; result: Readonly<Record<string, string | null>> }>;
/** Original DRAFT/PENDING/COMPLETED evidence, never current status or physical completion. */
export function projectProductionReceipt(value: unknown, command: ProductionCommand): ProductionReceipt | null {
  const d = record(value), r = record(d?.result), b = command.body, key = b.request_id as string;
  if (!d || !r || d.operation !== command.operation || d.request_id !== key || d.target !== command.target ||
      d.audit_event_no !== productionEvent(command) || r.id !== key) return null;
  let result: Record<string,string|null>;
  if (command.operation === 'test-release') {
    if (r.test_release_no !== b.test_release_no || r.status !== 'DRAFT' || r.release_id !== command.target ||
        r.snapshot_id !== b.snapshot_id || !id(r.snapshot_id) || !text(r.snapshot_no,80) ||
        r.purpose_scope !== b.purpose_scope || r.actor_name !== b.actor_name || r.reason !== b.reason) return null;
    result = { id:key, test_release_no:b.test_release_no, status:'DRAFT', release_id:command.target,
      snapshot_id:b.snapshot_id, snapshot_no:r.snapshot_no, purpose_scope:b.purpose_scope,
      actor_name:b.actor_name, reason:b.reason };
  } else if (command.operation === 'deployment') {
    if (r.deployment_no !== b.deployment_no || r.status !== 'PENDING' || r.authorization_id !== command.target ||
        r.production_line_id !== b.production_line_id || !id(r.production_line_id) ||
        !id(r.expected_release_id) || !id(r.expected_snapshot_id)) return null;
    result = { id:key, deployment_no:b.deployment_no, status:'PENDING', authorization_id:command.target,
      production_line_id:b.production_line_id, expected_release_id:r.expected_release_id, expected_snapshot_id:r.expected_snapshot_id };
  } else {
    const time = productionTime(r.changed_at);
    if (r.changeover_no !== b.changeover_no || r.status !== 'COMPLETED' || r.deployment_no !== command.target ||
        !id(r.deployment_id) || !id(r.authorization_id) || r.from_release_id !== b.from_release_id ||
        !id(r.from_release_id) || !id(r.to_release_id) || r.from_release_id === r.to_release_id ||
        !time || b.changed_at !== null && time !== productionTime(b.changed_at) || r.note !== b.note) return null;
    result = { id:key, changeover_no:b.changeover_no, status:'COMPLETED', deployment_id:r.deployment_id,
      deployment_no:command.target, authorization_id:r.authorization_id, from_release_id:b.from_release_id,
      to_release_id:r.to_release_id, changed_at:time, note:b.note };
  }
  return Object.freeze({ operation:command.operation, request_id:key, target:command.target,
    audit_event_no:productionEvent(command), result:Object.freeze(result) });
}
export type ProductionError = Exclude<FirstError, 'first_submission_disabled' | 'version_conflict'> |
  'production_submission_disabled';
const denials: Readonly<Record<number, readonly ProductionError[]>> = {
  400:['invalid_request'], 401:['session_required'], 403:['cross_origin_request','read_only_mode','submission_forbidden'],
  409:['request_conflict','submission_conflict'], 413:['request_too_large'],
  415:['json_required'], 422:['invalid_request'], 503:['production_submission_disabled'],
};
export type ProductionState = Readonly<{ phase:'idle'|'sending'|'checking'|'unknown'|'rejected'|'confirmed';
  review:Review; command:ProductionCommand; error:ProductionError|null; receipt:ProductionReceipt|null }>;
/** Memory-only original bytes; audit recovery never repeats a write. */
export class ProductionSubmission {
  private current: ProductionState;
  private uncertain = false;
  private readonly body: string;
  constructor(review: Review) {
    if (review.confirmed !== true) throw Error('Confirm the exact request before sending.');
    const command = parseProductionCommand({ operation:review.draft.operation,
      target:review.draft.operation === 'changeover' ? decodeURIComponent(review.draft.path.split('/')[4]) : review.draft.payload[review.draft.operation === 'test-release' ? 'release_id' : 'authorization_id'], body:review.draft.payload });
    if (!command) throw Error('invalid_review');
    const canonical = productionReview(command);
    if (canonical.draft.path !== review.draft.path || canonical.draft.trace !== review.draft.trace ||
        canonical.draft.audit !== review.draft.audit || JSON.stringify(canonical.draft.payload) !== JSON.stringify(review.draft.payload)) throw Error('invalid_review');
    this.body = JSON.stringify(command);
    this.current = Object.freeze({ phase:'idle', review:canonical, command, error:null, receipt:null });
  }
  get state(): ProductionState { return this.current; }
  private update(phase:ProductionState['phase'], error:ProductionError|null, receipt:ProductionReceipt|null = null) {
    this.current = Object.freeze({ ...this.current, phase, error, receipt }); return this.current;
  }
  send(enabled:boolean, fetcher:typeof fetch = fetch): Promise<ProductionState> { return this.run('submit',enabled,fetcher); }
  recover(enabled:boolean, fetcher:typeof fetch = fetch): Promise<ProductionState> { return this.run('recover',enabled,fetcher); }
  private async run(mode:'submit'|'recover', enabled:boolean, fetcher:typeof fetch): Promise<ProductionState> {
    if (['sending','checking','confirmed'].includes(this.current.phase)) return this.current;
    if (mode === 'recover') this.uncertain = true;
    if (enabled !== true) return this.update(this.uncertain ? 'unknown' : 'rejected','production_submission_disabled');
    this.update(mode === 'submit' ? 'sending' : 'checking',null);
    try {
      const response = await fetcher(mode === 'submit' ? '/auth/production-command' : '/auth/production-command-receipt', {
        method:'POST', body:this.body, headers:{'Content-Type':'application/json',Accept:'application/json'},
        credentials:'same-origin', redirect:'error', cache:'no-store', signal:AbortSignal.timeout(15000) });
      const value = await readCommandResponse(response);
      const receipt = response.status === 200 ? projectProductionReceipt(value,this.current.command) : null;
      if (receipt) { this.uncertain = false; return this.update('confirmed',null,receipt); }
      const error = record(value)?.error;
      if (typeof error === 'string' && denials[response.status]?.includes(error as ProductionError))
        return this.update(this.uncertain ? 'unknown' : 'rejected',error as ProductionError);
    } catch { /* Lost responses and missing audit records do not prove absence. */ }
    this.uncertain = true; return this.update('unknown','outcome_unknown');
  }
}
