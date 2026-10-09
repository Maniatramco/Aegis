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
const {TemporaryDocumentChat}=load(path.resolve(__dirname,'../app/temporary-document-chat.tsx'));
const models=[
 {id:'chat',name:'Local chat',provider:'ollama',provider_model:'qwen3',capabilities:['chat'],enabled:true},
 {id:'embed',name:'Embedding only',provider:'ollama',provider_model:'nomic',capabilities:['embedding'],enabled:true},
 {id:'extract',name:'Extraction only',provider:'ollama',provider_model:'qwen3',capabilities:['extraction'],enabled:true},
 {id:'disabled',name:'Disabled chat',provider:'ollama',provider_model:'disabled',capabilities:['chat'],enabled:false},
 {id:'mock',name:'Mock chat',provider:'mock',provider_model:'mock',capabilities:['chat'],enabled:true},
 {id:'cloud',name:'Cloud chat',provider:'openai',provider_model:'remote',capabilities:['chat'],enabled:true}
];
function render(settings={local_only:true,mock_allowed:false}) {
 return renderToStaticMarkup(React.createElement(TemporaryDocumentChat,{models,initialModelId:'chat',settings,api:async()=>{},onExit:()=>{}}));
}
test('temporary mode needs no dataset, exposes one file input, and blocks questions before upload',()=>{
 const html=render();
 assert.equal((html.match(/type="file"/g)||[]).length,1);
 assert.doesNotMatch(html,/multiple=""/);
 assert.match(html,/accept="\.pdf,\.docx,\.txt"/);
 assert.match(html,/aria-label="Send temporary question" disabled=""/);
 assert.match(html,/No embeddings, index, or saved conversation/);
 assert.match(html,/up to one hour/);
 assert.doesNotMatch(html,/Choose a dataset|JSON template|reranking|New chat|Saved chat/);
});
test('only enabled chat-capable registrations are selectable and local-only disables cloud options',()=>{
 const html=render();
 assert.match(html,/<option value="chat" selected="">Local chat/);
 assert.match(html,/<option value="cloud" disabled="">Cloud chat/);
 assert.doesNotMatch(html,/Embedding only|Extraction only|Disabled chat|Mock chat/);
});
test('cloud registrations become selectable when local-only is disabled',()=>{
 const html=render({local_only:false,mock_allowed:false});
 assert.match(html,/<option value="cloud">Cloud chat/);
 assert.doesNotMatch(html,/cloud disabled/);
});
