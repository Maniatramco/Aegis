"use client";
import {useEffect,useRef,useState} from 'react';
import {FileSearch,X} from 'lucide-react';
import {eligibleModels} from './dataset-workspace';
import {JobProgress} from './operation-progress';

type Entity=Record<string,any>;
type Api=(path:string,method?:string,body?:unknown)=>Promise<any>;
export function ReExtractionDialog({source,documents,datasets,templates,extractions,jobs,api,onRefresh,onReview,onConfigure,onClose,onProgressVisibilityChange}:{source:Entity;documents:Entity[];datasets:Entity[];templates:Entity[];extractions:Entity[];jobs:Entity[];api:Api;onRefresh:()=>void;onReview:(e:Entity)=>void;onConfigure:(id:string)=>void;onClose:()=>void;onProgressVisibilityChange?:(jobId:string|null)=>void}){
 const dataset=datasets.find(d=>d.id===(source.dataset_id||source.parent_id));
 const sourceDocs=documents.filter(d=>source.document_ids?.includes(d.id));
 const models=eligibleModels(dataset,'extraction'),chosen=models.find(m=>m.id===dataset?.default_extraction_model_id)||(models.length===1?models[0]:undefined);
 const prompts=templates.filter(t=>!t.dataset_id||t.dataset_id===dataset?.id);
 const [template,setTemplate]=useState(prompts.some(t=>t.id===source.template_id)?source.template_id:''),[busy,setBusy]=useState(false),[error,setError]=useState(''),[external,setExternal]=useState(false),[run,setRun]=useState<Entity|null>(null);
 const key=useRef(crypto.randomUUID()),submitting=useRef(false),dialog=useRef<HTMLDialogElement>(null);
 const needsConsent=!!chosen?.provider&&!['ollama','mock','sentence_transformers'].includes(chosen.provider);
 const ready=sourceDocs.length===source.document_ids?.length&&sourceDocs.length>0&&sourceDocs.every(d=>d.status==='ready'&&!d.requires_reindex)&&dataset?.active!==false;
 const job=jobs.find(j=>j.id===run?.job?.id)||run?.job,latest=extractions.find(e=>e.id===run?.id)||run;
 useEffect(()=>{dialog.current?.showModal();return()=>dialog.current?.close();},[]);
 useEffect(()=>{onProgressVisibilityChange?.(job?.id||null);return()=>onProgressVisibilityChange?.(null);},[job?.id,onProgressVisibilityChange]);
 const submit=async()=>{
  if(submitting.current||!ready||!chosen||!template||run)return;
  submitting.current=true;setBusy(true);setError('');
  try{
   setRun(await api('/extractions','POST',{dataset_id:dataset?.id,document_ids:source.document_ids,template_id:template,model_id:chosen.id,allow_external:external,merge_records:!!source.merge_records,wait_for_index:!!source.merge?.logical,display_name:source.name,idempotency_key:key.current}));
   onRefresh();
  }catch(err){setError((err as Error).message);}finally{submitting.current=false;setBusy(false);}
 };
 return <dialog ref={dialog} className="reextract-dialog" aria-label="Re-extract options" onCancel={event=>{if(busy)event.preventDefault();}} onClose={onClose}>
  <div className="panel-head"><div><h2>{run?'Re-extraction progress':'Re-extract'}</h2><p className="small muted">{dataset?.name} · {sourceDocs.map(d=>d.name).join(', ')||source.name}</p></div><button className="btn icon" disabled={busy} aria-label="Close re-extract options" onClick={()=>dialog.current?.close()}><X size={18}/></button></div>
  <p className="small muted">Previous extraction: <code>{source.id}</code>. Its saved results and original files are preserved.</p>
  {!run&&<><label className="field">Prompt template<select aria-label="Re-extract prompt template" value={template} onChange={e=>setTemplate(e.target.value)} disabled={busy}><option value="">Choose a prompt template</option>{prompts.map(t=><option key={t.id} value={t.id}>{t.name} · v{t.version||1}</option>)}</select></label>
  <p className="small muted">Uses {chosen?.name||'the dataset default extraction model'}{source.merge_records?' · keeps separate records for each original':''}.</p>
  {!chosen&&<p role="alert" className="upload-notice">Set a default extraction model for this dataset. <button className="text-button" onClick={()=>{dialog.current?.close();onConfigure(dataset?.id||'');}}>Open dataset settings</button></p>}
  {!ready&&<p role="alert" className="upload-notice">The source files must be ready in an active dataset. <button className="text-button" onClick={()=>{dialog.current?.close();onConfigure(dataset?.id||'');}}>Open dataset settings</button></p>}
  {!prompts.length&&<p role="alert">Create a prompt in Onboard → Prompt first.</p>}
  {needsConsent&&<label className="check"><input type="checkbox" checked={external} onChange={e=>setExternal(e.target.checked)} disabled={busy}/>I approve sending document content to {chosen.provider}. Provider charges may apply.</label>}</>}
  {job&&<JobProgress job={job}/>}
  {job&&['queued','running'].includes(job.status)&&<p className="small muted">Processing continues if you close this dialog. Follow the new run in Review.</p>}
  {(error||latest?.error)&&<p className="review-error" role="alert">{error||latest?.error}</p>}
  <div className="row wrap">{!run?<button className="btn primary" disabled={busy||!ready||!template||!chosen||(needsConsent&&!external)} onClick={submit}><FileSearch size={16}/>{busy?'Starting…':'Start re-extraction'}</button>:latest?.status==='ready'||job?.status==='completed'?<button className="btn primary" disabled={busy} onClick={async()=>{if(submitting.current)return;submitting.current=true;setBusy(true);try{const result=await api(`/extractions/${run.id}`);dialog.current?.close();onReview(result);}catch(err){setError((err as Error).message);}finally{submitting.current=false;setBusy(false);}}}>Review results</button>:null}<button className="btn" disabled={busy} onClick={()=>dialog.current?.close()}>{run?'Close':'Cancel'}</button></div>
 </dialog>;
}
