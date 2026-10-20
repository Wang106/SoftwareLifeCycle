'use strict';
const{test}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs');
const read=path=>fs.readFileSync(path,'utf8');
test('replacement proxy is independently default-off and POST-only',()=>{
 const auth=read('lib/browser-auth.ts'),submit=read('app/auth/release-decision-supersession/route.ts'),recover=read('app/auth/release-decision-supersession-receipt/route.ts');
 assert.match(auth,/RELEASE_DECISION_SUPERSESSION_SUBMISSION_MODE==='enabled'/);
 assert.match(auth,/RELEASE_DECISION_SUPERSESSION_APPROVED_API_BASE_URL/);
 assert.match(auth,/RELEASE_DECISION_SUPERSESSION_APPROVED_APP_ORIGIN/);
 assert.match(auth,/request\.method!==\x27POST\x27/);
 assert.match(submit,/handleReleaseDecisionSupersession\(request,process\.env,'submit'\)/);
 assert.match(recover,/handleReleaseDecisionSupersession\(request,process\.env,'recover'\)/);
});
test('browser session posts once then proves the exact operation through atomic audit',()=>{
 const source=read('lib/browser-session.ts');
 assert.match(source,/releaseDecisionSupersessionPath\(command\)/);
 assert.match(source,/\/api\/v1\/activity\/['"]\+releaseDecisionSupersessionEvent\(command\)/);
 assert.match(source,/projectReleaseDecisionSupersessionAudit\(audit\.value,command,identity\.principal\.id\)/);
});
test('effective decision detail exposes preparation only and commands page keeps generic form separate',()=>{
 const detail=read('app/release-decisions/[decisionNo]/page.tsx'),commands=read('app/commands/page.tsx');
 assert.match(detail,/row\.effective&&row\.release&&row\.snapshot/);
 assert.match(detail,/operation:'decision-supersession'/);
  assert.match(commands,/releaseDecisionSupersessionSubmissionConfigured/);
  assert.match(commands,/!decisionSupersessionContextRequested && !releaseChainRevocationContextRequested && <CommandWorkbench/);
});
