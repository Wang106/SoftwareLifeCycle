import PrincipalStatusPreparation from '../../../../components/principal-status-preparation';
import Link from 'next/link';
import { cookies } from 'next/headers';
import { Localized } from '../../../../components/localized';
import { authConfig, principalSubmissionConfigured } from '../../../../lib/browser-auth';
import { readAdminPrincipalDetail, SESSION_COOKIE } from '../../../../lib/browser-session';

export const dynamic = 'force-dynamic';
export default async function PrincipalDetailPage({ params, searchParams }: {
  params: Promise<{ id: string }>; searchParams: Promise<{ offset?: string | string[] }>;
}) {
  const {id}=await params, query=await searchParams, raw=query.offset??'0';
  const valid=typeof raw==='string' && /^(0|[1-9][0-9]{0,5})$/.test(raw) &&
    Object.keys(query).every(key=>key==='offset');
  let config=null;
  try { config=await authConfig(process.env); } catch { /* Hide configuration details. */ }
  const result=!valid?{state:'invalid_filter' as const}:!config?{state:'disabled' as const}:
    await readAdminPrincipalDetail(config.session,(await cookies()).get(SESSION_COOKIE)?.value,id,Number(raw));
  const pageLink=(offset:number)=>'/account/principals/'+encodeURIComponent(id)+'?offset='+offset;
  return <Localized><div className="top"><div>
    <h1><Localized>{'Identity detail and status history'}</Localized></h1>
    <Link href="/account/principals"><Localized>{'Identity administration'}</Localized></Link>
  </div></div><section className="panel">
    <Localized>{result.state==='disabled' && <p><Localized>{'Login is not available in this environment.'}</Localized></p>}</Localized>
    <Localized>{result.state==='session_required' && <p><Localized>{'Sign in again to review identities.'}</Localized>
      <Link href="/account"><Localized>{'Account'}</Localized></Link></p>}</Localized>
    <Localized>{result.state==='forbidden' && <p role="alert"><Localized>{'Administrator permission is required.'}</Localized></p>}</Localized>
    <Localized>{result.state==='not_found' && <p role="alert"><Localized>{'Identity not found.'}</Localized></p>}</Localized>
    <Localized>{result.state==='invalid_filter' && <p role="alert"><Localized>{'Invalid identity filters.'}</Localized></p>}</Localized>
    <Localized>{result.state==='unavailable' && <p role="alert"><Localized>{'Identity information is unavailable. Please retry.'}</Localized></p>}</Localized>
    <Localized>{result.state==='ready' && <>
      <h2><Localized>{result.principal.display_name}</Localized></h2>
      <p><Localized>{result.principal.id}</Localized></p>
      <p><Localized>{'Principal type'}</Localized><Localized>{': '}</Localized><Localized>{result.principal.principal_type}</Localized></p>
      <p><Localized>{'Principal status'}</Localized><Localized>{': '}</Localized><Localized>{result.principal.status}</Localized></p>
      <p><Localized>{'Created at'}</Localized><Localized>{': '}</Localized><Localized>{result.principal.created_at}</Localized></p>
      <p><Localized>{result.principal.admin_principal_protected ? 'Protected administrator identity' : 'No administrator assignment observed'}</Localized></p>
      <p><Localized>{result.principal.issuer_matches_configuration ? 'Matches configuration' : 'Does not match configuration'}</Localized></p>
      <p className="muted"><Localized>{'Issuer matching and administrator protection are read snapshots, not permission to change an identity.'}</Localized></p>
      <PrincipalStatusPreparation submissionEnabled={principalSubmissionConfigured(process.env, config) && result.read_only_mode === false} target={{ id: result.principal.id, principalType: result.principal.principal_type,
        status: result.principal.status, historyStatus: result.current_status,
        protectedAdministrator: result.principal.admin_principal_protected,
        issuerMatchesConfiguration: result.principal.issuer_matches_configuration }} />
      <h2><Localized>{'Status change history'}</Localized></h2>
      <p><Localized>{'History read status'}</Localized><Localized>{': '}</Localized><Localized>{result.current_status}</Localized></p>
      <p className="muted"><Localized>{'Detail and history are separate reads; concurrent changes may show different statuses.'}</Localized></p>
      <p className="muted"><Localized>{'Only recorded identity status changes are shown. Registration and provider history are not included.'}</Localized></p>
      <p><Localized>{'Total status events'}</Localized><Localized>{': '}</Localized><Localized>{result.total}</Localized></p>
      <Localized>{result.items.length===0 && <p><Localized>{'No status events on this page.'}</Localized></p>}</Localized>
      <div style={{overflowX:'auto'}}><table><thead><tr>
        <th><Localized>{'Event'}</Localized></th><th><Localized>{'Time'}</Localized></th>
        <th><Localized>{'Actor'}</Localized></th><th><Localized>{'Before'}</Localized></th>
        <th><Localized>{'After'}</Localized></th><th><Localized>{'Reason'}</Localized></th>
      </tr></thead><tbody><Localized>{result.items.map(event=><tr key={event.id}>
        <td><Localized>{event.event_no}</Localized><br/><Localized>{event.id}</Localized><br/><Localized>{event.action}</Localized></td>
        <td><Localized>{event.occurred_at}</Localized></td>
        <td><Localized>{event.actor_display_name??'Unknown'}</Localized><br/><Localized>{event.actor_principal_id??''}</Localized></td>
        <td><Localized>{event.expected_status??'Unknown'}</Localized></td><td><Localized>{event.status??'Unknown'}</Localized></td>
        <td><Localized>{event.reason??''}</Localized><Localized>{event.reason_truncated&&<span><Localized>{'Reason truncated'}</Localized></span>}</Localized></td>
      </tr>)}</Localized></tbody></table></div>
      <p><Localized>{Number(raw)>0 && <Link href={pageLink(Math.max(0,Number(raw)-10))}><Localized>{'Previous page'}</Localized></Link>}</Localized>
        <Localized>{result.next_offset!==null && <Link href={pageLink(result.next_offset)}><Localized>{'Next page'}</Localized></Link>}</Localized></p>
      <Localized>{result.navigation_limited && <p><Localized>{'Page navigation stops at the API offset limit. Narrow the filters.'}</Localized></p>}</Localized>
    </>}</Localized>
  </section></Localized>;
}

