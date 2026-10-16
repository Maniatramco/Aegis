const {test}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),Module=require('node:module'),ts=require('typescript');
const filename=path.resolve(__dirname,'../../ags_frontend/app/dataset-chat-status.tsx'),mod=new Module(filename,module);mod.filename=filename;mod.paths=module.paths;const original=mod.require.bind(mod);
mod.require=id=>id==='lucide-react'?new Proxy({},{get:()=>()=>null}):id==='./workflow-stepper'?{WorkflowStepper:()=>null}:id.endsWith('.css')?{}:original(id);
mod._compile(ts.transpileModule(fs.readFileSync(filename,'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022,jsx:ts.JsxEmit.ReactJSX}}).outputText,filename);
const {DatasetChatStatus}=mod.exports;
const text=node=>node==null?'':typeof node==='string'||typeof node==='number'?String(node):Array.isArray(node)?node.map(text).join(''):text(node.props?.children);
const all=node=>!node||typeof node!=='object'?[]:Array.isArray(node)?node.flatMap(all):[node,...all(node.props?.children)];
test('status starts collapsed and distinguishes checked sources from cited sources',()=>{
 const tree=DatasetChatStatus({message:{status:'completed',source_summary:{checked_count:3,cited_count:1,documents:1,saved_results:1,dataset_descriptions:1}}});
 assert.equal(tree.type,'details');assert.equal(tree.props.open,undefined);assert.match(text(tree),/3 sources checked · 1 cited/);assert.match(text(tree),/1 document · 1 saved result · 1 dataset description/);
});
test('live retrieval counts stay visible during generation without expanding workflow details',()=>{
 const tree=DatasetChatStatus({message:{status:'streaming',source_summary:{checked_count:2,documents:1,dataset_descriptions:1},answer_workflow:{status:'running',steps:[{id:'answer',label:'Generating grounded answer',status:'running'}]}}});
 assert.equal(tree.props.open,undefined);assert.match(text(tree),/Preparing answer2 sources checked/);assert.doesNotMatch(text(tree),/cited/);
 const stepper=all(tree).find(node=>typeof node.type==='function'&&node.props?.label==='Knowledge search details');assert.equal(stepper.props.steps[0].status,'running');
});
test('older answers and failed retrieval never invent checked-source counts',()=>{
 const older=DatasetChatStatus({message:{status:'completed',citations:[{index:1},{index:2}]}});assert.match(text(older),/Source counts were not recorded/);assert.doesNotMatch(text(older),/sources checked/);
 const failed=DatasetChatStatus({message:{status:'failed'}});assert.match(text(failed),/Needs attention/);assert.doesNotMatch(text(failed),/Answer ready|sources checked/);
});
