import { type Review } from './command-draft';
import { FirstSubmission, commandReview, parseFirstCommand, record, exactFields, type FirstCommand } from './first-command-transport';
import { GovernanceSubmission, governanceReview, parseGovernanceCommand, type GovernanceCommand } from './governance-command-transport';
import { DistributionSubmission, distributionReview, parseDistributionCommand, type DistributionCommand } from './distribution-command-transport';
import { ProductionSubmission, productionReview, parseProductionCommand, type ProductionCommand } from './production-command-transport';
import { EvidenceSubmission, evidenceReview, parseEvidenceCommand, type EvidenceCommand } from './evidence-command-transport';
import { ResourceSubmission, resourceReview, parseResourceCommand, type ResourceCommand } from './resource-command-transport';

export type BusinessCommand = FirstCommand | GovernanceCommand | DistributionCommand | ProductionCommand | EvidenceCommand | ResourceCommand;
export type BusinessSubmission = FirstSubmission | GovernanceSubmission | DistributionSubmission | ProductionSubmission | EvidenceSubmission | ResourceSubmission;
export const recoveryTextLimit = 32768;
const format = 'slc-business-recovery';
function validOrigin(origin: string): boolean {
  try { const u = new URL(origin); return u.origin === origin && !u.username && !u.password &&
    (u.protocol === 'https:' || u.protocol === 'http:' && ['localhost','127.0.0.1','[::1]'].includes(u.hostname)); }
  catch { return false; }
}
function validUnicode(value: unknown): boolean {
  if (typeof value === 'string') return !/[\uD800-\uDFFF]/u.test(value.replace(/[\uD800-\uDBFF][\uDC00-\uDFFF]/g, ''));
  if (Array.isArray(value)) return value.every(validUnicode);
  const d = record(value); return !d || Object.entries(d).every(([k,v]) => validUnicode(k) && validUnicode(v));
}
function parseCommand(value: unknown): BusinessCommand | null {
  return parseFirstCommand(value) ?? parseGovernanceCommand(value) ?? parseDistributionCommand(value) ??
    parseProductionCommand(value) ?? parseEvidenceCommand(value) ?? parseResourceCommand(value);
}
export function businessReview(c: BusinessCommand): Review {
  switch (c.operation) {
    case 'snapshot': case 'actual': case 'batch': return commandReview(c as FirstCommand);
    case 'approval': case 'decision': return governanceReview(c as GovernanceCommand);
    case 'delivery': case 'distribution': case 'authorization': return distributionReview(c as DistributionCommand);
    case 'test-release': case 'deployment': case 'changeover': return productionReview(c as ProductionCommand);
    case 'impact': case 'acceptance': return evidenceReview(c as EvidenceCommand);
    case 'resource': return resourceReview(c as ResourceCommand);
  }
}
function submission(c: BusinessCommand): BusinessSubmission {
  const review = businessReview(c);
  switch (c.operation) {
    case 'snapshot': case 'actual': case 'batch': return new FirstSubmission(review);
    case 'approval': case 'decision': return new GovernanceSubmission(review);
    case 'delivery': case 'distribution': case 'authorization': return new DistributionSubmission(review);
    case 'test-release': case 'deployment': case 'changeover': return new ProductionSubmission(review);
    case 'impact': case 'acceptance': return new EvidenceSubmission(review);
    case 'resource': return new ResourceSubmission(review);
  }
}
function envelope(c: BusinessCommand, origin: string) { return { format, version:1, origin, operation:c.operation, target:c.target, body:c.body }; }
/** Canonical original request only. No credential, trusted identity, receipt or caller URL. */
export function exportBusinessRecovery(review: Review, origin: string): string {
  if (review.confirmed !== true || !validOrigin(origin)) throw Error('invalid_recovery');
  const b = review.draft.payload, op = review.draft.operation;
  const target = op === 'resource' ? b.entity_id : op === 'delivery' || op === 'test-release' ? b.release_id :
    op === 'distribution' ? b.delivery_package_id : op === 'authorization' ? b.distribution_id :
    op === 'deployment' ? b.authorization_id : decodeURIComponent(review.draft.path.split('/')[4]);
  const c = parseCommand({operation:op,target,body:b});
  if (!c || !validUnicode(c)) throw Error('invalid_recovery');
  const canonical = businessReview(c);
  if (canonical.draft.path !== review.draft.path || canonical.draft.trace !== review.draft.trace ||
      canonical.draft.audit !== review.draft.audit || JSON.stringify(c.body) !== JSON.stringify(b)) throw Error('invalid_recovery');
  const result = JSON.stringify(envelope(c,origin),null,2);
  if (new TextEncoder().encode(result).length > recoveryTextLimit) throw Error('invalid_recovery');
  return result;
}
/** Accept our exact compact/pretty representation only; duplicate keys/normalization are rejected. */
export function parseBusinessRecovery(text: string, origin: string): BusinessCommand | null {
  if (!validOrigin(origin) || text.length > recoveryTextLimit || new TextEncoder().encode(text).length > recoveryTextLimit) return null;
  try {
    const value = JSON.parse(text), d = record(value);
    if (!d || !exactFields(d,['format','version','origin','operation','target','body']) || d.format !== format ||
        d.version !== 1 || d.origin !== origin || !validUnicode(d)) return null;
    const c = parseCommand({operation:d.operation,target:d.target,body:d.body});
    if (!c) return null;
    const canonical = envelope(c,origin), input = text.trim();
    return input === JSON.stringify(canonical) || input === JSON.stringify(canonical,null,2) ? c : null;
  } catch { return null; }
}
/** Read-only facade: staging marks uncertainty synchronously; import never sends or queries automatically. */
export function importBusinessRecovery(text: string, origin: string) {
  const c = parseBusinessRecovery(text,origin);
  if (!c) throw Error('invalid_recovery');
  const controller = submission(c);
  void controller.recover(false);
  const staged = Object.freeze({ ...controller.state, error:'outcome_unknown' as const });
  let queried = false;
  return Object.freeze({ get state() { return queried ? controller.state : staged; },
    recover:(enabled:boolean, fetcher?:typeof fetch) => { queried = true; return controller.recover(enabled,fetcher); } });
}
export type ImportedBusinessRecovery = ReturnType<typeof importBusinessRecovery>;
