import {record,exactFields} from './first-command-transport';
import {parseReleaseDecisionSupersessionCommand,confirmReleaseDecisionSupersession,ReleaseDecisionSupersessionSubmission,
  type ReleaseDecisionSupersessionCommand,type ReleaseDecisionSupersessionReview} from './release-decision-supersession-transport';

export const releaseDecisionSupersessionRecoveryTextLimit=32768;
const format='slc-release-decision-supersession-recovery';
function validOrigin(origin:string):boolean{
  try{const u=new URL(origin);return u.origin===origin&&!u.username&&!u.password&&
    (u.protocol==='https:'||u.protocol==='http:'&&['localhost','127.0.0.1','[::1]'].includes(u.hostname));}
  catch{return false;}
}
function validUnicode(value:unknown):boolean{
 if(typeof value==='string'){for(let i=0;i<value.length;i++){const c=value.charCodeAt(i);if(c>=0xd800&&c<=0xdbff){const n=value.charCodeAt(++i);if(!(n>=0xdc00&&n<=0xdfff))return false;}else if(c>=0xdc00&&c<=0xdfff)return false;}return true;}
 return value===null||typeof value!=='object'||Object.values(value).every(validUnicode);
}
function envelope(c:ReleaseDecisionSupersessionCommand,origin:string){return {format,version:1,origin,...c};}
/** Canonical frozen preparation only, never credentials or success evidence.
 * Predecessor number/decision/readiness labels are client metadata, NOT audit-certified facts.
 * Original audit recovery binds the original body, predecessor UUID, release and snapshot. */
export function exportReleaseDecisionSupersessionRecovery(review:ReleaseDecisionSupersessionReview,origin:string):string{
  if(review.confirmed!==true||!validOrigin(origin))throw Error('invalid_recovery');
  const c=parseReleaseDecisionSupersessionCommand(review.command);
  if(!c||!validUnicode(c)||JSON.stringify(c)!==JSON.stringify(review.command))throw Error('invalid_recovery');
  const text=JSON.stringify(envelope(c,origin),null,2);
  if(new TextEncoder().encode(text).length>releaseDecisionSupersessionRecoveryTextLimit)throw Error('invalid_recovery');
  return text;
}
/** Exact compact/pretty export syntax rejects duplicate keys and silent normalization. */
export function parseReleaseDecisionSupersessionRecovery(text:string,origin:string):ReleaseDecisionSupersessionCommand|null{
  if(!validOrigin(origin)||typeof text!=='string'||text.length>releaseDecisionSupersessionRecoveryTextLimit||
    new TextEncoder().encode(text).length>releaseDecisionSupersessionRecoveryTextLimit)return null;
  try{
    const d=record(JSON.parse(text));
    if(!d||!exactFields(d,['format','version','origin','operation','target','body','predecessor'])||
      d.format!==format||d.version!==1||d.origin!==origin)return null;
    const c=parseReleaseDecisionSupersessionCommand({operation:d.operation,target:d.target,body:d.body,predecessor:d.predecessor});
    if(!c||!validUnicode(c))return null;
    const canonical=envelope(c,origin),input=text.trim();
    return input===JSON.stringify(canonical)||input===JSON.stringify(canonical,null,2)?c:null;
  }catch{return null;}
}
/** Import does zero network. The returned facade exposes no business send method. */
export function importReleaseDecisionSupersessionRecovery(text:string,origin:string){
  const c=parseReleaseDecisionSupersessionRecovery(text,origin);if(!c)throw Error('invalid_recovery');
  const controller=new ReleaseDecisionSupersessionSubmission(confirmReleaseDecisionSupersession(c,true));
  void controller.recover(false);
  const staged=Object.freeze({...controller.state,error:'outcome_unknown' as const});let queried=false;
  return Object.freeze({get state(){return queried?controller.state:staged;},
    recover:(enabled:boolean,fetcher?:typeof fetch)=>{queried=true;return controller.recover(enabled,fetcher);}});
}
export type ImportedReleaseDecisionSupersessionRecovery=ReturnType<typeof importReleaseDecisionSupersessionRecovery>;
