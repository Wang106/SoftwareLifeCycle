
import { Localized, LocalizedAttributes } from "../../../../../components/localized";
import Link from 'next/link';
import { apiGet } from '../../../../../lib/api';

type DeliveryDetail = {
  id: string; package_no: string; revision: number; status: string;
  release: { id: string; version: string; type: string } | null;
  snapshot: { id: string; snapshot_no: string; content_hash: string; status: string } | null;
  recipient: { type: string; code: string; name: string };
  purpose: string; created_by: string | null;
  history_counts: { artifacts: number; distributions: number };
  policy_counts: Record<string, number>; control_reference_count: number;
};
type ArtifactPage = { total: number; next_offset: number | null;
  items: { id: string; snapshot_artifact_id: string; filename: string | null; artifact_type: string | null; sha256: string | null;
    distribution_level: string | null; policy_decision: string; control_reference: string | null }[];
};

export default async function Page({ params, searchParams }: {
  params: Promise<{ packageNo: string; revision: string }>;
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const { packageNo, revision } = await params;
  const number = Number(revision);
  const endpoint = `/api/v1/deliveries/${encodeURIComponent(packageNo)}/revisions/${number}`;
  const delivery = Number.isSafeInteger(number) && number > 0
    ? await apiGet<DeliveryDetail>(`${endpoint}/profile`)
    : null;
  if (!delivery) return <section className="panel"><h1><Localized>{"Delivery unavailable"}</Localized></h1>
    <p className="muted"><Localized>{"This package revision was not found or the delivery API is unavailable."}</Localized></p>
    <Link href="/distribution/deliveries"><Localized>{"← All deliveries"}</Localized></Link></section>;

  const search = await searchParams;
  const query = new URLSearchParams();
  for (const key of ['limit', 'offset']) {
    if (typeof search[key] === 'string') query.set(key, search[key]);
    else if (search[key] !== undefined) query.set(key, 'invalid');
  }
  const artifacts = await apiGet<ArtifactPage>(`${endpoint}/artifacts?${query}`);
  const path = `/distribution/deliveries/${encodeURIComponent(packageNo)}/${number}`;
  const first = new URLSearchParams(query); first.delete('offset');
  const next = new URLSearchParams(query);
  if (artifacts?.next_offset !== null && artifacts?.next_offset !== undefined) next.set('offset', String(artifacts.next_offset));
  return <>
    <div className="top"><div><div className="eyebrow"><Localized>{"DELIVERY · "}</Localized><Localized>{delivery.package_no}</Localized></div>
      <h1><Localized>{"Delivery Package Rev"}</Localized><Localized>{delivery.revision}</Localized></h1>
      <p className="muted"><Localized>{"Artifacts and policy decisions recorded for this exact revision."}</Localized></p></div>
      <span className={'status ' + (delivery.status === 'DISTRIBUTED' ? 'pass' : 'warning')}><Localized>{delivery.status}</Localized></span></div>
    <div className="grid2">
      <section className="panel"><h2><Localized>{"Delivery context"}</Localized></h2><div className="kv">
        <span><Localized>{"Exact package UUID"}</Localized></span><b><Localized>{delivery.id}</Localized></b>
        <span><Localized>{"Recipient type"}</Localized></span><b><Localized>{delivery.recipient.type}</Localized></b>
        <span><Localized>{"Recipient"}</Localized></span><b><Localized>{delivery.recipient.name}</Localized><Localized>{" · "}</Localized><Localized>{delivery.recipient.code}</Localized></b>
        <span><Localized>{"Purpose"}</Localized></span><b><Localized>{delivery.purpose}</Localized></b>
        <span><Localized>{"Release"}</Localized></span><b><Localized>{delivery.release ? <Link href={`/releases/${delivery.release.type === 'APPLICATION' ? 'application' : 'standard'}/${delivery.release.id}`}><Localized>{delivery.release.type}</Localized> <Localized>{delivery.release.version}</Localized></Link> : '—'}</Localized></b>
        <span><Localized>{"Snapshot"}</Localized></span><b><Localized>{delivery.snapshot?.snapshot_no || '—'}</Localized><Localized>{" · "}</Localized><Localized>{delivery.snapshot?.status || '—'}</Localized></b>
        <span><Localized>{"Created by"}</Localized></span><b><Localized>{delivery.created_by || '—'}</Localized></b>
      </div></section>
      <section className="panel"><h2><Localized>{"Frozen policy result"}</Localized></h2><div className="kv">
        <span><Localized>{"Included artifacts"}</Localized></span><b><Localized>{delivery.history_counts.artifacts}</Localized></b>
        <span><Localized>{"Allowed"}</Localized></span><b><Localized>{delivery.policy_counts.ALLOW || 0}</Localized></b>
        <span><Localized>{"Approval required"}</Localized></span><b><Localized>{delivery.policy_counts.APPROVAL_REQUIRED || 0}</Localized></b>
        <span><Localized>{"Other recorded decisions"}</Localized></span><b><Localized>{delivery.policy_counts.OTHER || 0}</Localized></b>
        <span><Localized>{"Distinct recorded controls"}</Localized></span><b><Localized>{delivery.control_reference_count}</Localized></b>
      </div><p className="muted"><Localized>{"Counts cover every recorded item in this revision. Recorded policy decisions do not grant current permission."}</Localized></p><code className="hash">{delivery.snapshot?.content_hash || '—'}</code></section>
    </div>
    <section className="panel tablewrap"><h2><Localized>{"Frozen artifact manifest"}</Localized></h2>
      <Localized>{artifacts ? <><p className="muted"><Localized>{artifacts.total}</Localized><Localized>{" recorded items · Showing "}</Localized><Localized>{artifacts.items.length}</Localized><Localized>{" on this page. Control references below apply to the displayed rows."}</Localized></p><table><thead><tr><th><Localized>{"Artifact"}</Localized></th><th><Localized>{"Type"}</Localized></th><th><Localized>{"SHA-256"}</Localized></th><th><Localized>{"Distribution level"}</Localized></th><th><Localized>{"Policy decision"}</Localized></th><th><Localized>{"Control"}</Localized></th></tr></thead>
        <tbody><Localized>{artifacts.items.map(item => <tr key={item.id}>
          <td><b><Localized>{item.filename || 'Frozen artifact metadata unavailable'}</Localized></b><div className="muted"><Localized>{"Snapshot artifact UUID: "}</Localized><Localized>{item.snapshot_artifact_id}</Localized></div></td><td><Localized>{item.artifact_type || '—'}</Localized></td><td><code>{item.sha256 || '—'}</code></td>
          <td><Localized>{item.distribution_level?.replaceAll('_', ' ') || '—'}</Localized></td>
          <td><span className={'status ' + (item.policy_decision === 'ALLOW' ? 'pass' : 'warning')}><Localized>{item.policy_decision.replaceAll('_', ' ')}</Localized></span></td>
          <td><Localized>{item.control_reference || '—'}</Localized></td>
        </tr>)}</Localized></tbody></table>
      <Localized>{artifacts.items.length === 0 && <p className="muted"><Localized>{"No artifacts on this page."}</Localized></p>}</Localized>
      <p><Localized>{search.offset !== undefined && <Link href={`${path}?${first}`}><Localized>{"First page"}</Localized></Link>}</Localized>
        <Localized>{artifacts.next_offset !== null && <Link href={`${path}?${next}`}><Localized>{" Next page →"}</Localized></Link>}</Localized></p></>
        : <p className="muted"><Localized>{"Artifact page unavailable. The API is unavailable or pagination is invalid."}</Localized></p>}</Localized>
    </section>
    <section className="panel"><h2><Localized>{"Distribution records"}</Localized></h2>
      <p><Link href={`/commands?${new URLSearchParams({operation: 'distribution', target: delivery.id})}`}><Localized>{"Prepare distribution for this exact package revision →"}</Localized></Link></p>
      <p className="muted"><Localized>{"Copy the exact recipient values above; this entry does not preselect or certify a recipient."}</Localized></p>
      <p><Link href={`/distribution/distributions?${new URLSearchParams({delivery_package_id: delivery.id})}`}><Localized>{delivery.history_counts.distributions}</Localized><Localized>{" recorded distributions →"}</Localized></Link></p>
      <p className="muted"><Localized>{"Distribution does not itself authorize production use."}</Localized></p>
    </section>
    <p className="datasource"><Link href="/distribution/deliveries"><Localized>{"← All deliveries"}</Localized></Link></p>
  <p><Link href={`/activity?${new URLSearchParams({entity_type: 'DELIVERY_PACKAGE', entity_id: delivery.id})}`}><Localized>{"Recorded audit events →"}</Localized></Link></p></>;
}
