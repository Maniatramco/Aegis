const {test}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),Module=require('node:module'),ts=require('typescript');
const file=path.resolve(__dirname,'../../ags_frontend/app/agent-answer-workflow.tsx'),mod=new Module(file,module);mod.filename=file;mod.paths=module.paths;
const base=mod.require.bind(mod);mod.require=id=>id.endsWith('.css')?{}:id==='./workflow-stepper'?{WorkflowStepper:()=>null}:base(id);
mod._compile(ts.transpileModule(fs.readFileSync(file,'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022,jsx:ts.JsxEmit.ReactJSX}}).outputText,file);
const {phaseFor,groupWorkflowSteps}=mod.exports;

test('server steps map to the four answer phases, with workflows as their own phase',()=>{
 const cases={'Checking agent configuration':'understand','Checking workspace':'understand','Reading current workspace state':'understand','Understanding request':'understand','Choosing tools':'understand',
  'Chat Agent · Querying vector knowledge':'evidence','Hybrid search':'evidence','Reranking evidence':'evidence','Reading complete scoped catalog':'evidence','Searching unified Aegis knowledge':'evidence',
  'Chat Agent · Answering from knowledge':'answer','Generating response':'answer','Answering or routing question':'answer',
  'Validating answer':'check','Repairing answer citations':'check','Saving response':'check','Validating general answer':'check',
  'Re-extract Agent':'workflow','Onboard & Extract Agent':'workflow','Routing to Extract Agent':'workflow','Connecting to agent':'understand','Submitting request':'understand'};
 for(const [label,phase] of Object.entries(cases))assert.equal(phaseFor(label),phase,label);
});
test('ten answer steps collapse into four phases with the live step named in the running phase',()=>{
 const labels=['Checking agent configuration','Checking workspace','Reading current workspace state','Understanding request','Chat Agent · Querying vector knowledge','Hybrid search','Reranking evidence','Chat Agent · Answering from knowledge','Validating answer','Saving response'];
 const steps=labels.map((label,i)=>({id:String(i),label,status:i<6?'completed':i===6?'running':'pending',started_at:1000,duration_ms:i<6?500:undefined}));
 const phases=groupWorkflowSteps(steps,2500);
 assert.deepEqual(phases.map(p=>[p.label,p.status]),[['Understand request','completed'],['Find evidence','running'],['Write answer','pending'],['Check & save','pending']]);
 assert.equal(phases[0].detail,'4 steps · 2s');assert.equal(phases[1].detail,'Reranking evidence · 1s');
 steps[8].status='failed';assert.equal(groupWorkflowSteps(steps,2500)[3].status,'failed');
 assert.deepEqual(groupWorkflowSteps([],0),[]);
});
