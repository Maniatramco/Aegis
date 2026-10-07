"use client";
import { useEffect, useMemo, useRef, useState } from "react";
import { AlertCircle, Check, ChevronDown, Download, RefreshCw } from "lucide-react";
import "./workspace-flow.css";
type Entity=Record<string,any>;
type Api=(path:string,method?:string,body?:unknown)=>Promise<any>;
function fields(value:any,path=""): {path:string;value:any}[] {
  if(value && typeof value==="object" && Object.keys(value).length) return Object.entries(value).flatMap(([key,item])=>fields(item,path+"/"+key.replace(/~/g,"~0").replace(/\//g,"~1")));
  return [{path:path||"/",value}];
}
function replace(value:any,path:string,next:any) {
  if(path==="/")return next;
  const copy=structuredClone(value),parts=path.slice(1).split("/").map(p=>p.replace(/~1/g,"/").replace(/~0/g,"~"));
  let parent=copy;for(const p of parts.slice(0,-1))parent=parent[p];parent[parts.at(-1)!]=next;return copy;
}
export function ExtractionReview({extraction:e,documents,api,onSaved,onDirty}:{extraction:Entity;documents:Entity[];api:Api;onSaved:(value:Entity)=>void;onDirty:(dirty:boolean)=>void}) {
  const [draft,setDraft]=useState(JSON.stringify(e.result??{},null,2)),[selected,setSelected]=useState("");
  const [saving,setSaving]=useState(false),[error,setError]=useState(""),[preview,setPreview]=useState<Entity|null>(null);
  const generation=useRef(0);
  const dirty=draft!==JSON.stringify(e.result??{},null,2);
  let parsed:any;try{parsed=JSON.parse(draft);}catch{}
  const entries=parsed===undefined?[]:fields(parsed);
  const savedTypes=new Map(fields(e.result??{}).map(field=>[field.path,typeof field.value]));
  const origin=useMemo(()=>{
    const evidence=[...(e.evidence||[]),...(e.original_evidence||[])];
    return evidence.find(item=>item.field===selected) || evidence.find(item=>selected.startsWith(item.field+"/")) || (e.sources||[])[0];
  },[e,selected]);
  const document=documents.find(d=>d.id===origin?.document_id) || documents.find(d=>e.document_ids?.includes(d.id));
  useEffect(()=>{setDraft(JSON.stringify(e.result??{},null,2));setError("");},[e.id,e.version,e.status]);
  useEffect(()=>{onDirty(dirty);return()=>onDirty(false);},[dirty,onDirty]);
  useEffect(()=>{if(!dirty)return;const warn=(event:BeforeUnloadEvent)=>{event.preventDefault();};window.addEventListener("beforeunload",warn);return()=>window.removeEventListener("beforeunload",warn);},[dirty]);
  useEffect(()=>{const current=++generation.current;setPreview(null);if(document)api(`/documents/${document.id}/preview`).then(value=>{if(current===generation.current)setPreview(value);}).catch(err=>{if(current===generation.current)setPreview({error:err.message});});},[document?.id,api]);
  const reload=async()=>{if(dirty&&!window.confirm("Discard unsaved changes and reload the latest saved values?"))return;setError("");try{onSaved(await api(`/extractions/${e.id}`));}catch(err){setError((err as Error).message);}};
  const save=async()=>{if(saving)return;setSaving(true);setError("");try{const result=JSON.parse(draft);onSaved(await api(`/extractions/${e.id}`,"PATCH",{result,version:e.version}));}catch(err){setError((err as Error).message);}finally{setSaving(false);}};
  const reextract=async()=>{if(saving)return;if(!window.confirm("Re-extract using the recorded template and current mapped model? Saved edits are preserved as a previous version. Unsaved changes will be discarded."))return;setSaving(true);try{onSaved(await api(`/extractions/${e.id}/reextract`,"POST",{version:e.version,confirm_reviewed:true,allow_external:false}));}catch(err){setError((err as Error).message);}finally{setSaving(false);}};
  const page=origin?.page;
  return <section className="review-workspace" aria-label="Review extraction">
    <div className="review-heading"><div><h2>Review extraction</h2><p>{document?.name||e.name} · Saved version {e.version} · {e.review_status||e.status}</p></div><div className="row wrap">
      <button className="btn" aria-label="Reload extraction" title="Reload extraction" onClick={reload} disabled={saving}><RefreshCw size={15}/>Reload</button>
      <details className="download-results"><summary className="btn"><Download size={15}/>Download results<ChevronDown size={14}/></summary><div>{[["xlsx","Excel (.xlsx)"],["csv","CSV (.csv)"],["json","JSON (.json)"]].map(([format,label])=><a key={format} href={`/api/extractions/${e.id}/export?format=${format}`} download>{label}</a>)}<small>Latest saved values only. Unsaved edits are not exported.</small></div></details>
    </div></div>
    {e.mock&&<p className="upload-notice">MOCK TEST OUTPUT · Synthetic development data. Review against the original.</p>}
    {(error||e.error)&&<p className="review-error" role="alert"><AlertCircle size={18}/>{error||e.error}</p>}
    {e.status!=="ready" ? <div role="status"><p>Extraction {e.status}. Document indexing and structured extraction are separate operations.</p><button className="btn" onClick={reload}>Check status</button></div> : <div className="review-split">
      <section className="review-values"><h3>Extracted results</h3><p className="muted small">Select a field to inspect its source. Edits change results, never the original.</p>
        {entries.map(({path,value})=><div className={`review-field ${selected===path?"selected":""}`} key={path}>
          <button className="field-source" onClick={()=>setSelected(path)} aria-label={`Show source for ${path}`} aria-pressed={selected===path}>{path.slice(1).replace(/_/g," ").replace(/\//g," › ")||"Result"}</button>
          <input aria-label={`Value ${path}`} value={typeof value==="string"?value:JSON.stringify(value)} onFocus={()=>setSelected(path)} onChange={event=>{let next:any=event.target.value;if(savedTypes.get(path)!=="string"){try{next=JSON.parse(next);}catch{next=event.target.value;}}setDraft(JSON.stringify(replace(parsed,path,next),null,2));}}/>
          {(e.edited_fields||[]).includes(path)&&<small>Reviewed edit · source quote may describe the original value.</small>}
        </div>)}
        <details className="review-json"><summary>Edit complete JSON</summary><textarea aria-label="Extraction result JSON" className="mono" value={draft} onChange={event=>setDraft(event.target.value)}/></details>
        {parsed===undefined&&<p role="alert" className="review-error">Invalid JSON. Correct the syntax before saving.</p>}
        <p className={dirty?"unsaved-changes":"saved-changes"} role="status">{dirty?"Unsaved changes · downloads use saved values":"All changes saved"}</p>
        <div className="review-actions"><button className="btn primary" onClick={save} disabled={saving||!dirty||parsed===undefined}><Check size={15}/>{saving?"Saving…":"Save changes"}</button><button className="btn" disabled={!dirty||saving} onClick={()=>{setDraft(JSON.stringify(e.result,null,2));setError("");}}>Cancel</button></div>
        <button className="text-button" onClick={reextract} disabled={saving||dirty}>Re-extract results</button>
        <details><summary>Versions and provenance</summary><p className="small muted">Previous saved versions remain available. Edited fields lose verified evidence; original quotes are retained for review.</p><button className="btn" onClick={async()=>{try{const versions=await api(`/extractions/${e.id}/versions`);setPreview(p=>({...p,versions}));}catch(err){setError((err as Error).message);}}}>Load saved versions</button>{preview?.versions&&<pre className="code">{JSON.stringify(preview.versions,null,2)}</pre>}</details>
      </section>
      <section className="review-source"><h3>Source document{page?` · Page ${page}`:""}</h3>
        {document ? <><a className="text-button" href={`/api/documents/${document.id}/download`} download>Download unchanged original</a><p className="source-location-note">{page?"The recorded source page is shown.":"Source page location is unavailable for this format."} Region coordinates are unavailable; no highlight is invented.</p>
          {origin?.quote&&<blockquote className="source-quote"><strong>Recorded verbatim evidence</strong><p>{origin.quote}</p>{(e.edited_fields||[]).includes(selected)&&<small>Original evidence; recheck your edited value.</small>}</blockquote>}
          {/\.pdf$/i.test(document.name)?<iframe key={`${document.id}:${page||1}`} title={`Original ${document.name} page ${page||1}`} src={`/api/documents/${document.id}/source#page=${page||1}`}/>:
            <pre className="source-text">{preview?.error||preview?.text||"Loading extracted text…"}</pre>}
          {/\.docx$/i.test(document.name)&&<p className="small muted">DOCX text is shown as a fallback. Download the original to inspect layout; page numbers cannot be inferred.</p>}
        </>:<p>No source document is available. This value has no verified location.</p>}
      </section>
    </div>}
  </section>;
}
