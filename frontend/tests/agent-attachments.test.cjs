const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');const path=require('node:path');const Module=require('node:module');const ts=require('typescript');
function compile(name,overrides={}){
 const filename=path.resolve(__dirname,'../app',name);const compiled=new Module(filename,module);compiled.filename=filename;compiled.paths=module.paths;
 const original=compiled.require.bind(compiled);
 compiled.require=id=>Object.hasOwn(overrides,id)?overrides[id]:original(id);
 compiled._compile(ts.transpileModule(fs.readFileSync(filename,'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022,jsx:ts.JsxEmit.ReactJSX}}).outputText,filename);
 return compiled.exports;
}
const helpers=compile('agent-attachments.ts');const {mergeAgentAttachments,isFileDrag}=helpers;
const file=(name,size=100,lastModified=1)=>({name,size,lastModified});
test('successive drops append attachments and deduplicate repeated files',()=>{
 const a=file('invoice.PDF'),b=file('notes.txt');
 const result=mergeAgentAttachments([a],[a,b,b]);assert.deepEqual(result,{files:[a,b],error:''});
 assert.equal(mergeAgentAttachments([a],[file(a.name,a.size,2)]).files.length,2);
});
test('invalid batches preserve earlier attachments without partially adding files',()=>{
 const existing=[file('saved.pdf')];
 for(const incoming of [[file('good.txt'),file('bad.exe')],[file('empty.txt',0)],[file('large.docx',2*1024*1024+1)],[]]){
  const result=mergeAgentAttachments(existing,incoming,2);assert.equal(result.files,existing);assert.ok(result.error);
 }
 assert.equal(mergeAgentAttachments(existing,[file('limit.docx',2*1024*1024)],2).error,'');
});
test('the 20-file limit includes existing attachments and excludes duplicates',()=>{
 const existing=Array.from({length:20},(_,i)=>file(`${i}.txt`));
 assert.equal(mergeAgentAttachments(existing,[existing[0]]).error,'');
 const rejected=mergeAgentAttachments(existing,[file('extra.txt')]);assert.equal(rejected.files,existing);assert.match(rejected.error,/20/);
});
test('text drags are distinct from file drags',()=>{
 assert.equal(isFileDrag(['Files','text/plain']),true);assert.equal(isFileDrag(['text/plain']),false);
});

// Exercise the real component's input handlers with persistent hooks, without
// uploading files or running network-dependent catalog/conversation effects.
function assistant(apiHandler){
 const storage=new Map();global.sessionStorage={getItem:key=>storage.get(key)??null,setItem:(key,value)=>storage.set(key,value),removeItem:key=>storage.delete(key)};
 let index=0;const hooks=[],calls=[],savedPrompts=[];const effects=[];
 const react={useState(initial){const slot=index++;if(!(slot in hooks))hooks[slot]=initial;return [hooks[slot],value=>{hooks[slot]=typeof value==='function'?value(hooks[slot]):value;}];},useRef(initial){const slot=index++;if(!(slot in hooks))hooks[slot]={current:initial};return hooks[slot];},useCallback:fn=>fn,useEffect:fn=>effects.push(fn)};
 const empty=new Proxy({},{get:()=>()=>null});
 const {AgentV2}=compile('agent-v2.tsx',{'react':react,'lucide-react':empty,'./agent-attachments':helpers,'./prompt-upload':compile('prompt-upload.ts'),'./prompt-upload-preview':empty,'./agent-prompt-selection':compile('agent-prompt-selection.ts'),'./agent-document-selection':compile('agent-document-selection.ts'),'./agent-v2.css':{},'./agent-document-filter':empty,'./chat-stream':empty,'./agent-v2-chat':empty,'./batch-progress':empty,'./agent-v2-output':empty,'./batch-workflow':empty,'./agent-voice':empty});
 const props={api:(...args)=>{calls.push(args);return apiHandler?apiHandler(...args):new Promise(()=>{});},stream:()=>assert.fail('Dropping files must not start an answer'),username:'attachment-test',onJobs(){},onVisibleJobs(){},onReview(){},onPromptSaved:prompt=>savedPrompts.push(prompt),maxUploadMb:2};
 let root;function render(){index=0;effects.length=0;root=AgentV2(props);return root;}
 function elements(node){if(!node||typeof node!=='object')return [];if(Array.isArray(node))return node.flatMap(elements);return [node,...elements(node.props?.children)];}
 const find=(key,value)=>elements(root).find(node=>node.props?.[key]===value);
 const names=()=>elements(root).filter(node=>node.props?.className?.split(' ').includes('agent-v2-file-card')).map(node=>elements(node).find(child=>child.type==='strong').props.children);
 render();return {render,find,names,calls,savedPrompts,effects,elements:()=>elements(root),get root(){return root;}};
}
function drag(files=[],types=['Files'],items=[]){return {dataTransfer:{types,files,items,dropEffect:''},prevented:false,stopped:false,preventDefault(){this.prevented=true;},stopPropagation(){this.stopped=true;}};}
test('nested drag events keep the drop overlay visible until the chat is exited',()=>{
 const view=assistant();const event=drag();view.root.props.onDragEnter(event);view.render();view.root.props.onDragEnter(event);view.render();
 view.root.props.onDragLeave(event);view.render();assert.ok(view.find('className','agent-v2-drop-overlay'));
 view.root.props.onDragLeave(event);view.render();assert.equal(view.find('className','agent-v2-drop-overlay'),undefined);
});
test('drop and file picker share append validation; attachment removal works',()=>{
 const view=assistant();const first=drag([file('first.pdf')]);view.root.props.onDrop(first);view.render();assert.equal(first.prevented,true);
 const input=view.find('type','file');const target={files:[file('second.txt')],value:'selected'};input.props.onChange({target});view.render();assert.equal(target.value,'');
 view.root.props.onDrop(drag([file('first.pdf')]));view.render();assert.deepEqual(view.names(),['first.pdf','second.txt']);
 view.root.props.onDrop(drag([file('bad.exe')]));view.render();assert.deepEqual(view.names(),['first.pdf','second.txt']);assert.ok(view.find('role','alert'));
 view.find('aria-label','Remove attachment first.pdf').props.onClick();view.render();assert.deepEqual(view.names(),['second.txt']);assert.equal(view.calls.length,0);
});
test('folders are rejected and dragging text retains normal browser handling',()=>{
 const view=assistant();const text=drag([],['text/plain']);view.root.props.onDrop(text);view.render();assert.equal(text.prevented,false);
 view.root.props.onDrop(drag([file('folder.txt')],['Files'],[{kind:'file',webkitGetAsEntry:()=>({isDirectory:true})}]));view.render();assert.deepEqual(view.names(),[]);assert.ok(view.find('role','alert'));
});
test('files-only Send proposes an upload; files are never sent before confirmation',()=>{
 const view=assistant();assert.equal(view.find('aria-label','Send agent request').props.disabled,true);
 view.root.props.onDrop(drag([file('invoice.pdf')]));view.render();assert.equal(view.find('aria-label','Send agent request').props.disabled,false);
 view.find('aria-label','Agent Model').props.onChange({target:{value:'chat-model'}});view.render();view.find('aria-label','Send agent request').props.onClick();view.render();
 assert.equal(view.calls.length,1);assert.equal(view.calls[0][0],'/agent-v2/plans');assert.equal(view.calls[0][2].text,'Upload the attached documents.');assert.deepEqual(view.calls[0][2].attached_filenames,['invoice.pdf']);assert.equal(view.calls[0][2] instanceof FormData,false);
 const event=drag([file('later.txt')]);view.root.props.onDragOver(event);assert.equal(event.dataTransfer.dropEffect,'none');view.root.props.onDrop(event);view.render();assert.deepEqual(view.names(),['invoice.pdf']);assert.ok(view.find('role','alert'));
});
test('file drops outside the chat cannot navigate the page; listeners are removed',()=>{
 const previous=global.window;const listeners=new Map();global.window={addEventListener:(name,handler)=>listeners.set(name,handler),removeEventListener:(name,handler)=>{assert.equal(listeners.get(name),handler);listeners.delete(name);}};
 try{const view=assistant();const cleanup=view.effects[0]();const event=drag();listeners.get('drop')(event);assert.equal(event.prevented,true);const text=drag([],['text/plain']);listeners.get('drop')(text);assert.equal(text.prevented,false);cleanup();assert.equal(listeners.size,0);}finally{global.window=previous;}
});

const flush=()=>new Promise(resolve=>setImmediate(resolve));
const promptSchema={type:'object',properties:{owner:{type:'string'}},required:['owner'],additionalProperties:false};
const jsonFile=(name='prompt.json',body=JSON.stringify({name:'Owner',schema:promptSchema}))=>({...file(name,Buffer.byteLength(body)),text:async()=>body});
const button=(view,name)=>view.elements().find(node=>node.type==='button'&&node.props.children===name);
const preview=view=>view.elements().find(node=>node.props?.onConfirm&&Object.hasOwn(node.props,'prompt'));
test('only JSON attachments ask for a role, and unresolved JSON cannot be sent',()=>{
 const view=assistant();view.root.props.onDrop(drag([file('notes.txt'),jsonFile('data.JSON')]));view.render();
 assert.equal(view.find('aria-label','Use notes.txt as'),undefined);assert.ok(view.find('aria-label','Use data.JSON as'));
 assert.equal(view.find('aria-label','Send agent request').props.disabled,true);view.find('aria-label','Send agent request').props.onClick();view.render();assert.equal(view.calls.length,0);
 button(view,'Document').props.onClick();view.render();assert.equal(view.find('aria-label','Send agent request').props.disabled,false);
 view.find('aria-label','Agent Model').props.onChange({target:{value:'chat-model'}});view.render();view.find('aria-label','Send agent request').props.onClick();
 assert.deepEqual(view.calls[0][2].attached_filenames,['notes.txt','data.JSON']);assert.equal(view.calls[0][0],'/agent-v2/plans');
});
test('prompt choice validates, reviews, then saves once without document upload or model inference',async()=>{
 const view=assistant(async(path,method,body)=>path==='/templates'?{id:'saved-prompt',name:body.name}:path==='/agent-v2/catalog'?{datasets:[],documents:[],templates:[],models:[]}:{valid:true});
 view.find('aria-label','Agent dataset').props.onChange({target:{value:'dataset-one'}});view.render();view.root.props.onDrop(drag([jsonFile()]));view.render();
 button(view,'Prompt template').props.onClick();await flush();view.render();assert.equal(view.calls.length,1);assert.equal(view.calls[0][0],'/templates/validate');assert.deepEqual(view.calls[0][2].schema,promptSchema);
 assert.ok(preview(view).props.prompt);assert.equal(view.find('aria-label','Send agent request').props.disabled,true);preview(view).props.onConfirm();view.render();
 assert.equal(view.calls.length,1);view.find('aria-label','Send agent request').props.onClick();await flush();view.render();
 assert.deepEqual(view.calls.map(call=>call[0]),['/templates/validate','/templates','/agent-v2/catalog']);assert.equal(view.calls[1][2].dataset_id,'dataset-one');
 assert.equal(view.calls[1][2].source_filename,'prompt.json');assert.equal(view.savedPrompts.length,1);assert.equal(view.savedPrompts[0].id,'saved-prompt');
 assert.equal(view.calls[1][2].name,'prompt.json');assert.deepEqual(view.names(),[]);
 view.find('aria-label','Send agent request').props.onClick();await flush();view.render();assert.equal(view.calls.filter(call=>call[0]==='/templates').length,1);
});

test('a second upload of the same filename is reviewed as an update and sent without changing identity',async()=>{
 let version=0;
 const view=assistant(async(path,method,body)=>path==='/templates'?{id:'same-prompt',name:body.source_filename,version:++version}:path==='/templates/validate'?{valid:true,existing_template_id:version?'same-prompt':null}:path==='/agent-v2/catalog'?{datasets:[],documents:[],templates:[],models:[]}:{valid:true});
 view.find('aria-label','Agent dataset').props.onChange({target:{value:'dataset-one'}});view.render();
 for(let iteration=0;iteration<2;iteration++){
  view.root.props.onDrop(drag([jsonFile('mani.json',JSON.stringify({name:'Different internal name '+iteration,schema:promptSchema}))]));view.render();
  button(view,'Prompt template').props.onClick();await flush();view.render();assert.equal(preview(view).props.prompt.replacesExisting,iteration===1);
  preview(view).props.onConfirm();view.render();view.find('aria-label','Send agent request').props.onClick();await flush();view.render();assert.deepEqual(view.names(),[]);
 }
 const saves=view.calls.filter(call=>call[0]==='/templates');assert.equal(saves.length,2);assert.ok(saves.every(call=>call[2].name==='mani.json'&&call[2].source_filename==='mani.json'));
 assert.deepEqual(view.savedPrompts.map(prompt=>prompt.id),['same-prompt','same-prompt']);
});
test('a confirmed prompt is supplied to extraction planning and excluded from document filenames',async()=>{
 const view=assistant((path,method,body)=>path==='/templates'?Promise.resolve({id:'saved-prompt',name:body.name}):path==='/agent-v2/catalog'?Promise.resolve({datasets:[],documents:[],templates:[],models:[]}):path==='/templates/validate'?Promise.resolve({valid:true}):new Promise(()=>{}));
 view.find('aria-label','Agent dataset').props.onChange({target:{value:'dataset-one'}});view.find('aria-label','Agent Model').props.onChange({target:{value:'chat-model'}});view.render();
 view.root.props.onDrop(drag([jsonFile(),file('invoice.pdf')]));view.render();button(view,'Prompt template').props.onClick();await flush();view.render();preview(view).props.onConfirm();view.render();
 view.find('aria-label','Message Aegis Assistant').props.onChange({target:{value:'Upload and extract the attached documents',selectionStart:41}});view.render();view.find('aria-label','Send agent request').props.onClick();await flush();
 const plan=view.calls.find(call=>call[0]==='/agent-v2/plans');assert.deepEqual(plan[2].attached_filenames,['invoice.pdf']);assert.equal(plan[2].template_id,'saved-prompt');assert.equal(plan[2].dataset_id,'dataset-one');
});
test('invalid prompt JSON stays attached for correction or document reclassification',async()=>{
 const view=assistant(async()=>assert.fail('Invalid JSON must fail before an API call'));view.find('aria-label','Agent dataset').props.onChange({target:{value:'dataset-one'}});view.render();
 view.root.props.onDrop(drag([jsonFile('bad.json','{bad')]));view.render();button(view,'Prompt template').props.onClick();await flush();view.render();
 assert.ok(view.find('role','alert'));assert.equal(preview(view).props.prompt,null);assert.deepEqual(view.names(),['bad.json']);assert.equal(view.find('aria-label','Send agent request').props.disabled,true);
 button(view,'Document').props.onClick();view.render();assert.equal(view.find('aria-label','Send agent request').props.disabled,false);
 assert.equal(view.find('role','alert'),undefined);
});

test('server schema validation errors stay beside their file and block saving until corrected',async()=>{
 const view=assistant(async(path)=>{assert.equal(path,'/templates/validate');throw new Error('Strict extraction requires additionalProperties:false at $.properties.details');});
 view.find('aria-label','Agent dataset').props.onChange({target:{value:'dataset-one'}});view.render();
 view.root.props.onDrop(drag([jsonFile()]));view.render();button(view,'Prompt template').props.onClick();await flush();view.render();
 const alert=view.find('role','alert');assert.match(alert.props.children,/prompt.json.*\$\.properties.details/);
 assert.equal(view.find('aria-label','Send agent request').props.disabled,true);assert.equal(preview(view).props.prompt,null);
 view.find('aria-label','Send agent request').props.onClick();assert.equal(view.calls.length,1);
 view.find('aria-label','Remove attachment prompt.json').props.onClick();view.render();assert.equal(view.find('role','alert'),undefined);
});
