const {test}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),Module=require('node:module'),ts=require('typescript');
const React=require('react'),{renderToStaticMarkup}=require('react-dom/server');
function load(name,overrides={}){
 const filename=path.resolve(__dirname,'../../ags_frontend/app',name),compiled=new Module(filename,module);compiled.filename=filename;compiled.paths=module.paths;
 const original=compiled.require.bind(compiled);compiled.require=id=>Object.hasOwn(overrides,id)?overrides[id]:id.endsWith('.css')?{}:id.startsWith('.')&&fs.existsSync(path.resolve(path.dirname(filename),id+'.ts'))?load(id+'.ts',overrides):original(id);
 compiled._compile(ts.transpileModule(fs.readFileSync(filename,'utf8'),{compilerOptions:{esModuleInterop:true,module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022,jsx:ts.JsxEmit.ReactJSX}}).outputText,filename);return compiled.exports;
}
const {runtimeConnections,modelConnectionSummary,connectionLocation}=load('runtime-connections.ts');
const services=runtimeConnections('http://private-user:private-password@api:8000/?token=private-token',{AEGIS_DEPLOYMENT_TARGET:'oci',AEGIS_API_LOCATION:'oci',AEGIS_WORKER_LOCATION:'oci',AEGIS_MODEL_LOCATION:'local',SECRET_KEY:'never-expose'});
const connections={files:{provider:'oci',name:'mk-aegis',region:'ap-mumbai-1'},database:{provider:'oci',name:'agsora'},knowledge:{provider:'oci',name:'Oracle vectors'},services};
function renderFooter({open=false,data=connections,unavailable=false,datasets,datasetId}={}){
 let index=0;
 const react={...React,useEffect(){},useState(initial){const current=index++;return [current===0?data:current===1?unavailable:current===2?open:current===4?'https://workspace.invalid':initial,()=>{}];}};
 const {ConnectionStatus}=load('connection-status.tsx',{react,'react-dom':{createPortal:children=>children}});
 const previous=global.document;
 try{
  global.document={body:{}};
  return renderToStaticMarkup(React.createElement(ConnectionStatus,{api:async()=>assert.fail('Rendering should not probe connections'),revision:0,datasets,datasetId}));
 }finally{if(previous===undefined)delete global.document;else global.document=previous;}
}
test('footer reports configured service locations and strips endpoint credentials',()=>{
 assert.equal(services.api.endpoint,'http://api:8000');assert.equal(services.web.provider,'oci');assert.equal(services.models.provider,'local');
 for(const secret of ['private-password','private-token','never-expose'])assert.ok(!JSON.stringify(services).includes(secret));
 assert.equal(runtimeConnections('https://different-host.example',{}).api.provider,'unknown');
 assert.equal(runtimeConnections('http://api:8000',{AEGIS_DEPLOYMENT_TARGET:'local'}).api.provider,'local');
});
test('collapsed footer shows Connections and base version without the expanded service list',()=>{
 const html=renderFooter();
 const release=require('../../ags_frontend/app/application-version.json');
 assert.match(html,/href="#About"/);assert.match(html,/Connections/);assert.ok(html.includes('v'+release.version));assert.match(html,/aria-expanded="false"/);
 assert.ok(!html.includes('Connection details'));assert.ok(!html.includes('mk-aegis'));assert.ok(!html.includes('agsora'));
 assert.equal((html.match(/<button/g)||[]).length,1);
});
test('expanded Connections preserves all seven services and their existing details',()=>{
 const html=renderFooter({open:true});
 assert.match(html,/aria-expanded="true"/);assert.match(html,/role="region" aria-label="Connection details"/);
 for(const label of ['Storage','Database','Vector DB','FastAPI','WebApp','Worker','AI models','OCI','Local','mk-aegis','agsora','Oracle vectors','ap-mumbai-1','https://workspace.invalid','http://api:8000'])assert.ok(html.includes(label),label);
 assert.equal((html.match(/<article /g)||[]).length,7);
 assert.ok(!html.includes('private-password'));assert.ok(!html.includes('private-token'));
});
test('connection popover keeps loading and unavailable results explicit',()=>{
 assert.match(renderFooter({open:true,data:null}),/Checking destinations/);
 assert.match(renderFooter({open:true,data:null,unavailable:true}),/Status unavailable/);
});
function interactiveFooter(){
 const saved={window:global.window,document:global.document,Node:global.Node};
 const listeners=new Map();
 class Element{contains(node){return node===this||node?.parent===this;}focus(){global.document.activeElement=this;}}
 const trigger=new Element(),popup=new Element();
 trigger.getBoundingClientRect=()=>({left:250,top:760});
 global.Node=Element;
 global.document={body:{},activeElement:null,visibilityState:'visible',addEventListener:(name,fn)=>listeners.set(name,fn),removeEventListener:(name)=>listeners.delete(name)};
 global.window={innerWidth:1100,innerHeight:800,location:{origin:'https://workspace.invalid'},setTimeout,clearTimeout,setInterval:()=>0,clearInterval(){},addEventListener(){},removeEventListener(){}};
 let cursor=0,root;const hooks=[],effects=[];
 const react={
  useState(initial){const i=cursor++;hooks[i]??={value:initial};return [hooks[i].value,value=>{hooks[i].value=typeof value==='function'?value(hooks[i].value):value;}];},
  useRef(initial){const i=cursor++;return hooks[i]??={current:initial};},
  useCallback(fn){const i=cursor++;return hooks[i]??=fn;},
  useId(){cursor++;return 'connections-test';},
  useEffect(fn,deps){const i=cursor++,old=hooks[i];if(!old||deps.some((value,index)=>!Object.is(value,old.deps[index]))){hooks[i]={deps,cleanup:old?.cleanup};effects.push(()=>{hooks[i].cleanup?.();hooks[i].cleanup=fn();});}}
 };
 const {ConnectionStatus}=load('connection-status.tsx',{react,'react-dom':{createPortal:children=>children}});
 const api=async path=>{assert.equal(path,'/storage/status');return connections;};
 const nodes=value=>!value||typeof value!=='object'?[]:Array.isArray(value)?value.flatMap(nodes):[value,...nodes(value.props?.children)];
 const render=()=>{
  cursor=0;root=ConnectionStatus({api,revision:0});
  for(const node of nodes(root)){if(node.type==='button'&&node.props.className==='connection-status-trigger')node.props.ref.current=trigger;if(node.props['aria-label']==='Connection details')node.props.ref.current=popup;}
  while(effects.length)effects.shift()();
 };
 return {render,all:()=>nodes(root),trigger:()=>nodes(root).find(node=>node.props?.className==='connection-status-trigger'),panel:()=>nodes(root).find(node=>node.props?.['aria-label']==='Connection details'),dispatch:(name,event)=>listeners.get(name)?.(event),outside:()=>new Element(),destroy(){for(const hook of hooks)hook?.cleanup?.();for(const [key,value] of Object.entries(saved)){if(value===undefined)delete global[key];else global[key]=value;}}};
}
test('hover opens Connections, crossing into the popover retains it, and leaving closes it',async()=>{
 const h=interactiveFooter();try{
  h.render();await Promise.resolve();h.render();assert.equal(h.panel(),undefined);
  h.trigger().props.onMouseEnter();h.render();assert.ok(h.panel());
  h.trigger().props.onMouseLeave();h.panel().props.onMouseEnter();await new Promise(resolve=>setTimeout(resolve,210));h.render();assert.ok(h.panel());
  h.panel().props.onMouseLeave();await new Promise(resolve=>setTimeout(resolve,210));h.render();assert.equal(h.panel(),undefined);
 }finally{h.destroy();}
});
test('Connections supports keyboard focus, Escape, click pinning and outside dismissal',async()=>{
 const h=interactiveFooter();try{
  h.render();await Promise.resolve();h.render();h.trigger().props.onFocus();h.render();assert.ok(h.panel());
  h.dispatch('keydown',{key:'Escape'});h.render();assert.equal(h.panel(),undefined);
  h.trigger().props.onClick();h.render();h.trigger().props.onMouseLeave();await new Promise(resolve=>setTimeout(resolve,210));h.render();assert.ok(h.panel());
  h.dispatch('pointerdown',{target:h.outside()});h.render();assert.equal(h.panel(),undefined);
  h.trigger().props.onFocus();h.render();h.trigger().props.onBlur({relatedTarget:h.outside()});h.render();assert.equal(h.panel(),undefined);
 }finally{h.destroy();}
});
test('Gemini dataset defaults override the old Local model-host hint and show GCP',()=>{
 const models=[{id:'chat',provider:'openai-compatible',provider_model:'gemini-flash',connection:{protocol:'openai-compatible',endpoint:'https://generativelanguage.googleapis.com/v1beta/openai'}},
  {id:'embed',provider_model:'gemini-embedding',connection:{protocol:'openai-compatible',endpoint:'https://generativelanguage.googleapis.com/v1beta/openai'}},
  {id:'local-unused',provider:'ollama',provider_model:'qwen',connection:{protocol:'ollama',endpoint:'http://localhost:11435'}}];
 const datasets=[{id:'gemini-dataset',default_chat_model_id:'chat',default_extraction_model_id:'chat',embedding_model_id:'embed',models}];
 const summary=modelConnectionSummary(datasets,'gemini-dataset');
 assert.equal(summary.provider,'gcp');assert.deepEqual(summary.locations,['gcp']);assert.equal(summary.name,'Google Gemini');
 assert.ok(!summary.detail.includes('qwen'));assert.match(summary.detail,/gemini-flash/);assert.match(summary.detail,/gemini-embedding/);
 const html=renderFooter({open:true,datasets,datasetId:'gemini-dataset'});
 assert.match(html,/Google Gemini/);assert.match(html,/>GCP</);assert.ok(!html.includes('Laptop models'));
});
test('mixed dataset model defaults report Local / GCP and respect scope and disabled mappings',()=>{
 const local={id:'local',provider:'ollama',provider_model:'qwen',connection:{protocol:'ollama',endpoint:'http://localhost:11435'}};
 const gemini={id:'gemini',provider_model:'gemini',connection:{protocol:'vertex',endpoint:'https://us-central1-aiplatform.googleapis.com',region:'us-central1'}};
 const datasets=[{id:'local-dataset',default_chat_model_id:'local',models:[local]},
  {id:'mixed-dataset',default_chat_model_id:'gemini',embedding_model_id:'local',models:[local,gemini]},
  {id:'inactive',active:false,models:[{id:'ignored',provider:'oci'}]}];
 assert.equal(modelConnectionSummary(datasets,'local-dataset').provider,'local');
 const mixed=modelConnectionSummary(datasets,'mixed-dataset');assert.equal(mixed.provider,'mixed');assert.deepEqual(mixed.locations,['local','gcp']);
 assert.match(renderFooter({open:true,datasets,datasetId:'mixed-dataset'}),/Local \/ GCP/);
 assert.deepEqual(modelConnectionSummary(datasets).locations,['local','gcp']);
 assert.equal(modelConnectionSummary([{models:[{...local,enabled:false},{...gemini,mapping_enabled:false}]}]).provider,'unknown');
 assert.equal(modelConnectionSummary(datasets,'not-accessible').provider,'unknown');
});
test('model location uses real provider metadata, sanitizes endpoint credentials and never guesses from a Gemini name',()=>{
 const summary=modelConnectionSummary([{models:[{provider_model:'gemini-name-through-a-proxy',connection:{protocol:'openai-compatible',endpoint:'https://user:DO-NOT-EXPOSE@proxy.example/v1?key=PRIVATE-TOKEN'}}]}]);
 assert.equal(summary.provider,'unknown');assert.equal(summary.endpoint,'https://proxy.example');
 assert.ok(!JSON.stringify(summary).includes('DO-NOT-EXPOSE'));assert.ok(!JSON.stringify(summary).includes('PRIVATE-TOKEN'));
 assert.equal(modelConnectionSummary([{models:[{connection:{protocol:'openai-compatible',endpoint:'https://generativelanguage.googleapis.com.example.org'}}]}]).provider,'unknown');
 assert.equal(connectionLocation('gcp'),'GCP');assert.equal(connectionLocation('constructor'),'Unknown');
 assert.equal(runtimeConnections('http://api:8000',{AEGIS_MODEL_LOCATION:'gcp'}).models.provider,'gcp');
});
