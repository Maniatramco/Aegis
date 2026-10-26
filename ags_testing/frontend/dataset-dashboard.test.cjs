const {test}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),Module=require('node:module'),ts=require('typescript');
const filename=path.resolve(__dirname,'../../ags_frontend/app/dataset-dashboard.tsx'),compiled=new Module(filename,module);compiled.filename=filename;compiled.paths=module.paths;
const scopeFile=path.resolve(__dirname,'../../ags_frontend/app/dataset-knowledge-scope.ts'),scopeModule=new Module(scopeFile,module);scopeModule.filename=scopeFile;scopeModule.paths=module.paths;scopeModule._compile(ts.transpileModule(fs.readFileSync(scopeFile,'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText,scopeFile);
let hooks=[],cursor=0;
const original=compiled.require.bind(compiled);
compiled.require=id=>id==='./needs-attention'?{openAttention(){}}:id==='./dataset-knowledge-scope'?scopeModule.exports:id==='react'?{useState(initial){const slot=cursor++;if(!(slot in hooks))hooks[slot]=initial;return [hooks[slot],value=>{hooks[slot]=typeof value==='function'?value(hooks[slot]):value;}];}}:id.endsWith('.css')?{}:id==='./dataset-knowledge-picker'?{DatasetKnowledgePicker:props=>({type:'picker',props})}:id==='lucide-react'||id==='./agent-logo'?new Proxy({},{get:()=>()=>null}):original(id);
compiled._compile(ts.transpileModule(fs.readFileSync(filename,'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022,jsx:ts.JsxEmit.ReactJSX}}).outputText,filename);
const {DatasetDashboard,datasetDocuments,datasetReadiness}=compiled.exports;
const datasets=[{id:'a',name:'Invoices'},{id:'b',name:'Policies'}],documents=[{id:'one',parent_id:'a',name:'invoice.txt',status:'ready'},{id:'two',dataset_id:'b',name:'policy.txt',status:'ready'},{id:'stale',kb_id:'a',name:'old.txt',status:'ready',requires_reindex:true}];
const all=node=>!node||typeof node!=='object'?[]:Array.isArray(node)?node.flatMap(all):typeof node.type==='function'?all(node.type(node.props)):[node,...all(node.props?.children)];
const text=node=>!node?'':typeof node==='string'?node:Array.isArray(node)?node.map(text).join(''):text(node.props?.children);
function mount(values={}){const state=[],selected=[],agents=[],destinations=[],reviews=[];let root;const props={username:'tester',datasets,documents,loading:false,search:'',onClearSearch(){},onBrowse(){},canManage:false,selectedId:'',onSelect:id=>{selected.push(id);props.selectedId=id;},onNavigate:path=>destinations.push(path),onReview:id=>reviews.push(id),renderAgent:(id,onBusy,sourceScope,onSourceChange,knowledgeScope,options)=>{agents.push({id,onBusy,sourceScope,onSourceChange,knowledgeScope,options});return null;},guide:null,...values};
 const render=()=>{hooks=state;cursor=0;agents.length=0;root=DatasetDashboard(props);};render();return {render,get nodes(){return all(root);},selected,agents,destinations,reviews};}
function find(v,label){return v.nodes.find(n=>n.props?.['aria-label']===label);}
function mountChat(values={}){const v=mount(values);v.nodes.find(n=>n.type==='button'&&text(n)==='Open chat').props.onClick();v.render();return v;}
test('source summaries keep dataset boundaries and do not count stale indexes as ready',()=>{
 assert.deepEqual(datasetDocuments(documents,'a').map(d=>d.id),['one','stale']);
 assert.deepEqual(datasetReadiness(datasets[0],datasetDocuments(documents,'a')),{ready:1,label:'1 need reindex',state:'pending'});
 assert.equal(datasetReadiness({active:false},[]).label,'Inactive');
});
test('notebook exposes only selected dataset sources',()=>{
 const v=mountChat({selectedId:'a'});assert.deepEqual(v.agents.map(a=>a.id),['a']);
 const sources=v.nodes.find(n=>n.props?.className==='dashboard-source-list');assert.match(text(sources),/invoice.txt/);assert.doesNotMatch(text(sources),/policy.txt/);
 assert.equal(find(v,'Include source old.txt').props.disabled,true);
 find(v,'Ask Aegis about Policies').props.onClick();v.render();assert.deepEqual(v.agents.map(a=>a.id),['b']);
});
test('source deselection remains explicit and never becomes the dataset-wide scope',()=>{
 const v=mountChat({selectedId:'a',documents:documents.filter(d=>d.id!=='stale')});assert.equal(v.agents[0].sourceScope,null);
 find(v,'Include source invoice.txt').props.onChange();v.render();assert.deepEqual(v.agents[0].sourceScope,[]);
 find(v,'Select all indexed sources').props.onChange();v.render();assert.equal(v.agents[0].sourceScope,null);
});
test('Sources collapses while the expanded Agent remains available without Studio',()=>{
 const v=mount({selectedId:'a'});find(v,'Collapse sources').props.onClick();v.render();assert.equal(find(v,'Expand sources').props['aria-expanded'],false);assert.equal(v.nodes.find(n=>n.props?.id==='notebook-source-content').props.hidden,true);
 assert.ok(v.nodes.some(n=>n.props?.['aria-label']==='Dataset knowledge workspace chat'));assert.equal(v.nodes.some(n=>n.props?.['aria-label']==='Aegis Studio'),false);
 find(v,'Expand sources').props.onClick();v.render();assert.equal(v.nodes.find(n=>n.props?.id==='notebook-source-content').props.hidden,false);
});
test('workspace chat starts from authorized datasets; active work blocks scope switching',()=>{
 const workspace=mountChat();assert.deepEqual(workspace.agents[0].knowledgeScope.datasetIds,['a','b']);const v=mountChat({selectedId:'a'});v.agents[0].onBusy(true);v.render();assert.equal(find(v,'Ask Aegis about Policies').props.disabled,true);assert.equal(find(v,'Include source invoice.txt').props.disabled,true);
 const inactive=mount({datasets:[{id:'a',name:'Inactive',active:false}],selectedId:'a'});assert.equal(inactive.agents.length,0);assert.ok(inactive.nodes.some(n=>n.type==='h3'&&text(n)==='This dataset is inactive'));
 workspace.render();workspace.agents[0].onBusy(true);workspace.render();assert.equal(find(workspace,'Chat with all accessible dataset knowledge').props.disabled,true);
 assert.equal(find(v,'Ask Aegis about Invoices').props.disabled,true);
});

test('Dashboard omits onboarding while existing-source selection and browsing remain available',()=>{
 const calls=[];const v=mount({canManage:true,selectedId:'a',onBrowse:()=>calls.push('datasets')});
 assert.equal(v.nodes.some(n=>n.type==='button'&&text(n)==='Onboard dataset'),false);
 v.nodes.find(n=>n.type==='button'&&text(n)==='Add Dataset Knowledge').props.onClick();v.render();assert.ok(v.nodes.some(n=>n.type==='picker'));assert.deepEqual(calls,[]);
 const member=mount({canManage:false,onBrowse:()=>calls.push('browse')});
 member.nodes.find(n=>n.type==='button'&&text(n)==='Browse datasets').props.onClick();assert.equal(calls.at(-1),'browse');
});

test('including available knowledge opens a bounded cross-dataset scope',()=>{
 const v=mount({selectedId:'a'});v.nodes.find(n=>n.type==='button'&&text(n)==='Add Dataset Knowledge').props.onClick();v.render();
 const picker=v.nodes.find(n=>n.type==='picker');picker.props.onInclude({datasetIds:['a','b'],documentIds:['one','two']});v.render();
 assert.equal(v.selected.at(-1),'');assert.deepEqual(v.agents[0].knowledgeScope,{datasetIds:['a','b'],documentIds:['one','two']});
});

test('Dashboard does not initialize chat on first load, including a preselected dataset',()=>{
 for(const selectedId of ['', 'a']){const v=mount({selectedId});assert.equal(v.agents.length,0);v.render();assert.equal(v.agents.length,0);assert.ok(v.nodes.some(n=>n.type==='button'&&text(n)==='Open chat'));find(v,'Ask Aegis about Policies').props.onClick();v.render();assert.deepEqual(v.agents.map(a=>a.id),['b']);}
});


test('sticky knowledge action remains outside the scrollable source list and collapsed sources',()=>{
 const v=mount();const toolbar=v.nodes.find(n=>n.props?.['aria-label']==='Dataset knowledge actions');
 assert.ok(all(toolbar).some(n=>n.type==='button'&&text(n)==='Add Dataset Knowledge'));
 const content=v.nodes.find(n=>n.props?.id==='notebook-source-content');assert.equal(all(content).some(n=>n.type==='button'&&text(n)==='Add Dataset Knowledge'),false);
 find(v,'Collapse sources').props.onClick();v.render();assert.equal(v.nodes.find(n=>n.type==='button'&&text(n)==='Add Dataset Knowledge').props.disabled,false);
});

test('dataset checkboxes combine scopes and preserve individual file exclusions',()=>{
 const v=mountChat({selectedId:'a'});find(v,'Include source invoice.txt').props.onChange();v.render();
 find(v,'Include dataset Policies in knowledge').props.onChange();v.render();
 assert.deepEqual(v.agents[0].knowledgeScope,{datasetIds:['a','b'],documentIds:['two']});
 find(v,'Include dataset Invoices in knowledge').props.onChange();v.render();
 assert.deepEqual(v.agents[0].knowledgeScope,{datasetIds:['b'],documentIds:['two']});
 find(v,'Include dataset Policies in knowledge').props.onChange();v.render();
 assert.equal(v.agents.length,0);assert.ok(v.nodes.some(n=>n.type==='h3'&&text(n)==='Choose knowledge for this chat'));
});

test('dragging a dataset onto collapsed Sources adds only permitted ready knowledge without duplicates',()=>{
 const v=mountChat({selectedId:'a'}),type='application/x-aegis-dataset-ids';find(v,'Collapse sources').props.onClick();v.render();
 let payload;const tile=v.nodes.find(n=>n.props?.className==='dashboard-dataset-tile'&&all(n).some(c=>c.props?.['aria-label']==='Ask Aegis about Policies'));
 tile.props.onDragStart({preventDefault(){assert.fail('Valid dataset should drag');},dataTransfer:{setData:(mime,data)=>{assert.equal(mime,type);payload=data;}}});
 const drop=()=>find(v,'Dataset sources').props.onDrop({preventDefault(){},dataTransfer:{getData:mime=>mime===type?payload:''}});
 drop();v.render();assert.deepEqual(v.agents[0].knowledgeScope,{datasetIds:['a','b'],documentIds:['one','two']});
 assert.equal(v.nodes.find(n=>n.props?.id==='notebook-source-content').props.hidden,true);
 drop();v.render();assert.deepEqual(v.agents[0].knowledgeScope.documentIds,['one','two']);
 const before=v.agents[0].knowledgeScope;find(v,'Dataset sources').props.onDrop({preventDefault(){},dataTransfer:{getData:()=>JSON.stringify(['unauthorized'])}});v.render();assert.deepEqual(v.agents[0].knowledgeScope,before);
});

test('active chat disables multi-selection and ignores dropped datasets',()=>{
 const v=mountChat({selectedId:'a'});v.agents[0].onBusy(true);v.render();
 assert.equal(find(v,'Include dataset Policies in knowledge').props.disabled,true);
 assert.equal(v.nodes.find(n=>n.type==='button'&&text(n)==='Add Dataset Knowledge').props.disabled,true);
 find(v,'Dataset sources').props.onDrop({preventDefault(){},dataTransfer:{getData:()=>JSON.stringify(['b'])}});v.render();assert.equal(v.agents[0].id,'a');
});

test('including indexed knowledge keeps datasets and sources beside chat with exact file scope',()=>{
 const v=mount({selectedId:'a'});v.nodes.find(n=>n.type==='button'&&text(n)==='Add Dataset Knowledge').props.onClick();v.render();
 v.nodes.find(n=>n.type==='picker').props.onInclude({datasetIds:['a','b'],documentIds:['one','two','stale','foreign']});v.render();
 assert.equal(find(v,'Dataset dashboard').props['data-chat-focused'],false);
 assert.equal(find(v,'Authorized datasets').props.hidden,false);assert.equal(find(v,'Dataset sources').props.hidden,false);
 assert.deepEqual(v.agents[0].knowledgeScope,{datasetIds:['a','b'],documentIds:['one','two']});
 assert.equal(find(v,'Expand Dataset Knowledge Chat').props.title,'Expand Dataset Knowledge Chat');
 assert.equal(v.nodes.find(n=>n.type==='button'&&text(n)==='Add Dataset Knowledge').props.disabled,false);
});

test('only explicit expansion hides panels; restoring and peeking preserve active chat scope',()=>{
 const v=mount();find(v,'Ask Aegis about Policies').props.onClick();v.render();
 assert.equal(find(v,'Dataset dashboard').props['data-chat-focused'],false);
 const scope=v.agents[0].sourceScope,id=v.agents[0].id;
 find(v,'Expand Dataset Knowledge Chat').props.onClick();v.render();
 assert.equal(find(v,'Dataset dashboard').props['data-chat-focused'],true);
 assert.equal(find(v,'Authorized datasets').props.hidden,true);assert.equal(find(v,'Dataset sources').props.hidden,true);
 find(v,'Show sources').props.onClick();v.render();assert.equal(find(v,'Hide sources').props.title,'Hide sources');
 assert.equal(find(v,'Dataset sources').props.hidden,false);
 assert.equal(v.agents[0].sourceScope,scope);assert.equal(v.agents[0].id,id);
 v.agents[0].onBusy(true);v.render();find(v,'Restore Dashboard layout').props.onClick();v.render();
 assert.equal(find(v,'Authorized datasets').props.hidden,false);assert.equal(find(v,'Dataset sources').props.hidden,false);
 assert.equal(v.agents[0].id,id);assert.equal(v.agents[0].sourceScope,scope);
});

test('initial, inactive, unindexed and emptied selections keep the three-panel layout',()=>{
 const initial=mount();assert.equal(find(initial,'Dataset dashboard').props['data-chat-focused'],false);assert.equal(initial.agents.length,0);
 for(const values of [{documents:[]},{datasets:[{id:'a',name:'Invoices',active:false}],documents}]){
  const v=mount(values);find(v,'Ask Aegis about Invoices').props.onClick();v.render();assert.equal(find(v,'Dataset dashboard').props['data-chat-focused'],false);
 }
 const v=mount();find(v,'Ask Aegis about Policies').props.onClick();v.render();
 find(v,'Include dataset Policies in knowledge').props.onChange();v.render();
 assert.equal(find(v,'Dataset dashboard').props['data-chat-focused'],false);assert.equal(v.agents.length,0);
});

test('mobile panel switching keeps the existing chat and bounded sources mounted',()=>{
 const v=mountChat({selectedId:'a'});const before=v.agents[0];
 for(const name of ['Sources (2)','Datasets (2)','Knowledge Chat']){
  v.nodes.find(n=>n.type==='button'&&text(n)===name).props.onClick();v.render();
  assert.equal(v.agents[0].id,before.id);assert.deepEqual(v.agents[0].sourceScope,before.sourceScope);
 }
 assert.equal(find(v,'Dataset dashboard').props['data-mobile-panel'],'chat');
});

test('landing summary counts only loaded active knowledge and announces what was added',()=>{
 const {dashboardSummary,knowledgeAnnouncement}=compiled.exports;
 const docs=[...documents,{id:'run',parent_id:'b',name:'run.txt',status:'processing'},{id:'bad',parent_id:'b',name:'bad.txt',status:'failed'}];
 assert.deepEqual(dashboardSummary([...datasets,{id:'c',name:'Empty'},{id:'d',name:'Off',active:false}],docs),{datasets:3,indexed:2,attention:2,processing:1,empty:1});
 const added=knowledgeAnnouncement({datasetIds:['a','b'],documentIds:['one','two']},{datasetIds:['a'],documentIds:null},datasets,documents);
 assert.match(added.notice,/^Added Policies · 2 indexed sources/);assert.deepEqual(added.suggestions[0],'Summarize Policies');
});

test('asking from the landing opens a roomy chat with the question; chat asks earn room until restored',()=>{
 const v=mount();assert.equal(find(v,'Dataset dashboard').props['data-mode'],'landing');assert.equal(v.agents.length,0);
 v.nodes.find(n=>n.props?.id==='dashboard-ask-input').props.onChange({target:{value:'What changed?'}});v.render();
 v.nodes.find(n=>n.type==='form'&&n.props.className==='dashboard-ask').props.onSubmit({preventDefault(){}});v.render();
 assert.equal(find(v,'Dataset dashboard').props['data-chat-focused'],true);assert.equal(find(v,'Dataset dashboard').props['data-mode'],'workspace');
 const options=v.agents[0].options||{};assert.equal(options.initialQuestion.text,'What changed?');options.onInitialSent();v.render();assert.equal(v.agents[0].options.initialQuestion,null);
 find(v,'Restore Dashboard layout').props.onClick();v.render();v.agents[0].options.onAsk();v.render();
 assert.equal(find(v,'Dataset dashboard').props['data-chat-focused'],false);
 const w=mount();find(w,'Ask Aegis about Policies').props.onClick();w.render();assert.equal(find(w,'Dataset dashboard').props['data-chat-focused'],false);
 w.agents[0].options.onAsk();w.render();assert.equal(find(w,'Dataset dashboard').props['data-chat-focused'],true);
});

test('overview keeps the chat mounted and new knowledge routes to the connection flow',()=>{
 const calls=[];const v=mount({onAddNew:()=>calls.push('new')});find(v,'Ask Aegis about Policies').props.onClick();v.render();
 find(v,'Back to Dashboard overview').props.onClick();v.render();
 assert.equal(find(v,'Dataset dashboard').props['data-mode'],'landing');assert.deepEqual(v.agents.map(a=>a.id),['b']);assert.equal(find(v,'Dataset knowledge workspace chat').props.hidden,true);
 v.nodes.find(n=>n.type==='button'&&n.props.className==='dashboard-new-knowledge').props.onClick();
 find(v,'Add new knowledge from cloud storage').props.onClick();assert.deepEqual(calls,['new','new']);
});

test('documents handed over from Add knowledge open chat with exactly that indexed scope',()=>{
 const v=mount({startScope:{datasetIds:['b'],documentIds:['two','unknown']}});
 assert.equal(find(v,'Dataset dashboard').props['data-mode'],'workspace');
 assert.deepEqual(v.agents[0].knowledgeScope,{datasetIds:['b'],documentIds:['two']});
 assert.match(v.agents[0].options.notice,/^Added Policies · 1 indexed source/);
});

test('hero chips quick-remove and quick-add knowledge without leaving the overview',()=>{
 const v=mount({documents:documents.filter(d=>d.id!=='stale')});
 const chips=()=>v.nodes.filter(n=>n.props?.className==='dashboard-chip').map(n=>text(n));
 assert.deepEqual(chips(),['Invoices','Policies']);
 find(v,'Remove Policies from this chat').props.onClick();v.render();
 assert.deepEqual(chips(),['Invoices']);assert.equal(find(v,'Dataset dashboard').props['data-mode'],'landing');assert.equal(v.agents.length,0);
 v.nodes.find(n=>n.props?.className==='dashboard-chip-add').props.onClick();v.render();
 find(v,'Add Policies to this chat').props.onClick();v.render();assert.deepEqual(chips(),['Invoices','Policies']);
 find(v,'Remove Invoices from this chat').props.onClick();v.render();find(v,'Remove Policies from this chat').props.onClick();v.render();
 assert.ok(v.nodes.some(n=>n.props?.className==='dashboard-chip dashboard-chip-empty'));
 assert.equal(v.nodes.find(n=>n.type==='button'&&n.props.type==='submit').props.disabled,true);
 v.nodes.find(n=>n.type==='button'&&text(n)==='Use all knowledge').props.onClick();v.render();assert.deepEqual(chips(),['Invoices','Policies']);
 v.nodes.find(n=>n.type==='button'&&text(n)==='Open chat').props.onClick();v.render();assert.deepEqual(v.agents[0].knowledgeScope.datasetIds,['a','b']);
});
