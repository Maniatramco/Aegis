"use client";
import {ActionButton} from "./action-button";
import { useEffect, useRef, useState } from "react";
type Dataset={id:string;name:string;description?:string;active?:boolean};
export function DatasetAssignments({api,account,onClose}:{api:(path:string,method?:string,body?:any)=>Promise<any>;account:{id:string;username:string};onClose:()=>void}){
 const [datasets,setDatasets]=useState<Dataset[]>([]),[selected,setSelected]=useState<string[]>([]),[search,setSearch]=useState("");
 const [loading,setLoading]=useState(true),[loaded,setLoaded]=useState(false),[revision,setRevision]=useState(0),[saving,setSaving]=useState(false),[error,setError]=useState(""),[notice,setNotice]=useState("");
 const ref=useRef<HTMLElement>(null);
 useEffect(()=>{let active=true;setLoading(true);setLoaded(false);setError("");setNotice("");setSearch("");
  Promise.all([api('/datasets'),api(`/users/${encodeURIComponent(account.id)}/datasets`)]).then(([catalog,mapping])=>{if(active){setDatasets(catalog);setSelected(mapping.dataset_ids);setLoaded(true);}}).catch(e=>{if(active)setError(e instanceof Error?e.message:'Unable to load dataset assignments.');}).finally(()=>{if(active)setLoading(false);});
  ref.current?.scrollIntoView({block:'nearest'});ref.current?.focus({preventScroll:true});return()=>{active=false;};
 },[account.id,revision]);
 async function save(){setSaving(true);setError("");setNotice("");try{await api(`/users/${encodeURIComponent(account.id)}/datasets`,'PUT',{dataset_ids:selected});setNotice(`Saved dataset access for ${account.username}. New requests use these assignments immediately. Refresh the user's screen to update its list.`);}catch(e){setError(e instanceof Error?e.message:'Assignments were not saved.');}finally{setSaving(false);}}
 return <section ref={ref} tabIndex={-1} className="card dataset-assignments" aria-label={`Dataset access for ${account.username}`}>
  <h2>Dataset access · {account.username}</h2><p className="muted small">Choose the datasets this user can work with. Assigned users can upload documents, chat, extract, and review shared results. Only the administrator can change assignments or model configuration.</p>
  {loading&&<p role="status">Loading dataset access…</p>}
  {!loading&&loaded&&<>
   <label className="account-search" htmlFor="assignment-search"><input id="assignment-search" value={search} placeholder="Filter datasets" onChange={e=>setSearch(e.target.value)} disabled={saving}/></label>
   <div className="assignment-list">{datasets.filter(dataset=>dataset.name.toLowerCase().includes(search.toLowerCase())).map(dataset=><label key={dataset.id} className="assignment-option"><input type="checkbox" checked={selected.includes(dataset.id)} disabled={saving} onChange={e=>{setNotice("");setSelected(previous=>e.target.checked?[...previous,dataset.id]:previous.filter(id=>id!==dataset.id));}}/><span><strong>{dataset.name}</strong>{dataset.active===false&&<small>Inactive dataset</small>}{dataset.description&&<small>{dataset.description}</small>}</span></label>)}</div>
   {!datasets.length&&<p className="muted small">Create a dataset in Datasets first, then assign it here.</p>}
   <p className="muted small">{selected.length} assigned dataset{selected.length===1?'':'s'}. With no assignments, this user sees no datasets.</p>
  </>}
  {error&&<div className="notice error" role="alert">{error}</div>}
  {notice&&<div className="notice" role="status">{notice}</div>}
  <div className="row"><button className="btn primary" disabled={loading||saving||!loaded} onClick={()=>void save()}>{saving?'Saving…':'Save dataset access'}</button>{!loaded&&!loading&&<ActionButton className="btn" onClick={()=>setRevision(value=>value+1)} label="Retry" action="retry"/>}<ActionButton className="btn" disabled={saving} onClick={onClose} label="Close" action="close"/></div>
 </section>;
}
