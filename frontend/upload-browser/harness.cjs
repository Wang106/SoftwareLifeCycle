'use strict';
const fs=require('node:fs'),os=require('node:os'),path=require('node:path'),http=require('node:http'),{execFileSync}=require('node:child_process');
const {startStorage}=require('./storage-api.cjs'),{ORIGIN,createRelay}=require('./relay-bridge.cjs');
const frontend=path.resolve(__dirname,'..');
async function buildHarness(){
  const directory=fs.mkdtempSync(path.join(os.tmpdir(),'slc-upload-browser-'));
  let identity;try{identity=fs.lstatSync(directory)}catch(e){fs.rmdirSync(directory);throw e}let disposed=false;
  const dispose=()=>{if(disposed)throw Error('already disposed');const current=fs.lstatSync(directory);if(current.ino!==identity.ino||current.dev!==identity.dev||!current.isDirectory()||current.isSymbolicLink())throw Error('build directory changed');fs.rmSync(directory,{recursive:true});if(fs.existsSync(directory))throw Error('build cleanup incomplete');disposed=true;};
  try{
    const compiled=path.join(directory,'compiled'),bundlePath=path.join(directory,'bundle','component.js');
    // Use the already locked TypeScript and Next webpack, not new dependencies,
    // JSX/hook mocks, production output directories, or an authentication bypass.
    execFileSync(process.execPath,[require.resolve('typescript/bin/tsc'),
      'upload-browser/entry.tsx','lib/private-upload-proxy.ts','--target','ES2021','--module','commonjs',
      '--jsx','react-jsx','--esModuleInterop','--resolveJsonModule','--strict',
      '--skipLibCheck','--outDir',compiled],{cwd:frontend,stdio:'pipe',timeout:60000});
    const bundledWebpack=require('next/dist/compiled/webpack/webpack');
    const webpack=bundledWebpack.webpack;
    const stats=await new Promise((resolve,reject)=>{
      const compiler=webpack({mode:'production',target:'web',devtool:false,
        entry:path.join(compiled,'upload-browser','entry.js'),
        output:{path:path.dirname(bundlePath),filename:'component.js'},
        resolve:{modules:[path.join(frontend,'node_modules'),'node_modules']},
        optimization:{minimize:false},performance:false,
        plugins:[new webpack.DefinePlugin({'process.env':JSON.stringify({NODE_ENV:'production'})})],
      });
      compiler.run((error,result)=>compiler.close(closeError=>{
        if(error||closeError)return reject(error||closeError);
        if(!result||result.hasErrors())return reject(Error(result?.toString({all:false,errors:true})||'No webpack result'));
        resolve(result);
      }));
    });
    const modules=stats.toJson({all:false,modules:true,nestedModules:true}).modules||[];
    const names=[];
    function visit(items){for(const item of items){if(item.name)names.push(item.name);if(item.modules)visit(item.modules);if(item.children)visit(item.children);}}
    visit(modules);
    for(const required of ['private-upload-picker.js','private-upload-draft.js','private-upload-journal.js','localized.js','react-dom']){
      if(!names.some(name=>name.replaceAll('\\','/').includes(required)))throw Error(`Missing real component dependency: ${required}`);
    }
    return {directory,compiled,bundlePath,modules:names,dispose};
  }catch(error){dispose();throw error;}
}

async function startHarness(built,options={}){
 const storage=await startStorage(options);let server;
 try {
 const relay=await createRelay(built.compiled,storage.origin),bundle=fs.readFileSync(built.bundlePath),violations=[],pending=new Set();let origin;
 const html='<!doctype html><html lang="en"><head><meta charset="utf-8"><link rel="icon" href="data:,"><title>Synthetic upload</title></head><body><main id="fixture-root"></main><script defer src="/component.js"></script></body></html>';
 async function handle(req,res){const reject=()=>{violations.push('unexpected-request');res.writeHead(400);res.end()};if(req.headers.host!==new URL(origin).host||req.headers.upgrade)return reject();
  if(req.method==='GET'&&['/upload','/disabled','/component.js'].includes(req.url)){res.writeHead(200,{'Content-Type':req.url==='/component.js'?'text/javascript':'text/html','Cache-Control':'no-store','Content-Security-Policy':"default-src 'none'; script-src 'self'; connect-src 'self'; img-src data:; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'"});res.end(req.url==='/component.js'?bundle:html);return}
  const m=/^\/auth\/private-upload-(context|reserve|receipt|content)(\?request_id=[a-f0-9-]{36})?$/.exec(req.url);if(!m||req.method!==(m[1]==='content'?'PUT':'POST')||!!m[2]!== (m[1]==='content'))return reject();
  const chunks=[];let size=0;const timer=setTimeout(()=>req.destroy(),5000);try{for await(const b of req){size+=b.length;if(size>8388608)throw Error('limit');chunks.push(b)}}finally{clearTimeout(timer)}
  const h=new Headers();for(const k of ['origin','sec-fetch-site','content-type','content-length','cookie','content-encoding','content-range'])if(typeof req.headers[k]==='string')h.set(k,req.headers[k]);
  const result=await relay.handle(new Request(ORIGIN+req.url,{method:req.method,headers:h,body:Buffer.concat(chunks)}),m[1]);res.writeHead(result.status,Object.fromEntries(result.headers));res.end(Buffer.from(await result.arrayBuffer()));
 }
 server=http.createServer((q,r)=>{const p=handle(q,r).catch(()=>{violations.push('handler-failure');if(!r.destroyed){r.writeHead(500);r.end()}});pending.add(p);void p.finally(()=>pending.delete(p))});server.on('upgrade',(_,s)=>{violations.push('upgrade');s.destroy()});server.requestTimeout=6000;server.headersTimeout=6000;
 await new Promise((resolve,reject)=>{server.once('error',reject);server.listen(0,'127.0.0.1',resolve)});origin='http://127.0.0.1:'+server.address().port;
 return {origin,logicalOrigin:ORIGIN,cookie:relay.cookie,bytes:storage.bytes,sha256:storage.sha256,component:storage.component,async evidence(){return {counts:storage.counts(),queries:storage.queries(),relay:relay.counts(),disk:await storage.inspect(),violations:[...violations,...relay.violations,...storage.violations]}},async close(){let failure;try{await new Promise((resolve,reject)=>{server.close(e=>e?reject(e):resolve());server.closeAllConnections()});await Promise.all([...pending]);}catch(e){failure=e}const cleanup=await storage.close();if(failure)throw failure;return {...cleanup,listener_closed:cleanup.listener_closed&&!server.listening,pending:cleanup.pending+pending.size}}};
 }catch(error){try{if(server?.listening)await new Promise((resolve,reject)=>{server.close(e=>e?reject(e):resolve());server.closeAllConnections()});}finally{await storage.close();}throw error;}
}
module.exports={buildHarness,startHarness};
