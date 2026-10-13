"use client";
import {useEffect,useState} from 'react';
import {Cloud,HardDrive} from 'lucide-react';
import './connection-status.css';
type Destination={provider:string;name:string;region?:string};
type Connections=Record<'files'|'database'|'knowledge',Destination>;
type Api=(path:string)=>Promise<any>;

export function ConnectionStatus({api,revision}:{api:Api;revision:number}){
 const [connections,setConnections]=useState<Connections|null>(null);
 const [unavailable,setUnavailable]=useState(false);
 useEffect(()=>{
  let active=true;
  const load=async()=>{try{const result=await api('/storage/status');if(active){setConnections(result);setUnavailable(false);}}catch{if(active){setConnections(null);setUnavailable(true);}}};
  void load();
  const timer=window.setInterval(()=>{if(document.visibilityState==='visible')void load();},60000);
  window.addEventListener('focus',load);
  return ()=>{active=false;window.clearInterval(timer);window.removeEventListener('focus',load);};
 },[api,revision]);
 return <footer className="connection-status" aria-label="Active storage destinations" aria-live="polite">
  <span className="connection-status-caption">Active destinations</span>
  {!connections?<span className="connection-status-pending">{unavailable?'Status unavailable · refresh to retry':'Checking destinations…'}</span>:
   (['files','database','knowledge'] as const).map(key=>{
    const destination=connections[key],remote=destination.provider==='oci',Icon=remote?Cloud:HardDrive;
    const label={files:'Files',database:'Database',knowledge:'Knowledge'}[key];
    return <span key={key} className="connection-status-item" title={`${label}: ${remote?'OCI':'Local'} · ${destination.name}${destination.region?' · '+destination.region:''}${key==='files'?' · Destination for new files; existing files retain their saved location.':''}`}>
     <Icon size={13} aria-hidden="true"/><span>{label}: <strong>{remote?'OCI':'Local'}</strong></span>
     <span className="connection-status-name">{destination.name}</span>
    </span>;
   })}
 </footer>;
}
