"use client";
import {Loader2} from "lucide-react";
import {useState} from "react";
import { BatchProgress } from "./batch-progress";
import {WorkflowStepper} from "./workflow-stepper";
import { currentUploadStep, readableUploadError, type UploadProgressItem } from "./batch-workflow";
type Entity=Record<string,any>;
const labels:Record<string,string>={upload:'Upload',extract:'Read document / OCR',index:'Build index',prepare:'Prepare sources',generate:'Extract fields',retrieving:'Retrieve evidence',reranking:'Rerank evidence',validate:'Validate fields',writing_output:'Write Parquet',ready:'Ready'};
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
 if(job.kind==='extract') {
  const completed=stages.filter(([,stage])=>stage.status==='completed').length;
  const progress=stages.length?Math.round(completed/stages.length*100):0;
  const failed=['failed','cancelled'].includes(job.status);
  const summary=job.status==='completed'?'Extraction completed. Your result is ready to review.':failed?'Extraction stopped. Check the reason below.':job.workflow?.current==='generate'?'The model is extracting your fields. Progress follows completed stages.':stages.length?'Preparing and validating your extraction. Progress follows completed stages.':'Stage details are unavailable for this job. Check its status.';
  return <div className="job-progress" aria-label="Processing workflow"><section className="batch-progress is-compact" aria-label="Extraction workflow">
   <div className="batch-progress-heading"><strong>Extraction workflow</strong><span>{job.status==='completed'?'Ready':failed?'Needs attention':job.status==='running'?'In progress':'Queued'}</span></div>
   <div className="batch-progress-track" role="progressbar" aria-label="Extraction progress" aria-valuemin={0} aria-valuemax={100} aria-valuenow={progress} aria-valuetext={stages.length?`${completed} of ${stages.length} stages completed`:'Stage details unavailable'}><span style={{width:`${progress}%`}}/></div>
   <WorkflowStepper label="Extraction workflow steps" steps={stages.map(([name,stage])=>({id:name,label:labels[name]||name,status:stage.status,statusLabel:stage.status==='blocked'?'Waiting':undefined}))}/>
   <p className="batch-progress-summary" role="status">{summary}</p>
   {job.error&&<p role="alert" className="review-error">{job.error}</p>}
  </section></div>;
 }
 if(job.kind==='index'&&stages.length)return <div className="job-progress" aria-label="Processing workflow"><BatchProgress compact items={[{id:job.target_id||job.id,name:'Document',status:'submitted',document:{status:job.status==='completed'?'ready':'processing'},job,ready:job.status==='completed',failed:['failed','cancelled'].includes(job.status),processing:['queued','running'].includes(job.status)}]}/>{job.error&&<p role="alert" className="review-error">{job.error}</p>}</div>;
 return <div className="job-progress" aria-label="Processing workflow">
  <div className="row between"><strong>{job.kind==='extract'?'Extraction':'Document processing'}</strong><span>{job.status==='running'?'In progress':job.status}</span></div>
  <progress max={100} value={job.progress||0} aria-label="Processing progress" />
  {job.workflow?.stages?.extract?.detail&&<p role="status" className="small muted">{job.workflow.stages.extract.detail}</p>}
  <WorkflowStepper label="Document processing steps" steps={stages.map(([name,stage])=>({id:name,label:labels[name]||name,status:stage.status,statusLabel:stage.status==='blocked'?'Waiting':undefined}))}/>
  {job.status==='running'&&<p className="small muted">{job.workflow?.current==='generate'?'The model is extracting your fields. This may take a few minutes for long documents.':'Processing continues in the background.'} Progress reports completed stages, not an estimated time.</p>}
  {job.error&&<p role="alert" className="review-error">{job.error}</p>}
 </div>;
}
export function OperationProgress({requests,jobs,uploadItems=[],documents=[],uploadWorkflowVisible=false,visibleJobId=null,visibleJobIds=[],workspaceLoading=false,compact=false,agentWorkspace=false}:{requests:{id:string;label:string}[];jobs:Entity[];uploadItems?:UploadProgressItem[];documents?:Entity[];uploadWorkflowVisible?:boolean;visibleJobId?:string|null;visibleJobIds?:string[];workspaceLoading?:boolean;compact?:boolean;agentWorkspace?:boolean}) {
 const [expanded,setExpanded]=useState(false);
 // Agent replies, document journeys and onboarding own their inline progress.
 // Never mirror API requests or job updates into a second floating workflow.
 if(agentWorkspace)return null;
 const active=jobs.filter(j=>['queued','running'].includes(j.status)&&j.id!==visibleJobId&&!visibleJobIds.includes(j.id));
 const backgroundUploads=uploadItems.filter(item=>!item.job?.id||(item.job.id!==visibleJobId&&!visibleJobIds.includes(item.job.id)));
 const tracked=new Set(backgroundUploads.flatMap(item=>item.document?[item.id,item.document.id]:[]));
 const processingBatch=backgroundUploads.some(item=>item.status==='uploading'||item.processing);
 const untracked=active.filter(job=>job.kind==='index'&&!tracked.has(job.document_id||job.target_id)).map(job=>{
  const document=documents.find(d=>d.id===(job.document_id||job.target_id));
  return {id:job.document_id||job.target_id,name:document?.name||'Document',status:'submitted',document:document||{status:'processing'},job,processing:true};
 });
 const batchItems:UploadProgressItem[]=[...(processingBatch?backgroundUploads:[]),...untracked];
 const otherJobs=active.filter(job=>job.kind!=='index');
 const requestLabels=Array.from(new Set(requests.map(request=>request.label)));
 const loadingTitle=requestLabels.length===1?requestLabels[0]:requestLabels.every(label=>label.startsWith('Loading '))?'Loading workspace…':'Updating workspace…';
 if(!workspaceLoading&&!requests.length&&!otherJobs.length&&(!batchItems.length||uploadWorkflowVisible))return null;
 return <aside className={`operation-popup${workspaceLoading||requests.length?' is-loading':''}${agentWorkspace?' in-agent':''}`} aria-label="Workspace progress" role="status" aria-live="polite">
  <div className="operation-popup-heading"><span className="operation-popup-icon"><Loader2 size={20} className="animate-spin" aria-hidden="true"/></span><div><strong>{workspaceLoading?'Loading your workspace…':requests.length?loadingTitle:'Processing in background'}</strong>{(workspaceLoading||requests.length>0)&&<p className="operation-popup-description">{workspaceLoading?'Getting your datasets, documents, and models ready.':'This will close automatically when complete.'}</p>}</div></div>
  {compact&&<button className="text-button" aria-expanded={expanded} onClick={()=>setExpanded(!expanded)}>{expanded?'Hide background progress':'Show background progress'}</button>}
  {(!compact||expanded)&&<>
  {!workspaceLoading&&requestLabels.length>1&&<ul className="operation-request-list">{requestLabels.map(label=><li key={label}>{label}</li>)}</ul>}
  {!uploadWorkflowVisible&&batchItems.length>0&&<><BatchProgress items={batchItems} compact/><ul className="batch-popup-documents" aria-label="Background document statuses">{batchItems.map(item=>{const error=item.error||(item.failed&&(item.document?.error||item.job?.error));return <li key={item.id}><strong>{item.name}</strong><span>{currentUploadStep(item)}</span>{error&&<p className="batch-popup-error">{readableUploadError(error)}</p>}</li>;})}</ul></>}
  {otherJobs.map(job=><JobProgress key={job.id} job={job}/>)}
  </>}
 </aside>;
}
