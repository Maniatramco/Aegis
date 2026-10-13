"use client";
import {useEffect,useId,useLayoutEffect,useRef,useState} from 'react';
import {CheckCircle2,Loader2,CircleAlert,CircleStop,X} from 'lucide-react';
import {WorkflowStepper} from './workflow-stepper';
import './agent-answer-workflow.css';

export type AnswerWorkflow={status:string;started_at:number;steps:{id:string;label:string;status:string;started_at:number;duration_ms?:number}[]};
export const stepElapsed=(step:AnswerWorkflow['steps'][number],now:number)=>Math.max(0,step.duration_ms??now-step.started_at);
export const elapsedLabel=(ms:number)=>ms<1000?`${(ms/1000).toFixed(1)}s`:ms<60000?`${Math.floor(ms/1000)}s`:`${Math.floor(ms/60000)}m ${Math.floor(ms/1000)%60}s`;
const stageStatus=(status:string)=>({completed:'Completed',running:'In progress',failed:'Needs attention',aborted:'Stopped',cancelled:'Stopped'}[status]||'Pending');
export function AgentAnswerWorkflow({workflow,status='completed'}:{workflow?:AnswerWorkflow;status?:string}){
 const [now,setNow]=useState(Date.now());
 const state=workflow?.status||(status==='streaming'?'running':status);
 const active=state==='running';
 const [expanded,setExpanded]=useState(active);
 const [preview,setPreview]=useState(false);
 const [position,setPosition]=useState({left:12,top:12});
 const anchor=useRef<HTMLDivElement>(null),detailPanel=useRef<HTMLDivElement>(null);
 const closeTimer=useRef<ReturnType<typeof setTimeout>|null>(null),suppressHover=useRef(false);
 const panelId=useId(),detailId=useId();
 const cancelClose=()=>{if(closeTimer.current!==null){clearTimeout(closeTimer.current);closeTimer.current=null;}};
 const inspect=()=>{cancelClose();if(!suppressHover.current)setPreview(true);};
 const leave=()=>{cancelClose();closeTimer.current=setTimeout(()=>{setPreview(false);suppressHover.current=false;},160);};
 const close=()=>{cancelClose();setExpanded(false);setPreview(false);suppressHover.current=true;};
 useEffect(()=>{setExpanded(active);setPreview(false);suppressHover.current=false;},[active]);
 useEffect(()=>()=>cancelClose(),[]);
 useEffect(()=>{if(!active)return;setNow(Date.now());const timer=setInterval(()=>setNow(Date.now()),1000);return()=>clearInterval(timer);},[active]);
 useLayoutEffect(()=>{
  if(!preview)return;
  const place=()=>{
   const rect=anchor.current?.getBoundingClientRect(),panel=detailPanel.current;
   if(!rect||!panel)return;
   const width=panel.offsetWidth,height=panel.offsetHeight;
   const left=Math.max(12,Math.min(rect.left,window.innerWidth-width-12));
   const below=rect.bottom+8,above=rect.top-height-8;
   const top=Math.max(12,Math.min(below+height<=window.innerHeight-12?below:above>=12?above:below,window.innerHeight-height-12));
   setPosition({left,top});
  };
  place();window.addEventListener('resize',place);window.addEventListener('scroll',place,true);
  const observer=typeof ResizeObserver==='undefined'?null:new ResizeObserver(place);
  if(detailPanel.current)observer?.observe(detailPanel.current);
  return()=>{window.removeEventListener('resize',place);window.removeEventListener('scroll',place,true);observer?.disconnect();};
 },[preview,workflow?.steps.length]);
 const current=workflow?.steps.find(s=>s.status==='running');
 const total=workflow?.steps.reduce((sum,s)=>sum+stepElapsed(s,now),0)??0;
 const label=current?.label||(active?'Waiting for agent':state==='completed'?'Response ready':state==='aborted'?'Response stopped':'Needs attention');
 const StatusIcon=active?Loader2:state==='completed'?CheckCircle2:state==='aborted'?CircleStop:CircleAlert;
 const steps=workflow?.steps.map(s=>({id:s.id,label:s.label,status:s.status,detail:elapsedLabel(stepElapsed(s,now))}))||[];
 return <div ref={anchor} className="agent-answer-workflow" data-status={state} data-expanded={expanded||preview} onMouseEnter={inspect} onMouseLeave={leave} onFocusCapture={inspect} onBlurCapture={event=>{if(!event.currentTarget.contains(event.relatedTarget))leave();}} onKeyDown={event=>{if(event.key==='Escape'){event.stopPropagation();close();}}}>
  <button type="button" className="answer-workflow-summary" aria-label="Answer workflow details" aria-expanded={expanded||preview} aria-controls={preview?detailId:panelId} onClick={()=>{if(expanded)close();else{setExpanded(true);suppressHover.current=false;setPreview(true);}}}><StatusIcon size={10} className="answer-workflow-state" aria-hidden="true"/><span className="answer-workflow-label" role="status">{label}</span>{workflow&&<time>{elapsedLabel(current?stepElapsed(current,now):total)}</time>}<span className="answer-workflow-toggle" aria-hidden="true"/></button>
  <div id={panelId} className="answer-workflow-expanded" hidden={!expanded}>
   <button type="button" className="answer-workflow-close" aria-label="Close answer workflow" onClick={close}><X size={13}/></button>
   {steps.length?<WorkflowStepper compact scrollCompact label="Answer workflow steps" steps={steps}/>:<p>{active?'Waiting for workflow updates.':'Step details were not saved with this earlier answer.'}</p>}
  </div>
  {preview&&<div ref={detailPanel} id={detailId} className="answer-workflow-preview" role="region" aria-label="Expanded answer workflow" style={position}>
   <div className="answer-workflow-preview-heading"><strong>Answer workflow</strong><span>{label}</span><button type="button" className="answer-workflow-close" aria-label="Close workflow details" onClick={()=>{setPreview(false);suppressHover.current=true;}}><X size={14}/></button></div>
   {steps.length?<><WorkflowStepper compact scrollCompact label="Expanded workflow stages" steps={steps}/><div className="answer-workflow-detail-scroll"><table className="answer-workflow-detail-table"><thead><tr><th>Stage</th><th>Status</th><th>Time</th></tr></thead><tbody>{workflow!.steps.map(step=><tr key={step.id} data-status={step.status}><td>{step.label}</td><td>{stageStatus(step.status)}</td><td><time>{elapsedLabel(stepElapsed(step,now))}</time></td></tr>)}</tbody></table></div></>:<p>{active?'Waiting for workflow updates.':'Step details were not saved with this earlier answer.'}</p>}
  </div>}
 </div>;
}
