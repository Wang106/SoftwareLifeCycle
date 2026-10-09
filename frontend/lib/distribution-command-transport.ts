import { blankFields, prepare, confirm, validUuid, type Review } from './command-draft';
import { record, exactFields, readCommandResponse, type FirstError } from './first-command-transport';

export type DistributionOperation = 'delivery' | 'distribution' | 'authorization';
export type DistributionBody = Readonly<Record<string, string | number | null | readonly string[]>>;
export type DistributionCommand = Readonly<{ operation: DistributionOperation; target: string; body: DistributionBody }>;
const fields = {
  delivery: ['request_id','release_id','package_no','revision','recipient_type','recipient_code','purpose','snapshot_artifact_ids','created_by'],
  distribution: ['request_id','delivery_package_id','distribution_no','recipient_type','recipient_code'],
  authorization: ['request_id','release_id','distribution_id','authorization_no','customer_id','project_id','site_code','line_code','purpose','batch_limit','restriction_note'],
} as const;
const targetField = (operation: DistributionOperation) => operation === 'delivery' ? 'release_id' :
  operation === 'distribution' ? 'delivery_package_id' : 'distribution_id';
const id = (value: unknown): value is string => typeof value === 'string' && validUuid(value) && value === value.toLowerCase();
const integer = (value: unknown): value is number => Number.isSafeInteger(value) && (value as number) >= 1 && (value as number) <= 2147483647;
const text = (value: unknown, max: number): value is string => typeof value === 'string' &&
  value.trim().length > 0 && value.length <= max && !/[\u0000-\u001f\u007f]/.test(value);
const optional = (value: unknown): value is string | null => value === null || typeof value === 'string' && value !== '';
const artifacts = (value: unknown): value is readonly string[] => Array.isArray(value) && value.length >= 1 && value.length <= 200 &&
  value.every(id) && new Set(value).size === value.length;
export function distributionReview(command: DistributionCommand): Review {
  const b = command.body;
  return confirm(prepare(command.operation, { ...blankFields, target: command.target,
    release: b.release_id as string ?? '', packageNo: b.package_no as string ?? '',
    revision: b.revision === undefined ? '' : String(b.revision),
    artifacts: Array.isArray(b.snapshot_artifact_ids) ? b.snapshot_artifact_ids.join('\n') : '',
    actor: b.created_by as string ?? '', recipientType: b.recipient_type as string ?? '',
    recipientCode: b.recipient_code as string ?? '', purpose: b.purpose as string ?? '',
    distributionNo: b.distribution_no as string ?? '', authorizationNo: b.authorization_no as string ?? '',
    customer: b.customer_id as string ?? '', project: b.project_id as string ?? '',
    site: b.site_code as string ?? '', line: b.line_code as string ?? '',
    limitMode: b.batch_limit === null ? 'UNLIMITED' : 'FINITE',
    limit: b.batch_limit === null || b.batch_limit === undefined ? '' : String(b.batch_limit),
    note: b.restriction_note as string ?? '' }, b.request_id as string), true);
}
/** Fixed existing commands, explicit limits and immutable canonical artifact set; no arbitrary route or credentials. */
export function parseDistributionCommand(value: unknown): DistributionCommand | null {
  const d = record(value), b = record(d?.body);
  if (!d || !b || !exactFields(d,['operation','target','body']) ||
      !['delivery','distribution','authorization'].includes(d.operation as string) ||
      typeof d.target !== 'string' || !validUuid(d.target.trim()) ||
      typeof b.request_id !== 'string' || !validUuid(b.request_id)) return null;
  const operation = d.operation as DistributionOperation;
  if (!exactFields(b,fields[operation]) || !Object.entries(b).every(([key,item]) =>
      ['revision','batch_limit','created_by','restriction_note','snapshot_artifact_ids'].includes(key) || typeof item === 'string')) return null;
  if (operation === 'delivery' && (!integer(b.revision) || !optional(b.created_by) ||
      !Array.isArray(b.snapshot_artifact_ids) || b.snapshot_artifact_ids.length < 1 || b.snapshot_artifact_ids.length > 200 ||
      !b.snapshot_artifact_ids.every(v => typeof v === 'string' && validUuid(v)))) return null;
  if (operation === 'authorization' && (!(b.batch_limit === null || integer(b.batch_limit)) || !optional(b.restriction_note))) return null;
  const target = d.target.trim().toLowerCase(), bodyTarget = b[targetField(operation)];
  if (typeof bodyTarget !== 'string' || !validUuid(bodyTarget) || bodyTarget.toLowerCase() !== target) return null;
  try {
    const review = distributionReview({ operation, target, body:b as DistributionBody });
    const command = Object.freeze({ operation, target, body:review.draft.payload });
    return new TextEncoder().encode(JSON.stringify(command)).length <= 8192 ? command : null;
  } catch { return null; }
}
export function distributionPath(command: DistributionCommand): string { return distributionReview(command).draft.path; }
export function distributionEvent(command: DistributionCommand): string {
  return 'EVT-' + (command.operation === 'delivery' ? 'DP' : command.operation === 'distribution' ? 'DS' : 'PA') + '-' +
    (command.body.request_id as string).replaceAll('-','');
}
export type DistributionReceipt = Readonly<{ operation: DistributionOperation; request_id: string; target: string;
  audit_event_no: string; result: Readonly<Record<string, string | number | null | readonly string[]>> }>;
