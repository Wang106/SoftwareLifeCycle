'use strict';
const http=require('node:http');
const {once}=require('node:events');
const endpoints=Object.freeze({dashboard:'/api/v1/dashboard/summary',changes:'/api/v1/change-catalog/requests',issues:'/api/v1/change-catalog/issues',projects:'/api/v1/organization-views/projects'});
function dashboardFixture(){return{active_changes:7,open_issues:5,high_open_issues:2,ready_releases:3,current_release:null,recent_activity:Array.from({length:40},(_,i)=>({event_no:`EVT-LOADING-${i}`,summary:`SYNTHETIC_LOADING_ACTIVITY_${i}`,entity_ref:'sample-only',occurred_at:'2026-01-01T00:00:00Z'}))};}
async function startLoadingFixture(){
 const requests=[],violations=[],pending=new Set();let hold=true,failed=false;
 function respond(res){if(res.destroyed)return;res.writeHead(failed?503:200,{'content-type':'application/json','cache-control':'no-store'});res.end(JSON.stringify(failed?{detail:'PRIVATE_FIXTURE_ERROR'}:dashboardFixture()));}
 const server=http.createServer((req,res)=>{
  const url=new URL(req.url,'http://127.0.0.1');const entry={url:req.url,path:url.pathname,method:req.method};requests.push(entry);
  if(req.method!=='GET'||!Object.values(endpoints).includes(url.pathname)||url.search||req.headers.authorization||req.headers.cookie){violations.push(entry);res.writeHead(400);res.end('rejected');return;}
  if(url.pathname===endpoints.dashboard){if(hold){pending.add(res);res.on('close',()=>pending.delete(res));}else respond(res);return;}
  const kind=url.pathname===endpoints.changes?'changes':url.pathname===endpoints.issues?'issues':'projects';
  res.writeHead(200,{'content-type':'application/json','cache-control':'no-store'});res.end(JSON.stringify({kind,total:0,limit:50,offset:0,next_offset:null,items:[],in_verification:0,ready_for_release:0}));
 });
 server.listen(0,'127.0.0.1');await once(server,'listening');
 return{apiOrigin:`http://127.0.0.1:${server.address().port}`,requests,violations,releaseDashboard(failure=false){hold=false;failed=failure;for(const res of pending)respond(res);pending.clear();},async close(){for(const res of pending)res.destroy();server.closeAllConnections();await new Promise((resolve,reject)=>server.close(e=>e?reject(e):resolve()));}};
}
module.exports={endpoints,dashboardFixture,startLoadingFixture};
