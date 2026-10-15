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
const {OperationProgress,extractionProgressJob,JobProgress}=load(path.resolve(__dirname,'../../ags_frontend/app/operation-progress.tsx'));
const {explainPlan}=load(path.resolve(__dirname,'../../ags_frontend/app/agent-v2.tsx'));
const {AgentChatAnswer,AgentAnswerText,conversationExchanges}=load(path.resolve(__dirname,'../../ags_frontend/app/agent-v2-chat.tsx'));

test('V2 shares saved chat history and canonical sources without fabricating unfinished answers',()=>{
 const conversation={id:'saved-chat',mode:'documents',dataset_id:'dataset-a',document_ids:['doc-a'],messages:[{id:'q1',role:'user',text:'Question',model_selection:{model_id:'m',model_name:'Local model'}},{id:'a1',role:'assistant',text:'Supported answer [1]',status:'completed',citations:[{index:1,document_id:'doc-a',document_name:'Evidence.txt',text:'Canonical excerpt',page:2}]},{id:'q2',role:'user',text:'Follow-up'}]};
 const exchanges=conversationExchanges(conversation);assert.equal(exchanges.length,2);assert.equal(exchanges[0].conversation_id,'saved-chat');assert.equal(exchanges[1].chat,undefined);assert.deepEqual(exchanges[0].calls,[]);
 const html=renderToStaticMarkup(React.createElement(AgentChatAnswer,{message:exchanges[0].chat,api:()=>{},onError:()=>{}}));
 assert.match(html,/Sources · 1/);assert.match(html,/Open citation 1/);assert.match(html,/Evidence.txt · page 2/);assert.equal(exchanges[0].chat.citations[0].text,'Canonical excerpt');assert.doesNotMatch(html,/Canonical excerpt/);assert.match(html,/Copy agent answer/);assert.doesNotMatch(html,/Helpful agent answer|Unhelpful agent answer/);
});
test('compact chat formatting escapes HTML and preserves readable code',()=>{
 const html=renderToStaticMarkup(React.createElement(AgentAnswerText,{text:'**Bold** and `value`\n```python\nprint("hello")\n```\n<script>alert(1)</script>'}));
 assert.match(html,/<strong>Bold<\/strong>/);assert.match(html,/<code>value<\/code>/);assert.match(html,/<pre><code>/);assert.match(html,/&lt;script&gt;/);assert.doesNotMatch(html,/<script>/);
 const failed=renderToStaticMarkup(React.createElement(AgentChatAnswer,{message:{text:'Partial',status:'failed',error:{detail:'Offline'}},api:()=>{},onError:()=>{}}));
 assert.match(failed,/role="alert"/);assert.match(failed,/Offline/);assert.match(failed,/Copy agent answer/);assert.doesNotMatch(failed,/Helpful agent answer|Unhelpful agent answer/);
});

test('unified knowledge citations open the authorized source rather than a missing document',()=>{
 const html=renderToStaticMarkup(React.createElement(AgentChatAnswer,{message:{text:'Supplier dataset [1]',status:'completed',citations:[{index:1,kind:'knowledge',source_type:'dataset',knowledge_id:'point-id',knowledge_collection:'aegis_knowledge_abc',document_name:'Supplier dataset',text:'Canonical dataset description',source_version:2}]},api:()=>{},onError:()=>{}}));
 assert.match(html,/Supplier dataset/);assert.match(html,/Open citation 1/);
 assert.match(html,/class="text-button"/);
 assert.doesNotMatch(html,/documents\/undefined/);
 assert.doesNotMatch(html,/Canonical dataset description/);
});
const items=Array.from({length:10},(_,i)=>({id:'row-'+i,name:'invoice-'+i+'.txt',status:'submitted',processing:true,document:{id:'doc-'+i,status:'processing'},job:{status:'running',workflow:{current:'extract',stages:{extract:{status:'running'}}}}}));
const jobs=items.map((item,i)=>({...item.job,id:'job-'+i,kind:'index',document_id:item.document.id}));

test('Agent keeps requests and background jobs inline without a second floating workflow',()=>{
 const props={requests:[{id:'refresh',label:'Reading workspace'}],workspaceLoading:true,jobs:[...jobs,{id:'extract',kind:'extract',status:'running',workflow:{stages:{generate:{status:'running'}}}}],uploadItems:items};
 assert.equal(renderToStaticMarkup(React.createElement(OperationProgress,{...props,agentWorkspace:true})), '');
 assert.match(renderToStaticMarkup(React.createElement(OperationProgress,props)),/aria-label="Workspace progress"/);
});
test('closing the upload panel gives ten documents one background workflow',()=>{
 const html=renderToStaticMarkup(React.createElement(OperationProgress,{requests:[],jobs,uploadItems:items}));
 assert.equal((html.match(/aria-label="Batch upload workflow"/g)||[]).length,1);
 assert.equal((html.match(/invoice-\d+\.txt/g)||[]).length,10);
 assert.equal((html.match(/class="job-progress"/g)||[]).length,0);
 assert.match(html,/stage-running/);
});

