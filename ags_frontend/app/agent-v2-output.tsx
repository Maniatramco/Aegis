"use client";
import {ActionButton} from "./action-button";
import {JobProgress} from './operation-progress';
import {MergedDetails} from './merged-details';

type Entity=Record<string,any>;
const stageNames:Record<string,string>={extract:'Reading document / OCR',index:'Building index',prepare:'Preparing sources',generate:'Extracting fields',retrieving:'Retrieving evidence',reranking:'Reranking evidence',validate:'Validating result',writing_output:'Writing Parquet',ready:'Ready'};

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
  {result.extraction_ids?.length>0&&<p role="status">Extraction accepted: {result.extraction_ids.map((id:string)=><code key={id}>{id} </code>)}</p>}
  {result.documents&&<><details><summary>{result.documents.length} uploaded document references · indexing is separate from field extraction</summary><ul>{result.documents.map((document:Entity)=><li key={document.id}>{document.name}<code>{document.id}</code></li>)}</ul></details>{result.documents.filter((d:Entity)=>d.merge).map((d:Entity)=><MergedDetails key={d.id} merge={{...d.merge,document_id:d.id}}/>)}</>}
  {result.extractions?.filter((entry:Entity)=>!entry.superseded).map((entry:Entity)=><section key={entry.extraction_id}><strong>{entry.name}</strong><span className="small"> · {entry.status==='completed'?'Ready for review':entry.status}</span><p className="small">Extraction ID: <code>{entry.extraction_id}</code></p><MergedDetails merge={entry.merge} extractionId={entry.extraction_id}/>{entry.record_progress&&<p role="status">{entry.record_progress.completed} of {entry.record_progress.total} source records extracted</p>}{entry.data?.records&&<p>{entry.data.records.length} separate records in this result</p>}{entry.status==='completed'&&<div className="agent-v2-result-actions"><details><summary>Extracted fields</summary><pre>{JSON.stringify(entry.data,null,2)}</pre></details><ActionButton className="text-button" onClick={()=>onReview(entry.extraction_id)} label="Review result and evidence" action="review"/></div>}</section>)}
  {!result.extractions&&tool.status==='completed'&&result.extraction_id&&<div className="agent-v2-result-actions"><p className="small">Extraction ID: <code>{result.extraction_id}</code></p><details><summary>Extracted fields</summary><pre>{JSON.stringify(result.data,null,2)}</pre></details><ActionButton className="text-button" onClick={()=>onReview(result.extraction_id)} label="Review result and evidence" action="review"/></div>}
 </div>;
}
