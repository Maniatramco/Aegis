"use client";
import {Loader2} from "lucide-react";
import { BatchProgress } from "./batch-progress";
import { currentUploadStep, readableUploadError, type UploadProgressItem } from "./batch-workflow";
type Entity=Record<string,any>;
const labels:Record<string,string>={upload:'Upload',extract:'Read document',index:'Build index',prepare:'Prepare sources',generate:'Extract fields',validate:'Validate and save',ready:'Ready'};
export function extractionProgressJob(extraction:Entity|null,jobs:Entity[]):Entity|undefined {
 if(!extraction)return undefined;
 const recorded=extraction.job;
 const live=recorded?.id&&jobs.find(job=>job.id===recorded.id);
 if(live)return live;
 const matching=jobs.filter(job=>job.kind==='extract'&&job.target_id===extraction.id);
 matching.sort((a,b)=>Number(b.created_at||0)-Number(a.created_at||0));
 return matching[0]||recorded;
}
export function JobProgress({job}:{job:Entity}) {
 const stages=Object.entries(job.workflow?.stages||{}) as [string,Entity][];
 return <div className="job-progress" aria-label="Processing workflow">
  <div className="row between"><strong>{job.kind==='extract'?'Extraction':'Document processing'}</strong><span>{job.status==='running'?'In progress':job.status}</span></div>
  <progress max={100} value={job.progress||0} aria-label="Processing progress" />
  {stages.length>0&&<ol className="job-stage-list">{stages.map(([name,stage])=><li key={name} data-status={stage.status}><span>{stage.status==='completed'?'✓':stage.status==='running'?'●':'○'}</span>{labels[name]||name}<small>{stage.status==='blocked'?'Waiting':stage.status}</small></li>)}</ol>}
  {job.status==='running'&&<p className="small muted">{job.workflow?.current==='generate'?'The model is extracting your fields. This may take a few minutes for long documents.':'Processing continues in the background.'} Progress reports completed stages, not an estimated time.</p>}
  {job.error&&<p role="alert" className="review-error">{job.error}</p>}
 </div>;
}
export function OperationProgress({requests,jobs,uploadItems=[],documents=[],uploadWorkflowVisible=false,visibleJobId=null}:{requests:{id:string;label:string}[];jobs:Entity[];uploadItems?:UploadProgressItem[];documents?:Entity[];uploadWorkflowVisible?:boolean;visibleJobId?:string|null}) {
 const active=jobs.filter(j=>['queued','running'].includes(j.status)&&j.id!==visibleJobId);
 const tracked=new Set(uploadItems.flatMap(item=>item.document?[item.id,item.document.id]:[]));
 const processingBatch=uploadItems.some(item=>item.status==='uploading'||item.processing);
 const untracked=active.filter(job=>job.kind==='index'&&!tracked.has(job.document_id||job.target_id)).map(job=>{
  const document=documents.find(d=>d.id===(job.document_id||job.target_id));
  return {id:job.document_id||job.target_id,name:document?.name||'Document',status:'submitted',document:document||{status:'processing'},job,processing:true};
 });
 const batchItems:UploadProgressItem[]=[...(processingBatch?uploadItems:[]),...untracked];
 const otherJobs=active.filter(job=>job.kind!=='index');
 const requestLabels=Array.from(new Set(requests.map(request=>request.label)));
 const loadingTitle=requestLabels.length===1?requestLabels[0]:requestLabels.every(label=>label.startsWith('Loading '))?'Loading workspace…':'Updating workspace…';
 if(!requests.length&&!otherJobs.length&&(!batchItems.length||uploadWorkflowVisible))return null;
 return <aside className={`operation-popup${requests.length?' is-loading':''}`} aria-label="Workspace progress" role="status" aria-live="polite">
  <div className="operation-popup-heading"><span className="operation-popup-icon"><Loader2 size={20} className="animate-spin" aria-hidden="true"/></span><div><strong>{requests.length?loadingTitle:'Processing in background'}</strong>{requests.length>0&&<p className="operation-popup-description">This will close automatically when complete.</p>}</div></div>
  {requestLabels.length>1&&<ul className="operation-request-list">{requestLabels.map(label=><li key={label}>{label}</li>)}</ul>}
  {!uploadWorkflowVisible&&batchItems.length>0&&<><BatchProgress items={batchItems} compact/><ul className="batch-popup-documents" aria-label="Background document statuses">{batchItems.map(item=>{const error=item.error||(item.failed&&(item.document?.error||item.job?.error));return <li key={item.id}><strong>{item.name}</strong><span>{currentUploadStep(item)}</span>{error&&<p className="batch-popup-error">{readableUploadError(error)}</p>}</li>;})}</ul></>}
  {otherJobs.map(job=><JobProgress key={job.id} job={job}/>)}
 </aside>;
}
