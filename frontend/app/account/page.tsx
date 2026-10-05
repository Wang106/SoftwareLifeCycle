import { cookies } from 'next/headers';
import { Localized } from '../../components/localized';
import { authConfig } from '../../lib/browser-auth';
import { resolveSession, SESSION_COOKIE } from '../../lib/browser-session';

export const dynamic = 'force-dynamic';
export default async function AccountPage({ searchParams }: { searchParams: Promise<{ auth?: string }> }) {
  let config = null;
  try { config = await authConfig(process.env); } catch { /* Render the disabled state without configuration details. */ }
  const identity = config ? await resolveSession(config.session, (await cookies()).get(SESSION_COOKIE)?.value) : null;
  const auth = (await searchParams).auth;
  const failed = auth === 'failed';
  return <>
    <div className="top"><div><div className="eyebrow"><Localized>{'ACCOUNT'}</Localized></div>
      <h1><Localized>{'Account and session'}</Localized></h1>
      <p className="muted"><Localized>{'Use your organization account to sign in.'}</Localized></p>
    </div></div>
    <section className="panel">
      <Localized>{failed && <p role="alert"><Localized>{'Sign-in failed. Please try again.'}</Localized></p>}</Localized>
      <Localized>{auth === 'logout_failed' && <p role="alert"><Localized>{'Sign-out could not be confirmed. Please retry signing out.'}</Localized></p>}</Localized>
      <Localized>{!config ? <p><Localized>{'Login is not available in this environment.'}</Localized></p> :
        identity ? <>
          <h2><Localized>{'Signed in'}</Localized></h2>
          <p><Localized>{identity.principal.display_name}</Localized></p>
          <p className="muted"><Localized>{identity.principal.id}</Localized></p>
          <p><Localized>{'Active global grants'}</Localized><Localized>{': '}</Localized><Localized>{identity.active_grant_counts.GLOBAL}</Localized></p>
          <p><Localized>{'Active project memberships'}</Localized><Localized>{': '}</Localized><Localized>{identity.active_grant_counts.PROJECT}</Localized></p>
          <p><Localized>{'Active software memberships'}</Localized><Localized>{': '}</Localized><Localized>{identity.active_grant_counts.SOFTWARE}</Localized></p>
          <Localized>{identity.read_only_mode && <p className="muted"><Localized>{'This environment is read-only.'}</Localized></p>}</Localized>
          <p className="muted"><Localized>{'Signing out ends this browser session. Your organization account may remain signed in.'}</Localized></p>
          <form method="post" action="/auth/logout"><button type="submit" className="btn"><Localized>{'Sign out'}</Localized></button></form>
        </> : <>
          <h2><Localized>{'Signed out'}</Localized></h2>
          <p className="muted"><Localized>{'If your session expired, sign in again.'}</Localized></p>
          <form method="post" action="/auth/login"><button type="submit" className="btn"><Localized>{'Sign in'}</Localized></button></form>
        </>}</Localized>
    </section>
  </>;
}
