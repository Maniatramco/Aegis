"use client";
import {useState,type ReactNode} from 'react';
import {Search,Square} from 'lucide-react';
import {ActionButton} from './action-button';
import {openAttention} from './needs-attention';
import {SummaryTiles} from './summary-tiles';

type Entity=Record<string,any>;
const RUNNING=['pending','queued','running','processing'],FAILED=['failed','cancelled'];
export const JOB_TABS=[['all','All'],['running','Running'],['failed','Failed'],['completed','Completed']] as const;
export function jobGroup(job:Entity){return RUNNING.includes(job.status)?'running':FAILED.includes(job.status)?'failed':job.status==='completed'?'completed':'other';}
const KINDS:Record<string,string>={index:'Indexing',extract:'Extraction',reextract:'Re-extraction',upload:'Upload'};
export const kindLabel=(kind='')=>KINDS[kind]||kind.replaceAll('_',' ')||'Processing';
/** Who started a job; older API responses without it fall back to an unknown starter. */
export const starter=(job:Entity)=>job.started_by||{id:null,label:'Unknown',self:false};
const starterKey=(job:Entity)=>starter(job).id||starter(job).label;

/** Seconds a job has taken: finished jobs stop at their last update, active ones keep counting. */
export function jobSeconds(job:Entity,now:number){const end=jobGroup(job)==='running'?now:(job.updated_at||job.created_at);return Math.max(0,(end||now)-(job.created_at||now));}
export function durationLabel(seconds:number){seconds=Math.round(seconds);if(seconds<60)return `${seconds}s`;const m=Math.floor(seconds/60);if(m<60)return `${m}m ${seconds%60}s`;return `${Math.floor(m/60)}h ${m%60}m`;}
export function ago(seconds:number){if(seconds<60)return 'just now';const m=Math.floor(seconds/60);if(m<60)return `${m} min ago`;const h=Math.floor(m/60);return h<24?`${h} h ago`:`${Math.floor(h/24)} d ago`;}

/** Workload at a glance, from the loaded jobs only. */
export function jobSummary(jobs:Entity[],now:number){
 const running=jobs.filter(j=>['running','processing'].includes(j.status)).length,queued=jobs.filter(j=>['queued','pending'].includes(j.status)).length;
 const failed=jobs.filter(j=>jobGroup(j)==='failed').length;
 const done=jobs.filter(j=>j.status==='completed'),recent=done.filter(j=>now-(j.updated_at||j.created_at)<=86400);
 const average=done.length?done.reduce((sum,j)=>sum+jobSeconds(j,now),0)/done.length:0;
 return [
  {label:'Running now',value:running,detail:`${queued} queued`,tone:'info'},
  {label:'Failed',value:failed,detail:'need attention',tone:'error',attention:{}},
  {label:'Completed',value:recent.length,detail:'in the last 24 hours',tone:'ok'},
  {label:'Average time',value:done.length?durationLabel(average):'—',detail:'per completed job',tone:''},
 ];
}

/** Activity per person: who is running, waiting on, or has failed work. */
export function jobsByPerson(jobs:Entity[]){
 const people=new Map<string,{key:string;label:string;self:boolean;running:number;failed:number;completed:number;last:number}>();
 for(const job of jobs){const who=starter(job),key=starterKey(job);const row=people.get(key)||{key,label:who.label,self:Boolean(who.self),running:0,failed:0,completed:0,last:0};
  const group=jobGroup(job);if(group==='running')row.running++;else if(group==='failed')row.failed++;else if(group==='completed')row.completed++;
  row.last=Math.max(row.last,job.updated_at||job.created_at||0);people.set(key,row);}
 return [...people.values()].sort((a,b)=>Number(b.self)-Number(a.self)||b.running-a.running||b.last-a.last);
}
const initials=(label:string)=>label==='You'?'You':label.split(/[\s._@-]+/).filter(Boolean).slice(0,2).map(part=>part[0]?.toUpperCase()).join('')||'?';

