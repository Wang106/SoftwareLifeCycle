import {test, expect, type Page, type Route, type Locator} from '@playwright/test';
import {exportAuthorizationApprovalRecovery, parseAuthorizationApprovalRecovery} from '../lib/authorization-approval-recovery';
import {confirmAuthorizationApproval} from '../lib/authorization-approval-transport';
const {buildHarness, startHarness} = require('./harness.cjs');
const {createHash} = require('node:crypto');
const target = {authorization_no: 'AUTH-原始'};
const id = (n: string) => `${n.repeat(8)}-${n.repeat(4)}-${n.repeat(4)}-${n.repeat(4)}-${n.repeat(12)}`;
const facts = {
  authorization_id:id('1'), authorization_no:target.authorization_no, release_id:id('2'),
  snapshot_id:id('3'), release_decision_id:id('4'), distribution_id:id('5'), delivery_package_id:id('6'),
  package_revision:2, customer_id:id('7'), project_id:id('8'), site_code:'Site', line_code:'Line',
  purpose:'PRODUCTION', batch_limit:5, restriction_note:'Synthetic scope only',
  creation_event_id:id('9'), creator_principal_id:id('a'),
};
const contextValue = {version:1, context:facts, context_digest:createHash('sha256')
  .update(JSON.stringify({context:Object.fromEntries(Object.entries(facts).sort(([a],[b]) => a<b?-1:a>b?1:0)),version:1})).digest('hex')};
const reason = 'Synthetic original reason 原文 <b>not markup</b>';
const scopeLabels: Record<string,string> = {
  authorization_id:'Authorization UUID',authorization_no:'Authorization number',release_id:'Release ID',
  snapshot_id:'Snapshot ID',release_decision_id:'Release decision UUID',distribution_id:'Distribution UUID',
  delivery_package_id:'Delivery package UUID',package_revision:'Package revision',customer_id:'Customer UUID',
  project_id:'Project UUID',site_code:'Site code',line_code:'Line code',purpose:'Purpose',batch_limit:'Batch limit',
  restriction_note:'Restriction note',creation_event_id:'Creation audit UUID',creator_principal_id:'Creator principal UUID',
};
const receiptLabels: Record<string,string> = {authorization_id:'Authorization UUID',authorization_no:'Authorization number',
  request_id:'Request ID',audit_event_no:'Audit event number',applied_status:'Original applied status',approved_at:'Approved at',
  creator_principal_id:'Creator principal UUID',approver_principal_id:'Approver principal UUID',
  expected_context_digest:'Expected context digest',reason:'Reason'};
const receiptLabelsZh: Record<string,string> = {authorization_id:'授权 UUID',authorization_no:'授权编号',request_id:'请求 ID',
  audit_event_no:'审计事件编号',applied_status:'原始已应用状态',approved_at:'批准时间',creator_principal_id:'创建者身份 UUID',
  approver_principal_id:'批准人身份 UUID',expected_context_digest:'预期上下文摘要',reason:'原因'};
const historicalEnglish='This receipt proves only the original APPROVED decision. It does not prove current eligibility, deployment, physical production or formal release.';
const historicalChinese='此回执仅证明原始 APPROVED 决策，不证明当前可用资格、部署、实际生产或正式发布。';
async function exactFields(section: Locator, values: Record<string,unknown>, labels: Record<string,string>) {
  await expect(section.locator('dl > div')).toHaveCount(Object.keys(values).length);
  for (const [key,value] of Object.entries(values)) {
    const label=section.getByText(labels[key],{exact:true});
    await expect(label).toHaveCount(1);
    await expect(label).toHaveJSProperty('tagName','DT');
    await expect(label.locator('..').locator('dd')).toHaveText(String(value));
  }
}