test('V2 owns all its visible jobs while unrelated progress remains available',()=>{
 const owned=jobs.map(job=>job.id);
 const hidden=renderToStaticMarkup(React.createElement(OperationProgress,{requests:[],jobs,visibleJobIds:owned}));
 assert.equal(hidden,'');
 const tracked=items.map((item,i)=>({...item,job:{...item.job,id:owned[i]}}));
 assert.equal(renderToStaticMarkup(React.createElement(OperationProgress,{requests:[],jobs,uploadItems:tracked,visibleJobIds:owned})), '');
 const other={id:'unrelated-extraction',kind:'extract',status:'running',workflow:{stages:{generate:{status:'running'}}}};
 const html=renderToStaticMarkup(React.createElement(OperationProgress,{requests:[],jobs:[...jobs,other],visibleJobIds:owned}));
 assert.equal((html.match(/class="job-progress"/g)||[]).length,1);
 assert.equal((html.match(/aria-label="Batch upload workflow"/g)||[]).length,0);
 assert.match(html,/Extraction/);
});

test('V2 describes selected tools without repeating invented pre-execution results',()=>{
 const text=explainPlan({explanation:'All files are valid and extraction completed!',calls:[{tool:'upload'},{tool:'extract'}]});
 assert.match(text,/Upload documents → Extract fields/);
 assert.match(text,/confirm the workflow/);
 assert.match(text,/after indexing finishes/);
 assert.doesNotMatch(text,/are valid|completed!/);
 const reply='Hi! I can upload documents, extract fields, and re-extract while keeping previous results. What would you like to do?';
 assert.equal(explainPlan({calls:[],explanation:reply}),reply);
 assert.match(explainPlan({calls:[],explanation:''}),/What would you like to do/);
});

const {AgentJobProgress,AgentResult}=load(path.resolve(__dirname,'../../ags_frontend/app/agent-v2-output.tsx'));
test('merged result identifies every original and the single extraction without losing profiles',()=>{
 const merge={filename:'merged-profiles-3.pdf',source_count:3,document_id:'combined',sources:['Alice','Bob','Carol'].map((name,n)=>({key:String(n+1),name:name+'.pdf',size:100,page_count:1,merged_page_start:n+1,merged_page_end:n+1}))};
 const html=renderToStaticMarkup(React.createElement(AgentResult,{tool:{result:{extractions:[{extraction_id:'extract-all-three',status:'completed',name:merge.filename,merge,data:{records:merge.sources.map(s=>({source_filename:s.name,fields:{full_name:s.name}}))}}]}},onReview(){}}));
 assert.match(html,/Extraction ID:.*extract-all-three/);assert.match(html,/merged-profiles-3.pdf/);assert.match(html,/3 separate records/);
 for(const name of ['Alice','Bob','Carol'])assert.match(html,new RegExp(name+'\\.pdf'));
 assert.match(html,/\/api\/extractions\/extract-all-three\/merged-file/);
});

