'use strict';
const {test}=require('node:test');
const assert=require('node:assert/strict');
const {validateWorkerConfig,readWorkerConfig}=require('../scripts/check-worker-config.cjs');
const config=readWorkerConfig();
test('missing, disabled or non-boolean Preview URL settings fail the deploy preflight',()=>{
  for (const preview_urls of [undefined, false, 'true', 1]) {
    assert.throws(()=>validateWorkerConfig({...config,preview_urls}),/explicitly enabled/);
  }
});
test('Wrangler accepts explicit Preview bindings and existing OpenNext production config',()=>{
  assert.doesNotThrow(()=>validateWorkerConfig(config));
});
test('missing Preview block or runtime API is rejected before deploy',()=>{
  for(const previews of [undefined,{}, {vars:{}}]) {
    assert.throws(()=>validateWorkerConfig({...config,previews}),/explicit API_BASE_URL/);
  }
});
test('Preview cannot target a company endpoint or silently add resources and production routes',()=>{
  assert.throws(()=>validateWorkerConfig({...config,previews:{vars:{API_BASE_URL:'https://company.example'}}}),/explicit API_BASE_URL/);
  for(const extra of [{routes:config.routes},{d1_databases:[]},{vars:{...config.previews.vars,SECRET:'unexpected'}}]) {
    assert.throws(()=>validateWorkerConfig({...config,previews:{...config.previews,...extra}}),/separate reviewed configuration/);
  }
});
test('Preview changes cannot silently replace the production domain or OpenNext entry',()=>{
  assert.throws(()=>validateWorkerConfig({...config,routes:[{pattern:'preview.example',custom_domain:true}]}),/production API\/domain/);
  assert.throws(()=>validateWorkerConfig({...config,assets:{directory:'public',binding:'ASSETS'}}),/top level/);
});

test('repository-root Wrangler config supports the actual Workers Builds Preview command',()=>{
  const path=require('node:path');
  const root=readWorkerConfig(path.resolve(__dirname,'../../wrangler.jsonc'));
  assert.doesNotThrow(()=>validateWorkerConfig(root));
  assert.equal(root.previews.vars.API_BASE_URL, config.previews.vars.API_BASE_URL);
  assert.equal(root.build.command, 'cd frontend && npm ci && npx opennextjs-cloudflare build');
  assert.ok(root.main.replaceAll('\\','/').endsWith('/frontend/.open-next/worker.js'));
  assert.ok(root.assets.directory.replaceAll('\\','/') === 'frontend/.open-next/assets');
  assert.throws(()=>validateWorkerConfig({...root,previews:undefined}),/explicit API_BASE_URL/);
});
