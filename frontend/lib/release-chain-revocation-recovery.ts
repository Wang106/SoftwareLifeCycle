import {record,exactFields} from './first-command-transport';
import {parseReleaseChainRevocationCommand,confirmReleaseChainRevocation,ReleaseChainRevocationSubmission,
  type ReleaseChainRevocationCommand,type ReleaseChainRevocationReview} from './release-chain-revocation-transport';
export const releaseChainRevocationRecoveryTextLimit=49152;const format='slc-release-chain-revocation-recovery';
function validOrigin(origin:string){try{const u=new URL(origin);return u.origin===origin&&!u.username&&!u.password&&(u.protocol==='https:'||u.protocol==='http:'&&['localhost','127.0.0.1','[::1]'].includes(u.hostname));}catch{return false;}}
const envelope=(c:ReleaseChainRevocationCommand,origin:string)=>({format,version:1,origin,...c});
export function exportReleaseChainRevocationRecovery(review:ReleaseChainRevocationReview,origin:string){
  if(review.confirmed!==true||!validOrigin(origin))throw Error('invalid_recovery');
  const c=parseReleaseChainRevocationCommand(review.command);if(!c||JSON.stringify(c)!==JSON.stringify(review.command))throw Error('invalid_recovery');
  // The reason may be up to 4000 multi-byte characters, so the recovery envelope has a larger
  // bound than single-scalar command recoveries; this only carries the command, never credentials.
  const text=JSON.stringify(envelope(c,origin),null,2);
  if(new TextEncoder().encode(text).length>releaseChainRevocationRecoveryTextLimit)throw Error('invalid_recovery');
  return text;
}
export function parseReleaseChainRevocationRecovery(text:string,origin:string):ReleaseChainRevocationCommand|null{
  if(!validOrigin(origin)||typeof text!=='string'||text.length>releaseChainRevocationRecoveryTextLimit||
    new TextEncoder().encode(text).length>releaseChainRevocationRecoveryTextLimit)return null;
  try{const d=record(JSON.parse(text));
    if(!d||!exactFields(d,['format','version','origin','operation','target_kind','target_id','body'])||
      d.format!==format||d.version!==1||d.origin!==origin)return null;
    const c=parseReleaseChainRevocationCommand({operation:d.operation,target_kind:d.target_kind,target_id:d.target_id,body:d.body});
    if(!c)return null;
    const canonical=envelope(c,origin),input=text.trim();
    return input===JSON.stringify(canonical)||input===JSON.stringify(canonical,null,2)?c:null;
  }catch{return null;}
}
export function importReleaseChainRevocationRecovery(text:string,origin:string){
  const c=parseReleaseChainRevocationRecovery(text,origin);if(!c)throw Error('invalid_recovery');
  // Import is always audit-only: it stages a read-only query and can never become a sendable draft.
  const controller=new ReleaseChainRevocationSubmission(confirmReleaseChainRevocation(c,true));
  void controller.recover(false);
  const staged=Object.freeze({...controller.state,error:'outcome_unknown' as const});
  let queried=false;
  return Object.freeze({get state(){return queried?controller.state:staged;},
    recover:(enabled:boolean,fetcher?:typeof fetch)=>{queried=true;return controller.recover(enabled,fetcher);}});
}
export type ImportedReleaseChainRevocationRecovery=ReturnType<typeof importReleaseChainRevocationRecovery>;
