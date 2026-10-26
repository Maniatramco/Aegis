"use client";
import {ActionButton} from "./action-button";
import {Search,X,FileSearch,ArrowUpDown,ChevronLeft,ChevronRight} from 'lucide-react';
import {useRef,useState} from 'react';
import {ReviewSelectors} from './review-selectors';
type Entity=Record<string,any>;
export function extractionDataset(e:Entity,documents:Entity[]=[]){
 return e.dataset_id||e.parent_id||documents.find(d=>e.document_ids?.includes(d.id))?.dataset_id||'';
}
function filename(e:Entity,documents:Entity[]){return e.merge?.filename||documents.filter(d=>e.document_ids?.includes(d.id)).map(d=>d.name).join(', ')||e.name||'Extraction';}
function reviewStatus(e:Entity){return e.status==='ready'?(e.review_status==='reviewed'?'Reviewed':'Pending review'):e.status;}
function columnValues(e:Entity,datasets:Entity[],documents:Entity[],templates:Entity[]){return {
 dataset:datasets.find(d=>d.id===extractionDataset(e,documents))?.name||'Dataset unavailable',
 template:templates.find(t=>t.id===e.template_id)?.name||e.template_name||'Unavailable',
 document:filename(e,documents),id:e.id,created:e.created_at||0,review:reviewStatus(e),status:e.status
};}
export function matchingExtractions(extractions:Entity[],dataset:string,query:string,status:string,documents:Entity[]=[],datasets:Entity[]=[],templates:Entity[]=[]){
 const terms=query.trim().toLocaleLowerCase().split(/\s+/).filter(Boolean);
 return extractions.filter(e=>{
  const values=columnValues(e,datasets,documents,templates);
  const date=e.created_at?new Date(e.created_at*1000):null;
  const dateText=date&&Number.isFinite(date.getTime())?[date.toLocaleString(),date.toISOString()]:[];
  const text=[...Object.values(values),...(e.merge?.sources||[]).map((s:Entity)=>s.name),e.name,...dateText,`v${e.version||1}`,`v${e.template_version||1}`].join(' ').toLocaleLowerCase();
  const matchesStatus=status==='reviewed'?e.status==='ready'&&e.review_status==='reviewed':status==='unreviewed'?e.status==='ready'&&e.review_status!=='reviewed':!status||e.status===status;
  return (!dataset||extractionDataset(e,documents)===dataset)&&matchesStatus&&terms.every(term=>text.includes(term));
 }).sort((a,b)=>Number(b.created_at)-Number(a.created_at));
}
export function reviewSummary(extractions:Entity[]){
 const ready=extractions.filter(e=>e.status==='ready');
 return [
  {status:'unreviewed',label:'Pending review',tone:'warn',count:ready.filter(e=>e.review_status!=='reviewed').length},
  {status:'reviewed',label:'Reviewed',tone:'ok',count:ready.filter(e=>e.review_status==='reviewed').length},
  {status:'processing',label:'Processing',tone:'info',count:extractions.filter(e=>e.status==='processing').length},
  {status:'failed',label:'Failed',tone:'error',count:extractions.filter(e=>e.status==='failed').length},
 ];
}
export function ExtractionDirectory({datasets,extractions,documents,templates=[],selectedDataset,onDatasetChange,onOpen,onReExtract,busy}:{datasets:Entity[];extractions:Entity[];documents:Entity[];templates?:Entity[];selectedDataset:string;onDatasetChange:(id:string)=>void;onOpen:(id:string)=>void;onReExtract?:(id:string)=>void;busy?:boolean}){
 const [query,setQuery]=useState(''),[status,setStatus]=useState('');
 const searchInput=useRef<HTMLInputElement>(null);
 const [sort,setSort]=useState({key:'created',direction:-1}),[page,setPage]=useState(0);
 const [template,setTemplate]=useState(''),[extraction,setExtraction]=useState('');
 const prompts=templates.filter(t=>!selectedDataset||!(t.dataset_id||t.parent_id)||(t.dataset_id||t.parent_id)===selectedDataset);
 const selectedTemplate=prompts.some(t=>t.id===template)?template:prompts.find(t=>extractions.some(e=>e.template_id===t.id&&(!selectedDataset||extractionDataset(e,documents)===selectedDataset)))?.id||prompts[0]?.id||'';
 const scoped=extractions.filter(e=>(!selectedDataset||extractionDataset(e,documents)===selectedDataset)&&e.template_id===selectedTemplate);
 const selectedExtraction=scoped.some(e=>e.id===extraction)?extraction:'';
 const rows=matchingExtractions(scoped,selectedDataset,query,status,documents,datasets,templates).filter(e=>!selectedExtraction||e.id===selectedExtraction).sort((a,b)=>{
  const av=columnValues(a,datasets,documents,templates)[sort.key as keyof ReturnType<typeof columnValues>],bv=columnValues(b,datasets,documents,templates)[sort.key as keyof ReturnType<typeof columnValues>];
  return sort.direction*(typeof av==='number'&&typeof bv==='number'?av-bv:String(av).localeCompare(String(bv),undefined,{numeric:true}));
 });
 const currentPage=Math.min(page,Math.max(0,Math.ceil(rows.length/20)-1)),visibleRows=rows.slice(currentPage*20,(currentPage+1)*20);
 const clearSearch=()=>{setQuery('');setPage(0);searchInput.current?.focus();};
 const headings=[['dataset','Dataset'],['template','Prompt template'],['document','Document / extraction'],['created','Extracted time'],['review','Review status']];
 // Tiles count the extractions currently in scope and double as one-click status filters.
 const summary=reviewSummary(scoped);
 return <section className="extraction-directory" aria-label="Extraction results directory">
  <div className="review-summary" role="group" aria-label="Review summary">{summary.map(tile=><button key={tile.status} type="button" className="review-tile" data-tone={tile.tone} aria-pressed={status===tile.status} onClick={()=>{setStatus(status===tile.status?'':tile.status);setPage(0);}}><span>{tile.label}</span><strong>{tile.count}</strong><small>{status===tile.status?'Showing only these · click to clear':'Show only these'}</small></button>)}</div>
  <ReviewSelectors datasets={datasets} templates={prompts} extractions={scoped} dataset={selectedDataset} template={selectedTemplate} extraction={selectedExtraction} allDatasets allExtractions disabled={busy} datasetLabel="Extraction dataset filter" onDataset={id=>{setTemplate('');setExtraction('');setPage(0);onDatasetChange(id);}} onTemplate={id=>{setTemplate(id);setExtraction('');setPage(0);}} onExtraction={id=>{setExtraction(id);setPage(0);}}/>
  <div className="extract-list-toolbar">
   <div className="extract-search" role="search" aria-label="Search extraction results"><Search size={18} aria-hidden="true"/><input ref={searchInput} type="search" aria-label="Search extractions" aria-controls="extraction-directory-results" placeholder="Search names, files, templates or IDs" autoComplete="off" spellCheck={false} value={query} onChange={e=>{setQuery(e.target.value);setPage(0);}} onKeyDown={event=>{if(event.key==='Escape'){event.preventDefault();clearSearch();}}}/>{query&&<button type="button" className="extract-search-clear" aria-label="Clear extraction search" title="Clear search" onClick={clearSearch}><X size={16}/></button>}</div>
   <label>Review status<select aria-label="Extraction status filter" value={status} onChange={e=>{setStatus(e.target.value);setPage(0);}}><option value="">All statuses</option><option value="unreviewed">Pending review</option><option value="reviewed">Reviewed</option>{['queued','processing','failed','cancelled'].map(s=><option key={s} value={s}>{s[0].toUpperCase()+s.slice(1)}</option>)}</select></label>
  </div>
  <div className="extraction-directory-results" id="extraction-directory-results">
   {rows.length?<table><thead><tr>{headings.map(([key,label])=><th key={key} scope="col" aria-sort={sort.key===key?(sort.direction===1?'ascending':'descending'):'none'}><button onClick={()=>setSort({key,direction:sort.key===key?-sort.direction:1})}>{label}<ArrowUpDown size={12}/></button></th>)}<th scope="col">Actions</th></tr></thead><tbody>{visibleRows.map(e=>{
    const values=columnValues(e,datasets,documents,templates),count=e.profile_count??0;
    return <tr key={e.id}><td title={values.dataset}>{values.dataset}</td><td>{values.template}<small>v{e.template_version||1}</small></td><td><strong>{values.document}</strong><small><code title={e.id}>{e.id.slice(0,8)}</code> · v{e.version||1}{e.merge?.sources?.length?` · ${e.merge.sources.length} merged files`:''}{count?` · ${count} ${count===1?'profile / item':'profiles / items'}`:''}</small></td><td>{e.created_at?new Date(e.created_at*1000).toLocaleString():'—'}</td><td><span className={`extraction-status ${e.status==='ready'?(e.review_status==='reviewed'?'reviewed':'pending-review'):e.status}`}>{values.review}</span></td><td><div className="extract-row-actions">{onReExtract&&<ActionButton className="text-button" aria-label={`Re-extract extraction ${e.id}`} onClick={()=>onReExtract(e.id)} disabled={busy||["queued","processing"].includes(e.status)} title={["queued","processing"].includes(e.status)?"Wait for this extraction to finish":"Re-extract"} label="Re-extract" action="reextract"/>}<ActionButton className="text-button" aria-label={`Review extraction ${e.id}`} onClick={()=>onOpen(e.id)} disabled={busy} label="Review" action="review"/></div></td></tr>;
   })}</tbody></table>:<div className="extraction-directory-empty"><FileSearch size={24}/><p>{query.trim()?`No results for “${query.trim()}”`:'No extractions match your filters.'}</p><small>Try a different name, file, template or ID, or adjust your filters.</small></div>}
  </div>
  <footer className="extract-list-pagination"><span role="status" aria-live="polite" aria-atomic="true">{rows.length?`${currentPage*20+1}–${Math.min((currentPage+1)*20,rows.length)} of ${rows.length}`:'0'} extractions</span><div><button title="Previous extraction page" className="btn icon" aria-label="Previous extraction page" disabled={currentPage===0} onClick={()=>setPage(currentPage-1)}><ChevronLeft size={16}/></button><span>Page {currentPage+1} of {Math.max(1,Math.ceil(rows.length/20))}</span><button title="Next extraction page" className="btn icon" aria-label="Next extraction page" disabled={(currentPage+1)*20>=rows.length} onClick={()=>setPage(currentPage+1)}><ChevronRight size={16}/></button></div></footer>
 </section>;
}
