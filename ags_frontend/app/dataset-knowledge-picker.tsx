"use client";
import {useEffect,useRef,useState} from 'react';
import {ChevronDown,CloudUpload,Database,FileText,Search,X} from 'lucide-react';
import {availableKnowledge} from './dataset-knowledge-scope';
type Entity=Record<string,any>;
export type DatasetKnowledgeScope={datasetIds:string[];documentIds:string[]|null};
const datasetOf=(doc:Entity)=>doc.dataset_id||doc.kb_id||doc.parent_id;
export function DatasetKnowledgePicker({datasets,documents,initial,onInclude,onAddNew,onClose}:{datasets:Entity[];documents:Entity[];initial:DatasetKnowledgeScope;onInclude:(scope:DatasetKnowledgeScope)=>void;onAddNew?:()=>void;onClose:()=>void}){
 const dialog=useRef<HTMLDialogElement>(null),[search,setSearch]=useState('');
 const available=availableKnowledge(datasets,documents);
 const [selected,setSelected]=useState<string[]>(()=>initial.documentIds||available.filter(doc=>initial.datasetIds.includes(datasetOf(doc))).map(doc=>doc.id));
 // Datasets already in the chat start open; the rest stay compact until needed.
 const [open,setOpen]=useState<string[]>(()=>datasets.filter(d=>available.some(doc=>datasetOf(doc)===d.id&&selected.includes(doc.id))).map(d=>d.id));
 useEffect(()=>{dialog.current?.showModal();return()=>dialog.current?.close();},[]);
 const include=()=>{const chosen=available.filter(doc=>selected.includes(doc.id));onInclude({datasetIds:[...new Set(chosen.map(datasetOf))].sort(),documentIds:chosen.map(doc=>doc.id).sort()});};
 const query=search.trim().toLowerCase();
 const groups=datasets.map(dataset=>{const docs=available.filter(doc=>datasetOf(doc)===dataset.id);return {dataset,docs,matching:docs.filter(doc=>`${dataset.name} ${doc.name}`.toLowerCase().includes(query))};});
 const ready=groups.filter(g=>g.docs.length&&(!query||g.matching.length||g.dataset.name.toLowerCase().includes(query)));
 const waiting=groups.filter(g=>!g.docs.length&&(!query||g.dataset.name.toLowerCase().includes(query)));
 const chosen=available.filter(doc=>selected.includes(doc.id)),chosenSets=new Set(chosen.map(datasetOf)).size;
 return <dialog ref={dialog} className="dataset-knowledge-picker picker-v2" aria-labelledby="knowledge-picker-title" onCancel={onClose}>
  <header className="picker-hero"><div><span className="picker-eyebrow">Dataset knowledge</span><h2 id="knowledge-picker-title">Add Dataset Knowledge</h2><p>Choose whole datasets or individual indexed files for this chat. Nothing is uploaded or changed.</p></div><button type="button" className="picker-close" aria-label="Close dataset knowledge picker" onClick={onClose}><X size={18}/></button></header>
  <label className="picker-search"><Search size={16}/><input aria-label="Search available dataset knowledge" placeholder="Search datasets or files" value={search} onChange={e=>setSearch(e.target.value)}/></label>
  <div className="picker-list">
   {ready.map(({dataset,docs,matching})=>{
    const count=docs.filter(doc=>selected.includes(doc.id)).length,all=count===docs.length,partial=count>0&&!all,expanded=open.includes(dataset.id)||Boolean(query);
    return <section key={dataset.id} className="picker-dataset" data-selected={count>0}>
     <div className="picker-dataset-row">
      <button type="button" className="picker-expand" aria-expanded={expanded} aria-controls={`picker-files-${dataset.id}`} aria-label={`${expanded?'Hide':'Show'} files in ${dataset.name}`} onClick={()=>setOpen(current=>current.includes(dataset.id)?current.filter(id=>id!==dataset.id):[...current,dataset.id])}><ChevronDown size={16}/></button>
      <span className="picker-dataset-icon"><Database size={18}/></span>
      <span className="picker-dataset-copy"><strong>{dataset.name}</strong><small>{docs.length} indexed file{docs.length===1?'':'s'}</small></span>
      {count>0&&<span className="picker-count">{all?'All files':`${count} of ${docs.length}`}</span>}
      <input type="checkbox" aria-label={`Include dataset ${dataset.name}`} checked={all} ref={element=>{if(element)element.indeterminate=partial;}} onChange={()=>setSelected(current=>all?current.filter(id=>!docs.some(doc=>doc.id===id)):[...new Set([...current,...docs.map(doc=>doc.id)])])}/>
     </div>
     <ul id={`picker-files-${dataset.id}`} className="picker-files" hidden={!expanded}>{matching.map(doc=><li key={doc.id}><label><FileText size={15}/><span title={doc.name}>{doc.name}</span><input type="checkbox" aria-label={`Include available file ${doc.name}`} checked={selected.includes(doc.id)} onChange={()=>setSelected(current=>current.includes(doc.id)?current.filter(id=>id!==doc.id):[...current,doc.id])}/></label></li>)}</ul>
    </section>;})}
   {!ready.length&&<p className="picker-empty">{query?'No indexed datasets or files match your search.':'No indexed files are available yet.'}</p>}
   {waiting.length>0&&<p className="picker-waiting"><strong>Not ready yet</strong> {waiting.map(g=>g.dataset.name).join(', ')} · no indexed files</p>}
  </div>
  {onAddNew&&<div className="picker-new"><span className="picker-new-icon"><CloudUpload size={18}/></span><span><strong>Not here yet?</strong><small>Bring documents from Amazon S3, Azure Blob, OCI Object Storage, SharePoint or Google Drive.</small></span><button type="button" className="btn" onClick={onAddNew}>Add new knowledge from cloud storage</button></div>}
  <footer className="picker-footer"><span>{chosen.length?`${chosen.length} file${chosen.length===1?'':'s'} from ${chosenSets} dataset${chosenSets===1?'':'s'}`:'No files selected'}</span><button type="button" className="btn" onClick={onClose}>Cancel</button><button type="button" className="btn primary" disabled={!chosen.length} onClick={include}>Include selected knowledge</button></footer>
 </dialog>;
}