const api = ['/auth/authorization-approval-context','/auth/authorization-approval','/auth/authorization-approval-receipt'];
type Seen = {path:string;method:string;body:string};
let built: {bundlePath:string;dispose():Promise<void>};
let server: {origin:string;violations:unknown[];close():Promise<void>};
let reads: Seen[], blocked: string[], errors: string[], release: (() => void) | undefined;
type ErrorResponse = {status:number;error:string};
let responses: Partial<Record<'context'|'approval'|'receipt',ErrorResponse>>;
let held: Promise<void>, mode: 'allowed'|'creator-denied'|'unknown';
function receipt(command: any) {
  return {authorization_id:facts.authorization_id,authorization_no:target.authorization_no,
    request_id:command.body.request_id,audit_event_no:'EVT-PAA-'+command.body.request_id.replaceAll('-',''),
    applied_status:'APPROVED',approved_at:'2026-10-27T01:00:00.000001Z',creator_principal_id:facts.creator_principal_id,
    approver_principal_id:id('c'),expected_context_digest:contextValue.context_digest,reason:command.body.reason};
}
test.beforeAll(async () => { built = await buildHarness(); });
test.afterAll(async () => { if (built) await built.dispose(); });
test.beforeEach(async ({context, page}) => {
  server = await startHarness({bundlePath:built.bundlePath}); reads=[]; blocked=[]; errors=[]; mode='allowed'; responses={};
  held = new Promise(resolve => { release=resolve; });
  page.on('pageerror', error => errors.push(error.message));
  await context.routeWebSocket('**/*', socket => { blocked.push('websocket'); socket.close(); });
  await context.route('**/*', async (route: Route) => {
    const request=route.request(), url=new URL(request.url()), headers=await request.allHeaders();
    const path=url.pathname+url.search;
    const languageOnly=!headers.cookie || /^slc_language=(en|zh)$/.test(headers.cookie);
    const credentials=['authorization','proxy-authorization'].some(key => Object.hasOwn(headers,key));
    const staticGet=request.method()==='GET' && ['/component/approval','/component/readonly','/component/disabled','/component.js'].includes(path);
    const commandPost=request.method()==='POST' && api.includes(path) && request.resourceType()==='fetch';
    if(url.origin!==server.origin || !languageOnly || credentials || (!staticGet&&!commandPost)) {
      blocked.push(`${request.method()} ${url.pathname}`); await route.abort('blockedbyclient'); return;
    }
    if(staticGet) { await route.continue(); return; }
    const body=request.postData()||''; reads.push({path,method:request.method(),body});
    if(Buffer.byteLength(body)>8192 || headers['content-type']!=='application/json') {
      blocked.push('invalid-body'); await route.abort('blockedbyclient'); return;
    }
    let value; try { value=JSON.parse(body); } catch { blocked.push('invalid-json'); await route.abort('blockedbyclient');return; }
    if(path===api[0]) {
      expect(value).toEqual(target);
      const response=responses.context;
      await route.fulfill({status:response?.status??(mode==='creator-denied'?403:200),contentType:'application/json',
        body:JSON.stringify(response?{error:response.error}:mode==='creator-denied'?{error:'submission_forbidden'}:contextValue)}); return;
    }
    expect(value.target).toEqual(target); expect(value.context).toEqual(contextValue);
    if(path===api[1]) {
      await held;
      const response=responses.approval;
      await route.fulfill({status:response?.status??(mode==='unknown'?502:200),contentType:'application/json',
        body:JSON.stringify(response?{error:response.error}:mode==='unknown'?{error:'outcome_unknown'}:receipt(value))}); return;
    }
    const response=responses.receipt;
    await route.fulfill({status:response?.status??200,contentType:'application/json',
      body:JSON.stringify(response?{error:response.error}:receipt(value))});
  });
});
test.afterEach(async ({browser}, info) => {
  release?.();
  try {
    await info.attach('component-request-evidence',{body:JSON.stringify({layer:'component-only-synthetic-api',reads,blocked},null,2),contentType:'application/json'});
    expect(blocked).toEqual([]); expect(errors).toEqual([]); expect(server.violations).toEqual([]);
    if(info.status===info.expectedStatus && info.status==='passed') info.annotations.push(
      {type:'browser-engine',description:browser.browserType().name()},
      {type:'synthetic-component-fixture',description:'verified'},
      {type:'browser-worker-index',description:String(info.workerIndex)},
      {type:'evidence-layer',description:'component-only-not-authentication'},
    );
  } finally { await server.close(); }
});
async function open(page: Page, path='/component/approval') {
  await page.goto(server.origin+path);
  await expect(page.getByRole('heading',{name:'Review production authorization approval',exact:true})).toBeVisible();
  expect(reads).toEqual([]);
}
async function prepare(page: Page, submissionEnabled = true) {
  await page.getByRole('button',{name:'Load private approval context',exact:true}).click();
  const scope=page.getByRole('heading',{name:'Private approval context',exact:true}).locator('..');
  await exactFields(scope,facts,scopeLabels);
  await page.locator('textarea[name="reason"]').fill(reason);
  await page.getByRole('button',{name:'Prepare authorization approval',exact:true}).click();
  expect(reads.map(r=>r.path)).toEqual([api[0]]);
  const review=page.getByRole('heading',{name:'Review exact authorization approval',exact:true}).locator('..');
  const command=JSON.parse(await review.locator('pre code').first().innerText());
  expect(command.context).toEqual(contextValue); expect(command.body.reason).toBe(reason);
  expect(command.body.request_id).toMatch(/^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/);
  await expect(page.getByRole('button',{name:'Send confirmed authorization approval',exact:true})).toHaveCount(0);
  // Confirmation unmounts this one-shot checkbox; check() incorrectly waits
  // for the removed input to remain checked after the real click succeeds.
  await page.getByRole('checkbox').click();
  await expect(page.getByRole('checkbox')).toHaveCount(0);
  const send = page.getByRole('button',{name:'Send confirmed authorization approval',exact:true});
  await expect(send).toBeVisible();
  if (submissionEnabled) await expect(send).toBeEnabled();
  else await expect(send).toBeDisabled();
  return command;
}
test('synthetic creator denial never exposes an approval command or sends approval', async ({page}) => {
  mode='creator-denied'; await open(page);
  await page.getByRole('button',{name:'Load private approval context',exact:true}).click();
  await expect(page.getByRole('status')).toHaveText('Private approval context could not be loaded. Nothing was sent.');
  await expect(page.locator('textarea[name="reason"]')).toHaveCount(0);
  await expect(page.getByRole('checkbox')).toHaveCount(0);
  expect(reads.map(r=>r.path)).toEqual([api[0]]);
});
test('private synthetic scope is explicit and confirmation freezes the exact command', async ({page}) => {
  await open(page); const command=await prepare(page);
  await expect(page.locator('textarea[name="reason"]')).toBeDisabled();
  await expect(page.getByRole('button',{name:'Send confirmed authorization approval',exact:true})).toBeEnabled();
  expect(reads.map(r=>r.path)).toEqual([api[0]]);
  const exported=JSON.parse(await page.locator('pre code').first().innerText());
  expect(exported).toEqual(command);
});
test('duplicate clicks submit once and a valid synthetic reply confirms without automatic recovery', async ({page}) => {
  await open(page); const command=await prepare(page);
  const button=page.getByRole('button',{name:'Send confirmed authorization approval',exact:true});
  await button.evaluate((node: HTMLButtonElement) => {node.click();node.click();});
  await expect.poll(()=>reads.filter(r=>r.path===api[1]).length).toBe(1);
  // The send action is rendered only while idle, not as a disabled sending button.
  await expect(button).toHaveCount(0);
  const result=page.getByRole('heading',{name:'Authorization approval result',exact:true}).locator('..');
  await expect(result).toContainText('Operation phase: sending');
  expect(reads.find(r=>r.path===api[1])?.body).toBe(JSON.stringify(command));
  release?.();
  await exactFields(result,receipt(command),receiptLabels);
  await expect(result).toContainText('Operation phase: confirmed');
  await expect(result.getByText(historicalEnglish,{exact:true})).toBeVisible();
  await page.waitForTimeout(200);
  expect(reads.map(r=>r.path)).toEqual([api[0],api[1]]);
});
test('synthetic historical receipt is bilingual and raw reason is never HTML', async ({page}) => {
  await open(page); const command=await prepare(page); release?.();
  await page.getByRole('button',{name:'Send confirmed authorization approval',exact:true}).click();
  const result=page.getByRole('heading',{name:'Authorization approval result',exact:true}).locator('..');
  await expect(result.getByText(historicalEnglish,{exact:true})).toBeVisible();
  await exactFields(result,receipt(command),receiptLabels);
  await expect(result.locator('dl b')).toHaveCount(0);
  await page.getByRole('button',{name:'中文',exact:true}).click();
  await expect(page.locator('html')).toHaveAttribute('lang','zh-CN');
  const chineseResult=page.getByRole('heading',{name:'生产授权批准结果',exact:true}).locator('..');
  await expect(chineseResult.getByText(historicalChinese,{exact:true})).toBeVisible();
  await exactFields(chineseResult,receipt(command),receiptLabelsZh);
  await expect(chineseResult.locator('dl b')).toHaveCount(0);
  await expect(chineseResult).toContainText('操作阶段: 已确认');
  await page.getByRole('button',{name:'English',exact:true}).click();
  await expect(result.getByText(historicalEnglish,{exact:true})).toBeVisible();
  await exactFields(result,receipt(command),receiptLabels);
  expect(reads.map(r=>r.path)).toEqual([api[0],api[1]]);
});
test('disabled and readonly capabilities never send approval while explicit recovery only queries', async ({page}) => {
  await open(page,'/component/disabled');
  await expect(page.getByRole('button',{name:'Load private approval context',exact:true})).toBeDisabled();
  expect(reads).toEqual([]);
  await open(page,'/component/readonly'); await prepare(page, false);
  await expect(page.getByRole('button',{name:'Send confirmed authorization approval',exact:true})).toBeDisabled();
  expect(reads.map(r=>r.path)).toEqual([api[0]]);
  // A separate approval instance observes an unknown synthetic outcome; recovery is explicit.
  reads=[]; await open(page); mode='unknown'; await prepare(page); release?.();
  await page.getByRole('button',{name:'Send confirmed authorization approval',exact:true}).click();
  const query=page.getByRole('button',{name:'Query original audit without resubmitting',exact:true});
  await expect(query).toBeVisible(); expect(reads.map(r=>r.path)).toEqual([api[0],api[1]]);
  await query.click();
  await expect(query).toHaveCount(0);
  expect(reads.map(r=>r.path)).toEqual([api[0],api[1],api[2]]);
  expect(reads[2].body).toBe(reads[1].body);
});


