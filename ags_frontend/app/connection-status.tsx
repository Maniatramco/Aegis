"use client";
import {useEffect,useState} from 'react';
import {createPortal} from 'react-dom';
import {Cloud,HardDrive,CircleHelp} from 'lucide-react';
import './connection-status.css';
type Destination={provider:string;name:string;region?:string;endpoint?:string;detail?:string};
type Connections=Record<'files'|'database'|'knowledge',Destination>&{services?:Record<string,Destination>};
type Api=(path:string)=>Promise<any>;

export function ConnectionStatus({api,revision}:{api:Api;revision:number}){
 const [connections,setConnections]=useState<Connections|null>(null);
 const [unavailable,setUnavailable]=useState(false);
 const [detail,setDetail]=useState<{id:string;left:number;bottom:number}|null>(null);
 const [origin,setOrigin]=useState('');
 useEffect(()=>{
  setOrigin(window.location.origin);
  const outside=(event:PointerEvent)=>{if(!(event.target instanceof Element)||!event.target.closest('.connection-status-item,.connection-status-popup'))setDetail(null);};
  const escape=(event:KeyboardEvent)=>{if(event.key==='Escape')setDetail(null);};
  const resize=()=>setDetail(null);
  document.addEventListener('pointerdown',outside);document.addEventListener('keydown',escape);window.addEventListener('resize',resize);
  return()=>{document.removeEventListener('pointerdown',outside);document.removeEventListener('keydown',escape);window.removeEventListener('resize',resize);};
 },[]);
 useEffect(()=>{
  let active=true,inFlight=false;
  const load=async()=>{if(inFlight)return;inFlight=true;try{const result=await api('/storage/status');if(active){setConnections(result);setUnavailable(false);}}catch{if(active){setConnections(null);setUnavailable(true);}}finally{inFlight=false;}};
  void load();
  const timer=window.setInterval(()=>{if(document.visibilityState==='visible')void load();},60000);
  window.addEventListener('focus',load);
  return ()=>{active=false;window.clearInterval(timer);window.removeEventListener('focus',load);};
 },[api,revision]);
 const unknown={provider:'unknown',name:'Not reported',detail:'Hosting location has not been reported by this deployment.'};
 const items:(Destination&{id:string;label:string})[]=connections?[
  {id:'files',label:'Storage',...connections.files,name:connections.files.provider==='local'?'Application filesystem':connections.files.name,detail:'Active destination for new documents and result files. Existing files retain their saved destination.'},
  {id:'database',label:'Database',...connections.database,name:connections.database.provider==='local'?'Application database':connections.database.name,detail:'Stores application records, users, datasets and extraction metadata.'},
  {id:'knowledge',label:'Vector DB',...connections.knowledge,detail:'Knowledge index for documents, metadata and published extraction results.'},
  {id:'api',label:'FastAPI',...(connections.services?.api||unknown)},
  {id:'web',label:'WebApp',...(connections.services?.web||unknown),endpoint:origin},
  {id:'worker',label:'Worker',...(connections.services?.worker||unknown)},
  {id:'models',label:'AI models',...(connections.services?.models||unknown)},
 ]:[];
 const selected=items.find(item=>item.id===detail?.id);
 const location=(provider:string)=>provider==='oci'?'OCI':provider==='local'?'Local':'Unknown';
 const show=(id:string,element:HTMLElement)=>{const rect=element.getBoundingClientRect();setDetail({id,left:Math.max(8,Math.min(rect.left,window.innerWidth-328)),bottom:window.innerHeight-rect.top+8});};
 return <><footer className="connection-status" aria-label="Live service connections" onScroll={()=>setDetail(null)}>
  <span className="connection-status-caption">Connections</span>
  {!connections?<span className="connection-status-pending">{unavailable?'Status unavailable · refresh to retry':'Checking destinations…'}</span>:
   items.map(item=>{
    const Icon=item.provider==='oci'?Cloud:item.provider==='local'?HardDrive:CircleHelp;
    return <button type="button" key={item.id} className="connection-status-item" aria-label={`${item.label}: ${location(item.provider)}. Show connection details`} aria-describedby={detail?.id===item.id?'connection-detail':undefined} onMouseEnter={event=>show(item.id,event.currentTarget)} onMouseLeave={()=>setDetail(null)} onFocus={event=>show(item.id,event.currentTarget)} onBlur={()=>setDetail(null)} onClick={event=>show(item.id,event.currentTarget)}>
     <Icon size={13} aria-hidden="true"/><span>{item.label}: <strong>{location(item.provider)}</strong></span>
    </button>;
   })}
 </footer>{detail&&selected&&typeof document!=='undefined'&&createPortal(<aside id="connection-detail" role="tooltip" className="connection-status-popup" style={{left:detail.left,bottom:detail.bottom}}>
  <h3>{selected.label}<span>{location(selected.provider)}</span></h3>
  <p>{selected.detail}</p>
  <dl><dt>Connection</dt><dd>{selected.name}</dd>{selected.region&&<><dt>Region</dt><dd>{selected.region}</dd></>}{selected.endpoint&&<><dt>Endpoint</dt><dd>{selected.endpoint}</dd></>}</dl>
 </aside>,document.body)}</>;
}
