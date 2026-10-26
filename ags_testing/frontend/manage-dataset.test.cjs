const {test}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),Module=require('node:module'),ts=require('typescript');
const React=require('react'),{renderToStaticMarkup}=require('react-dom/server');
const file=path.resolve(__dirname,'../../ags_frontend/app/manage-dataset.tsx'),mod=new Module(file,module);mod.filename=file;mod.paths=module.paths;const original=mod.require.bind(mod);
mod.require=id=>id.endsWith('.css')?{}:id==='lucide-react'?new Proxy({},{get:()=>()=>null}):id==='./needs-attention'?{openAttention(){}}:id==='./dataset-workspace'?{DatasetMappings:()=>React.createElement('div',{className:'mappings-stub'})}:id==='react'?{...React,useEffect(){}}:original(id);
mod._compile(ts.transpileModule(fs.readFileSync(file,'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022,jsx:ts.JsxEmit.ReactJSX}}).outputText,file);
const {ManageDataset,TABS}=mod.exports;
const dataset={id:'k',name:'Contracts',description:'Signed agreements',active:true};
const props=extra=>({dataset,models:[],documents:[{id:'a',name:'a.pdf',dataset_id:'k',status:'ready'},{id:'b',name:'b.pdf',dataset_id:'k',status:'failed'},{id:'c',name:'other.pdf',dataset_id:'x',status:'ready'}],templates:[{id:'t',name:'Key terms',dataset_id:'k',version:2,schema:{properties:{party:{},fee:{}}}},{id:'u',name:'Elsewhere',dataset_id:'x'}],isAdmin:true,api:async()=>({}),reload(){},notify(){},onNavigate(){},onClose(){},...extra});
const html=extra=>renderToStaticMarkup(React.createElement(ManageDataset,props(extra)));
test('the four onboarded things are tabs, with a count of documents that need attention',()=>{
 assert.deepEqual(TABS.map(([,label])=>label),['Details','Models','Documents','Prompts']);
 const page=html();assert.match(page,/role="dialog" aria-modal="true"/);assert.match(page,/2 documents · 1 prompt/);assert.match(page,/aria-label="1 need attention"/);
 assert.match(page,/value="Contracts"/);assert.match(page,/Signed agreements/);assert.match(page,/Save changes/);
});
test('documents and prompts list only this dataset, with ways to add and fix them',()=>{
 const docs=html({tab:'documents'});assert.match(docs,/a\.pdf/);assert.doesNotMatch(docs,/other\.pdf/);assert.match(docs,/Upload in Aegis Agent/);assert.match(docs,/Add from cloud storage/);assert.match(docs,/Review 1 that need attention/);assert.match(docs,/Reindex or delete files/);
 const prompts=html({tab:'prompts'});assert.match(prompts,/Key terms/);assert.match(prompts,/Version 2/);assert.match(prompts,/2 fields/);assert.doesNotMatch(prompts,/Elsewhere/);
 assert.match(html({tab:'models'}),/mappings-stub/);
});
test('non-administrators see details read-only and cannot change models',()=>{
 const page=html({isAdmin:false});assert.match(page,/Only administrators can change dataset details/);assert.doesNotMatch(page,/Save changes/);assert.match(page,/disabled=""/);
 assert.match(html({isAdmin:false,tab:'models'}),/Only administrators can change model mappings/);assert.doesNotMatch(html({isAdmin:false,tab:'documents'}),/Reindex or delete files/);
});
