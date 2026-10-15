const {actionButton,expandActions}=require('./support/action-button.cjs');
const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');const path=require('node:path');const Module=require('node:module');const ts=require('typescript');

test('local-model re-extract waits for OCI consent, supports cancel and submits once after approval',async()=>{
 let index=0,receipt=null,approve;const hooks=[],calls=[],scopes=[];let refreshed=0;
 const react={useState(initial){const slot=index++;if(!(slot in hooks))hooks[slot]=typeof initial==='function'?initial():initial;return [hooks[slot],value=>{hooks[slot]=typeof value==='function'?value(hooks[slot]):value;}];},useRef(initial){const slot=index++;if(!(slot in hooks))hooks[slot]={current:initial};return hooks[slot];},useEffect(){}};
 const filename=path.resolve(__dirname,'../app/re-extract.tsx');const compiled=new Module(filename,module);compiled.paths=module.paths;
 const original=compiled.require.bind(compiled);
 compiled.require=id=>id==='./extraction-name'?(()=>{const helper=new Module(filename,module);helper.paths=module.paths;helper._compile(ts.transpileModule(fs.readFileSync(path.resolve(__dirname,'../app/extraction-name.ts'),'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText,filename);return helper.exports;})():id==='./action-button'?actionButton:id==='react'?react:id==='lucide-react'?{FileSearch:()=>null,X:()=>null}:id==='./operation-progress'?{JobProgress:()=>null}:id==='./dataset-workspace'?{eligibleModels:dataset=>dataset.models}:id==='./agent-consent'?{useAgentConsent:()=>({popup:null,request:async scope=>{scopes.push(scope);return receipt==='pending'?new Promise(resolve=>{approve=resolve;}):receipt;}})}:original(id);
 compiled._compile(ts.transpileModule(fs.readFileSync(filename,'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022,jsx:ts.JsxEmit.ReactJSX}}).outputText,filename);
 const props={source:{id:'previous',dataset_id:'dataset',document_ids:['doc'],template_id:'prompt',name:'Saved resume'},documents:[{id:'doc',name:'resume.pdf',status:'ready'}],datasets:[{id:'dataset',models:[{id:'model',name:'Qwen3 Extraction',provider:'ollama'}],default_extraction_model_id:'model'}],templates:[{id:'prompt',dataset_id:'dataset',name:'resume.json'}],extractions:[],jobs:[],api:async(...args)=>{calls.push(args);return {id:'new',job:{id:'job',status:'queued'}};},onRefresh(){refreshed++;},onReview(){},onConfigure(){},onClose(){}};
 let root;const render=()=>{index=0;root=expandActions(compiled.exports.ReExtractionDialog(props));};
 const elements=node=>!node||typeof node!=='object'?[]:Array.isArray(node)?node.flatMap(elements):[node,...elements(node.props?.children)];
 const start=()=>elements(root).find(node=>node.type==='button'&&node.props.className?.split(' ').includes('primary'));
 render();assert.equal(start().props.disabled,false);
 await start().props.onClick();render();
 assert.equal(calls.length,0,'Cancelling consent must not create an extraction');assert.equal(start().props.disabled,false);
 receipt='pending';const pending=start().props.onClick();render();assert.equal(start().props.disabled,true);assert.equal(calls.length,0);
 await start().props.onClick();assert.equal(scopes.length,2,'Repeated clicks must not open another approval');
 approve({dataset_id:'dataset',required:true,destinations:[{key:'oci-vectors'}]});await pending;render();
 assert.deepEqual(scopes[1],{dataset_id:'dataset',roles:['embedding','extraction']});
 assert.equal(calls.length,1);assert.equal(calls[0][0],'/extractions');assert.equal(calls[0][2].allow_external,true);
 assert.equal(calls[0][2].template_id,'prompt');assert.deepEqual(calls[0][2].document_ids,['doc']);assert.equal(refreshed,1);
 assert.ok(!elements(root).some(node=>node.props?.role==='alert'));
});
