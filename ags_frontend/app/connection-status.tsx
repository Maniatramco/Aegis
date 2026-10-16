"use client";
import {useCallback,useEffect,useId,useRef,useState} from 'react';
import {createPortal} from 'react-dom';
import {Cloud,HardDrive,CircleHelp,Network,ChevronUp,X} from 'lucide-react';
import {version} from './application-version.json';
import {connectionLocation,modelConnectionSummary,type ModelDataset} from './runtime-connections';
import './connection-status.css';

type Destination={provider:string;name:string;region?:string;endpoint?:string;detail?:string;locations?:string[]};
type Connections=Record<'files'|'database'|'knowledge',Destination>&{services?:Record<string,Destination>};
type Api=(path:string)=>Promise<any>;

export function ConnectionStatus({api,revision,datasets,datasetId}:{api:Api;revision:number;datasets?:ModelDataset[];datasetId?:string}){
 const [connections,setConnections]=useState<Connections|null>(null);
 const [unavailable,setUnavailable]=useState(false);
 const [open,setOpen]=useState(false);
 const [position,setPosition]=useState({left:8,bottom:44,maxHeight:560});
 const [origin,setOrigin]=useState('');
 const trigger=useRef<HTMLButtonElement>(null);
 const popup=useRef<HTMLElement>(null);
 const pinned=useRef(false);
 const closeTimer=useRef<number|undefined>(undefined);
 const popupId=useId();
 const clearClose=useCallback(()=>{window.clearTimeout(closeTimer.current);},[]);
 const close=useCallback(()=>{clearClose();pinned.current=false;setOpen(false);},[clearClose]);
 const show=()=>{
  clearClose();
  const rect=trigger.current?.getBoundingClientRect();
  if(!rect)return;
  setPosition({left:Math.max(8,Math.min(rect.left,window.innerWidth-568)),bottom:window.innerHeight-rect.top+8,maxHeight:Math.max(80,rect.top-16)});
  setOpen(true);
 };
 const leave=()=>{
  clearClose();
  if(!pinned.current&&!popup.current?.contains(document.activeElement))closeTimer.current=window.setTimeout(()=>setOpen(false),180);
 };
 const blur=(next:EventTarget|null)=>{
  if(next instanceof Node&&(trigger.current?.contains(next)||popup.current?.contains(next)))return;
  close();
 };
 useEffect(()=>{
  setOrigin(window.location.origin);
  const outside=(event:PointerEvent)=>{if(event.target instanceof Node&&!trigger.current?.contains(event.target)&&!popup.current?.contains(event.target))close();};
  const escape=(event:KeyboardEvent)=>{if(event.key==='Escape'){if(popup.current?.contains(document.activeElement))trigger.current?.focus();close();}};
  document.addEventListener('pointerdown',outside);document.addEventListener('keydown',escape);window.addEventListener('resize',close);
  return()=>{clearClose();document.removeEventListener('pointerdown',outside);document.removeEventListener('keydown',escape);window.removeEventListener('resize',close);};
 },[clearClose,close]);
 useEffect(()=>{
  let active=true,inFlight=false;
  const load=async()=>{if(inFlight)return;inFlight=true;try{const result=await api('/storage/status');if(active){setConnections(result);setUnavailable(false);}}catch{if(active){setConnections(null);setUnavailable(true);}}finally{inFlight=false;}};
  void load();
  const timer=window.setInterval(()=>{if(document.visibilityState==='visible')void load();},60000);
  window.addEventListener('focus',load);
  return ()=>{active=false;window.clearInterval(timer);window.removeEventListener('focus',load);};
 },[api,revision]);
 const modelHost=datasets===undefined?connections?.services?.models:modelConnectionSummary(datasets,datasetId);
 const unknown={provider:'unknown',name:'Not reported',detail:'Hosting location has not been reported by this deployment.'};
 const items:(Destination&{id:string;label:string})[]=connections?[
  {id:'files',label:'Storage',...connections.files,name:connections.files.provider==='local'?'Application filesystem':connections.files.name,detail:'Active destination for new documents and result files. Existing files retain their saved destination.'},
  {id:'database',label:'Database',...connections.database,name:connections.database.provider==='local'?'Application database':connections.database.name,detail:'Stores application records, users, datasets and extraction metadata.'},
  {id:'knowledge',label:'Vector DB',...connections.knowledge,detail:'Knowledge index for documents, metadata and published extraction results.'},
  {id:'api',label:'FastAPI',...(connections.services?.api||unknown)},
  {id:'web',label:'WebApp',...(connections.services?.web||unknown),endpoint:origin},
  {id:'worker',label:'Worker',...(connections.services?.worker||unknown)},
  {id:'models',label:'AI models',...(modelHost||unknown)},
 ]:[];
 const location=(item:Destination)=>item.locations?.length?item.locations.map(connectionLocation).join(' / '):connectionLocation(item.provider);
 return <><footer className="connection-status" aria-label="Application status">
  <button ref={trigger} type="button" className="connection-status-trigger" aria-expanded={open} aria-controls={open?popupId:undefined} onMouseEnter={show} onMouseLeave={leave} onFocus={show} onBlur={event=>blur(event.relatedTarget)} onClick={()=>{if(pinned.current)close();else{pinned.current=true;show();}}}>
   <Network size={14} aria-hidden="true"/><span>Connections</span><ChevronUp size={12} aria-hidden="true"/>
  </button>
  <span className="application-version" aria-label={`Application version v${version}`}>v{version}</span>
 </footer>{open&&typeof document!=='undefined'&&createPortal(<section ref={popup} id={popupId} role="region" aria-label="Connection details" className="connection-status-popup" style={{left:position.left,bottom:position.bottom,maxHeight:position.maxHeight}} onMouseEnter={clearClose} onMouseLeave={leave} onFocus={clearClose} onBlur={event=>blur(event.relatedTarget)}>
  <header><h2>Connections</h2><button type="button" aria-label="Close connection details" onClick={()=>{trigger.current?.focus();close();}}><X size={15} aria-hidden="true"/></button></header>
  {!connections?<p className="connection-status-pending" role="status">{unavailable?'Status unavailable · refresh to retry':'Checking destinations…'}</p>:<div className="connection-status-grid">{items.map(item=>{
   const Icon=item.provider==='local'?HardDrive:item.provider==='unknown'?CircleHelp:Cloud;
   return <article className="connection-status-card" key={item.id}>
    <h3><span><Icon size={13} aria-hidden="true"/>{item.label}</span><span className="connection-status-location">{location(item)}</span></h3>
    <p>{item.detail}</p><dl><dt>Connection</dt><dd>{item.name}</dd>{item.region&&<><dt>Region</dt><dd>{item.region}</dd></>}{item.endpoint&&<><dt>Endpoint</dt><dd>{item.endpoint}</dd></>}</dl>
   </article>;
  })}</div>}
 </section>,document.body)}</>;
}