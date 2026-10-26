"use client";
import {ActionButton} from "./action-button";
import {useEffect,useRef,useState} from "react";
import {CheckCircle2,Database,FileText,MessageSquare,Search,Trash2,X} from "lucide-react";
import "./workspace-flow.css";
import "./home-cards.css";
import "./dataset-directory.css";
import {openAttention} from "./needs-attention";
type Entity=Record<string,any>;
/** Readiness across the datasets this user can see, from loaded documents only. */
export function directorySummary(datasets:Entity[],documents:Entity[]){
 const per=datasets.map(d=>{const docs=documents.filter(doc=>(doc.dataset_id||doc.kb_id)===d.id);return {docs,ready:docs.filter(doc=>doc.status==="ready"&&!doc.requires_reindex).length,failed:docs.filter(doc=>["failed","cancelled"].includes(doc.status)).length};});
 return [
  {label:'Datasets',value:datasets.length,detail:`${datasets.filter(d=>d.active===false).length} inactive`,tone:''},
  {label:'Ready to ask',value:per.filter(p=>p.ready>0).length,detail:'with indexed documents',tone:'ok'},
  {label:'Need attention',value:per.filter(p=>p.failed>0).length,detail:'have failed documents',tone:'error',attention:{}},
  {label:'No documents',value:per.filter(p=>!p.docs.length).length,detail:'waiting for uploads',tone:'warn'},
 ];
}
export function DirectoryRows({datasets,documents,onChat,search,onClearSearch,onDelete}:{datasets:Entity[];documents:Entity[];onChat:(id:string)=>void;search:string;onClearSearch:()=>void;onDelete?:(dataset:Entity)=>void}) {
 const visible=datasets.filter(d=>`${d.name} ${d.description||""}`.toLowerCase().includes(search.trim().toLowerCase()));
 return <div className="dataset-directory-list">
  <div className="dataset-directory-table" role="region" aria-label="Dataset results" tabIndex={0}>
   <table aria-label="Registered datasets">
    <thead><tr><th scope="col">Dataset</th><th scope="col">Description</th><th scope="col" className="dataset-count">Documents</th><th scope="col" className="dataset-count">Ready</th><th scope="col">Status</th><th scope="col">Actions</th></tr></thead>
    <tbody>{visible.map(d=>{
     const docs=documents.filter(doc=>(doc.dataset_id||doc.kb_id)===d.id),ready=docs.filter(doc=>doc.status==="ready"&&!doc.requires_reindex).length,failed=docs.filter(doc=>["failed","cancelled"].includes(doc.status)).length,pending=docs.filter(doc=>["queued","processing"].includes(doc.status)).length;
     const status=failed?`${failed} failed`:pending?`${pending} processing`:ready===docs.length&&docs.length?"Ready":docs.length?"Reindex required":"No documents";
     const state=failed?'failed':pending||ready!==docs.length?'pending':docs.length?'ready':'empty';
     return <tr key={d.id}>
      <th scope="row"><span className="directory-name" title={d.name}>{d.name}</span>{d.active===false&&<small>Inactive</small>}</th>
      <td><span className="dataset-directory-description" title={d.description||undefined}>{d.description||'—'}</span></td>
      <td className="dataset-count">{docs.length}</td><td className="dataset-count">{ready}</td>
      <td>{failed||docs.some(doc=>doc.status==="ready"&&doc.requires_reindex)?<button type="button" className="dataset-directory-status attention-trigger" data-state={state} title="See what needs attention and how to fix it" onClick={()=>openAttention({datasetId:d.id})}>{status}</button>:<span className="dataset-directory-status" data-state={state}>{status}</span>}</td>
      <td><div className="dataset-row-actions"><button type="button" className="btn icon dataset-directory-chat" aria-label={`Open chat for ${d.name}`} title={`Open chat for ${d.name}`} onClick={()=>onChat(d.id)}><MessageSquare size={17}/><span className="dataset-action-label">Ask</span></button>{onDelete&&<button type="button" className="btn icon dataset-delete" aria-label={`Delete dataset ${d.name}`} title={`Delete dataset ${d.name}`} onClick={()=>onDelete(d)}><Trash2 size={16}/></button>}</div></td>
     </tr>;
    })}{!visible.length&&<tr><td colSpan={6}><div className="directory-empty"><h3>No matching datasets</h3><p>Try another name or description.</p><ActionButton type="button" className="btn" onClick={onClearSearch} label="Clear search" action="close"/></div></td></tr>}</tbody>
   </table>
  </div>
 </div>;
}
export function DatasetSearch({value,onChange}:{value:string;onChange:(value:string)=>void}){
 const [open,setOpen]=useState(false),container=useRef<HTMLDivElement>(null),input=useRef<HTMLInputElement>(null),button=useRef<HTMLButtonElement>(null);
 const close=()=>{setOpen(false);onChange('');button.current?.focus();};
 useEffect(()=>{if(!open)return;input.current?.focus();const outside=(event:MouseEvent)=>{if(!container.current?.contains(event.target as Node)){setOpen(false);onChange('');}};document.addEventListener('click',outside);return()=>document.removeEventListener('click',outside);},[open,onChange]);
 return <div className="home-search-control" data-expanded={open} ref={container} onKeyDown={event=>{if(event.key==='Escape'&&open){event.stopPropagation();close();}}}>
  <div className="home-search-reveal" id="home-dataset-search" aria-hidden={!open} inert={!open}><label className="home-datasets-search"><input ref={input} aria-label="Search datasets" placeholder="Search datasets…" tabIndex={open?0:-1} value={value} onChange={event=>onChange(event.target.value)}/></label></div>
  <button type="button" className="btn icon" ref={button} aria-label={open?'Close dataset search':'Search datasets'} title={open?'Close search':'Search datasets'} aria-expanded={open} aria-controls="home-dataset-search" onClick={()=>open?close():setOpen(true)}>{open?<X size={18}/>:<Search size={18}/>}</button>
 </div>;
}
export function DatasetHome({datasets,loading,onBrowse,documents,onChat,canManage=true,search='',onClearSearch=()=>{}}:{datasets:Entity[];loading:boolean;onBrowse:()=>void;documents:Entity[];onChat:(id:string)=>void;canManage?:boolean;search?:string;onClearSearch?:()=>void}) {
 const visible=datasets.filter(d=>`${d.name} ${d.description||""}`.toLowerCase().includes(search.toLowerCase()));
 return <section className="home-datasets" aria-label="Your datasets">
 {loading&&(!datasets.length||!documents.length)?<div className="home-card-grid" aria-hidden="true">{[1,2,3].map(id=><div key={id} className="skeleton" style={{height:140,borderRadius:12}} />)}</div>:<div className="home-card-grid">{visible.map(d=>{
 const all=documents.filter(doc=>(doc.dataset_id||doc.kb_id)===d.id),ready=all.filter(doc=>doc.status==="ready"&&!doc.requires_reindex).length,active=all.filter(doc=>["queued","processing"].includes(doc.status)).length,failed=all.filter(doc=>["failed","cancelled"].includes(doc.status)).length,stale=all.filter(doc=>doc.status==="ready"&&doc.requires_reindex).length;
 const status=failed?`${failed} failed`:active?`${active} processing`:stale?`${stale} need reindex`:all.length?"Ready":"No documents";
 const state=failed?'failed':active||stale?'pending':all.length?'ready':'empty';
 return <article className="home-dataset-card" key={d.id} aria-label={`Dataset ${d.name}`}>
   <div className="home-card-heading"><span className="home-card-icon"><Database size={18} aria-hidden="true"/></span><div className="home-card-title"><h3><span title={d.name} className="directory-name">{d.name}</span></h3>{d.active===false&&<span className="home-card-inactive">Inactive</span>}</div></div>
   {d.description&&<p className="home-card-description" title={d.description}>{d.description}</p>}
   <div className="home-card-metrics"><span><FileText size={14} aria-hidden="true"/><strong>{all.length}</strong> document{all.length===1?'':'s'}</span><span className={ready?'home-card-ready':undefined}><CheckCircle2 size={14} aria-hidden="true"/>{ready} ready</span></div>
   <div className="home-card-footer"><span className="home-card-status" data-state={state}>{status}</span><ActionButton type="button" className="btn home-card-chat" onClick={()=>onChat(d.id)} label={`Open chat for ${d.name}`} action="chat"/></div>
 </article>;
 })}{!visible.length&&<div className="directory-empty">{datasets.length?<><p>No datasets match your search.</p><ActionButton type="button" className="btn" onClick={onClearSearch} label="Clear search" action="close"/></>:<><h3>{canManage?'No registered datasets yet':'No datasets assigned'}</h3><p>{canManage?'Visit Datasets to create your first dataset.':'Ask your administrator to assign a dataset to your account.'}</p><ActionButton className="btn" onClick={onBrowse} label="Browse datasets" action="documents"/></>}</div>}</div>}
 </section>;
}