/** Original READY/DRAFT record and exact evidence; current status, sent files and approval are never inferred. */
export function projectDistributionReceipt(value: unknown, command: DistributionCommand): DistributionReceipt | null {
  const d = record(value), r = record(d?.result), b = command.body, key = b.request_id as string;
  if (!d || !r || d.operation !== command.operation || d.request_id !== key || d.target !== command.target ||
      d.audit_event_no !== distributionEvent(command) || r.id !== key || !id(r.release_id) || !id(r.snapshot_id)) return null;
  let result: Record<string, string | number | null | readonly string[]>;
  if (command.operation === 'delivery') {
    if (r.package_no !== b.package_no || r.revision !== b.revision || r.status !== 'READY' || r.release_id !== command.target ||
        r.recipient_type !== b.recipient_type || r.recipient_code !== b.recipient_code || r.purpose !== b.purpose ||
        !text(r.snapshot_no,80) || !text(r.decision_no,50) || !text(r.approval_no,50) ||
        !artifacts(r.snapshot_artifact_ids) || JSON.stringify([...r.snapshot_artifact_ids].sort()) !== JSON.stringify(b.snapshot_artifact_ids)) return null;
    result = { id:key, package_no:b.package_no, revision:b.revision, status:'READY',
      release_id:r.release_id, snapshot_id:r.snapshot_id, snapshot_no:r.snapshot_no,
      decision_no:r.decision_no, approval_no:r.approval_no, recipient_type:b.recipient_type,
      recipient_code:b.recipient_code, purpose:b.purpose, snapshot_artifact_ids:Object.freeze([...(b.snapshot_artifact_ids as readonly string[])]) };
  } else if (command.operation === 'distribution') {
    if (r.distribution_no !== b.distribution_no || r.delivery_package_id !== command.target || r.status !== 'READY' ||
        !text(r.package_no,50) || !integer(r.revision) ||
        r.recipient_type !== b.recipient_type || r.recipient_code !== b.recipient_code) return null;
    result = { id:key, distribution_no:b.distribution_no, status:'READY', delivery_package_id:command.target,
      package_no:r.package_no, revision:r.revision, release_id:r.release_id, snapshot_id:r.snapshot_id,
      recipient_type:b.recipient_type, recipient_code:b.recipient_code };
  } else {
    if (r.authorization_no !== b.authorization_no || r.status !== 'DRAFT' || r.distribution_id !== command.target ||
        r.release_id !== b.release_id || r.customer_id !== b.customer_id || r.project_id !== b.project_id ||
        r.site_code !== b.site_code || r.line_code !== b.line_code || r.purpose !== b.purpose ||
        r.batch_limit !== b.batch_limit || r.restriction_note !== b.restriction_note ||
        !text(r.distribution_no,50) || !id(r.delivery_package_id) || !text(r.package_no,50) || !integer(r.revision)) return null;
    result = { id:key, authorization_no:b.authorization_no, status:'DRAFT', distribution_id:command.target,
      distribution_no:r.distribution_no, delivery_package_id:r.delivery_package_id, package_no:r.package_no, revision:r.revision,
      release_id:r.release_id, snapshot_id:r.snapshot_id, customer_id:b.customer_id, project_id:b.project_id,
      site_code:b.site_code, line_code:b.line_code, purpose:b.purpose, batch_limit:b.batch_limit, restriction_note:b.restriction_note };
  }
  return Object.freeze({ operation:command.operation, request_id:key, target:command.target,
    audit_event_no:distributionEvent(command), result:Object.freeze(result) });
}
export type DistributionError = Exclude<FirstError, 'first_submission_disabled' | 'version_conflict'> |
  'distribution_submission_disabled';
