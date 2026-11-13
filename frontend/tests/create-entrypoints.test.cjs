'use strict';
const { test, after } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const os = require('node:os');
const ts = require('typescript');
const React = require('react');
const { renderToStaticMarkup } = require('react-dom/server');
const output = fs.mkdtempSync(path.join(os.tmpdir(), 'slc-create-entrypoints-'));
require('node:child_process').execFileSync(process.execPath, [require.resolve('typescript/bin/tsc'),
  'app/create/page.tsx', 'components/command-workbench.tsx', '--target', 'ES2021', '--module', 'commonjs',
  '--jsx', 'react-jsx', '--esModuleInterop', '--resolveJsonModule', '--strict', '--skipLibCheck', '--outDir', output]);
fs.symlinkSync(path.resolve('node_modules'), path.join(output, 'node_modules'), 'dir');
after(() => fs.rmSync(output, { recursive: true, force: true }));
const Page = require(path.join(output, 'app/create/page.js')).default;
const Workbench = require(path.join(output, 'components/command-workbench.js')).default;
const { LanguageProvider } = require(path.join(output, 'components/localized.js'));
const dictionary = require('../lib/i18n/zh.json');
const render = (locale, node) => renderToStaticMarkup(React.createElement(LanguageProvider, { initialLocale: locale }, node));
const center = locale => render(locale, React.createElement(Page));
const available = [
  ['Prepare controlled request', '/commands'],
  ['Test Release', '/commands?operation=test-release'],
  ['Delivery Packages', '/commands?operation=delivery'],
  ['Production Authorizations', '/commands?operation=authorization'],
];
const unavailable = [
  ['Software Change Request', '/changes'], ['Issue', '/issues'],
  ['DVP Plan', '/testing/dvp'], ['Application Release', '/releases/application'],
];
for (const [label, href] of available) {
  test(label + ' opens the preparation form rather than a catalog, in both languages', () => {
    for (const locale of ['en', 'zh']) {
      const links = center(locale).match(/<a\b[\s\S]*?<\/a>/g) || [];
      const link = links.find(value => value.includes('<b>' + (locale === 'en' ? label : dictionary[label]) + '</b>'));
      assert.ok(link, label);
      assert.ok(link.includes('href="' + href + '"'), link);
      assert.ok(link.includes(locale === 'en' ? 'Open form' : '打开填写表单'));
    }
  });
}
for (const [label, href] of unavailable) {
  test(label + ' is explicitly unavailable, with a separate browse-only link', () => {
    for (const locale of ['en', 'zh']) {
      const cards = center(locale).match(/<article\b[\s\S]*?<\/article>/g) || [];
      const card = cards.find(value => value.includes('<b>' + (locale === 'en' ? label : dictionary[label]) + '</b>'));
      assert.ok(card, label);
      assert.ok(card.includes(locale === 'en' ? 'Creation form not implemented' : '新建表单尚未实现'));
      assert.ok(card.includes('href="' + href + '"'));
      assert.ok(card.includes(locale === 'en' ? 'Browse existing records' : '浏览已有记录'));
      assert.doesNotMatch(card, /<a\b[^>]*>[\s\S]*?<b>/);
    }
  });
}
test('create center separates preparation, authorized submission and unavailable upload in both languages', () => {
  for (const locale of ['en', 'zh']) {
    const html = center(locale);
    assert.ok(html.includes(locale === 'en'
      ? 'Available forms prepare requests. Submission still requires an approved signed-in environment; the public demo remains read-only.'
      : '已有表单可填写并准备请求；提交仍需获准且已登录的环境，公开演示保持只读。'));
    assert.ok(html.includes(locale === 'en'
      ? 'File upload is not implemented. Resource references do not upload or store files.'
      : '文件上传尚未实现；资源引用不会上传或存储文件。'));
    assert.doesNotMatch(html, /<form\b|type="file"|<button[^>]*type="submit"/);
  }
});
function nodes(node) {
  return Array.isArray(node) ? node.flatMap(nodes) : node && typeof node === 'object'
    ? [node, ...nodes(node.props?.children)] : [];
}
async function destination(href) {
  const module = { exports: {} };
  const code = ts.transpileModule(fs.readFileSync('app/commands/page.tsx', 'utf8'), {
    compilerOptions: { target: ts.ScriptTarget.ES2021, module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX, esModuleInterop: true },
  }).outputText;
  new Function('require', 'module', 'exports', code)(name => {
    if (name === 'next/headers') return { cookies: () => { throw Error('No identity read in disabled public mode'); } };
    if (name === '../../lib/browser-auth') return new Proxy({}, { get: (_, key) => key === 'authConfig' ? async () => null : () => false });
    if (name === '../../lib/browser-session') return { resolveSession: () => { throw Error('No session resolution in disabled public mode'); } };
    if (name.startsWith('../../')) return require(path.join(output, name.slice(6)));
    return require(name);
  }, module, module.exports);
  const query = Object.fromEntries(new URL(href, 'https://example.invalid').searchParams);
  const tree = await module.exports.default({ searchParams: Promise.resolve(query) });
  return nodes(tree).find(node => node.type === Workbench);
}
for (const [label, href] of available.slice(1)) {
  test(label + ' destination selects its existing editable form without enabling any write capability', async () => {
    const html = center('en');
    const link = (html.match(/<a\b[\s\S]*?<\/a>/g) || []).find(value => value.includes('<b>' + label + '</b>'));
    assert.ok(link.includes('href="' + href + '"'));
    const workbench = await destination(href);
    const operation = new URL(href, 'https://example.invalid').searchParams.get('operation');
    assert.equal(workbench.props.initialOperation, operation);
    assert.equal(workbench.props.initialTarget, '');
    for (const [name, value] of Object.entries(workbench.props)) {
      if (name.endsWith('Enabled')) assert.equal(value, false, name);
    }
    const fields = {
      'test-release': ['testReleaseNo', 'snapshot', 'actor'],
      delivery: ['packageNo', 'revision', 'recipientType', 'recipientCode'],
      authorization: ['authorizationNo', 'release', 'customer', 'project', 'site', 'line'],
    }[operation];
    for (const locale of ['en', 'zh']) {
      const form = render(locale, workbench);
      assert.ok(form.includes('value="' + operation + '" selected=""'));
      for (const name of fields) assert.ok(form.includes('name="' + name + '"'), name);
      assert.doesNotMatch(form, /<fieldset[^>]*disabled/);
      assert.doesNotMatch(form, /type="file"|Send confirmed business request|发送已确认的业务请求/);
    }
  });
}
