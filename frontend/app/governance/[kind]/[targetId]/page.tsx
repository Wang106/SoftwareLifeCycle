import Link from 'next/link';
import { Localized } from '../../../../components/localized';
import { apiGet } from '../../../../lib/api';
import { governanceTarget, parseGovernance, RevocationRecord } from '../../../../lib/release-chain-governance';

export default async function Page({ params }: { params: Promise<{kind: string; targetId: string}> }) {
  const {kind, targetId} = await params;
  const target = governanceTarget(kind, targetId);
  const raw = target ? await apiGet<unknown>(`/api/v1/governance/${target.kind}/${target.id}`, {timeoutMs: 10000}) : null;
  const observation = target ? parseGovernance(raw, target.kind) : null;
  if (!target || !observation) return <section className="panel">
    <h1><Localized>{'Governance observation unavailable'}</Localized></h1>
    <p><Localized>{'The exact target or a valid governance response could not be confirmed. No active authority is inferred.'}</Localized></p>
  </section>;
  const events: {relation: string; event: RevocationRecord}[] = [
    ...(observation.self_revocation ? [{relation: 'Exact target revocation', event: observation.self_revocation}] : []),
    ...observation.ancestor_revocations.map(event => ({relation: 'Ancestor revocation', event})),
  ];
  return <Localized><>
    <section className="panel">
      <h1><Localized>{'Release-chain governance'}</Localized></h1>
      <div className="kv">
        <span><Localized>{'Target kind'}</Localized></span><b><Localized>{target.kind}</Localized></b>
        <span><Localized>{'Exact target UUID'}</Localized></span><code>{target.id}</code>
        <span><Localized>{'Recorded object status'}</Localized></span><b><Localized>{observation.recorded_status ?? 'Unavailable'}</Localized></b>
        <span><Localized>{'Current governance observation'}</Localized></span>
        <b><Localized>{observation.governance_state}</Localized></b>
      </div>
      <p className="muted"><Localized>{'ACTIVE means no revocation was observed on this path. It does not establish approval, readiness or permission to submit new work.'}</Localized></p>
      <p className="muted"><Localized>{'Revocation ends future authority. Existing delivery and production facts remain historical records; it does not recall files or reverse physical flashing.'}</Localized></p>
      <p><Link prefetch={false} href={`/governance/${target.kind.toLowerCase()}/${target.id}`}><Localized>{'Read again'}</Localized></Link></p>
    </section>
    <section className="panel tablewrap">
      <h2><Localized>{'Revocation records on this authority path'}</Localized></h2>
      <p className="muted"><Localized>{'Only the exact target and its ancestors are included, with at most four permanent records. Descendant events are not included.'}</Localized></p>
      {observation.governance_state === 'UNRESOLVED' ? <p><Localized>{'Authority ancestry is unresolved. Empty records do not confirm an active path.'}</Localized></p> :
        events.length === 0 ? <p><Localized>{'No revocation recorded on this path.'}</Localized></p> :
          <table><thead><tr>
            <th><Localized>{'Relationship'}</Localized></th><th><Localized>{'Revoked target kind'}</Localized></th>
            <th><Localized>{'Revocation record'}</Localized></th><th><Localized>{'Reason'}</Localized></th>
            <th><Localized>{'Recorded by'}</Localized></th><th><Localized>{'Recorded at (UTC)'}</Localized></th>
            <th><Localized>{'Audit'}</Localized></th>
          </tr></thead><tbody>{events.map(({relation, event}) => <tr key={event.id}>
            <td><Localized>{relation}</Localized></td><td><Localized>{event.target_kind}</Localized></td>
            <td><code>{event.revocation_no}</code><div><code>{event.id}</code></div></td>
            <td style={{whiteSpace: 'pre-wrap', overflowWrap: 'anywhere'}}>{event.reason}</td>
            <td>{event.revoked_by}</td><td>{new Date(event.revoked_at).toISOString()}</td>
            <td><Link prefetch={false} href={`/activity/EVT-RCR-${event.id.replaceAll('-', '').toLowerCase()}`}><Localized>{'Original audit event →'}</Localized></Link></td>
          </tr>)}</tbody></table>}
      <p className="muted"><Localized>{'These are current read observations. The original audit event records the operation; this page is not a submission receipt.'}</Localized></p>
    </section>
  </></Localized>;
}
