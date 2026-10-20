import {validUuid} from './command-draft';
import {record,exactFields,readCommandResponse,type FirstError} from './first-command-transport';

const kinds=['RELEASE','DELIVERY_PACKAGE','DISTRIBUTION','AUTHORIZATION'] as const;
export type ReleaseChainTargetKind=typeof kinds[number];
const depthByKind:Readonly<Record<ReleaseChainTargetKind,number>>={RELEASE:0,DELIVERY_PACKAGE:1,DISTRIBUTION:2,AUTHORIZATION:3};
const nodeFieldByKind:Readonly<Record<ReleaseChainTargetKind,'release_id'|'delivery_package_id'|'distribution_id'|'authorization_id'>>={
  RELEASE:'release_id',DELIVERY_PACKAGE:'delivery_package_id',DISTRIBUTION:'distribution_id',AUTHORIZATION:'authorization_id'};
const actionByKind:Readonly<Record<ReleaseChainTargetKind,string>>={
  RELEASE:'RELEASE_REVOKED',DELIVERY_PACKAGE:'DELIVERY_REVOKED',DISTRIBUTION:'DISTRIBUTION_REVOKED',AUTHORIZATION:'AUTHORIZATION_REVOKED'};
const pathByKind:Readonly<Record<ReleaseChainTargetKind,string>>={
  RELEASE:'/api/v1/releases/',DELIVERY_PACKAGE:'/api/v1/deliveries/',DISTRIBUTION:'/api/v1/distributions/',AUTHORIZATION:'/api/v1/authorizations/'};
// A reason may carry up to 4000 multi-byte characters, so the full envelope needs a larger
// bound than the legacy 8192 used by single-scalar commands (see design review section 3).
const ENVELOPE_LIMIT=24576;

export type ReleaseChainRevocationContext=Readonly<{
  version:1;release_id:string;snapshot_id:string;release_decision_id:string;
  delivery_package_id:string|null;distribution_id:string|null;authorization_id:string|null;
}>;
export type ReleaseChainRevocationCommand=Readonly<{
  operation:'release-chain-revocation';target_kind:ReleaseChainTargetKind;target_id:string;
  body:Readonly<{request_id:string;reason:string;expected_context:ReleaseChainRevocationContext}>;
}>;

const uuid=(value:unknown):value is string=>typeof value==='string'&&validUuid(value)&&value===value.toLowerCase();
const reasonText=(value:unknown):value is string=>{
  if(typeof value!=='string')return false;
  const t=value.trim();
  return t.length>0&&t.length<=4000&&!/[\u0000-\u001f\u007f]/.test(value)&&
    !/[\uD800-\uDFFF]/u.test(value.replace(/[\uD800-\uDBFF][\uDC00-\uDFFF]/g,''));
};
function validContext(value:unknown,kind:ReleaseChainTargetKind,target_id:string):value is ReleaseChainRevocationContext{
  const x=record(value);if(!x)return false;
  if(!exactFields(x,['version','release_id','snapshot_id','release_decision_id','delivery_package_id','distribution_id','authorization_id']))return false;
  if(x.version!==1)return false;
  if(!uuid(x.release_id)||!uuid(x.snapshot_id)||!uuid(x.release_decision_id))return false;
  const depth=depthByKind[kind];
  const nullable=(v:unknown,required:boolean)=>required?uuid(v):v===null;
  if(!nullable(x.delivery_package_id,depth>=1)||!nullable(x.distribution_id,depth>=2)||!nullable(x.authorization_id,depth>=3))return false;
  return x[nodeFieldByKind[kind]]===target_id;
}
export function parseReleaseChainRevocationCommand(value:unknown):ReleaseChainRevocationCommand|null{
  const d=record(value),b=record(d?.body),x=record(b?.expected_context);
  if(!d||!b||!x||!exactFields(d,['operation','target_kind','target_id','body'])||d.operation!=='release-chain-revocation'||
    !exactFields(b,['request_id','reason','expected_context'])||!kinds.includes(d.target_kind as ReleaseChainTargetKind)||
    !uuid(d.target_id)||!uuid(b.request_id)||!reasonText(b.reason)||
    !validContext(x,d.target_kind as ReleaseChainTargetKind,d.target_id as string))return null;
  const kind=d.target_kind as ReleaseChainTargetKind;
  const command=Object.freeze({operation:'release-chain-revocation' as const,target_kind:kind,target_id:d.target_id as string,
    body:Object.freeze({request_id:b.request_id as string,reason:(b.reason as string).trim(),
      expected_context:Object.freeze({version:1 as const,release_id:x.release_id as string,snapshot_id:x.snapshot_id as string,
        release_decision_id:x.release_decision_id as string,delivery_package_id:x.delivery_package_id as string|null,
        distribution_id:x.distribution_id as string|null,authorization_id:x.authorization_id as string|null}) as ReleaseChainRevocationContext})});
  return new TextEncoder().encode(JSON.stringify(command)).length<=ENVELOPE_LIMIT?command:null;
}
export const releaseChainRevocationEvent=(c:ReleaseChainRevocationCommand)=>'EVT-RCR-'+c.body.request_id.replaceAll('-','');
export const releaseChainRevocationPath=(c:ReleaseChainRevocationCommand)=>pathByKind[c.target_kind]+encodeURIComponent(c.target_id)+'/revocations';
export const releaseChainRevocationAction=(c:ReleaseChainRevocationCommand)=>actionByKind[c.target_kind];
export type ReleaseChainRevocationReview=Readonly<{command:ReleaseChainRevocationCommand;confirmed:boolean}>;
export function confirmReleaseChainRevocation(input:unknown,confirmed:boolean):ReleaseChainRevocationReview{
  const command=parseReleaseChainRevocationCommand(input);if(!command)throw Error('invalid_review');
  return Object.freeze({command,confirmed:confirmed===true});
}
export type ReleaseChainRevocationReceipt=Readonly<{operation:'release-chain-revocation';request_id:string;target_kind:ReleaseChainTargetKind;
  target_id:string;audit_event_no:string;result:Readonly<Record<string,string|number|null>>}>;
