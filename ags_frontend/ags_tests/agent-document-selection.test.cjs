const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');const path=require('node:path');const Module=require('node:module');const ts=require('typescript');
const filename=path.resolve(__dirname,'../app/agent-document-selection.ts');
const compiled=new Module(filename,module);compiled.filename=filename;compiled.paths=module.paths;
compiled._compile(ts.transpileModule(fs.readFileSync(filename,'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText,filename);
const {readyDatasetDocuments,matchingDocuments,documentMention,documentOptionLabel,eligibleAgentModels}=compiled.exports;
test('document suggestions never include another dataset or processing files',()=>{
 const docs=[{id:'a',parent_id:'one',status:'ready',name:'Invoice.pdf'},{id:'b',parent_id:'two',status:'ready',name:'Hidden.pdf'},{id:'c',parent_id:'one',status:'processing',name:'Pending.pdf'}];
 assert.deepEqual(readyDatasetDocuments(docs,'one').map(d=>d.id),['a']);assert.deepEqual(readyDatasetDocuments(docs,''),[]);
 assert.deepEqual(matchingDocuments(readyDatasetDocuments(docs,'one'),'INVOICE').map(d=>d.id),['a']);
});
test('hash trigger works at the caret without consuming later text or code fragments',()=>{
 assert.deepEqual(documentMention('Summarize #invoice later',18),{start:10,end:18,query:'invoice'});
 assert.deepEqual(documentMention('#',1),{start:0,end:1,query:''});
 for(const text of ['C#','https://example/#anchor','## title','no mention'])assert.equal(documentMention(text,text.length),null);
 assert.equal(documentMention('#invoice\nnext line',18),null);
});
test('duplicate filenames keep distinct document identities',()=>{
 const docs=[{id:'document-111111',name:'invoice.pdf'},{id:'document-222222',name:'invoice.pdf'}];
 assert.notEqual(documentOptionLabel(docs[0],docs),documentOptionLabel(docs[1],docs));
});
test('one agent model selector only offers enabled dataset mappings for document chat',()=>{
 const models=[{id:'a',capabilities:['chat']},{id:'b',capabilities:['chat'],enabled:false},{id:'c',capabilities:['embedding']}];
 assert.deepEqual(eligibleAgentModels(models,undefined).map(m=>m.id),['a']);
 assert.deepEqual(eligibleAgentModels(models,{models:[models[0],{id:'unmapped',capabilities:['chat'],mapping_enabled:false}]}).map(m=>m.id),['a']);
});
