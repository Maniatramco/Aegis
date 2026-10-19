const {test}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),Module=require('node:module'),ts=require('typescript');
const types=['Dataset','Document','Extraction','Prompt','Review','Model'];
const categoryNodes=types.map(type=>({id:type,type,label:type+'s',count:3,status:'saved',dataset_ids:['a','b'],attributes:{}}));
const recordNodes=[{...categoryNodes[0],id:'dataset:a',label:'Invoices',count:undefined},{...categoryNodes[1],id:'document:one',label:'invoice.txt',count:undefined},{...categoryNodes[1],id:'document:two',label:'terms.txt',count:undefined}];
const graph=(nodes,edges)=>({nodes,edges,items:nodes,total_items:nodes.length,related_total:nodes.length,has_more:false,truncated:false,totals:{nodes:18,edges:20,categories:Object.fromEntries(types.map(type=>[type,3]))},generated_at:1,warnings:[]});
const overview=graph(categoryNodes,[{id:'contains',source:'Dataset',target:'Document',label:'contains'},{id:'maps',source:'Dataset',target:'Model',label:'mapped models'}]);
const records=graph(recordNodes,[{id:'source',source:'dataset:a',target:'document:one',label:'contains'}]);
const elements=node=>!node||typeof node!=='object'?[]:Array.isArray(node)?node.flatMap(elements):typeof node.type==='function'?elements(node.type(node.props)):[node,...elements(node.props?.children)];
const text=node=>!node?'':typeof node==='string'?node:Array.isArray(node)?node.map(text).join(''):text(node.props?.children);
const near=(actual,expected)=>assert.ok(Math.abs(actual-expected)<1e-8,`${actual} should equal ${expected}`);

