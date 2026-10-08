import { blankFields, prepare, confirm, type Review } from './command-draft';
import { record, exactFields, readCommandResponse, type FirstError } from './first-command-transport';

export type GovernanceOperation = 'approval' | 'decision';
export type GovernanceCommand = Readonly<{ operation: GovernanceOperation; target: string;
  body: Readonly<Record<string, string | null>> }>;
const uuid = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/;
const text = (value: unknown, max: number): value is string => typeof value === 'string' &&
  value.trim().length > 0 && value.length <= max && !/[\u0000-\u001f\u007f]/.test(value);
const id = (value: unknown): value is string => typeof value === 'string' && uuid.test(value);
export function governanceReview(command: GovernanceCommand): Review {
  const b = command.body;
  return confirm(prepare(command.operation, { ...blankFields, target: command.target,
    actor: b.actor ?? b.decided_by ?? '', step: b.expected_step_id ?? '', action: b.action ?? '',
    decisionNo: b.decision_no ?? '', readiness: b.readiness_status ?? '', decision: b.decision ?? '',
    note: b.comment ?? b.notes ?? '' }, b.request_id as string), true);
}
/** Only two fixed existing commands; declared actor text does not grant permission. */
export function parseGovernanceCommand(value: unknown): GovernanceCommand | null {
  const d = record(value), b = record(d?.body);
  if (!d || !b || !exactFields(d, ['operation','target','body']) ||
      !['approval','decision'].includes(d.operation as string) || typeof d.target !== 'string' ||
      typeof b.request_id !== 'string' || !/^[0-9a-f-]{36}$/i.test(b.request_id)) return null;
  const operation = d.operation as GovernanceOperation;
  const fields = operation === 'approval' ? ['request_id','expected_step_id','actor','action','comment'] :
    ['request_id','decision_no','decided_by','readiness_status','decision','notes'];
  const note = operation === 'approval' ? b.comment : b.notes;
  if (!exactFields(b, fields) || !(note === null || (typeof note === 'string' && note !== '')) ||
      !Object.entries(b).every(([key, item]) => key === 'comment' || key === 'notes' || typeof item === 'string')) return null;
  try {
    const review = governanceReview({ operation, target: d.target, body: b } as GovernanceCommand);
    const command = Object.freeze({ operation, target: d.target.trim(), body: review.draft.payload as GovernanceCommand['body'] });
    return new TextEncoder().encode(JSON.stringify(command)).length <= 8192 ? command : null;
  } catch { return null; }
}
export function governancePath(command: GovernanceCommand): string { return governanceReview(command).draft.path; }
export function governanceEvent(command: GovernanceCommand): string {
  return 'EVT-' + (command.operation === 'approval' ? 'AP' : 'RD') + '-' + (command.body.request_id as string).replaceAll('-', '');
}
export type GovernanceReceipt = Readonly<{ operation: GovernanceOperation; request_id: string; target: string;
  audit_event_no: string; result: Readonly<Record<string, string | number | null>> }>;
/** Stable original outcome, never inferred from current workflow state or declarations. */
export function projectGovernanceReceipt(value: unknown, command: GovernanceCommand): GovernanceReceipt | null {
  const d = record(value), r = record(d?.result), b = command.body, key = b.request_id as string;
  if (!d || !r || d.operation !== command.operation || d.request_id !== key || d.target !== command.target ||
      d.audit_event_no !== governanceEvent(command) || !id(r.approval_id) || r.approval_no !== command.target) return null;
  let result: Record<string, string | number | null>;
  if (command.operation === 'approval') {
    if (r.approval_action_id !== key || r.step_id !== b.expected_step_id || r.action !== b.action || r.step_status !== b.action ||
        (b.action === 'APPROVED' ? !['PENDING','APPROVED'].includes(r.approval_status as string) : r.approval_status !== b.action) ||
        !Number.isSafeInteger(r.step_order) || (r.step_order as number) < 0 || (r.step_order as number) > 2147483647 ||
        !text(r.role_name,120) || !text(r.target_type,50) || !id(r.target_id) || !(r.snapshot_id === null || id(r.snapshot_id))) return null;
    result = { approval_id:r.approval_id, approval_no:command.target, approval_action_id:key,
      step_id:b.expected_step_id, action:b.action, step_status:b.action, approval_status:r.approval_status as string,
      step_order:r.step_order as number, role_name:r.role_name, target_type:r.target_type,
      target_id:r.target_id, snapshot_id:r.snapshot_id as string | null };
  } else {
    if (r.id !== key || r.decision_no !== b.decision_no || r.decision !== b.decision ||
        r.readiness_status !== b.readiness_status || !id(r.release_id) || !id(r.snapshot_id) ||
        !text(r.snapshot_no,80) || typeof r.content_hash !== 'string' || !/^[0-9a-f]{64}$/.test(r.content_hash)) return null;
    result = { id:key, approval_id:r.approval_id, approval_no:command.target, decision_no:b.decision_no,
      decision:b.decision, readiness_status:b.readiness_status, release_id:r.release_id,
      snapshot_id:r.snapshot_id, snapshot_no:r.snapshot_no, content_hash:r.content_hash };
  }
  return Object.freeze({ operation:command.operation, request_id:key, target:command.target,
    audit_event_no:governanceEvent(command), result:Object.freeze(result) });
}
export type GovernanceError = Exclude<FirstError, 'first_submission_disabled' | 'version_conflict'> |
  'governance_submission_disabled' | 'step_conflict';
