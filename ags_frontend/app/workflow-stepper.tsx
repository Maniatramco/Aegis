"use client";
import {useEffect,useRef,useState,type CSSProperties} from 'react';
import {Check,Circle,AlertCircle,CircleStop,Minus,Bot,FileText,List,MessageCircle} from 'lucide-react';
import './horizontal-workflow-stepper.css';

export type WorkflowStep={id:string;label:string;status:string;detail?:string;statusLabel?:string;icon?:'document'|'knowledge'|'chat'};
type StageState='completed'|'running'|'failed'|'cancelled'|'skipped'|'unknown'|'pending';
export const workflowStepState=(status:string):StageState=>status==='completed'?'completed':status==='running'?'running':status==='failed'?'failed':['cancelled','aborted','stopped'].includes(status)?'cancelled':['skipped','not_required'].includes(status)?'skipped':status==='unknown'?'unknown':'pending';
const state=workflowStepState;
export function WorkflowStepper({steps,label='Workflow steps',compact=false,scrollCompact=false}:{steps:WorkflowStep[];label?:string;compact?:boolean;scrollCompact?:boolean}){
 const frame=useRef<HTMLDivElement>(null);
 const track=useRef<HTMLDivElement>(null);
 const [density,setDensity]=useState('auto');
 const [inspected,setInspected]=useState<string|null>(null);
 const active=steps.filter(step=>state(step.status)==='running').map(step=>step.id).join(',');
 useEffect(()=>{
  const container=frame.current;
  if(!container)return;
  const fit=()=>{
   if(!container.clientWidth)return;
   const track=container.clientWidth/Math.max(1,steps.length);
   setDensity(track<58?'mini':track<90?'compact':'spacious');
  };
  fit();
  if(typeof ResizeObserver==='undefined')return;
  const resize=new ResizeObserver(fit);resize.observe(container);
  return ()=>resize.disconnect();
 },[steps.length]);
 useEffect(()=>setInspected(null),[active]);
 useEffect(()=>{
  const viewport=track.current;if(!viewport)return;
  const index=steps.findIndex(step=>state(step.status)==='running');
  const marker=viewport.querySelectorAll<HTMLElement>('li')[index<0?steps.length-1:index];
  if(marker)viewport.scrollLeft=Math.max(0,marker.offsetLeft-(viewport.clientWidth-marker.offsetWidth)/2);
 },[active,steps.length,scrollCompact]);
 if(!steps.length)return null;
 const caption=steps.find(step=>step.id===inspected)||steps.find(step=>state(step.status)==='running')||steps.find(step=>['failed','cancelled','unknown'].includes(state(step.status)))||steps.find(step=>state(step.status)==='pending')||steps[steps.length-1];
 const statusLabel=(step:WorkflowStep)=>step.statusLabel||(['blocked','waiting','queued'].includes(step.status)?'Waiting':{completed:'Completed',running:'In progress',failed:'Needs attention',cancelled:'Stopped',skipped:'Not used',unknown:'Status unavailable',pending:'Pending'}[state(step.status)]);
 const completed=steps.filter(step=>state(step.status)==='completed').length;
 const rail=<ol className="workflow-stages batch-stages horizontal-workflow-stepper" aria-label={label}>{steps.map((step,index)=>{
  const status=state(step.status);
  const next=steps[index+1];
  const connector=status==='completed'&&next?(state(next.status)==='running'?'flowing':state(next.status)==='completed'?'complete':'pending'):'pending';
  const Icon=step.icon==='document'?FileText:step.icon==='knowledge'?List:step.icon==='chat'?MessageCircle:Bot;
  return <li key={step.id} className={`stage-${status}`} data-status={status} aria-current={status==='running'?'step':undefined}>
   {next&&<span className={`workflow-connector connector-${connector}`} data-connection={connector} aria-hidden="true"><i/><i/><i/></span>}
   <button type="button" className="workflow-step-inspect" aria-label={`${step.label} · ${statusLabel(step)}${step.detail?` · ${step.detail}`:''}`} title={`${step.label} · ${statusLabel(step)}`} onFocus={()=>setInspected(step.id)} onBlur={()=>setInspected(null)} onClick={()=>setInspected(step.id)}><span className="stage-symbol" aria-hidden="true">{status==='completed'?<Check size={21} strokeWidth={3}/>:status==='failed'?<AlertCircle size={21}/>:status==='cancelled'?<CircleStop size={21}/>:status==='skipped'?<Minus size={18}/>:step.icon||status==='running'?<Icon size={21}/>:<Circle size={10} fill="currentColor" strokeWidth={0}/>}</span></button>
   <strong className="workflow-step-label">{step.label}</strong><small className="workflow-step-status">{statusLabel(step)}</small>
   {step.detail&&<small className="workflow-step-detail">{step.detail}</small>}
  </li>;
 })}</ol>;
 return <div ref={frame} className="workflow-frame" data-active={Boolean(active)||undefined} data-density={compact?'mini':density} data-compact={compact||undefined} style={{'--workflow-count':steps.length} as CSSProperties}>
 {compact&&scrollCompact?<div ref={track} className="workflow-track-viewport">{rail}</div>:rail}
 {(compact||density==='mini')&&<div className="workflow-stage-caption" data-status={state(caption.status)} role="status" aria-live="polite" aria-atomic="true"><strong title={caption.label}>{caption.label}</strong><span>{statusLabel(caption)}{caption.detail?` · ${caption.detail}`:''}</span><small>{completed} of {steps.length} completed{steps.some(step=>state(step.status)==='skipped')?` · ${steps.filter(step=>state(step.status)==='skipped').length} not used`:''}</small></div>}
 </div>;
}
