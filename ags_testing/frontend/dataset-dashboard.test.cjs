const {test}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),Module=require('node:module'),ts=require('typescript');
const filename=path.resolve(__dirname,'../../ags_frontend/app/dataset-dashboard.tsx'),compiled=new Module(filename,module);compiled.filename=filename;compiled.paths=module.paths;
const scopeFile=path.resolve(__dirname,'../../ags_frontend/app/dataset-knowledge-scope.ts'),scopeModule=new Module(scopeFile,module);scopeModule.filename=scopeFile;scopeModule.paths=module.paths;scopeModule._compile(ts.transpileModule(fs.readFileSync(scopeFile,'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText,scopeFile);
let hooks=[],cursor=0;
const original=compiled.require.bind(compiled);
compiled.require=id=>id==='./dataset-knowledge-scope'?scopeModule.exports:id==='react'?{useState(initial){const slot=cursor++;if(!(slot in hooks))hooks[slot]=initial;return [hooks[slot],value=>{hooks[slot]=typeof value==='function'?value(hooks[slot]):value;}];}}:id.endsWith('.css')?{}:id==='./dataset-knowledge-picker'?{DatasetKnowledgePicker:props=>({type:'picker',props})}:id==='lucide-react'||id==='./agent-logo'?new Proxy({},{get:()=>()=>null}):original(id);
compiled._compile(ts.transpileModule(fs.readFileSync(filename,'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022,jsx:ts.JsxEmit.ReactJSX}}).outputText,filename);
const {DatasetDashboard,datasetDocuments,datasetReadiness,dashboardOverview}=compiled.exports;
const datasets=[{id:'a',name:'Invoices'},{id:'b',name:'Policies'}],documents=[{id:'one',parent_id:'a',name:'invoice.txt',status:'ready'},{id:'two',dataset_id:'b',name:'policy.txt',status:'ready'},{id:'stale',kb_id:'a',name:'old.txt',status:'ready',requires_reindex:true}];
const all=node=>!node||typeof node!=='object'?[]:Array.isArray(node)?node.flatMap(all):typeof node.type==='function'?all(node.type(node.props)):[node,...all(node.props?.children)];
const text=node=>!node?'':typeof node==='string'?node:Array.isArray(node)?node.map(text).join(''):text(node.props?.children);
function mount(values={}){const state=[],selected=[],agents=[],destinations=[],reviews=[];let root;const props={username:'tester',datasets,documents,loading:false,search:'',onClearSearch(){},onBrowse(){},canManage:false,selectedId:'',onSelect:id=>{selected.push(id);props.selectedId=id;},onNavigate:path=>destinations.push(path),onReview:id=>reviews.push(id),renderAgent:(id,onBusy,sourceScope,onSourceChange,knowledgeScope)=>{agents.push({id,onBusy,sourceScope,onSourceChange,knowledgeScope});return null;},guide:null,...values};
 const render=()=>{hooks=state;cursor=0;agents.length=0;root=DatasetDashboard(props);};render();return {render,get nodes(){return all(root);},selected,agents,destinations,reviews};}
function find(v,label){return v.nodes.find(n=>n.props?.['aria-label']===label);}
function mountChat(values={}){return mount(values);}
test('source summaries keep dataset boundaries and do not count stale indexes as ready',()=>{
 assert.deepEqual(datasetDocuments(documents,'a').map(d=>d.id),['one','stale']);
 assert.deepEqual(datasetReadiness(datasets[0],datasetDocuments(documents,'a')),{ready:1,label:'1 need reindex',state:'pending'});
 assert.equal(datasetReadiness({active:false},[]).label,'Inactive');
});
test('overview counts only accessible active dataset documents, with stale and failed sources counted once',()=>{
 const sets=[...datasets,{id:'inactive',active:false}];
 const docs=[...documents,{id:'bad',dataset_id:'a',status:'failed',requires_reindex:true},{id:'cancel',dataset_id:'a',status:'cancelled'},{id:'working',dataset_id:'b',status:'processing'},{id:'private',dataset_id:'unassigned',status:'ready'},{id:'archived',dataset_id:'inactive',status:'ready'}];
 assert.deepEqual(dashboardOverview(sets,docs),{active:2,indexed:2,attention:3,processing:1});
 assert.deepEqual(dashboardOverview([],docs),{active:0,indexed:0,attention:0,processing:0});
});
test('chat is mounted by default and compact context switching preserves its scope',()=>{
 const v=mount();assert.equal(find(v,'Dataset dashboard').props['data-mobile-panel'],'chat');assert.equal(v.agents.length,1);
 find(v,'Ask Aegis about Invoices').props.onClick();v.render();const scope=v.agents[0].sourceScope;
 for(const panel of ['Datasets (2)','Sources (2)','Knowledge Chat']){v.nodes.find(n=>n.type==='button'&&text(n)===panel).props.onClick();v.render();assert.equal(v.agents[0].id,'a');assert.deepEqual(v.agents[0].sourceScope,scope);}
});
test('loading and failed reads do not display false zero metrics or assignment instructions',()=>{
 for(const values of [{loading:true},{loadError:true}]){const v=mount({...values,datasets:[],documents:[]});const metrics=find(v,'Active dataset overview');assert.equal(all(metrics).filter(n=>n.type==='dd').some(n=>n.props.children===0),false);}
 const v=mount({loadError:true,datasets:[],documents:[]});assert.match(text(v.nodes),/Datasets could not be loaded/);assert.doesNotMatch(text(v.nodes),/No datasets assigned/);
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

test('Dashboard opens its read-only chat surface immediately for available authorized knowledge',()=>{
 for(const selectedId of ['', 'a']){const v=mount({selectedId});assert.equal(v.agents.length,1);assert.equal(find(v,'Dataset dashboard').props['data-mobile-panel'],'chat');find(v,'Ask Aegis about Policies').props.onClick();v.render();assert.deepEqual(v.agents.map(a=>a.id),['b']);}
 const empty=mount({datasets:[],documents:[]});assert.equal(empty.agents.length,0);
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
 const initial=mount();assert.equal(find(initial,'Dataset dashboard').props['data-chat-focused'],false);assert.equal(initial.agents.length,1);
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
