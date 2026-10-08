const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const Module=require('node:module');
const ts=require('typescript');
const file=path.resolve(__dirname,'../app/session-request.ts');
const compiled=new Module(file,module);
compiled._compile(ts.transpileModule(fs.readFileSync(file,'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText,file);
const {fetchWithSessionCsrf}=compiled.exports;
const json=(value,status=200)=>new Response(JSON.stringify(value),{status,headers:{'Content-Type':'application/json'}});
const stale=()=>json({detail:'Invalid CSRF token'},403);
const session={userId:'owner',csrf:'old'};

for(const multipart of [false,true])test(`recovers the same session and replays ${multipart?'multipart':'JSON'} once`,async()=>{
 const body=multipart?new FormData():JSON.stringify({confirmed:true});if(multipart)body.append('files',new Blob(['test']),'test.txt');
 const requests=[],tokens=[];const abort=new AbortController();
 const transport=async(url,init)=>{requests.push({url,init});return requests.length===1?stale():requests.length===2?json({user:{id:'owner'},csrf_token:'fresh'}):json({id:'created'});};
 const response=await fetchWithSessionCsrf('/api/agent-v2/plans',{method:'POST',body,headers:{'X-CSRF-Token':'old'},credentials:'include',signal:abort.signal},session,token=>tokens.push(token),transport);
 assert.equal(response.status,200);assert.equal(requests.length,3);assert.equal(requests[1].url,'/api/auth/me');assert.equal(requests[2].init.body,body);assert.equal(requests[2].init.signal,abort.signal);assert.equal(requests[2].init.headers.get('X-CSRF-Token'),'fresh');assert.deepEqual(tokens,['fresh']);
});
test('does not replay a second CSRF rejection',async()=>{
 let count=0;const response=await fetchWithSessionCsrf('/api/action',{method:'POST'},session,()=>{},async()=>++count===2?json({user:{id:'owner'},csrf_token:'fresh'}):stale());
 assert.equal(response.status,403);assert.equal(count,3);
});
test('does not replay policy rejections, reads, success, or uncertain failures',async()=>{
 for(const [method,status,detail] of [['POST',403,'External consent required'],['GET',403,'Invalid CSRF token'],['POST',200,'done'],['POST',500,'Invalid CSRF token']]){
  let count=0;const response=await fetchWithSessionCsrf('/api/action',{method},session,()=>assert.fail('must not refresh'),async()=>{count++;return json({detail},status);});assert.equal(response.status,status);assert.equal(count,1);
 }
 let count=0;await assert.rejects(fetchWithSessionCsrf('/api/action',{method:'POST'},session,()=>{},async()=>{count++;throw new Error('network interrupted');}),/network interrupted/);assert.equal(count,1);
});
test('never replays an action under a different account',async()=>{
 let count=0;await assert.rejects(fetchWithSessionCsrf('/api/action',{method:'POST'},session,()=>assert.fail('must not update'),async()=>++count===1?stale():json({user:{id:'other'},csrf_token:'fresh'})),/account changed/);assert.equal(count,2);
});
test('expired sessions stop recovery without replay',async()=>{
 let count=0;await assert.rejects(fetchWithSessionCsrf('/api/action',{method:'POST'},session,()=>assert.fail('must not update'),async()=>++count===1?stale():json({detail:'Session expired'},401)),/session expired/);assert.equal(count,2);
});
