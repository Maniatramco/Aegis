"use client";
import {useEffect,useRef,useState} from "react";
import {ArrowRight,CheckCircle2,Database,FileText,Search,Settings2,X} from "lucide-react";
import "./workspace-flow.css";
import "./home-cards.css";
type Entity=Record<string,any>;
export function DirectoryRows({datasets,documents,onChat,onOpen}:{datasets:Entity[];documents:Entity[];onChat:(id:string)=>void;onOpen:(id:string)=>void}) {
 const [search,setSearch]=useState("");
 return <div><label className="directory-search"><Search size={18}/><input aria-label="Search datasets" placeholder="Search datasets…" value={search} onChange={e=>setSearch(e.target.value)}/></label><div className="directory-table">{datasets.filter(d=>`${d.name} ${d.description||""}`.toLowerCase().includes(search.toLowerCase())).map(d=>{const docs=documents.filter(doc=>(doc.dataset_id||doc.kb_id)===d.id),ready=docs.filter(doc=>doc.status==="ready"&&!doc.requires_reindex).length,failed=docs.filter(doc=>["failed","cancelled"].includes(doc.status)).length,pending=docs.filter(doc=>["queued","processing"].includes(doc.status)).length;return <article className="directory-row" key={d.id}><a href={`#dataset/${d.id}`} className="directory-name" aria-label={`Open dataset ${d.name}`} onClick={()=>onOpen(d.id)}>{d.name}</a><span>{docs.length} documents<small>{ready} ready</small></span><span className={`directory-status ${failed?"failed":pending?"pending":"ready"}`}>{failed?`${failed} failed`:pending?`${pending} processing`:ready===docs.length&&docs.length?"Ready":docs.length?"Reindex required":"No documents"}{d.active===false&&<small>Inactive</small>}</span><button className="btn" onClick={()=>onChat(d.id)}>Open chat<ArrowRight size={15}/></button></article>;})}{!datasets.some(d=>`${d.name} ${d.description||""}`.toLowerCase().includes(search.toLowerCase()))&&<div className="directory-empty"><h3>No matching datasets</h3><p>Try another name or description.</p><button className="btn" onClick={()=>setSearch("")}>Clear search</button></div>}</div></div>;
}
export function DatasetSearch({value,onChange}:{value:string;onChange:(value:string)=>void}){
 const [open,setOpen]=useState(false),container=useRef<HTMLDivElement>(null),input=useRef<HTMLInputElement>(null),button=useRef<HTMLButtonElement>(null);
 const close=()=>{setOpen(false);onChange('');button.current?.focus();};
 useEffect(()=>{if(!open)return;input.current?.focus();const outside=(event:PointerEvent)=>{if(!container.current?.contains(event.target as Node)){setOpen(false);onChange('');}};document.addEventListener('pointerdown',outside);return()=>document.removeEventListener('pointerdown',outside);},[open,onChange]);
 return <div className="home-search-control" ref={container} onKeyDown={event=>{if(event.key==='Escape'&&open){event.stopPropagation();close();}}}>
  <button type="button" className="btn icon" ref={button} aria-label={open?'Close dataset search':'Search datasets'} title="Search datasets" aria-expanded={open} aria-controls="home-dataset-search" onClick={()=>open?close():setOpen(true)}><Search size={18}/></button>
  {open&&<div className="home-search-popover" id="home-dataset-search"><label className="home-datasets-search"><Search size={16} aria-hidden="true"/><input ref={input} aria-label="Search datasets" placeholder="Search datasets…" value={value} onChange={event=>onChange(event.target.value)}/></label><button type="button" className="btn icon" aria-label="Clear and close dataset search" title="Close search" onClick={close}><X size={16}/></button></div>}
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
   <div className="home-card-heading"><span className="home-card-icon"><Database size={18} aria-hidden="true"/></span><div className="home-card-title"><h3><a href={`#dataset/${encodeURIComponent(d.id)}`} aria-label={`Open dataset ${d.name}`} title={d.name} className="directory-name">{d.name}</a></h3>{d.active===false&&<span className="home-card-inactive">Inactive</span>}</div>{canManage&&<a className="btn icon home-card-settings" href={`#dataset/${encodeURIComponent(d.id)}`} aria-label={`Settings for ${d.name}`} title="Dataset settings"><Settings2 size={15}/></a>}</div>
   {d.description&&<p className="home-card-description" title={d.description}>{d.description}</p>}
   <div className="home-card-metrics"><span><FileText size={14} aria-hidden="true"/><strong>{all.length}</strong> document{all.length===1?'':'s'}</span><span className={ready?'home-card-ready':undefined}><CheckCircle2 size={14} aria-hidden="true"/>{ready} ready</span></div>
   <div className="home-card-footer"><span className="home-card-status" data-state={state}>{status}</span><button type="button" className="btn home-card-chat" onClick={()=>onChat(d.id)}>Open chat<ArrowRight size={14}/></button></div>
 </article>;
 })}{!visible.length&&<div className="directory-empty">{datasets.length?<><p>No datasets match your search.</p><button type="button" className="btn" onClick={onClearSearch}>Clear search</button></>:<><h3>{canManage?'No registered datasets yet':'No datasets assigned'}</h3><p>{canManage?'Visit Datasets to create your first dataset.':'Ask your administrator to assign a dataset to your account.'}</p><button className="btn" onClick={onBrowse}>Browse datasets</button></>}</div>}</div>}
 </section>;
}
