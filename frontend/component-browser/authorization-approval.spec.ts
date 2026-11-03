import {test, expect, type Page, type Route, type Locator} from '@playwright/test';
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
  server = await startHarness({bundlePath:built.bundlePath}); reads=[]; blocked=[]; errors=[]; mode='allowed';
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
      await route.fulfill({status:mode==='creator-denied'?403:200,contentType:'application/json',
        body:JSON.stringify(mode==='creator-denied'?{error:'submission_forbidden'}:contextValue)}); return;
    }
    expect(value.target).toEqual(target); expect(value.context).toEqual(contextValue);
    if(path===api[1]) {
      await held;
      await route.fulfill({status:mode==='unknown'?502:200,contentType:'application/json',
        body:JSON.stringify(mode==='unknown'?{error:'outcome_unknown'}:receipt(value))}); return;
    }
    await route.fulfill({status:200,contentType:'application/json',body:JSON.stringify(receipt(value))});
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
  await expect(button).toBeDisabled();
  expect(reads.find(r=>r.path===api[1])?.body).toBe(JSON.stringify(command));
  release?.();
  const result=page.getByRole('heading',{name:'Authorization approval result',exact:true}).locator('..');
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
