const principal='11111111-1111-4111-8111-111111111111';
const release='22222222-2222-4222-8222-22222222a222';
const snapshot='33333333-3333-4333-8333-33333333a333';
const decision='44444444-4444-4444-8444-44444444b444';
const delivery='55555555-5555-4555-8555-55555555c555';
const distribution='66666666-6666-4666-8666-66666666d666';
const authorization='77777777-7777-4777-8777-77777777e777';
const requestId='88aa8888-8888-4888-8888-888888888888';
const context=(kind,target)=>({
  version:1,release_id:release,snapshot_id:snapshot,release_decision_id:decision,
  delivery_package_id:kind==='DELIVERY_PACKAGE'||kind==='DISTRIBUTION'||kind==='AUTHORIZATION'?delivery:null,
  distribution_id:kind==='DISTRIBUTION'||kind==='AUTHORIZATION'?distribution:null,
  authorization_id:kind==='AUTHORIZATION'?authorization:null});
// Ensure the target node UUID matches the target_id for each depth.
const nodeId=kind=>({RELEASE:release,DELIVERY_PACKAGE:delivery,DISTRIBUTION:distribution,AUTHORIZATION:authorization})[kind];
function command(kind='RELEASE',target){
  const id=target||nodeId(kind);
  return{operation:'release-chain-revocation',target_kind:kind,target_id:id,body:{
    request_id:requestId,reason:'Permanently revoke the release chain / 永久撤销发布链',
    expected_context:context(kind,id)}};
}
const action=kind=>({RELEASE:'RELEASE_REVOKED',DELIVERY_PACKAGE:'DELIVERY_REVOKED',DISTRIBUTION:'DISTRIBUTION_REVOKED',AUTHORIZATION:'AUTHORIZATION_REVOKED'})[kind];
const eventNo=c=>'EVT-RCR-'+c.body.request_id.replaceAll('-','');
function receipt(c){const b=c.body,x=b.expected_context;
  return{operation:c.operation,request_id:b.request_id,target_kind:c.target_kind,target_id:c.target_id,audit_event_no:eventNo(c),result:{
    id:b.request_id,revocation_no:'RCR-'+b.request_id.replaceAll('-',''),target_kind:c.target_kind,release_id:x.release_id,
    snapshot_id:x.snapshot_id,release_decision_id:x.release_decision_id,reason:b.reason}};}
function audit(c){const b=c.body,x=b.expected_context;
  return{id:'99999999-9999-4999-8999-999999999999',event_no:eventNo(c),event_type:'RELEASE_CHAIN_REVOCATION',action:action(c.target_kind),
    entity_type:c.target_kind,entity_id:c.target_id,entity_ref:'RCR-'+b.request_id.replaceAll('-',''),actor_principal_id:principal,
    declared_actor_name:null,detail:b.reason,payload:{revocation_id:b.request_id,release_id:x.release_id,snapshot_id:x.snapshot_id,
    release_decision_id:x.release_decision_id,reason:b.reason,actor_source:'AUTHENTICATED_PRINCIPAL',protocol_version:1,
    review_context:{version:1,release_id:x.release_id,snapshot_id:x.snapshot_id,release_decision_id:x.release_decision_id,
      delivery_package_id:x.delivery_package_id,distribution_id:x.distribution_id,authorization_id:x.authorization_id},
    request:{target_kind:c.target_kind,target_id:c.target_id,reason:b.reason,expected_context:{
      version:1,release_id:x.release_id,snapshot_id:x.snapshot_id,release_decision_id:x.release_decision_id,
      delivery_package_id:x.delivery_package_id,distribution_id:x.distribution_id,authorization_id:x.authorization_id}}}};}
module.exports={principal,release,snapshot,decision,delivery,distribution,authorization,requestId,nodeId,command,action,eventNo,receipt,audit};
