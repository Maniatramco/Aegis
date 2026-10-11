"use client";
import {Search,FileSearch,ArrowRight} from 'lucide-react';
import {useState} from 'react';
type Entity=Record<string,any>;
export function extractionDataset(e:Entity,documents:Entity[]=[]){
 return e.dataset_id||e.parent_id||documents.find(d=>e.document_ids?.includes(d.id))?.dataset_id||'';
}
export function matchingExtractions(extractions:Entity[],dataset:string,query:string,status:string,documents:Entity[]=[]){
 const q=query.trim().toLocaleLowerCase();
 return extractions.filter(e=>(!dataset||extractionDataset(e,documents)===dataset)&&(!status||e.status===status)&&
  (!q||[e.id,e.name,e.merge?.filename,...(e.merge?.sources||[]).map((s:Entity)=>s.name),...(e.document_ids||[]).map((id:string)=>documents.find(d=>d.id===id)?.name)].filter(Boolean).join(' ').toLocaleLowerCase().includes(q)))
  .sort((a,b)=>Number(b.created_at)-Number(a.created_at));
}
export function ExtractionDirectory({datasets,extractions,documents,selectedDataset,selectedId,onDatasetChange,onOpen,busy}:{datasets:Entity[];extractions:Entity[];documents:Entity[];selectedDataset:string;selectedId?:string;onDatasetChange:(id:string)=>void;onOpen:(id:string)=>void;busy?:boolean}){
 const [query,setQuery]=useState(''),[status,setStatus]=useState('');
 const rows=matchingExtractions(extractions,selectedDataset,query,status,documents);
 return <section className="extraction-directory" aria-label="Extraction results directory">
  <div className="extraction-directory-head"><div><h2>Find an extraction</h2><p className="muted small">Select a dataset and extraction ID to inspect saved results.</p></div><span className="small muted">{rows.length} {rows.length===1?'extraction':'extractions'}</span></div>
  <div className="extraction-directory-filters">
   <label>Dataset<select aria-label="Review dataset filter" value={selectedDataset} onChange={e=>onDatasetChange(e.target.value)} disabled={busy}><option value="">All datasets</option>{datasets.map(d=><option key={d.id} value={d.id}>{d.name}</option>)}</select></label>
   <label className="extraction-id-search">Extraction ID or file<div><Search size={16}/><input aria-label="Search extraction ID or filename" placeholder="Paste an extraction ID or search files" value={query} onChange={e=>setQuery(e.target.value)}/></div></label>
   <label>Status<select aria-label="Review status filter" value={status} onChange={e=>setStatus(e.target.value)}><option value="">All statuses</option>{['ready','queued','processing','failed','cancelled'].map(s=><option key={s} value={s}>{s==='ready'?'Ready to review':s[0].toUpperCase()+s.slice(1)}</option>)}</select></label>
  </div>
  <div className="extraction-directory-results">
   {rows.length?<table><thead><tr><th>Extraction ID / file</th><th>Dataset</th><th>Status / version</th><th>Created</th><th><span className="sr-only">Open result</span></th></tr></thead><tbody>{rows.map(e=>{
    const ds=datasets.find(d=>d.id===extractionDataset(e,documents));
    const filename=e.merge?.filename||documents.find(d=>e.document_ids?.includes(d.id))?.name||e.name;
    const count=e.profile_count??e.result?.records?.length??(e.result!=null?1:0);
    return <tr key={e.id} className={e.id===selectedId?'selected':''}><td><button className="extraction-id-link" onClick={()=>onOpen(e.id)} disabled={busy} aria-label={`Open extraction ${e.id}`} aria-current={e.id===selectedId?'true':undefined}><code>{e.id}</code></button><strong>{filename}</strong><small>{e.merge?.sources?.length?`${e.merge.sources.length} merged files · `:''}{count?`${count} ${count===1?'profile / item':'profiles / items'}`:'Results pending'}</small></td><td>{ds?.name||'Dataset unavailable'}</td><td><span className={`extraction-status ${e.status}`}>{e.status==='ready'?'Ready':e.status}</span><small>v{e.version||1} · {e.review_status||'unreviewed'}</small></td><td>{e.created_at?new Date(e.created_at*1000).toLocaleString():'—'}</td><td><button className="btn icon" aria-label={`Review extraction ${e.id}`} onClick={()=>onOpen(e.id)} disabled={busy}><ArrowRight size={16}/></button></td></tr>;
   })}</tbody></table>:<div className="extraction-directory-empty"><FileSearch size={24}/><p>No extractions match this dataset, ID and status.</p></div>}
  </div>
 </section>;
}
