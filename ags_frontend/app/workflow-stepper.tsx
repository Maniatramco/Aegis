"use client";
import type {CSSProperties} from 'react';
import {Check,Circle,AlertCircle,Bot,FileText,List,MessageCircle} from 'lucide-react';
import {AgentLogo} from './agent-logo';
import './horizontal-workflow-stepper.css';

export type WorkflowStep={id:string;label:string;status:string;detail?:string;statusLabel?:string;icon?:'document'|'knowledge'|'chat'};
const state=(status:string)=>status==='completed'?'completed':status==='running'?'running':['failed','cancelled'].includes(status)?'failed':'pending';
/** Every workflow in Aegis uses the same navy track: each step keeps its name and status visible, finished steps fill the line,
 dots flow into the running step, and the running step carries the Aegis shield. compact/scrollCompact are kept for callers; the track always fits. */
export function WorkflowStepper({steps,label='Workflow steps'}:{steps:WorkflowStep[];label?:string;compact?:boolean;scrollCompact?:boolean}){
 if(!steps.length)return null;
 const statusLabel=(step:WorkflowStep)=>step.statusLabel||({completed:'Done',running:'In progress',failed:'Needs attention',pending:'Waiting'}[state(step.status)]);
 const completed=steps.filter(step=>state(step.status)==='completed').length;
 const live=steps.find(step=>state(step.status)==='running')||steps.find(step=>state(step.status)==='failed');
 return <div className="workflow-frame brand-track" style={{'--phase-count':steps.length} as CSSProperties}>
  <div className="brand-track-head"><span>{completed} of {steps.length} completed</span></div>
  <ol className="brand-track-steps" aria-label={label}>{steps.map((step,index)=>{
   const status=state(step.status),next=steps[index+1];
   const connector=status==='completed'&&next?(state(next.status)==='running'?'flowing':state(next.status)==='completed'?'complete':'pending'):'pending';
   const Icon=step.icon==='document'?FileText:step.icon==='knowledge'?List:step.icon==='chat'?MessageCircle:Bot;
   return <li key={step.id} className={`brand-step stage-${status}`} data-status={status} aria-current={status==='running'?'step':undefined}>
    {next&&<span className={`workflow-connector connector-${connector}`} data-connection={connector} aria-hidden="true"/>}
    <span className="brand-node" aria-hidden="true">{status==='running'?<><span className="brand-ring"/><AgentLogo size={20}/><span className="brand-badge"><Icon size={9}/></span></>:status==='completed'?<Check size={15} strokeWidth={3}/>:status==='failed'?<AlertCircle size={15}/>:step.icon?<Icon size={14}/>:<Circle size={8} fill="currentColor" strokeWidth={0}/>}</span>
    <span className="brand-text"><strong className="workflow-step-label">{step.label}</strong><small><span className="brand-state">{statusLabel(step)}</span>{step.detail?` · ${step.detail}`:''}</small></span>
   </li>;
  })}</ol>
  {live&&<p className="brand-track-live" role="status">{live.label} · {statusLabel(live)}</p>}
 </div>;
}
