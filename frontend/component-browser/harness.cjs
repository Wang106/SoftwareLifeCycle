'use strict';
// Never start Next or connect to an API/provider. All generated artifacts live in
// an owned OS temporary directory; the server can serve only four fixed paths.
const fs=require('node:fs');
const os=require('node:os');
const path=require('node:path');
const http=require('node:http');
const {execFileSync}=require('node:child_process');
const frontend=path.resolve(__dirname,'..');
const PAGE_PATHS=Object.freeze(['/component/approval','/component/readonly','/component/disabled']);
const SCRIPT_PATH='/component.js';
const API_PATHS=Object.freeze(['/auth/authorization-approval-context','/auth/authorization-approval','/auth/authorization-approval-receipt']);
const HTML='<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><link rel="icon" href="data:,"><title>Synthetic component fixture</title></head><body><main id="component-root"></main><script defer src="/component.js"></script></body></html>';

async function buildHarness(){
  const directory=fs.mkdtempSync(path.join(os.tmpdir(),'slc-b2-component-'));
  const dispose=()=>fs.rmSync(directory,{recursive:true,force:true});
  try{
    const compiled=path.join(directory,'compiled'),bundlePath=path.join(directory,'bundle','component.js');
    // Use the already locked TypeScript and Next webpack, not new dependencies,
    // JSX/hook mocks, production output directories, or an authentication bypass.
    execFileSync(process.execPath,[require.resolve('typescript/bin/tsc'),
      'component-browser/entry.tsx','--target','ES2021','--module','commonjs',
      '--jsx','react-jsx','--esModuleInterop','--resolveJsonModule','--strict',
      '--skipLibCheck','--outDir',compiled],{cwd:frontend,stdio:'pipe'});
    const bundledWebpack=require('next/dist/compiled/webpack/webpack');
    const webpack=bundledWebpack.webpack;
    const stats=await new Promise((resolve,reject)=>{
      const compiler=webpack({mode:'production',target:'web',devtool:false,
        entry:path.join(compiled,'component-browser','entry.js'),
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
    for(const required of ['authorization-approval-workbench.js','authorization-approval-transport.js','localized.js','next/dist/client/link.js','react-dom']){
      if(!names.some(name=>name.replaceAll('\\','/').includes(required)))throw Error(`Missing real component dependency: ${required}`);
    }
    return {directory,bundlePath,modules:names,dispose};
  }catch(error){dispose();throw error;}
}

async function startHarness({bundlePath,port=0}={}){
  if(!Number.isInteger(port)||port<0||port>65535)throw Error('Invalid loopback port');
  if(typeof bundlePath!=='string')throw Error('A built bundle is required');
  const bundle=fs.readFileSync(bundlePath),violations=[];
  let origin;
  const server=http.createServer((request,response)=>{
    // Never record request bodies, cookies, tokens, query strings, or raw paths.
    const reject=(reason,status=400)=>{
      violations.push(reason);response.writeHead(status,{'Content-Type':'text/plain','Cache-Control':'no-store'});response.end('Fixture request rejected');
    };
    if(request.headers.host!==new URL(origin).host)return reject('unexpected-host');
    if(request.method!=='GET')return reject('unexpected-method',405);
    if(request.headers.upgrade)return reject('unexpected-upgrade');
    if(!PAGE_PATHS.includes(request.url)&&request.url!==SCRIPT_PATH)return reject('unexpected-path',404);
    response.writeHead(200,{'Content-Type':request.url===SCRIPT_PATH?'text/javascript; charset=utf-8':'text/html; charset=utf-8',
      'Cache-Control':'no-store','X-Content-Type-Options':'nosniff','Referrer-Policy':'no-referrer',
      'Content-Security-Policy':"default-src 'none'; script-src 'self'; connect-src 'self'; img-src data:; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'"});
    response.end(request.url===SCRIPT_PATH?bundle:HTML);
  });
  server.on('upgrade',(_request,socket)=>{violations.push('unexpected-upgrade');socket.destroy();});
  await new Promise((resolve,reject)=>{server.once('error',reject);server.listen(port,'127.0.0.1',resolve);});
  origin=`http://127.0.0.1:${server.address().port}`;
  return {origin,violations,close:()=>new Promise((resolve,reject)=>{server.close(error=>error?reject(error):resolve());server.closeAllConnections();})};
}
module.exports={buildHarness,startHarness,PAGE_PATHS,SCRIPT_PATH,API_PATHS};
