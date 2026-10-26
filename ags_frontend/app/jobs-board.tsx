"use client";
import {useState,type ReactNode} from 'react';
import {Square} from 'lucide-react';
import {ActionButton} from './action-button';

type Entity=Record<string,any>;
const RUNNING=['pending','queued','running','processing'],FAILED=['failed','cancelled'];
export const JOB_TABS=[['all','All'],['running','Running'],['failed','Failed'],['completed','Completed']] as const;
export function jobGroup(job:Entity){return RUNNING.includes(job.status)?'running':FAILED.includes(job.status)?'failed':job.status==='completed'?'completed':'other';}

/** Jobs as cards with status tabs; retry and cancel keep the page's existing handlers. */
export function JobsBoard({jobs,documents,busy,formatDate,onRetry,onCancel,empty}:{jobs:Entity[];documents:Entity[];busy:boolean;formatDate:(value:number)=>string;onRetry:(job:Entity)=>void;onCancel:(job:Entity)=>void;empty:ReactNode}){
 const [tab,setTab]=useState<string>('all');
 const counts=Object.fromEntries(JOB_TABS.map(([id])=>[id,id==='all'?jobs.length:jobs.filter(job=>jobGroup(job)===id).length]));
 const visible=tab==='all'?jobs:jobs.filter(job=>jobGroup(job)===tab);
 if(!jobs.length)return <section className="panel">{empty}</section>;
 return <section className="jobs-board" aria-label="Processing jobs">
  <div className="jobs-tabs" role="group" aria-label="Filter jobs">{JOB_TABS.map(([id,label])=><button key={id} type="button" aria-pressed={tab===id} onClick={()=>setTab(id)}>{label}<span>{counts[id]}</span></button>)}</div>
  <p className="jobs-refresh small muted">Refreshes automatically every few seconds.</p>
  <ul className="jobs-list">{visible.map(job=>{
   const group=jobGroup(job),progress=Math.min(100,Math.round(job.progress||0));
   const name=documents.find(d=>d.id===job.document_id)?.name||job.document_id||job.id;
   return <li key={job.id} className="jobs-card" data-group={group}>
    <div className="jobs-card-main">
     <div className="jobs-card-title"><span className="jobs-kind">{(job.kind||job.type||'Processing').replaceAll('_',' ')}</span><strong title={name}>{name}</strong></div>
     <span className="jobs-meta">{formatDate(job.created_at)} · attempt {job.attempts||0}</span>
     {job.error&&<p className="jobs-error" role="alert">{job.error}</p>}
    </div>
    <div className="jobs-progress" aria-label={`Progress ${progress} percent`}><div className="progress"><span style={{width:`${progress}%`}}/></div><span>{progress}%</span></div>
    <div className="jobs-actions">
     <span className="jobs-status" data-group={group}>{job.status}</span>
     {FAILED.includes(job.status)&&<ActionButton className="btn primary" disabled={busy} onClick={()=>onRetry(job)} label="Retry" action="retry" showLabel/>}
     {['pending','queued','running'].includes(job.status)&&<button className="btn danger" disabled={busy} onClick={()=>onCancel(job)}><Square size={13}/>Cancel</button>}
    </div>
   </li>;})}
   {!visible.length&&<li className="jobs-none">No {tab} jobs right now.</li>}
  </ul>
 </section>;
}
