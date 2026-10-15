const {actionButton,expandActions}=require('./support/action-button.cjs');
const {test}=require('node:test'),assert=require('node:assert/strict');
const fs=require('node:fs'),path=require('node:path'),Module=require('node:module'),ts=require('typescript');
function view({stale=true,approval={required:true},workflow}={}){
 let index=0;const hooks=[],calls=[],scopes=[];
 const react={useState(initial){const slot=index++;if(!(slot in hooks))hooks[slot]=typeof initial==='function'?initial():initial;return [hooks[slot],value=>{hooks[slot]=typeof value==='function'?value(hooks[slot]):value;}];},useRef(initial){const slot=index++;if(!(slot in hooks))hooks[slot]={current:initial};return hooks[slot];},useEffect(){}};
 const filename=path.resolve(__dirname,'../app/re-extract.tsx'),compiled=new Module(filename,module);compiled.paths=module.paths;
 const original=compiled.require.bind(compiled);compiled.require=id=>id==='./action-button'?actionButton:id==='react'?react:id==='lucide-react'?{FileSearch:()=>null,X:()=>null}:id==='./operation-progress'?{JobProgress:()=>null}:id==='./dataset-workspace'?{eligibleModels:d=>d.models}:id==='./agent-consent'?{useAgentConsent:()=>({popup:null,request:async scope=>{scopes.push(scope);return typeof approval==='function'?approval():approval;}})}:id==='./extraction-name'?(()=>{const helper=new Module(filename,module);helper.paths=module.paths;helper._compile(ts.transpileModule(fs.readFileSync(path.resolve(__dirname,'../app/extraction-name.ts'),'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText,filename);return helper.exports;})():original(id);
 compiled._compile(ts.transpileModule(fs.readFileSync(filename,'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022,jsx:ts.JsxEmit.ReactJSX}}).outputText,filename);
 const props={source:{id:'previous',version:3,dataset_id:'dataset',document_ids:['doc'],template_id:'prompt',name:'TermSheet'},documents:[{id:'doc',name:'TermSheet.pdf',status:'ready',requires_reindex:stale}],datasets:[{id:'dataset',models:[{id:'model',name:'Gemini Extraction'}],default_extraction_model_id:'model'}],templates:[{id:'prompt',dataset_id:'dataset',name:'Strict.json'}],extractions:[],jobs:[],api:async(...args)=>{calls.push(args);return workflow||{id:'new-workflow',calls:[{tool:'upload',status:'waiting',jobs:[{id:'index',status:'queued'}]},{tool:'reextract',status:'pending'}]};},onRefresh(){},onReview(){},onConfigure(){},onClose(){}};
 let root;const elements=n=>!n||typeof n!=='object'?[]:Array.isArray(n)?n.flatMap(elements):[n,...elements(n.props?.children)];
 const render=()=>{index=0;root=expandActions(compiled.exports.ReExtractionDialog(props));};
 const find=(key,value)=>elements(root).find(n=>n.props?.[key]===value);
 const button=()=>elements(root).find(n=>n.type==='button'&&n.props.className?.split(' ').includes('primary'));render();
 return {render,find,button,calls,scopes,props,elements:()=>elements(root)};
}
test('stale embeddings offer confirmed reindex and rerun with an actual editable timestamped name',async()=>{
 const v=view();assert.equal(v.button().props.disabled,false);assert.match(JSON.stringify(v.button().props.children),/Reindex and re-extract/);
 assert.match(v.find('aria-label','Re-extraction name').props.value,/^TermSheet_\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2}$/);
 v.find('aria-label','Re-extraction name').props.onChange({target:{value:'My custom test'}});v.render();await v.button().props.onClick();v.render();
 assert.deepEqual(v.scopes,[{dataset_id:'dataset',roles:['embedding','extraction']}]);
 assert.equal(v.calls.length,1);assert.equal(v.calls[0][0],'/extractions/previous/rerun');
 assert.equal(v.calls[0][2].display_name,'My custom test');assert.equal(v.calls[0][2].source_version,3);
 assert.equal(v.button(),undefined,'A completed index alone must not offer Review results');
});
test('cancelling consent creates no model or index jobs; approval cannot be submitted twice',async()=>{
 const cancelled=view({approval:null});await cancelled.button().props.onClick();assert.equal(cancelled.calls.length,0);
 let approve;const v=view({approval:()=>new Promise(resolve=>{approve=resolve;})});const pending=v.button().props.onClick();v.render();
 assert.equal(v.button().props.disabled,true);await v.button().props.onClick();assert.equal(v.scopes.length,1);assert.equal(v.calls.length,0);
 approve({required:true});await pending;assert.equal(v.calls.length,1);
});
test('unchanged embeddings use normal extraction, while processing files and empty names stay blocked',async()=>{
 const v=view({stale:false});const name=v.find('aria-label','Re-extraction name').props.value;v.render();assert.equal(v.find('aria-label','Re-extraction name').props.value,name);
 await v.button().props.onClick();assert.equal(v.calls[0][0],'/extractions');assert.equal(v.calls[0][2].display_name,name);
 const blocked=view();blocked.props.documents[0].status='processing';blocked.render();assert.equal(blocked.button().props.disabled,true);
 const empty=view();empty.find('aria-label','Re-extraction name').props.onChange({target:{value:''}});empty.render();assert.equal(empty.button().props.disabled,true);
});
test('failed rebuild keeps the failure visible; a completed rerun offers its new result',async()=>{
 const failed=view({workflow:{id:'workflow',calls:[{tool:'upload',status:'failed',error:'Embedding quota exceeded'}]}});await failed.button().props.onClick();failed.render();assert.match(JSON.stringify(failed.find('role','alert').props.children),/Embedding quota exceeded/);assert.equal(failed.button(),undefined);
 const done=view({workflow:{id:'workflow',calls:[{tool:'upload',status:'completed',jobs:[{id:'index',status:'completed'}]},{tool:'reextract',status:'completed',result:{extractions:[{extraction_id:'new-result',status:'completed'}]}}]}});await done.button().props.onClick();done.render();assert.equal(done.button().props['aria-label'],'Review results');
});
