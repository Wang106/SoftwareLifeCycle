import {record,exactFields} from './first-command-transport';
import {parseAcceptanceCorrectionCommand,confirmAcceptanceCorrection,AcceptanceCorrectionSubmission,
  type AcceptanceCorrectionCommand,type AcceptanceCorrectionReview} from './acceptance-correction-transport';

export const correctionRecoveryTextLimit=32768;
const format='slc-acceptance-correction-recovery';
function validOrigin(origin:string):boolean{
  try{const u=new URL(origin);return u.origin===origin&&!u.username&&!u.password&&
    (u.protocol==='https:'||u.protocol==='http:'&&['localhost','127.0.0.1','[::1]'].includes(u.hostname));}
  catch{return false;}
}
function envelope(c:AcceptanceCorrectionCommand,origin:string){return {format,version:1,origin,...c};}
/** Canonical original context only, never credentials, identity assertions or success evidence. */
export function exportAcceptanceCorrectionRecovery(review:AcceptanceCorrectionReview,origin:string):string{
  if(review.confirmed!==true||!validOrigin(origin))throw Error('invalid_recovery');
  const c=parseAcceptanceCorrectionCommand(review.command);
  if(!c||JSON.stringify(c)!==JSON.stringify(review.command))throw Error('invalid_recovery');
  const text=JSON.stringify(envelope(c,origin),null,2);
  if(new TextEncoder().encode(text).length>correctionRecoveryTextLimit)throw Error('invalid_recovery');
  return text;
}
/** Exact compact/pretty export syntax rejects duplicate keys and silent normalization. */
export function parseAcceptanceCorrectionRecovery(text:string,origin:string):AcceptanceCorrectionCommand|null{
  if(!validOrigin(origin)||typeof text!=='string'||text.length>correctionRecoveryTextLimit||
    new TextEncoder().encode(text).length>correctionRecoveryTextLimit)return null;
  try{
    const d=record(JSON.parse(text));
    if(!d||!exactFields(d,['format','version','origin','operation','target','body','predecessor'])||
      d.format!==format||d.version!==1||d.origin!==origin)return null;
    const c=parseAcceptanceCorrectionCommand({operation:d.operation,target:d.target,body:d.body,predecessor:d.predecessor});
    if(!c)return null;
    const canonical=envelope(c,origin),input=text.trim();
    return input===JSON.stringify(canonical)||input===JSON.stringify(canonical,null,2)?c:null;
  }catch{return null;}
}
/** Import does zero network. The returned facade exposes no business send method. */
export function importAcceptanceCorrectionRecovery(text:string,origin:string){
  const c=parseAcceptanceCorrectionRecovery(text,origin);if(!c)throw Error('invalid_recovery');
  const controller=new AcceptanceCorrectionSubmission(confirmAcceptanceCorrection(c,true));
  void controller.recover(false);
  const staged=Object.freeze({...controller.state,error:'outcome_unknown' as const});let queried=false;
  return Object.freeze({get state(){return queried?controller.state:staged;},
    recover:(enabled:boolean,fetcher?:typeof fetch)=>{queried=true;return controller.recover(enabled,fetcher);}});
}
export type ImportedAcceptanceCorrectionRecovery=ReturnType<typeof importAcceptanceCorrectionRecovery>;
