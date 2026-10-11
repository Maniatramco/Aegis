"use client";
import { useEffect, useMemo, useRef, useState } from "react";
import { AlertCircle, Check, ChevronDown, Download, RefreshCw } from "lucide-react";
import "./workspace-flow.css";
import {JobProgress,extractionProgressJob} from "./operation-progress";
import {MergedDetails} from "./merged-details";
type Entity=Record<string,any>;
type Api=(path:string,method?:string,body?:unknown,signal?:AbortSignal,quiet?:boolean)=>Promise<any>;
function fields(value:any,path=""): {path:string;value:any}[] {
  if(value && typeof value==="object" && Object.keys(value).length) return Object.entries(value).flatMap(([key,item])=>fields(item,path+"/"+key.replace(/~/g,"~0").replace(/\//g,"~1")));
  return [{path:path||"/",value}];
}
function replace(value:any,path:string,next:any) {
  if(path==="/")return next;
  const copy=structuredClone(value),parts=path.slice(1).split("/").map(p=>p.replace(/~1/g,"/").replace(/~0/g,"~"));
  let parent=copy;for(const p of parts.slice(0,-1))parent=parent[p];parent[parts.at(-1)!]=next;return copy;
}
export function ExtractionReview({extraction:e,datasetName,documents,jobs,api,onSaved,onDirty,openRequest=0}:{extraction:Entity;datasetName?:string;documents:Entity[];jobs:Entity[];api:Api;onSaved:(value:Entity)=>void;onDirty:(dirty:boolean)=>void;openRequest?:number}) {
  const heading=useRef<HTMLHeadingElement>(null);
  useEffect(()=>{
    const frame=requestAnimationFrame(()=>{
      heading.current?.focus({preventScroll:true});
      heading.current?.closest('.review-workspace')?.scrollIntoView({block:'start',behavior:'instant'});
    });
    return()=>cancelAnimationFrame(frame);
  },[e.id,openRequest]);
  const [draft,setDraft]=useState(JSON.stringify(e.result??{},null,2)),[selected,setSelected]=useState("");
  const [saving,setSaving]=useState(false),[error,setError]=useState(""),[preview,setPreview]=useState<Entity|null>(null);
  const [sourceDocument,setSourceDocument]=useState('');
  const [profile,setProfile]=useState('all');
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
  const dirty=draft!==JSON.stringify(e.result??{},null,2);
  let parsed:any;try{parsed=JSON.parse(draft);}catch{}
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
  useEffect(()=>{const current=++generation.current;setPreview(null);if(document&&e.status==='ready')api(`${sourceBase}/preview`).then(value=>{if(current===generation.current)setPreview(value);}).catch(err=>{if(current===generation.current)setPreview({error:err.message});});return()=>{generation.current++;};},[sourceBase,e.status,api]);
  const reload=async()=>{if(dirty&&!window.confirm("Discard unsaved changes and reload the latest saved values?"))return;setError("");try{onSaved(await api(`/extractions/${e.id}`));}catch(err){setError((err as Error).message);}};
  const save=async()=>{if(saving)return;setSaving(true);setError("");try{const result=JSON.parse(draft);onSaved(await api(`/extractions/${e.id}`,"PATCH",{result,version:e.version}));}catch(err){setError((err as Error).message);}finally{setSaving(false);}};
  const reextract=async()=>{if(saving)return;if(!window.confirm("Re-extract using the recorded template and current mapped model? Saved edits are preserved as a previous version. Unsaved changes will be discarded."))return;setSaving(true);try{onSaved(await api(`/extractions/${e.id}/reextract`,"POST",{version:e.version,confirm_reviewed:true,allow_external:false}));}catch(err){setError((err as Error).message);}finally{setSaving(false);}};
  const page=originalAsset?origin?.source_page:origin?.page;
  return <section className="review-workspace" aria-label="Review extraction">
    <div className="review-heading"><div><span className="review-eyebrow">EXTRACTION RESULT</span><h2 ref={heading} tabIndex={-1}>Review extraction</h2><p>{e.merge?.filename||document?.name||e.name}</p></div><div className="row wrap">
      <button className="btn" aria-label="Reload extraction" title="Reload extraction" onClick={reload} disabled={saving}><RefreshCw size={15}/>Reload</button>
      <details className="download-results"><summary className="btn"><Download size={15}/>Download results<ChevronDown size={14}/></summary><div>{[["parquet","Parquet (.parquet)"],["xlsx","Excel (.xlsx)"],["csv","CSV (.csv)"],["json","JSON (.json)"]].map(([format,label])=><a key={format} href={`/api/extractions/${e.id}/export?format=${format}`} download>{label}</a>)}<small>Latest saved values only. Unsaved edits are not exported.</small></div></details>
    </div></div>
    <dl className="review-identity"><div><dt>Extraction ID</dt><dd><code>{e.id}</code></dd></div><div><dt>Dataset</dt><dd>{datasetName||'Selected dataset'}<small>{e.dataset_id||e.parent_id}</small></dd></div><div><dt>Status</dt><dd><span className={`extraction-status ${e.status}`}>{e.status}</span><small>{e.review_status||'unreviewed'} · version {e.version}</small></dd></div><div><dt>Created</dt><dd>{e.created_at?new Date(e.created_at*1000).toLocaleString():'—'}</dd></div></dl>
    <MergedDetails merge={e.merge} extractionId={e.id}/>
    {e.ocr_sources?.length>0&&<p className="upload-notice" role="status">AI OCR was used in {e.ocr_sources.length} source section(s). Check names, numbers and tables against the unchanged originals. Quotes matched to OCR text do not verify the image transcription. Model: {e.ocr_sources[0].model}.</p>}
    {e.result?.records&&<p role="status">{e.result.records.length} separate records extracted — one for each original file.</p>}
    {e.merge_records&&e.result?.records&&<p className="small" aria-label="Extracted record names">{e.result.records.map((r:Entity)=>r.fields?.full_name||r.fields?.name||r.source_filename).join(' · ')}</p>}
    {e.mock&&<p className="upload-notice">MOCK TEST OUTPUT · Synthetic development data. Review against the original.</p>}
    {(error||e.error)&&<p className="review-error" role="alert"><AlertCircle size={18}/>{error||e.error}</p>}
    {e.status!=="ready" ? <div role="status">{job&&<JobProgress job={job}/>}<p>Extraction {e.status}. Results appear here automatically when processing completes.</p><button className="btn" onClick={reload}>Check status</button>{e.status==='failed'&&<button className="btn" disabled={saving} onClick={async()=>{setSaving(true);try{onSaved(await api(`/extractions/${e.id}/resume`,'POST',{version:e.version,template_id:e.template_id,allow_external:false}));setError('');}catch(error){setError((error as Error).message);}finally{setSaving(false);}}}>Resume with latest saved prompt</button>}</div> : <div className="review-split">
      <section className="review-values"><h3>Extracted results</h3><p className="muted small">Select a field to inspect its source. Edits change results, never the original.</p>
        <div className="review-actions review-save-toolbar"><button className="btn primary" onClick={save} disabled={saving||!dirty||parsed===undefined}><Check size={15}/>{saving?"Saving…":"Save changes"}</button><button className="btn" disabled={!dirty||saving} onClick={()=>{setDraft(JSON.stringify(e.result,null,2));setError("");}}>Cancel</button></div>
        {e.merge_records&&parsed?.records&&<label className="review-profile-picker">Profile / item<select aria-label="Review profile" value={profile} onChange={event=>{setProfile(event.target.value);setSelected(event.target.value==='all'?'':`/records/${event.target.value}/fields/full_name`);}}><option value="all">All {parsed.records.length} profiles / items</option>{parsed.records.map((r:Entity,i:number)=><option key={i} value={i}>{r.fields?.full_name||r.fields?.name||`Item ${i+1}`} — {r.source_filename}</option>)}</select></label>}
        {!e.evidence?.length&&<p className="upload-notice" role="status">No verified field evidence was returned. Check these values against the original document before using them.</p>}
        {entries.map(({path,value},index)=><div key={path}>{e.merge_records&&path.match(/^\/records\/(\d+)\//)?.[1]!==entries[index-1]?.path.match(/^\/records\/(\d+)\//)?.[1]&&<h4>Record {Number(path.split('/')[2])+1} · {parsed.records[Number(path.split('/')[2])]?.source_filename}</h4>}<div className={`review-field ${selected===path?"selected":""}`} key={path}>
          <button className="field-source" onClick={()=>{setSourceDocument('');setSelected(path);}} aria-label={`Show source for ${path}`} aria-pressed={selected===path}>{(e.merge_records?path.replace(/^\/records\/\d+\/fields/, ''):path).slice(1).replace(/_/g," ").replace(/\//g," › ")||"Result"}</button>
          {typeof value==='string'&&value.length>80?<textarea rows={3} aria-label={`Value ${path}`} value={value} onFocus={()=>{setSourceDocument('');setSelected(path);}} onChange={event=>setDraft(JSON.stringify(replace(parsed,path,event.target.value),null,2))}/>:
          <input aria-label={`Value ${path}`} value={typeof value==="string"?value:JSON.stringify(value)} onFocus={()=>{setSourceDocument('');setSelected(path);}} onChange={event=>{let next:any=event.target.value;if(savedTypes.get(path)!=="string"){try{next=JSON.parse(next);}catch{next=event.target.value;}}setDraft(JSON.stringify(replace(parsed,path,next),null,2));}}/>}
          {(e.edited_fields||[]).includes(path)&&<small>Reviewed edit · source quote may describe the original value.</small>}
        </div></div>)}
        <details className="review-json"><summary>Edit complete JSON</summary><textarea aria-label="Extraction result JSON" className="mono" value={draft} onChange={event=>setDraft(event.target.value)}/></details>
        {parsed===undefined&&<p role="alert" className="review-error">Invalid JSON. Correct the syntax before saving.</p>}
        <p className={dirty?"unsaved-changes":"saved-changes"} role="status">{dirty?"Unsaved changes · downloads use saved values":"All changes saved"}</p>
        <button className="text-button" onClick={reextract} disabled={saving||dirty}>Re-extract results</button>
        <details><summary>Versions and provenance</summary><p className="small muted">Previous saved versions remain available. Edited fields lose verified evidence; original quotes are retained for review.</p><button className="btn" onClick={async()=>{try{const versions=await api(`/extractions/${e.id}/versions`);setPreview(p=>({...p,versions}));}catch(err){setError((err as Error).message);}}}>Load saved versions</button>{preview?.versions&&<pre className="code">{JSON.stringify(preview.versions,null,2)}</pre>}</details>
      </section>
      <section className="review-source"><h3>Source document{page?` · Page ${page}`:""}</h3>
        {sourceChoices.length>1&&<label>Original source files<select aria-label="Review source document" value={choice?.id||''} onChange={event=>setSourceDocument(event.target.value)}>{sourceChoices.map(d=><option key={d.id} value={d.id}>{d.name}</option>)}</select><span className="small muted">{e.merge_records?'Each original has its own fields in this combined result.':'These sources were combined into one result.'} Choose an original to inspect it.</span></label>}
        {document ? <><a className="text-button" href={`/api${sourceBase}/download`} download>Download unchanged original</a><p className="source-location-note">{page?"The recorded source page is shown.":"Source page location is unavailable for this format."} Region coordinates are unavailable; no highlight is invented.</p>
          {origin?.quote&&<blockquote className="source-quote"><strong>Recorded verbatim evidence</strong><p>{origin.quote}</p>{(e.edited_fields||[]).includes(selected)&&<small>Original evidence; recheck your edited value.</small>}</blockquote>}
          {/\.pdf$/i.test(document.name)?<><a className="text-button" href={`/api${sourceBase}/source#page=${page||1}`} target="_blank" rel="noopener">Open original PDF{page?` · page ${page}`:""}</a><img key={`${document.id}:${page||1}`} className="review-original-page" alt={`Original ${document.name} page ${page||1}`} src={`/api${sourceBase}/page-image?page=${page||1}`} style={{width:'100%',height:'auto',marginTop:12}}/><p className="small muted">Preview rendered from the unchanged original. Open the PDF to zoom or inspect other pages.</p></>:
            <pre className="source-text">{preview?.error||preview?.text||"Loading extracted text…"}</pre>}
          {/\.docx$/i.test(document.name)&&<p className="small muted">DOCX text is shown as a fallback. Download the original to inspect layout; page numbers cannot be inferred.</p>}
        </>:<p>No source document is available. This value has no verified location.</p>}
      </section>
    </div>}
  </section>;
}
