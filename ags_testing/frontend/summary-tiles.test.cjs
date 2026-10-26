const {test}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),Module=require('node:module'),ts=require('typescript');
const React=require('react'),{renderToStaticMarkup}=require('react-dom/server');
function compile(name){const filename=path.resolve(__dirname,'../../ags_frontend/app',name),m=new Module(filename,module);m.filename=filename;m.paths=module.paths;const original=m.require.bind(m);m.require=id=>id.endsWith('.css')?{}:id==='./manage-dataset'?{openDatasetEditor(){}}:id==='./summary-tiles'?compile('summary-tiles.tsx'):id==='./needs-attention'?compile('needs-attention.tsx'):id==='./action-button'?require('./support/action-button.cjs').actionButton:id==='lucide-react'?new Proxy({},{get:()=>()=>null}):original(id);m._compile(ts.transpileModule(fs.readFileSync(filename,'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022,jsx:ts.JsxEmit.ReactJSX}}).outputText,filename);return m.exports;}
test('dataset readiness counts datasets by their loaded documents',()=>{
 const {directorySummary}=compile('dataset-directory.tsx');
 const datasets=[{id:'a'},{id:'b'},{id:'c',active:false},{id:'d'}];
 const documents=[{dataset_id:'a',status:'ready'},{dataset_id:'b',status:'failed'},{kb_id:'b',status:'ready',requires_reindex:true},{dataset_id:'c',status:'ready'}];
 assert.deepEqual(directorySummary(datasets,documents).map(t=>[t.label,t.value]),[['Datasets',4],['Ready to ask',2],['Need attention',1],['No documents',1]]);
 assert.equal(directorySummary(datasets,documents)[0].detail,'1 inactive');
});
test('summary tiles render as a labelled description list',()=>{
 const {SummaryTiles}=compile('summary-tiles.tsx');
 const html=renderToStaticMarkup(React.createElement(SummaryTiles,{label:'Extract summary',tiles:[{label:'Records',value:3,detail:'matching',tone:'ok'}]}));
 assert.match(html,/<dl class="screen-summary" aria-label="Extract summary">/);assert.match(html,/<dt>Records<\/dt><dd>3<\/dd>/);assert.match(html,/data-tone="ok"/);
});
test('model mapping overview counts fully mapped datasets and names missing roles',()=>{
 const {mappingTiles,missingRoles,MappingOverview}=compile('mapping-overview.tsx');
 const datasets=[{id:'a',name:'Claims',embedding_model_id:'e',default_chat_model_id:'c',default_extraction_model_id:'x'},{id:'b',name:'Policies',default_chat_model_id:'c',active:false}];
 assert.deepEqual(mappingTiles(datasets).map(t=>[t.label,t.value]),[['Datasets',2],['Fully mapped',1],['Missing embedding',1]]);
 assert.deepEqual(missingRoles(datasets[1]),['Embedding','Extraction']);
 const html=renderToStaticMarkup(React.createElement(MappingOverview,{datasets,selected:'b',busy:false,onSelect:()=>{}}));
 assert.match(html,/aria-pressed="true"[^>]*>.*Policies/);assert.match(html,/Needs Embedding, Extraction/);
 assert.equal(renderToStaticMarkup(React.createElement(MappingOverview,{datasets:[],selected:'',busy:false,onSelect:()=>{}})),'');
});
