'use strict';
const {test}=require('node:test');
const assert=require('node:assert/strict');
const {validateWorkerConfig,readWorkerConfig}=require('../scripts/check-worker-config.cjs');
const config=readWorkerConfig();
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