test('unknown approval survives same-origin reload only through manual audit-only import and exact query', async ({page}) => {
  mode='unknown'; await open(page); const command=await prepare(page); release?.();
  await page.getByRole('button',{name:'Send confirmed authorization approval',exact:true}).click();
  const result=page.getByRole('heading',{name:'Authorization approval result',exact:true}).locator('..');
  await expect(result).toContainText('Operation phase: unknown');
  await expect(result).toContainText('outcome_unknown');
  expect(reads.map(r=>r.path)).toEqual([api[0],api[1]]);
  const originalBytes=reads[1].body;
  expect(originalBytes).toBe(JSON.stringify(command));
  const review=page.getByRole('heading',{name:'Review exact authorization approval',exact:true}).locator('..');
  await expect(review.locator('pre code')).toHaveCount(2);
  // Read the rendered export, never clipboard APIs or a reconstructed envelope.
  const recoveryText=await review.locator('pre code').nth(1).innerText();
  expect(JSON.parse(recoveryText)).toEqual({format:'slc-authorization-approval-recovery',version:1,origin:server.origin,...command});
  expect(command.target).toEqual(target);
  expect(command.context).toEqual(contextValue);
  expect(command.body.expected_context_digest).toBe(contextValue.context_digest);
  expect(command.body.reason).toBe(reason);
  const beforeReload=reads.slice(), originalURL=page.url();
  // The actual unknown-state beforeunload warning must be accepted to reload.
  page.once('dialog', async dialog => { expect(dialog.type()).toBe('beforeunload'); await dialog.accept(); });
  await page.reload();
  await expect(page).toHaveURL(originalURL);
  await expect(page.getByRole('heading',{name:'Review production authorization approval',exact:true})).toBeVisible();
  await expect(page.getByRole('heading',{name:'Restore an original approval audit query',exact:true})).toBeVisible();
  await expect(review).toHaveCount(0); await expect(result).toHaveCount(0);
  await expect(page.getByRole('heading',{name:'Private approval context',exact:true})).toHaveCount(0);
  await expect(page.locator('textarea[name="reason"]')).toHaveCount(0);
  await expect(page.locator('textarea[name="importText"]')).toHaveValue('');
  await expect(page.locator('pre code')).toHaveCount(0);
  await page.waitForTimeout(200);
  expect(reads).toEqual(beforeReload);
  await page.locator('textarea[name="importText"]').fill(recoveryText);
  expect(reads).toEqual(beforeReload);
  await page.getByRole('button',{name:'Import approval recovery without sending',exact:true}).click();
  const imported=page.getByRole('heading',{name:'Imported approval context — unverified evidence',exact:true}).locator('..');
  await exactFields(imported,facts,scopeLabels);
  await expect(page.getByText('Imported approval recovery is audit-only. Nothing was sent; explicitly query your original audit after signing in.',{exact:true})).toBeVisible();
  await expect(result).toContainText('Operation phase: unknown');
  expect(JSON.parse(await review.locator('pre code').first().innerText())).toEqual(command);
  await expect(review.locator('pre code').nth(1)).toHaveText(recoveryText);
  for(const name of ['Send confirmed authorization approval','Retry original authorization approval','Load private approval context','Prepare authorization approval']) {
    await expect(page.getByRole('button',{name,exact:true})).toHaveCount(0);
  }
  await expect(page.getByRole('checkbox')).toHaveCount(0);
  await expect(page.locator('textarea[name="reason"]')).toHaveCount(0);
  await page.waitForTimeout(200);
  expect(reads).toEqual(beforeReload);
  await page.getByRole('button',{name:'Query original audit without resubmitting',exact:true}).click();
  await exactFields(result,receipt(command),receiptLabels);
  await expect(result).toContainText('Operation phase: confirmed');
  await expect(result.getByText(historicalEnglish,{exact:true})).toBeVisible();
  await expect(result.locator('dl b')).toHaveCount(0);
  await expect(page.getByRole('button',{name:'Query original audit without resubmitting',exact:true})).toHaveCount(0);
  expect(JSON.parse(await review.locator('pre code').first().innerText())).toEqual(command);
  await page.waitForTimeout(200);
  expect(reads).toEqual([...beforeReload,{path:api[2],method:'POST',body:originalBytes}]);
});