export function projectReleaseChainRevocationReceipt(value:unknown,c:ReleaseChainRevocationCommand):ReleaseChainRevocationReceipt|null{
  const d=record(value),r=record(d?.result),b=c.body,x=b.expected_context;
  if(!d||!r||d.operation!==c.operation||d.request_id!==b.request_id||d.target_kind!==c.target_kind||d.target_id!==c.target_id||
    d.audit_event_no!==releaseChainRevocationEvent(c)||r.id!==b.request_id||r.revocation_no!=='RCR-'+b.request_id.replaceAll('-','')||
    r.target_kind!==c.target_kind||r.release_id!==x.release_id||r.snapshot_id!==x.snapshot_id||r.release_decision_id!==x.release_decision_id||
    r.reason!==b.reason)return null;
  const result:Record<string,string|number|null>={id:b.request_id,revocation_no:'RCR-'+b.request_id.replaceAll('-',''),
    target_kind:c.target_kind,release_id:x.release_id,snapshot_id:x.snapshot_id,release_decision_id:x.release_decision_id,reason:b.reason};
  return Object.freeze({operation:c.operation,request_id:b.request_id,target_kind:c.target_kind,target_id:c.target_id,
    audit_event_no:releaseChainRevocationEvent(c),result:Object.freeze(result)});
}
export type ReleaseChainRevocationError=Exclude<FirstError,'first_submission_disabled'|'version_conflict'>|'release_chain_revocation_disabled';
const denials:Readonly<Record<number,readonly ReleaseChainRevocationError[]>>={400:['invalid_request'],401:['session_required'],
  403:['cross_origin_request','read_only_mode','submission_forbidden'],409:['request_conflict','submission_conflict'],
  413:['request_too_large'],415:['json_required'],422:['invalid_request'],503:['release_chain_revocation_disabled']};
export type ReleaseChainRevocationState=Readonly<{phase:'idle'|'sending'|'checking'|'unknown'|'rejected'|'confirmed';
  review:ReleaseChainRevocationReview;command:ReleaseChainRevocationCommand;
  error:ReleaseChainRevocationError|null;receipt:ReleaseChainRevocationReceipt|null}>;
export class ReleaseChainRevocationSubmission{
  private current:ReleaseChainRevocationState;private uncertain=false;private readonly body:string;
  constructor(review:ReleaseChainRevocationReview){if(review.confirmed!==true)throw Error('Confirm the exact request before sending.');
    const command=parseReleaseChainRevocationCommand(review.command);if(!command||JSON.stringify(command)!==JSON.stringify(review.command))throw Error('invalid_review');
    const canonical=confirmReleaseChainRevocation(command,true);this.body=JSON.stringify(command);
    this.current=Object.freeze({phase:'idle',review:canonical,command,error:null,receipt:null});}
  get state(){return this.current;}
  private update(phase:ReleaseChainRevocationState['phase'],error:ReleaseChainRevocationError|null,receipt:ReleaseChainRevocationReceipt|null=null){
    this.current=Object.freeze({...this.current,phase,error,receipt});return this.current;}
  send(enabled:boolean,fetcher:typeof fetch=fetch){return this.run('submit',enabled,fetcher);}
  recover(enabled:boolean,fetcher:typeof fetch=fetch){return this.run('recover',enabled,fetcher);}
  private async run(mode:'submit'|'recover',enabled:boolean,fetcher:typeof fetch):Promise<ReleaseChainRevocationState>{
    if(['sending','checking','confirmed'].includes(this.current.phase))return this.current;if(mode==='recover')this.uncertain=true;
    if(enabled!==true)return this.update(this.uncertain?'unknown':'rejected','release_chain_revocation_disabled');
    this.update(mode==='submit'?'sending':'checking',null);
    try{const response=await fetcher(mode==='submit'?'/auth/release-chain-revocation':'/auth/release-chain-revocation-receipt',
      {method:'POST',body:this.body,headers:{'Content-Type':'application/json',Accept:'application/json'},credentials:'same-origin',
        redirect:'error',cache:'no-store',signal:AbortSignal.timeout(15000)});
      const value=await readCommandResponse(response);const receipt=response.status===200?projectReleaseChainRevocationReceipt(value,this.current.command):null;
      if(receipt){this.uncertain=false;return this.update('confirmed',null,receipt);}const error=record(value)?.error;
      if(typeof error==='string'&&denials[response.status]?.includes(error as ReleaseChainRevocationError))
        return this.update(this.uncertain?'unknown':'rejected',error as ReleaseChainRevocationError);
    }catch{}this.uncertain=true;return this.update('unknown','outcome_unknown');
  }
}
