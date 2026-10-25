"use client";
import {useEffect,useRef,useState} from 'react';
import {ActionButton} from './action-button';
import {JobProgress} from './operation-progress';
import './jobs-activity.css';
type Entity=Record<string,any>;
const active=(status:string)=>['pending','queued','running'].includes(status);
const attention=(status:string)=>['failed','cancelled'].includes(status);
const words:Record<string,string>={index:'Index document',extract:'Extract fields',queued:'Queued',pending:'Waiting',running:'In progress',completed:'Completed',failed:'Failed',cancelled:'Cancelled'};
const readable=(value:string)=>words[value]||value.replaceAll('_',' ');
export function jobPresentation(job:Entity,documents:Entity[],extractions:Entity[]=[]){
 const target=job.document_id||job.target_id;
 const document=documents.find(item=>item.id===target);
 const extraction=extractions.find(item=>item.id===target);
 const stages=Object.values(job.workflow?.stages||{}) as Entity[];
 const completed=stages.filter(stage=>stage.status==='completed').length;
 const raw=stages.length?completed/stages.length*100:typeof job.progress==='number'&&Number.isFinite(job.progress)?job.progress:job.status==='completed'?100:undefined;
 return {name:document?.name||extraction?.name||'Resource details unavailable',kind:readable(job.kind||job.type||'Processing'),hasStages:stages.length>0,extractionId:job.kind==='extract'&&extraction?.status==='ready'?extraction.id:undefined,progress:raw===undefined?undefined:Math.max(0,Math.min(100,Math.round(raw))),progressLabel:stages.length?`${completed} of ${stages.length} stages completed`:raw===undefined?'Progress details unavailable':'Reported processing progress'};
}
export function JobsActivity({jobs,documents,extractions=[],busy,onRetry,onCancel,onReview}:{jobs:Entity[];documents:Entity[];extractions?:Entity[];busy:boolean;onRetry:(job:Entity)=>void;onCancel:(job:Entity)=>void;onReview?:(id:string)=>void}){
 const [filter,setFilter]=useState('all');
 const filters=useRef<HTMLDivElement>(null),actionJob=useRef<string|null>(null);
 const choices=[{id:'all',label:'All',count:jobs.length},{id:'active',label:'Active',count:jobs.filter(job=>active(job.status)).length},{id:'attention',label:'Needs attention',count:jobs.filter(job=>attention(job.status)).length},{id:'completed',label:'Completed',count:jobs.filter(job=>job.status==='completed').length}];
 const visible=jobs.filter(job=>filter==='all'||filter==='active'&&active(job.status)||filter==='attention'&&attention(job.status)||filter==='completed'&&job.status==='completed');
 const signature=visible.map(job=>job.id).join(',');
 useEffect(()=>{if(actionJob.current&&!visible.some(job=>job.id===actionJob.current)){if(document.activeElement===document.body)filters.current?.querySelector<HTMLButtonElement>('button[aria-pressed=true]')?.focus();actionJob.current=null;}},[signature]);
 return <section className="jobs-activity" aria-labelledby="jobs-heading">
  <div className="jobs-heading"><div><h2 id="jobs-heading">Processing history</h2><p>Follow actual processing stages and resolve the files that need attention.</p></div></div>
  <div ref={filters} className="jobs-filters" role="group" aria-label="Filter jobs">{choices.map(choice=><button key={choice.id} type="button" className="btn" aria-pressed={filter===choice.id} onClick={()=>setFilter(choice.id)}>{choice.label}<span>{choice.count}</span></button>)}</div>
  <p className="jobs-summary" role="status" aria-live="polite">{choices[1].count} active · {choices[2].count} need attention. Progress counts completed stages, not remaining time.</p>
  {!visible.length?<div className="jobs-empty"><h3>{jobs.length?'No jobs match this filter':'No processing jobs yet'}</h3><p>{jobs.length?'Choose another filter to see your saved processing history.':'Jobs appear after you explicitly upload, index or extract documents.'}</p>{jobs.length>0&&<button type="button" className="btn" onClick={()=>setFilter('all')}>Show all jobs</button>}</div>:<ul className="jobs-list">{visible.map(job=>{const info=jobPresentation(job,documents,extractions);return <li key={job.id}>
   <article className="job-row" aria-labelledby={`job-${job.id}`}>
    <div className="job-resource"><h3 id={`job-${job.id}`}>{info.name}</h3><span>{info.kind}</span><small>Job <code title={job.id}>{job.id.slice(0,8)}</code> · {job.attempts||0} attempt{job.attempts===1?'':'s'}</small></div>
    <div className="job-state"><span data-status={job.status}>{readable(job.status||'unknown')}</span>{job.created_at>0&&<time dateTime={new Date(job.created_at*1000).toISOString()}>{new Date(job.created_at*1000).toLocaleString()}</time>}</div>
    <div className="job-meter"><label htmlFor={`job-progress-${job.id}`}>{info.progressLabel}</label><progress id={`job-progress-${job.id}`} max={100} value={info.progress} aria-label={`${info.name} processing progress`}/>{info.progress!==undefined&&<small>{info.progress}% {info.hasStages?'of stages reported complete':'reported progress'}</small>}</div>
    <div className="job-actions">{attention(job.status)&&<ActionButton className="btn" disabled={busy} label="Retry" action="retry" aria-label={`Retry ${info.kind.toLowerCase()} for ${info.name}`} onClick={()=>{actionJob.current=job.id;onRetry(job);}}/>} {active(job.status)&&<button type="button" className="btn danger" disabled={busy} aria-label={`Cancel ${info.kind.toLowerCase()} for ${info.name}`} onClick={()=>onCancel(job)}>Cancel</button>}{info.extractionId&&onReview&&<ActionButton className="btn" label="Review result" action="review" aria-label={`Review result ${info.name}`} onClick={()=>onReview(info.extractionId)}/>}</div>
    {job.error&&<p className="job-error"><strong>Needs attention:</strong> {job.error}</p>}
    {job.workflow?.stages&&<details className="job-details"><summary>View processing stages</summary><JobProgress job={job}/></details>}
   </article></li>;})}</ul>}
 </section>;
}