test('merged review keeps its filename and exposes all record fields and retained originals',()=>{
 const {ExtractionReview}=load(path.resolve(__dirname,'../../ags_frontend/app/extraction-review.tsx'));
 const sources=['Alice','Bob','Carol'].map((name,n)=>({key:String(n+1),name:name+'.pdf',size:100,page_count:1,merged_page_start:n+1,merged_page_end:n+1}));
 const e={id:'extract-three',version:1,status:'ready',document_ids:['combined'],merge_records:true,merge:{filename:'merged-three.pdf',source_count:3,document_id:'combined',sources},result:{records:sources.map(s=>({source_filename:s.name,source_key:s.key,fields:{full_name:s.name}}))},sources:sources.map(s=>({document_id:'combined',source_key:s.key,page:Number(s.key),source_page:1}))};
 const html=renderToStaticMarkup(React.createElement(ExtractionReview,{extraction:e,documents:[{id:'combined',name:'merged-three.pdf'}],jobs:[],api:async()=>{},onSaved(){},onDirty(){}}));
 assert.match(html,/merged-three.pdf/);assert.match(html,/Extraction ID.*extract-three/);assert.match(html,/3 separate records extracted/);
 for(const [n,name] of ['Alice','Bob','Carol'].entries()){assert.match(html,new RegExp(`Value /records/${n}/fields/full_name`));assert.match(html,new RegExp(name+'\\.pdf'));}
 assert.match(html,/\/api\/documents\/combined\/merged-sources\/1\/source/);
});
test('compact agent progress retains real stage counts and visible failures',()=>{
 const job={kind:'extract',status:'failed',progress:80,error:'Model unavailable',workflow:{current:'generate',stages:{prepare:{status:'completed'},generate:{status:'failed'},validate:{status:'blocked'},ready:{status:'blocked'}}}};
 const html=renderToStaticMarkup(React.createElement(AgentJobProgress,{job}));
 assert.match(html,/Extraction stopped.*25%/);
 assert.match(html,/aria-label="Agent extraction progress"[^>]*aria-valuenow="25"/);
 assert.doesNotMatch(html,/<details[^>]* open/);
 assert.match(html,/<\/details>.*role="alert".*Model unavailable/);
 const unknown=renderToStaticMarkup(React.createElement(AgentJobProgress,{job:{kind:'extract',status:'running',progress:80}}));
 assert.doesNotMatch(unknown,/Agent extraction progress|80%/);
});
test('compact results keep full JSON expandable and retain the review action',()=>{
 const html=renderToStaticMarkup(React.createElement(AgentResult,{tool:{status:'completed',result:{extraction_id:'saved-result',data:{reference:'QA-001',nested:{amount:42}}}},onReview:()=>{}}));
 assert.match(html,/<details><summary>Extracted fields<\/summary>/);
 assert.match(html,/QA-001/);assert.match(html,/amount/);
 assert.match(html,/Review result and evidence/);
 assert.doesNotMatch(html,/Extraction completed\. Open the result/);
 const pending=renderToStaticMarkup(React.createElement(AgentResult,{tool:{status:'waiting',result:{extraction_id:'queued-result'}},onReview:()=>{}}));
 assert.doesNotMatch(pending,/Review result and evidence|Extracted fields/);
});
test('an open upload panel suppresses duplicate background workflows without suppressing extraction jobs',()=>{
 const hidden=renderToStaticMarkup(React.createElement(OperationProgress,{requests:[],jobs,uploadItems:items,uploadWorkflowVisible:true}));
 assert.equal(hidden,'');
 const html=renderToStaticMarkup(React.createElement(OperationProgress,{requests:[],jobs:[...jobs,{id:'extract-job',kind:'extract',status:'running',workflow:{stages:{generate:{status:'running'}}}}],uploadItems:items,uploadWorkflowVisible:true}));
 assert.equal((html.match(/aria-label="Batch upload workflow"/g)||[]).length,0);
 assert.equal((html.match(/class="job-progress"/g)||[]).length,1);
 assert.match(html,/Extraction/);
});

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
const {ExtractionReview}=load(path.resolve(__dirname,'../../ags_frontend/app/extraction-review.tsx'));
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


test('workspace startup keeps one stable popup as requests finish and background jobs arrive',()=>{
 const states=[[],[{id:'datasets',label:'Loading datasets…'},{id:'documents',label:'Loading documents…'}],[{id:'documents',label:'Loading documents…'}],[]];
 const job={id:'background',kind:'extract',status:'running'};
 for(const requests of states){
  const html=renderToStaticMarkup(React.createElement(OperationProgress,{workspaceLoading:true,requests,jobs:[job]}));
  assert.equal((html.match(/aria-label="Workspace progress"/g)||[]).length,1);
  assert.match(html,/<strong>Loading your workspace…<\/strong>/);
  assert.match(html,/Getting your datasets, documents, and models ready/);
  assert.doesNotMatch(html,/Loading datasets…|Loading documents…|operation-request-list/);
  assert.equal((html.match(/aria-label="Processing workflow"/g)||[]).length,1);
 }
 assert.equal(renderToStaticMarkup(React.createElement(OperationProgress,{workspaceLoading:false,requests:[],jobs:[]})),'');
 const background=renderToStaticMarkup(React.createElement(OperationProgress,{workspaceLoading:false,requests:[],jobs:[job]}));
 assert.match(background,/Processing workflow/);
});
const {DatasetHome}=load(path.resolve(__dirname,'../../ags_frontend/app/dataset-directory.tsx'));
test('Home does not add another loading announcement or flash an empty dataset message during startup',()=>{
 const html=renderToStaticMarkup(React.createElement(DatasetHome,{datasets:[],documents:[],loading:true,onBrowse:()=>{},onChat:()=>{}}));
 assert.doesNotMatch(html,/Loading datasets|role="status"|No registered datasets yet/);
 assert.match(html,/aria-hidden="true"/);
 const partial=renderToStaticMarkup(React.createElement(DatasetHome,{datasets:[{id:'dataset',name:'Dataset arriving first'}],documents:[],loading:true,onBrowse:()=>{},onChat:()=>{}}));
 assert.doesNotMatch(partial,/No documents|0 ready/);
 const empty=renderToStaticMarkup(React.createElement(DatasetHome,{datasets:[],documents:[],loading:false,onBrowse:()=>{},onChat:()=>{}}));
 assert.match(empty,/No registered datasets yet/);
});

