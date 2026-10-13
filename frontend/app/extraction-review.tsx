"use client";
import { useEffect, useMemo, useRef, useState } from "react";
import { AlertCircle, Check, ChevronDown, ChevronLeft, ChevronRight, Download, RefreshCw, Maximize2, Minimize2, Minus, Plus, ExternalLink, FileText } from "lucide-react";
import "./workspace-flow.css";
import {JobProgress,extractionProgressJob} from "./operation-progress";
import {MergedDetails} from "./merged-details";
import {evidenceExcerpt} from './citation-source';
type Entity=Record<string,any>;
type Api=(path:string,method?:string,body?:unknown,signal?:AbortSignal,quiet?:boolean)=>Promise<any>;
function fields(value:any,path=""): {path:string;value:any}[] {
  if(Array.isArray(value)&&value.every(item=>typeof item==='string'))return [{path:path||'/',value}];
  if(value && typeof value==="object" && Object.keys(value).length) return Object.entries(value).flatMap(([key,item])=>fields(item,path+"/"+key.replace(/~/g,"~0").replace(/\//g,"~1")));
  return [{path:path||"/",value}];
}
function replace(value:any,path:string,next:any) {
  if(path==="/")return next;
  const copy=structuredClone(value),parts=path.slice(1).split("/").map(p=>p.replace(/~1/g,"/").replace(/~0/g,"~"));
  let parent=copy;for(const p of parts.slice(0,-1))parent=parent[p];parent[parts.at(-1)!]=next;return copy;
}
export function OriginalPdfViewer({sourceBase,name,pageCount,evidencePage}:{sourceBase:string;name:string;pageCount?:number; evidencePage?:number}) {
  const [page,setPage]=useState(evidencePage||1),[zoom,setZoom]=useState(100),[expanded,setExpanded]=useState(false),[failed,setFailed]=useState(false),[retry,setRetry]=useState(0);
  const dialog=useRef<HTMLDialogElement>(null);
  const [fit,setFit]=useState(false),[thumbnails,setThumbnails]=useState(false);
  useEffect(()=>{setPage(evidencePage||1);setZoom(100);setFit(false);},[sourceBase,evidencePage]);
  useEffect(()=>{setFailed(false);},[sourceBase,page,retry]);
  useEffect(()=>{if(expanded)dialog.current?.showModal();},[expanded]);
  const count=pageCount&&pageCount>0?pageCount:undefined;
  const start=Math.floor((page-1)/40)*40+1;
  const pages=count?Array.from({length:Math.min(40,count-start+1)},(_,i)=>start+i):[page];
  const viewer=<><div className="review-pdf-toolbar"><button aria-label={thumbnails?"Hide page thumbnails":"Show page thumbnails"} aria-pressed={thumbnails} onClick={()=>setThumbnails(!thumbnails)}><FileText size={16}/></button><div className="review-page-controls"><button aria-label="Previous original page" disabled={page<=1} onClick={()=>setPage(p=>p-1)}><ChevronLeft size={16}/></button><label><span className="sr-only">Original PDF page</span><input aria-label="Original PDF page" type="number" min={1} max={count} value={page} onChange={event=>{const next=Number(event.target.value);if(Number.isInteger(next)&&next>=1&&(!count||next<=count))setPage(next);}}/></label><span>/ {count||'—'}</span><button aria-label="Next original page" disabled={!count||page>=count} onClick={()=>setPage(p=>p+1)}><ChevronRight size={16}/></button></div><div className="review-zoom-controls"><button aria-label="Fit original page" aria-pressed={fit} onClick={()=>setFit(true)}>Fit page</button><button aria-label="Zoom out original" disabled={zoom<=50} onClick={()=>{setFit(false);setZoom(z=>z-25);}}><Minus size={16}/></button><button aria-label="Reset original zoom" onClick={()=>{setFit(false);setZoom(100);}}>{zoom}%</button><button aria-label="Zoom in original" disabled={zoom>=200} onClick={()=>{setFit(false);setZoom(z=>z+25);}}><Plus size={16}/></button></div><a href={`/api${sourceBase}/source#page=${page}`} target="_blank" rel="noopener" aria-label="Open original PDF" title="Open original PDF"><ExternalLink size={16}/></a><a href={`/api${sourceBase}/download`} download aria-label="Download unchanged original" title="Download unchanged original"><Download size={16}/></a><button aria-label={expanded?'Close expanded document':'Expand document'} onClick={()=>setExpanded(!expanded)}>{expanded?<Minimize2 size={16}/>:<Maximize2 size={16}/>}</button></div><div className="review-pdf-body">{thumbnails&&<nav className="review-pdf-thumbnails" aria-label="Original PDF pages">{pages.map(p=><button key={p} aria-label={`Show original page ${p}`} aria-current={p===page?'page':undefined} onClick={()=>setPage(p)}><img loading="lazy" src={`/api${sourceBase}/page-image?page=${p}`} alt=""/><span>{p}</span></button>)}</nav>}<div className="review-pdf-canvas">{failed?<div className="review-preview-error" role="alert"><FileText size={26}/><p>This page could not be displayed.</p><button onClick={()=>setRetry(r=>r+1)}>Retry preview</button><a href={`/api${sourceBase}/download`} download>Download original</a></div>:<img key={`${sourceBase}:${page}:${retry}`} className={`review-original-page${fit?" fit-page":""}`} alt={`Original ${name} page ${page}`} src={`/api${sourceBase}/page-image?page=${page}`} style={fit?undefined:{width:`${zoom}%`}} onError={()=>setFailed(true)}/>}</div></div></>;
  return <>{!expanded&&<div className="review-pdf-viewer">{viewer}</div>}{expanded&&<dialog className="review-document-dialog" ref={dialog} onClose={()=>setExpanded(false)}><h3>{name}</h3><div className="review-pdf-viewer">{viewer}</div></dialog>}</>;
}
export function ExtractionReview({extraction:e,datasetName,documents,jobs,api,onSaved,onDirty,openRequest=0}:{extraction:Entity;datasetName?:string;documents:Entity[];jobs:Entity[];api:Api;onSaved:(value:Entity)=>void;onDirty:(dirty:boolean)=>void;openRequest?:number}) {
  const heading=useRef<HTMLHeadingElement>(null);
  useEffect(()=>{
    const frame=requestAnimationFrame(()=>{
      heading.current?.focus({preventScroll:true});
      if(heading.current?.closest('.review-page-shell'))window.scrollTo({top:0,behavior:'instant'});
      else heading.current?.closest('.review-workspace')?.scrollIntoView({block:'start',behavior:'instant'});
    });
    return()=>cancelAnimationFrame(frame);
  },[e.id,openRequest]);
  const [draft,setDraft]=useState(JSON.stringify(e.result??{},null,2)),[selected,setSelected]=useState("");
  const [saving,setSaving]=useState(false),[error,setError]=useState(""),[preview,setPreview]=useState<Entity|null>(null);
  const [sourceDocument,setSourceDocument]=useState('');
  const [profile,setProfile]=useState('all');
  const [pane,setPane]=useState('fields');
  const locked=e.review_status==='reviewed'||e.review_locked===true;
  useEffect(()=>{setProfile('all');setSelected('');},[e.id]);
  const generation=useRef(0);
  const savedCallback=useRef(onSaved);savedCallback.current=onSaved;
  const job=extractionProgressJob(e,jobs);
  useEffect(()=>{
    if(!['queued','processing'].includes(e.status))return;
    let active=true,inFlight=false;
    const timer=setInterval(async()=>{if(inFlight)return;inFlight=true;try{const value=await api(`/extractions/${e.id}`,'GET',undefined,undefined,true);if(active)savedCallback.current(value);}catch(error){if(active)setError((error as Error).message);}finally{inFlight=false;}},3000);
    return()=>{active=false;clearInterval(timer);};
  },[e.id,e.status,api]);
  let parsed:any;try{parsed=JSON.parse(draft);}catch{}
  const dirty=parsed===undefined||JSON.stringify(parsed)!==JSON.stringify(e.result??{});
  const savedValues=new Map(fields(e.result??{}).map(field=>[field.path,JSON.stringify(field.value)]));
  const currentValues=new Map(parsed===undefined?[]:fields(parsed).map(field=>[field.path,JSON.stringify(field.value)]));
  const changedCount=parsed===undefined?0:[...new Set([...savedValues.keys(),...currentValues.keys()])].filter(path=>savedValues.get(path)!==currentValues.get(path)).length;
  const entries=parsed===undefined?[]:fields(parsed).filter(f=>(!e.merge_records||!/^\/records\/\d+\/(?:source_key|source_filename)$/.test(f.path))&&(profile==='all'||f.path.startsWith(`/records/${profile}/`)));
  const savedTypes=new Map(fields(e.result??{}).map(field=>[field.path,typeof field.value]));
  const recordIndex=selected.match(/^\/records\/(\d+)\//)?.[1];
  const recordSource=recordIndex===undefined?null:e.result?.records?.[Number(recordIndex)];
  const mergedOriginal=e.merge?.sources?.find((s:Entity)=>s.key===recordSource?.source_key);
  const fieldOrigin=useMemo(()=>{
    const evidence=[...(e.evidence||[]),...(e.original_evidence||[])];
    return evidence.find(item=>item.field===selected) || evidence.find(item=>selected.startsWith(item.field+"/")) || (mergedOriginal?(e.sources||[]).find((s:Entity)=>e.merge.document_id?s.source_key===mergedOriginal.key:s.document_id===mergedOriginal.document_id):null) || (e.sources||[])[0];
  },[e,selected,mergedOriginal]);
  const sourceChoices:Entity[]=e.merge?.sources?.map((s:Entity)=>({...s,id:e.merge.document_id?`merged:${s.key}`:s.document_id})) || documents.filter(d=>e.document_ids?.includes(d.id));
  const choice=sourceChoices.find(s=>s.id===sourceDocument) || sourceChoices.find(s=>s.key===(mergedOriginal?.key||fieldOrigin?.source_key)) || sourceChoices.find(s=>s.id===fieldOrigin?.document_id) || sourceChoices[0];
  const originalAsset=Boolean(e.merge?.document_id&&choice?.key);
  const origin=sourceDocument?(e.sources||[]).find((s:Entity)=>originalAsset?s.source_key===choice.key:s.document_id===sourceDocument):fieldOrigin;
  const document=choice || documents.find(d=>d.id===origin?.document_id) || documents.find(d=>e.document_ids?.includes(d.id));
  const sourceBase=document?(originalAsset?`/documents/${e.merge.document_id}/merged-sources/${choice.key}`:`/documents/${document.id}`):'';
  useEffect(()=>{setSourceDocument('');},[e.id,selected]);
  useEffect(()=>{setDraft(JSON.stringify(e.result??{},null,2));setError("");},[e.id,e.version,e.status,openRequest]);
  useEffect(()=>{onDirty(dirty);return()=>onDirty(false);},[dirty,onDirty]);
  useEffect(()=>{if(!dirty)return;const warn=(event:BeforeUnloadEvent)=>{event.preventDefault();};window.addEventListener("beforeunload",warn);return()=>window.removeEventListener("beforeunload",warn);},[dirty]);
  useEffect(()=>{const current=++generation.current;setPreview(null);if(document&&e.status==='ready')api(`${sourceBase}/preview`,'GET',undefined,undefined,true).then(value=>{if(current===generation.current)setPreview(value);}).catch(err=>{if(current===generation.current)setPreview({error:err.message});});return()=>{generation.current++;};},[sourceBase,e.status,api]);
  const reload=async()=>{if(dirty&&!window.confirm("Discard unsaved changes and reload the latest saved values?"))return;setError("");try{onSaved(await api(`/extractions/${e.id}`));}catch(err){setError((err as Error).message);}};
  const save=async()=>{if(saving||locked||parsed===undefined)return;setSaving(true);setError("");try{const result=JSON.parse(draft);onSaved(await api(`/extractions/${e.id}`,"PATCH",{result,version:e.version}));}catch(err){setError((err as Error).message);}finally{setSaving(false);}};
  const reextract=async()=>{if(saving)return;if(!window.confirm("Re-extract using the recorded template and current mapped model? Saved edits are preserved as a previous version. Unsaved changes will be discarded."))return;setSaving(true);try{onSaved(await api(`/extractions/${e.id}/reextract`,"POST",{version:e.version,confirm_reviewed:true,allow_external:false}));}catch(err){setError((err as Error).message);}finally{setSaving(false);}};
  const page=originalAsset?origin?.source_page:origin?.page;
  const exactEvidence=(e.evidence||[]).some((item:Entity)=>item.field===selected||selected.startsWith(item.field+'/'));
  return <section className="review-workspace" aria-label="Review extraction">
    <div className="review-heading"><div><h2 ref={heading} tabIndex={-1}>Review</h2><span className={`extraction-status ${e.status}`}>{e.status}</span><span className="small muted">{e.review_status||'unreviewed'} · v{e.version}</span></div><div className="row wrap">
      <button className="btn" aria-label="Reload extraction" title="Reload extraction" onClick={reload} disabled={saving}><RefreshCw size={15}/>Reload</button>
      <details className="download-results"><summary className="btn"><Download size={15}/>Download results<ChevronDown size={14}/></summary><div>{[["parquet","Parquet (.parquet)"],["xlsx","Excel (.xlsx)"],["csv","CSV (.csv)"],["json","JSON (.json)"]].map(([format,label])=><a key={format} href={`/api/extractions/${e.id}/export?format=${format}`} download>{label}</a>)}<small>Latest saved values only. Unsaved edits are not exported.</small></div></details>
    </div></div>
    <details className="review-metadata"><summary>Extraction details <code>{e.id}</code></summary><dl className="review-identity"><div><dt>Extraction ID</dt><dd><code>{e.id}</code></dd></div><div><dt>Dataset</dt><dd>{datasetName||'Selected dataset'}<small>{e.dataset_id||e.parent_id}</small></dd></div><div><dt>Status</dt><dd>{e.review_status||'unreviewed'} · version {e.version}</dd></div><div><dt>Created</dt><dd>{e.created_at?new Date(e.created_at*1000).toLocaleString():'—'}</dd></div></dl>
    <MergedDetails merge={e.merge} extractionId={e.id}/>
    {e.ocr_sources?.length>0&&<p className="upload-notice" role="status">AI OCR was used in {e.ocr_sources.length} source section(s). Check names, numbers and tables against the unchanged originals. Quotes matched to OCR text do not verify the image transcription. Model: {e.ocr_sources[0].model}.</p>}
    {e.result?.records&&<p role="status">{e.result.records.length} separate records extracted — one for each original file.</p>}
    {e.merge_records&&e.result?.records&&<p className="small" aria-label="Extracted record names">{e.result.records.map((r:Entity)=>r.fields?.full_name||r.fields?.name||r.source_filename).join(' · ')}</p>}</details>
    {e.mock&&<p className="upload-notice">MOCK TEST OUTPUT · Synthetic development data. Review against the original.</p>}
    {(error||e.error)&&<p className="review-error" role="alert"><AlertCircle size={18}/>{error||e.error}</p>}
    {e.status!=="ready" ? <div role="status">{job&&<JobProgress job={job}/>}<p>Extraction {e.status}. Results appear here automatically when processing completes.</p><button className="btn" onClick={reload}>Check status</button>{e.status==='failed'&&<button className="btn" disabled={saving} onClick={async()=>{setSaving(true);try{onSaved(await api(`/extractions/${e.id}/resume`,'POST',{version:e.version,template_id:e.template_id,allow_external:false}));setError('');}catch(error){setError((error as Error).message);}finally{setSaving(false);}}}>Resume with latest saved prompt</button>}</div> : <><div className="review-pane-tabs"><button className="btn" aria-pressed={pane==='fields'} onClick={()=>setPane('fields')}>Extracted fields</button><button className="btn" aria-pressed={pane==='source'} onClick={()=>setPane('source')}>Original document</button></div><div className="review-split" data-pane={pane}>
      <section className="review-values" aria-label="Extracted fields"><div className="review-panel-heading"><h3>Extracted results</h3><div className="review-field-legend"><span><i className="legend-selected"/>Selected</span><span><i className="legend-modified"/>Modified value</span></div></div><div className="review-values-scroll">
        {e.merge_records&&parsed?.records&&<label className="review-profile-picker">Profile / item<select aria-label="Review profile" value={profile} onChange={event=>{setProfile(event.target.value);setSelected(event.target.value==='all'?'':`/records/${event.target.value}/fields/full_name`);}}><option value="all">All {parsed.records.length} profiles / items</option>{parsed.records.map((r:Entity,i:number)=><option key={i} value={i}>{r.fields?.full_name||r.fields?.name||`Item ${i+1}`} — {r.source_filename}</option>)}</select></label>}
        {!e.evidence?.length&&<p className="review-evidence-notice" role="status"><AlertCircle size={14}/>No verified field evidence. Check values against the original.</p>}
        <div className="review-field-columns"><span>FIELD</span><span>VALUE</span></div>
        {entries.map(({path,value},index)=><div key={path}>{e.merge_records&&path.match(/^\/records\/(\d+)\//)?.[1]!==entries[index-1]?.path.match(/^\/records\/(\d+)\//)?.[1]&&<h4>Record {Number(path.split('/')[2])+1} · {parsed.records[Number(path.split('/')[2])]?.source_filename}</h4>}<div className={`review-field ${selected===path?"selected":""} ${savedValues.get(path)!==JSON.stringify(value)?'modified':''}`} key={path}>
          <button className="field-source" onClick={()=>{setSourceDocument('');setSelected(path);}} aria-label={`Show source for ${path}`} aria-pressed={selected===path}>{(e.merge_records?path.replace(/^\/records\/\d+\/fields/, ''):path).slice(1).replace(/_/g," ").replace(/\//g," › ")||"Result"}</button>
          {Array.isArray(value)&&value.every(item=>typeof item==='string')?<details className="review-array-values"><summary><span>{value.join(', ')||'No items'}</span><small>{locked?'View items':'Edit list'}</small></summary><div>{value.map((item:string,i:number)=><div className="review-array-item" key={i}><input disabled={saving} readOnly={locked} aria-label={`Value ${path}/${i}`} value={item} onFocus={()=>{setSourceDocument('');setSelected(`${path}/${i}`);}} onChange={event=>{if(!locked)setDraft(JSON.stringify(replace(parsed,`${path}/${i}`,event.target.value),null,2));}}/>{!locked&&<button className="text-button" aria-label={`Remove ${path} item ${i+1}`} disabled={saving} onClick={()=>setDraft(JSON.stringify(replace(parsed,path,value.filter((_:string,index:number)=>index!==i)),null,2))}>Remove</button>}</div>)}{!locked&&<button className="text-button" disabled={saving} onClick={()=>setDraft(JSON.stringify(replace(parsed,path,[...value,'']),null,2))}>Add item</button>}</div></details>:typeof value==='string'&&value.length>80?<textarea disabled={saving} readOnly={locked} rows={3} aria-label={`Value ${path}`} value={value} onFocus={()=>{setSourceDocument('');setSelected(path);}} onChange={event=>{if(!locked)setDraft(JSON.stringify(replace(parsed,path,event.target.value),null,2));}}/>:
          <input disabled={saving} readOnly={locked} aria-label={`Value ${path}`} value={typeof value==="string"?value:JSON.stringify(value)} onFocus={()=>{setSourceDocument('');setSelected(path);}} onChange={event=>{if(locked)return;let next:any=event.target.value;if(savedTypes.get(path)!=="string"){try{next=JSON.parse(next);}catch{next=event.target.value;}}setDraft(JSON.stringify(replace(parsed,path,next),null,2));}}/>}
          {(e.edited_fields||[]).includes(path)&&<small>Reviewed edit · source quote may describe the original value.</small>}
        </div></div>)}
        {parsed===undefined&&<p role="alert" className="review-error">Invalid JSON. Correct the syntax before saving.</p>}
        {!locked&&<button className="text-button" onClick={reextract} disabled={saving||dirty}>Re-extract results</button>}
        <details><summary>Versions and provenance</summary><p className="small muted">Previous saved versions remain available. Edited fields lose verified evidence; original quotes are retained for review.</p><button className="btn" onClick={async()=>{try{const versions=await api(`/extractions/${e.id}/versions`);setPreview(p=>({...p,versions}));}catch(err){setError((err as Error).message);}}}>Load saved versions</button>{preview?.versions&&<pre className="code">{JSON.stringify(preview.versions,null,2)}</pre>}</details>
      </div></section>
      <section className="review-source" aria-label="Original document"><div className="review-panel-heading"><h3>Source document</h3><span title={document?.name}>{document?.name||'Unavailable'}</span></div>
        {sourceChoices.length>1&&<label>Original source files<select aria-label="Review source document" value={choice?.id||''} onChange={event=>setSourceDocument(event.target.value)}>{sourceChoices.map(d=><option key={d.id} value={d.id}>{d.name}</option>)}</select><span className="small muted">{e.merge_records?'Each original has its own fields in this combined result.':'These sources were combined into one result.'} Choose an original to inspect it.</span></label>}
        {document ? <>
          {/\.pdf$/i.test(document.name)?<OriginalPdfViewer sourceBase={sourceBase} name={document.name} pageCount={preview?.page_count} evidencePage={page}/>:<><a className="text-button" href={`/api${sourceBase}/download`} download>Download unchanged original</a><pre className="source-text">{preview?.error||preview?.text||"Loading extracted text…"}</pre></>}
          <details className="review-source-evidence" key={selected} open={!!selected}><summary>Source evidence{page?` · page ${page}`:''}</summary><p className="source-location-note">{page&&exactEvidence?"The recorded source page is shown for this field.":page?"This is a retrieved source page; no verified field-level location was saved.":"Source page location is unavailable for this field."} Region coordinates are unavailable; no highlight is invented.</p>
          {(origin?.quote||origin?.text)&&<blockquote className="source-quote"><strong>{exactEvidence?'Recorded field evidence':'Retrieved document passage'}</strong><p>{evidenceExcerpt(origin.quote||origin.text,[fields(parsed).find(f=>f.path===selected)?.value])}</p>{(e.edited_fields||[]).includes(selected)&&<small>Original evidence; recheck your edited value.</small>}</blockquote>}
          {/\.docx$/i.test(document.name)&&<p className="small muted">DOCX text is shown as a fallback. Download the original to inspect layout; page numbers cannot be inferred.</p>}
          </details>
        </>:<p>No source document is available. This value has no verified location.</p>}
      </section>
    </div><footer className="review-save-footer"><div role="status" className={dirty?'review-unsaved':'review-saved'}>{locked?<><Check size={16}/>Reviewed · locked</>:dirty?<><span className="review-dirty-dot"/>{parsed===undefined?'Correct invalid JSON before review':`${changedCount} modified ${changedCount===1?'value':'values'} · Unsaved changes`}</>:<>Ready for review</>}<small>{locked?'This extraction cannot be modified. Re-extract creates a separate result.':'Click Reviewed to save and permanently lock this result.'}</small></div><div className="review-actions">{!locked&&<button className="btn" disabled={!dirty||saving} onClick={()=>{setDraft(JSON.stringify(e.result,null,2));setError("");}}>Cancel</button>}<button className="btn primary" onClick={save} disabled={saving||locked||parsed===undefined}><Check size={16}/>{saving?"Marking Reviewed…":"Reviewed"}</button></div></footer></>}
  </section>;
}
