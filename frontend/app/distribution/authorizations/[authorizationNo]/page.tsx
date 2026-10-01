
import { Localized, LocalizedAttributes } from "../../../../components/localized";
import Link from 'next/link';
import { apiGet } from '../../../../lib/api';

type AuthorizationDetail = {
  id: string; authorization_no: string; status: string;
  release: { id: string; version: string; type: string } | null;
  snapshot: { id: string; snapshot_no: string; content_hash: string } | null;
  customer: { id: string; code: string; name: string } | null;
  project: { id: string; code: string; name: string } | null;
  distribution: { id: string; distribution_no: string; status: string; package_no: string | null; package_revision: number | null } | null;
  site_code: string; line_code: string; purpose: string;
  batch_limit: number | null; restriction_note: string | null; approved_at: string | null;
  history_counts: { deployments: number; batches: number };
  notice: string;
};

export default async function Page({ params }: { params: Promise<{ authorizationNo: string }> }) {
  const { authorizationNo } = await params;
  const authorization = await apiGet<AuthorizationDetail>(`/api/v1/authorizations/${encodeURIComponent(authorizationNo)}/profile`);
  if (!authorization) return <section className="panel"><h1><Localized>{"Authorization unavailable"}</Localized></h1>
    <p className="muted"><Localized>{"This authorization was not found or the API is unavailable."}</Localized></p>
    <Link href="/distribution/authorizations"><Localized>{"← All authorizations"}</Localized></Link></section>;

  const distribution = authorization.distribution;
  const deliveryHref = distribution?.package_no && distribution.package_revision
    ? `/distribution/deliveries/${encodeURIComponent(distribution.package_no)}/${distribution.package_revision}` : null;
  return <>
    <div className="top"><div><div className="eyebrow"><Localized>{"PRODUCTION GOVERNANCE"}</Localized></div><h1><Localized>{authorization.authorization_no}</Localized></h1>
      <p className="muted"><Localized>{"Authorization for a specified release, snapshot, customer, site and line."}</Localized></p></div>
      <span className={'status ' + (authorization.status === 'APPROVED' ? 'pass' : 'warning')}><Localized>{authorization.status}</Localized></span></div>
    <p><Link href={`/commands?${new URLSearchParams({operation: 'deployment', target: authorization.id})}`}><Localized>{"Prepare deployment expectation →"}</Localized></Link><Localized>{" · Review exact current approved scope first."}</Localized></p>
    <div className="grid2">
      <section className="panel"><h2><Localized>{"Authorized scope"}</Localized></h2><div className="kv">
        <span><Localized>{"Customer UUID"}</Localized></span><b><Localized>{authorization.customer?.id || 'Unavailable'}</Localized></b>
        <span><Localized>{"Project UUID"}</Localized></span><b><Localized>{authorization.project?.id || 'Unavailable'}</Localized></b>
        <span><Localized>{"Application release UUID"}</Localized></span><b><Localized>{authorization.release?.id || 'Unavailable'}</Localized></b>
        <span><Localized>{"Customer"}</Localized></span><b><Localized>{authorization.customer ? `${authorization.customer.name} · ${authorization.customer.code}` : '—'}</Localized></b>
        <span><Localized>{"Project"}</Localized></span><b><Localized>{authorization.project ? `${authorization.project.name} · ${authorization.project.code}` : '—'}</Localized></b>
        <span><Localized>{"Release"}</Localized></span><b><Localized>{authorization.release ? <Link href={authorization.release.type === 'APPLICATION' ? `/releases/application/${authorization.release.id}` : '/releases/application'}><Localized>{authorization.release.type}</Localized> <Localized>{authorization.release.version}</Localized></Link> : '—'}</Localized></b>
        <span><Localized>{"Snapshot"}</Localized></span><b><Localized>{authorization.snapshot?.snapshot_no || '—'}</Localized></b>
        <span><Localized>{"Site / line"}</Localized></span><b><Localized>{authorization.site_code}</Localized><Localized>{" / "}</Localized><Localized>{authorization.line_code}</Localized></b>
        <span><Localized>{"Purpose"}</Localized></span><b><Localized>{authorization.purpose}</Localized></b>
      </div></section>
      <section className="panel"><h2><Localized>{"Distribution prerequisite"}</Localized></h2>
        <Localized>{distribution ? <div className="kv">
          <span><Localized>{"Delivery"}</Localized></span><b><Localized>{deliveryHref ? <Link href={deliveryHref}><Localized>{distribution.package_no}</Localized><Localized>{" Rev"}</Localized><Localized>{distribution.package_revision}</Localized></Link> : 'Missing delivery link'}</Localized></b>
          <span><Localized>{"Distribution"}</Localized></span><b><Link href={`/distribution/distributions/${encodeURIComponent(distribution.distribution_no)}`}><Localized>{distribution.distribution_no}</Localized></Link></b>
          <span><Localized>{"Distribution status"}</Localized></span><b><Localized>{distribution.status}</Localized></b>
        </div> : <p className="muted"><Localized>{"No distribution linked to this authorization."}</Localized></p>}</Localized>
        <code className="hash">{authorization.snapshot?.content_hash || 'No snapshot hash'}</code>
      </section>
    </div>
    <section className="panel"><h2><Localized>{"Restrictions and batch usage"}</Localized></h2>
      <p><Localized>{authorization.restriction_note || 'No restriction note recorded.'}</Localized></p>
      <div className="kv"><span><Localized>{"Approved at"}</Localized></span><b><Localized>{authorization.approved_at ? new Date(authorization.approved_at).toISOString().slice(0, 16).replace('T', ' ') + ' UTC' : '—'}</Localized></b>
        <span><Localized>{"Batch limit"}</Localized></span><b><Localized>{authorization.batch_limit ?? 'No limit recorded'}</Localized></b>
        <span><Localized>{"Recorded batches"}</Localized></span><b><Localized>{authorization.history_counts.batches}</Localized></b>
        <span><Localized>{"Unfilled slots (count only)"}</Localized></span><b><Localized>{authorization.batch_limit === null ? 'No limit recorded' : Math.max(0, authorization.batch_limit - authorization.history_counts.batches)}</Localized></b>
      </div>
    </section>
    <section className="panel"><h2><Localized>{"Recorded production history"}</Localized></h2>
      <p className="muted"><Localized>{authorization.notice}</Localized></p>
      <p><Link href={`/deployments?${new URLSearchParams({authorization_id: authorization.id})}`}><Localized>{authorization.history_counts.deployments}</Localized><Localized>{" recorded deployments →"}</Localized></Link></p>
      <p><Link href={`/production/batches?${new URLSearchParams({authorization_id: authorization.id})}`}><Localized>{authorization.history_counts.batches}</Localized><Localized>{" recorded batches →"}</Localized></Link></p>
      <p className="muted"><Localized>{"Review software observations and binding evidence in paginated catalogs scoped to this exact authorization."}</Localized></p>
    </section>
    <p className="datasource"><Link href="/distribution/authorizations"><Localized>{"← All authorizations"}</Localized></Link></p>
  <p><Link href={`/activity?${new URLSearchParams({entity_type: 'SOFTWARE_AUTHORIZATION', entity_id: authorization.id})}`}><Localized>{"Recorded audit events →"}</Localized></Link></p></>;
}
