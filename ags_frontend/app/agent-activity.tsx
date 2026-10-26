"use client";
import {BrainCircuit,ClipboardList,CloudUpload,Database,FileScan,Layers,ListOrdered,PenLine,Save,Search,ShieldCheck,type LucideIcon} from 'lucide-react';
import type {CSSProperties} from 'react';
import {AgentLogo} from './agent-logo';
import './agent-activity.css';

type Entity=Record<string,any>;
export type AgentTask='think'|'search'|'rank'|'write'|'check'|'upload'|'index'|'publish'|'extract'|'reextract'|'onboard'|'save';
const TASKS:Record<AgentTask,{icon:LucideIcon;label:string}>={
 think:{icon:BrainCircuit,label:'Understanding the request'},
 search:{icon:Search,label:'Searching knowledge'},
 rank:{icon:ListOrdered,label:'Reranking evidence'},
 write:{icon:PenLine,label:'Writing the answer'},
 check:{icon:ShieldCheck,label:'Checking citations'},
 upload:{icon:CloudUpload,label:'Uploading documents'},
 index:{icon:Layers,label:'Indexing documents'},
 publish:{icon:Layers,label:'Publishing knowledge'},
 extract:{icon:ClipboardList,label:'Extracting fields'},
 reextract:{icon:FileScan,label:'Re-extracting fields'},
 onboard:{icon:Database,label:'Setting up the dataset'},
 save:{icon:Save,label:'Saving'},
};

/** Maps a live progress step label from the server to the task the agent is doing. */
export function taskForStep(label=''):AgentTask{
 if(/re-?extract/i.test(label))return 'reextract';
 if(/onboard/i.test(label))return 'onboard';
 if(/rerank/i.test(label))return 'rank';
 if(/validat|citation|recheck/i.test(label))return 'check';
 if(/search|retriev|querying|evidence/i.test(label))return 'search';
 if(/extract|fields/i.test(label))return 'extract';
 if(/upload/i.test(label))return 'upload';
 if(/index/i.test(label))return 'index';
 if(/publish/i.test(label))return 'publish';
 if(/saving/i.test(label))return 'save';
 if(/answer|generat|respon|writing/i.test(label))return 'write';
 return 'think';
}

/** What a plan is doing right now, or null when nothing is running. */
export function planActivity(plan:Entity,workflow?:{status?:string;steps?:Entity[]}):AgentTask|null{
 const call=(plan.calls||[]).find((c:Entity)=>['running','waiting'].includes(c.status));
 if(call){
  if(call.publication_pending)return 'publish';
  if(call.tool==='upload')return (call.jobs||[]).some((job:Entity)=>job.status==='processing'||job.status==='running')?'index':'upload';
  return call.tool==='reextract'?'reextract':'extract';
 }
 const running=[...(workflow?.steps||[])].reverse().find(step=>step.status==='running');
 if(running)return taskForStep(running.label);
 if(plan.chat?.status==='streaming')return 'write';
 if(workflow?.status==='running')return 'think';
 return null;
}

/** A glowing capsule while the agent works: a gradient ring spins around the Aegis shield, sparks orbit it,
 the current step shimmers, and dots carry the work to the step's icon. Compact keeps just the ringed shield and icon. */
export function AgentActivity({task,size=24,compact=false}:{task:AgentTask;size?:number;compact?:boolean}){
 const {icon:Icon,label}=TASKS[task];
 const orb=<span className="aa-orb" aria-hidden="true"><span className="aa-glow"/><span className="aa-ring"/><span className="aa-spark"/><span className="aa-spark aa-spark-alt"/><AgentLogo size={compact?size:Math.min(size,22)}/></span>;
 if(compact)return <span className="agent-activity agent-activity-compact" data-task={task} role="img" aria-label={`Aegis Agent · ${label}`} title={label} style={{'--aa-size':`${size}px`} as CSSProperties}>{orb}<span className="aa-task" aria-hidden="true"><Icon size={9}/></span></span>;
 return <span className="agent-activity agent-activity-capsule" data-task={task} role="img" aria-label={`Aegis Agent · ${label}`} title={label}>
  {orb}
  <span className="aa-text" aria-hidden="true"><span className="aa-name">Aegis Agent</span><span className="aa-label">{label}</span></span>
  <span className="aa-flow agent-activity-track" aria-hidden="true"><i/><i/><i/><i/><i/></span>
  <span className="aa-task" aria-hidden="true"><Icon size={14}/></span>
 </span>;
}

/** Static logo when idle, animated activity while the agent works. */
export function AgentPresence({task,size=24}:{task:AgentTask|null;size?:number}){
 return task?<AgentActivity task={task} size={size}/>:<AgentLogo size={size}/>;
}
