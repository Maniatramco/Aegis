const {test}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),Module=require('node:module'),ts=require('typescript');
const React=require('react'),{renderToStaticMarkup}=require('react-dom/server');
const filename=path.resolve(__dirname,'../../ags_frontend/app/jobs-board.tsx'),mod=new Module(filename,module);mod.filename=filename;mod.paths=module.paths;
const original=mod.require.bind(mod);mod.require=id=>id==='./action-button'?require('./support/action-button.cjs').actionButton:id==='lucide-react'?new Proxy({},{get:()=>()=>null}):id==='./needs-attention'?{openAttention(){}}:original(id);
mod._compile(ts.transpileModule(fs.readFileSync(filename,'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022,jsx:ts.JsxEmit.ReactJSX}}).outputText,filename);
const {JobsBoard,jobGroup}=mod.exports;

test('jobs group into running, failed and completed tabs',()=>{
 assert.deepEqual(['queued','running','pending','failed','cancelled','completed'].map(status=>jobGroup({status})),['running','running','running','failed','failed','completed']);
});
test('job cards keep retry for failures and cancel for active work, with tab counts',()=>{
 const jobs=[{id:'a',kind:'index',status:'failed',progress:35,error:'Interrupted',document_id:'d'},{id:'b',kind:'extract',status:'running',progress:50},{id:'c',kind:'index',status:'completed',progress:100}];
 const html=renderToStaticMarkup(React.createElement(JobsBoard,{jobs,documents:[{id:'d',name:'quarterly.txt'}],busy:false,formatDate:()=>'today',onRetry(){},onCancel(){},empty:null}));
 assert.match(html,/aria-label="Filter jobs"/);assert.match(html,/quarterly.txt/);assert.match(html,/Interrupted/);
 assert.match(html,/Retry/);assert.match(html,/Cancel/);assert.match(html,/All<span>3<\/span>/);assert.match(html,/Failed<span>1<\/span>/);
});
