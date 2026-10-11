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
const helpers=compile('agent-attachments.ts');const workflowStepper=compile('workflow-stepper.tsx',{'./horizontal-workflow-stepper.css':{}});const promptProgress=compile('agent-prompt-progress.tsx',{'./workflow-stepper':workflowStepper});const {mergeAgentAttachments,isFileDrag}=helpers;
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
function assistant(apiHandler,streamHandler){
 const storage=new Map();global.sessionStorage={getItem:key=>storage.get(key)??null,setItem:(key,value)=>storage.set(key,value),removeItem:key=>storage.delete(key)};
 let index=0;const hooks=[],calls=[],savedPrompts=[];const effects=[];
 const react={useState(initial){const slot=index++;if(!(slot in hooks))hooks[slot]=initial;return [hooks[slot],value=>{hooks[slot]=typeof value==='function'?value(hooks[slot]):value;}];},useRef(initial){const slot=index++;if(!(slot in hooks))hooks[slot]={current:initial};return hooks[slot];},useCallback:fn=>fn,useEffect:fn=>effects.push(fn)};
 const empty=new Proxy({},{get:()=>()=>null});
 const {AgentV2}=compile('agent-v2.tsx',{'react':react,'lucide-react':empty,'./agent-attachments':helpers,'./prompt-upload':compile('prompt-upload.ts'),'./prompt-upload-preview':empty,'./agent-prompt-progress':promptProgress,'./workflow-stepper':workflowStepper,'./agent-logo':empty,'./agent-answer-workflow':empty,'./agent-prompt-selection':compile('agent-prompt-selection.ts'),'./agent-document-selection':compile('agent-document-selection.ts'),'./agent-v2.css':{},'./agent-document-filter':empty,'./chat-stream':streamHandler?compile('chat-stream.ts'):empty,'./agent-v2-chat':empty,'./batch-progress':empty,'./agent-v2-output':empty,'./batch-workflow':empty,'./agent-voice':empty});
 const props={api:(...args)=>{calls.push(args);return apiHandler?apiHandler(...args):new Promise(()=>{});},stream:streamHandler||(()=>assert.fail('Dropping files must not start an answer')),username:'attachment-test',onJobs(){},onVisibleJobs(){},onReview(){},onPromptSaved:prompt=>savedPrompts.push(prompt),maxUploadMb:2};
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
 const event=drag([file('later.txt')]);view.root.props.onDragOver(event);assert.equal(event.dataTransfer.dropEffect,'none');view.root.props.onDrop(event);view.render();assert.deepEqual(view.names(),[]);assert.ok(view.find('role','alert'));
 assert.deepEqual(sentRequests(view).at(-1).props.attachments.map(file=>file.name),['invoice.pdf']);
});
test('file drops outside the chat cannot navigate the page; listeners are removed',()=>{
 const previous=global.window;const listeners=new Map();global.window={addEventListener:(name,handler)=>listeners.set(name,handler),removeEventListener:(name,handler)=>{assert.equal(listeners.get(name),handler);listeners.delete(name);}};
 try{const view=assistant();const cleanup=view.effects[0]();const event=drag();listeners.get('drop')(event);assert.equal(event.prevented,true);const text=drag([],['text/plain']);listeners.get('drop')(text);assert.equal(text.prevented,false);cleanup();assert.equal(listeners.size,0);}finally{global.window=previous;}
});

const flush=()=>new Promise(resolve=>setImmediate(resolve));
const sentRequests=view=>view.elements().filter(node=>Object.hasOwn(node.props||{},'attachments'));
const setRequest=(view,text='pls run extract')=>{view.find('aria-label','Message Aegis Agent').props.onChange({target:{value:text,selectionStart:text.length}});view.render();};
const selectContext=view=>{view.find('aria-label','Agent dataset').props.onChange({target:{value:'dataset-one'}});view.find('aria-label','Agent Model').props.onChange({target:{value:'chat-model'}});view.render();};
const uploadPlan=(body,id='upload-plan')=>({id,request:body.text,attached_filenames:body.attached_filenames,dataset_id:'dataset-one',document_ids:[],template_id:'',planner:{name:'Test'},calls:[{tool:'upload',title:'Upload documents',status:'pending'}]});

