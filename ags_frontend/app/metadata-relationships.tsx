"use client";
import {useEffect,useId,useMemo,useRef,useState,type KeyboardEvent,type PointerEvent} from 'react';
import {ArrowLeft,ArrowRight,CheckCircle2,ChevronDown,ChevronRight,Database,FileText,Focus,GitFork,Layers,List,Maximize,Minus,Network,Pin,PinOff,Plus,RefreshCw,RotateCcw,Search,ShieldCheck,SlidersHorizontal,Sparkles,Tag,X} from 'lucide-react';
import {expansionPositions,fitGraph,lineageLayout,mergeScene,neighborhood,networkLayout,relationshipBends,relationshipGeometry} from './metadata-graph';

type Entity=Record<string,any>;
type Api=(path:string,method?:string,body?:unknown,signal?:AbortSignal,quiet?:boolean)=>Promise<any>;
type Kind='Dataset'|'Document'|'Extraction'|'Prompt'|'Review'|'Model';
type GraphNode={id:string;type:Kind;label:string;count?:number;status:string;version?:number;dataset_ids:string[];attributes:Record<string,string|number>;action?:{kind:string;id:string}};
type Edge={id:string;source:string;target:string;label:string;count?:number;relationships?:Record<string,number>};
type Graph={nodes:GraphNode[];edges:Edge[];items:GraphNode[];total_items:number;related_total:number;has_more:boolean;truncated:boolean;totals:{nodes:number;edges:number;categories:Partial<Record<Kind,number>>};generated_at:number;warnings:string[]};
type Filter={level:'overview'|'instances';category:string;focus:string;offset:number;search:string};
type Point={x:number;y:number};
type Camera=Point&{zoom:number};
type Drag={pointerId:number;client:Point;canvas:Point;camera:Camera;node:{id:string;position:Point}|null;moved:boolean};
const START_CAMERA:Camera={zoom:1,x:0,y:0};
const OVERVIEW:Filter={level:'overview',category:'',focus:'',offset:0,search:''};
const EMPTY:Graph={nodes:[],edges:[],items:[],total_items:0,related_total:0,has_more:false,truncated:false,totals:{nodes:0,edges:0,categories:{}},generated_at:0,warnings:[]};
const kinds:Record<Kind,{plural:string;color:string;Icon:typeof Database;description:string}>={
 Dataset:{plural:'Datasets',color:'#2563eb',Icon:Database,description:'The datasets you are authorized to inspect, including inactive datasets when selected.'},
 Document:{plural:'Documents',color:'#2877b5',Icon:FileText,description:'Original documents and their current processing status. Saved extraction document lists establish source links.'},
 Extraction:{plural:'Extractions',color:'#315de7',Icon:Layers,description:'Saved runs linked to their dataset, source documents, prompt version and pinned model selection.'},
 Prompt:{plural:'Prompts',color:'#396a9d',Icon:SlidersHorizontal,description:'Saved prompt/schema versions. Historical versions used by runs remain distinct from the current prompt.'},
 Review:{plural:'Reviews',color:'#17386b',Icon:CheckCircle2,description:'Recorded review revisions and the extraction version that was reviewed.'},
 Model:{plural:'Models',color:'#447fae',Icon:Sparkles,description:'Current dataset model mappings and historical model versions recorded by extraction runs. No model connection is tested.'}
};
const positions:Record<Kind,[number,number]>={Dataset:[155,220],Document:[450,135],Extraction:[775,265],Prompt:[450,490],Review:[805,545],Model:[155,535]};
const phonePositions:Record<Kind,[number,number]>={Dataset:[140,150],Document:[400,235],Extraction:[400,460],Prompt:[140,425],Review:[400,685],Model:[140,685]};
const words=(text:string,max=18)=>{const lines:string[]=[];let line='';for(const word of text.split(' ')){if(line&&(line+' '+word).length>max){lines.push(line);line=word;}else line=line?line+' '+word:word;}if(line)lines.push(line);return lines.slice(0,3).map(value=>value.length>max?value.slice(0,max-1)+'…':value);};
function layout(nodes:GraphNode[],overview:boolean,phone:boolean,focus:string){
 if(overview)return nodes.map(node=>{const [x,y]=(phone?phonePositions:positions)[node.type];return{...node,x,y,r:60};});
 if(focus&&nodes.length<=6){const others=nodes.filter(n=>n.id!==focus),spots=phone?[[135,145],[405,145],[135,585],[405,585],[270,720]]:[[220,160],[760,160],[220,510],[760,510],[490,620]];return nodes.map(node=>{const i=others.findIndex(n=>n.id===node.id),[x,y]=node.id===focus?(phone?[270,365]:[490,335]):spots[i];return{...node,x,y,r:52};});}
 return nodes.map((node,i)=>({...node,x:phone?(i%2?395:145):140+(i%4)*235,y:100+Math.floor(i/(phone?2:4))*145,r:50}));
}

