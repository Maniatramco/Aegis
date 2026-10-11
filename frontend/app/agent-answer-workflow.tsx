"use client";
import {useEffect,useState} from 'react';
import {AgentLogo} from './agent-logo';
import {WorkflowStepper} from './workflow-stepper';
import './agent-answer-workflow.css';

export type AnswerWorkflow={status:string;started_at:number;steps:{id:string;label:string;status:string;started_at:number;duration_ms?:number}[]};
export const stepElapsed=(step:AnswerWorkflow['steps'][number],now:number)=>Math.max(0,step.duration_ms??now-step.started_at);
export const elapsedLabel=(ms:number)=>ms<1000?`${(ms/1000).toFixed(1)}s`:ms<60000?`${Math.floor(ms/1000)}s`:`${Math.floor(ms/60000)}m ${Math.floor(ms/1000)%60}s`;
export function AgentAnswerWorkflow({workflow}:{workflow:AnswerWorkflow}){
 const [now,setNow]=useState(Date.now());
 useEffect(()=>{if(workflow.status!=='running')return;setNow(Date.now());const timer=setInterval(()=>setNow(Date.now()),1000);return()=>clearInterval(timer);},[workflow.status]);
 const current=workflow.steps.find(s=>s.status==='running');
 const active=workflow.status==='running';
 const total=workflow.steps.reduce((sum,s)=>sum+stepElapsed(s,now),0);
 const label=current?.label||(active?'Waiting for agent':workflow.status==='completed'?'Response ready':workflow.status==='aborted'?'Response stopped':'Response needs attention');
 return <details className="agent-answer-workflow" data-status={workflow.status}>
  <summary aria-label="Answer workflow details"><AgentLogo size={20}/><span className="answer-workflow-label" role="status">{label}</span><time>{elapsedLabel(current?stepElapsed(current,now):total)}</time><span className="answer-workflow-toggle">Details</span></summary>
  <div className="answer-workflow-expanded"><WorkflowStepper label="Answer workflow steps" steps={workflow.steps.map(s=>({id:s.id,label:s.label,status:s.status,detail:elapsedLabel(stepElapsed(s,now))}))}/><p>Time spent in each reported step · total {elapsedLabel(total)}</p></div>
 </details>;
}