function recoveryFixture(origin: string, authorizationNo=target.authorization_no) {
  const fixtureFacts={...facts,authorization_no:authorizationNo};
  const digest=createHash('sha256').update(JSON.stringify({context:Object.fromEntries(
    Object.entries(fixtureFacts).sort(([a],[b])=>a<b?-1:a>b?1:0)),version:1})).digest('hex');
  const command={operation:'authorization-approval' as const,target:{authorization_no:authorizationNo},
    context:{version:1 as const,context:fixtureFacts,context_digest:digest},
    body:{request_id:id('d'),expected_context_digest:digest,reason}};
  const text=exportAuthorizationApprovalRecovery(confirmAuthorizationApproval(command,true),origin);
  // The wrong-target negative is otherwise valid, not merely a malformed command.
  expect(parseAuthorizationApprovalRecovery(text,origin)).toEqual(command);
  return text;
}
async function rejectRecovery(page: Page, text: string) {
  await open(page);
  await page.locator('textarea[name="importText"]').fill(text);
  await page.getByRole('button',{name:'Import approval recovery without sending',exact:true}).click();
  await expect(page.getByRole('status')).toHaveText('Recovery text is invalid or does not match this site and authorization. Nothing was sent.');
  await expect(page.locator('textarea[name="importText"]')).toHaveValue(text);
  for(const name of ['Review exact authorization approval','Authorization approval result','Imported approval context — unverified evidence']) {
    await expect(page.getByRole('heading',{name,exact:true})).toHaveCount(0);
  }
  for(const name of ['Send confirmed authorization approval','Retry original authorization approval','Query original audit without resubmitting']) {
    await expect(page.getByRole('button',{name,exact:true})).toHaveCount(0);
  }
  await expect(page).toHaveURL(server.origin+'/component/approval');
  await page.waitForTimeout(200);
  expect(reads).toEqual([]);
}
test('fresh manual recovery rejects a foreign-origin envelope without any API request', async ({page}) => {
  const envelope=JSON.parse(recoveryFixture(server.origin));
  envelope.origin='https://foreign.example.test'; // Pasted text only; never navigate to this origin.
  await rejectRecovery(page,JSON.stringify(envelope,null,2));
});
test('fresh manual recovery rejects a valid wrong-target envelope without any API request', async ({page}) => {
  await rejectRecovery(page,recoveryFixture(server.origin,'AUTH-OTHER'));
});


