import {cookies} from 'next/headers';
import Link from 'next/link';
import {authConfig,batchCorrectionSubmissionConfigured} from '../../../../../../lib/browser-auth';
import {resolveSession,SESSION_COOKIE} from '../../../../../../lib/browser-session';
import BatchCorrectionWorkbench from '../../../../../../components/batch-correction-workbench';
import {Localized} from '../../../../../../components/localized';
export const dynamic='force-dynamic';
export default async function Page({params}:{params:Promise<{id:string;batchNo:string}>}){
  const {id,batchNo}=await params;
  let config=null;
  try{config=await authConfig(process.env);}catch{ /* Do not expose credentials or configuration failures. */ }
  const configured=batchCorrectionSubmissionConfigured(process.env,config);
  const values=configured?(await cookies()).getAll(SESSION_COOKIE):[];
  const identity=configured&&config&&values.length===1?await resolveSession(config.session,values[0].value):null;
  const enabled=configured&&identity?.principal.principal_type==='USER';
  return <Localized><>
    <h1><Localized>{'Batch correction workbench'}</Localized></h1>
    <BatchCorrectionWorkbench deploymentNo={id} batchNo={batchNo} contextEnabled={enabled}
      submissionEnabled={enabled&&identity?.read_only_mode===false} recoveryEnabled={enabled}/>
    <Link href={`/deployments/${encodeURIComponent(id)}/batches/${encodeURIComponent(batchNo)}/history`} prefetch={false}><Localized>{'Back to recorded batch history'}</Localized></Link>
  </></Localized>;
}