const denials: Readonly<Record<number, readonly GovernanceError[]>> = {
  400:['invalid_request'], 401:['session_required'], 403:['cross_origin_request','read_only_mode','submission_forbidden'],
  409:['request_conflict','step_conflict','submission_conflict'], 413:['request_too_large'],
  415:['json_required'], 422:['invalid_request'], 503:['governance_submission_disabled'],
};
export type GovernanceState = Readonly<{ phase:'idle'|'sending'|'checking'|'unknown'|'rejected'|'confirmed';
  review:Review; command:GovernanceCommand; error:GovernanceError|null; receipt:GovernanceReceipt|null }>;
/** Memory-only original bytes; audit recovery never repeats a write. */
export class GovernanceSubmission {
  private current: GovernanceState;
  private uncertain = false;
  private readonly body: string;
  constructor(review: Review) {
    if (review.confirmed !== true) throw Error('Confirm the exact request before sending.');
    const command = parseGovernanceCommand({ operation:review.draft.operation,
      target:decodeURIComponent(review.draft.path.split('/')[4] || ''), body:review.draft.payload });
    if (!command) throw Error('invalid_review');
    const canonical = governanceReview(command);
    if (canonical.draft.path !== review.draft.path || canonical.draft.trace !== review.draft.trace ||
        canonical.draft.audit !== review.draft.audit || JSON.stringify(canonical.draft.payload) !== JSON.stringify(review.draft.payload)) throw Error('invalid_review');
    this.body = JSON.stringify(command);
    this.current = Object.freeze({ phase:'idle', review:canonical, command, error:null, receipt:null });
  }
  get state(): GovernanceState { return this.current; }
  private update(phase:GovernanceState['phase'], error:GovernanceError|null, receipt:GovernanceReceipt|null = null) {
    this.current = Object.freeze({ ...this.current, phase, error, receipt }); return this.current;
  }
  send(enabled:boolean, fetcher:typeof fetch = fetch): Promise<GovernanceState> { return this.run('submit',enabled,fetcher); }
  recover(enabled:boolean, fetcher:typeof fetch = fetch): Promise<GovernanceState> { return this.run('recover',enabled,fetcher); }
  private async run(mode:'submit'|'recover', enabled:boolean, fetcher:typeof fetch): Promise<GovernanceState> {
    if (['sending','checking','confirmed'].includes(this.current.phase)) return this.current;
    if (mode === 'recover') this.uncertain = true;
    if (enabled !== true) return this.update(this.uncertain ? 'unknown' : 'rejected','governance_submission_disabled');
    this.update(mode === 'submit' ? 'sending' : 'checking',null);
    try {
      const response = await fetcher(mode === 'submit' ? '/auth/governance-command' : '/auth/governance-command-receipt', {
        method:'POST', body:this.body, headers:{'Content-Type':'application/json',Accept:'application/json'},
        credentials:'same-origin', redirect:'error', cache:'no-store', signal:AbortSignal.timeout(15000) });
      const value = await readCommandResponse(response);
      const receipt = response.status === 200 ? projectGovernanceReceipt(value,this.current.command) : null;
      if (receipt) { this.uncertain = false; return this.update('confirmed',null,receipt); }
      const error = record(value)?.error;
      if (typeof error === 'string' && denials[response.status]?.includes(error as GovernanceError))
        return this.update(this.uncertain ? 'unknown' : 'rejected',error as GovernanceError);
    } catch { /* Lost responses and missing audit records do not prove absence. */ }
    this.uncertain = true; return this.update('unknown','outcome_unknown');
  }
}
