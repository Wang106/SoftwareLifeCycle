import Link from 'next/link';
import GrantStatusPreparation from '../../../../../components/grant-status-preparation';
import { cookies } from 'next/headers';
import { Localized } from '../../../../../components/localized';
import { authConfig, grantSubmissionConfigured } from '../../../../../lib/browser-auth';
import { readAdminGrantDetail, SESSION_COOKIE } from '../../../../../lib/browser-session';

export const dynamic = 'force-dynamic';
export default async function GrantDetailPage({ params, searchParams }: {
  params: Promise<{ scope: string; id: string }>;
  searchParams: Promise<{ offset?: string | string[] }>;
}) {
  const { scope, id } = await params, query = await searchParams;
  const raw = query.offset ?? '0';
  let config = null;
  try { config = await authConfig(process.env); } catch { /* Hide configuration details. */ }
  const valid = typeof raw === 'string' && /^(0|[1-9][0-9]{0,5})$/.test(raw);
  const result = !valid ? { state: 'invalid_filter' as const } :
    !config ? { state: 'disabled' as const } :
    await readAdminGrantDetail(config.session, (await cookies()).get(SESSION_COOKIE)?.value,
      scope, id, Number(raw));
  const pageLink = (offset: number) => '/account/grants/' + encodeURIComponent(scope) + '/' +
    encodeURIComponent(id) + '?offset=' + offset;
  return <Localized><div className="top"><div>
    <h1><Localized>{'Grant detail and status history'}</Localized></h1>
    <Link href="/account/grants"><Localized>{'Grant administration'}</Localized></Link>
  </div></div><section className="panel">
    <Localized>{result.state === 'disabled' && <p><Localized>{'Login is not available in this environment.'}</Localized></p>}</Localized>
    <Localized>{result.state === 'session_required' && <p><Localized>{'Sign in again to review grants.'}</Localized><Link href="/account"><Localized>{'Account'}</Localized></Link></p>}</Localized>
    <Localized>{result.state === 'forbidden' && <p role="alert"><Localized>{'Administrator permission is required.'}</Localized></p>}</Localized>
    <Localized>{result.state === 'not_found' && <p role="alert"><Localized>{'Grant not found.'}</Localized></p>}</Localized>
    <Localized>{result.state === 'invalid_filter' && <p role="alert"><Localized>{'Invalid grant filters.'}</Localized></p>}</Localized>
    <Localized>{result.state === 'unavailable' && <p role="alert"><Localized>{'Grant information is unavailable. Please retry.'}</Localized></p>}</Localized>
    <Localized>{result.state === 'ready' && <>
      <h2><Localized>{result.grant.principal.display_name}</Localized></h2>
      <p><Localized>{result.grant.principal.id}</Localized></p>
      <p><Localized>{result.grant.scope}</Localized><Localized>{': '}</Localized><Localized>{result.grant.role}</Localized></p>
      <p><Localized>{result.grant.id}</Localized></p>
      <Localized>{result.grant.target && <p><Localized>{result.grant.target.code}</Localized><Localized>{' · '}</Localized>
        <Localized>{result.grant.target.name}</Localized><Localized>{' · '}</Localized><Localized>{result.grant.target.id}</Localized></p>}</Localized>
      <p><Localized>{'Grant status'}</Localized><Localized>{': '}</Localized><Localized>{result.grant.status}</Localized></p>
      <p><Localized>{'Effective grant'}</Localized><Localized>{': '}</Localized><Localized>{result.grant.effective ? 'Effective' : 'Not effective'}</Localized></p>
      <GrantStatusPreparation key={[result.grant.scope, result.grant.id, result.grant.principal.id,
        result.grant.role].join(':')}
        submissionEnabled={grantSubmissionConfigured(process.env, config) && !result.read_only_mode}
        target={{ id: result.grant.id, scope: result.grant.scope, status: result.grant.status,
          historyStatus: result.current_status, role: result.grant.role, principalId: result.grant.principal.id }} />
      <h2><Localized>{'Status change history'}</Localized></h2>
      <p><Localized>{'History read status'}</Localized><Localized>{': '}</Localized><Localized>{result.current_status}</Localized></p>
      <p className="muted"><Localized>{'Detail and history are separate reads; concurrent changes may show different statuses.'}</Localized></p>
      <p><Localized>{'Total status events'}</Localized><Localized>{': '}</Localized><Localized>{result.total}</Localized></p>
      <p className="muted"><Localized>{'Only recorded grant status changes are shown. Empty history does not prove that this grant was never changed.'}</Localized></p>
      <Localized>{result.items.length === 0 && <p><Localized>{'No status events on this page.'}</Localized></p>}</Localized>
      <div style={{ overflowX: 'auto' }}><table><thead><tr>
        <th><Localized>{'Event'}</Localized></th><th><Localized>{'Time'}</Localized></th>
        <th><Localized>{'Actor'}</Localized></th><th><Localized>{'Before'}</Localized></th>
        <th><Localized>{'After'}</Localized></th><th><Localized>{'Reason'}</Localized></th>
      </tr></thead><tbody><Localized>{result.items.map(event => <tr key={event.id}>
        <td><Localized>{event.event_no}</Localized><br/><Localized>{event.id}</Localized><br/><Localized>{event.action}</Localized></td>
        <td><Localized>{event.occurred_at}</Localized></td>
        <td><Localized>{event.actor_display_name ?? 'Unknown'}</Localized><br/><Localized>{event.actor_principal_id ?? ''}</Localized></td>
        <td><Localized>{event.expected_status ?? 'Unknown'}</Localized></td>
        <td><Localized>{event.status ?? 'Unknown'}</Localized></td>
        <td><Localized>{event.reason ?? ''}</Localized><Localized>{event.reason_truncated && <span><Localized>{'Reason truncated'}</Localized></span>}</Localized></td>
      </tr>)}</Localized></tbody></table></div>
      <p><Localized>{Number(raw) > 0 && <Link href={pageLink(Math.max(0, Number(raw) - 10))}><Localized>{'Previous page'}</Localized></Link>}</Localized>
        <Localized>{result.next_offset !== null && <Link href={pageLink(result.next_offset)}><Localized>{'Next page'}</Localized></Link>}</Localized></p>
    </>}</Localized>
  </section></Localized>;
}
