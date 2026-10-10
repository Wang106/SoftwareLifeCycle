'use strict';
// Exercise actual Next production handlers and bilingual SSR with auth disabled.
const assert = require('node:assert/strict');
const {spawn} = require('node:child_process');
const net = require('node:net');
async function port() {
 const server=net.createServer();await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
 const result=server.address().port;await new Promise(resolve=>server.close(resolve));return result;
}
async function main() {
 const selected=await port(),base=`http://127.0.0.1:${selected}`;
 const child=spawn(process.execPath,[require.resolve('next/dist/bin/next'),'start','--hostname','127.0.0.1','--port',String(selected)],{
  env:{...process.env,NEXT_TELEMETRY_DISABLED:'1',BROWSER_OIDC_MODE:'disabled',BROWSER_SESSION_MODE:'disabled',GRANT_STATUS_SUBMISSION_MODE:'disabled',
   GRANT_STATUS_APPROVED_API_BASE_URL:'',GRANT_STATUS_APPROVED_APP_ORIGIN:'',
   ADMIN_REGISTRATION_SUBMISSION_MODE:'disabled',ADMIN_REGISTRATION_APPROVED_API_BASE_URL:'',ADMIN_REGISTRATION_APPROVED_APP_ORIGIN:'',
   PRINCIPAL_STATUS_SUBMISSION_MODE:'disabled',PRINCIPAL_STATUS_APPROVED_API_BASE_URL:'',PRINCIPAL_STATUS_APPROVED_APP_ORIGIN:'',
   FIRST_COMMAND_SUBMISSION_MODE:'disabled',FIRST_COMMAND_APPROVED_API_BASE_URL:'',FIRST_COMMAND_APPROVED_APP_ORIGIN:'',
   EVIDENCE_COMMAND_SUBMISSION_MODE:'disabled',EVIDENCE_COMMAND_APPROVED_API_BASE_URL:'',EVIDENCE_COMMAND_APPROVED_APP_ORIGIN:'',
   ACCEPTANCE_CORRECTION_SUBMISSION_MODE:'disabled',ACCEPTANCE_CORRECTION_APPROVED_API_BASE_URL:'',ACCEPTANCE_CORRECTION_APPROVED_APP_ORIGIN:'',
   RESOURCE_COMMAND_SUBMISSION_MODE:'disabled',RESOURCE_COMMAND_APPROVED_API_BASE_URL:'',RESOURCE_COMMAND_APPROVED_APP_ORIGIN:'',
   PRODUCTION_COMMAND_SUBMISSION_MODE:'disabled',PRODUCTION_COMMAND_APPROVED_API_BASE_URL:'',PRODUCTION_COMMAND_APPROVED_APP_ORIGIN:'',
   DISTRIBUTION_COMMAND_SUBMISSION_MODE:'disabled',DISTRIBUTION_COMMAND_APPROVED_API_BASE_URL:'',DISTRIBUTION_COMMAND_APPROVED_APP_ORIGIN:'',
   GOVERNANCE_COMMAND_SUBMISSION_MODE:'disabled',GOVERNANCE_COMMAND_APPROVED_API_BASE_URL:'',GOVERNANCE_COMMAND_APPROVED_APP_ORIGIN:'',
   OIDC_CLIENT_SECRET:'',BROWSER_SESSION_KEY:'',API_BASE_URL:'',NEXT_PUBLIC_API_BASE_URL:'',NEXT_PUBLIC_API_URL:''},stdio:['ignore','pipe','pipe'],
 });
 let logs='';for(const stream of [child.stdout,child.stderr])stream.on('data',chunk=>{logs=(logs+chunk).slice(-12000);});
 try {
  let ready=false;
  for(let i=0;i<100;i++){
   if(child.exitCode!==null)throw Error(`Next exited: ${logs}`);
   try{const response=await fetch(base+'/auth/session',{signal:AbortSignal.timeout(1000)});if(response.status===503){ready=true;break;}}catch{}
   await new Promise(resolve=>setTimeout(resolve,100));
  }
  assert.ok(ready,`Next did not become ready: ${logs}`);
  for(const [language,message,htmlLanguage] of [['zh','此环境暂未开放登录。','zh-CN'],['en','Login is not available in this environment.','en']]){
   const response=await fetch(base+'/account',{headers:{Cookie:`slc_language=${language}`}});
   assert.equal(response.status,200);assert.ok(response.headers.get('cache-control').includes('no-store'));const html=await response.text();assert.ok(html.includes(message));assert.ok(html.includes(`lang="${htmlLanguage}"`));assert.ok(!html.includes('<form'));
   console.log(`Account SSR ${language}: 200, login unavailable and no login form`);
   const registration=await fetch(base+'/account/grants/new',{headers:{Cookie:`slc_language=${language}`}});
   assert.equal(registration.status,200);assert.ok(registration.headers.get('cache-control').includes('no-store'));
   const registrationHtml=await registration.text();assert.ok(registrationHtml.includes(message));
   assert.ok(!registrationHtml.includes('<form'));assert.ok(!registrationHtml.includes('name="subject"'));
   console.log(`Registration SSR ${language}: 200, private/no-store, unavailable and no identity form`);
   for(const path of ['/account/principals','/account/principals/12345678-1234-1234-1234-123456789abc']){
    const privatePage=await fetch(base+path,{headers:{Cookie:`slc_language=${language}`}});
    assert.equal(privatePage.status,200);assert.ok(privatePage.headers.get('cache-control').includes('no-store'));
    const privateHtml=await privatePage.text();assert.ok(privateHtml.includes(message));assert.ok(!privateHtml.includes('<form'));
    console.log(`Identity SSR ${language} ${path}: 200, private/no-store, disabled and no form`);
   }
  }
  for(const [language,title,sendLabel] of [['zh','准备生命周期请求','发送已确认的业务请求'],['en','Prepare a lifecycle request','Send confirmed business request']]) {
   for(const operation of ['impact','acceptance','resource']) {
    const response=await fetch(base+'/commands?operation='+operation,{headers:{Cookie:`slc_language=${language}`}});
    assert.equal(response.status,200);assert.ok(response.headers.get('cache-control').includes('no-store'));
    const html=await response.text();assert.ok(html.includes(title));assert.ok(!html.includes(sendLabel));
    assert.ok(html.includes('name="target"'));assert.ok(html.includes(language==='zh'?'资源引用':'resource reference'));
    assert.ok(html.includes('name="recoveryText"'));assert.ok(html.includes(language==='zh'?'恢复原业务请求':'Restore an original business request'));
    assert.ok(html.includes(language==='zh'?'不会自动发送或查询':'never sends or queries automatically'));
    console.log(`Command SSR ${language} ${operation}: 200, no-store, preparation without send capability`);
   }
  }
  for(const [language,message] of [['zh','登录失败，请重试。'],['en','Sign-in failed. Please try again.']]) {
   const response=await fetch(base+'/account?auth=failed',{headers:{Cookie:`slc_language=${language}`}});assert.equal(response.status,200);assert.ok((await response.text()).includes(message));console.log(`Account error SSR ${language}: translated generic failure`);
  }
  for(const [language,message] of [['zh','尚未确认退出成功，请重试退出登录。'],['en','Sign-out could not be confirmed. Please retry signing out.']]) {
   const response=await fetch(base+'/account?auth=logout_failed',{headers:{Cookie:`slc_language=${language}`}});assert.equal(response.status,200);assert.ok((await response.text()).includes(message));console.log(`Account logout error SSR ${language}: translated retry message`);
  }
  for(const [route,method,status] of [['login','GET',405],['login','POST',503],['callback','GET',503],['session','GET',503],['logout','POST',503],['grant-status','GET',405],['grant-status','POST',503],['admin-registration','GET',405],['admin-registration','POST',503],['principal-status','GET',405],['principal-status','POST',503],['first-command','GET',405],['first-command','POST',503],['first-command-receipt','GET',405],['first-command-receipt','POST',503],['acceptance-correction','GET',405],['acceptance-correction','POST',503],['acceptance-correction-receipt','GET',405],['acceptance-correction-receipt','POST',503],['evidence-command','GET',405],['evidence-command','POST',503],['evidence-command-receipt','GET',405],['evidence-command-receipt','POST',503],['resource-command','GET',405],['resource-command','POST',503],['resource-command-receipt','GET',405],['resource-command-receipt','POST',503],['production-command','GET',405],['production-command','POST',503],['production-command-receipt','GET',405],['production-command-receipt','POST',503],['distribution-command','GET',405],['distribution-command','POST',503],['distribution-command-receipt','GET',405],['distribution-command-receipt','POST',503],['governance-command','GET',405],['governance-command','POST',503],['governance-command-receipt','GET',405],['governance-command-receipt','POST',503]]){
   const response=await fetch(`${base}/auth/${route}`,{method,headers:{Origin:base},redirect:'manual'});
   assert.equal(response.status,status);assert.equal(response.headers.get('cache-control'),'private, no-store');assert.ok(response.headers.get('vary').includes('Cookie'));assert.equal(response.headers.get('location'),null);
   const data=await response.json();assert.equal(data.error,status===405?'method_not_allowed':route==='grant-status'?'grant_submission_disabled':route==='admin-registration'?'registration_submission_disabled':route==='principal-status'?'principal_submission_disabled':route.startsWith('first-command')?'first_submission_disabled':route.startsWith('acceptance-correction')?'acceptance_correction_disabled':route.startsWith('evidence-command')?'evidence_submission_disabled':route.startsWith('resource-command')?'resource_submission_disabled':route.startsWith('production-command')?'production_submission_disabled':route.startsWith('distribution-command')?'distribution_submission_disabled':route.startsWith('governance-command')?'governance_submission_disabled':'login_not_configured');
   console.log(`Next production route ${method} /auth/${route}: ${status}, private/no-store`);
  }
 } finally {
  child.kill('SIGTERM');
  if(child.exitCode===null)await Promise.race([new Promise(resolve=>child.once('exit',resolve)),new Promise(resolve=>setTimeout(()=>{child.kill('SIGKILL');resolve();},2000)).then(()=>{})]);
 }
}
main().catch(error=>{console.error(error.message);process.exitCode=1;});