for (const [title,status,error] of [
  ['synthetic context session unavailable fails closed without approval or receipt requests',401,'session_required'],
  ['synthetic context permission denied fails closed without approval or receipt requests',403,'submission_forbidden'],
  ['synthetic context target unavailable fails closed without approval or receipt requests',404,'target_not_found'],
] as const) test(title, async ({page}) => {
  responses.context={status,error}; await open(page);
  await page.getByRole('button',{name:'Load private approval context',exact:true}).click();
  await expect(page.getByRole('status')).toHaveText('Private approval context could not be loaded. Nothing was sent.');
  for (const name of ['Private approval context','Review exact authorization approval','Authorization approval result']) {
    await expect(page.getByRole('heading',{name,exact:true})).toHaveCount(0);
  }
  await expect(page.locator('textarea[name="reason"]')).toHaveCount(0);
  await expect(page.getByRole('checkbox')).toHaveCount(0);
  await expect(page.locator('pre code')).toHaveCount(0);
  for (const name of ['Prepare authorization approval','Send confirmed authorization approval','Retry original authorization approval','Query original audit without resubmitting']) {
    await expect(page.getByRole('button',{name,exact:true})).toHaveCount(0);
  }
  await page.waitForTimeout(200);
  expect(reads).toEqual([{path:api[0],method:'POST',body:JSON.stringify(target)}]);
});

