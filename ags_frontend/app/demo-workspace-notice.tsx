"use client";
import {useRef,useState} from 'react';
/** Fixture metadata only controls this notice; it never grants application access. */
export function DemoWorkspaceNotice({onChanged,onJobs}:{onChanged:()=>void;onJobs:()=>void}){
 const details=useRef<HTMLDetailsElement>(null),locked=useRef(false);
 const [busy,setBusy]=useState(false),[message,setMessage]=useState('');
 const run=async()=>{if(locked.current)return;locked.current=true;setBusy(true);setMessage('');try{const response=await fetch('/api/_demo/start-index',{method:'POST'});const data=await response.json();if(!response.ok)throw new Error(data.detail||'The local scenario could not start.');setMessage('Synthetic indexing queued. Follow its real stage changes in Jobs & activity.');onChanged();}catch(error){setMessage((error as Error).message);}finally{locked.current=false;setBusy(false);}};
 return <details ref={details} className="demo-workspace-menu" onKeyDown={event=>{if(event.key==='Escape'&&details.current?.open){details.current.open=false;details.current.querySelector('summary')?.focus();}}}>
  <summary className="pill" aria-label="Local demo using synthetic data. Open demo controls">Local demo<span className="demo-synthetic-label"> · synthetic data</span></summary>
  <div role="region" aria-label="Local demo controls"><strong>Local preview · synthetic data only</strong><p>This isolated workspace uses scripted model responses and local sample files. No real accounts, documents or external services are connected. Sample changes reset when the preview restarts.</p><p>Try “Summarize the key points” or “What is the project reference?” in Aegis Agent. Provider setup is read-only; uploads accept only the supplied synthetic sample.</p><button type="button" className="btn" disabled={busy} onClick={()=>void run()}>{busy?'Starting scenario…':'Run indexing demo'}</button><button type="button" className="btn" onClick={()=>{if(details.current)details.current.open=false;onJobs();}}>Open Jobs & activity</button><a href="/api/_demo/sample" download>Download synthetic sample TXT</a><a href="/?demo=sign-in">View sign-in preview</a>{message&&<p role="status">{message}</p>}</div>
 </details>;
}
