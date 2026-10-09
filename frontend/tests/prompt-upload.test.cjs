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
const {readPromptUpload}=load(path.resolve(__dirname,'../app/prompt-upload.ts'));
const {PromptUploadPreview}=load(path.resolve(__dirname,'../app/prompt-upload-preview.tsx'));
const schema={type:'object',properties:{total:{type:'number'}},required:['total'],additionalProperties:false};
const file=(body,name='invoice.json',size=Buffer.byteLength(body))=>({name,size,text:async()=>body});
test('prompt upload accepts raw schema or named wrapper and preserves the reviewed JSON',async()=>{
 const raw=await readPromptUpload(file(JSON.stringify(schema)));
 assert.deepEqual(raw.schema,schema);assert.equal(raw.name,'invoice');
 const wrapped=await readPromptUpload(file('\uFEFF'+JSON.stringify({name:'  Invoice totals  ',schema})));
 assert.equal(wrapped.name,'Invoice totals');assert.deepEqual(wrapped.schema,schema);
 assert.deepEqual(JSON.parse(wrapped.preview),{name:'  Invoice totals  ',schema});
});
test('malformed, non-object, wrong-extension and excessive prompt uploads fail before preview',async()=>{
 for(const input of [file('{bad'),file('[]'),file('null'),file('{"schema":[]}'),file('{}','notes.txt'),file('{}','large.json',1048577),file('', 'empty.json'),file('{"name":" ","schema":{}}')]){
  await assert.rejects(()=>readPromptUpload(input));
 }
});
test('review dialog shows complete escaped JSON and requires an explicit confirmation',()=>{
 const preview=renderToStaticMarkup(React.createElement(PromptUploadPreview,{prompt:{fileName:'invoice.json',name:'Invoice',schema,preview:JSON.stringify({...schema,description:'<script>alert(1)</script>'},null,2)},datasetName:'QA dataset',onConfirm:()=>{},onCancel:()=>{}}));
 assert.match(preview,/Review uploaded prompt/);assert.match(preview,/Uploaded prompt JSON/);
 assert.match(preview,/Confirm prompt/);assert.match(preview,/Cancel/);assert.match(preview,/QA dataset/);
 assert.match(preview,/&lt;script&gt;/);assert.doesNotMatch(preview,/<script>/);
 assert.match(preview,/Use Send to save it/);
});

const {filterPromptTemplates,promptTemplateDownload}=load(path.resolve(__dirname,'../app/prompt-template-data.ts'));
const {PromptTemplates}=load(path.resolve(__dirname,'../app/prompt-templates.tsx'));
test('dataset filtering keeps scoped prompts separate and legacy prompts accessible',()=>{
 const prompts=[{id:'a',name:'Invoice',dataset_id:'one'},{id:'b',name:'Invoice two',dataset_id:'two'},{id:'c',name:'Shared invoice',dataset_id:null}];
 assert.deepEqual(filterPromptTemplates(prompts,'one',' invoice ').map(t=>t.id),['a']);
 assert.deepEqual(filterPromptTemplates(prompts,'two','').map(t=>t.id),['b']);
 assert.deepEqual(filterPromptTemplates(prompts,'shared','').map(t=>t.id),['c']);
 assert.equal(filterPromptTemplates(prompts,'all','INVOICE').length,3);
 assert.equal(filterPromptTemplates(prompts,'one','missing').length,0);
});
test('download round trips complete nested schema through Upload Prompt without binding destination dataset',async()=>{
 const nested={...schema,description:'Find amounts',properties:{group:{type:'object',properties:{amount:{type:['number','null'],description:'Total',minimum:0}},required:['amount'],additionalProperties:false}},required:['group']};
 const exported=promptTemplateDownload({name:'Invoice / totals?',schema:nested,version:3,dataset_id:'source'});
 assert.equal(exported.fileName,'Invoice - totals--v3.json');
 const uploaded=await readPromptUpload(file(exported.json,exported.fileName));
 assert.equal(uploaded.name,'Invoice / totals?');assert.deepEqual(uploaded.schema,nested);
 assert.equal(JSON.parse(exported.json).dataset_id,undefined);
 assert.deepEqual(JSON.parse(promptTemplateDownload({name:'Legacy',schema_json:schema}).json).schema,schema);
 assert.throws(()=>promptTemplateDownload({name:'Broken'}),/no valid schema/);
});
test('template list renders one row per selected dataset prompt with all row actions',()=>{
 const markup=renderToStaticMarkup(React.createElement(PromptTemplates,{templates:[{id:'a',name:'Invoice one',schema,dataset_id:'one',version:2},{id:'b',name:'Other dataset',schema,dataset_id:'two'}],datasets:[{id:'one',name:'Invoices'},{id:'two',name:'Other'}],selectedDataset:'one',initialId:'',api:async()=>{},onSaved:()=>{},onUse:()=>{},onDirty:()=>{}}));
 assert.match(markup,/prompt-template-row/);assert.match(markup,/Invoice one/);assert.doesNotMatch(markup,/Prompt template Other dataset/);
 for(const label of ['Edit','Versions','Download','Use template'])assert.match(markup,new RegExp(label));
 assert.match(markup,/Invoices \u00b7 1 field \u00b7 Version 2/);assert.match(markup,/href="\/api\/templates\/a\/export\?version=2"/);assert.match(markup,/download="Invoice one-v2.json"/);assert.doesNotMatch(markup,/prompt-template-editor/);
});
test('editing a scoped template displays its fixed dataset and existing fields',()=>{
 const markup=renderToStaticMarkup(React.createElement(PromptTemplates,{templates:[{id:'a',name:'Invoice',schema,dataset_id:'one'}],datasets:[{id:'one',name:'Invoices'}],selectedDataset:'one',initialId:'a',api:async()=>{},onSaved:()=>{},onUse:()=>{},onDirty:()=>{}}));
 assert.match(markup,/<select aria-label="Template dataset"[^>]*disabled/);
 assert.match(markup,/The dataset is fixed/);assert.match(markup,/Save new version/);
});
