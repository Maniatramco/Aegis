const {test}=require('node:test');const assert=require('node:assert/strict');
const fs=require('node:fs'),path=require('node:path'),Module=require('node:module'),ts=require('typescript');
const React=require('react'),{renderToStaticMarkup}=require('react-dom/server');
function compile(name,overrides={}){
 const filename=path.resolve(__dirname,'../app',name),m=new Module(filename,module);m.filename=filename;m.paths=module.paths;
 const original=m.require.bind(m);m.require=id=>Object.hasOwn(overrides,id)?overrides[id]:original(id);
 m._compile(ts.transpileModule(fs.readFileSync(filename,'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022,jsx:ts.JsxEmit.ReactJSX}}).outputText,filename);return m.exports;
}
const {ExtractionDirectory,matchingExtractions}=compile('extraction-directory.tsx');
const runs=[{id:'extract-a',dataset_id:'dataset-a',name:'merged.pdf',status:'ready',version:2,created_at:2,review_status:'reviewed',merge:{filename:'merged.pdf',sources:[{name:'one.pdf'},{name:'two.pdf'}]},profile_count:2},
 {id:'extract-b',dataset_id:'dataset-b',name:'merged.pdf',status:'failed',version:1,created_at:3}];
test('review directory filters by dataset, exact extraction ID, source filename and status',()=>{
 assert.deepEqual(matchingExtractions(runs,'dataset-a','','',[]).map(e=>e.id),['extract-a']);
 assert.deepEqual(matchingExtractions(runs,'','extract-b','',[]).map(e=>e.id),['extract-b']);
 assert.deepEqual(matchingExtractions(runs,'','two.pdf','ready',[]).map(e=>e.id),['extract-a']);
 assert.equal(matchingExtractions(runs,'dataset-a','extract-b','',[]).length,0);
});
test('review directory displays dataset identity, complete extraction ID, merged filename and version',()=>{
 const html=renderToStaticMarkup(React.createElement(ExtractionDirectory,{datasets:[{id:'dataset-a',name:'Resume QA'}],extractions:runs,documents:[],selectedDataset:'dataset-a',selectedId:'extract-a',onDatasetChange(){},onOpen(){}}));
 for(const text of ['Resume QA','extract-a','merged.pdf','v2','2 merged files','2 profiles / items','Review dataset filter','Search extraction ID or filename'])assert.ok(html.includes(text),text);
 assert.ok(!html.includes('extract-b'));
});
test('saved-result citations render clickable references and extraction source actions',()=>{
 const {AgentChatAnswer}=compile('agent-v2-chat.tsx',{'./agent-attachments':compile('agent-attachments.ts')});
 const html=renderToStaticMarkup(React.createElement(AgentChatAnswer,{message:{id:'m',text:'Python listed. [1]',status:'completed',citations:[{kind:'extraction',index:1,extraction_id:'extract-a',version:2,review_status:'reviewed',document_name:'one.pdf',text:'{"skills":["Python"]}'}]},api:async()=>{},onError(){},onReview(){}}));
 assert.match(html,/Open citation 1/);assert.match(html,/Open extraction source/);assert.match(html,/version 2/);
 assert.ok(!html.includes('/api/documents/undefined'));
});
