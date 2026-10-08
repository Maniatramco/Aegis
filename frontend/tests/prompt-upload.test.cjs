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
