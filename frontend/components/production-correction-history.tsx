import Link from 'next/link';
import { apiGet } from '../lib/api';
import { Localized } from './localized';

type Kind = 'batch' | 'changeover';
type Values = {
  from_release_id?: string | null; from_version?: string | null;
  to_release_id?: string | null; to_version?: string | null;
  release_id?: string | null; version?: string | null;
  snapshot_id?: string | null; snapshot_no?: string | null;
  changeover_id?: string | null; changeover_no?: string | null;
  changed_at?: string | null; started_at?: string | null; ended_at?: string | null; note?: string | null;
};
type History = {
  kind: Kind; record_no: string; deployment_no: string; stored_status: string; history_state: string;
  recorded_baseline: null | { source: string; recorded_at: string | null; baseline_event_no: string | null; values: Values };
  effective: { revision: number; head_id: string | null; values: Values };
  correction_count: number; limit: number; truncated: boolean;
  corrections: { id: string; revision: number; predecessor_id: string | null; correction_reason: string;
    recorded_at: string | null; audit_event_no: string; values: Values }[];
};
const plural = { batch: 'batches', changeover: 'changeovers' };
const object = (value: unknown): value is Record<string, unknown> => value !== null && typeof value === 'object' && !Array.isArray(value);
const nullableText = (value: unknown) => value === null || typeof value === 'string';
const validFacts = (value: unknown) => object(value) && Object.values(value).every(nullableText);
const titles = { batch: 'Batch correction history', changeover: 'Changeover correction history' };
function value(text: string | null | undefined) { return text === null || text === undefined ? <Localized>{'Not recorded'}</Localized> : text; }
function Facts({ kind, facts }: { kind: Kind; facts: Values }) {
  const fields: [string, string | null | undefined][] = kind === 'changeover'
    ? [['From release', facts.from_version], ['From release ID', facts.from_release_id],
       ['To release', facts.to_version], ['To release ID', facts.to_release_id], ['Occurrence time', facts.changed_at]]
    : [['Release', facts.version], ['Release ID', facts.release_id], ['Snapshot', facts.snapshot_no],
       ['Snapshot ID', facts.snapshot_id], ['Changeover', facts.changeover_no], ['Changeover ID', facts.changeover_id],
       ['Started', facts.started_at], ['Ended', facts.ended_at]];
  return <Localized><dl className="kv" style={{ overflowWrap: 'anywhere' }}>{fields.map(([label, text]) => <div key={label}><dt><Localized>{label}</Localized></dt><dd style={{ margin: 0 }}>{value(text)}</dd></div>)}
    <div><dt><Localized>{'Note'}</Localized></dt><dd style={{ whiteSpace: 'pre-wrap', margin: 0 }}>{value(facts.note)}</dd></div></dl></Localized>;
}
export default async function ProductionCorrectionHistory({ kind, deploymentNo, recordNo }: {
  kind: Kind; deploymentNo: string; recordNo: string;
}) {
  const data = await apiGet<History>(`/api/v1/deployments/${encodeURIComponent(deploymentNo)}/${plural[kind]}/${encodeURIComponent(recordNo)}/history`);
  const back = <Link href={`/deployments/${encodeURIComponent(deploymentNo)}`}><Localized>{'Back to deployment'}</Localized></Link>;
  // A mismatched upstream response is not substitute evidence for this route.
  if (!data || data.kind !== kind || data.deployment_no !== deploymentNo || data.record_no !== recordNo ||
      !object(data.effective) || !validFacts(data.effective.values) || !Number.isSafeInteger(data.effective.revision) || !nullableText(data.effective.head_id) ||
      (data.recorded_baseline !== null && (!object(data.recorded_baseline) || !validFacts(data.recorded_baseline.values) || typeof data.recorded_baseline.source !== 'string' || !nullableText(data.recorded_baseline.recorded_at) || !nullableText(data.recorded_baseline.baseline_event_no))) ||
      typeof data.stored_status !== 'string' || typeof data.history_state !== 'string' || !Number.isSafeInteger(data.correction_count) || !Array.isArray(data.corrections) || data.corrections.slice(0, 50).some(row => !object(row) || !validFacts(row.values) || typeof row.id !== 'string' || !Number.isSafeInteger(row.revision) || !nullableText(row.predecessor_id) || typeof row.correction_reason !== 'string' || !nullableText(row.recorded_at) || typeof row.audit_event_no !== 'string')) {
    return <Localized><section className="panel"><h1><Localized>{'Correction history unavailable'}</Localized></h1>
      <p><Localized>{'No matching history was returned. No substitute history is shown.'}</Localized></p>{back}</section></Localized>;
  }
  const corrections = data.corrections.slice(0, 50);
  return <Localized><>
    <div className="top"><div><div className="eyebrow"><Localized>{'READ-ONLY PRODUCTION HISTORY'}</Localized></div>
      <h1><Localized>{titles[kind]}</Localized></h1><p>{data.record_no} · {data.deployment_no}</p></div></div>
    <section className="panel"><p><Localized>{'Sample read-only history. These records do not authorize writes or prove physical software changes or reversal.'}</Localized></p>
      <p><Localized>{'This is a history observation, not confirmation of a submitted command. A newer correction may exist after this read.'}</Localized></p>
      <p><Localized>{'Stored status'}</Localized>: <Localized>{data.stored_status}</Localized> · <Localized>{'History state'}</Localized>: <Localized>{data.history_state}</Localized></p></section>
    <div className="grid2"><section className="panel"><h2><Localized>{'Recorded baseline'}</Localized></h2>
      {data.recorded_baseline ? <><p><Localized>{'Baseline source'}</Localized>: <Localized>{data.recorded_baseline.source}</Localized></p>
        <p><Localized>{'Ledger recorded time'}</Localized>: {value(data.recorded_baseline.recorded_at)}</p>
        <Facts kind={kind} facts={data.recorded_baseline.values}/>
        {data.recorded_baseline.baseline_event_no && <Link href={`/activity/${encodeURIComponent(data.recorded_baseline.baseline_event_no)}`}>{data.recorded_baseline.baseline_event_no}</Link>}
      </> : <p><Localized>{'No baseline recorded. Current stored values are not a reconstructed history.'}</Localized></p>}
    </section><section className="panel"><h2><Localized>{'Effective recorded facts'}</Localized></h2>
      <p><Localized>{'Current revision'}</Localized>: {data.effective.revision}</p>
      <p><Localized>{'Current correction ID'}</Localized>: {value(data.effective.head_id)}</p>
      <Facts kind={kind} facts={data.effective.values}/></section></div>
    <section className="panel"><h2><Localized>{'Append-only corrections'}</Localized></h2>
      <p><Localized>{'Total corrections'}</Localized>: {data.correction_count} · <Localized>{'Showing latest'}</Localized>: {corrections.length}</p>
      {(data.truncated || data.correction_count > corrections.length) && <p className="muted"><Localized>{'This bounded view shows at most 50 corrections; older records are not deleted.'}</Localized></p>}
      {!corrections.length && <p><Localized>{'No correction records returned.'}</Localized></p>}
      {corrections.map(row => <article key={row.id} className="panel"><h3><Localized>{'Revision'}</Localized> {row.revision}</h3>
        <p><Localized>{'Correction ID'}</Localized>: {row.id}</p><p><Localized>{'Predecessor correction ID'}</Localized>: {value(row.predecessor_id)}</p>
        <p><Localized>{'Ledger recorded time'}</Localized>: {value(row.recorded_at)}</p>
        <p><Localized>{'Correction reason'}</Localized>: <span style={{ whiteSpace: 'pre-wrap' }}>{row.correction_reason}</span></p>
        <Facts kind={kind} facts={row.values}/><Link href={`/activity/${encodeURIComponent(row.audit_event_no)}`}>{row.audit_event_no}</Link>
      </article>)}
    </section>{kind==='batch'&&<p><Link href={`/deployments/${encodeURIComponent(deploymentNo)}/batches/${encodeURIComponent(recordNo)}/correct`} prefetch={false}><Localized>{'Open controlled batch correction workbench'}</Localized></Link></p>}<p>{back} · <Link href={`/production/${plural[kind]}`}><Localized>{'Back to production catalog'}</Localized></Link></p>
  </></Localized>;
}
