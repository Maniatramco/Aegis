const {test}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),Module=require('node:module'),ts=require('typescript');
const filename=path.resolve(__dirname,'../../ags_frontend/app/add-knowledge.tsx'),mod=new Module(filename,module);mod.filename=filename;mod.paths=module.paths;
const original=mod.require.bind(mod);mod.require=id=>id.endsWith('.css')?{}:id==='lucide-react'?new Proxy({},{get:()=>()=>null}):original(id);
mod._compile(ts.transpileModule(fs.readFileSync(filename,'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022,jsx:ts.JsxEmit.ReactJSX}}).outputText,filename);
const {STORAGE_PROVIDERS,blankConnection,connectionPayload,vectorizeState,MAX_SELECTION}=mod.exports;

test('all five storage providers are offered with read-only sign-in guidance',()=>{
 assert.deepEqual(STORAGE_PROVIDERS.map(p=>p.id),['s3','azure_blob','oci_object','sharepoint','google_drive']);
 assert.match(STORAGE_PROVIDERS.find(p=>p.id==='azure_blob').auth,/read and list only/);assert.equal(MAX_SELECTION,20);
});

test('new connections default to the provider region and never send saved metadata back',()=>{
 assert.equal(blankConnection('oci_object','d').region,'ap-mumbai-1');assert.equal(blankConnection('s3','d').region,'ap-south-1');assert.equal(blankConnection('azure_blob','d').region,'');
 const body=connectionPayload({...blankConnection('s3','d'),id:'c',version:2,updated_at:1,credentials_configured:true,secret_ref:'secret',owner:'bob'});
 for(const key of ['id','version','updated_at','credentials_configured','secret_ref','owner'])assert.equal(key in body,false);
 assert.equal(body.provider,'s3');assert.equal(body.dataset_id,'d');
});

test('vectorized copies are ready to ask only after indexing succeeds and chat knowledge is published',()=>{
 const docs=[{id:'a',status:'processing'},{id:'b',status:'ready'},{id:'c',status:'ready',requires_reindex:true},{id:'d',status:'failed'}];
 assert.equal(vectorizeState({status:'imported',document_id:'a'},docs).state,'running');
 assert.deepEqual(vectorizeState({status:'imported',document_id:'b'},docs),{state:'publishing',label:'Indexed · publishing to chat…'});
 assert.deepEqual(vectorizeState({status:'imported',document_id:'b'},docs,['b']),{state:'ready',label:'Ready to ask'});
 assert.equal(vectorizeState({status:'already_imported',document_id:'b'},docs,['b']).label,'Already indexed · ready to ask');
 assert.equal(vectorizeState({status:'imported',document_id:'c'},docs).state,'running');
 assert.equal(vectorizeState({status:'imported',document_id:'d'},docs).state,'failed');
 assert.equal(vectorizeState({status:'imported',document_id:'missing'},docs).state,'running');
 assert.deepEqual(vectorizeState({status:'failed',message:'Too large'},docs),{state:'failed',label:'Too large'});
});