const denials: Readonly<Record<number, readonly DistributionError[]>> = {
  400:['invalid_request'], 401:['session_required'], 403:['cross_origin_request','read_only_mode','submission_forbidden'],
  409:['request_conflict','submission_conflict'], 413:['request_too_large'],
  415:['json_required'], 422:['invalid_request'], 503:['distribution_submission_disabled'],
};
export type DistributionState = Readonly<{ phase:'idle'|'sending'|'checking'|'unknown'|'rejected'|'confirmed';
  review:Review; command:DistributionCommand; error:DistributionError|null; receipt:DistributionReceipt|null }>;
/** Memory-only original bytes; audit recovery never repeats a write. */
export class DistributionSubmission {
  private current: DistributionState;
  private uncertain = false;
  private readonly body: string;
  constructor(review: Review) {
    if (review.confirmed !== true) throw Error('Confirm the exact request before sending.');
    const command = parseDistributionCommand({ operation:review.draft.operation,
      target:review.draft.payload[targetField(review.draft.operation as DistributionOperation)], body:review.draft.payload });
    if (!command) throw Error('invalid_review');
    const canonical = distributionReview(command);
    if (canonical.draft.path !== review.draft.path || canonical.draft.trace !== review.draft.trace ||
        canonical.draft.audit !== review.draft.audit || JSON.stringify(canonical.draft.payload) !== JSON.stringify(review.draft.payload)) throw Error('invalid_review');
    this.body = JSON.stringify(command);
    this.current = Object.freeze({ phase:'idle', review:canonical, command, error:null, receipt:null });
  }
  get state(): DistributionState { return this.current; }
  private update(phase:DistributionState['phase'], error:DistributionError|null, receipt:DistributionReceipt|null = null) {
    this.current = Object.freeze({ ...this.current, phase, error, receipt }); return this.current;
  }
  send(enabled:boolean, fetcher:typeof fetch = fetch): Promise<DistributionState> { return this.run('submit',enabled,fetcher); }
  recover(enabled:boolean, fetcher:typeof fetch = fetch): Promise<DistributionState> { return this.run('recover',enabled,fetcher); }
  private async run(mode:'submit'|'recover', enabled:boolean, fetcher:typeof fetch): Promise<DistributionState> {
    if (['sending','checking','confirmed'].includes(this.current.phase)) return this.current;
    if (mode === 'recover') this.uncertain = true;
    if (enabled !== true) return this.update(this.uncertain ? 'unknown' : 'rejected','distribution_submission_disabled');
    this.update(mode === 'submit' ? 'sending' : 'checking',null);
    try {
      const response = await fetcher(mode === 'submit' ? '/auth/distribution-command' : '/auth/distribution-command-receipt', {
        method:'POST', body:this.body, headers:{'Content-Type':'application/json',Accept:'application/json'},
        credentials:'same-origin', redirect:'error', cache:'no-store', signal:AbortSignal.timeout(15000) });
      const value = await readCommandResponse(response);
      const receipt = response.status === 200 ? projectDistributionReceipt(value,this.current.command) : null;
      if (receipt) { this.uncertain = false; return this.update('confirmed',null,receipt); }
      const error = record(value)?.error;
      if (typeof error === 'string' && denials[response.status]?.includes(error as DistributionError))
        return this.update(this.uncertain ? 'unknown' : 'rejected',error as DistributionError);
    } catch { /* Lost responses and missing audit records do not prove absence. */ }
    this.uncertain = true; return this.update('unknown','outcome_unknown');
  }
}