async function mount(t,{phone=false,screenScale=1,expandResponse,initialRecords}={}){
 let cursor=0,root,dirty=true,pending=[];const hooks=[],calls=[],captures=new Set(),listeners={};
 const react={
  useState(initial){const slot=cursor++;if(!(slot in hooks))hooks[slot]=typeof initial==='function'?initial():initial;return[hooks[slot],value=>{hooks[slot]=typeof value==='function'?value(hooks[slot]):value;dirty=true;}];},
  useRef(initial){const slot=cursor++;if(!(slot in hooks))hooks[slot]={current:initial};return hooks[slot];},
  useId(){cursor++;return 'metadata-test';},
  useMemo(run,deps){const slot=cursor++,old=hooks[slot];if(!old||deps.some((value,i)=>!Object.is(value,old.deps[i])))hooks[slot]={deps,value:run()};return hooks[slot].value;},
  useEffect(run,deps){const slot=cursor++,old=hooks[slot];if(!old||deps.some((value,i)=>!Object.is(value,old.deps[i])))pending.push(()=>{old?.cleanup?.();hooks[slot]={deps,cleanup:run()};});}
 };
 const filename=path.resolve(__dirname,'../../ags_frontend/app/metadata-relationships.tsx'),compiled=new Module(filename,module);compiled.filename=filename;compiled.paths=module.paths;const original=compiled.require.bind(compiled);
 const helperFile=path.resolve(__dirname,'../../ags_frontend/app/metadata-graph.ts'),helper=new Module(helperFile,module);helper.filename=helperFile;helper.paths=module.paths;helper._compile(ts.transpileModule(fs.readFileSync(helperFile,'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText,helperFile);
 compiled.require=id=>id==='./metadata-graph'?helper.exports:id==='react'?react:id==='lucide-react'?new Proxy({},{get:()=>()=>null}):original(id);
 compiled._compile(ts.transpileModule(fs.readFileSync(filename,'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022,jsx:ts.JsxEmit.ReactJSX}}).outputText,filename);
 const svg={addEventListener:(name,listener)=>listeners[name]=listener,removeEventListener:name=>delete listeners[name],getScreenCTM:()=>({inverse:()=>({a:screenScale,b:0,c:0,d:screenScale,e:-30,f:-70})}),setPointerCapture:id=>captures.add(id),hasPointerCapture:id=>captures.has(id),releasePointerCapture:id=>captures.delete(id)};
 const other={showModal(){},close(){},querySelector:()=>({focus(){}})};
 const props={datasets:[{id:'a',name:'Invoices'},{id:'b',name:'Policies'}],initialDatasetIds:['a','b'],api:async(url,method,body,signal)=>{calls.push(url);const query=new URLSearchParams(url.split('?')[1]);if(query.get('focus')&&expandResponse)return expandResponse(url,signal);return query.get('level')==='overview'?overview:initialRecords||records;},onClose(){},onReview(){}};
 function render(){cursor=0;dirty=false;root=compiled.exports.MetadataRelationships(props);for(const node of elements(root))if(node.props?.ref)node.props.ref.current=node.type==='svg'?svg:other;
  const old=global.matchMedia;global.matchMedia=()=>({matches:phone,addEventListener(){},removeEventListener(){}});try{const work=pending;pending=[];work.forEach(run=>run());}finally{if(old===undefined)delete global.matchMedia;else global.matchMedia=old;}}
 async function settle(){for(let i=0;i<5;i++){if(dirty)render();await new Promise(resolve=>setTimeout(resolve,1));}assert.ok(!dirty,'render settled');}
 t.after(()=>hooks.forEach(hook=>hook?.cleanup?.()));await settle();
 const all=()=>elements(root),find=label=>all().find(node=>node.props?.['aria-label']===label),node=id=>all().find(node=>node.props?.['data-metadata-node']===id);
 const point=id=>{const disc=elements(node(id)).find(n=>n.props?.className==='metadata-node-disc');return{x:disc.props.cx,y:disc.props.cy};};
 const camera=()=>all().find(n=>n.type==='g'&&n.props.transform)?.props.transform;
 const event=(id,x,y,options={})=>({button:0,buttons:1,pointerId:1,isPrimary:true,clientX:x,clientY:y,target:{closest:()=>id?{getAttribute:()=>id}:null},preventDefault(){},...options});
 const pointer=(name,id,x,y,options={})=>{find('Metadata relationship graph').props[name](event(id,x,y,options));if(dirty)render();};
 const move=(id,x,y,dx,dy,options={})=>{pointer('onPointerDown',id,x,y,options);pointer('onPointerMove',id,x+dx,y+dy,options);pointer('onPointerUp',id,x+dx,y+dy,options);};
 const key=(id,key,options={})=>{node(id).props.onKeyDown({key,preventDefault(){},...options});if(dirty)render();};
 const click=label=>{find(label).props.onClick();if(dirty)render();};
 const edge=label=>all().find(n=>n.props?.className?.startsWith('metadata-edge')&&n.props?.['aria-label']?.includes(label));
 return{all,find,node,point,camera,event,pointer,move,key,click,edge,settle,calls,captures,svg,listeners,text};
}

test('every category node moves independently, updating its edges without panning or fetching',async t=>{
 const v=await mount(t),original=Object.fromEntries(types.map(id=>[id,v.point(id)])),initialPath=elements(v.edge('contains')).find(n=>n.props?.className==='metadata-edge-line').props.d,requests=v.calls.length;
 for(const id of types)v.move(id,100,150,45,25);
 for(const id of types){near(v.point(id).x,original[id].x+45);near(v.point(id).y,original[id].y+25);}
 assert.equal(v.camera(),'translate(0 0) scale(1)');assert.equal(v.find('Metadata relationship graph').props.viewBox,'0 0 1000 690');assert.equal(v.calls.length,requests);
 assert.notEqual(elements(v.edge('contains')).find(n=>n.props?.className==='metadata-edge-line').props.d,initialPath);assert.equal(v.captures.size,0);
});

test('screen scaling and zoom are both accounted for, without accumulating movement errors',async t=>{
 const v=await mount(t,{screenScale:2}),before=v.point('Document');v.click('Zoom relationships in');v.click('Zoom relationships in');const camera=v.camera();
 v.pointer('onPointerDown','Document',100,150);v.pointer('onPointerMove','Document',135,171);v.pointer('onPointerMove','Document',170,192);v.pointer('onPointerUp','Document',170,192);
 near(v.point('Document').x,before.x+140/1.4);near(v.point('Document').y,before.y+84/1.4);assert.equal(v.camera(),camera);
 assert.deepEqual(v.point('Dataset'),{x:155,y:220});
});

test('background panning leaves node coordinates alone and still works after node dragging',async t=>{
 const v=await mount(t,{screenScale:2});v.move('Dataset',100,100,25,20);const node=v.point('Dataset');v.move(null,600,80,40,-20);
 assert.deepEqual(v.point('Dataset'),node);assert.equal(v.camera(),'translate(80 -40) scale(1)');
});

test('click threshold preserves details; completed drags do not activate a node or edge',async t=>{
 const v=await mount(t),before=v.point('Dataset');v.move('Dataset',100,100,5,3);assert.deepEqual(v.point('Dataset'),before);
 v.node('Dataset').props.onClick();await v.settle();assert.ok(v.node('Dataset').props.className.includes('selected'));
 v.move('Document',200,200,30,20);v.node('Document').props.onClick();v.edge('contains').props.onClick();await v.settle();assert.ok(!v.node('Document').props.className.includes('selected'));assert.ok(!v.edge('contains').props.className.includes('selected'));
 v.move('Document',200,200,0,0);v.node('Document').props.onClick();await v.settle();assert.ok(v.node('Document').props.className.includes('selected'));
});

test('touch cancellation, lost capture and additional pointers cannot leave a stuck drag',async t=>{
 const v=await mount(t);v.pointer('onPointerDown','Dataset',100,100,{pointerType:'touch'});v.pointer('onPointerDown','Document',200,200,{pointerId:2,isPrimary:false,pointerType:'touch'});v.pointer('onPointerMove','Document',400,400,{pointerId:2,pointerType:'touch'});
 v.pointer('onPointerMove','Dataset',130,140,{pointerType:'touch'});assert.deepEqual(v.point('Dataset'),{x:185,y:260});assert.deepEqual(v.point('Document'),{x:450,y:135});assert.equal(v.captures.size,1);
 v.pointer('onPointerCancel','Dataset',130,140,{type:'pointercancel'});v.pointer('onPointerMove','Dataset',600,600);assert.deepEqual(v.point('Dataset'),{x:185,y:260});assert.equal(v.captures.size,0);
 v.move('Document',200,200,30,0);v.pointer('onPointerDown','Dataset',100,100);v.pointer('onPointerMove','Dataset',130,100);v.pointer('onLostPointerCapture',null,130,100,{target:v.svg,type:'lostpointercapture'});
 assert.equal(v.captures.size,0);assert.equal(v.find('Metadata relationship graph').props['data-dragging'],undefined);v.move('Model',400,400,0,25);assert.deepEqual(v.point('Model'),{x:155,y:560});
});

test('keyboard adjustment supports fine/coarse movement, individual reset and inspection',async t=>{
 const v=await mount(t);v.key('Dataset','ArrowRight');v.key('Dataset','ArrowDown',{shiftKey:true});assert.deepEqual(v.point('Dataset'),{x:165,y:260});assert.deepEqual(v.point('Document'),{x:450,y:135});
 v.key('Dataset','ArrowRight',{ctrlKey:true});assert.deepEqual(v.point('Dataset'),{x:165,y:260});v.key('Dataset','Home');assert.deepEqual(v.point('Dataset'),{x:155,y:220});
 assert.equal(v.find('Back to Dashboard').props.title,'Back to Dashboard');assert.ok(v.node('Dataset').props['aria-describedby']);v.key('Dataset','Enter');assert.ok(v.node('Dataset').props.className.includes('selected'));assert.match(v.text(v.find('Reset node layout')),/^$/);
});

test('record nodes also drag; layouts survive list, drill-down and refresh, with a scoped reset',async t=>{
 const v=await mount(t);v.move('Dataset',100,100,25,30);const arranged=v.point('Dataset');v.click('Show metadata list');v.click('Show relationship graph');assert.deepEqual(v.point('Dataset'),arranged);
 v.key('Document','Enter');v.all().find(n=>n.type==='button'&&v.text(n)==='Explore documents').props.onClick();await v.settle();
 const original=v.point('document:one');v.move('document:one',100,100,70,30);assert.deepEqual(v.point('document:one'),{x:original.x+70,y:original.y+30});
 v.click('Reset node layout');assert.deepEqual(v.point('document:one'),original);v.all().find(n=>n.type==='button'&&v.text(n)==='Overview').props.onClick();await v.settle();assert.deepEqual(v.point('Dataset'),arranged);
 v.click('Refresh metadata relationships');await v.settle();assert.deepEqual(v.point('Dataset'),arranged);v.click('Reset node layout');assert.deepEqual(v.point('Dataset'),{x:155,y:220});assert.equal(v.camera(),'translate(0 0) scale(1)');
});

test('mobile curved connections and their labels follow moved nodes with a stable viewBox',async t=>{
 const v=await mount(t,{phone:true}),edge=()=>elements(v.edge('mapped models')),original=edge().find(n=>n.type==='text').props.x,pathBefore=edge().find(n=>n.props?.className==='metadata-edge-line').props.d;
 v.move('Dataset',100,100,45,-20,{pointerType:'touch'});v.move('Model',100,100,45,30,{pointerType:'touch'});
 assert.notEqual(edge().find(n=>n.props?.className==='metadata-edge-line').props.d,pathBefore);near(edge().find(n=>n.type==='text').props.x,original+45);assert.equal(v.find('Metadata relationship graph').props.viewBox,'0 0 540 805');
});

test('fit brings freely moved nodes into view without discarding their arrangement',async t=>{
 const v=await mount(t);v.move('Dataset',100,100,2000,-1000);const moved=v.point('Dataset');v.click('Fit relationships to screen');assert.deepEqual(v.point('Dataset'),moved);
 const [,x,y,zoom]=v.camera().match(/translate\(([^ ]+) ([^)]+)\) scale\(([^)]+)\)/).map(Number);
 for(const id of types){const point=v.point(id);assert.ok((point.x-68)*zoom+x>=0);assert.ok((point.x+68)*zoom+x<=1000);assert.ok((point.y-68)*zoom+y>=0);assert.ok((point.y+68)*zoom+y<=690);}
});


test('released pointers, leaving before capture and reset end any unfinished gesture',async t=>{
 const v=await mount(t);v.pointer('onPointerDown','Document',100,100);v.pointer('onPointerMove','Document',130,140);const moved=v.point('Document');
 v.pointer('onPointerMove','Document',160,170,{buttons:0});v.pointer('onPointerMove','Document',200,200);assert.deepEqual(v.point('Document'),moved);assert.equal(v.captures.size,0);
 v.pointer('onPointerDown','Document',100,100);v.pointer('onPointerLeave','Document',104,104);v.pointer('onPointerMove','Document',200,200);assert.deepEqual(v.point('Document'),moved);
 v.pointer('onPointerDown','Document',100,100);v.pointer('onPointerMove','Document',140,140);v.click('Reset node layout');v.pointer('onPointerMove','Document',250,250);assert.deepEqual(v.point('Document'),{x:450,y:135});assert.equal(v.captures.size,0);
});

test('pinning preserves a node during automatic layouts while allowing a manual adjustment',async t=>{
 const v=await mount(t);v.key('Dataset','Enter');v.click('Pin node position');v.click('Arrange as network');assert.deepEqual(v.point('Dataset'),{x:155,y:220});assert.equal(v.node('Dataset').props['data-pinned'],true);
 v.move('Dataset',100,100,20,30);v.click('Arrange as lineage');assert.deepEqual(v.point('Dataset'),{x:175,y:250});v.click('Unpin node position');v.click('Arrange as lineage');assert.notDeepEqual(v.point('Dataset'),{x:175,y:250});v.click('Reset node layout');assert.equal(v.node('Dataset').props['data-pinned'],undefined);
});
test('selection and hover reveal neighbors; type and label controls change only the current view',async t=>{
 const v=await mount(t),requests=v.calls.length;v.key('Dataset','Enter');assert.ok(!v.node('Document').props.className.includes('dimmed'));assert.ok(v.node('Extraction').props.className.includes('dimmed'));
 v.click('Clear graph selection');assert.ok(!v.node('Extraction').props.className.includes('dimmed'));v.node('Model').props.onPointerEnter({pointerType:'mouse'});await v.settle();assert.ok(v.node('Document').props.className.includes('dimmed'));
 v.click('Hide documents from graph');assert.equal(v.node('Document'),undefined);assert.equal(v.edge('contains'),undefined);v.all().find(n=>n.type==='button'&&v.text(n)==='Show all types').props.onClick();await v.settle();assert.ok(v.node('Document'));
 v.click('Hide relationship labels');assert.equal(v.edge('contains').props['data-label-hidden'],true);v.click('Show relationship labels');assert.equal(v.edge('contains').props['data-label-hidden'],undefined);assert.equal(v.calls.length,requests);
});
const runNode={...categoryNodes[2],id:'run:new',label:'Saved run',count:undefined},modelNode={...categoryNodes[5],id:'model:new',label:'Pinned model',count:undefined};
const expandedDocument=graph([recordNodes[1],runNode],[{id:'doc-run',source:'document:one',target:'run:new',label:'source of'}]);
const expandedRun=graph([runNode,modelNode],[{id:'model-run',source:'model:new',target:'run:new',label:'used by'}]);
async function recordsView(v){v.key('Document','Enter');v.all().find(n=>n.type==='button'&&v.text(n)==='Explore documents').props.onClick();await v.settle();}

test('double-click exploration and expansion retain exact dataset scope; collapse removes orphaned branches',async t=>{
 const v=await mount(t,{expandResponse:url=>new URLSearchParams(url.split('?')[1]).get('focus')==='run:new'?expandedRun:expandedDocument});v.node('Document').props.onDoubleClick({preventDefault(){}});await v.settle();
 const before=v.point('document:one');v.key('document:one','Enter');v.click('Expand node connections');await v.settle();assert.ok(v.node('run:new'));assert.deepEqual(v.point('document:one'),before);assert.equal(v.node('document:one').props['data-expanded'],true);
 const query=new URLSearchParams(v.calls.at(-1).split('?')[1]);assert.deepEqual(query.getAll('dataset_id'),['a','b']);assert.equal(query.get('focus'),'document:one');assert.equal(query.get('limit'),'1');
 v.key('run:new','Enter');v.click('Expand node connections');await v.settle();assert.ok(v.node('model:new'));v.key('document:one','Enter');v.click('Collapse node expansion');await v.settle();assert.equal(v.node('run:new'),undefined);assert.equal(v.node('model:new'),undefined);assert.ok(v.node('document:one'));
});
test('an expansion failure reports its failure without inventing connections or losing the original scene',async t=>{
 const v=await mount(t,{expandResponse:()=>Promise.reject(new Error('Scoped metadata unavailable'))});await recordsView(v);v.key('document:one','Enter');v.click('Expand node connections');await v.settle();assert.equal(v.node('run:new'),undefined);assert.ok(v.node('document:one'));assert.match(v.text(v.all().find(n=>n.props?.role==='alert')),/Scoped metadata unavailable/);assert.equal(v.find('Expand node connections').props.disabled,false);
});
test('a late expansion cannot cross a changed view or dataset scope',async t=>{
 let resolve,signal;const v=await mount(t,{expandResponse:(url,currentSignal)=>{signal=currentSignal;return new Promise(done=>resolve=done);}});await recordsView(v);v.key('document:one','Enter');v.click('Expand node connections');await v.settle();v.all().find(n=>n.type==='button'&&v.text(n)==='Overview').props.onClick();await v.settle();assert.equal(signal.aborted,true);resolve(expandedDocument);await v.settle();assert.ok(v.node('Dataset'));assert.equal(v.node('run:new'),undefined);
});
test('an expansion arriving after a manual drag keeps the latest manually chosen position',async t=>{
 let resolve;const v=await mount(t,{expandResponse:()=>new Promise(done=>resolve=done)});await recordsView(v);v.key('document:one','Enter');v.click('Expand node connections');await v.settle();v.move('document:one',100,100,60,40);const moved=v.point('document:one');resolve(expandedDocument);await v.settle();assert.deepEqual(v.point('document:one'),moved);assert.ok(v.node('run:new'));
});


test('record scenes start with matching items and add preloaded neighbors only after expansion',async t=>{
 const initial={...records,nodes:[...recordNodes,runNode],items:recordNodes,edges:[...records.edges,...expandedDocument.edges],related_total:4};const v=await mount(t,{initialRecords:initial,expandResponse:()=>expandedDocument});await recordsView(v);assert.equal(v.node('run:new'),undefined);v.key('document:one','Enter');v.click('Expand node connections');await v.settle();assert.ok(v.node('run:new'));
});


test('wheel zoom is centered on the pointer, preserves node coordinates and cleans up its listener',async t=>{
 const v=await mount(t),before=v.point('Document');let prevented=false;v.listeners.wheel({preventDefault(){prevented=true;},clientX:230,clientY:270,deltaY:-100,deltaMode:0});await v.settle();assert.equal(prevented,true);assert.deepEqual(v.point('Document'),before);const [,x,y,zoom]=v.camera().match(/translate\(([^ ]+) ([^)]+)\) scale\(([^)]+)\)/).map(Number);assert.ok(zoom>1);near(x,200*(1-zoom));near(y,200*(1-zoom));v.click('Show metadata list');assert.equal(v.listeners.wheel,undefined);
});