/** Jobs as a monitoring view: workload tiles, activity per person, filters and a live job table. Retry and cancel keep the page's existing handlers. */
export function JobsBoard({jobs,documents,datasets=[],extractions=[],busy,formatDate,onRetry,onCancel,empty,now=Date.now()/1000}:{jobs:Entity[];documents:Entity[];datasets?:Entity[];extractions?:Entity[];busy:boolean;formatDate:(value:number)=>string;onRetry:(job:Entity)=>void;onCancel:(job:Entity)=>void;empty:ReactNode;now?:number}){
 const [tab,setTab]=useState<string>('all'),[person,setPerson]=useState(''),[kind,setKind]=useState(''),[query,setQuery]=useState('');
 if(!jobs.length)return <section className="panel">{empty}</section>;
 const extraction=(job:Entity)=>extractions.find(e=>e.id===job.target_id);
 const docName=(job:Entity)=>documents.find(d=>d.id===(job.document_id||job.target_id))?.name||extraction(job)?.name||extraction(job)?.display_name;
 const datasetName=(job:Entity)=>{const doc=documents.find(d=>d.id===(job.document_id||job.target_id));const run=extraction(job),id=job.dataset_id||doc?.dataset_id||doc?.kb_id||run?.dataset_id||run?.kb_id||run?.parent_id;return datasets.find(d=>d.id===id)?.name||'';};
 const people=jobsByPerson(jobs),kinds=[...new Set(jobs.map(j=>j.kind).filter(Boolean))];
 const scoped=jobs.filter(job=>(!person||starterKey(job)===person)&&(!kind||job.kind===kind)&&(!query.trim()||`${docName(job)||''} ${datasetName(job)} ${job.id}`.toLowerCase().includes(query.trim().toLowerCase())));
 const counts=Object.fromEntries(JOB_TABS.map(([id])=>[id,id==='all'?scoped.length:scoped.filter(job=>jobGroup(job)===id).length]));
 const visible=tab==='all'?scoped:scoped.filter(job=>jobGroup(job)===tab);
 const filtered=Boolean(person||kind||query.trim());
 return <section className="jobs-board jobs-monitor" aria-label="Processing jobs">
  <SummaryTiles label="Job monitoring summary" tiles={jobSummary(jobs,now)}/>
  <div className="jobs-monitor-layout">
   <aside className="jobs-people" aria-label="Activity by person">
    <h3>Activity by person</h3>
    <ul>{people.map(row=><li key={row.key}><button type="button" aria-pressed={person===row.key} onClick={()=>setPerson(person===row.key?'':row.key)} title={`Show only jobs started by ${row.label}`}>
     <span className="jobs-avatar" data-self={row.self||undefined} aria-hidden="true">{initials(row.label)}</span>
     <span className="jobs-people-name"><strong>{row.label}</strong><small>Last activity {ago(now-row.last)}</small></span>
     <span className="jobs-people-counts">{row.running>0&&<em data-group="running">{row.running} running</em>}{row.failed>0&&<em data-group="failed">{row.failed} failed</em>}<em data-group="completed">{row.completed} done</em></span>
    </button></li>)}</ul>
   </aside>
   <div className="jobs-monitor-main">
    <div className="jobs-toolbar">
     <div className="jobs-tabs" role="group" aria-label="Filter jobs">{JOB_TABS.map(([id,label])=><button key={id} type="button" aria-pressed={tab===id} onClick={()=>setTab(id)}>{label}<span>{counts[id]}</span></button>)}</div>
     <select className="jobs-filter" aria-label="Started by" value={person} onChange={event=>setPerson(event.target.value)}><option value="">Everyone</option>{people.map(row=><option key={row.key} value={row.key}>{row.label}</option>)}</select>
     {kinds.length>1&&<select className="jobs-filter" aria-label="Job type" value={kind} onChange={event=>setKind(event.target.value)}><option value="">All types</option>{kinds.map(value=><option key={value} value={value}>{kindLabel(value)}</option>)}</select>}
     <label className="jobs-search"><Search size={14} aria-hidden="true"/><input aria-label="Search jobs" placeholder="Search file, dataset or job ID" value={query} onChange={event=>setQuery(event.target.value)}/></label>
    </div>
    <p className="jobs-refresh small muted">Refreshes automatically every few seconds.{filtered&&<> · <button type="button" className="text-button" onClick={()=>{setPerson('');setKind('');setQuery('');}}>Clear filters</button></>}</p>
    <div className="jobs-table" role="region" aria-label="Job list" tabIndex={0}>
     <table>
      <thead><tr><th scope="col">Status</th><th scope="col">Job</th><th scope="col">Started by</th><th scope="col">Started</th><th scope="col">Duration</th><th scope="col">Progress</th><th scope="col"><span className="sr-only">Actions</span></th></tr></thead>
      <tbody>{visible.map(job=>{
       const group=jobGroup(job),progress=Math.min(100,Math.round(job.progress||0)),who=starter(job),name=docName(job)||job.document_id||job.id,dataset=datasetName(job);
       return <tr key={job.id} className="jobs-row" data-group={group}>
        <td data-label="Status">{group==='failed'?<button type="button" className="jobs-status attention-trigger" data-group={group} title="See what failed and how to fix it" onClick={()=>openAttention({jobId:job.id})}>{job.status} · details</button>:<span className="jobs-status" data-group={group}>{job.status}</span>}</td>
        <td data-label="Job" className="jobs-row-job"><span className="jobs-kind">{kindLabel(job.kind||job.type)}</span><strong title={name}>{name}</strong><small>{[dataset,job.stage,job.attempts>1?`attempt ${job.attempts}`:''].filter(Boolean).join(' · ')}</small>{job.error&&<p className="jobs-error" role="alert">{job.error}</p>}</td>
        <td data-label="Started by"><span className="jobs-person"><span className="jobs-avatar" data-self={who.self||undefined} aria-hidden="true">{initials(who.label)}</span><span>{who.label}</span></span></td>
        <td data-label="Started"><span title={formatDate(job.created_at)}>{ago(now-(job.created_at||now))}</span></td>
        <td data-label="Duration">{durationLabel(jobSeconds(job,now))}{group==='running'&&<small> so far</small>}</td>
        <td data-label="Progress"><div className="jobs-progress" aria-label={`Progress ${progress} percent`}><div className="progress"><span style={{width:`${progress}%`}}/></div><span>{progress}%</span></div></td>
        <td className="jobs-actions">
         {FAILED.includes(job.status)&&<ActionButton className="btn primary" disabled={busy} onClick={()=>onRetry(job)} label="Retry" action="retry" showLabel/>}
         {['pending','queued','running'].includes(job.status)&&<button className="btn danger" disabled={busy} onClick={()=>onCancel(job)}><Square size={13}/>Cancel</button>}
        </td>
       </tr>;})}
       {!visible.length&&<tr><td colSpan={7} className="jobs-none">No {tab==='all'?'':tab+' '}jobs match{filtered?' these filters':''} right now.</td></tr>}
      </tbody>
     </table>
    </div>
   </div>
  </div>
 </section>;
}
