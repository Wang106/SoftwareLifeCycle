import {record,exactFields} from './first-command-transport';
import {parseAuthorizationApprovalCommand,confirmAuthorizationApproval,AuthorizationApprovalSubmission,
  type AuthorizationApprovalCommand,type AuthorizationApprovalReview} from './authorization-approval-transport';

export const authorizationApprovalRecoveryTextLimit=32768;
const format='slc-authorization-approval-recovery';
function validOrigin(origin:string):boolean{
  try{const u=new URL(origin);return u.origin===origin&&!u.username&&!u.password&&
    (u.protocol==='https:'||u.protocol==='http:'&&['localhost','127.0.0.1','[::1]'].includes(u.hostname));}
  catch{return false;}
}
function envelope(c:AuthorizationApprovalCommand,origin:string){return {format,version:1,origin,...c};}
/** Canonical original context only, never credentials, identity assertions or success evidence. */
export function exportAuthorizationApprovalRecovery(review:AuthorizationApprovalReview,origin:string):string{
  if(review.confirmed!==true||!validOrigin(origin))throw Error('invalid_recovery');
  const c=parseAuthorizationApprovalCommand(review.command);
  if(!c||JSON.stringify(c)!==JSON.stringify(review.command))throw Error('invalid_recovery');
  const text=JSON.stringify(envelope(c,origin),null,2);
  if(new TextEncoder().encode(text).length>authorizationApprovalRecoveryTextLimit)throw Error('invalid_recovery');
  return text;
}
/** Exact compact/pretty export syntax rejects duplicate keys and silent normalization. */
export function parseAuthorizationApprovalRecovery(text:string,origin:string):AuthorizationApprovalCommand|null{
  if(!validOrigin(origin)||typeof text!=='string'||text.length>authorizationApprovalRecoveryTextLimit||
    new TextEncoder().encode(text).length>authorizationApprovalRecoveryTextLimit)return null;
  try{
    const d=record(JSON.parse(text));
    if(!d||!exactFields(d,['format','version','origin','operation','target','context','body'])||
      d.format!==format||d.version!==1||d.origin!==origin)return null;
    const c=parseAuthorizationApprovalCommand({operation:d.operation,target:d.target,context:d.context,body:d.body});
    if(!c)return null;
    const canonical=envelope(c,origin),input=text.trim();
    return input===JSON.stringify(canonical)||input===JSON.stringify(canonical,null,2)?c:null;
  }catch{return null;}
}
/** Import does zero network. The returned facade exposes no business send method. */
export function importAuthorizationApprovalRecovery(text:string,origin:string){
  const c=parseAuthorizationApprovalRecovery(text,origin);if(!c)throw Error('invalid_recovery');
  const controller=new AuthorizationApprovalSubmission(confirmAuthorizationApproval(c,true));
  void controller.recover(false);
  const staged=Object.freeze({...controller.state,error:'outcome_unknown' as const});let queried=false;
  return Object.freeze({get state(){return queried?controller.state:staged;},
    recover:(enabled:boolean,fetcher?:typeof fetch)=>{queried=true;return controller.recover(enabled,fetcher);}});
}
export type ImportedAuthorizationApprovalRecovery=ReturnType<typeof importAuthorizationApprovalRecovery>;