async function noReceipt(page: Page, result: Locator) {
  await expect(result.locator('dl')).toHaveCount(0);
  await expect(page.getByRole('link',{name:'Open original approval audit',exact:true})).toHaveCount(0);
  for (const name of ['Send confirmed authorization approval','Retry original authorization approval']) {
    await expect(page.getByRole('button',{name,exact:true})).toHaveCount(0);
  }
}

test('synthetic permission loss after review rejects once and preserves the frozen command', async ({page}) => {
  await open(page); const command=await prepare(page);
  const review=page.getByRole('heading',{name:'Review exact authorization approval',exact:true}).locator('..');
  const frozenText=await review.locator('pre code').first().innerText();
  responses.approval={status:403,error:'submission_forbidden'}; release?.();
  await page.getByRole('button',{name:'Send confirmed authorization approval',exact:true}).click();
  const result=page.getByRole('heading',{name:'Authorization approval result',exact:true}).locator('..');
  await expect(result).toContainText('Operation phase: rejected');
  await expect(result.locator('code')).toHaveText('submission_forbidden');
  await expect(result.getByText('This attempt was rejected before a confirmed result. Reload private approval context before preparing another request.',{exact:true})).toBeVisible();
  await noReceipt(page,result);
  for (const name of ['Query original audit without resubmitting','Reload context for a new approval']) {
    await expect(page.getByRole('button',{name,exact:true})).toBeEnabled();
  }
  await expect(review.locator('pre code').first()).toHaveText(frozenText);
  expect(JSON.parse(await review.locator('pre code').first().innerText())).toEqual(command);
  await page.waitForTimeout(200);
  expect(reads).toEqual([{path:api[0],method:'POST',body:JSON.stringify(target)},
    {path:api[1],method:'POST',body:JSON.stringify(command)}]);
});

