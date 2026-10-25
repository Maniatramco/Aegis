const {test}=require('node:test');const assert=require('node:assert/strict');
const fs=require('node:fs');const path=require('node:path');const Module=require('node:module');const ts=require('typescript');
const React=require('react');const {renderToStaticMarkup}=require('react-dom/server');
const cache=new Map();
function load(filename){if(cache.has(filename))return cache.get(filename).exports;const mod=new Module(filename,module);mod.filename=filename;mod.paths=Module._nodeModulePaths(path.dirname(filename));cache.set(filename,mod);const base=mod.require.bind(mod);mod.require=id=>{if(id.endsWith('.css'))return {};if(id.startsWith('.')){const stem=path.resolve(path.dirname(filename),id);const file=[stem+'.tsx',stem+'.ts',stem].find(value=>fs.existsSync(value)&&fs.statSync(value).isFile());if(file&&/\.tsx?$/.test(file))return load(file);}return base(id);};mod._compile(ts.transpileModule(fs.readFileSync(filename,'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022,jsx:ts.JsxEmit.ReactJSX,esModuleInterop:true}}).outputText,filename);return mod.exports;}
const source=name=>path.resolve(__dirname,'../../ags_frontend/app/'+name);
const {datasetMilestones}=load(source('dataset-readiness.ts'));
const {jobPresentation,JobsActivity}=load(source('jobs-activity.tsx'));
const {WorkflowStepper}=load(source('workflow-stepper.tsx'));
const {documentJourneySteps,currentUploadStep}=load(source('batch-workflow.ts'));

test('readiness separates current indexes, saved extraction and reviewed results without double counting runs',()=>{
 const docs=[{id:'a',dataset_id:'one',status:'ready'},{id:'b',dataset_id:'one',status:'ready',requires_reindex:true},{id:'c',dataset_id:'two',status:'failed'}];
 const results=[{status:'ready',document_ids:['a'],review_status:'unreviewed'},{status:'ready',document_ids:['a'],review_status:'reviewed'},{status:'failed',document_ids:['b'],review_status:'reviewed'},{status:'ready',document_ids:['c'],review_status:'reviewed'}];
 assert.deepEqual(datasetMilestones('one',docs,results),{added:2,indexed:1,extracted:1,reviewed:1,attention:1});
 assert.equal(datasetMilestones('two',docs,results).indexed,0);
 assert.equal(datasetMilestones(undefined,docs,results).extracted,2);
});
test('jobs resolve real target_id and completed stages, and preserve unknown progress',()=>{
 const stages={read:{status:'completed'},index:{status:'running'},ready:{status:'blocked'}};
 const info=jobPresentation({kind:'index',target_id:'doc',progress:99,workflow:{stages}},[{id:'doc',name:'sample.txt'}]);
 assert.equal(info.name,'sample.txt');assert.equal(info.progress,33);assert.equal(info.progressLabel,'1 of 3 stages completed');
 assert.equal(jobPresentation({kind:'index',status:'queued'},[]).progress,undefined);
 assert.equal(jobPresentation({kind:'extract',target_id:'result'},[],[{id:'result',name:'Renewal review'}]).name,'Renewal review');
});
test('job actions are explicit, contextual and limited to actual retry/cancel states',()=>{
 let actions=0;
 const html=renderToStaticMarkup(React.createElement(JobsActivity,{jobs:[{id:'failed',kind:'index',target_id:'doc',status:'failed',error:'Synthetic interruption'},{id:'waiting',kind:'index',target_id:'doc',status:'queued'},{id:'done',kind:'index',target_id:'doc',status:'completed'}],documents:[{id:'doc',name:'sample.txt'}],busy:false,onRetry:()=>actions++,onCancel:()=>actions++}));
 assert.equal(actions,0);assert.match(html,/Retry index document for sample.txt/);assert.match(html,/Cancel index document for sample.txt/);assert.match(html,/Synthetic interruption/);assert.match(html,/Progress details unavailable/);assert.match(html,/role="group" aria-label="Filter jobs"/);
});
test('shared stepper distinguishes cancelled, skipped and unknown stages without fabricating active work',()=>{
 const html=renderToStaticMarkup(React.createElement(WorkflowStepper,{compact:true,steps:[{id:'a',label:'Retrieve',status:'not_required'},{id:'b',label:'Generate',status:'cancelled'},{id:'c',label:'Validate',status:'unknown'}]}));
 assert.match(html,/stage-skipped/);assert.match(html,/Not used/);assert.match(html,/stage-cancelled/);assert.match(html,/Stopped/);assert.match(html,/Status unavailable/);assert.doesNotMatch(html,/data-active|connector-flowing|aria-current="step"/);
 const active=renderToStaticMarkup(React.createElement(WorkflowStepper,{steps:[{id:'a',label:'Read',status:'completed'},{id:'b',label:'Index',status:'running'}]}));assert.match(active,/data-active="true"/);assert.match(active,/connector-flowing/);
});

test('cancelled index jobs stop their formerly running stage without claiming an answer ran',()=>{
 const item={id:'cancelled',name:'sample.txt',status:'submitted',failed:true,document:{status:'processing'},job:{status:'cancelled',workflow:{current:'index',stages:{extract:{status:'completed'},index:{status:'running'}}}}};
 const steps=documentJourneySteps([item]);assert.equal(steps[1].status,'cancelled');assert.equal(steps[2].label,'Ready to ask');assert.equal(currentUploadStep(item),'Processing cancelled');
 const html=renderToStaticMarkup(React.createElement(WorkflowStepper,{steps}));assert.doesNotMatch(html,/data-active|aria-current="step"/);
});
