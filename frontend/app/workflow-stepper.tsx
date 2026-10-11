"use client";
import {useEffect,useRef} from 'react';
import {Check,Circle,AlertCircle,Bot,FileText,List,MessageCircle} from 'lucide-react';
import './horizontal-workflow-stepper.css';

export type WorkflowStep={id:string;label:string;status:string;detail?:string;statusLabel?:string;icon?:'document'|'knowledge'|'chat'};
const state=(status:string)=>status==='completed'?'completed':status==='running'?'running':['failed','cancelled'].includes(status)?'failed':'pending';
export function WorkflowStepper({steps,label='Workflow steps'}:{steps:WorkflowStep[];label?:string}){
 const list=useRef<HTMLOListElement>(null);
 const active=steps.filter(step=>state(step.status)==='running').map(step=>step.id).join(',');
 useEffect(()=>{
  const container=list.current;
  if(!container)return;
  const showActive=()=>{
   const current=container.querySelector<HTMLElement>('[aria-current="step"]');
   if(current&&container.scrollWidth>container.clientWidth)container.scrollLeft=Math.max(0,current.offsetLeft-(container.clientWidth-current.offsetWidth)/2);
  };
  showActive();
  if(typeof ResizeObserver==='undefined')return;
  const resize=new ResizeObserver(showActive);resize.observe(container);
  return ()=>resize.disconnect();
 },[active]);
 if(!steps.length)return null;
 return <ol ref={list} className="workflow-stages batch-stages horizontal-workflow-stepper" aria-label={label} tabIndex={0}>{steps.map((step,index)=>{
  const status=state(step.status);
  const next=steps[index+1];
  const connector=status==='completed'&&next?(state(next.status)==='running'?'flowing':state(next.status)==='completed'?'complete':'pending'):'pending';
  const Icon=step.icon==='document'?FileText:step.icon==='knowledge'?List:step.icon==='chat'?MessageCircle:Bot;
  return <li key={step.id} className={`stage-${status}`} data-status={status} aria-current={status==='running'?'step':undefined}>
   {next&&<span className={`workflow-connector connector-${connector}`} data-connection={connector} aria-hidden="true"><i/><i/><i/></span>}
   <span className="stage-symbol" aria-hidden="true">{status==='completed'?<Check size={21} strokeWidth={3}/>:status==='failed'?<AlertCircle size={21}/>:step.icon||status==='running'?<Icon size={21}/>:<Circle size={10} fill="currentColor" strokeWidth={0}/>}</span>
   <strong>{step.label}</strong><small>{step.statusLabel||({completed:'Completed',running:'In progress',failed:'Needs attention',pending:'Pending'}[status])}</small>
   {step.detail&&<small className="workflow-step-detail">{step.detail}</small>}
  </li>;
 })}</ol>;
}