for (const [title,status,error] of [
  ['imported synthetic recovery session unavailable preserves unknown audit-only state',401,'session_required'],
  ['imported synthetic original receipt unavailable preserves unknown audit-only state',502,'outcome_unknown'],
] as const) test(title, async ({page}) => {
  responses.receipt={status,error}; await open(page);
  const recoveryText=recoveryFixture(server.origin);
  const command=parseAuthorizationApprovalRecovery(recoveryText,server.origin);
  expect(command).not.toBeNull();
  await page.locator('textarea[name="importText"]').fill(recoveryText);
  await page.getByRole('button',{name:'Import approval recovery without sending',exact:true}).click();
  const result=page.getByRole('heading',{name:'Authorization approval result',exact:true}).locator('..');
  const review=page.getByRole('heading',{name:'Review exact authorization approval',exact:true}).locator('..');
  const scope=page.getByRole('heading',{name:'Imported approval context — unverified evidence',exact:true}).locator('..');
  await exactFields(scope,facts,scopeLabels);
  await expect(result).toContainText('Operation phase: unknown');
  const frozenText=await review.locator('pre code').first().innerText();
  expect(JSON.parse(frozenText)).toEqual(command);
  await expect(review.locator('pre code').nth(1)).toHaveText(recoveryText);
  await page.waitForTimeout(200); expect(reads).toEqual([]);
  const query=page.getByRole('button',{name:'Query original audit without resubmitting',exact:true});
  await query.click();
  await expect(result).toContainText('Operation phase: unknown');
  await expect(result.locator('code')).toHaveText(error);
  await expect(result.getByText('The original outcome is unknown. Keep this request and query its original audit; do not prepare a replacement.',{exact:true})).toBeVisible();
  await noReceipt(page,result);
  for (const name of ['Load private approval context','Prepare authorization approval','Reload context for a new approval']) {
    await expect(page.getByRole('button',{name,exact:true})).toHaveCount(0);
  }
  await expect(page.getByRole('checkbox')).toHaveCount(0);
  await expect(page.locator('textarea[name="reason"]')).toHaveCount(0);
  await expect(query).toBeEnabled();
  await exactFields(scope,facts,scopeLabels);
  await expect(review.locator('pre code').first()).toHaveText(frozenText);
  expect(JSON.parse(await review.locator('pre code').first().innerText())).toEqual(command);
  await expect(review.locator('pre code').nth(1)).toHaveText(recoveryText);
  await page.waitForTimeout(200);
  expect(reads).toEqual([{path:api[2],method:'POST',body:JSON.stringify(command)}]);
});


test('cancelling an unknown approval reload retains the original document and frozen request', async ({page}) => {
  mode='unknown'; await open(page); const command=await prepare(page); release?.();
  await page.getByRole('button',{name:'Send confirmed authorization approval',exact:true}).click();
  const result=page.getByRole('heading',{name:'Authorization approval result',exact:true}).locator('..');
  const review=page.getByRole('heading',{name:'Review exact authorization approval',exact:true}).locator('..');
  await expect(result).toContainText('Operation phase: unknown');
  const commandText=await review.locator('pre code').first().innerText();
  const recoveryText=await review.locator('pre code').nth(1).innerText();
  expect(JSON.parse(commandText)).toEqual(command);
  const expectedReads=[{path:api[0],method:'POST',body:JSON.stringify(target)},
    {path:api[1],method:'POST',body:JSON.stringify(command)}];
  expect(reads).toEqual(expectedReads);
  const originalURL=page.url(), marker='retained-'+command.body.request_id;
  await page.evaluate(value=>{document.documentElement.dataset.b3DocumentMarker=value;},marker);
  // The user dismisses the real navigation warning, not a business cancellation.
  const dismissed=new Promise<void>((resolve,reject)=>page.once('dialog',async dialog=>{
    try { expect(dialog.type()).toBe('beforeunload'); await dialog.dismiss(); resolve(); }
    catch(error) { reject(error); }
  }));
  const [cancelled]=await Promise.all([page.reload().then(()=>false,()=>true),dismissed]);
  expect(cancelled).toBe(true);
  // A rejected navigation alone is insufficient: prove the old document/state survives.
  await expect(page).toHaveURL(originalURL);
  await expect(page.locator('html')).toHaveAttribute('data-b3-document-marker',marker);
  await expect(result).toContainText('Operation phase: unknown');
  await expect(result.locator('code')).toHaveText('outcome_unknown');
  await expect(review.locator('pre code').first()).toHaveText(commandText);
  expect(JSON.parse(await review.locator('pre code').first().innerText())).toEqual(command);
  await expect(review.locator('pre code').nth(1)).toHaveText(recoveryText);
  await exactFields(page.getByRole('heading',{name:'Private approval context',exact:true}).locator('..'),facts,scopeLabels);
  await expect(page.locator('textarea[name="reason"]')).toHaveValue(reason);
  await expect(page.locator('textarea[name="reason"]')).toBeDisabled();
  await expect(page.getByRole('button',{name:'Retry original authorization approval',exact:true})).toBeEnabled();
  await expect(page.getByRole('button',{name:'Query original audit without resubmitting',exact:true})).toBeEnabled();
  await expect(page.getByRole('button',{name:'Reload context for a new approval',exact:true})).toHaveCount(0);
  await expect(result.locator('dl')).toHaveCount(0);
  await expect(page.getByRole('link',{name:'Open original approval audit',exact:true})).toHaveCount(0);
  await page.waitForTimeout(200);
  expect(reads).toEqual(expectedReads);
});

