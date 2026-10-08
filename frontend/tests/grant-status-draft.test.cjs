'use strict';
const { test, after } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs'), path = require('node:path');
const { execFileSync } = require('node:child_process');
const output = fs.mkdtempSync(path.join(require('node:os').tmpdir(), 'slc-grant-draft-'));
execFileSync(process.execPath, [require.resolve('typescript/bin/tsc'),
  'lib/grant-status-draft.ts', 'components/grant-status-preparation.tsx',
  '--target', 'ES2021', '--module', 'commonjs', '--jsx', 'react-jsx', '--esModuleInterop',
  '--resolveJsonModule', '--strict', '--skipLibCheck', '--outDir', output]);
fs.symlinkSync(path.resolve('node_modules'), path.join(output, 'node_modules'), 'dir');
const { prepareGrantStatus, confirmGrantStatus, exportGrantStatus } = require(path.join(output, 'lib/grant-status-draft.js'));
const React = require('react'), { renderToStaticMarkup } = require('react-dom/server');
const Component = require(path.join(output, 'components/grant-status-preparation.js')).default;
const { LanguageProvider } = require(path.join(output, 'components/localized.js'));
after(() => fs.rmSync(output, { recursive: true, force: true }));
const id = '12345678-1234-1234-1234-123456789abc', principalId = '23456789-1234-1234-1234-123456789abc';
const target = { id, principalId, scope: 'GLOBAL', role: 'PLATFORM_ADMIN', status: 'ACTIVE', historyStatus: 'ACTIVE' };
for (const scope of ['GLOBAL', 'PROJECT', 'SOFTWARE']) for (const status of ['ACTIVE', 'SUSPENDED']) {
  test('exact API contract: ' + scope + ' ' + status, () => {
    const role = scope === 'GLOBAL' ? 'PLATFORM_ADMIN' : 'REVIEWER';
    const review = prepareGrantStatus({ ...target, scope, role, status, historyStatus: status, id: id.toUpperCase() }, 'ADM:001', '  测试授权状态变更原因  ');
    assert.throws(() => exportGrantStatus(review), /Confirm/);
    const request = JSON.parse(exportGrantStatus(confirmGrantStatus(review, true)));
    assert.deepEqual(request, { method: 'POST',
      path: scope === 'GLOBAL' ? '/api/v1/security/admin/global-roles/' + id + '/status' :
        '/api/v1/security/admin/memberships/' + scope + '/' + id + '/status',
      body: { event_no: 'ADM:001', expected_status: status, status: status === 'ACTIVE' ? 'SUSPENDED' : 'ACTIVE', reason: '测试授权状态变更原因' } });
    assert.equal(review.target.principalId, principalId);
    assert.ok(!('principal_id' in request.body)); assert.ok(!('actor' in request.body));
  });
}
test('invalid identity, scopes and inconsistent read snapshots cannot produce a request', () => {
  for (const change of [{ scope: '../GLOBAL' }, { id: '../admin' }, { principalId: 'person-name' },
    { role: '' }, { status: 'DISABLED' }, { historyStatus: 'SUSPENDED' }])
    assert.throws(() => prepareGrantStatus({ ...target, ...change }, 'ADM-1', 'Controlled reason'));
});
test('audit keys reject malformed and overlength values and preserve valid exact keys', () => {
  for (const key of ['', '/bad', '.bad', 'bad key', 'x'.repeat(51), 'key/secret'])
    assert.throws(() => prepareGrantStatus(target, key, 'Controlled reason'), /Audit number/);
  for (const key of ['A', 'A'.repeat(50), 'ADM:1_key-2.3'])
    assert.equal(prepareGrantStatus(target, key, 'Controlled reason').request.body.event_no, key);
});
test('reason boundaries match printable Unicode code-point API semantics', () => {
  for (const reason of ['four', '  abc  ', 'x'.repeat(501), 'reason\ncontrol', 'reason\u007fcontrol'])
    assert.throws(() => prepareGrantStatus(target, 'ADM-1', reason), /Reason/);
  assert.equal(Array.from(prepareGrantStatus(target, 'ADM-1', '😀'.repeat(500)).request.body.reason).length, 500);
  assert.throws(() => prepareGrantStatus(target, 'ADM-1', '😀'.repeat(501)), /Reason/);
});
test('review is immutable, repeat export retains body/key and unchecking forbids export', () => {
  const source = { ...target }, review = confirmGrantStatus(prepareGrantStatus(source, 'ADM-1', 'Controlled reason'), true);
  const before = exportGrantStatus(review);
  source.id = principalId; source.status = 'SUSPENDED';
  assert.equal(exportGrantStatus(review), before);
  assert.throws(() => { review.request.body.event_no = 'OTHER'; }, TypeError);
  assert.throws(() => { review.target.principalId = id; }, TypeError);
  assert.throws(() => exportGrantStatus(confirmGrantStatus(review, false)), /Confirm/);
});
test('preparation renders Chinese/English without credentials, submission or browser persistence', () => {
  const render = locale => renderToStaticMarkup(React.createElement(LanguageProvider, { initialLocale: locale }, React.createElement(Component, { target })));
  assert.ok(render('zh').includes('准备授权状态变更'));
  assert.ok(render('en').includes('Prepare grant status change'));
  assert.ok(render('zh').includes('本表单不会修改权限'));
  const source = fs.readFileSync('components/grant-status-preparation.tsx', 'utf8');
  assert.ok(!/fetch\(|localStorage|sessionStorage|Authorization|Bearer/.test(source));
  assert.ok(source.includes('setReview(null)')); // Editing invalidates preview and its confirmation.
  assert.ok(source.includes('disabled={!review.confirmed || copying}'));
});

test('controlled form SSR separates preparation from explicitly enabled submission',()=>{
 const render=(locale,submissionEnabled)=>renderToStaticMarkup(React.createElement(LanguageProvider,{initialLocale:locale},
  React.createElement(Component,{target,submissionEnabled})));
 assert.ok(render('zh',true).includes('此环境可进行受控提交'));
 assert.ok(render('en',true).includes('Controlled submission is available'));
 for(const enabled of [false,true])assert.ok(!render('en',enabled).includes('Send confirmed grant request'));
 // No request is reviewed/confirmed in the initial render, even with the server capability.
});
