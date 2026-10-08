"use client";
import {Loader2} from "lucide-react";
type Entity=Record<string,any>;
const labels:Record<string,string>={upload:'Upload',extract:'Read document',index:'Build index',prepare:'Prepare sources',generate:'Extract fields',validate:'Validate and save',ready:'Ready'};
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
export function OperationProgress({requests,jobs}:{requests:{id:string;label:string}[];jobs:Entity[]}) {
 const active=jobs.filter(j=>['queued','running'].includes(j.status));
 if(!requests.length&&!active.length)return null;
 return <aside className="operation-popup" aria-label="Workspace progress" role="status" aria-live="polite">
  <div className="row"><Loader2 size={18} className="animate-spin"/><strong>{requests.length?'Working…':'Processing in background'}</strong></div>
  {requests.length>0&&<ul>{Array.from(new Set(requests.map(r=>r.label))).map(label=><li key={label}>{label}</li>)}</ul>}
  {active.map(job=><JobProgress key={job.id} job={job}/>)}
 </aside>;
}
