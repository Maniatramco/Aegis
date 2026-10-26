const {test}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),Module=require('node:module'),ts=require('typescript');
const React=require('react'),{renderToStaticMarkup}=require('react-dom/server');
const filename=path.resolve(__dirname,'../../ags_frontend/app/jobs-board.tsx'),mod=new Module(filename,module);mod.filename=filename;mod.paths=module.paths;
const tiles={SummaryTiles:({tiles})=>React.createElement('dl',null,tiles.map(t=>React.createElement('div',{key:t.label},`${t.label}:${t.value}`)))};
const original=mod.require.bind(mod);mod.require=id=>id==='./action-button'?require('./support/action-button.cjs').actionButton:id==='lucide-react'?new Proxy({},{get:()=>()=>null}):id==='./needs-attention'?{openAttention(){}}:id==='./summary-tiles'?tiles:original(id);
mod._compile(ts.transpileModule(fs.readFileSync(filename,'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022,jsx:ts.JsxEmit.ReactJSX}}).outputText,filename);
const {JobsBoard,jobGroup,jobSummary,jobsByPerson,jobSeconds,durationLabel,ago}=mod.exports;
const now=10000;
const jobs=[
 {id:'a',kind:'index',status:'failed',progress:35,error:'Interrupted',document_id:'d',created_at:now-600,updated_at:now-540,attempts:2,started_by:{id:'u2',label:'Priya Shah',self:false},dataset_id:'k'},
 {id:'b',kind:'extract',status:'running',progress:50,created_at:now-90,updated_at:now-10,started_by:{id:'me',label:'You',self:true}},
 {id:'c',kind:'index',status:'completed',progress:100,created_at:now-300,updated_at:now-180,started_by:{id:'me',label:'You',self:true}},
 {id:'e',kind:'index',status:'queued',progress:0,created_at:now-5,updated_at:now-5,started_by:{id:null,label:'Another user',self:false}},
];
test('jobs group into running, failed and completed tabs',()=>{
 assert.deepEqual(['queued','running','pending','failed','cancelled','completed'].map(status=>jobGroup({status})),['running','running','running','failed','failed','completed']);
});
test('monitoring summary counts live work and times finished jobs from the loaded records',()=>{
 assert.equal(jobSeconds(jobs[1],now),90);assert.equal(jobSeconds(jobs[2],now),120);
 assert.equal(durationLabel(45),'45s');assert.equal(durationLabel(192),'3m 12s');assert.equal(durationLabel(3840),'1h 4m');assert.equal(ago(30),'just now');assert.equal(ago(600),'10 min ago');
 assert.deepEqual(jobSummary(jobs,now).map(t=>[t.label,t.value,t.detail]),[['Running now',1,'1 queued'],['Failed',1,'need attention'],['Completed',1,'in the last 24 hours'],['Average time','2m 0s','per completed job']]);
});
test('activity by person puts you first and counts each person\'s work',()=>{
 const people=jobsByPerson(jobs);
 assert.deepEqual(people.map(p=>[p.label,p.running,p.failed,p.completed]),[['You',1,0,1],['Another user',1,0,0],['Priya Shah',0,1,0]]);
 assert.equal(jobsByPerson([{status:'completed'}])[0].label,'Unknown');
});
test('the job table shows who started each job, its dataset, duration and actions',()=>{
 const html=renderToStaticMarkup(React.createElement(JobsBoard,{jobs,documents:[{id:'d',name:'quarterly.txt'}],datasets:[{id:'k',name:'Finance'}],busy:false,formatDate:()=>'today',onRetry(){},onCancel(){},empty:null,now}));
 assert.match(html,/aria-label="Filter jobs"/);assert.match(html,/aria-label="Started by"/);assert.match(html,/aria-label="Activity by person"/);
 assert.match(html,/quarterly.txt/);assert.match(html,/Finance · Indexing|Finance/);assert.match(html,/attempt 2/);assert.match(html,/Interrupted/);
 assert.match(html,/Priya Shah/);assert.match(html,/>PS</);assert.match(html,/1m 30s<small> so far/);assert.match(html,/10 min ago/);
 assert.match(html,/Retry/);assert.match(html,/Cancel/);assert.match(html,/All<span>4<\/span>/);assert.match(html,/Failed<span>1<\/span>/);
});
