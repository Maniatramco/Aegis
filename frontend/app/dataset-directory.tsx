"use client";
import {useState} from "react";
import {ArrowRight,CheckCircle2,Database,FileText,Search,Settings2} from "lucide-react";
import "./workspace-flow.css";
import "./home-cards.css";
type Entity=Record<string,any>;
export function DirectoryRows({datasets,documents,onChat,onOpen}:{datasets:Entity[];documents:Entity[];onChat:(id:string)=>void;onOpen:(id:string)=>void}) {
 const [search,setSearch]=useState("");
 return <div><label className="directory-search"><Search size={18}/><input aria-label="Search datasets" placeholder="Search datasets…" value={search} onChange={e=>setSearch(e.target.value)}/></label><div className="directory-table">{datasets.filter(d=>`${d.name} ${d.description||""}`.toLowerCase().includes(search.toLowerCase())).map(d=>{const docs=documents.filter(doc=>(doc.dataset_id||doc.kb_id)===d.id),ready=docs.filter(doc=>doc.status==="ready"&&!doc.requires_reindex).length,failed=docs.filter(doc=>["failed","cancelled"].includes(doc.status)).length,pending=docs.filter(doc=>["queued","processing"].includes(doc.status)).length;return <article className="directory-row" key={d.id}><a href={`#dataset/${d.id}`} className="directory-name" aria-label={`Open dataset ${d.name}`} onClick={()=>onOpen(d.id)}>{d.name}</a><span>{docs.length} documents<small>{ready} ready</small></span><span className={`directory-status ${failed?"failed":pending?"pending":"ready"}`}>{failed?`${failed} failed`:pending?`${pending} processing`:ready===docs.length&&docs.length?"Ready":docs.length?"Reindex required":"No documents"}{d.active===false&&<small>Inactive</small>}</span><button className="btn" onClick={()=>onChat(d.id)}>Open chat<ArrowRight size={15}/></button></article>;})}{!datasets.some(d=>`${d.name} ${d.description||""}`.toLowerCase().includes(search.toLowerCase()))&&<div className="directory-empty"><h3>No matching datasets</h3><p>Try another name or description.</p><button className="btn" onClick={()=>setSearch("")}>Clear search</button></div>}</div></div>;
}
export function DatasetHome({datasets,loading,onBrowse,documents,onChat}:{datasets:Entity[];loading:boolean;onBrowse:()=>void;documents:Entity[];onChat:(id:string)=>void}) {
 const [search,setSearch]=useState("");
 const visible=datasets.filter(d=>`${d.name} ${d.description||""}`.toLowerCase().includes(search.toLowerCase()));
 return <section className="home-datasets" aria-label="Your datasets">
 <div className="home-datasets-header"><div className="home-datasets-heading"><h2>Your datasets</h2><span>{visible.length}{search?` of ${datasets.length}`:''} dataset{datasets.length===1?'':'s'}</span></div>
 <label className="home-datasets-search"><Search size={16} aria-hidden="true"/><input aria-label="Search datasets" placeholder="Search datasets…" value={search} onChange={e=>setSearch(e.target.value)}/></label></div>
 {loading&&!datasets.length?<p role="status">Loading datasets…</p>:<div className="home-card-grid">{visible.map(d=>{
 const all=documents.filter(doc=>(doc.dataset_id||doc.kb_id)===d.id),ready=all.filter(doc=>doc.status==="ready"&&!doc.requires_reindex).length,active=all.filter(doc=>["queued","processing"].includes(doc.status)).length,failed=all.filter(doc=>["failed","cancelled"].includes(doc.status)).length,stale=all.filter(doc=>doc.status==="ready"&&doc.requires_reindex).length;
 const status=failed?`${failed} failed`:active?`${active} processing`:stale?`${stale} need reindex`:all.length?"Ready":"No documents";
 const state=failed?'failed':active||stale?'pending':all.length?'ready':'empty';
 return <article className="home-dataset-card" key={d.id} aria-label={`Dataset ${d.name}`}>
   <div className="home-card-heading"><span className="home-card-icon"><Database size={18} aria-hidden="true"/></span><div className="home-card-title"><h3><a href={`#dataset/${encodeURIComponent(d.id)}`} aria-label={`Open dataset ${d.name}`} title={d.name} className="directory-name">{d.name}</a></h3>{d.active===false&&<span className="home-card-inactive">Inactive</span>}</div><a className="btn icon home-card-settings" href={`#dataset/${encodeURIComponent(d.id)}`} aria-label={`Settings for ${d.name}`} title="Dataset settings"><Settings2 size={15}/></a></div>
   {d.description&&<p className="home-card-description" title={d.description}>{d.description}</p>}
   <div className="home-card-metrics"><span><FileText size={14} aria-hidden="true"/><strong>{all.length}</strong> document{all.length===1?'':'s'}</span><span className={ready?'home-card-ready':undefined}><CheckCircle2 size={14} aria-hidden="true"/>{ready} ready</span></div>
   <div className="home-card-footer"><span className="home-card-status" data-state={state}>{status}</span><button type="button" className="btn home-card-chat" onClick={()=>onChat(d.id)}>Open chat<ArrowRight size={14}/></button></div>
 </article>;
 })}{!visible.length&&<div className="directory-empty">{datasets.length?<><p>No datasets match your search.</p><button type="button" className="btn" onClick={()=>setSearch('')}>Clear search</button></>:<><h3>No registered datasets yet</h3><p>Visit Datasets to create your first dataset.</p><button className="btn" onClick={onBrowse}>Browse datasets</button></>}</div>}</div>}
 <p className="home-datasets-note">Accessible datasets only. Status reflects your stored documents and current indexes.</p></section>;
}
