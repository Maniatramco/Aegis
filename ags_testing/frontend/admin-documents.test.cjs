const {test}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),Module=require('node:module'),ts=require('typescript');
function view(failDelete=false){
 let index=0,root;const hooks=[],calls=[],changed=[];
 const react={useState(initial){const slot=index++;if(!(slot in hooks))hooks[slot]=initial;return [hooks[slot],value=>hooks[slot]=typeof value==='function'?value(hooks[slot]):value];},useRef(initial){const slot=index++;if(!(slot in hooks))hooks[slot]={current:initial};return hooks[slot];},useEffect(){},useCallback(fn){return fn;}};
 const filename=path.resolve(__dirname,'../../ags_frontend/app/admin-documents.tsx'),compiled=new Module(filename,module);compiled.filename=filename;compiled.paths=module.paths;const original=compiled.require.bind(compiled);
 compiled.require=id=>id==='react'?react:id.endsWith('.css')?{}:id==='lucide-react'||id==='./workflow-stepper'?new Proxy({},{get:()=>()=>null}):original(id);
 compiled._compile(ts.transpileModule(fs.readFileSync(filename,'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022,jsx:ts.JsxEmit.ReactJSX}}).outputText,filename);
 const doc={id:'document',name:'synthetic.txt',version:1,status:'ready',created_at:1,size:10,dataset_name:'Synthetic',storage:{status:'present',provider:'oci',bucket:'test'},extractions:[]};
 const catalog={items:[doc],datasets:[],total:1};hooks[0]=catalog;
 const props={api:async(...args)=>{calls.push(args);if(args[0].endsWith('/deletion-preview'))return {version:1,impact_token:'a'.repeat(64),affected:{extractions:2,conversations:1,workflows:0,jobs:3},note:'Permanent deletion',cleanup_stage:'planned'};if(args[1]==='DELETE'&&failDelete)throw Error('Cleanup paused at files. Retry deletion.');return catalog;},onChanged:()=>changed.push(true),onReview(){}};
 function elements(node){if(!node||typeof node!=='object')return [];if(Array.isArray(node))return node.flatMap(elements);return [node,...elements(node.props?.children)];}
 const render=()=>{index=0;root=compiled.exports.AdminDocuments(props);};const find=(key,value)=>elements(root).find(n=>n.props?.[key]===value);const button=text=>elements(root).find(n=>n.type==='button'&&n.props.children===text);
 render();return {render,find,button,calls,changed,async settle(){await new Promise(setImmediate);render();}};
}
test('permanent delete requires exact filename and submits the reviewed version and impact token',async()=>{
 const v=view();const deleteButton=v.find('className','btn danger');deleteButton.props.onClick();await v.settle();
 assert.equal(v.button('Delete permanently').props.disabled,true);
 const field=v.find('autoComplete','off');field.props.onChange({target:{value:'synthetic.txt'}});v.render();
 assert.equal(v.button('Delete permanently').props.disabled,false);v.button('Delete permanently').props.onClick();await v.settle();
 const request=v.calls.find(c=>c[1]==='DELETE');assert.deepEqual(request,['/admin/documents/document','DELETE',{confirmation:'synthetic.txt',expected_version:1,expected_impact:'a'.repeat(64)}]);assert.equal(v.changed.length,1);
});
test('partial deletion failure keeps the confirmation and error after refreshing the catalog',async()=>{
 const v=view(true);v.find('className','btn danger').props.onClick();await v.settle();
 v.find('autoComplete','off').props.onChange({target:{value:'synthetic.txt'}});v.render();v.button('Delete permanently').props.onClick();await v.settle();
 assert.equal(v.find('role','alert').props.children,'Cleanup paused at files. Retry deletion.');assert.ok(v.find('role','dialog'));assert.equal(v.changed.length,0);assert.equal(v.find('role','status'),undefined);
});
test('cancelling deletion makes no destructive request',async()=>{
 const v=view();v.find('className','btn danger').props.onClick();await v.settle();v.button('Cancel').props.onClick();v.render();
 assert.equal(v.calls.filter(c=>c[1]==='DELETE').length,0);assert.equal(v.find('role','dialog'),undefined);
});
