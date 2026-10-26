"use client";
import {useEffect,useId,useRef,useState,type CSSProperties} from 'react';
import {AgentLogo} from './agent-logo';
import {BrainCircuit,Check,CheckCircle2,Loader2,CircleAlert,CircleStop,Layers,PenLine,Search,ShieldCheck,X,type LucideIcon} from 'lucide-react';
import './agent-answer-workflow.css';

export type AnswerWorkflow={status:string;started_at:number;steps:{id:string;label:string;status:string;started_at:number;duration_ms?:number}[]};
export const stepElapsed=(step:AnswerWorkflow['steps'][number],now:number)=>Math.max(0,step.duration_ms??now-step.started_at);
export const elapsedLabel=(ms:number)=>ms<1000?`${(ms/1000).toFixed(1)}s`:ms<60000?`${Math.floor(ms/1000)}s`:`${Math.floor(ms/60000)}m ${Math.floor(ms/1000)%60}s`;
type Step=AnswerWorkflow['steps'][number];
/** The few phases people follow; every real step still appears in the detail table. */
export const PHASES=[['understand','Understand request'],['evidence','Find evidence'],['workflow','Run workflow'],['answer','Write answer'],['check','Check & save']] as const;
export type Phase=typeof PHASES[number][0];
export function phaseFor(label=''):Phase{
 if(/validat|citation|saving/i.test(label))return 'check';
 if(/answer|generat|writing/i.test(label))return 'answer';
 if(/search|retriev|querying|rerank|evidence|catalog|saved|results|fields|knowledge/i.test(label))return 'evidence';
 if(/extract agent|onboard|upload/i.test(label))return 'workflow';
 return 'understand';
}
/** Collapse server steps into phases: failed wins, then running, then done; time is the sum of its steps. */
export function groupWorkflowSteps(steps:Step[],now:number){
 return PHASES.map(([id,label])=>{
  const members=steps.filter(step=>phaseFor(step.label)===id);
  if(!members.length)return null;
  const statuses=members.map(step=>step.status);
  const status=statuses.includes('failed')?'failed':statuses.some(s=>s==='aborted'||s==='cancelled')?'aborted':statuses.includes('running')?'running':statuses.every(s=>s==='completed')?'completed':'pending';
  const running=members.find(step=>step.status==='running');
  const ms=members.reduce((sum,step)=>sum+stepElapsed(step,now),0);
  return {id,label,status,detail:running?`${running.label} · ${elapsedLabel(stepElapsed(running,now))}`:status==='pending'?`${members.length} step${members.length===1?'':'s'}`:`${members.length} step${members.length===1?'':'s'} · ${elapsedLabel(ms)}`};
 }).filter(Boolean) as {id:string;label:string;status:string;detail:string}[];
}
const stageStatus=(status:string)=>({completed:'Completed',running:'In progress',failed:'Needs attention',aborted:'Stopped',cancelled:'Stopped'}[status]||'Pending');
/** Answer progress as a chip that opens an inline panel under the agent header: four phases, with every actual step one click away. Nothing floats over the answer. */
const PHASE_ICONS:Record<string,LucideIcon>={understand:BrainCircuit,evidence:Search,workflow:Layers,answer:PenLine,check:ShieldCheck};
const phaseStatus=(status:string)=>({completed:'Done',running:'In progress',failed:'Needs attention',aborted:'Stopped'}[status]||'Waiting');
/** The answer's phases as a track: each phase keeps its icon, name and status visible; the line fills as phases finish and flows into the live one. */
export function PhaseTrack({phases}:{phases:{id:string;label:string;status:string;detail:string}[]}){
 return <ol className="phase-track" aria-label="Answer workflow phases" style={{'--phase-count':phases.length} as CSSProperties}>{phases.map(phase=>{const Icon=phase.status==='completed'?Check:phase.status==='failed'?CircleAlert:PHASE_ICONS[phase.id]||BrainCircuit;
  return <li key={phase.id} className="phase-step" data-phase={phase.id} data-status={phase.status} aria-current={phase.status==='running'?'step':undefined}>
   <span className="phase-node" aria-hidden="true">{phase.status==='running'?<><span className="phase-ring"/><AgentLogo size={20}/><span className="phase-badge"><Icon size={9}/></span></>:<Icon size={15}/>}</span>
   <span className="phase-text"><strong>{phase.label}</strong><small><span className="phase-state">{phaseStatus(phase.status)}</span> · {phase.detail}</small></span>
  </li>;})}</ol>;
}
export function AgentAnswerWorkflow({workflow,status='completed'}:{workflow?:AnswerWorkflow;status?:string}){
 const [now,setNow]=useState(Date.now());
 const state=workflow?.status||(status==='streaming'?'running':status);
 const active=state==='running';
 const [expanded,setExpanded]=useState(active);
 const [showSteps,setShowSteps]=useState(false);
 const dismissed=useRef(false);
 const panelId=useId(),stepsId=useId();
 const close=()=>{dismissed.current=true;setExpanded(false);setShowSteps(false);};
 useEffect(()=>{if(!active){setExpanded(false);setShowSteps(false);dismissed.current=false;}else if(!dismissed.current)setExpanded(true);},[active]);
 useEffect(()=>{if(!active)return;setNow(Date.now());const timer=setInterval(()=>setNow(Date.now()),1000);return()=>clearInterval(timer);},[active]);
 const current=workflow?.steps.find(s=>s.status==='running');
 const total=workflow?.steps.reduce((sum,s)=>sum+stepElapsed(s,now),0)??0;
 const currentPhase=current&&PHASES.find(([id])=>id===phaseFor(current.label))?.[1];
 const label=currentPhase||(active?'Waiting for agent':state==='completed'?'Response ready':state==='aborted'?'Response stopped':'Needs attention');
 const StatusIcon=active?Loader2:state==='completed'?CheckCircle2:state==='aborted'?CircleStop:CircleAlert;
 const phases=groupWorkflowSteps(workflow?.steps||[],now);
 const done=phases.filter(p=>p.status==='completed').length;
 const count=workflow?.steps.length||0;
 return <div className="agent-answer-workflow" data-status={state} data-expanded={expanded} onKeyDown={event=>{if(event.key==='Escape'&&expanded){event.stopPropagation();close();}}}>
  <button title="Answer workflow details" type="button" className="answer-workflow-summary" aria-label="Answer workflow details" aria-expanded={expanded} aria-controls={panelId} onClick={()=>{if(expanded)close();else{dismissed.current=false;setExpanded(true);}}}><StatusIcon size={10} className="answer-workflow-state" aria-hidden="true"/><span className="answer-workflow-label" role="status">{label}</span>{workflow&&<time>{elapsedLabel(current?stepElapsed(current,now):total)}</time>}<span className="answer-workflow-toggle" aria-hidden="true"/></button>
  <div id={panelId} className="answer-workflow-expanded" role="region" aria-label="Expanded answer workflow" hidden={!expanded}>
   <button title="Close answer workflow" type="button" className="answer-workflow-close" aria-label="Close answer workflow" onClick={close}><X size={13}/></button>
   {phases.length?<><div className="phase-track-head"><strong>Answer workflow</strong><span>{done} of {phases.length} phases done · {elapsedLabel(total)}</span></div><PhaseTrack phases={phases}/></>:<p>{active?'Waiting for workflow updates.':'Step details were not saved with this earlier answer.'}</p>}
   {count>0&&<button type="button" className="answer-workflow-steps-toggle" aria-expanded={showSteps} aria-controls={stepsId} onClick={()=>setShowSteps(!showSteps)}>{showSteps?'Hide steps':`Show all ${count} steps`}</button>}
   {showSteps&&<div id={stepsId} className="answer-workflow-detail-scroll"><table className="answer-workflow-detail-table"><thead><tr><th>Step</th><th>Phase</th><th>Status</th><th>Time</th></tr></thead><tbody>{workflow!.steps.map(step=><tr key={step.id} data-status={step.status}><td>{step.label}</td><td>{PHASES.find(([id])=>id===phaseFor(step.label))?.[1]}</td><td>{stageStatus(step.status)}</td><td><time>{elapsedLabel(stepElapsed(step,now))}</time></td></tr>)}</tbody></table></div>}
  </div>
 </div>;
}