test('submitted files leave the composer immediately and remain with their question; confirmation uploads their original bytes',async()=>{
 let resolvePlan;const attached=new File(['Original invoice content'],'invoice.txt',{type:'text/plain'});
 const view=assistant((path,method,body)=>path==='/agent-v2/plans'?new Promise(resolve=>{resolvePlan=()=>resolve(uploadPlan(body));}):Promise.resolve({...uploadPlan({text:'pls run extract',attached_filenames:['invoice.txt']}),calls:[{tool:'upload',title:'Upload documents',status:'completed'}]}));
 selectContext(view);view.root.props.onDrop(drag([attached]));view.render();setRequest(view);view.find('aria-label','Send agent request').props.onClick();view.render();
 assert.deepEqual(view.names(),[]);assert.equal(sentRequests(view).at(-1).props.text,'pls run extract');assert.equal(sentRequests(view).at(-1).props.attachments[0].name,'invoice.txt');assert.equal(view.calls.length,1);
 resolvePlan();await flush();view.render();assert.deepEqual(view.names(),[]);assert.equal(button(view,'Confirm upload').props.disabled,false);
 // A later draft must not replace the bytes bound to this submitted message.
 view.root.props.onDrop(drag([new File(['Later draft'],'later.txt')]));view.render();
 button(view,'Confirm upload').props.onClick();await flush();view.render();
 const form=view.calls.find(call=>call[0].endsWith('/upload'))[2];assert.equal(form.getAll('files').length,1);assert.equal(form.get('files').name,'invoice.txt');assert.equal(await form.get('files').text(),'Original invoice content');
 assert.deepEqual(view.names(),['later.txt']);assert.equal(sentRequests(view)[0].props.attachments[0].name,'invoice.txt');
});

test('failed planning restores the draft and its files for retry',async()=>{
 let attempts=0;const view=assistant(async(path,method,body)=>{if(++attempts===1)throw new Error('Planning unavailable');return uploadPlan(body);});
 selectContext(view);view.root.props.onDrop(drag([file('retry.pdf')]));view.render();setRequest(view);view.find('aria-label','Send agent request').props.onClick();await flush();view.render();
 assert.deepEqual(view.names(),['retry.pdf']);assert.equal(view.find('aria-label','Message Aegis Agent').props.value,'pls run extract');assert.match(view.find('role','alert').props.children,/Planning unavailable/);
 view.find('aria-label','Send agent request').props.onClick();await flush();view.render();assert.deepEqual(view.names(),[]);assert.equal(sentRequests(view)[0].props.attachments[0].name,'retry.pdf');
});

test('failed upload keeps submitted bytes for retry, and clarification carries them into its replacement plan',async()=>{
 let planning=0,uploads=0;const attached=new File(['Retained bytes'],'retained.txt');
 const view=assistant(async(path,method,body)=>{if(path==='/agent-v2/plans')return uploadPlan(body,'plan-'+(++planning));if(method==='GET')return uploadPlan({text:'Proceed',attached_filenames:['retained.txt']},'plan-1');if(++uploads===1)throw new Error('Upload temporarily unavailable');return {...uploadPlan({text:'Proceed',attached_filenames:['retained.txt']},'plan-2'),calls:[{tool:'upload',title:'Upload',status:'completed'}]};});
 selectContext(view);view.root.props.onDrop(drag([attached]));view.render();setRequest(view);view.find('aria-label','Send agent request').props.onClick();await flush();view.render();
 button(view,'Confirm upload').props.onClick();await flush();view.render();assert.deepEqual(view.names(),[]);assert.equal(button(view,'Confirm upload').props.disabled,false);
 setRequest(view,'Use the selected dataset');view.find('aria-label','Send agent request').props.onClick();await flush();view.render();
 assert.deepEqual(view.calls.filter(call=>call[0]==='/agent-v2/plans')[1][2].attached_filenames,['retained.txt']);
 button(view,'Confirm upload').props.onClick();await flush();view.render();
 const forms=view.calls.filter(call=>call[0].endsWith('/upload')).map(call=>call[2]);assert.equal(forms.length,2);for(const form of forms)assert.equal(await form.get('files').text(),'Retained bytes');
});

