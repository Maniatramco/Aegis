const {test}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),Module=require('node:module'),ts=require('typescript');
const React=require('react'),{renderToStaticMarkup}=require('react-dom/server');
const file=path.resolve(__dirname,'../../ags_frontend/app/agent-activity.tsx'),mod=new Module(file,module);mod.filename=file;mod.paths=module.paths;const original=mod.require.bind(mod);
mod.require=id=>id.endsWith('.css')?{}:id==='lucide-react'?new Proxy({},{get:()=>()=>null}):id==='./agent-logo'?{AgentLogo:()=>React.createElement('img',{className:'aegis-agent-logo'})}:original(id);
mod._compile(ts.transpileModule(fs.readFileSync(file,'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022,jsx:ts.JsxEmit.ReactJSX}}).outputText,file);
const {taskForStep,planActivity,AgentActivity,AgentPresence}=mod.exports;
test('live server step labels map to what the agent is doing',()=>{
 const cases={'Hybrid search':'search','Chat Agent · Querying vector knowledge':'search','Reranking evidence':'rank','Chat Agent · Answering from knowledge':'write','Generating response':'write','Validating answer':'check','Repairing answer citations':'check','Re-extract Agent':'reextract','Onboard & Extract Agent':'onboard','Saving response':'save','Checking workspace':'think','Understanding request':'think'};
 for(const [label,task] of Object.entries(cases))assert.equal(taskForStep(label),task,label);
});
test('a running tool outranks the answer workflow, and idle plans show no activity',()=>{
 assert.equal(planActivity({calls:[{tool:'upload',status:'running',jobs:[{status:'processing'}]}]}),'index');
 assert.equal(planActivity({calls:[{tool:'upload',status:'waiting',jobs:[]}]}),'upload');
 assert.equal(planActivity({calls:[{tool:'extract',status:'running',publication_pending:true}]}),'publish');
 assert.equal(planActivity({calls:[{tool:'reextract',status:'running'}]}),'reextract');
 assert.equal(planActivity({calls:[]},{status:'running',steps:[{label:'Hybrid search',status:'completed'},{label:'Reranking evidence',status:'running'}]}),'rank');
 assert.equal(planActivity({calls:[],chat:{status:'streaming'}},{status:'running',steps:[]}),'write');
 assert.equal(planActivity({calls:[{tool:'extract',status:'completed'}],chat:{status:'completed'}},{status:'completed',steps:[{label:'Validating answer',status:'completed'}]}),null);
});
test('activity is announced by task name and idle presence is the plain logo',()=>{
 const html=renderToStaticMarkup(React.createElement(AgentActivity,{task:'extract'}));
 assert.match(html,/data-task="extract"/);assert.match(html,/aria-label="Aegis Agent · Extracting fields"/);assert.match(html,/agent-activity-track/);
 assert.doesNotMatch(renderToStaticMarkup(React.createElement(AgentActivity,{task:'search',compact:true})),/agent-activity-track/);
 assert.equal(renderToStaticMarkup(React.createElement(AgentPresence,{task:null})),'<img class="aegis-agent-logo"/>');
});
