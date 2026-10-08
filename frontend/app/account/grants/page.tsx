import Link from 'next/link';
import { cookies } from 'next/headers';
import { Localized } from '../../../components/localized';
import { authConfig } from '../../../lib/browser-auth';
import { readAdminGrants, SESSION_COOKIE } from '../../../lib/browser-session';

export const dynamic = 'force-dynamic';
type Query = { scope?: string | string[]; status?: string | string[]; offset?: string | string[] };
export default async function AdminGrantsPage({ searchParams }: { searchParams: Promise<Query> }) {
  const query = await searchParams;
  const scope = query.scope ?? 'GLOBAL', status = query.status ?? '', rawOffset = query.offset ?? '0';
  const valid = typeof scope === 'string' && typeof status === 'string' &&
    typeof rawOffset === 'string' && /^(0|[1-9][0-9]{0,5})$/.test(rawOffset);
  let config = null;
  try { config = await authConfig(process.env); } catch { /* No configuration details in UI. */ }
  const result = !valid ? { state: 'invalid_filter' as const } : !config ?
    { state: 'disabled' as const } :
    await readAdminGrants(config.session, (await cookies()).get(SESSION_COOKIE)?.value,
      scope as string, status as string, Number(rawOffset));
  const currentScope = typeof scope === 'string' && ['GLOBAL', 'PROJECT', 'SOFTWARE'].includes(scope) ? scope : 'GLOBAL';
  const currentStatus = typeof status === 'string' && ['ACTIVE', 'SUSPENDED'].includes(status) ? status : '';
  const pageLink = (offset: number) => '/account/grants?' + new URLSearchParams({
    scope: currentScope, status: currentStatus, offset: String(offset) });
  return <Localized><div className="top"><div>
    <h1><Localized>{'Grant administration'}</Localized></h1>
    <p className="muted"><Localized>{'Review global, project and software grants.'}</Localized></p>
  </div></div>
  <section className="panel">
    <form method="get" action="/account/grants">
      <label><Localized>{'Grant scope'}</Localized><select name="scope" defaultValue={currentScope}>
        <option value="GLOBAL"><Localized>{'GLOBAL'}</Localized></option>
        <option value="PROJECT"><Localized>{'PROJECT'}</Localized></option>
        <option value="SOFTWARE"><Localized>{'SOFTWARE'}</Localized></option>
      </select></label>
      <label><Localized>{'Grant status'}</Localized><select name="status" defaultValue={currentStatus}>
        <option value=""><Localized>{'All statuses'}</Localized></option>
        <option value="ACTIVE"><Localized>{'ACTIVE'}</Localized></option>
        <option value="SUSPENDED"><Localized>{'SUSPENDED'}</Localized></option>
      </select></label>
      <button className="btn" type="submit"><Localized>{'Apply filters'}</Localized></button>
    </form>
    <Localized>{result.state === 'disabled' && <p><Localized>{'Login is not available in this environment.'}</Localized></p>}</Localized>
    <Localized>{result.state === 'session_required' && <p><Localized>{'Sign in again to review grants.'}</Localized><Link href="/account"><Localized>{'Account'}</Localized></Link></p>}</Localized>
    <Localized>{result.state === 'forbidden' && <p role="alert"><Localized>{'Administrator permission is required.'}</Localized></p>}</Localized>
    <Localized>{result.state === 'invalid_filter' && <p role="alert"><Localized>{'Invalid grant filters.'}</Localized></p>}</Localized>
    <Localized>{result.state === 'unavailable' && <p role="alert"><Localized>{'Grant information is unavailable. Please retry.'}</Localized></p>}</Localized>
    <Localized>{result.state === 'ready' && <>
      <p><Link href="/account/grants/new"><Localized>{'Prepare identity or grant registration'}</Localized></Link></p>
      <p><Localized>{'Total grants'}</Localized><Localized>{': '}</Localized><Localized>{result.total}</Localized></p>
      <Localized>{result.items.length === 0 && <p><Localized>{'No grants match these filters.'}</Localized></p>}</Localized>
      <div style={{ overflowX: 'auto' }}><table><thead><tr>
        <th><Localized>{'Principal'}</Localized></th><th><Localized>{'Target'}</Localized></th>
        <th><Localized>{'Role'}</Localized></th><th><Localized>{'Grant status'}</Localized></th>
        <th><Localized>{'Effective grant'}</Localized></th>
      </tr></thead><tbody><Localized>{result.items.map(row => <tr key={row.id}>
        <td><Localized>{row.principal.display_name}</Localized><br/><Localized>{row.principal.id}</Localized>
          <br/><Localized>{row.principal.status}</Localized></td>
        <td><Localized>{row.target ? row.target.code + ' · ' + row.target.name : 'GLOBAL'}</Localized></td>
        <td><Localized>{row.role}</Localized><br/><Link href={'/account/grants/' + row.scope + '/' + row.id}><Localized>{row.id}</Localized></Link></td>
        <td><Localized>{row.status}</Localized></td>
        <td><Localized>{row.effective ? 'Effective' : 'Not effective'}</Localized></td>
      </tr>)}</Localized></tbody></table></div>
      <p><Localized>{Number(rawOffset) > 0 && <Link href={pageLink(Math.max(0, Number(rawOffset) - 10))}><Localized>{'Previous page'}</Localized></Link>}</Localized>
      <Localized>{result.next_offset !== null && <Link href={pageLink(result.next_offset)}><Localized>{'Next page'}</Localized></Link>}</Localized></p>
      <p className="muted"><Localized>{'A grant row does not describe all effective permissions.'}</Localized></p>
    </>}</Localized>
  </section></Localized>;
}
