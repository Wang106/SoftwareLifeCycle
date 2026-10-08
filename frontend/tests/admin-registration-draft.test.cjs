'use strict';
const {test,after}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs'),path=require('node:path');
const output=fs.mkdtempSync(path.join(require('node:os').tmpdir(),'slc-registration-'));
require('node:child_process').execFileSync(process.execPath,[require.resolve('typescript/bin/tsc'),
 'lib/admin-registration-draft.ts','components/admin-registration-preparation.tsx',
 '--target','ES2021','--module','commonjs','--jsx','react-jsx','--esModuleInterop',
 '--resolveJsonModule','--strict','--skipLibCheck','--outDir',output]);
fs.symlinkSync(path.resolve('node_modules'),path.join(output,'node_modules'),'dir');
const {prepareRegistration,confirmRegistration,exportRegistration,registrationRoles}=require(path.join(output,'lib/admin-registration-draft.js'));
const React=require('react'),{renderToStaticMarkup}=require('react-dom/server');
const Component=require(path.join(output,'components/admin-registration-preparation.js')).default;
const {LanguageProvider}=require(path.join(output,'components/localized.js'));
after(()=>fs.rmSync(output,{recursive:true,force:true}));
const newId='12345678-1234-1234-1234-123456789abc';
const principalId='23456789-1234-1234-1234-123456789abc',scopeId='34567890-1234-1234-1234-123456789abc';
const common={newId,eventNo:'ADM-REGISTER-01',reason:'  测试新增记录的原因  '};
function principal(change={}){return {...common,kind:'PRINCIPAL',principalType:'USER',subject:'Opaque.Subject:CASE',displayName:'测试用户',...change};}
function grant(kind='PROJECT',change={}){return {...common,kind,principalId,role:registrationRoles[kind][0],
 ...(kind==='GLOBAL'?{}:{scopeId}),...change};}
