const {actionButton,expandActions}=require('./support/action-button.cjs');
const {test}=require('node:test');const assert=require('node:assert/strict');
const fs=require('node:fs');const path=require('node:path');const Module=require('node:module');const ts=require('typescript');
const draftFile=path.resolve(__dirname,'../app/onboarding-draft.ts');const draftModule=new Module(draftFile,module);draftModule.paths=module.paths;draftModule._compile(ts.transpileModule(fs.readFileSync(draftFile,'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText,draftFile);const draft=draftModule.exports;
function view(api,initialStorage=new Map(),full=false,extra={}){
 global.sessionStorage={getItem:k=>initialStorage.get(k)??null,setItem:(k,v)=>initialStorage.set(k,v),removeItem:k=>initialStorage.delete(k)};
 let cursor=0,root;const hooks=[],effects=[],calls=[];let ready=0;const busy=[];
 const react={useState(init){const i=cursor++;if(!(i in hooks))hooks[i]=typeof init==='function'?init():init;return [hooks[i],v=>{hooks[i]=typeof v==='function'?v(hooks[i]):v;}];},useRef(init){const i=cursor++;return hooks[i]||=( {current:init});},useEffect(fn){effects.push(fn);}};
 const filename=path.resolve(__dirname,'../app/agent-onboarding.tsx');const mod=new Module(filename,module);mod.filename=filename;mod.paths=module.paths;
 const base=mod.require.bind(mod);const empty=new Proxy({},{get:()=>()=>null});mod.require=id=>id==='./action-button'?actionButton:id==='react'?react:id==='./onboarding-draft'?draft:id==='./agent-consent'?{useAgentConsent:()=>({popup:null,request:async()=>({required:false})})}:id==='lucide-react'||id==='./workflow-stepper'?empty:id.endsWith('.css')?{}:base(id);
 mod._compile(ts.transpileModule(fs.readFileSync(filename,'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022,jsx:ts.JsxEmit.ReactJSX}}).outputText,filename);
 const models=[{id:'emb',name:'Embeddings',provider_model:'embed',provider:'ollama',enabled:true,credential_configured:true,capabilities:['embedding']},{id:'chat',name:'Chat and extract',provider_model:'chat',provider:'ollama',enabled:true,credential_configured:true,capabilities:['chat','extraction']}];
 const props={api:async(...args)=>{calls.push(args);return api(...args);},models,storageKey:'setup',proposal:{name:'QA dataset',process_documents:full},onBusy:b=>busy.push(b),onReady:()=>ready++,onUse:()=>{},...extra};
 const nodes=n=>!n||typeof n!=='object'?[]:Array.isArray(n)?n.flatMap(nodes):[n,...nodes(n.props?.children)];
 function render(){cursor=0;effects.length=0;root=expandActions(mod.exports.AgentOnboarding(props));}
 render();effects[0]();render();if(!full){nodes(root).find(n=>n.props?.['aria-label']==='Upload documents and run extraction')?.props.onChange({target:{checked:false}});render();}return {render,runUpdateEffects:()=>effects.slice(1).forEach(fn=>fn()),calls,storage:initialStorage,find:(key,v)=>nodes(root).find(n=>n.props?.[key]===v),button:()=>nodes(root).find(n=>n.type==='button'),get ready(){return ready;},busy};
}
const flush=()=>new Promise(r=>setImmediate(r));
const settle=async(done)=>{const deadline=Date.now()+2000;while(!done()&&Date.now()<deadline)await new Promise(r=>setTimeout(r,5));assert.ok(done(),'asynchronous onboarding settled');};
test('confirmation is required; browser observes worker progress without advancing stages and ignores duplicate clicks',async()=>{
 let polls=0;const v=view(async(path,method,body)=>path==='/agent-v2/onboarding'?{id:'w',status:'pending',steps:[],...body}:{id:'w',status:(++polls,'completed'),dataset_id:'dataset',steps:[]});
 assert.equal(v.calls.length,0);assert.equal(v.button().props.disabled,false);
 v.button().props.onClick();v.button().props.onClick();await flush();v.render();
 assert.equal(v.calls.filter(c=>c[0]==='/agent-v2/onboarding').length,1);assert.equal(polls,1);assert.equal(v.ready,1);assert.ok(!v.calls.some(c=>c[0].endsWith('/advance')));
 assert.equal(v.calls[0][2].embedding_model_id,'emb');assert.equal(v.calls[0][2].default_chat_model_id,'chat');assert.equal(v.calls[0][2].default_extraction_model_id,'chat');
 assert.equal(v.storage.get('setup'),'w');assert.deepEqual(v.busy,[true,false]);
});
test('a restored failed setup retries its existing workflow without another dataset proposal',async()=>{
 const saved={id:'w',status:'failed',name:'Saved',description:'',embedding_model_id:'emb',default_chat_model_id:'chat',default_extraction_model_id:'chat',dataset_id:'dataset',steps:[],error:'Temporary failure'};
 const v=view(async(path,method)=>method==='GET'?saved:{...saved,status:'completed',error:''},new Map([['setup','w']]));
 await flush();v.render();assert.equal(v.find('aria-label','Onboarding dataset name'),undefined);
 assert.equal(v.button().props.children,'Retry onboarding workflow');v.button().props.onClick();await flush();v.render();
 assert.equal(v.calls.filter(c=>c[1]==='POST').length,1);assert.equal(v.calls.at(-1)[0],'/agent-v2/onboarding/w/advance');assert.equal(v.ready,1);
});
test('unknown create outcome retains the same confirmed request across reload, validation rejection permits correction',async()=>{
 let body;const storage=new Map();const v=view(async(path,method,value)=>{body=value;throw new Error('Connection interrupted');},storage);
 v.button().props.onClick();await flush();v.render();assert.ok(storage.get('setup-request'));
 const resumed=view(async(path,method,value)=>path==='/agent-v2/onboarding'?{...value,id:'w',status:'pending',steps:[]}:{id:'w',status:'completed',dataset_id:'d',steps:[]},storage);
 resumed.button().props.onClick();await flush();assert.deepEqual(resumed.calls[0][2],body);
 const rejected=view(async()=>{throw Object.assign(new Error('Invalid model'),{status:422});});rejected.button().props.onClick();await flush();rejected.render();
 assert.equal(rejected.storage.has('setup-request'),false);assert.equal(rejected.find('aria-label','Onboarding dataset name').props.disabled,false);
});

test('full onboarding confirms document hashes and prompt together, stages files once and advances to review',async()=>{
 let current,polls=0;const v=view(async(path,method,body)=>{
  if(path==='/agent-v2/onboarding')return current={...body,id:'full',status:'pending',steps:[]};
  if(path.endsWith('/files')){assert.ok(body instanceof FormData);assert.equal(body.getAll('files').length,2);return current={...current,files_saved:true};}
  assert.equal(method,'GET');polls++;return current={...current,status:'completed',dataset_id:'dataset',results:[{id:'result',name:'Invoice'}]};
 },new Map(),true);
 assert.equal(v.button().props.disabled,true);
 v.find('aria-label','Onboarding documents').props.onChange({target:{files:[new File(['Owner Alice.'],'one.txt'),new File(['Owner Bob.'],'two.txt')]}});
 v.find('aria-label','Onboarding prompt schema').props.onChange({target:{value:JSON.stringify({type:'object',properties:{owner:{type:'string'}},required:['owner'],additionalProperties:false})}});
 v.render();assert.equal(v.button().props.disabled,false);v.button().props.onClick();
 await settle(()=>v.ready===1);v.render();
 const body=v.calls[0][2];assert.equal(body.processing.documents.length,2);assert.match(body.processing.documents[0].sha256,/^[a-f0-9]{64}$/);
 assert.equal(body.processing.schema.properties.owner.type,'string');assert.equal(v.calls.filter(c=>c[0].endsWith('/files')).length,1);assert.equal(polls,1);assert.equal(v.ready,1);
});

test('a restored staged workflow resumes without browser files or another upload',async()=>{
 const saved={id:'full',status:'waiting',name:'Saved',description:'',embedding_model_id:'emb',default_chat_model_id:'chat',default_extraction_model_id:'chat',dataset_id:'dataset',files_saved:true,processing:{prompt_name:'owner.json',documents:[{name:'one.txt'}],extraction_mode:'independent'},steps:[]};
 let reads=0;const v=view(async(path,method)=>{assert.equal(method,'GET');return ++reads===1?saved:{...saved,status:'completed'};},new Map([['setup','full']]),true);
 await flush();v.render();assert.equal(v.find('aria-label','Reattach onboarding documents'),undefined);
 assert.equal(v.button().props.disabled,false);v.button().props.onClick();await flush();assert.equal(v.calls.filter(c=>c[0].endsWith('/files')).length,0);assert.equal(v.ready,1);
});

test('a rejected document transfer retains the accepted workflow and confirmed request for correction',async()=>{
 const v=view(async(path,method,body)=>{
  if(path==='/agent-v2/onboarding')return {...body,id:'full',status:'pending',steps:[]};
  throw Object.assign(new Error('Reattach original files'),{status:422});
 },new Map(),true);
 v.find('aria-label','Onboarding documents').props.onChange({target:{files:[new File(['Owner Alice.'],'one.txt')]}});
 v.find('aria-label','Onboarding prompt schema').props.onChange({target:{value:'{"type":"object","properties":{},"required":[],"additionalProperties":false}'}});
 v.render();v.button().props.onClick();await settle(()=>v.busy.at(-1)===false);v.render();
 assert.equal(v.storage.get('setup'),'full');assert.ok(v.storage.get('setup-request'));assert.ok(v.find('aria-label','Reattach onboarding documents'));
});

test('New dataset maps defaults without offering processing and reports the completed dataset once',async()=>{
 const completed=[];
 const dataset={id:'new-dataset',name:'QA dataset',version:2,models_complete:true};
 const v=view(async(path,method,body)=>path==='/agent-v2/onboarding'?{...body,id:'w',status:'pending',steps:[]}:{id:'w',status:'completed',dataset_id:dataset.id,dataset,steps:[]},new Map(),true,{datasetOnly:true,onCompleted:d=>completed.push(d)});
 assert.equal(v.find('aria-label','Upload documents and run extraction'),undefined);
 assert.equal(v.find('aria-label','Onboarding documents'),undefined);
 assert.equal(v.find('aria-label','Onboarding embedding model').props.value,'emb');
 assert.equal(v.find('aria-label','Onboarding chat model').props.value,'chat');
 assert.equal(v.find('aria-label','Onboarding extraction model').props.value,'chat');
 assert.equal(v.button().props.children,'Create dataset');
 v.button().props.onClick();await flush();v.render();v.runUpdateEffects();v.render();v.runUpdateEffects();
 assert.equal(v.calls[0][2].processing,null);
 assert.equal(v.calls.filter(c=>c[1]==='POST').length,1);
 assert.deepEqual(completed,[dataset]);
});
