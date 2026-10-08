import Link from 'next/link';
import { cookies } from 'next/headers';
import { Localized } from '../../../components/localized';
import { authConfig } from '../../../lib/browser-auth';
import { readAdminPrincipals, SESSION_COOKIE } from '../../../lib/browser-session';

export const dynamic = 'force-dynamic';
type Query = { principal_id?: string | string[]; principal_type?: string | string[];
  status?: string | string[]; offset?: string | string[] };
export default async function PrincipalCatalogPage({ searchParams }: { searchParams: Promise<Query> }) {
  const query = await searchParams;
  const id = query.principal_id ?? '', kind = query.principal_type ?? '', status = query.status ?? '', raw = query.offset ?? '0';
  const valid = [id, kind, status, raw].every(v => typeof v === 'string') &&
    /^(0|[1-9][0-9]{0,5})$/.test(raw as string) &&
    Object.keys(query).every(key => ['principal_id', 'principal_type', 'status', 'offset'].includes(key));
  let config = null;
  try { config = await authConfig(process.env); } catch { /* Hide configuration details. */ }
  const result = !valid ? { state: 'invalid_filter' as const } : !config ? { state: 'disabled' as const } :
    await readAdminPrincipals(config.session, (await cookies()).get(SESSION_COOKIE)?.value,
      id as string, kind as string, status as string, Number(raw));
  const pageLink = (offset: number) => '/account/principals?'+new URLSearchParams({
    principal_id: id as string, principal_type: kind as string, status: status as string, offset: String(offset) });
  return <Localized><div className="top"><div>
    <h1><Localized>{'Identity administration'}</Localized></h1>
    <p className="muted"><Localized>{'Review local identities, including disabled identities without grants.'}</Localized></p>
    <Link href="/account"><Localized>{'Account'}</Localized></Link>
  </div></div><section className="panel">
    <Localized>{result.state === 'disabled' && <p><Localized>{'Login is not available in this environment.'}</Localized></p>}</Localized>
    <Localized>{result.state === 'session_required' && <p><Localized>{'Sign in again to review identities.'}</Localized></p>}</Localized>
    <Localized>{result.state === 'forbidden' && <p role="alert"><Localized>{'Administrator permission is required.'}</Localized></p>}</Localized>
    <Localized>{result.state === 'not_found' && <p role="alert"><Localized>{'Identity information is unavailable. Please retry.'}</Localized></p>}</Localized>
    <Localized>{result.state === 'invalid_filter' && <p role="alert"><Localized>{'Invalid identity filters.'}</Localized>
      <Link href="/account/principals"><Localized>{'Reset filters'}</Localized></Link></p>}</Localized>
    <Localized>{result.state === 'unavailable' && <p role="alert"><Localized>{'Identity information is unavailable. Please retry.'}</Localized></p>}</Localized>
    <Localized>{result.state === 'ready' && <>
      <form method="get" action="/account/principals">
        <label><Localized>{'Principal UUID'}</Localized><input name="principal_id" defaultValue={id as string} maxLength={36}/></label>
        <label><Localized>{'Principal type'}</Localized><select name="principal_type" defaultValue={kind as string}>
          <option value=""><Localized>{'All types'}</Localized></option>
          <option value="USER"><Localized>{'USER'}</Localized></option>
          <option value="SERVICE"><Localized>{'SERVICE'}</Localized></option>
        </select></label>
        <label><Localized>{'Principal status'}</Localized><select name="status" defaultValue={status as string}>
          <option value=""><Localized>{'All statuses'}</Localized></option>
          <option value="ACTIVE"><Localized>{'ACTIVE'}</Localized></option>
          <option value="DISABLED"><Localized>{'DISABLED'}</Localized></option>
        </select></label>
        <button type="submit" className="btn"><Localized>{'Apply filters'}</Localized></button>
      </form>
      <p><Link href="/account/grants/new"><Localized>{'Prepare identity or grant registration'}</Localized></Link></p>
      <p><Localized>{'Total identities'}</Localized><Localized>{': '}</Localized><Localized>{result.total}</Localized></p>
      <Localized>{result.items.length === 0 && <p><Localized>{'No identities match these filters.'}</Localized></p>}</Localized>
      <div style={{overflowX:'auto'}}><table><thead><tr>
        <th><Localized>{'Principal'}</Localized></th><th><Localized>{'Principal type'}</Localized></th>
        <th><Localized>{'Principal status'}</Localized></th><th><Localized>{'Administrator protection'}</Localized></th>
        <th><Localized>{'Configured issuer match'}</Localized></th>
      </tr></thead><tbody><Localized>{result.items.map(row => <tr key={row.id}>
        <td><Localized>{row.display_name}</Localized><br/><Link href={'/account/principals/'+row.id}><Localized>{row.id}</Localized></Link></td>
        <td><Localized>{row.principal_type}</Localized></td><td><Localized>{row.status}</Localized></td>
        <td><Localized>{row.admin_principal_protected ? 'Protected administrator identity' : 'No administrator assignment observed'}</Localized></td>
        <td><Localized>{row.issuer_matches_configuration ? 'Matches configuration' : 'Does not match configuration'}</Localized></td>
      </tr>)}</Localized></tbody></table></div>
      <p><Localized>{Number(raw)>0 && <Link href={pageLink(Math.max(0,Number(raw)-10))}><Localized>{'Previous page'}</Localized></Link>}</Localized>
        <Localized>{result.next_offset!==null && <Link href={pageLink(result.next_offset)}><Localized>{'Next page'}</Localized></Link>}</Localized></p>
      <Localized>{result.navigation_limited && <p><Localized>{'Page navigation stops at the API offset limit. Narrow the filters.'}</Localized></p>}</Localized>
      <p className="muted"><Localized>{'Issuer matching and administrator protection are read snapshots, not permission to change an identity.'}</Localized></p>
    </>}</Localized>
  </section></Localized>;
}
