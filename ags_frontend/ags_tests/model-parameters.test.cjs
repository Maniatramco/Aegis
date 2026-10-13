const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const ts=require('typescript');
const Module=require('node:module');
const file=path.resolve(__dirname,'../app/model-parameters.ts');
const compiled=new Module(file,module);
compiled._compile(ts.transpileModule(fs.readFileSync(file,'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS}}).outputText,file);
const {parseModelParameters,supportedModelParameters}=compiled.exports;

test('provider/category parameters follow each native request format',()=>{
 assert.ok(supportedModelParameters('ollama','chat').includes('top_p'));
 assert.ok(supportedModelParameters('vertex','extraction').includes('topP'));
 assert.ok(supportedModelParameters('bedrock','chat').includes('stopSequences'));
 assert.deepEqual(supportedModelParameters('ollama','embedding'),['keep_alive']);
 assert.deepEqual(supportedModelParameters('vertex','embedding'),[]);
 assert.ok(supportedModelParameters('oci','chat',{chat_format:'cohere'}).includes('stop_sequences'));
});
test('parameters retain JSON types and blank means default',()=>{
 const keys=supportedModelParameters('ollama','chat');
 assert.deepEqual(parseModelParameters('{"temperature":0.2,"seed":42,"stop":["END"]}',keys),{temperature:0.2,seed:42,stop:['END']});
 assert.deepEqual(parseModelParameters(' ',keys),{});
});
test('malformed, non-object, and transport/token overrides cannot be submitted',()=>{
 const keys=supportedModelParameters('ollama','chat');
 for(const value of ['{bad}','null','[]','"value"','{"stream":true}','{"num_ctx":8192}','{"api_key":"secret"}']) assert.throws(()=>parseModelParameters(value,keys));
});
