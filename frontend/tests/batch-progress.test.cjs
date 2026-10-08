const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const Module=require('node:module');
const ts=require('typescript');
const React=require('react');
const {renderToStaticMarkup}=require('react-dom/server');
const cache=new Map();
function load(filename){
 if(cache.has(filename))return cache.get(filename).exports;
 const compiled=new Module(filename,module);compiled.filename=filename;compiled.paths=Module._nodeModulePaths(path.dirname(filename));cache.set(filename,compiled);
 compiled.require=function(spec){
  if(spec.endsWith('.css'))return {};
  if(spec.startsWith('.')){const base=path.resolve(path.dirname(filename),spec);const source=[base+'.tsx',base+'.ts'].find(file=>fs.existsSync(file));if(source)return load(source);}
  return Module.prototype.require.call(this,spec);
 };
 compiled._compile(ts.transpileModule(fs.readFileSync(filename,'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022,jsx:ts.JsxEmit.ReactJSX}}).outputText,filename);
 return compiled.exports;
}
const {OperationProgress}=load(path.resolve(__dirname,'../app/operation-progress.tsx'));
const items=Array.from({length:10},(_,i)=>({id:'row-'+i,name:'invoice-'+i+'.txt',status:'submitted',processing:true,document:{id:'doc-'+i,status:'processing'},job:{status:'running',workflow:{current:'extract',stages:{extract:{status:'running'}}}}}));
const jobs=items.map((item,i)=>({...item.job,id:'job-'+i,kind:'index',document_id:item.document.id}));
test('closing the upload panel gives ten documents one background workflow',()=>{
 const html=renderToStaticMarkup(React.createElement(OperationProgress,{requests:[],jobs,uploadItems:items}));
 assert.equal((html.match(/aria-label="Batch upload workflow"/g)||[]).length,1);
 assert.equal((html.match(/invoice-\d+\.txt/g)||[]).length,10);
 assert.equal((html.match(/class="job-progress"/g)||[]).length,0);
 assert.match(html,/stage-running/);
});
test('an open upload panel suppresses duplicate background workflows without suppressing extraction jobs',()=>{
 const hidden=renderToStaticMarkup(React.createElement(OperationProgress,{requests:[],jobs,uploadItems:items,uploadWorkflowVisible:true}));
 assert.equal(hidden,'');
 const html=renderToStaticMarkup(React.createElement(OperationProgress,{requests:[],jobs:[...jobs,{id:'extract-job',kind:'extract',status:'running',workflow:{stages:{generate:{status:'running'}}}}],uploadItems:items,uploadWorkflowVisible:true}));
 assert.equal((html.match(/aria-label="Batch upload workflow"/g)||[]).length,0);
 assert.equal((html.match(/class="job-progress"/g)||[]).length,1);
 assert.match(html,/Extraction/);
});
