const {test}=require('node:test');const assert=require('node:assert/strict');const fs=require('node:fs');const path=require('node:path');const Module=require('node:module');const ts=require('typescript');
const flush=()=>new Promise(resolve=>setImmediate(resolve));
async function screen(handler,component="StorageConfiguration"){
 let cursor=0,root;const hooks=[],effects=[],calls=[];let changed=0;
 const react={useState(initial){const i=cursor++;if(!(i in hooks))hooks[i]=initial;return [hooks[i],value=>hooks[i]=typeof value==='function'?value(hooks[i]):value];},useEffect(fn){effects.push(fn);}};
 const filename=path.resolve(__dirname,'../app/storage-configuration.tsx');const mod=new Module(filename,module);mod.filename=filename;mod.paths=module.paths;const base=mod.require.bind(mod);
 mod.require=id=>id==='react'?react:id==='lucide-react'||id==='./workflow-stepper'?new Proxy({},{get:()=>()=>null}):id.endsWith('.css')?{}:base(id);
 mod._compile(ts.transpileModule(fs.readFileSync(filename,'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022,jsx:ts.JsxEmit.ReactJSX}}).outputText,filename);
 const nodes=n=>!n||typeof n!=='object'?[]:Array.isArray(n)?n.flatMap(nodes):[n,...nodes(n.props?.children)];
 const props={api:async(...args)=>{calls.push(args);if(args[0]==='/storage'&&!args[1])return {destination:{storage_provider:'local',oci_storage_namespace:'ns',oci_storage_bucket:'bucket',oci_storage_region:'region'},local_root:'/data',credential_mount:'/run/oci'};if(args[0]==='/workspace/reset-preview')return {counts:{knowledge_base:1},active_jobs:0,index_collections:[]};return handler(...args);},onChanged:()=>changed++};
 const render=()=>{cursor=0;root=mod.exports[component](props);};render();effects[0]();await flush();render();
 return {render,calls,get changed(){return changed;},field:label=>nodes(root).find(n=>n.props?.['aria-label']===label),button:text=>nodes(root).find(n=>n.type==='button'&&nodes(n.props.children).length>=0&&JSON.stringify(n.props.children).includes(text)),all:()=>nodes(root)};
}
test('OCI connection test does not change active storage; save sends mounted file paths',async()=>{
 const s=await screen(async(path,method,body)=>path==='/storage/test'?{message:'Read verified'}:{destination:body,test:{message:'Saved'}});
 s.button('OCI Object Storage').props.onClick();s.render();
 s.button('Test connection').props.onClick();await flush();s.render();
 assert.equal(s.calls.filter(c=>c[1]==='PUT').length,0);
 s.button('Save storage configuration').props.onClick();await flush();s.render();
 const saved=s.calls.find(c=>c[1]==='PUT');assert.equal(saved[2].storage_provider,'oci');assert.equal(saved[2].oci_storage_key_file,'/run/oci/aegis_api_key.pem');assert.equal(s.changed,1);
});
test('fresh start is disabled until the exact confirmation phrase is supplied',async()=>{
 const s=await screen(async()=>({id:'archive'}));assert.equal(s.button('Archive and start fresh').props.disabled,true);
 s.field('Fresh start confirmation').props.onChange({target:{value:'START FRESH'}});s.render();assert.equal(s.button('Archive and start fresh').props.disabled,false);
 s.button('Archive and start fresh').props.onClick();await flush();s.render();assert.deepEqual(s.calls.find(c=>c[0]==='/workspace/reset')[2],{confirmation:'START FRESH'});assert.equal(s.changed,1);
});
test('failed OCI validation remains visible and does not report a saved destination',async()=>{
 const s=await screen(async()=>{throw Error('Bucket permission denied');});s.button('Save storage configuration').props.onClick();await flush();s.render();
 assert.equal(s.changed,0);assert.ok(s.all().some(n=>n.props?.role==='alert'&&n.props.children==='Bucket permission denied'));
});
test('database setup stays on Storage, masks passwords and activates only after schema verification',async()=>{
 const initial={active_provider:'local',local_database:'oracle',wallet_ready:true,form:{provider:'oci',name:'agsora',region:'ap-mumbai-1',username:'AEGIS',dsn:'agsora_low',auth_mode:'mtls',wallet_directory:'/run/aegis-db/wallet'}};
 const s=await screen(async(path,method)=>!method?initial:{ok:true,message:'Verified',tables_present:method==='POST'&&path.endsWith('/test')?0:13,tables_required:13,schema_ready:!path.endsWith('/test')},'DatabaseConfiguration');
 assert.equal(s.field('Database password').props.type,'password');assert.equal(s.field('Wallet password').props.type,'password');
 assert.equal(s.button('Create Aegis tables').props.disabled,true);assert.equal(s.button('Activate').props.disabled,true);
 s.button('Test database connection').props.onClick();await flush();s.render();assert.equal(s.changed,0);
 assert.equal(s.button('Create Aegis tables').props.disabled,false);assert.equal(s.button('Activate').props.disabled,true);
 s.button('Create Aegis tables').props.onClick();await flush();s.render();assert.equal(s.button('Activate').props.disabled,false);assert.equal(s.changed,0);
 s.button('Activate').props.onClick();await flush();s.render();assert.equal(s.changed,1);
});
test('database credentials failure never activates or reports success',async()=>{
 const s=await screen(async(path,method)=>!method?{active_provider:'local',form:{provider:'oci',auth_mode:'mtls'}}:Promise.reject(Error('Check database or wallet password')),'DatabaseConfiguration');
 s.button('Test database connection').props.onClick();await flush();s.render();assert.equal(s.changed,0);
 assert.ok(s.all().some(n=>n.props?.role==='alert'&&n.props.children==='Check database or wallet password'));
 assert.equal(s.button('Create Aegis tables').props.disabled,true);
});
