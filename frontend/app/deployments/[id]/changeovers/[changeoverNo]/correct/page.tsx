import {cookies} from 'next/headers';
import Link from 'next/link';
import {authConfig,changeoverCorrectionSubmissionConfigured} from '../../../../../../lib/browser-auth';
import {resolveSession,SESSION_COOKIE} from '../../../../../../lib/browser-session';
import ChangeoverCorrectionWorkbench from '../../../../../../components/changeover-correction-workbench';
import {Localized} from '../../../../../../components/localized';
export const dynamic='force-dynamic';
export default async function Page({params}:{params:Promise<{id:string;changeoverNo:string}>}){
  const {id,changeoverNo}=await params;
  let config=null;
  try{config=await authConfig(process.env);}catch{ /* Do not expose credentials or configuration failures. */ }
  const configured=changeoverCorrectionSubmissionConfigured(process.env,config);
  const values=configured?(await cookies()).getAll(SESSION_COOKIE):[];
  const identity=configured&&config&&values.length===1?await resolveSession(config.session,values[0].value):null;
  const enabled=configured&&identity?.principal.principal_type==='USER';
  return <Localized><>
    <h1><Localized>{'Changeover correction workbench'}</Localized></h1>
    <ChangeoverCorrectionWorkbench deploymentNo={id} changeoverNo={changeoverNo} contextEnabled={enabled}
      submissionEnabled={enabled&&identity?.read_only_mode===false} recoveryEnabled={enabled}/>
    <Link href={`/deployments/${encodeURIComponent(id)}/changeovers/${encodeURIComponent(changeoverNo)}/history`} prefetch={false}><Localized>{'Back to recorded changeover history'}</Localized></Link>
  </></Localized>;
}
