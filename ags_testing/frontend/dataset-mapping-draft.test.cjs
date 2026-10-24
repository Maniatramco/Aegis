const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const ts=require('typescript');
const Module=require('node:module');
const file=path.resolve(__dirname,'../../ags_frontend/app/dataset-mapping-draft.ts');
const compiled=new Module(file,module);
compiled._compile(ts.transpileModule(fs.readFileSync(file,'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS}}).outputText,file);
const {selectMappingDefault,setMappingEnabled}=compiled.exports;
const initial=()=>({chatDefault:'mini-chat',extractDefault:'mini-extract',embedding:'embedding',mappings:[{model_id:'embedding',enabled:true},{model_id:'mini-chat',enabled:true},{model_id:'full-chat',enabled:true},{model_id:'mini-extract',enabled:true},{model_id:'full-extract',enabled:true},{model_id:'other',enabled:false,retained:'metadata'}]});

test('changing a default preserves every other mapped model, disabled state and metadata',()=>{
 const before=initial();const next=selectMappingDefault(before,'chatDefault','full-chat');
 assert.equal(next.chatDefault,'full-chat');assert.deepEqual(next.mappings,before.mappings);
 assert.equal(before.chatDefault,'mini-chat');assert.equal(next.extractDefault,before.extractDefault);assert.equal(next.embedding,before.embedding);
});
test('a newly chosen default is enabled exactly once without dropping alternatives',()=>{
 const before=initial();const next=selectMappingDefault(before,'extractDefault','new-extract');
 assert.deepEqual(next.mappings.slice(0,before.mappings.length),before.mappings);
 assert.deepEqual(next.mappings.at(-1),{model_id:'new-extract',enabled:true});
 assert.equal(selectMappingDefault(next,'extractDefault','new-extract').mappings.length,next.mappings.length);
});
test('choosing a previously disabled model enables its saved mapping and retains metadata',()=>{
 const next=selectMappingDefault(initial(),'chatDefault','other');
 assert.deepEqual(next.mappings.find(m=>m.model_id==='other'),{model_id:'other',enabled:true,retained:'metadata'});
});
test('enabling both OpenAI alternatives keeps defaults and embedding unchanged',()=>{
 const before={...initial(),mappings:[{model_id:'embedding',enabled:true},{model_id:'mini-chat',enabled:true},{model_id:'mini-extract',enabled:true}]};
 const next=setMappingEnabled(setMappingEnabled(before,'full-chat',true),'full-extract',true);
 assert.equal(next.chatDefault,before.chatDefault);assert.equal(next.extractDefault,before.extractDefault);assert.equal(next.embedding,before.embedding);
 assert.equal(next.mappings.filter(m=>m.enabled).length,5);assert.equal(before.mappings.length,3);
});
test('disabling an alternative preserves unrelated mappings and both role defaults',()=>{
 const before=initial();const next=setMappingEnabled(before,'full-chat',false);
 assert.equal(next.mappings.find(m=>m.model_id==='full-chat').enabled,false);
 assert.deepEqual(next.mappings.filter(m=>m.model_id!=='full-chat'),before.mappings.filter(m=>m.model_id!=='full-chat'));
 assert.equal(next.chatDefault,before.chatDefault);assert.equal(next.extractDefault,before.extractDefault);
});
test('the selected chat, extraction and embedding defaults cannot be disabled',()=>{
 const before=initial();for(const id of [before.chatDefault,before.extractDefault,before.embedding])assert.equal(setMappingEnabled(before,id,false),before);
});
test('reenabling an alternative does not duplicate its mapping',()=>{
 const next=setMappingEnabled(setMappingEnabled(initial(),'full-chat',false),'full-chat',true);
 assert.equal(next.mappings.filter(m=>m.model_id==='full-chat').length,1);assert.equal(next.mappings.find(m=>m.model_id==='full-chat').enabled,true);
});
