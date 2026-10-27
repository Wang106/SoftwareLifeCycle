import {cookies} from 'next/headers';
import Link from 'next/link';
import {authConfig,authorizationApprovalSubmissionConfigured} from '../../../../../lib/browser-auth';
import {resolveSession,SESSION_COOKIE} from '../../../../../lib/browser-session';
import AuthorizationApprovalWorkbench from '../../../../../components/authorization-approval-workbench';
import {Localized} from '../../../../../components/localized';
export const dynamic='force-dynamic';
export default async function Page({params}:{params:Promise<{authorizationNo:string}>}){
  const {authorizationNo}=await params;
  let config=null;
  try{config=await authConfig(process.env);}catch{ /* Do not expose credentials or configuration failures. */ }
  const configured=authorizationApprovalSubmissionConfigured(process.env,config);
  const values=configured?(await cookies()).getAll(SESSION_COOKIE):[];
  const identity=configured&&config&&values.length===1?await resolveSession(config.session,values[0].value):null;
  const enabled=configured&&identity?.principal.principal_type==='USER';
  return <Localized><>
    <h1><Localized>{'Authorization approval workbench'}</Localized></h1>
    <AuthorizationApprovalWorkbench authorizationNo={authorizationNo} contextEnabled={enabled}
      submissionEnabled={enabled&&identity?.read_only_mode===false} recoveryEnabled={enabled}/>
    <Link href={`/distribution/authorizations/${encodeURIComponent(authorizationNo)}`} prefetch={false}><Localized>{'Back to authorization details'}</Localized></Link>
  </></Localized>;
}
