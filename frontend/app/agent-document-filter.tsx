"use client";
import {useEffect,useRef,useState} from 'react';
import {Filter,X} from 'lucide-react';
import {documentOptionLabel,matchingDocuments} from './agent-document-selection';
type Entity=Record<string,any>;
export function AgentDocumentFilter({documents,selected,onChange,disabled}:{documents:Entity[];selected:string[];onChange:(ids:string[])=>void;disabled:boolean}){
 const [open,setOpen]=useState(false);const [query,setQuery]=useState('');const root=useRef<HTMLDivElement>(null);
 useEffect(()=>{const close=(event:PointerEvent)=>{if(!root.current?.contains(event.target as Node))setOpen(false);};document.addEventListener('pointerdown',close);return()=>document.removeEventListener('pointerdown',close);},[]);
 useEffect(()=>{if(disabled)setOpen(false);},[disabled]);
 return <div ref={root} className="agent-v2-document-filter" onKeyDown={e=>{if(e.key==='Escape'){setOpen(false);root.current?.querySelector('button')?.focus();}}}>
  <button className="btn agent-v2-filter-trigger" aria-label="Filter documents" aria-expanded={open} aria-controls="agent-document-filter" disabled={disabled} onClick={()=>{setOpen(!open);setQuery('');}}><Filter size={15}/><span>Documents{selected.length?` · ${selected.length}`:''}</span></button>
  {open&&<div id="agent-document-filter" className="agent-v2-document-popover" role="dialog" aria-label="Filter dataset documents">
   <div className="agent-v2-picker-heading"><strong>Filter documents</strong><button className="btn icon" aria-label="Close document filter" onClick={()=>setOpen(false)}><X size={15}/></button></div>
   <input autoFocus aria-label="Search dataset documents" placeholder="Search documents…" value={query} onChange={e=>setQuery(e.target.value)}/>
   <button className="text-button" onClick={()=>onChange([])}>Use all ready documents</button>
   <div className="agent-v2-document-options">{matchingDocuments(documents,query).map(d=><label key={d.id}><input type="checkbox" checked={selected.includes(d.id)} disabled={!selected.includes(d.id)&&selected.length>=20} onChange={e=>onChange(e.target.checked?[...selected,d.id]:selected.filter(id=>id!==d.id))}/><span>{documentOptionLabel(d,documents)}</span></label>)}{!matchingDocuments(documents,query).length&&<p>No matching ready documents.</p>}</div>
   <p className="muted small">{selected.length?`${selected.length}/20 selected`:'All ready documents'} · Type # in your message to choose a document.</p>
  </div>}
 </div>;
}
