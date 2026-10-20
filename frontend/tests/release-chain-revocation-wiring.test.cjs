'use strict';
const{test}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs');
const read=path=>fs.readFileSync(path,'utf8');
test('revocation proxy is independently default-off and POST-only',()=>{
  const auth=read('lib/browser-auth.ts'),submit=read('app/auth/release-chain-revocation/route.ts'),recover=read('app/auth/release-chain-revocation-receipt/route.ts');
  assert.match(auth,/RELEASE_CHAIN_REVOCATION_SUBMISSION_MODE==='enabled'/);
  assert.match(auth,/RELEASE_CHAIN_REVOCATION_APPROVED_API_BASE_URL/);
  assert.match(auth,/RELEASE_CHAIN_REVOCATION_APPROVED_APP_ORIGIN/);
  assert.match(auth,/request\.method!==\x27POST\x27/);
  assert.match(submit,/handleReleaseChainRevocation\(request,process\.env,'submit'\)/);
  assert.match(recover,/handleReleaseChainRevocation\(request,process\.env,'recover'\)/);
});
test('browser session posts once then proves the exact operation through atomic audit',()=>{
  const source=read('lib/browser-session.ts');
  assert.match(source,/releaseChainRevocationPath\(command\)/);
  assert.match(source,/\/api\/v1\/activity\/['"]\+releaseChainRevocationEvent\(command\)/);
  assert.match(source,/projectReleaseChainRevocationAudit\(audit\.value,command,identity\.principal\.id\)/);
});
test('four revocation targets map to their fixed API paths and actions',()=>{
  const source=read('lib/release-chain-revocation-transport.ts');
  assert.match(source,/\/api\/v1\/releases\//);
  assert.match(source,/\/api\/v1\/deliveries\//);
  assert.match(source,/\/api\/v1\/distributions\//);
  assert.match(source,/\/api\/v1\/authorizations\//);
  assert.match(source,/RELEASE_REVOKED/);
  assert.match(source,/DELIVERY_REVOKED/);
  assert.match(source,/DISTRIBUTION_REVOKED/);
  assert.match(source,/AUTHORIZATION_REVOKED/);
});
test('recovery export/import is canonical, origin-bound and audit-only',()=>{
  const source=read('lib/release-chain-revocation-recovery.ts');
  assert.match(source,/slc-release-chain-revocation-recovery/);
  assert.match(source,/validOrigin\(origin\)/);
  assert.match(source,/new ReleaseChainRevocationSubmission\(confirmReleaseChainRevocation\(c,true\)\)/);
  assert.match(source,/void controller\.recover\(false\)/);
  assert.match(source,/queried=true/);
});
test('commands page exposes a separate revocation workbench and governance stays read-only',()=>{
  const commands=read('app/commands/page.tsx'),governance=read('app/governance/[kind]/[targetId]/page.tsx');
  assert.match(commands,/releaseChainRevocationSubmissionConfigured/);
  assert.match(commands,/ReleaseChainRevocationWorkbench/);
  assert.match(commands,/!releaseChainRevocationContextRequested && <CommandWorkbench/);
  assert.match(commands,/query\.operation === 'release-chain-revocation'/);
  assert.doesNotMatch(governance,/\/commands/);
});
