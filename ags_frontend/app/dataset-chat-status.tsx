"use client";
import {CheckCircle2,ChevronDown,CircleAlert,Loader2,Search} from 'lucide-react';
import {WorkflowStepper} from './workflow-stepper';
import './dataset-chat-status.css';

type Entity=Record<string,any>;
export function DatasetChatStatus({message}:{message:Entity}){
 const state=message.status==='streaming'?'running':message.status||message.answer_workflow?.status||'completed';
 const active=state==='running',completed=state==='completed';
 const running=message.answer_workflow?.steps?.find((step:Entity)=>step.status==='running')?.label||'';
 const phase=/Answering or routing/.test(running)?'Understanding question':/Generating|Repairing/.test(running)?'Preparing answer':/Validating|Saving/.test(running)?'Validating answer':/Resolving|Checking accessible/.test(running)?'Checking dataset access':'Searching Unified Knowledge';
 const stats=message.source_summary,known=Number.isInteger(stats?.checked_count)&&stats.checked_count>=0;
 const general=stats?.knowledge_used===false||message.request_route?.routing_mode==='dataset_general_chat';
 const label=active?phase:completed?general?'General answer':'Answer ready':state==='aborted'?'Stopped':'Needs attention';
 const Icon=active?Loader2:completed?CheckCircle2:CircleAlert;
 const steps=(message.answer_workflow?.steps||[]).map((step:Entity)=>({id:step.id,label:step.label,status:step.status,detail:step.duration_ms===undefined?undefined:`${(step.duration_ms/1000).toFixed(1)}s`}));
 const breakdown=known?[['documents','document'],['saved_results','saved result'],['dataset_descriptions','dataset description'],['guidance','guidance source']].filter(([key])=>stats[key]>0).map(([key,name])=>`${stats[key]} ${name}${stats[key]===1?'':'s'}`).join(' · '):'';
 return <details className="dataset-chat-status" data-status={state}>
  <summary aria-label="Knowledge search status and sources"><Icon size={12} className={active?'dataset-chat-status-spin':undefined}/><span>{label}</span>{general?<span className="dataset-chat-source-count">No knowledge lookup</span>:known&&<span className="dataset-chat-source-count">{stats.checked_count} source{stats.checked_count===1?'':'s'} checked{completed&&Number.isInteger(stats.cited_count)?` · ${stats.cited_count} cited`:''}</span>}<ChevronDown size={12}/></summary>
  <div className="dataset-chat-status-details">{general?<p>Answered directly by your selected chat model. Unified Knowledge was not searched; no sources were retrieved or cited.</p>:<><p><Search size={13}/>Unified Knowledge · {known&&Number.isInteger(stats.dataset_count)?`${stats.dataset_count} dataset${stats.dataset_count===1?'':'s'} searched`:'selected datasets'} · selected files and your access permissions</p>{known?<><strong>{breakdown}</strong><p>Counts cover distinct sources retrieved and inspected for this answer. Multiple passages from one document count once. This does not mean every file in the datasets was reviewed.</p></>:<p>{active?'The source count appears after retrieval.':'Source counts were not recorded for this earlier answer.'}</p>}</>}{steps.length>0&&<WorkflowStepper compact label="Knowledge search details" steps={steps}/>}</div>
 </details>;
}
