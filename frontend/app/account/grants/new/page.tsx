import Link from 'next/link';
import { cookies } from 'next/headers';
import AdminRegistrationPreparation from '../../../../components/admin-registration-preparation';
import { Localized } from '../../../../components/localized';
import { authConfig, registrationSubmissionConfigured } from '../../../../lib/browser-auth';
import { readAdminGrants, SESSION_COOKIE } from '../../../../lib/browser-session';

export const dynamic = 'force-dynamic';
export default async function RegistrationPage() {
  let config = null;
  try { config = await authConfig(process.env); } catch { /* Never expose provider configuration. */ }
  // Reuse the private backend-admin read; grant counts cannot authorize this page.
  const result = !config ? {state:'disabled' as const} :
    await readAdminGrants(config.session,(await cookies()).get(SESSION_COOKIE)?.value,'GLOBAL','',0);
  return <Localized><div className="top"><div>
    <h1><Localized>{'Identity and grant registration preparation'}</Localized></h1>
    <Link href="/account/grants"><Localized>{'Grant administration'}</Localized></Link>
  </div></div><section className="panel">
    <Localized>{result.state==='disabled' && <p><Localized>{'Login is not available in this environment.'}</Localized></p>}</Localized>
    <Localized>{result.state==='session_required' && <p><Localized>{'Sign in again to review grants.'}</Localized>
      <Link href="/account"><Localized>{'Account'}</Localized></Link></p>}</Localized>
    <Localized>{result.state==='forbidden' && <p role="alert"><Localized>{'Administrator permission is required.'}</Localized></p>}</Localized>
    <Localized>{(result.state==='unavailable' || result.state==='invalid_filter') && <p role="alert">
      <Localized>{'Grant information is unavailable. Please retry.'}</Localized></p>}</Localized>
    <Localized>{result.state==='ready' && <AdminRegistrationPreparation submissionEnabled={registrationSubmissionConfigured(process.env,config) && !result.read_only_mode} />}</Localized>
  </section></Localized>;
}