test('extraction uses the shared horizontal workflow and real completed-stage progress',()=>{
 const stages={prepare:{status:'completed'},generate:{status:'running'},validate:{status:'blocked'},ready:{status:'blocked'}};
 const html=renderToStaticMarkup(React.createElement(JobProgress,{job:{kind:'extract',status:'running',progress:80,workflow:{current:'generate',stages}}}));
 assert.match(html,/aria-label="Extraction workflow"/);assert.match(html,/workflow-stages batch-stages/);assert.match(html,/aria-valuenow="25"/);assert.match(html,/stage-running/);assert.match(html,/Prepare sources/);assert.match(html,/Validate fields/);assert.doesNotMatch(html,/job-stage-list/);
 const failed=renderToStaticMarkup(React.createElement(JobProgress,{job:{kind:'extract',status:'failed',error:'Model unavailable',workflow:{current:'generate',stages:{...stages,generate:{status:'failed'}}}}}));
 assert.match(failed,/Needs attention/);assert.match(failed,/stage-failed/);assert.match(failed,/Model unavailable/);assert.match(failed,/aria-valuenow="25"/);
 const done=renderToStaticMarkup(React.createElement(JobProgress,{job:{kind:'extract',status:'completed',workflow:{stages:Object.fromEntries(Object.keys(stages).map(name=>[name,{status:'completed'}]))}}}));
 assert.match(done,/aria-valuenow="100"/);assert.match(done,/Your result is ready to review/);
 const legacy=renderToStaticMarkup(React.createElement(JobProgress,{job:{kind:'extract',status:'running'}}));assert.match(legacy,/Stage details are unavailable/);assert.match(legacy,/aria-valuenow="0"/);
});
const {WorkflowStepper}=load(path.resolve(__dirname,'../../ags_frontend/app/workflow-stepper.tsx'));
const {BatchProgress}=load(path.resolve(__dirname,'../../ags_frontend/app/batch-progress.tsx'));
test('particles feed only the active stage; Knowledge to Chat waits until Knowledge finishes',()=>{
 const steps=['Document','Knowledge','AI Chat'].map((label,n)=>({id:String(n),label,status:n===0?'completed':n===1?'running':'pending'}));
 const html=renderToStaticMarkup(React.createElement(WorkflowStepper,{steps}));
 assert.equal((html.match(/data-connection="flowing"/g)||[]).length,1);
 assert.equal((html.match(/data-connection="pending"/g)||[]).length,1);
 assert.equal((html.match(/aria-current="step"/g)||[]).length,1);
 steps[1].status='completed';steps[2].status='running';
 const chat=renderToStaticMarkup(React.createElement(WorkflowStepper,{steps}));
 assert.equal((chat.match(/data-connection="complete"/g)||[]).length,1);
 assert.equal((chat.match(/data-connection="flowing"/g)||[]).length,1);
 steps[2].status='failed';
 assert.doesNotMatch(renderToStaticMarkup(React.createElement(WorkflowStepper,{steps})),/connector-flowing|aria-current/);
 steps[2].status='completed';
 const complete=renderToStaticMarkup(React.createElement(WorkflowStepper,{steps}));
 assert.equal((complete.match(/data-connection="complete"/g)||[]).length,2);
 assert.equal((complete.match(/stage-completed/g)||[]).length,3);
 assert.doesNotMatch(complete,/connector-flowing|stage-running/);
});
test('document journey uses real reading, knowledge and chat-readiness states',()=>{
 const item={id:'doc',name:'evidence.txt',status:'submitted',document:{status:'processing'},processing:true,job:{status:'running',workflow:{current:'index',stages:{extract:{status:'completed'},index:{status:'running'},ready:{status:'blocked'}}}}};
 const render=()=>renderToStaticMarkup(React.createElement(BatchProgress,{items:[item],compact:true}));
 const active=render();assert.match(active,/>Document</);assert.match(active,/>Knowledge</);assert.match(active,/>AI Chat</);
 assert.equal((active.match(/stage-running/g)||[]).length,1);
 assert.equal((active.match(/connector-flowing/g)||[]).length,1);
 item.job.status='failed';item.processing=false;item.failed=true;item.job.workflow.stages.index.status='failed';
 const failed=render();assert.match(failed,/stage-failed/);assert.doesNotMatch(failed,/connector-flowing|stage-running/);
 item.ready=true;item.failed=false;item.job.status='completed';
 const ready=render();assert.equal((ready.match(/stage-completed/g)||[]).length,3);assert.match(ready,/All documents are ready/);
});
