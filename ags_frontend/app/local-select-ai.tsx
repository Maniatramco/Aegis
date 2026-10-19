"use client";
import {useEffect,useRef,useState,type FormEvent} from 'react';
import {ArrowUpRight,CheckCircle2,ChevronDown,Code2,Database,HardDrive,RefreshCw,ShieldCheck,Sparkles} from 'lucide-react';
import {WorkflowStepper,type WorkflowStep} from './workflow-stepper';
import './local-select-ai.css';

type Api=(path:string,method?:string,body?:unknown,signal?:AbortSignal,quiet?:boolean)=>Promise<any>;
type Status={enabled:boolean;ready?:boolean;detail?:string;model?:string;database?:string;tables?:Record<string,string[]>};
type Result={sql:string;columns:string[];rows:(string|number|null)[][];row_limit:number;has_more:boolean;metadata_as_of:number;metadata_rows:Record<string,number>;steps:WorkflowStep[]};
const examples=[
 'How many documents are in each dataset? Include datasets with zero documents.',
 'List datasets that have no data steward.',
 'Count extraction runs by review status.',
];

export function LocalSelectAI({datasetIds,api}:{datasetIds:string[];api:Api}){
 const [status,setStatus]=useState<Status|null>(null),[refresh,setRefresh]=useState(0);
 const [question,setQuestion]=useState(examples[0]),[busy,setBusy]=useState(false),[error,setError]=useState('');
 const [result,setResult]=useState<Result|null>(null),[attempted,setAttempted]=useState(false);
 const request=useRef<AbortController|null>(null);
 const scopeKey=[...datasetIds].sort().join('|');
 useEffect(()=>{
  const controller=new AbortController();
  void api('/governance/local-sql/status','GET',undefined,controller.signal,true).then(value=>{
   if(!controller.signal.aborted)setStatus(value);
  }).catch(()=>{if(!controller.signal.aborted)setStatus(old=>old?.enabled?{enabled:true,ready:false,detail:'Local services are unavailable. Refresh to check again.'}:null);});
  return()=>controller.abort();
 },[api,refresh]);
 useEffect(()=>{
  request.current?.abort();request.current=null;
  setResult(null);setError('');setBusy(false);setAttempted(false);
  return()=>request.current?.abort();
 },[scopeKey]);
 const submit=async(event:FormEvent)=>{
  event.preventDefault();if(busy||!status?.ready||!datasetIds.length||question.trim().length<3)return;
  const controller=new AbortController();request.current=controller;
  setBusy(true);setError('');setResult(null);setAttempted(true);
  try{
   const value=await api('/governance/local-sql/query','POST',{dataset_ids:datasetIds,question:question.trim()},controller.signal,true);
   if(!controller.signal.aborted)setResult(value);
  }catch(reason:any){if(!controller.signal.aborted)setError(reason.message||'The local query could not complete.');}
  finally{if(!controller.signal.aborted)setBusy(false);}
 };
 if(!status?.enabled)return null;
 const steps:WorkflowStep[]=result?.steps??(attempted?[{id:'request',label:'Local SQL request',status:busy?'running':'failed',detail:busy?'Oracle is generating and checking your query. The first request can take longer.':'Request stopped. No successful stages are assumed.'}]:[]);
 return <section className="local-ai" aria-labelledby="local-ai-title">
  <div className="local-ai-heading"><div className="local-ai-heading-icon"><Sparkles size={24}/></div><div><span className="local-ai-eyebrow">LOCAL SELECT AI · PREVIEW</span><h3 id="local-ai-title">Ask your metadata. See the SQL.</h3><p>Explore dataset ownership, document counts and extraction status with Oracle Select AI.</p></div><span className="local-ai-cost"><ShieldCheck size={15}/>No cloud inference charges</span></div>
  <div className="local-ai-facts"><span><Database size={15}/>Oracle Database Free</span><span><HardDrive size={15}/>Qwen3 4B · on this computer</span><span className={status.ready?'local-ai-ready':'local-ai-offline'}><i/>{status.ready?'Local services ready':'Local services unavailable'}</span><button type="button" className="btn icon" aria-label="Refresh local Select AI status" disabled={busy} onClick={()=>setRefresh(old=>old+1)}><RefreshCw size={14}/></button></div>
  {!status.ready&&<p className="local-ai-error" role="status">{status.detail}</p>}
  <div className="local-ai-content"><div className="local-ai-question">
   <div className="local-ai-scope"><span><ShieldCheck size={15}/>{datasetIds.length} authorized {datasetIds.length===1?'dataset':'datasets'} in scope</span><small>Uses the dataset selection below</small></div>
   <form onSubmit={submit}><label htmlFor="local-ai-question">What would you like to know?</label><textarea id="local-ai-question" value={question} maxLength={1200} rows={3} disabled={busy} onChange={event=>setQuestion(event.target.value)}/><div className="local-ai-submit"><span>Metadata only · read-only results</span><button type="submit" className="btn primary" disabled={busy||!status.ready||!datasetIds.length||question.trim().length<3}>{busy?'Running locally…':'Generate & preview'}<ArrowUpRight size={16}/></button></div></form>
   <div className="local-ai-examples" aria-label="Example metadata questions">{examples.map(value=><button key={value} type="button" disabled={busy} onClick={()=>setQuestion(value)}>{value}</button>)}</div>
  </div><aside className="local-ai-explainer"><Code2 size={20}/><strong>Your question becomes a query</strong><p>Oracle builds SQL with the local model. Aegis checks it, then reads a temporary copy of your permitted metadata.</p><ul><li>Cloud model calls are blocked</li><li>Original files and extracted values are excluded</li><li>Your module and dataset access are rechecked</li></ul><details><summary>Available metadata <ChevronDown size={13}/></summary>{Object.entries(status.tables??{}).map(([table,columns])=><div key={table}><code>{table}</code><small>{columns.join(', ')}</small></div>)}</details></aside></div>
  {steps.length>0&&<div className="local-ai-workflow" aria-live="polite"><WorkflowStepper steps={steps} label="Local Select AI request stages"/></div>}
  {error&&<p className="local-ai-error" role="alert">{error}</p>}
  {result&&<div className="local-ai-result"><div className="local-ai-result-heading"><div><CheckCircle2 size={18}/><h4>Query preview</h4></div><span>{result.rows.length} {result.rows.length===1?'row':'rows'}{result.has_more?' · limited to '+result.row_limit:''}</span></div><div className="local-ai-result-grid"><div className="local-ai-sql"><span>GENERATED ORACLE SQL</span><pre><code>{result.sql}</code></pre></div><div className="local-ai-table-wrap" role="region" aria-label="Local SQL query results" tabIndex={0}><table><thead><tr>{result.columns.map((column,index)=><th key={index}>{column.replaceAll('_',' ')}</th>)}</tr></thead><tbody>{result.rows.map((row,index)=><tr key={index}>{row.map((cell,number)=><td key={number}>{cell===null?<span className="local-ai-null">Not set</span>:String(cell)}</td>)}</tr>)}</tbody></table>{!result.rows.length&&<p>No metadata matched this query.</p>}</div></div><p className="local-ai-result-note">Complete selected metadata snapshot · {Object.values(result.metadata_rows).reduce((sum,value)=>sum+value,0)} metadata rows · {new Date(result.metadata_as_of*1000).toLocaleTimeString()} · Generated SQL may need review.</p></div>}
 </section>;
}