export function MetadataRelationships({datasets,initialDatasetIds,api,onClose,onReview}:{datasets:Entity[];initialDatasetIds:string[];api:Api;onClose:()=>void;onReview:(id:string)=>void}){
 const dialog=useRef<HTMLDialogElement>(null),details=useRef<HTMLElement>(null),svg=useRef<SVGSVGElement>(null),prefix=useId().replaceAll(':','');
 const [selectedIds,setSelectedIds]=useState(()=>initialDatasetIds.filter(id=>datasets.some(d=>d.id===id))),[draft,setDraft]=useState<string[]>([]),[picker,setPicker]=useState(false);
 const [filter,setFilter]=useState<Filter>(OVERVIEW),[baseGraph,setGraph]=useState<Graph|null>(null),[loading,setLoading]=useState(false),[error,setError]=useState(''),[revision,setRevision]=useState(0);
 const [expansions,setExpansions]=useState<Record<string,Graph>>({}),[expanding,setExpanding]=useState(''),[expansionError,setExpansionError]=useState(''),[hovered,setHovered]=useState(''),[hiddenTypes,setHiddenTypes]=useState<string[]>([]),[labelOverride,setLabelOverride]=useState<boolean|null>(null);
 const [pinSets,setPinSets]=useState<Record<string,string[]>>({}),[layoutModes,setLayoutModes]=useState<Record<string,string>>({});
 const expansionRequest=useRef<AbortController|null>(null),requestGeneration=useRef(0);
 const [selected,setSelected]=useState<{kind:'node'|'edge';id:string}|null>(null),[sheet,setSheet]=useState(false),[list,setList]=useState(false),[phone,setPhone]=useState(false);
 const [camera,setCamera]=useState<Camera>(START_CAMERA),[arrangements,setArrangements]=useState<Record<string,Record<string,Point>>>({}),[dragging,setDragging]=useState<string|null>(null),[announcement,setAnnouncement]=useState('');
 const drag=useRef<Drag|null>(null),dragMoved=useRef(false);
 const scopeKey=[...selectedIds].sort().join('|'),catalogKey=datasets.map(d=>d.id).sort().join('|');
 const requestContext=JSON.stringify([scopeKey,catalogKey,filter,revision]),latestContext=useRef(requestContext);latestContext.current=requestContext;
 useEffect(()=>{dialog.current?.showModal();const media=matchMedia('(max-width: 700px)'),update=()=>setPhone(media.matches);update();media.addEventListener('change',update);return()=>{media.removeEventListener('change',update);dialog.current?.close();};},[]);
 useEffect(()=>{setSelectedIds(ids=>ids.filter(id=>datasets.some(d=>d.id===id)));},[catalogKey]);
 useEffect(()=>{
  const controller=new AbortController();requestGeneration.current++;expansionRequest.current?.abort();setExpansions({});setExpanding('');setExpansionError('');setHovered('');setHiddenTypes([]);setLabelOverride(null);setGraph(null);setError('');setSelected(null);setSheet(false);setCamera({zoom:1,x:0,y:0});
  if(!selectedIds.length){setGraph(EMPTY);setLoading(false);return()=>controller.abort();}
  setLoading(true);
  const timer=setTimeout(()=>{const query=new URLSearchParams({level:filter.level,category:filter.category,focus:filter.focus,offset:String(filter.offset),limit:'12',search:filter.search});selectedIds.forEach(id=>query.append('dataset_id',id));
   void api('/metadata-relationships?'+query,'GET',undefined,controller.signal,true).then((data:Graph)=>{if(controller.signal.aborted||latestContext.current!==requestContext)return;
    // Start with matching records. Neighbours enter the scene only when explicitly expanded.
    if(filter.level==='instances'&&!filter.focus&&Array.isArray(data.items)){const ids=new Set(data.items.map(node=>node.id));setGraph({...data,nodes:data.items,edges:data.edges.filter(edge=>ids.has(edge.source)&&ids.has(edge.target))});}
    else setGraph(data);
   }).catch(reason=>{if(!controller.signal.aborted&&latestContext.current===requestContext)setError(reason instanceof Error?reason.message:'Could not load metadata relationships.');}).finally(()=>{if(!controller.signal.aborted&&latestContext.current===requestContext)setLoading(false);});},filter.search?250:0);
  return()=>{clearTimeout(timer);controller.abort();};
 },[scopeKey,catalogKey,filter,revision,api]);
 useEffect(()=>{if(sheet&&phone)details.current?.querySelector<HTMLButtonElement>('button')?.focus();},[sheet,phone,selected?.id]);
 useEffect(()=>()=>expansionRequest.current?.abort(),[]);
 const graph=useMemo(()=>baseGraph?mergeScene(baseGraph,expansions):null,[baseGraph,expansions]);
 const overview=filter.level==='overview',visibleNodes=(graph?.nodes||[]).filter(node=>!hiddenTypes.includes(node.type)),displayNodes=visibleNodes.slice(0,phone?40:120);
 // Keep each scoped view's arrangement for this explorer session, including across refresh/list switches.
 const layoutKey=JSON.stringify([scopeKey,phone,filter]),savedPositions=arrangements[layoutKey]||{},pinned=new Set(pinSets[layoutKey]||[]),width=phone?540:1000,height=phone?805:690;
 const defaults=useMemo(()=>{
  const seeds=layout((graph?.nodes||[]).slice(0,phone?40:120),overview,phone,filter.focus);
  if(overview)return seeds;
  const nodes=seeds.map(node=>({...node,r:43})),points=networkLayout(nodes,graph?.edges||[],width,height);
  return nodes.map(node=>({...node,...points[node.id]}));
 },[graph?.nodes,graph?.edges,overview,phone,filter.focus]);
 const defaultLookup=new Map(defaults.map(node=>[node.id,node]));
 const visibleDefaults=displayNodes.map(node=>defaultLookup.get(node.id)!).filter(Boolean);
 const placed=visibleDefaults.map(node=>({...node,...savedPositions[node.id]})),lookup=new Map(placed.map(node=>[node.id,node]));
 // Moving a node must not resize the SVG and change its coordinate system during the gesture.
 useEffect(()=>{if(baseGraph&&!overview)setCamera(fitGraph(defaults.map(node=>({...node,...savedPositions[node.id]})),width,height));},[baseGraph,phone]);
 useEffect(()=>{
  const active=drag.current;drag.current=null;dragMoved.current=false;setDragging(null);
  if(active&&svg.current?.hasPointerCapture(active.pointerId))svg.current.releasePointerCapture(active.pointerId);
 },[layoutKey,list,loading]);
 useEffect(()=>{if(overview)setCamera(START_CAMERA);},[phone]);
 useEffect(()=>{
  const canvas=svg.current;if(!canvas||list||loading)return;
  const wheel=(event:WheelEvent)=>{
   event.preventDefault();if(drag.current)return;
   const matrix=canvas.getScreenCTM()?.inverse();if(!matrix)return;
   const point={x:matrix.a*event.clientX+matrix.c*event.clientY+matrix.e,y:matrix.b*event.clientX+matrix.d*event.clientY+matrix.f},delta=event.deltaY*(event.deltaMode===1?16:event.deltaMode===2?height:1);
   setCamera(old=>{const zoom=Math.max(.2,Math.min(2.6,old.zoom*Math.exp(-Math.max(-400,Math.min(400,delta))*.0015))),ratio=zoom/old.zoom;return{zoom,x:point.x-(point.x-old.x)*ratio,y:point.y-(point.y-old.y)*ratio};});
  };
  canvas.addEventListener('wheel',wheel,{passive:false});return()=>canvas.removeEventListener('wheel',wheel);
 },[Boolean(graph?.nodes.length),list,loading,phone]);
 const edges=(graph?.edges||[]).filter(e=>lookup.has(e.source)&&lookup.has(e.target)),bends=relationshipBends(edges);
 const highlight=neighborhood(placed,edges,dragging&&dragging!=='canvas'?{kind:'node',id:dragging}:hovered?{kind:'node',id:hovered}:selected),hasHighlight=highlight.nodes.size>0,showLabels=labelOverride??overview;
 const selectedNode=selected?.kind==='node'?graph?.nodes.find(n=>n.id===selected.id):null,selectedEdge=selected?.kind==='edge'?graph?.edges.find(e=>e.id===selected.id):null;
 const selectNode=(id:string)=>{setSelected({kind:'node',id});setSheet(true);};
 const explore=(category:string,focus='')=>{setFilter({level:'instances',category,focus,offset:0,search:''});setSelected(null);setSheet(false);};
 const reset=()=>{setFilter(OVERVIEW);setSelected(null);setSheet(false);};
 const closeSheet=()=>{setSheet(false);dialog.current?.querySelector<HTMLButtonElement>('.metadata-back')?.focus();};
 const setZoom=(change:number)=>setCamera(old=>{const zoom=Math.max(.2,Math.min(2.6,old.zoom+change)),ratio=zoom/old.zoom,cx=width/2,cy=height/2;return{zoom,x:cx-(cx-old.x)*ratio,y:cy-(cy-old.y)*ratio};});
 const moveNode=(id:string,position:Point)=>setArrangements(old=>({...old,[layoutKey]:{...old[layoutKey],[id]:position}}));
 const resetNode=(id:string)=>setArrangements(old=>{const positions={...old[layoutKey]};delete positions[id];return{...old,[layoutKey]:positions};});
 const cancelDrag=()=>{
  const active=drag.current;drag.current=null;setDragging(null);
  if(active){dragMoved.current=true;if(svg.current?.hasPointerCapture(active.pointerId))svg.current.releasePointerCapture(active.pointerId);}
 };
 const resetLayout=()=>{cancelDrag();setArrangements(old=>{const next={...old};delete next[layoutKey];return next;});setPinSets(old=>({...old,[layoutKey]:[]}));setLayoutModes(old=>({...old,[layoutKey]:overview?'default':'network'}));setCamera(overview?START_CAMERA:fitGraph(defaults,width,height));setAnnouncement('Graph layout reset.');};
 const fitLayout=()=>{
  cancelDrag();
  setCamera(fitGraph(placed,width,height));
 };
 const arrange=(mode:'network'|'lineage')=>{cancelDrag();const points=mode==='network'?networkLayout(placed,edges,width,height,pinned):lineageLayout(placed,width,pinned);setArrangements(old=>({...old,[layoutKey]:{...old[layoutKey],...points}}));setLayoutModes(old=>({...old,[layoutKey]:mode}));setCamera(fitGraph(placed.map(node=>({...node,...points[node.id]})),width,height));setAnnouncement(`${mode==='network'?'Network':'Lineage'} layout applied. Pinned nodes kept their positions.`);};
 const togglePin=(id:string)=>{setPinSets(old=>{const current=old[layoutKey]||[];return{...old,[layoutKey]:current.includes(id)?current.filter(value=>value!==id):[...current,id]};});setAnnouncement(`${nodeName(id)} ${pinned.has(id)?'unpinned':'pinned for automatic layouts'}.`);};
 const toggleType=(kind:string)=>{cancelDrag();setHiddenTypes(old=>old.includes(kind)?old.filter(value=>value!==kind):[...old,kind]);setSelected(null);setHovered('');setSheet(false);};
 const toggleExpansion=async(id:string)=>{
  const node=graph?.nodes.find(value=>value.id===id);if(!node||expanding||loading)return;
  if(overview){explore(node.type);return;}
  setExpansionError('');
  if(expansions[id]){const remaining={...expansions};delete remaining[id];const reachable=new Set(mergeScene(baseGraph!,remaining).nodes.map(value=>value.id));setExpansions(Object.fromEntries(Object.entries(remaining).filter(([key])=>reachable.has(key))));setAnnouncement(`${node.label} expansion collapsed.`);return;}
  const controller=new AbortController(),generation=requestGeneration.current;expansionRequest.current=controller;setExpanding(id);
  // Freeze all existing positions. A later response must preserve any intervening manual drag.
  setArrangements(old=>({...old,[layoutKey]:{...Object.fromEntries(placed.map(value=>[value.id,{x:value.x,y:value.y}])),...old[layoutKey]}}));
  const query=new URLSearchParams({level:'instances',focus:id,limit:'1'});selectedIds.forEach(value=>query.append('dataset_id',value));
  try{const data=await api('/metadata-relationships?'+query,'GET',undefined,controller.signal,true) as Graph;if(controller.signal.aborted||generation!==requestGeneration.current||latestContext.current!==requestContext)return;if(!data.nodes?.some(value=>value.id===id))throw new Error('The selected record was not returned by the scoped catalog.');
   setArrangements(old=>{const existing=placed.map(value=>({...value,...old[layoutKey]?.[value.id]})),incoming=data.nodes.map(value=>({...value,x:0,y:0,r:43}));return{...old,[layoutKey]:{...old[layoutKey],...expansionPositions(existing,incoming,id)}};});setExpansions(old=>({...old,[id]:data}));setAnnouncement(`${node.label} connections expanded.`);
  }catch(reason){if(!controller.signal.aborted&&generation===requestGeneration.current&&latestContext.current===requestContext)setExpansionError(reason instanceof Error?reason.message:'Could not expand connections.');}
  finally{if(!controller.signal.aborted&&generation===requestGeneration.current&&latestContext.current===requestContext)setExpanding('');}
 };
 const canvasPoint=(event:PointerEvent<SVGSVGElement>):Point|null=>{
  const matrix=svg.current?.getScreenCTM()?.inverse();if(!matrix)return null;
  return{x:matrix.a*event.clientX+matrix.c*event.clientY+matrix.e,y:matrix.b*event.clientX+matrix.d*event.clientY+matrix.f};
 };
 const pointerDown=(event:PointerEvent<SVGSVGElement>)=>{
  if(event.button!==0||event.isPrimary===false||drag.current)return;
  const canvas=canvasPoint(event);if(!canvas)return;
  const id=(event.target as Element).closest('[data-metadata-node]')?.getAttribute('data-metadata-node'),node=id?lookup.get(id):null;
  dragMoved.current=false;drag.current={pointerId:event.pointerId,client:{x:event.clientX,y:event.clientY},canvas,camera,node:node?{id:node.id,position:{x:node.x,y:node.y}}:null,moved:false};
 };
 const pointerMove=(event:PointerEvent<SVGSVGElement>)=>{
  const start=drag.current;if(!start||start.pointerId!==event.pointerId||!svg.current)return;
  // Also recover if a browser/window interruption lost the pointer-up notification.
  if(event.buttons===0){cancelDrag();return;}
  if(!start.moved&&Math.hypot(event.clientX-start.client.x,event.clientY-start.client.y)<8)return;
  const point=canvasPoint(event);if(!point)return;
  if(!start.moved){start.moved=true;svg.current.setPointerCapture(event.pointerId);setDragging(start.node?.id||'canvas');}
  event.preventDefault();const dx=point.x-start.canvas.x,dy=point.y-start.canvas.y;
  if(start.node)moveNode(start.node.id,{x:start.node.position.x+dx/start.camera.zoom,y:start.node.position.y+dy/start.camera.zoom});
  else setCamera({...start.camera,x:start.camera.x+dx,y:start.camera.y+dy});
 };
 const pointerEnd=(event:PointerEvent<SVGSVGElement>)=>{
  const start=drag.current;if(!start||start.pointerId!==event.pointerId)return;
  dragMoved.current=start.moved||event.type==='pointercancel';drag.current=null;setDragging(null);
  if(start.moved&&start.node)setAnnouncement(`${nodeName(start.node.id)} moved.`);
  if(svg.current?.hasPointerCapture(event.pointerId))svg.current.releasePointerCapture(event.pointerId);
 };
 const chooseEdge=(id:string)=>{setSelected({kind:'edge',id});setSheet(true);};
 const nodeName=(id:string)=>graph?.nodes.find(n=>n.id===id)?.label||id;
 const onKey=(event:KeyboardEvent<SVGGElement>,action:()=>void)=>{if(event.key==='Enter'||event.key===' '){event.preventDefault();action();}};
 const nodeKey=(event:KeyboardEvent<SVGGElement>,id:string)=>{
  if(event.altKey||event.ctrlKey||event.metaKey||drag.current)return;
  const node=lookup.get(id);if(!node)return;
  const step=event.shiftKey?40:10,delta:Record<string,Point>={ArrowLeft:{x:-step,y:0},ArrowRight:{x:step,y:0},ArrowUp:{x:0,y:-step},ArrowDown:{x:0,y:step}};
  if(delta[event.key]){event.preventDefault();moveNode(id,{x:node.x+delta[event.key].x,y:node.y+delta[event.key].y});setAnnouncement(`${node.label} moved.`);}
  else if(event.key==='Home'){event.preventDefault();resetNode(id);setAnnouncement(`${node.label} returned to its starting position.`);}
  else onKey(event,()=>selectNode(id));
 };
 const fields=(data:Record<string,string|number>)=><dl>{Object.entries(data).filter(([,value])=>value!==''&&value!==null&&value!==undefined).map(([key,value])=><div key={key}><dt>{key}</dt><dd>{key==='Reviewed at'&&typeof value==='number'?new Date(value*1000).toLocaleString():String(value)}</dd></div>)}</dl>;
 const openRecord=(node:GraphNode)=>{if(node.action?.kind==='extraction'){onClose();onReview(node.action.id);}};
 return <dialog ref={dialog} className="metadata-dialog" aria-labelledby="metadata-title" onCancel={event=>{event.preventDefault();if(sheet&&phone)closeSheet();else if(picker)setPicker(false);else onClose();}}>
  <header className="metadata-heading"><button type="button" className="btn metadata-back" aria-label="Back to Dashboard" title="Back to Dashboard" onClick={onClose}><ArrowLeft size={15}/><span>Back to Dashboard</span></button><div className="metadata-title"><span>CONNECTED WORKSPACE</span><h2 id="metadata-title">Metadata Relationships</h2><p>Follow your datasets from original documents to reviewed results.</p></div><span className="metadata-readonly"><ShieldCheck size={13}/>Read-only metadata</span></header>
  <div className="metadata-tools"><div className="metadata-dataset-picker"><button type="button" className="btn" aria-expanded={picker} aria-controls="metadata-dataset-options" onClick={()=>{setDraft(selectedIds);setPicker(!picker);}}><Database size={15}/>{selectedIds.length} dataset{selectedIds.length===1?'':'s'}<ChevronDown size={13}/></button>{picker&&<div id="metadata-dataset-options" className="metadata-picker-menu"><strong>Dataset scope</strong><p>Inspect saved metadata, including files that are not indexed. Chat file filters do not apply.</p><div className="metadata-picker-list">{datasets.map(dataset=><label key={dataset.id}><input type="checkbox" aria-label={`Show metadata for ${dataset.name}`} checked={draft.includes(dataset.id)} onChange={()=>setDraft(ids=>ids.includes(dataset.id)?ids.filter(id=>id!==dataset.id):[...ids,dataset.id])}/><span>{dataset.name}{dataset.active===false&&<small>Inactive · saved metadata only</small>}</span></label>)}</div><div className="metadata-picker-actions"><button type="button" className="btn" onClick={()=>setPicker(false)}>Cancel</button><button type="button" className="btn primary" disabled={draft.length>100} onClick={()=>{setSelectedIds(draft);setFilter(OVERVIEW);setPicker(false);}}>Apply selection</button></div>{draft.length>100&&<p role="alert">Choose up to 100 datasets.</p>}</div>}</div>
   <label className="metadata-search"><Search size={15}/><input aria-label="Find metadata records" placeholder="Find a dataset, document or run…" maxLength={200} value={filter.search} onChange={event=>setFilter({level:event.target.value?'instances':'overview',category:'',focus:'',offset:0,search:event.target.value})}/></label><button type="button" className="btn icon" aria-label={list?'Show relationship graph':'Show metadata list'} aria-pressed={list} onClick={()=>setList(!list)}><List size={17}/></button><button type="button" className="btn icon" aria-label="Refresh metadata relationships" disabled={loading} onClick={()=>setRevision(value=>value+1)}><RefreshCw size={16}/></button>
  </div>
  <div className="metadata-content"><section className="metadata-canvas" aria-label="Metadata relationship explorer" aria-busy={loading}><div className="metadata-canvas-top"><div><button type="button" onClick={reset}>Overview</button>{!overview&&<><ChevronRight size={12}/><span>{filter.search?'Search results':filter.focus?'Connected records':filter.category?kinds[filter.category as Kind].plural:'Records'}</span></>}</div><span><i/>{loading?'Reading metadata…':error?'Unavailable':graph?.generated_at?'Snapshot loaded':'Choose datasets'}</span></div>
   <div className="metadata-totals"><span><b>{graph?.totals.nodes??'—'}</b> records</span><span><b>{graph?.totals.edges??'—'}</b> relationships</span><small>Totals for selected datasets</small></div>
   {error?<div className="metadata-empty" role="alert"><Network size={28}/><h3>Metadata could not be loaded</h3><p>{error}</p><button type="button" className="btn" onClick={()=>setRevision(value=>value+1)}>Try again</button></div>:loading?<div className="metadata-empty" role="status"><Network size={28}/><h3>Reading saved relationships</h3><p>No chat, model call or knowledge search is running.</p></div>:!graph?.nodes.length?<div className="metadata-empty"><Database size={30}/><h3>{selectedIds.length?'No matching metadata':'Choose dataset metadata'}</h3><p>{filter.search?'Try a different record name or identifier.':'Select one or more accessible datasets to explore their saved relationships.'}</p>{filter.search&&<button type="button" className="btn" onClick={reset}>Clear search</button>}</div>:<>
    <div className="metadata-explore-tools" hidden={list}>
     <div className="metadata-view-tabs" role="group" aria-label="Metadata graph view"><button type="button" aria-label="Show category overview" aria-pressed={overview} onClick={reset}><Layers size={13}/>Categories</button><button type="button" aria-label="Explore metadata records" aria-pressed={!overview} onClick={()=>explore('')}><Network size={13}/>Records</button></div>
     <div className="metadata-layout-tools" role="group" aria-label="Graph layout controls"><button type="button" aria-label="Arrange as network" title="Arrange as network" aria-pressed={layoutModes[layoutKey]==='network'||(!overview&&!layoutModes[layoutKey])} disabled={!placed.length} onClick={()=>arrange('network')}><Network size={15}/></button><button type="button" aria-label="Arrange as lineage" title="Arrange as lineage" aria-pressed={layoutModes[layoutKey]==='lineage'} disabled={!placed.length} onClick={()=>arrange('lineage')}><GitFork size={15}/></button><button type="button" aria-label={showLabels?'Hide relationship labels':'Show relationship labels'} title={showLabels?'Hide relationship labels':'Show relationship labels'} aria-pressed={showLabels} onClick={()=>setLabelOverride(!showLabels)}><Tag size={15}/></button><button type="button" aria-label="Clear graph selection" title="Clear graph selection" disabled={!selected&&!hovered} onClick={()=>{setSelected(null);setHovered('');setSheet(false);}}><Focus size={15}/></button></div>
     <span className="metadata-scene-count">{placed.length} nodes · {edges.length} links</span>{hiddenTypes.length>0&&<button type="button" className="metadata-show-types" onClick={()=>setHiddenTypes([])}>Show all types</button>}
    </div>
    {expansionError&&<p className="metadata-expansion-message error" role="alert">Connections could not be expanded: {expansionError}</p>}{expanding&&<p className="metadata-expansion-message" role="status">Reading saved connections…</p>}
    {(graph.truncated||visibleNodes.length>placed.length)&&<p className="metadata-view-limit" role="status">This graph shows {placed.length} records. More related records may be available; refine the dataset scope or search to explore them.</p>}
    <div className="metadata-graph-stage" hidden={list}><svg ref={svg} role="group" viewBox={`0 0 ${width} ${height}`} aria-label="Metadata relationship graph" aria-describedby={`${prefix}-move-help`} data-dragging={dragging?true:undefined} onClick={event=>{if(!dragMoved.current&&(event.target as Element).hasAttribute('data-metadata-background')){setSelected(null);setHovered('');setSheet(false);}}} onPointerDown={pointerDown} onPointerMove={pointerMove} onPointerUp={pointerEnd} onPointerCancel={pointerEnd} onPointerLeave={event=>{if(drag.current?.pointerId===event.pointerId&&!svg.current?.hasPointerCapture(event.pointerId))cancelDrag();}} onLostPointerCapture={event=>{if(event.target===svg.current)pointerEnd(event);}}><defs><pattern id={`${prefix}-dots`} width="25" height="25" patternUnits="userSpaceOnUse"><circle cx="1" cy="1" r="1" className="metadata-grid-dot"/></pattern><marker id={`${prefix}-arrow`} viewBox="0 0 10 10" refX="8" refY="5" markerWidth="6" markerHeight="6" orient="auto"><path d="M0 0L10 5L0 10Z" className="metadata-arrow"/></marker></defs><rect data-metadata-background="true" width="100%" height="100%" fill={`url(#${prefix}-dots)`}/><g transform={`translate(${camera.x} ${camera.y}) scale(${camera.zoom})`}>
     {edges.map(edge=>{const a=lookup.get(edge.source)!,b=lookup.get(edge.target)!,{path,x,y}=relationshipGeometry(a,b,bends.get(edge.id)||0,overview&&phone&&edge.source==='Dataset'&&edge.target==='Model');const text=edge.label+(edge.count?' · '+edge.count:''),width=Math.min(180,text.length*(phone?6.4:5.3)+15);return <g key={edge.id} role="button" tabIndex={0} aria-label={`${nodeName(edge.source)} ${edge.label} ${nodeName(edge.target)}${edge.count?' · '+edge.count+' relationships':''}`} className={`metadata-edge${selected?.id===edge.id?' selected':''}${hasHighlight&&!highlight.edges.has(edge.id)?' dimmed':''}`} data-label-hidden={!showLabels||undefined} onClick={()=>{if(!dragMoved.current)chooseEdge(edge.id);}} onKeyDown={event=>onKey(event,()=>chooseEdge(edge.id))}><path className="metadata-edge-line" d={path} markerEnd={`url(#${prefix}-arrow)`}/><path d={path} stroke="transparent" strokeWidth={24} fill="none"/><rect x={x-width/2} y={y-11} width={width} height={22} rx={5}/><text x={x} y={y+4}>{text}</text></g>;})}
     {placed.map(node=>{const Icon=kinds[node.type].Icon,color=kinds[node.type].color,lines=words(overview?kinds[node.type].plural:node.label,overview?16:13),selectedHere=selected?.id===node.id;return <g key={node.id} role="button" tabIndex={0} aria-label={`${overview?kinds[node.type].plural:node.label}${node.count!==undefined?' · '+node.count+' records':''}`} aria-describedby={`${prefix}-move-help`} className={`metadata-node${selectedHere?' selected':''}${hasHighlight&&!highlight.nodes.has(node.id)?' dimmed':''}`} data-expanded={Boolean(expansions[node.id])||undefined} data-pinned={pinned.has(node.id)||undefined} data-record={!overview||undefined} data-metadata-node={node.id} data-dragging={dragging===node.id?true:undefined} onClick={()=>{if(!dragMoved.current)selectNode(node.id);}} onKeyDown={event=>nodeKey(event,node.id)} onPointerEnter={event=>{if(event.pointerType==='mouse'||event.pointerType==='pen')setHovered(node.id);}} onPointerLeave={()=>setHovered(value=>value===node.id?'':value)} onDoubleClick={event=>{event.preventDefault();if(!dragMoved.current)void toggleExpansion(node.id);}}><title>{node.label} · Drag to move · Double-click to explore</title><circle className="metadata-node-halo" cx={node.x} cy={node.y} r={node.r+8} stroke={color}/><circle className="metadata-node-disc" cx={node.x} cy={node.y} r={node.r} fill={color} stroke={color}/><circle className="metadata-node-type-badge" cx={node.x-node.r+11} cy={node.y-node.r+11} r={11} stroke={color}/><Icon className="metadata-node-type-icon" x={node.x-node.r+5} y={node.y-node.r+5} size={12} color={color}/>{pinned.has(node.id)&&<Pin className="metadata-pin-marker" x={node.x+node.r-14} y={node.y-node.r} size={16} fill="white" color={color}/>}<text className="metadata-node-label" x={node.x} y={node.y-(lines.length-1)*10-(overview?8:4)}>{lines.map((line,i)=><tspan key={i} x={node.x} dy={i?20:0}>{line}</tspan>)}</text>{overview?<><path d={`M${node.x-28} ${node.y+17}H${node.x+28}`} stroke={color} opacity={.3}/><text className="metadata-node-count" x={node.x} y={node.y+38}>{node.count}</text></>:<text className="metadata-node-status" x={node.x} y={node.y+30}>{node.status}{node.version?' · v'+node.version:''}</text>}</g>;})}
    </g></svg><div className="metadata-camera"><button type="button" aria-label="Zoom relationships in" title="Zoom in" onClick={()=>setZoom(.2)}><Plus size={14}/></button><span>{Math.round(camera.zoom*100)}%</span><button type="button" aria-label="Zoom relationships out" title="Zoom out" onClick={()=>setZoom(-.2)}><Minus size={14}/></button><button type="button" aria-label="Fit relationships to screen" title="Fit to screen" onClick={fitLayout}><Maximize size={14}/></button><button type="button" aria-label="Reset node layout" title="Reset node layout" onClick={resetLayout}><RotateCcw size={14}/></button></div></div>
    <p id={`${prefix}-move-help`} className="metadata-graph-help" hidden={list}>Drag nodes · Double-click to explore · Pan background · Scroll to zoom<span className="sr-only">. Select a node to highlight its connections and see details. With a node focused, use arrow keys to move it, Shift and arrow keys for larger steps, and Home to reset its position.</span></p>
    <div className="metadata-record-list" hidden={!list}>{graph.nodes.filter(node=>!hiddenTypes.includes(node.type)).map(node=><button type="button" key={node.id} onClick={()=>selectNode(node.id)}><i style={{background:kinds[node.type].color}}/><span><strong>{overview?kinds[node.type].plural:node.label}</strong><small>{overview?`${node.count} records`:node.type+' · '+node.status}</small></span><ChevronRight size={15}/></button>)}</div>
    {!overview&&<div className="metadata-pagination"><span>{filter.focus?'Connected records':`${graph.total_items} matching records · page ${Math.floor(filter.offset/12)+1}`}{graph.related_total>displayNodes.length&&!list?` · ${displayNodes.length} records shown`:''}{Object.keys(expansions).length?' · Includes expanded connections':''}{graph.truncated&&list?' · Loaded view is limited; refine the scope or search to explore more.':''}</span>{!filter.focus&&<div><button type="button" className="btn" disabled={!filter.offset} onClick={()=>setFilter(old=>({...old,offset:Math.max(0,old.offset-12)}))}>Previous</button><button type="button" className="btn" disabled={!graph.has_more} onClick={()=>setFilter(old=>({...old,offset:old.offset+12}))}>Next</button></div>}</div>}
   </>}
   <div className="metadata-legend" role="group" aria-label="Visible entity types">{Object.entries(kinds).map(([kind,def])=><button key={kind} type="button" onClick={()=>toggleType(kind)} aria-pressed={!hiddenTypes.includes(kind)} aria-label={`${hiddenTypes.includes(kind)?'Show':'Hide'} ${def.plural.toLowerCase()} ${hiddenTypes.includes(kind)?'in':'from'} graph`} title={`${hiddenTypes.includes(kind)?'Show':'Hide'} ${def.plural.toLowerCase()}`} disabled={loading||!graph?.totals.categories[kind as Kind]}><i style={{background:def.color}}/>{def.plural}<small>{graph?.totals.categories[kind as Kind]||0}</small></button>)}</div>
  </section>
  {phone&&sheet&&<button type="button" className="metadata-sheet-backdrop" aria-label="Dismiss metadata details" onClick={closeSheet}/>}
  <aside ref={details} className={`metadata-details${phone&&sheet?' open':''}`} aria-label="Metadata record details" role={phone&&sheet?'dialog':undefined} aria-modal={phone&&sheet?true:undefined} onKeyDown={event=>{if(phone&&sheet&&event.key==='Tab'){const buttons=[...details.current!.querySelectorAll<HTMLButtonElement>('button:not(:disabled)')],first=buttons[0],last=buttons.at(-1);if(event.shiftKey&&document.activeElement===first){event.preventDefault();last?.focus();}else if(!event.shiftKey&&document.activeElement===last){event.preventDefault();first?.focus();}}}}>
   <div className="metadata-sheet-handle"/><button type="button" className="btn icon metadata-close-details" aria-label="Close metadata details" onClick={closeSheet}><X size={17}/></button>
   {selectedNode?<><span className="metadata-eyebrow">{overview?'ENTITY CATEGORY':selectedNode.type.toUpperCase()}</span><div className="metadata-detail-icon" style={{color:kinds[selectedNode.type].color}}>{(()=>{const Icon=kinds[selectedNode.type].Icon;return <Icon size={25}/>;})()}</div><h3>{overview?kinds[selectedNode.type].plural:selectedNode.label}</h3><p>{kinds[selectedNode.type].description}</p><div className="metadata-detail-actions"><button type="button" className="btn" aria-label={pinned.has(selectedNode.id)?'Unpin node position':'Pin node position'} aria-pressed={pinned.has(selectedNode.id)} onClick={()=>togglePin(selectedNode.id)}>{pinned.has(selectedNode.id)?<PinOff size={14}/>:<Pin size={14}/>}<span>{pinned.has(selectedNode.id)?'Unpin position':'Pin position'}</span></button>{!overview&&<button type="button" className="btn" aria-label={expansions[selectedNode.id]?'Collapse node expansion':'Expand node connections'} disabled={Boolean(expanding)} onClick={()=>void toggleExpansion(selectedNode.id)}>{expansions[selectedNode.id]?<Minus size={14}/>:<Plus size={14}/>}<span>{expanding===selectedNode.id?'Reading connections…':expansions[selectedNode.id]?'Collapse expansion':'Expand connections'}</span></button>}</div>{overview?<>{fields({'Visible records':selectedNode.count||0,'Established by':'Saved Aegis metadata'})}<button type="button" className="btn primary metadata-explore" onClick={()=>explore(selectedNode.type)}>Explore {kinds[selectedNode.type].plural.toLowerCase()}<ArrowRight size={14}/></button></>:<>{fields({'Status':selectedNode.status,...selectedNode.attributes,'Datasets':selectedNode.dataset_ids.map(id=>datasets.find(d=>d.id===id)?.name||'Dataset').join(', ')})}<button type="button" className="btn metadata-explore" onClick={()=>explore('',selectedNode.id)}><Network size={15}/>Focus connected records</button>{selectedNode.action?.kind==='extraction'&&<button type="button" className="btn primary metadata-explore" onClick={()=>openRecord(selectedNode)}>Open extraction in Review<ArrowRight size={14}/></button>}{selectedNode.action?.kind==='document'&&<a className="btn metadata-explore" href={`/api/documents/${encodeURIComponent(selectedNode.action.id)}/source`} target="_blank" rel="noreferrer">Open original document<ArrowRight size={14}/></a>}<div className="metadata-detail-section"><h4>Connections in this page</h4>{graph?.edges.filter(e=>e.source===selectedNode.id||e.target===selectedNode.id).map(edge=><button type="button" key={edge.id} onClick={()=>{setSelected({kind:'edge',id:edge.id});}}><span>{edge.label}<small>{nodeName(edge.source===selectedNode.id?edge.target:edge.source)}</small></span><ChevronRight size={13}/></button>)}</div></>}</>:selectedEdge?<><span className="metadata-eyebrow">SAVED RELATIONSHIP</span><div className="metadata-detail-icon"><Network size={25}/></div><h3>{nodeName(selectedEdge.source)} → {nodeName(selectedEdge.target)}</h3><p>{selectedEdge.label}</p>{fields({'Direction':'Source → target',...(selectedEdge.count?{'Visible relationships':selectedEdge.count}:{}),...(selectedEdge.relationships||{})})}<p>These links come from saved identifiers and versions. They do not indicate a new processing operation.</p><button type="button" className="btn metadata-explore" onClick={()=>selectNode(selectedEdge.source)}>Inspect source node<ArrowRight size={14}/></button></>:<><span className="metadata-eyebrow">FOLLOW YOUR DATA</span><div className="metadata-detail-icon"><Network size={26}/></div><h3>Every result has a source.</h3><p>Explore the saved connections behind your dataset knowledge.</p><ol><li>Select a node to highlight its connections and inspect properties.</li><li>Double-click to explore records or expand their connections in place.</li><li>Pin a node to keep its position when arranging the network or lineage.</li></ol><div className="metadata-detail-note"><ShieldCheck size={15}/>Dataset access is checked before records, relationships and counts are returned.</div></>}
  </aside></div>
  <p className="sr-only" role="status" aria-live="polite">{announcement}</p><footer className="metadata-footer"><span><ShieldCheck size={12}/>Your selected datasets · Metadata only · No inference</span><span>{graph?.generated_at?'Read '+new Date(graph.generated_at*1000).toLocaleTimeString():''}</span></footer>{graph?.warnings.length? <p className="metadata-warning" role="status">{graph.warnings.join(' ')}</p>:null}
 </dialog>;
}
