"use client";
import {ActionButton} from "./action-button";
import {useEffect,useRef,useState} from 'react';
import {FileScan,X} from 'lucide-react';
import {eligibleModels} from './dataset-workspace';
import {JobProgress} from './operation-progress';
import {useAgentConsent} from './agent-consent';
import {suggestedExtractionName} from './extraction-name';

type Entity=Record<string,any>;
type Api=(path:string,method?:string,body?:unknown)=>Promise<any>;
export function ReExtractionDialog({source,documents,datasets,templates,extractions,jobs,api,onRefresh,onReview,onConfigure,onClose,onProgressVisibilityChange}:{source:Entity;documents:Entity[];datasets:Entity[];templates:Entity[];extractions:Entity[];jobs:Entity[];api:Api;onRefresh:()=>void;onReview:(e:Entity)=>void;onConfigure:(id:string)=>void;onClose:()=>void;onProgressVisibilityChange?:(jobId:string|null)=>void}){
 const dataset=datasets.find(d=>d.id===(source.dataset_id||source.parent_id));
 const sourceDocs=documents.filter(d=>source.document_ids?.includes(d.id));
 const models=eligibleModels(dataset,'extraction'),chosen=models.find(m=>m.id===dataset?.default_extraction_model_id)||(models.length===1?models[0]:undefined);
 const prompts=templates.filter(t=>!t.dataset_id||t.dataset_id===dataset?.id);
 const [template,setTemplate]=useState(prompts.some(t=>t.id===source.template_id)?source.template_id:''),[busy,setBusy]=useState(false),[error,setError]=useState(''),[run,setRun]=useState<Entity|null>(null);
 const [name,setName]=useState(()=>suggestedExtractionName([source.name||sourceDocs[0]?.name||'Document extraction']));
 const consent=useAgentConsent(api);
 const apiRef=useRef(api),refreshRef=useRef(onRefresh);apiRef.current=api;refreshRef.current=onRefresh;
 const key=useRef(crypto.randomUUID()),submitting=useRef(false),dialog=useRef<HTMLDialogElement>(null);
 const ready=sourceDocs.length===source.document_ids?.length&&sourceDocs.length>0&&sourceDocs.every(d=>d.status==='ready')&&dataset?.active!==false;
 const needsReindex=sourceDocs.some(d=>d.requires_reindex);
 const workflowJobs=(run?.workflow?.calls||[]).flatMap((call:Entity)=>call.jobs||[]).map((job:Entity)=>jobs.find(j=>j.id===job.id)||job);
 const workflowEntry=(run?.workflow?.calls||[]).flatMap((call:Entity)=>call.result?.extractions||[]).find((entry:Entity)=>!entry.superseded);
 const resultId=workflowEntry?.extraction_id||run?.id;
 const workflowError=(run?.workflow?.calls||[]).find((call:Entity)=>call.error)?.error;
 const job=jobs.find(j=>j.id===run?.job?.id)||run?.job||workflowJobs.find((job:Entity)=>job.status!=='completed')||workflowJobs.at(-1),latest=extractions.find(e=>e.id===resultId)||(workflowEntry?{status:workflowEntry.status==='completed'?'ready':workflowEntry.status,error:workflowEntry.error}:run);
 useEffect(()=>{dialog.current?.showModal();return()=>dialog.current?.close();},[]);
 useEffect(()=>{onProgressVisibilityChange?.(job?.id||null);return()=>onProgressVisibilityChange?.(null);},[job?.id,onProgressVisibilityChange]);
 const tracking=!!run?.workflow?.calls.some((call:Entity)=>['waiting','running'].includes(call.status)||(run.workflow.auto_continue&&call.status==='pending'));
 useEffect(()=>{
  if(!run?.workflow?.id||!tracking)return;
  let stopped=false,timer:ReturnType<typeof setTimeout>;
  const poll=async()=>{
   try{const workflow=await apiRef.current(`/agent-v2/plans/${run.workflow.id}`);if(!stopped){setRun({workflow});refreshRef.current();setError('');}}
   catch(err){if(!stopped)setError(`Could not refresh progress. Accepted work continues in the background. ${(err as Error).message}`);}
   finally{if(!stopped)timer=setTimeout(poll,3000);}
  };
  timer=setTimeout(poll,1500);
  return()=>{stopped=true;clearTimeout(timer);};
 },[run?.workflow?.id,tracking]);
 const submit=async()=>{
  if(submitting.current||!ready||!chosen||!template||!name.trim()||run)return;
  submitting.current=true;setBusy(true);setError('');
  try{
   const approval=await consent.request({dataset_id:dataset!.id,roles:['embedding','extraction']});
   if(!approval)return;
   if(needsReindex){
    const workflow=await api(`/extractions/${source.id}/rerun`,'POST',{source_version:source.version||1,template_id:template,display_name:name.trim(),allow_external:true,idempotency_key:key.current});
    setRun({workflow});
   }else setRun(await api('/extractions','POST',{dataset_id:dataset?.id,document_ids:source.document_ids,template_id:template,allow_external:true,merge_records:!!source.merge_records,wait_for_index:!!source.merge?.logical,display_name:name.trim(),idempotency_key:key.current}));
   onRefresh();
  }catch(err){setError((err as Error).message);}finally{submitting.current=false;setBusy(false);}
 };
 return <><dialog ref={dialog} className="reextract-dialog" aria-label="Re-extract options" onCancel={event=>{if(busy)event.preventDefault();}} onClose={onClose}>
  <div className="panel-head"><div><h2>{run?'Re-extraction progress':'Re-extract'}</h2><p className="small muted">{dataset?.name} · {sourceDocs.map(d=>d.name).join(', ')||source.name}</p></div><button title="Close re-extract options" className="btn icon" disabled={busy} aria-label="Close re-extract options" onClick={()=>dialog.current?.close()}><X size={18}/></button></div>
  <p className="small muted">Previous extraction: <code>{source.id}</code>. Its saved results and original files are preserved.</p>
  {!run&&<><label className="field">Prompt template<select aria-label="Re-extract prompt template" value={template} onChange={e=>setTemplate(e.target.value)} disabled={busy}><option value="">Choose a prompt template</option>{prompts.map(t=><option key={t.id} value={t.id}>{t.name} · v{t.version||1}</option>)}</select></label>
  <label className="field">Extraction name<input aria-label="Re-extraction name" maxLength={200} value={name} disabled={busy} onChange={e=>setName(e.target.value)}/><span className="small muted">Edit this name if needed. The suffix uses your local date and time.</span></label>
  <p className="small muted">Uses {chosen?.name||'the dataset default extraction model'}{source.merge_records?' · keeps separate records for each original':''}.</p>
  {!chosen&&<p role="alert" className="upload-notice">Set a default extraction model for this dataset. <ActionButton className="text-button" onClick={()=>{dialog.current?.close();onConfigure(dataset?.id||'');}} label="Open Model Mapping" action="mapping"/></p>}
  {ready&&needsReindex&&<p role="status" className="upload-notice">The indexing configuration changed. Confirm once to rebuild the source indexes with this dataset’s current embedding and OCR models, then re-extract. Earlier results and originals are preserved.</p>}
  {!ready&&<p role="alert" className="upload-notice">Wait for source document processing to finish and make sure the dataset is active. <ActionButton className="text-button" onClick={()=>{dialog.current?.close();onConfigure(dataset?.id||'');}} label="Open Model Mapping" action="mapping"/></p>}
  {!prompts.length&&<p role="alert">Create a prompt in Onboard → Prompt first.</p>}
  </>}
  {run?.workflow?workflowJobs.map((job:Entity)=><JobProgress key={job.id} job={job}/>):job&&<JobProgress job={job}/>}
  {job&&['queued','running','blocked'].includes(job.status)&&<p className="small muted">Processing continues if you close this dialog. Follow the new run in Review.</p>}
  {(error||workflowError||latest?.error)&&<p className="review-error" role="alert">{error||workflowError||latest?.error}</p>}
  <div className="row wrap">{!run?<button className="btn primary" disabled={busy||!ready||!template||!chosen||!name.trim()} onClick={submit}><FileScan size={16}/>{busy?'Starting…':needsReindex?'Reindex and re-extract':'Start re-extraction'}</button>:latest?.status==='ready'||(!run?.workflow&&job?.status==='completed')?<ActionButton className="btn primary" disabled={busy} onClick={async()=>{if(submitting.current)return;submitting.current=true;setBusy(true);try{const result=await api(`/extractions/${resultId}`);dialog.current?.close();onReview(result);}catch(err){setError((err as Error).message);}finally{submitting.current=false;setBusy(false);}}} label="Review results" action="review"/>:null}<button className="btn" disabled={busy} onClick={()=>dialog.current?.close()}>{run?'Close':'Cancel'}</button></div>
 </dialog>{consent.popup}</>;
}
