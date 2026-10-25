const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');const path=require('node:path');const Module=require('node:module');const ts=require('typescript');
const flush=()=>new Promise(resolve=>setImmediate(resolve));
async function screen(handler=async()=>[],initial=[]){
 let cursor=0,root;const hooks=[],effects=[],calls=[];let changes=0,chat='';
 const react={useState(initial){const i=cursor++;if(!(i in hooks))hooks[i]=typeof initial==='function'?initial():initial;return [hooks[i],value=>hooks[i]=typeof value==='function'?value(hooks[i]):value];},useRef(value){const i=cursor++;if(!(i in hooks))hooks[i]={current:value};return hooks[i];},useEffect(fn){effects.push(fn);}};
 const filename=path.resolve(__dirname,'../../ags_frontend/app/source-connections.tsx');const mod=new Module(filename,module);mod.filename=filename;mod.paths=module.paths;const base=mod.require.bind(mod);
 mod.require=id=>id==='react'?react:id==='lucide-react'||id==='./workflow-stepper'?new Proxy({},{get:()=>()=>null}):id.endsWith('.css')?{}:base(id);
 mod._compile(ts.transpileModule(fs.readFileSync(filename,'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022,jsx:ts.JsxEmit.ReactJSX}}).outputText,filename);
 const nodes=n=>!n||typeof n!=='object'?[]:Array.isArray(n)?n.flatMap(nodes):[n,...nodes(n.props?.children)];
 const props={api:async(...args)=>{calls.push(args);if(args[0]==='/source-connections'&&!args[1])return initial;return handler(...args);},datasets:[{id:'d',name:'Finance',active:true,embedding_model_id:'embed'}],documents:[],selectedDataset:'d',onDatasetChange:()=>{},onChanged:()=>changes++,onChat:id=>chat=id,onModels:()=>{}};
 const render=()=>{cursor=0;root=mod.exports.SourceConnections(props);};render();effects[0]();await flush();render();
 const button=label=>nodes(root).find(n=>n.type==='button'&&JSON.stringify(n.props.children).includes(label));
 const field=label=>nodes(root).find(n=>n.props?.['aria-label']===label);
 return {render,button,field,calls,props,get changes(){return changes;},get chat(){return chat;},all:()=>nodes(root),submit:()=>nodes(root).find(n=>n.type==='form').props.onSubmit({preventDefault(){}})};
}
test('provider forms clear previous credentials and select the destination dataset',async()=>{
 const s=await screen();s.button('New connection').props.onClick();s.render();
 assert.equal(s.field('Destination dataset').props.value,'d');
 s.field('AWS secret access key').props.onChange({target:{value:'private'}});s.render();
 s.button('Google Drive').props.onClick();s.render();
 assert.ok(s.field('Service-account JSON key'));assert.equal(s.field('AWS secret access key'),undefined);
 s.button('SharePoint').props.onClick();s.render();assert.ok(s.field('Application client secret'));assert.ok(!JSON.stringify(s.all()).includes('private'));
});
test('save publishes configuration without calling import and strips returned metadata',async()=>{
 const s=await screen(async(path,method,body)=>({id:'c',...body,credentials_configured:true}));
 s.button('New connection').props.onClick();s.render();s.field('Connection name').props.onChange({target:{value:'Finance S3'}});s.render();
 s.submit();await flush();s.render();
 const saved=s.calls.find(c=>c[1]==='POST');assert.equal(saved[0],'/source-connections');assert.equal(saved[2].dataset_id,'d');assert.equal(saved[2].provider,'s3');assert.ok(!s.calls.some(c=>c[0].includes('/import')));
 s.button('Edit').props.onClick();s.render();s.submit();await flush();
 const update=s.calls.find(c=>c[1]==='PUT');assert.equal(update[0],'/source-connections/c');assert.equal(update[2].id,undefined);assert.equal(update[2].credentials_configured,undefined);assert.deepEqual(update[2].credentials,{});
});
test('file selection requires explicit dataset publication; partial failure stays visible',async()=>{
 const c={id:'c',name:'Finance S3',provider:'s3',dataset_id:'d',enabled:true};
 const s=await screen(async(path,method)=>path.includes('/files')?{items:[{id:'a',name:'a.txt',folder:false,supported:true,selection:'scoped-capability'},{id:'b',name:'b.exe',folder:false,supported:false,selection:''}],next_cursor:''}:path.includes('/import')?{results:[{name:'a.txt',status:'failed',message:'Cloud access removed.'}],notice:'Copies follow dataset access.'}:[],[c]);
 s.button('Finance S3').props.onClick();s.render();s.button('Browse files').props.onClick();await flush();s.render();
 assert.equal(s.field('Import b.exe').props.disabled,true);s.field('Import a.txt').props.onChange({target:{checked:true}});s.render();
 assert.equal(s.button('Import selected files').props.disabled,true);
 const check=s.all().find(n=>n.type==='label'&&JSON.stringify(n.props.children).includes('Publish copies'));check.props.children[0].props.onChange({target:{checked:true}});s.render();
 assert.equal(s.button('Import selected files').props.disabled,false);s.button('Import selected files').props.onClick();await flush();s.render();
 const imported=s.calls.find(c=>c[0].includes('/import'));assert.deepEqual(imported[2],{selections:['scoped-capability'],publish_to_dataset:true,allow_external:false});
 assert.ok(JSON.stringify(s.all()).includes('Cloud access removed.'));assert.equal(s.button('Open Agent chat').props.disabled,true);assert.equal(s.changes,1);
});
