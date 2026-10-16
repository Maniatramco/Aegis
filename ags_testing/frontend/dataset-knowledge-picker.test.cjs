const {test}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),Module=require('node:module'),ts=require('typescript');
const scopeFile=path.resolve(__dirname,'../../ags_frontend/app/dataset-knowledge-scope.ts'),scopeModule=new Module(scopeFile,module);scopeModule.filename=scopeFile;scopeModule.paths=module.paths;scopeModule._compile(ts.transpileModule(fs.readFileSync(scopeFile,'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText,scopeFile);
function mount(values={}){
 let cursor=0,root;const hooks=[],included=[],closed=[];
 const react={useState(initial){const slot=cursor++;if(!(slot in hooks))hooks[slot]=typeof initial==='function'?initial():initial;return [hooks[slot],value=>hooks[slot]=typeof value==='function'?value(hooks[slot]):value];},useRef:value=>({current:value}),useEffect(){}};
 const file=path.resolve(__dirname,'../../ags_frontend/app/dataset-knowledge-picker.tsx'),mod=new Module(file,module);mod.filename=file;mod.paths=module.paths;const original=mod.require.bind(mod);mod.require=id=>id==='./dataset-knowledge-scope'?scopeModule.exports:id==='react'?react:id==='lucide-react'?new Proxy({},{get:()=>()=>null}):original(id);
 mod._compile(ts.transpileModule(fs.readFileSync(file,'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022,jsx:ts.JsxEmit.ReactJSX}}).outputText,file);
 const props={datasets:[{id:'a',name:'Invoices'},{id:'b',name:'Policies'}],documents:[{id:'one',dataset_id:'a',name:'invoice.txt',status:'ready'},{id:'two',parent_id:'b',name:'policy.txt',status:'ready'},{id:'stale',dataset_id:'a',name:'old.txt',status:'ready',requires_reindex:true}],initial:{datasetIds:['a'],documentIds:null},onInclude:value=>included.push(value),onClose:()=>closed.push(true),...values};
 const all=node=>!node||typeof node!=='object'?[]:Array.isArray(node)?node.flatMap(all):[node,...all(node.props?.children)];
 const render=()=>{cursor=0;root=mod.exports.DatasetKnowledgePicker(props);};render();return {render,included,closed,get nodes(){return all(root);}};
}
const find=(v,label)=>v.nodes.find(n=>n.props?.['aria-label']===label),button=(v,label)=>v.nodes.find(n=>n.type==='button'&&n.props.children===label);
test('knowledge picker includes existing indexed files without uploading or changing datasets',()=>{
 const v=mount();assert.equal(find(v,'Include available file invoice.txt').props.checked,true);assert.equal(find(v,'Include available file old.txt'),undefined);
 find(v,'Include dataset Policies').props.onChange();v.render();button(v,'Include selected knowledge').props.onClick();assert.deepEqual(v.included,[{datasetIds:['a','b'],documentIds:['one','two']}]);
});
test('unavailable and unassigned files cannot be selected, and empty scope cannot be applied',()=>{
 const v=mount({datasets:[{id:'a',name:'Invoices'}]});assert.equal(find(v,'Include available file policy.txt'),undefined);
 find(v,'Include available file invoice.txt').props.onChange();v.render();assert.equal(button(v,'Include selected knowledge').props.disabled,true);
});
test('search preserves selections and cancelling makes no inclusion change',()=>{
 const v=mount();find(v,'Search available dataset knowledge').props.onChange({target:{value:'Policies'}});v.render();assert.equal(find(v,'Include available file invoice.txt'),undefined);button(v,'Cancel').props.onClick();assert.deepEqual(v.included,[]);assert.deepEqual(v.closed,[true]);
});
