const {test}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),Module=require('node:module'),ts=require('typescript');
function compile(name,overrides={}){const filename=path.resolve(__dirname,'../../ags_frontend/app',name),mod=new Module(filename,module);mod.filename=filename;mod.paths=module.paths;const original=mod.require.bind(mod);mod.require=id=>Object.hasOwn(overrides,id)?overrides[id]:id.endsWith('.css')?{}:id.startsWith('.')?compile(id.slice(2)+'.ts',overrides):original(id);mod._compile(ts.transpileModule(fs.readFileSync(filename,'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022,jsx:ts.JsxEmit.ReactJSX}}).outputText,filename);return mod.exports;}
const catalog={datasets:[{id:'a',name:'A',default_chat_model_id:'chat',models:[{id:'chat',enabled:true,capabilities:['chat']}]}],documents:[{id:'file',parent_id:'a',status:'ready'}],models:[{id:'chat',name:'Mapped Chat',enabled:true,capabilities:['chat']}]};
function mount({scope={datasetIds:['a'],documentIds:['file']},storage=new Map(),handler,streamHandler}={}){
 global.sessionStorage={getItem:key=>storage.get(key)??null,setItem:(key,value)=>storage.set(key,value),removeItem:key=>storage.delete(key)};
 let cursor=0,root;const hooks=[],effects=[],calls=[],streams=[];
 const react={useState(initial){const slot=cursor++;if(!(slot in hooks))hooks[slot]=initial;return [hooks[slot],value=>hooks[slot]=typeof value==='function'?value(hooks[slot]):value];},useRef(initial){const slot=cursor++;if(!(slot in hooks))hooks[slot]={current:initial};return hooks[slot];},useEffect(fn){effects.push(fn);}};
 const empty=new Proxy({},{get:()=>()=>null});const {DatasetKnowledgeChat,knowledgeScopeKey}=compile('dataset-knowledge-chat.tsx',{'react':react,'lucide-react':empty,'./agent-logo':empty,'./agent-v2-chat':empty,'./dataset-chat-status':empty});
 const props={scope,username:'tester',api:async(...args)=>{calls.push(args);return handler?handler(...args):catalog;},stream:async(...args)=>{streams.push(args);return streamHandler?streamHandler(...args):new Promise(()=>{});}};
 const nodes=node=>!node||typeof node!=='object'?[]:Array.isArray(node)?node.flatMap(nodes):[node,...nodes(node.props?.children)];
 const render=()=>{cursor=0;effects.length=0;root=DatasetKnowledgeChat(props);};render();
 return {render,effects,calls,streams,storage,knowledgeScopeKey,nodes:()=>nodes(root),find:label=>nodes(root).find(node=>node.props?.['aria-label']===label),effect:part=>effects.find(fn=>String(fn).includes(part))()};
}
const flush=()=>new Promise(resolve=>setImmediate(resolve));
async function ready(v){v.effect('/dataset-chat/catalog');v.effect('setRestoring(true)');await flush();v.render();}
function ask(v,text='Who is the owner?'){v.find('Message Dataset Knowledge Chat').props.onChange({target:{value:text}});v.render();v.find('Send dataset chat question').props.onClick();}

test('dataset chat uses its own endpoint and exact files without Agent controls',async()=>{
 const v=mount();await ready(v);ask(v);await flush();assert.equal(v.streams.length,1);assert.equal(v.streams[0][0],'/dataset-chat/reply');assert.deepEqual(v.streams[0][1].document_ids,['file']);assert.deepEqual(v.streams[0][1].dataset_ids,['a']);assert.equal(v.calls.some(call=>call[0].startsWith('/agent-v2')),false);assert.equal(v.find('Agent dataset'),undefined);assert.equal(v.nodes().some(node=>node.type==='input'&&node.props.type==='file'),false);
});
test('empty, foreign and stale file scopes never become all files',async()=>{
 for(const documentIds of [[],['foreign']]){const v=mount({scope:{datasetIds:['a'],documentIds}});await ready(v);ask(v);await flush();v.render();assert.equal(v.streams.length,0);assert.ok(v.nodes().some(node=>node.props?.role==='alert'));}
});
test('opening chat never generates an overview; only explicit Send starts a model request',async()=>{
 const storage=new Map([['aegis-agent-v2:tester','existing-agent-state']]),v=mount({storage});await ready(v);
 for(const effect of v.effects)effect();await flush();v.render();
 assert.equal(v.streams.length,0);assert.equal(storage.get('aegis-agent-v2:tester'),'existing-agent-state');
 assert.equal([...storage.keys()].some(key=>key.endsWith('-overview')),false);
 ask(v,'Summarize the key themes');await flush();assert.equal(v.streams.length,1);assert.equal(v.streams[0][1].summary,false);
});

test('separate history rejects a thread with different file scope',async()=>{
 const v=mount({handler:async path=>path.endsWith('/catalog')?catalog:path==='/dataset-chat/conversations'?[{id:'foreign',dataset_ids:['a'],document_ids:['other']}]:assert.fail('A foreign thread must not be loaded')});await ready(v);v.find('Dataset chat history').props.onClick();await flush();v.render();assert.equal(v.nodes().filter(node=>node.type==='button').some(node=>node.props.key==='foreign'),false);assert.equal(v.calls.some(call=>call[0].startsWith('/conversations')),false);
});
test('finishing a streamed answer stores only the dataset-chat conversation',async()=>{
 const encoder=new TextEncoder(),v=mount({streamHandler:async()=>new Response(new ReadableStream({start(controller){controller.enqueue(encoder.encode('event: done\ndata: '+JSON.stringify({conversation_id:'dataset-thread',message:{text:'Alice owns it. [1]',status:'completed',citations:[]}})+'\n\n'));controller.close();}}))});await ready(v);ask(v);await flush();v.render();assert.ok([...v.storage.entries()].some(([key,value])=>key.startsWith('aegis-dataset-chat:')&&value==='dataset-thread'));assert.equal([...v.storage.keys()].some(key=>key.startsWith('aegis-agent-v2:')),false);
});
