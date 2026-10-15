const {test}=require('node:test');const assert=require('node:assert/strict');const fs=require('node:fs');const path=require('node:path');const Module=require('node:module');const ts=require('typescript');
const catalog=[['ollama','Local · Ollama','ollama','http://127.0.0.1:11435','none'],['openai','OpenAI','openai-compatible','https://api.openai.com/v1','api_key'],['gemini','Google · Gemini API','openai-compatible','https://generativelanguage.googleapis.com/v1beta/openai','api_key'],['azure-openai','Azure · OpenAI v1','azure-openai','','api_key'],['bedrock','AWS · Bedrock','bedrock','https://bedrock-runtime.us-east-1.amazonaws.com','aws_keys'],['vertex','Google Cloud · Vertex AI','vertex','https://us-central1-aiplatform.googleapis.com','service_account'],['oci','Oracle Cloud · Generative AI','oci','https://inference.generativeai.us-chicago-1.oci.oraclecloud.com','oci_credentials'],['openai-compatible','Other · OpenAI-compatible API','openai-compatible','','api_key']].map(([id,name,protocol,endpoint,auth])=>({id,name,protocol,endpoint,region:({bedrock:'us-east-1',vertex:'us-central1',oci:'us-chicago-1'})[id]||'',auth_modes:[auth],categories:['chat','extraction','embedding']}));
const flush=()=>new Promise(resolve=>setImmediate(resolve));
async function screen({reject=false,badProbe=false,defaults={}}={}){
 let cursor=0,root;const hooks=[],effects=[],calls=[];
 const react={useState(initial){const i=cursor++;if(!(i in hooks))hooks[i]=typeof initial==='function'?initial():initial;return[hooks[i],v=>hooks[i]=typeof v==='function'?v(hooks[i]):v];},useEffect(fn){effects.push(fn);}};
 const compile=file=>{const m=new Module(file,module);m.filename=file;m.paths=module.paths;const base=m.require.bind(m);m.require=id=>id==='react'?react:id==='lucide-react'?new Proxy({},{get:()=>()=>null}):id==='./action-button'?{ActionButton:()=>null}:id.endsWith('.css')?{}:id==='./model-parameters'?compile(path.resolve(path.dirname(file),'model-parameters.ts')).exports:base(id);m._compile(ts.transpileModule(fs.readFileSync(file,'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022,jsx:ts.JsxEmit.ReactJSX}}).outputText,file);return m;};
 const mod=compile(path.resolve(__dirname,'../app/model-registration.tsx'));
 const nodes=n=>!n||typeof n!=='object'?[]:Array.isArray(n)?n.flatMap(nodes):[n,...nodes(n.props?.children)];
 const props={models:[],settings:{model_defaults:{timeout:60,context_limit:32768,embedding_context_limit:8192,max_output_tokens:4096,headroom_tokens:512,context_max:2097152,output_max:131072,timeout_min:5,timeout_max:1800,...defaults}},busy:false,onSaved:()=>{},onMapping:()=>{},run:async fn=>{try{await fn();}catch{}},api:async(...args)=>{calls.push(args);if(args[0]==='/model-providers'){if(reject)throw Error('offline');return catalog;}if(args[0]==='/model-registrations/test'){if(badProbe)throw Error('not tool capable');return {ok:true,elapsed_ms:10,agent_tool_call_validated:true};}return {id:'saved'};}};
 const render=()=>{cursor=0;root=mod.exports.ModelRegistration(props);};render();effects[0]();await flush();render();
 const field=id=>nodes(root).find(n=>n.props?.id===id);
 const button=text=>nodes(root).find(n=>n.props?.label===text||(n.type==='button'&&JSON.stringify(n.props.children).includes(text)));
 button('Register model').props.onClick();render();
 return {render,calls,field,button,all:()=>nodes(root),choose:id=>{field('registration-protocol').props.onChange({target:{value:id}});render();},submit:()=>nodes(root).find(n=>n.type==='form').props.onSubmit({preventDefault(){}})};
}
test('provider choices come from backend and initialize protocol, endpoint, region and authentication',async()=>{
 const s=await screen();assert.equal(s.calls[0][0],'/model-providers');
 for(const p of catalog){s.choose(p.id);assert.equal(s.field('registration-protocol').props.value,p.id);assert.equal(s.field('registration-endpoint').props.value,p.endpoint);assert.equal(s.field('registration-auth').props.value,p.auth_modes[0]);if(p.region)assert.equal(s.field('registration-region').props.value,p.region);}
});
test('changing provider clears the previous model ID and requires a new connection test',async()=>{
 const s=await screen();s.choose('gemini');s.field('registration-model').props.onChange({target:{value:'synthetic-model'}});s.render();s.choose('azure-openai');assert.equal(s.field('registration-model').props.value,'');assert.equal(s.button('Save Model').props.disabled,true);s.submit();await flush();assert.equal(s.calls.filter(c=>c[0]==='/model-registrations').length,0);
});
test('successful capability test permits saving; changing execution details invalidates it',async()=>{
 const s=await screen();s.button('Test Connection').props.onClick({currentTarget:{form:{reportValidity:()=>true}}});await flush();s.render();assert.equal(s.button('Save Model').props.disabled,false);s.submit();await flush();assert.equal(s.calls.filter(c=>c[0]==='/model-registrations').length,1);
 const t=await screen();t.button('Test Connection').props.onClick({currentTarget:{form:{reportValidity:()=>true}}});await flush();t.render();t.field('registration-model').props.onChange({target:{value:'different'}});t.render();assert.equal(t.button('Save Model').props.disabled,true);
});
test('failed provider catalog or failed model test keeps saving disabled',async()=>{
 const s=await screen({reject:true});assert.equal(s.field('registration-protocol').props.disabled,true);assert.ok(s.all().some(n=>n.props?.role==='alert'));
 const t=await screen({badProbe:true});t.button('Test Connection').props.onClick({currentTarget:{form:{reportValidity:()=>true}}});await flush();t.render();assert.equal(t.button('Save Model').props.disabled,true);
});


test('model form defaults follow backend configuration while category switches use embedding input defaults',async()=>{
 const s=await screen({defaults:{timeout:90,context_limit:65536,embedding_context_limit:16384,max_output_tokens:8192,headroom_tokens:1024}});
 assert.equal(s.field('registration-timeout').props.value,90);
 assert.equal(s.field('registration-context-limit').props.value,65536);
 assert.equal(s.field('registration-output-limit').props.value,8192);
 s.field('registration-category').props.onChange({target:{value:'embedding'}});s.render();
 assert.equal(s.field('registration-context-limit').props.value,16384);
});