test('submitted attachment cards render compact read-only names and sizes with the question',()=>{
 const React=require('react'),{renderToStaticMarkup}=require('react-dom/server');const {AgentRequest}=compile('agent-v2-chat.tsx',{'./agent-attachments':helpers});
 const html=renderToStaticMarkup(React.createElement(AgentRequest,{text:'pls run extract',attachments:[{name:'resume.pdf',size:3072},{name:'saved.txt'}]}));
 assert.match(html,/Files sent with this message/);assert.match(html,/resume.pdf/);assert.match(html,/3 KB/);assert.match(html,/pls run extract/);assert.doesNotMatch(html,/<button|Clear files|Remove attachment/);
});
const promptSchema={type:'object',properties:{owner:{type:'string'}},required:['owner'],additionalProperties:false};
test('multi-file workflow blocks confirmation until merge or independent is chosen, then authorizes continuation',async()=>{
 const view=assistant(async(path,method,body)=>path==='/agent-v2/plans'?{...uploadPlan(body),template_id:'prompt-id',calls:[{tool:'upload',title:'Upload',status:'pending'},{tool:'extract',title:'Extract',status:'pending'}]}:{...uploadPlan({text:'extract'}),calls:[{tool:'upload',status:'waiting'}]});
 selectContext(view);view.root.props.onDrop(drag([new File(['one'],'one.txt'),new File(['two'],'two.txt')]));view.render();setRequest(view);view.find('aria-label','Send agent request').props.onClick();await flush();view.render();
 assert.equal(button(view,'Confirm upload and extraction').props.disabled,true);
 view.find('aria-label','Extraction mode').props.onChange({target:{value:'independent'}});view.render();
 assert.equal(button(view,'Confirm upload and extraction').props.disabled,false);
 button(view,'Confirm upload and extraction').props.onClick();await flush();view.render();
 const form=view.calls.find(call=>call[0].endsWith('/upload'))[2];
 assert.equal(form.get('extraction_mode'),'independent');assert.equal(form.get('continue_extraction'),'true');assert.equal(form.get('template_id'),'prompt-id');assert.equal(form.getAll('files').length,2);
});

test('partial extraction exposes successful review while a sibling fails, hiding superseded attempts',()=>{
 const React=require('react'),{renderToStaticMarkup}=require('react-dom/server');
 const {AgentResult}=compile('agent-v2-output.tsx',{'./operation-progress':{JobProgress:()=>null},'./merged-details':compile('merged-details.tsx')});
 const html=renderToStaticMarkup(React.createElement(AgentResult,{tool:{status:'failed',result:{extractions:[{extraction_id:'good',name:'one.pdf',status:'completed',data:{owner:'Alice'}},{extraction_id:'bad',name:'two.pdf',status:'failed'},{extraction_id:'old',name:'old attempt',status:'failed',superseded:true}]}},onReview(){}}));
 assert.match(html,/one.pdf/);assert.match(html,/Alice/);assert.match(html,/two.pdf/);assert.equal((html.match(/Review result and evidence/g)||[]).length,1);assert.doesNotMatch(html,/old attempt|send a new request/);
});
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
 // Reselecting the same dataset must keep the confirmed prompt for this submission.
 view.find('aria-label','Agent dataset').props.onChange({target:{value:'dataset-one'}});view.render();
 view.find('aria-label','Message Aegis Agent').props.onChange({target:{value:'Upload and extract the attached documents',selectionStart:41}});view.render();view.find('aria-label','Send agent request').props.onClick();await flush();
 const plan=view.calls.find(call=>call[0]==='/agent-v2/plans');assert.deepEqual(plan[2].attached_filenames,['invoice.pdf']);assert.equal(plan[2].template_id,'saved-prompt');assert.equal(plan[2].dataset_id,'dataset-one');
 assert.equal(plan[2].submitted_prompt_id,'saved-prompt');
});

