const {test}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),Module=require('node:module'),ts=require('typescript');
function view({ids=['finance'],status={enabled:true,ready:true,tables:{}},reply}={}){
 let cursor=0,root;const slots=[],calls=[],effects=[];
 const react={
  useState(initial){const i=cursor++;if(!(i in slots))slots[i]={value:typeof initial==='function'?initial():initial};return [slots[i].value,value=>slots[i].value=typeof value==='function'?value(slots[i].value):value];},
  useRef(initial){const i=cursor++;if(!(i in slots))slots[i]={current:initial};return slots[i];},
  useEffect(callback,deps){const i=cursor++,old=slots[i];if(!old||deps.some((value,index)=>value!==old.deps[index])){old?.cleanup?.();slots[i]={deps};effects.push(()=>slots[i].cleanup=callback());}}
 };
 const filename=path.resolve(__dirname,'../../ags_frontend/app/local-select-ai.tsx'),compiled=new Module(filename,module);compiled.filename=filename;compiled.paths=module.paths;const original=compiled.require.bind(compiled);
 compiled.require=id=>id==='react'?react:id==='lucide-react'?new Proxy({},{get:()=>()=>null}):id==='./workflow-stepper'?{WorkflowStepper:()=>null}:id.endsWith('.css')?{}:original(id);
 compiled._compile(ts.transpileModule(fs.readFileSync(filename,'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022,jsx:ts.JsxEmit.ReactJSX}}).outputText,filename);
 const props={datasetIds:ids,api:async(...args)=>{calls.push(args);return args[0].endsWith('/status')?status:reply?reply(...args):{sql:'SELECT COUNT(*) FROM LOCAL_DOCUMENTS',columns:['COUNT'],rows:[[3]],metadata_as_of:1,metadata_rows:{LOCAL_DOCUMENTS:3},steps:[{id:'actual',label:'Actual server stage',status:'completed'}]};}};
 function all(node){return !node||typeof node!=='object'?[]:Array.isArray(node)?node.flatMap(all):[node,...all(node.props?.children)];}
 function render(){cursor=0;root=compiled.exports.LocalSelectAI(props);while(effects.length)effects.shift()();}
 const nodes=()=>all(root),find=(key,value)=>nodes().find(node=>node.props?.[key]===value);
 render();
 return {render,nodes,find,calls,props,async settle(){await new Promise(resolve=>setImmediate(resolve));render();},submit(){return nodes().find(node=>node.type==='form').props.onSubmit({preventDefault(){}});}};
}

test('disabled local pilot renders no query UI and never submits inference',async()=>{
 const v=view({status:{enabled:false}});await v.settle();assert.equal(v.nodes().length,0);assert.equal(v.calls.length,1);assert.match(v.calls[0][0],/status$/);
});
test('no selected datasets keeps generation disabled',async()=>{
 const v=view({ids:[]});await v.settle();assert.equal(v.find('type','submit').props.disabled,true);await v.submit();assert.equal(v.calls.length,1);
});
test('query sends explicit scope and displays only real returned stages',async()=>{
 const v=view();await v.settle();await v.submit();v.render();
 assert.deepEqual(v.calls[1][2].dataset_ids,['finance']);assert.equal(v.calls[1][1],'POST');
 assert.equal(v.nodes().find(node=>node.props?.label==='Local Select AI request stages').props.steps[0].id,'actual');
 assert.ok(v.nodes().some(node=>node.type==='code'&&node.props.children==='SELECT COUNT(*) FROM LOCAL_DOCUMENTS'));
});
test('changing dataset scope aborts and discards an in-flight result',async()=>{
 let finish;const v=view({reply:()=>new Promise(resolve=>finish=resolve)});await v.settle();
 const pending=v.submit();v.render();const signal=v.calls[1][3];v.props.datasetIds=['other'];v.render();assert.equal(signal.aborted,true);
 finish({sql:'PRIVATE_OLD_SCOPE_SQL',rows:[],columns:[],metadata_rows:{},steps:[]});await pending;v.render();
 assert.equal(v.nodes().some(node=>node.props?.children==='PRIVATE_OLD_SCOPE_SQL'),false);
});
test('failures show a stopped request without invented completed stages',async()=>{
 const v=view({reply:()=>{throw Error('Access revoked');}});await v.settle();await v.submit();v.render();
 assert.equal(v.find('role','alert').props.children,'Access revoked');
 assert.equal(v.nodes().find(node=>node.props?.label==='Local Select AI request stages').props.steps[0].status,'failed');
});
