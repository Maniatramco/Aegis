const {test}=require('node:test');const assert=require('node:assert/strict');
const fs=require('node:fs'),path=require('node:path'),Module=require('node:module'),ts=require('typescript');
const React=require('react'),{renderToStaticMarkup}=require('react-dom/server');
function compile(name,overrides={}){
 const filename=path.resolve(__dirname,'../../ags_frontend/app',name),m=new Module(filename,module);m.filename=filename;m.paths=module.paths;
 const original=m.require.bind(m);m.require=id=>{
  if(Object.hasOwn(overrides,id))return overrides[id];
  if(id.endsWith('.css'))return {};
  if(id.startsWith('.')){const base=path.resolve(path.dirname(filename),id);const source=[base+'.tsx',base+'.ts'].find(file=>fs.existsSync(file));if(source)return compile(path.relative(path.resolve(__dirname,'../../ags_frontend/app'),source),overrides);}
  return original(id);
 };
 m._compile(ts.transpileModule(fs.readFileSync(filename,'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022,jsx:ts.JsxEmit.ReactJSX}}).outputText,filename);return m.exports;
}
const {ExtractionDirectory,matchingExtractions}=compile('extraction-directory.tsx');
const runs=[{id:'extract-a',dataset_id:'dataset-a',template_id:'schema',name:'merged.pdf',status:'ready',version:2,created_at:2,review_status:'reviewed',merge:{filename:'merged.pdf',sources:[{name:'one.pdf'},{name:'two.pdf'}]},profile_count:2},
 {id:'extract-b',dataset_id:'dataset-b',template_id:'schema',name:'merged.pdf',status:'failed',version:1,created_at:3}];
test('review directory filters by dataset, exact extraction ID, source filename and status',()=>{
 assert.deepEqual(matchingExtractions(runs,'dataset-a','','',[]).map(e=>e.id),['extract-a']);
 assert.deepEqual(matchingExtractions(runs,'','extract-b','',[]).map(e=>e.id),['extract-b']);
 assert.deepEqual(matchingExtractions(runs,'','two.pdf','ready',[]).map(e=>e.id),['extract-a']);
 assert.equal(matchingExtractions(runs,'dataset-a','extract-b','',[]).length,0);
});
test('review directory displays dataset identity, complete extraction ID, merged filename and version',()=>{
 const html=renderToStaticMarkup(React.createElement(ExtractionDirectory,{datasets:[{id:'dataset-a',name:'Resume QA'}],templates:[{id:'schema',name:'Profile schema'}],extractions:runs,documents:[],selectedDataset:'dataset-a',selectedId:'extract-a',onDatasetChange(){},onOpen(){}}));
 for(const text of ['Resume QA','extract-a','merged.pdf','v2','2 merged files','2 profiles / items','Extraction dataset filter','Search extractions','Actions','Reviewed'])assert.ok(html.includes(text),text);
 assert.ok(!html.includes('extract-b'));
 assert.ok(!html.includes('Search extraction column'));assert.match(html,/type="search"/);
});
test('saved-result citations render clickable references and extraction source actions',()=>{
 const {AgentChatAnswer}=compile('agent-v2-chat.tsx',{'./agent-attachments':compile('agent-attachments.ts')});
 const html=renderToStaticMarkup(React.createElement(AgentChatAnswer,{message:{id:'m',text:'Python listed. [1]',status:'completed',citations:[{kind:'extraction',index:1,extraction_id:'extract-a',version:2,review_status:'reviewed',document_name:'one.pdf',text:'{"skills":["Python"]}'}]},api:async()=>{},onError(){},onReview(){}}));
 assert.match(html,/Open citation 1/);assert.match(html,/Saved extraction/);assert.match(html,/class="text-button"/);assert.match(html,/version 2/);
 assert.ok(!html.includes('/api/documents/undefined'));
});

test('directory separates review state from processing state and searches actual dataset/template metadata',()=>{
 const mixed=[...runs,{id:'pending',dataset_id:'dataset-a',status:'ready',review_status:'unreviewed',template_id:'schema',created_at:4}];
 const datasets=[{id:'dataset-a',name:'Resume QA'}],templates=[{id:'schema',name:'Profile schema'}];
 assert.deepEqual(matchingExtractions(mixed,'','','reviewed').map(e=>e.id),['extract-a']);
 assert.deepEqual(matchingExtractions(mixed,'','','unreviewed').map(e=>e.id),['pending']);
 assert.deepEqual(matchingExtractions(mixed,'','Profile schema','',[],datasets,templates).map(e=>e.id),['pending','extract-b','extract-a']);
 assert.deepEqual(matchingExtractions(mixed,'','Resume QA','',[],datasets,templates).map(e=>e.id),['pending','extract-a']);
 assert.deepEqual(matchingExtractions(mixed,'','  RESUME   schema  REVIEWED ','',[],datasets,templates).map(e=>e.id),['extract-a']);
 assert.deepEqual(matchingExtractions(mixed,'','v2 1970-01-01','',[],datasets,templates).map(e=>e.id),['extract-a']);
 assert.equal(matchingExtractions(mixed,'','unmatched','',[],datasets,templates).length,0);
 assert.equal(matchingExtractions(mixed,'','','unreviewed').some(e=>e.status==='failed'),false);
});

test('extract actions keep review available while preventing a second run on a queued extraction',()=>{
 const html=renderToStaticMarkup(React.createElement(ExtractionDirectory,{datasets:[],templates:[{id:'schema',name:'Profile schema'}],extractions:[{id:'queued-run',template_id:'schema',status:'queued',created_at:1}],documents:[],selectedDataset:'',onDatasetChange(){},onOpen(){},onReExtract(){}}));
 assert.match(html,/aria-label="Re-extract extraction queued-run"[^>]*disabled/);
 assert.match(html,/aria-label="Review extraction queued-run"/);
 const review=html.match(/<button[^>]*aria-label="Review extraction queued-run"[^>]*>/)[0];assert.ok(!review.includes('disabled'));
});
test('Manage workspace model links preserve admin-only visibility',()=>{
 const {WorkspaceNavigation}=compile('workspace-navigation.tsx',{'./agent-logo':compile('agent-logo.tsx',{'./agent-logo.css':{}})});
 const props={view:'Extract',onNavigate(){},adminItems:[],adminOpen:true,onAdminToggle(){}};
 const member=renderToStaticMarkup(React.createElement(WorkspaceNavigation,{...props,isAdmin:false})),admin=renderToStaticMarkup(React.createElement(WorkspaceNavigation,{...props,isAdmin:true}));
 for(const label of ['Dashboard','Aegis Agent','Onboard','Datasets','Prompt templates','Extract','Review','Jobs &amp; activity'])assert.ok(member.includes('aria-label="'+label+'"'));
 assert.ok(!member.includes('aria-label="Onboard dataset"'));assert.ok(!admin.includes('aria-label="Onboard dataset"'));
 assert.ok(!member.includes('aria-label="Model Registration"'));assert.ok(!member.includes('aria-label="Model Mapping"'));
 assert.ok(admin.includes('aria-label="Model Registration"'));assert.ok(admin.includes('aria-label="Model Mapping"'));
 assert.ok(!admin.includes('aria-label="Model"'));assert.ok(!admin.includes('id="model-navigation"'));
 assert.ok(!admin.includes('aria-label="Re-extract"'));
});