test('update this saves the revised JSON before passing its prompt identity to chat',async()=>{
 const updatedSchema={type:'object',properties:{full_name:{type:'string'}},required:['full_name'],additionalProperties:false};
 const view=assistant((path,method,body)=>path==='/templates'?Promise.resolve({id:'existing-prompt',name:body.name,version:2}):path==='/agent-v2/catalog'?Promise.resolve({datasets:[],documents:[],templates:[],models:[]}):path==='/templates/validate'?Promise.resolve({valid:true,existing_template_id:'existing-prompt'}):new Promise(()=>{}));
 selectContext(view);view.root.props.onDrop(drag([jsonFile('sample_resume.json',JSON.stringify({name:'Internal name',schema:updatedSchema}))]));view.render();
 button(view,'Prompt template').props.onClick();await flush();view.render();assert.equal(preview(view).props.prompt.replacesExisting,true);
 assert.equal(view.calls.filter(call=>call[0]==='/templates').length,0);
 preview(view).props.onConfirm();view.render();setRequest(view,'can you update this');view.find('aria-label','Send agent request').props.onClick();await flush();view.render();
 const save=view.calls.find(call=>call[0]==='/templates');const plan=view.calls.find(call=>call[0]==='/agent-v2/plans');
 assert.deepEqual(save[2].schema,updatedSchema);assert.equal(save[2].name,'sample_resume.json');assert.equal(save[2].dataset_id,'dataset-one');
 assert.ok(view.calls.indexOf(save)<view.calls.indexOf(plan));assert.equal(plan[2].submitted_prompt_id,'existing-prompt');assert.equal(plan[2].template_id,'existing-prompt');assert.deepEqual(plan[2].attached_filenames,[]);
 assert.deepEqual(view.names(),[]);assert.equal(sentRequests(view).at(-1).props.attachments[0].name,'sample_resume.json');assert.equal(sentRequests(view).at(-1).props.text,'can you update this');
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


test('the displayed mapped Agent Model is the same ID used to submit after catalog refresh',async()=>{
 const model={id:'mapped-chat',name:'Mapped Chat',enabled:true,capabilities:['chat']};
 const view=assistant((path,method,body)=>path==='/templates'?Promise.resolve({id:'saved-prompt',name:body.name}):path==='/templates/validate'?Promise.resolve({valid:true}):path==='/agent-v2/catalog'?Promise.resolve({datasets:[{id:'dataset-one',models:[model],default_chat_model_id:model.id}],models:[model],documents:[],templates:[]}):new Promise(()=>{}));
 view.find('aria-label','Agent dataset').props.onChange({target:{value:'dataset-one'}});view.render();
 view.root.props.onDrop(drag([jsonFile()]));view.render();button(view,'Prompt template').props.onClick();await flush();view.render();preview(view).props.onConfirm();view.render();view.find('aria-label','Send agent request').props.onClick();await flush();view.render();
 assert.equal(view.find('aria-label','Agent Model').props.value,'mapped-chat');
 view.root.props.onDrop(drag([file('invoice.txt')]));view.render();setRequest(view,'Upload this file');view.find('aria-label','Send agent request').props.onClick();await flush();
 assert.equal(view.calls.find(call=>call[0]==='/agent-v2/plans')[2].planner_model_id,'mapped-chat');
});


test('deferred streaming proposal keeps the submitted bytes bound and waits for confirmation',async()=>{
 const attached=new File(['Original bytes'],'streamed.txt',{type:'text/plain'});let submitted;
 const view=assistant((path,method,body)=>{
  if(path==='/agent-v2/plans'){submitted=body;return Promise.resolve({...uploadPlan(body,'stream-plan'),calls:[],phase:'queued',runtime:'langgraph'});}
  assert.ok(body instanceof FormData);return Promise.resolve({...uploadPlan(submitted,'stream-plan'),calls:[{tool:'upload',status:'completed',title:'Upload documents'}]});
 },async()=>{
  const final={...uploadPlan(submitted,'stream-plan'),runtime:'langgraph',phase:'proposal'};
  const body='event: delta\ndata: '+JSON.stringify({text:'Review the upload.'})+'\n\nevent: done\ndata: '+JSON.stringify({plan:final,conversation_id:'conversation-one',message:{text:'Review the upload.',status:'completed',citations:[]}})+'\n\n';
  return new Response(body,{headers:{'Content-Type':'text/event-stream'}});
 });
 selectContext(view);view.root.props.onDrop(drag([attached]));view.render();setRequest(view,'Upload this file');view.find('aria-label','Send agent request').props.onClick();await flush();view.render();
 assert.equal(submitted.stream_answers,true);assert.deepEqual(view.names(),[]);assert.equal(view.calls.length,1);
 const confirm=view.elements().find(node=>node.props?.children==='Confirm upload');assert.ok(confirm);assert.equal(confirm.props.disabled,false);confirm.props.onClick();await flush();view.render();
 const form=view.calls.at(-1)[2];assert.equal(await form.getAll('files')[0].text(),'Original bytes');
});

test('thread follows streamed answers only while the reader remains near the bottom',()=>{
 const view=assistant();const area={scrollTop:0,scrollHeight:1200,clientHeight:400};const thread=view.find('aria-label','Agent conversation');thread.props.ref.current=area;
 thread.props.onScroll({currentTarget:area});view.render();assert.ok(view.find('aria-label','Scroll to latest message'));
 for(const effect of view.effects){if(String(effect).includes('followBottom.current'))effect();}
 assert.equal(area.scrollTop,0);
 view.find('aria-label','Scroll to latest message').props.onClick();view.render();assert.equal(area.scrollTop,1200);assert.equal(view.find('aria-label','Scroll to latest message'),undefined);
 area.scrollTop=790;view.find('aria-label','Agent conversation').props.onScroll({currentTarget:area});view.render();
 for(const effect of view.effects){if(String(effect).includes('followBottom.current'))effect();}
 assert.equal(area.scrollTop,1200);
});

test('real workflow events survive answer deltas and retain completed timings',async()=>{
 let submitted,controller;
 const stream=new ReadableStream({start(value){controller=value;}});
 const view=assistant((path,method,body)=>{
  assert.equal(path,'/agent-v2/plans');submitted=body;
  return Promise.resolve({...uploadPlan(body,'progress-plan'),calls:[],phase:'queued',runtime:'langgraph'});
 },async()=>new Response(stream,{headers:{'Content-Type':'text/event-stream'}}));
 selectContext(view);setRequest(view,'What is the status?');view.find('aria-label','Send agent request').props.onClick();await flush();view.render();
 const workflow={status:'running',started_at:100,steps:[{id:'1',label:'Checking workflow status',status:'running',started_at:100}]};
 const send=(event,payload)=>controller.enqueue(new TextEncoder().encode(`event: ${event}\ndata: ${JSON.stringify(payload)}\n\n`));
 send('progress',{workflow});send('delta',{text:'The saved extraction is ready.'});await flush();view.render();
 assert.deepEqual(view.elements().find(node=>node.props?.workflow).props.workflow,workflow);
 assert.ok(view.find('aria-label','Stop answer'));
 const complete={...workflow,status:'completed',steps:[{...workflow.steps[0],status:'completed',duration_ms:2345}]};
 send('done',{plan:{...uploadPlan(submitted,'progress-plan'),calls:[],runtime:'langgraph',answer_workflow:complete},conversation_id:'conversation-one',message:{text:'The saved extraction is ready.',status:'completed',answer_workflow:complete}});
 controller.close();await flush();view.render();
 assert.deepEqual(view.elements().find(node=>node.props?.workflow).props.workflow,complete);
 assert.equal(view.find('aria-label','Stop answer'),undefined);
});

test('stopping a streamed answer freezes its current workflow stage',async()=>{
 let submitted,controller;
 const stream=new ReadableStream({start(value){controller=value;}});
 const view=assistant((path,method,body)=>{
  if(method==='POST')submitted=body;
  return Promise.resolve({...uploadPlan(submitted,'stopped-plan'),calls:[],phase:'queued',runtime:'langgraph'});
 },async(path,body,signal)=>{
  signal.addEventListener('abort',()=>controller.error(new DOMException('Stopped','AbortError')));
  return new Response(stream,{headers:{'Content-Type':'text/event-stream'}});
 });
 selectContext(view);setRequest(view,'What is the status?');view.find('aria-label','Send agent request').props.onClick();await flush();view.render();
 const workflow={status:'running',started_at:Date.now()-2500,steps:[{id:'1',label:'Checking workflow status',status:'running',started_at:Date.now()-2000}]};
 controller.enqueue(new TextEncoder().encode(`event: progress\ndata: ${JSON.stringify({workflow})}\n\n`));await flush();view.render();
 view.find('aria-label','Stop answer').props.onClick();await flush();view.render();
 const stopped=view.elements().find(node=>node.props?.workflow).props.workflow;
 assert.equal(stopped.status,'aborted');assert.equal(stopped.steps[0].status,'cancelled');assert.ok(stopped.steps[0].duration_ms>=2000);
 assert.equal(view.find('aria-label','Stop answer'),undefined);
});


test('failed deferred planning offers retry with the original attached bytes',async()=>{
 const attached=new File(['Recover these bytes'],'retry.txt',{type:'text/plain'});let submitted;
 const view=assistant((path,method,body)=>{
  if(path==='/agent-v2/plans'){submitted=body;return Promise.resolve({...uploadPlan(body,'failed-stream'),calls:[],phase:'queued',runtime:'langgraph'});}
  return Promise.resolve({...uploadPlan(submitted,'failed-stream'),calls:[],runtime:'langgraph',chat:{text:'',status:'failed',citations:[],error:{detail:'Model unavailable'}}});
 },async()=>new Response('event: error\ndata: '+JSON.stringify({detail:'Model unavailable',message:{text:'',status:'failed',citations:[],error:{detail:'Model unavailable'}}})+'\n\n'));
 selectContext(view);view.root.props.onDrop(drag([attached]));view.render();setRequest(view,'Upload this file');view.find('aria-label','Send agent request').props.onClick();await flush();view.render();
 assert.deepEqual(view.names(),[]);const retry=view.elements().find(node=>node.props?.children==='Retry request');assert.ok(retry);retry.props.onClick();view.render();
 assert.deepEqual(view.names(),['retry.txt']);assert.equal(view.find('aria-label','Message Aegis Agent').props.value,'Upload this file');
});

test('saved prompt response retry needs no file and never saves another prompt version',async()=>{
 let submitted,attempt=0,planCount=0;
 const receipt={name:'prompt.json',version:4};
 const view=assistant(async(path,method,body)=>{
  if(path==='/templates/validate')return {valid:true};
  if(path==='/templates')return {id:'saved-prompt',...receipt};
  if(path==='/agent-v2/catalog')return {datasets:[],documents:[],models:[],templates:[]};
  if(path==='/agent-v2/plans'){submitted=body;return {...uploadPlan(body,'prompt-plan-'+(++planCount)),planner:{id:'chat-model',name:'Test'},template_id:'saved-prompt',submitted_prompt_id:body.submitted_prompt_id,prompt_receipt:receipt,calls:[],runtime:'langgraph',phase:'queued'};}
  return {...uploadPlan(submitted,'prompt-plan-1'),planner:{id:'chat-model',name:'Test'},template_id:'saved-prompt',submitted_prompt_id:'saved-prompt',prompt_receipt:receipt,calls:[],chat:{status:'failed',text:''}};
 },async()=>{
  const event=++attempt===1?{detail:'Response unavailable',message:{status:'failed',text:''}}:{conversation_id:'saved-chat',message:{status:'completed',text:'Saved prompt.json version 4.'}};
  return new Response(`event: ${attempt===1?'error':'done'}\ndata: ${JSON.stringify(event)}\n\n`);
 });
 selectContext(view);view.root.props.onDrop(drag([jsonFile()]));view.render();button(view,'Prompt template').props.onClick();await flush();view.render();preview(view).props.onConfirm();view.render();setRequest(view,'can you upload it');view.find('aria-label','Send agent request').props.onClick();await flush();view.render();
 const progress=view.elements().find(node=>node.type===promptProgress.AgentPromptProgress);assert.equal(progress.props.progress.receipt.version,4);assert.equal(progress.props.progress.phase,'failed');
 button(view,'Retry response').props.onClick();view.render();assert.equal(view.find('role','alert'),undefined);assert.equal(view.find('aria-label','Message Aegis Agent').props.value,'can you upload it');assert.deepEqual(view.names(),[]);
 view.find('aria-label','Send agent request').props.onClick();await flush();view.render();
 assert.equal(view.calls.filter(call=>call[0]==='/templates').length,1);assert.equal(submitted.submitted_prompt_id,'saved-prompt');assert.equal(button(view,'Retry response'),undefined);
 assert.equal(view.elements().filter(node=>node.type===promptProgress.AgentPromptProgress).at(-1).props.progress.phase,'completed');
});

test('visible prompt steps distinguish committed save from a failed response',()=>{
 const React=require('react'),{renderToStaticMarkup}=require('react-dom/server');
 const markup=renderToStaticMarkup(React.createElement(promptProgress.AgentPromptProgress,{progress:{name:'prompt.json',receipt:{name:'prompt.json',version:4},phase:'failed'}}));
 for(const label of ['Validate prompt','Save prompt','Prepare request','Respond','Version 4','Prompt is saved.'])assert.ok(markup.includes(label));
 assert.equal((markup.match(/data-status="completed"/g)||[]).length,3);assert.equal((markup.match(/data-status="failed"/g)||[]).length,1);
});

test('whole workflow restart sends retained scope once and begins with knowledge processing',async()=>{
 const failed={id:'failed-workflow',request:'extract',planner:{id:'chat-model',name:'Local'},dataset_id:'dataset-one',document_ids:['original'],template_id:'saved-template',extraction_mode:'independent',merge_strategy:'records',display_name:'QA result',calls:[{tool:'upload',title:'Upload',status:'completed',uploaded_document_ids:['original']},{tool:'extract',title:'Extract',status:'failed',error:'Model failed'}]};
 const view=assistant(async(path,method,body)=>path==='/agent-v2/plans'?failed:{...failed,calls:[{tool:'upload',title:'Rebuild document knowledge',status:'waiting',uploaded_document_ids:['original']},{tool:'extract',title:'Extract',status:'pending'}]});
 selectContext(view);setRequest(view);view.find('aria-label','Send agent request').props.onClick();await flush();view.render();
 const restart=button(view,'Restart workflow');assert.equal(restart.props.disabled,false);
 restart.props.onClick();restart.props.onClick();await flush();view.render();
 const requests=view.calls.filter(call=>call[0].endsWith('/restart'));assert.equal(requests.length,1);
 assert.deepEqual(requests[0][2],{dataset_id:'dataset-one',document_ids:['original'],template_id:'saved-template',extraction_mode:'independent',merge_strategy:'records',display_name:'QA result',allow_external:false,confirmed:true});
 assert.equal(button(view,'Restart workflow'),undefined);
});
