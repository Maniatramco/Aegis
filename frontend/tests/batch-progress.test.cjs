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
const {OperationProgress,extractionProgressJob}=load(path.resolve(__dirname,'../app/operation-progress.tsx'));
const {DocumentUploadPanel}=load(path.resolve(__dirname,'../app/document-upload.tsx'));
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

function uploadController(batchRows, extra={}) {
 return {dataset:{name:'Upload QA'},batchRows,pending:[],uploading:false,blocked:'',retrying:[],notice:'',pollError:false,externalRequired:false,consent:false,maxMb:25,...extra};
}
test('re-extraction dialog owns its workflow until it closes, when background progress resumes',()=>{
 const job={id:'re-extract-1',kind:'extract',status:'running',workflow:{stages:{generate:{status:'running'}}}};
 const foreground=renderToStaticMarkup(React.createElement(OperationProgress,{requests:[],jobs:[job],visibleJobId:job.id}));
 assert.equal(foreground,'');
 const background=renderToStaticMarkup(React.createElement(OperationProgress,{requests:[],jobs:[job],visibleJobId:null}));
 assert.equal((background.match(/class="job-progress"/g)||[]).length,1);
 assert.match(background,/Processing in background/);
});
test('a foreground extraction does not hide other jobs or unrelated loading activity',()=>{
 const jobs=[{id:'foreground',kind:'extract',status:'queued'},{id:'other',kind:'extract',status:'running'}];
 const html=renderToStaticMarkup(React.createElement(OperationProgress,{requests:[{id:'refresh',label:'Loading documents…'}],jobs,visibleJobId:'foreground'}));
 assert.equal((html.match(/class="job-progress"/g)||[]).length,1);
 assert.match(html,/Loading documents/);
 assert.match(html,/In progress/);
 assert.doesNotMatch(html,/>queued</);
});
test('processing and completed views show one workflow without a file picker or upload button',()=>{
 for(const batchRows of [items,items.map(item=>({...item,processing:false,ready:true,document:{...item.document,status:'ready'}}))]) {
  const html=renderToStaticMarkup(React.createElement(DocumentUploadPanel,{upload:uploadController(batchRows),workflowOnly:true}));
  assert.equal((html.match(/aria-label="Batch upload workflow"/g)||[]).length,1);
  assert.doesNotMatch(html,/type="file"|Drop documents here|Choose documents|class="upload-actions"/);
  assert.match(html,/invoice-0\.txt/);
 }
});
test('the attachment view retains file selection before starting processing',()=>{
 const html=renderToStaticMarkup(React.createElement(DocumentUploadPanel,{upload:uploadController([]),attachmentOnly:true}));
 assert.match(html,/type="file"/);
 assert.match(html,/Choose documents/);
 assert.doesNotMatch(html,/aria-label="Batch upload workflow"/);
});
test('workflow-only failures retain their reasons and retry actions without file selection',()=>{
 const failed={...items[0],processing:false,failed:true,document:{...items[0].document,status:'failed',error:'Embedding provider timed out'},job:{status:'failed',workflow:{current:'index'}}};
 const html=renderToStaticMarkup(React.createElement(DocumentUploadPanel,{upload:uploadController([failed]),workflowOnly:true}));
 assert.match(html,/Embedding provider timed out/);
 assert.match(html,/Retry failed step/);
 assert.doesNotMatch(html,/type="file"/);
 const rejected={id:'rejected',name:'rejected.txt',status:'failed',error:'Upload rejected'};
 const uploadFailure=renderToStaticMarkup(React.createElement(DocumentUploadPanel,{upload:uploadController([rejected],{pending:[rejected]}),workflowOnly:true}));
 assert.match(uploadFailure,/Retry upload/);
 assert.doesNotMatch(uploadFailure,/type="file"/);
});

const {ExtractionReview}=load(path.resolve(__dirname,'../app/extraction-review.tsx'));
test('review and background progress render an extraction workflow only once while refresh remains visible',()=>{
 const extraction={id:'review-extraction',status:'queued',version:1,document_ids:['review-doc'],job:{id:'review-job',kind:'extract',status:'queued'}};
 const jobs=[{id:'review-job',kind:'extract',target_id:extraction.id,status:'running',progress:20,workflow:{current:'generate',stages:{prepare:{status:'completed'},generate:{status:'running'}}}}];
 const foreground=extractionProgressJob(extraction,jobs);
 const html=renderToStaticMarkup(React.createElement(React.Fragment,null,
  React.createElement(ExtractionReview,{extraction,documents:[{id:'review-doc',name:'invoice.txt'}],jobs,api:async()=>{},onSaved:()=>{},onDirty:()=>{}}),
  React.createElement(OperationProgress,{requests:[{id:'refresh',label:'Loading documents…'}],jobs,visibleJobId:foreground.id})
 ));
 assert.equal((html.match(/aria-label="Processing workflow"/g)||[]).length,1);
 assert.match(html,/Loading documents/);
 assert.match(html,/Extract fields/);
 const background=renderToStaticMarkup(React.createElement(OperationProgress,{requests:[],jobs,visibleJobId:null}));
 assert.equal((background.match(/aria-label="Processing workflow"/g)||[]).length,1);
});
test('review resolves the current extraction job after a result refresh removes the embedded job',()=>{
 const jobs=[{id:'old',kind:'extract',target_id:'result',created_at:10,status:'completed'},{id:'unrelated',kind:'extract',target_id:'other',created_at:30,status:'running'},{id:'current',kind:'extract',target_id:'result',created_at:20,status:'running'}];
 assert.equal(extractionProgressJob({id:'result'},jobs).id,'current');
 assert.equal(extractionProgressJob({id:'result',job:{id:'current',status:'queued'}},jobs).status,'running');
 assert.equal(extractionProgressJob({id:'new',job:{id:'accepted',status:'queued'}},jobs).id,'accepted');
 assert.equal(extractionProgressJob(null,jobs),undefined);
});


test('loading progress names the current task and closes after all requests finish',()=>{
 const html=renderToStaticMarkup(React.createElement(OperationProgress,{requests:[{id:'datasets',label:'Loading datasets…'}],jobs:[]}));
 assert.match(html,/operation-popup is-loading/);
 assert.match(html,/<strong>Loading datasets…<\/strong>/);
 assert.doesNotMatch(html,/Working…|<li>/);
 assert.match(html,/close automatically when complete/);
 assert.equal(renderToStaticMarkup(React.createElement(OperationProgress,{requests:[],jobs:[]})),'');
});
test('parallel refresh lists each outstanding task once and keeps the final task specific',()=>{
 const requests=[{id:'datasets',label:'Loading datasets…'},{id:'documents',label:'Loading documents…'},{id:'duplicate',label:'Loading documents…'}];
 const html=renderToStaticMarkup(React.createElement(OperationProgress,{requests,jobs:[]}));
 assert.match(html,/<strong>Loading workspace…<\/strong>/);
 assert.equal((html.match(/<li>/g)||[]).length,2);
 const finishing=renderToStaticMarkup(React.createElement(OperationProgress,{requests:requests.slice(1),jobs:[]}));
 assert.match(finishing,/<strong>Loading documents…<\/strong>/);
 assert.doesNotMatch(finishing,/<li>/);
});
