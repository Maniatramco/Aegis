"use client";
import {useEffect,useRef,useState} from "react";
import {FileSearch,FileText,Search,X} from "lucide-react";
import {eligibleModels} from "./dataset-workspace";
import {JobProgress} from "./operation-progress";
type Entity=Record<string,any>;
type Api=(path:string,method?:string,body?:unknown)=>Promise<any>;
export function ReExtract({documents,datasets,templates,extractions,jobs,api,onRefresh,onReview,onConfigure,onProgressVisibilityChange}:{documents:Entity[];datasets:Entity[];templates:Entity[];extractions:Entity[];jobs:Entity[];api:Api;onRefresh:()=>void;onReview:(e:Entity)=>void;onConfigure:(id:string)=>void;onProgressVisibilityChange?:(jobId:string|null)=>void}) {
 const [search,setSearch]=useState(''),[filter,setFilter]=useState(''),[selected,setSelected]=useState(''),[template,setTemplate]=useState(''),[busy,setBusy]=useState(false),[error,setError]=useState(''),[external,setExternal]=useState(false),[run,setRun]=useState<Entity|null>(null);
 const submitting=useRef(false),dialog=useRef<HTMLDialogElement>(null);
 const doc=documents.find(d=>d.id===selected),dataset=datasets.find(d=>d.id===(doc?.dataset_id||doc?.kb_id)),models=eligibleModels(dataset,'extraction');
 const chosen=models.find(m=>m.id===dataset?.default_extraction_model_id)||(models.length===1?models[0]:undefined);
 const needsConsent=!!chosen?.provider&&!['ollama','mock','sentence_transformers'].includes(chosen.provider);
 const job=jobs.find(j=>j.id===run?.job?.id)||run?.job,latest=extractions.find(e=>e.id===run?.id)||run;
 useEffect(()=>{if(selected)dialog.current?.showModal();},[selected]);
 useEffect(()=>{onProgressVisibilityChange?.(selected&&job?.id?job.id:null);return()=>onProgressVisibilityChange?.(null);},[selected,job?.id,onProgressVisibilityChange]);
 const open=(d:Entity)=>{setSelected(d.id);setTemplate('');setError('');setExternal(false);setRun(null);};
 const submit=async()=>{
  if(submitting.current||!doc||!chosen||!template||run)return;
  submitting.current=true;setBusy(true);setError('');
  try{setRun(await api('/extractions','POST',{dataset_id:dataset?.id,document_ids:[doc.id],template_id:template,model_id:chosen.id,allow_external:external}));onRefresh();}
  catch(e){setError((e as Error).message);}finally{submitting.current=false;setBusy(false);}
 };
 const visible=documents.filter(d=>(!filter||(d.dataset_id||d.kb_id)===filter)&&`${d.name} ${datasets.find(k=>k.id===(d.dataset_id||d.kb_id))?.name||''}`.toLowerCase().includes(search.toLowerCase()));
 return <section className="panel reextract-page"><div className="panel-head"><div><h2>Your documents</h2><p className="small muted">Choose a document, pick a prompt template, and extract.</p></div><span className="pill">{visible.length} documents</span></div>
  <div className="reextract-filters"><label className="directory-search"><Search size={17}/><input aria-label="Search documents to extract" value={search} onChange={e=>setSearch(e.target.value)} placeholder="Search documents…"/></label><label className="field">Dataset<select aria-label="Filter extraction documents by dataset" value={filter} onChange={e=>setFilter(e.target.value)}><option value="">All accessible datasets</option>{datasets.map(d=><option key={d.id} value={d.id}>{d.name}</option>)}</select></label></div>
  <div className="reextract-list">{visible.map(d=>{const ds=datasets.find(k=>k.id===(d.dataset_id||d.kb_id)),runs=extractions.filter(e=>e.document_ids?.includes(d.id)),ready=d.status==='ready'&&!d.requires_reindex;return <article className="reextract-document" key={d.id} aria-label={`Extraction document ${d.name}`}><FileText size={22}/><div className="reextract-document-details"><h3>{d.name}</h3><p className="small muted">{ds?.name||'Dataset unavailable'} · {runs.length} saved extraction{runs.length===1?'':'s'}</p><span className={`directory-status ${d.status==='failed'?'failed':!ready?'pending':'ready'}`}>{d.requires_reindex?'Reindex required':d.status}</span>{d.error&&<p className="small">{d.error}</p>}{!ready&&<p className="small muted">Finish processing or reindex this document in Datasets first.</p>}</div><button className="btn" disabled={!ready||ds?.active===false||jobs.some(j=>j.kind==='extract'&&['queued','running'].includes(j.status)&&extractions.find(e=>e.id===j.target_id)?.document_ids?.includes(d.id))} onClick={()=>open(d)}><FileSearch size={16}/>{runs.length?'Re-extract':'Extract'}</button></article>;})}{!visible.length&&<div className="directory-empty"><h3>{documents.length?'No matching documents':'No documents yet'}</h3><p>{documents.length?'Try another search or dataset.':'Upload documents in Datasets to get started.'}</p></div>}</div>
  <dialog ref={dialog} className="reextract-dialog" aria-label="Document extraction options" onCancel={e=>{if(busy)e.preventDefault();}} onClose={()=>{setSelected('');setError('');}}>
   <div className="panel-head"><div><h2>{run?'Extraction progress':'Extract document'}</h2><p className="small muted">{doc?.name}</p></div><button className="btn icon" disabled={busy} aria-label="Close extraction options" onClick={()=>dialog.current?.close()}><X size={18}/></button></div>
   {!run&&<><label className="field">Prompt template<select aria-label="Re-extract prompt template" value={template} onChange={e=>setTemplate(e.target.value)} disabled={busy}><option value="">Choose a prompt template</option>{templates.filter(t=>!t.dataset_id||t.dataset_id===dataset?.id).map(t=><option key={t.id} value={t.id}>{t.name}</option>)}</select></label><p className="small muted">Uses {chosen?.name||'the dataset default extraction model'}. Saved results and originals are preserved.</p>
   {!chosen&&<p role="alert" className="upload-notice">Set a default extraction model for this dataset. <button className="text-button" onClick={()=>{dialog.current?.close();onConfigure(dataset?.id||'');}}>Open dataset settings</button></p>}
   {!templates.length&&<p role="alert">Create a prompt template on the Prompt templates screen first.</p>}
   {needsConsent&&<label className="check"><input type="checkbox" checked={external} onChange={e=>setExternal(e.target.checked)} disabled={busy}/>I approve sending document content to {chosen.provider}. Provider charges may apply.</label>}</>}
   {job&&<JobProgress job={job}/>}
   {job&&['queued','running'].includes(job.status)&&<p className="small muted">If you close this window, the background progress popup will keep you informed.</p>}
   {error&&<p className="review-error" role="alert">{error}</p>}
   <div className="row wrap">{!run?<button className="btn primary" disabled={busy||!template||!chosen||(needsConsent&&!external)} onClick={submit}><FileSearch size={16}/>{busy?'Starting…':'Start extraction'}</button>:latest?.status==='ready'||job?.status==='completed'?<button className="btn primary" disabled={busy} onClick={async()=>{if(submitting.current)return;submitting.current=true;setBusy(true);try{const result=await api(`/extractions/${run.id}`);dialog.current?.close();onReview(result);}catch(e){setError((e as Error).message);}finally{submitting.current=false;setBusy(false);}}}>Review results</button>:null}<button className="btn" disabled={busy} onClick={()=>dialog.current?.close()}>{run?'Close':'Cancel'}</button></div>
  </dialog>
 </section>;
}
