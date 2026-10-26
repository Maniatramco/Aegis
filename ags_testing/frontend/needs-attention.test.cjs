const {test}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),Module=require('node:module'),ts=require('typescript');
const React=require('react'),{renderToStaticMarkup}=require('react-dom/server');
const file=path.resolve(__dirname,'../../ags_frontend/app/needs-attention.tsx'),mod=new Module(file,module);mod.filename=file;mod.paths=module.paths;const original=mod.require.bind(mod);
mod.require=id=>id.endsWith('.css')?{}:id==='lucide-react'?new Proxy({},{get:()=>()=>null}):id==='react'?{...React,useEffect(){},useRef:()=>({current:null})}:original(id);
mod._compile(ts.transpileModule(fs.readFileSync(file,'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022,jsx:ts.JsxEmit.ReactJSX}}).outputText,file);
const {attentionItems,adviceFor,NeedsAttentionDialog}=mod.exports;
const datasets=[{id:'d1',name:'Quarterly intake'},{id:'d2',name:'Handbook'}];
const docs=[{id:'a',name:'a.pdf',dataset_id:'d1',status:'failed'},{id:'b',name:'b.pdf',dataset_id:'d2',status:'ready',requires_reindex:true},{id:'c',name:'c.pdf',dataset_id:'d2',status:'ready'}];
const jobs=[{id:'j1',document_id:'a',status:'failed',created_at:2,error:'Request timed out after 60s',workflow:{stages:{upload:{status:'completed'},index:{status:'failed'},ready:{status:'blocked'}}},attempts:2},{id:'j0',document_id:'a',status:'completed',created_at:1},{id:'j2',target_id:'x',kind:'extract',status:'cancelled',created_at:3}];
test('failed and out-of-date files, plus orphan failed jobs, need attention with their failing stage',()=>{
 const items=attentionItems(docs,jobs,datasets);
 assert.deepEqual(items.map(i=>[i.id,i.kind,i.stage]),[['a','failed','Index'],['b','reindex','Index'],['j2','failed','Extraction']]);
 assert.equal(items[0].job.id,'j1');assert.equal(items[0].dataset,'Quarterly intake');assert.equal(items[1].job,undefined);
 assert.deepEqual(attentionItems(docs,jobs,datasets,{datasetId:'d2'}).map(i=>i.id),['b']);
 assert.deepEqual(attentionItems(docs,jobs,datasets,{jobId:'j1'}).map(i=>i.id),['a']);
});
test('failure messages map to the screen that fixes them',()=>{
 assert.equal(adviceFor('Request timed out','failed').view,'Model Registration');
 assert.equal(adviceFor('Context limit exceeded','failed').view,'Model Registration');
 assert.equal(adviceFor('401 Unauthorized','failed').view,'Model Registration');
 assert.equal(adviceFor('No embedding model mapped','failed').view,'Model Mapping');
 assert.equal(adviceFor('anything','reindex').view,'Files & processing');
 assert.equal(adviceFor('indexing was interrupted','failed').view,undefined);
});
test('the pop-up offers retry for failed jobs and tells non-administrators who can fix the rest',()=>{
 const items=attentionItems(docs,jobs,datasets);
 const user=renderToStaticMarkup(React.createElement(NeedsAttentionDialog,{items,isAdmin:false,busy:false,onClose(){},onRetry(){},onNavigate(){}}));
 assert.match(user,/role="dialog" aria-modal="true"/);assert.match(user,/Retry/);assert.match(user,/needs an administrator/);assert.doesNotMatch(user,/Open Model Registration/);
 const admin=renderToStaticMarkup(React.createElement(NeedsAttentionDialog,{items,isAdmin:true,busy:false,onClose(){},onRetry(){},onNavigate(){}}));
 assert.match(admin,/Open Model Registration/);assert.match(admin,/Request timed out after 60s/);assert.match(admin,/data-status="failed"/);
 assert.match(renderToStaticMarkup(React.createElement(NeedsAttentionDialog,{items:[],isAdmin:true,busy:false,onClose(){},onRetry(){},onNavigate(){}})),/Nothing needs attention right now/);
});