function request(input){return JSON.parse(exportRegistration(confirmRegistration(prepareRegistration(input),true)));}
for(const principalType of ['USER','SERVICE'])test('disabled-first exact local registration: '+principalType,()=>{
 const input=principal({principalType,newId:newId.toUpperCase()}),review=prepareRegistration(input);
 assert.equal(review.initialStatus,'DISABLED');assert.equal(review.confirmed,false);
 assert.deepEqual(request(input),{method:'POST',path:'/api/v1/security/admin/principals',
  body:{event_no:common.eventNo,reason:'测试新增记录的原因',principal_id:newId,subject:input.subject,
   principal_type:principalType,display_name:input.displayName}});
 assert.ok(!('issuer' in review.request.body));assert.ok(!('status' in review.request.body));assert.ok(!('role' in review.request.body));
});
for(const kind of ['GLOBAL','PROJECT','SOFTWARE'])for(const role of registrationRoles[kind]){
 test('suspended-first exact scope/role registration: '+kind+' '+role,()=>{
  const input=grant(kind,{role}),review=prepareRegistration(input);
  assert.equal(review.initialStatus,'SUSPENDED');
  assert.deepEqual(request(input),{method:'POST',path:kind==='GLOBAL'?'/api/v1/security/admin/global-roles':
   '/api/v1/security/admin/memberships/'+kind,body:{event_no:common.eventNo,reason:'测试新增记录的原因',
   ...(kind==='GLOBAL'?{grant_id:newId}:{membership_id:newId}),principal_id:principalId,
   ...(kind==='GLOBAL'?{}:{scope_id:scopeId}),role}});
  assert.ok(!('status' in review.request.body));assert.ok(!('actor' in review.request.body));
 });
}
test('frontend role catalog matches the actual backend role scope contract',()=>{
 const source=fs.readFileSync('../backend/app/security_roles.py','utf8');
 for(const kind of ['GLOBAL','PROJECT','SOFTWARE']){
  const section=source.match(new RegExp(kind+'_ROLES\\s*=\\s*frozenset\\(\\s*\\{([\\s\\S]*?)\\}\\s*\\)'));
  assert.ok(section,kind);const expected=[...section[1].matchAll(/"([A-Z_]+)"/g)].map(x=>x[1]).sort();
  assert.deepEqual([...registrationRoles[kind]].sort(),expected);
 }
});
test('subject remains opaque and exact; printable Unicode boundaries match backend',()=>{
 for(const subject of ['Subject.CASE','opaque subject with internal spaces','😀'.repeat(500),'\ufeffsubject']){
  assert.equal(request(principal({subject})).body.subject,subject);
 }
 for(const subject of ['', ' subject','subject ', 'subject\u0085','\u0085subject','subject\nvalue','subject\u007f','😀'.repeat(501)])
  assert.throws(()=>prepareRegistration(principal({subject})),/Subject/);
});
test('display-name limits count code points and reject ambiguous edge whitespace',()=>{
 assert.equal(request(principal({displayName:'😀'.repeat(200)})).body.display_name,'😀'.repeat(200));
 for(const displayName of ['',' name','name\u3000','name\u0000','😀'.repeat(201)])
  assert.throws(()=>prepareRegistration(principal({displayName})),/Display name/);
});
test('unknown fields cannot request an active state, actor, issuer, credential or implicit role',()=>{
 for(const extra of [{issuer:'https://unapproved.test'},{actor:principalId},{token:'secret'},{status:'ACTIVE'},
  {role:'PLATFORM_ADMIN'},{scopeId}]){
  assert.throws(()=>prepareRegistration(principal(extra)),/fields/);
 }
 assert.throws(()=>prepareRegistration(grant('GLOBAL',{scopeId})),/fields/);
 for(const extra of [{status:'ACTIVE'},{actor:principalId},{api_url:'https://evil.test'}])
  assert.throws(()=>prepareRegistration(grant('PROJECT',extra)),/fields/);
});
test('exact UUID and cross-scope role validation rejects wrong targets and operations',()=>{
 for(const change of [{newId:'person-name'},{principalId:'../target'},{scopeId:'project-code'},
  {role:'PLATFORM_ADMIN'},{role:'SOFTWARE_VIEWER'}])
  assert.throws(()=>prepareRegistration(grant('PROJECT',change)));
 assert.throws(()=>prepareRegistration(grant('SOFTWARE',{role:'REVIEWER'})),/scope/);
 assert.throws(()=>prepareRegistration(principal({principalType:'ADMIN'})),/type/);
 assert.throws(()=>prepareRegistration(principal({kind:'../PRINCIPAL'})),/operation/);
});
test('audit and reason bounds preserve exact keys and backend-trimmed Unicode reasons',()=>{
 for(const eventNo of ['', ' key','key ', '/path','x'.repeat(51)])
  assert.throws(()=>prepareRegistration(principal({eventNo})),/Audit number/);
 for(const reason of ['four','x'.repeat(501),'reason\ncontrol','reason\u007fcontrol'])
  assert.throws(()=>prepareRegistration(principal({reason})),/Reason/);
 assert.equal(request(principal({reason:'😀'.repeat(500)})).body.reason,'😀'.repeat(500));
 assert.equal(request(principal({reason:'\u0085  Controlled reason  \u0085'})).body.reason,'Controlled reason');
 assert.equal(request(principal({eventNo:'A'.repeat(50)})).body.event_no,'A'.repeat(50));
});
test('immutable preview and explicit confirmation retain exact UUID/key/body on repeated export',()=>{
 const input=principal(),review=prepareRegistration(input);
 assert.throws(()=>exportRegistration(review),/Confirm/);
 const confirmed=confirmRegistration(review,true),before=exportRegistration(confirmed);
 input.subject='replacement';input.newId=principalId;input.eventNo='NEW';
 assert.equal(exportRegistration(confirmed),before);
 assert.throws(()=>{confirmed.request.body.subject='replacement';},TypeError);
 assert.throws(()=>{confirmed.request.path='/wrong';},TypeError);
 assert.throws(()=>exportRegistration(confirmRegistration(confirmed,false)),/Confirm/);
});
test('Chinese/English initial form exposes exact preparation fields without sending or credentials',()=>{
 const render=locale=>renderToStaticMarkup(React.createElement(LanguageProvider,{initialLocale:locale},
  React.createElement(Component)));
 const zh=render('zh'),en=render('en');
 assert.ok(zh.includes('准备新增身份或授权'));assert.ok(en.includes('Prepare identity or grant registration'));
 assert.ok(zh.includes('本表单不会创建身份或授权'));assert.ok(en.includes('does not create a provider account'));
 for(const html of [zh,en]){
  assert.ok(html.includes('name="subject"'));assert.ok(html.includes('name="principal_type"'));
  assert.ok(!html.includes('name="issuer"'));assert.ok(!html.includes('name="password"'));
  assert.ok(!html.includes('name="token"'));assert.ok(!html.includes('<pre>'));
  assert.ok(!html.includes('Send confirmed'));
 }
});
