"use client";
import {WorkflowStepper} from './workflow-stepper';
type Receipt={name:string;version:number};
export type PromptProgress={name:string;phase:string;receipt?:Receipt;error?:string};
export function AgentPromptProgress({progress}:{progress:PromptProgress}){
 const {phase,receipt}=progress;
 const failed=['failed','aborted','save_failed','prepare_failed'].includes(phase);
 const steps=[
  {label:'Validate prompt',status:phase==='validating'?'running':'completed',detail:''},
  {label:'Save prompt',status:receipt?'completed':phase==='saving'?'running':failed?'failed':'pending',detail:receipt?`${receipt.name} · Version ${receipt.version}`:''},
  ...(phase==='saved'||['validating','confirmed','saving'].includes(phase)?[]:[
   {label:'Prepare request',status:phase==='prepare_failed'?'failed':phase==='preparing'?'running':receipt?'completed':'pending',detail:''},
   {label:'Respond',status:phase==='completed'?'completed':['failed','aborted'].includes(phase)?'failed':phase==='responding'?'running':'pending',detail:failed&&receipt?'Prompt is saved. Retry only the request; no new prompt version is needed.':''}
  ])
 ];
 const labels:Record<string,string>={completed:'Completed',running:'In progress',pending:'Pending',failed:phase==='aborted'?'Stopped':'Needs attention'};
 return <section className="agent-v2-prompt-progress" aria-label={`Prompt workflow: ${progress.name}`}>
  <strong>Prompt workflow</strong><WorkflowStepper label="Prompt workflow steps" steps={steps.map(step=>({id:step.label,label:step.label,status:step.status,statusLabel:labels[step.status]}))}/>
  {receipt&&<p className="agent-v2-prompt-receipt">{receipt.name} · Version {receipt.version}</p>}
  {failed&&receipt&&<p>Prompt is saved. Retry only the request; no new prompt version is needed.</p>}
  {phase==='confirmed'&&<p>Review confirmed. Send to save the prompt.</p>}
  {progress.error&&<p role="alert">{progress.error}</p>}
 </section>;
}
