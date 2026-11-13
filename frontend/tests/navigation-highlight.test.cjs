'use strict';
const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const ts = require('typescript');
const React = require('react');
const { renderToStaticMarkup } = require('react-dom/server');

const layout = fs.readFileSync('app/layout.tsx', 'utf8');
const navigation = layout.match(/<nav className="nav">([\s\S]*?)<\/nav>/)[1];
const destinations = [...navigation.matchAll(/<Link\b[^>]*href="([^"]+)"/g)].map(match => match[1]);
function harness() {
  let pathname = '/';
  let allowed = [];
  let observed;
  const module = { exports: {} };
  const stubs = {
    react: { ...React, useContext: () => ({ allowed }) },
    'next/navigation': { usePathname: () => pathname },
    'next/link': props => {
      observed = props;
      const { prefetch, children, ...attributes } = props;
      return React.createElement('a', attributes, children);
    },
    './localized': { Localized: ({ children }) => children },
    '../lib/prefetch-queue': {},
  };
  const code = ts.transpileModule(fs.readFileSync('components/navigation-priority.tsx', 'utf8'), {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2021, jsx: ts.JsxEmit.ReactJSX, esModuleInterop: true },
  }).outputText;
  new Function('require', 'module', 'exports', code)(name => stubs[name] ?? require(name), module, module.exports);
  return {
    render(path, href, props = {}) {
      pathname = path;
      const html = renderToStaticMarkup(React.createElement(module.exports.PriorityLink,
        { href, allowBackground: true, highlightCurrent: true, ...props }, '导航 / Navigation'));
      return { html, props: observed };
    },
    allow(routes) { allowed = routes; },
  };
}
function activeLinks(h, path) {
  return destinations.filter(href => h.render(path, href).props['aria-current'] === 'page');
}

test('every actual sidebar destination is opted in, without marking brand or header links', () => {
  assert.equal(destinations.length, 21);
  const links = [...navigation.matchAll(/<Link\b[^>]*>/g)].map(match => match[0]);
  for (const link of links) assert.match(link, /\bhighlightCurrent\b/);
  assert.doesNotMatch(layout.replace(navigation, ''), /<Link\b[^>]*\bhighlightCurrent\b/);
});
for (const href of destinations) {
  test('sidebar marks only the exact route and segment descendants: ' + href, () => {
    const h = harness();
    assert.deepEqual(activeLinks(h, href), [href]);
    if (href !== '/') {
      for (const path of [href + '/', href + '/record%20name', href + '/record/history']) {
        assert.deepEqual(activeLinks(h, path), [href]);
      }
      for (const path of [href + '-archive', href + 's', href + '%2Frecord']) {
        assert.deepEqual(activeLinks(h, path), []);
      }
    }
  });
}

test('home never matches other paths and absent or unlisted routes select nothing', () => {
  const h = harness();
  for (const path of [null, '', '/account', '/search', '/create', '/unknown', '/releases', '/testing']) {
    assert.deepEqual(activeLinks(h, path), []);
  }
});

test('route changes and repeated back/forward values recompute selection without click state', () => {
  const h = harness();
  for (const path of ['/', '/changes', '/issues', '/changes', '/', '/changes', '/issues', '/issues']) {
    assert.deepEqual(activeLinks(h, path), [path]);
  }
});

test('highlight is opt-in, preserves classes, content, destination and bounded prefetch admission', () => {
  const h = harness();
  let result = h.render('/changes', '/changes', { className: 'existing' });
  assert.equal(result.props.className, 'existing');
  assert.equal(result.props.href, '/changes');
  assert.equal(result.props.prefetch, false);
  assert.equal(result.props['aria-current'], 'page');
  assert.ok(result.html.includes('导航 / Navigation'));
  assert.ok(!('highlightCurrent' in result.props));
  h.allow(['/changes']);
  assert.equal(h.render('/changes', '/changes').props.prefetch, true);
  assert.equal(h.render('/issues', '/changes').props.prefetch, true);
  assert.equal(h.render('/issues', '/issues').props.prefetch, false);
  assert.equal(h.render('/changes', '/changes', { allowBackground: false }).props.prefetch, false);
  assert.equal(h.render('/changes', '/changes', { highlightCurrent: false }).props['aria-current'], undefined);
  h.allow([]);
  assert.equal(h.render('/changes', '/changes').props.prefetch, false);
});

test('active navigation has a distinct persistent color and weight scoped to the sidebar', () => {
  const css = fs.readFileSync('app/globals.css', 'utf8');
  assert.match(css, /\.nav a\[aria-current="page"\]\{[^}]*background:#1e3a5f[^}]*color:#93c5fd[^}]*font-weight:700/);
  assert.ok(css.indexOf('.nav a[aria-current="page"]') > css.indexOf('.nav a:hover'));
});
