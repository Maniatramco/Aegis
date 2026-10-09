"use client";
import {JobProgress} from './operation-progress';

type Entity=Record<string,any>;
const stageNames:Record<string,string>={prepare:'Preparing sources',generate:'Extracting fields',validate:'Validating result',ready:'Saving result'};

export function AgentJobProgress({job}:{job:Entity}) {
 const stages=Object.values(job.workflow?.stages||{}) as Entity[];
 const completed=stages.filter(stage=>stage.status==='completed').length;
 const percentage=stages.length?Math.round(completed/stages.length*100):null;
 const stopped=['failed','cancelled'].includes(job.status);
 const label=job.status==='completed'?'Extraction complete':stopped?'Extraction stopped':job.status==='queued'?'Queued':stageNames[job.workflow?.current]||'Processing';
 return <div className="agent-v2-progress">
  <details className="agent-v2-progress-details"><summary><span role="status">{label}{percentage!==null?` · ${percentage}%`:''}</span><span>View steps</span></summary><JobProgress job={job}/></details>
  {percentage!==null&&<div className="agent-v2-progress-track" role="progressbar" aria-label="Agent extraction progress" aria-valuemin={0} aria-valuemax={100} aria-valuenow={percentage} aria-valuetext={`${completed} of ${stages.length} stages completed`}><span style={{width:`${percentage}%`}}/></div>}
  {job.error&&<p role="alert" className="agent-v2-error">{job.error}</p>}
 </div>;
}

export function AgentResult({tool,onReview}:{tool:Entity;onReview:(id:string)=>void}) {
 const result=tool.result;
 if(!result)return null;
 return <div className="agent-v2-tool-result">
  {tool.status==='failed'&&<p>This tool stopped. Correct the file or service issue, then send a new request.</p>}
  {result.documents&&<details><summary>{result.documents.length} document references</summary><ul>{result.documents.map((document:Entity)=><li key={document.id}>{document.name}<code>{document.id}</code></li>)}</ul></details>}
  {tool.status==='completed'&&result.extraction_id&&<div className="agent-v2-result-actions"><details><summary>Extracted fields</summary><pre>{JSON.stringify(result.data,null,2)}</pre></details><button className="text-button" onClick={()=>onReview(result.extraction_id)}>Review result and evidence</button></div>}
 </div>;
}