test('explicit unknown approval retry sends original bytes once despite duplicate clicks', async ({page}) => {
  mode='unknown'; await open(page); const command=await prepare(page); release?.();
  await page.getByRole('button',{name:'Send confirmed authorization approval',exact:true}).click();
  const result=page.getByRole('heading',{name:'Authorization approval result',exact:true}).locator('..');
  const review=page.getByRole('heading',{name:'Review exact authorization approval',exact:true}).locator('..');
  await expect(result).toContainText('Operation phase: unknown');
  const frozenText=await review.locator('pre code').first().innerText();
  const recoveryText=await review.locator('pre code').nth(1).innerText();
  expect(JSON.parse(frozenText)).toEqual(command);
  const firstReads=[{path:api[0],method:'POST',body:JSON.stringify(target)},
    {path:api[1],method:'POST',body:JSON.stringify(command)}];
  await page.waitForTimeout(200); expect(reads).toEqual(firstReads);
  // Reset the previously released promise so the retry is genuinely in flight.
  held=new Promise(resolve=>{release=resolve;}); mode='allowed';
  const retry=page.getByRole('button',{name:'Retry original authorization approval',exact:true});
  await expect(retry).toBeEnabled();
  await retry.evaluate((node:HTMLButtonElement)=>{node.click();node.click();});
  await expect.poll(()=>reads.filter(r=>r.path===api[1]).length).toBe(2);
  await expect(result).toContainText('Operation phase: sending');
  for(const name of ['Send confirmed authorization approval','Retry original authorization approval','Query original audit without resubmitting','Reload context for a new approval']) {
    await expect(page.getByRole('button',{name,exact:true})).toHaveCount(0);
  }
  await expect(review.locator('pre code').first()).toHaveText(frozenText);
  await expect(review.locator('pre code').nth(1)).toHaveText(recoveryText);
  await expect(result.locator('dl')).toHaveCount(0);
  const expectedReads=[...firstReads,{path:api[1],method:'POST',body:JSON.stringify(command)}];
  await page.waitForTimeout(200); expect(reads).toEqual(expectedReads);
  release?.();
  await expect(result).toContainText('Operation phase: confirmed');
  await exactFields(result,receipt(command),receiptLabels);
  await expect(result.getByText(historicalEnglish,{exact:true})).toBeVisible();
  await expect(page.getByRole('link',{name:'Open original approval audit',exact:true})).toHaveAttribute('href','/activity/'+receipt(command).audit_event_no);
  expect(JSON.parse(await review.locator('pre code').first().innerText())).toEqual(command);
  await expect(review.locator('pre code').first()).toHaveText(frozenText);
  await expect(review.locator('pre code').nth(1)).toHaveText(recoveryText);
  for(const name of ['Send confirmed authorization approval','Retry original authorization approval','Query original audit without resubmitting']) {
    await expect(page.getByRole('button',{name,exact:true})).toHaveCount(0);
  }
  await page.waitForTimeout(200); expect(reads).toEqual(expectedReads);
});
