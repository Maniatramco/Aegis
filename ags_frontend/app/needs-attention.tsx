"use client";
import {useEffect,useRef} from 'react';
import {AlertTriangle,CheckCircle2,CircleDashed,FileText,RefreshCw,X,XCircle} from 'lucide-react';
import './needs-attention.css';

type Entity=Record<string,any>;
export type AttentionScope={datasetId?:string;jobId?:string;documentId?:string};
export type AttentionView='Files & processing'|'Jobs & activity'|'Model Registration'|'Model Mapping'|'Storage'|'Datasets';
export type AttentionItem={id:string;kind:'failed'|'reindex';name:string;dataset:string;datasetId:string;job?:Entity;error:string;stage:string;advice:{text:string;view?:AttentionView;adminOnly?:boolean}};

const EVENT='aegis:attention';
/** Any screen can open the shared pop-up without threading callbacks through every component. */
export function openAttention(scope:AttentionScope={}){if(typeof window!=='undefined')window.dispatchEvent(new CustomEvent(EVENT,{detail:scope}));}
export function onAttention(handler:(scope:AttentionScope)=>void){
 const listener=(event:Event)=>handler((event as CustomEvent<AttentionScope>).detail||{});
 window.addEventListener(EVENT,listener);return()=>window.removeEventListener(EVENT,listener);
}

/** Turns a stored failure message into the next step a person can take. */
export function adviceFor(error:string,kind:'failed'|'reindex'):AttentionItem['advice']{
 if(kind==='reindex')return {text:'The dataset’s embedding or OCR mapping changed after this file was indexed. Reindex it so answers use the current models.',view:'Files & processing',adminOnly:true};
 if(/timed? ?out|timeout/i.test(error))return {text:'The model took too long. Increase its Timeout in Model Registration, then retry.',view:'Model Registration',adminOnly:true};
 if(/context|token|too (large|long)/i.test(error))return {text:'The content did not fit the model’s limits. Raise the context or output limit in Model Registration, or process fewer documents, then retry.',view:'Model Registration',adminOnly:true};
 if(/credential|unauthori[sz]ed|forbidden|api key|401|403|permission/i.test(error))return {text:'The model connection was refused. Check its credentials in Model Registration, then retry.',view:'Model Registration',adminOnly:true};
 if(/embedding|mapping|no model|not mapped/i.test(error))return {text:'The dataset is missing a model for this step. Map it in Model Mapping, then retry.',view:'Model Mapping',adminOnly:true};
 if(/storage|not found|missing|bucket|object/i.test(error))return {text:'The original file or its storage could not be read. Check Storage, then retry.',view:'Storage',adminOnly:true};
 return {text:'Retry processing. The original file is preserved, so nothing needs to be uploaded again.'};
}

const kindName=(kind='')=>({index:'Indexing',extract:'Extraction',reextract:'Re-extraction',upload:'Upload'} as Record<string,string>)[kind]||'Processing';
const failedStage=(job?:Entity)=>{const stages=job?.workflow?.stages||{};const name=Object.keys(stages).find(key=>stages[key]?.status==='failed');return name||job?.stage||kindName(job?.kind);};
const stageName=(name:string)=>({upload:'Upload',extract:'Read text',ocr:'OCR',index:'Index',ready:'Ready',prepare:'Prepare',retrieving:'Retrieve',reranking:'Rerank',generating:'Extract',validating:'Validate'} as Record<string,string>)[name]||name.charAt(0).toUpperCase()+name.slice(1);

/** Everything that needs a person: failed or cancelled processing, and files whose index is out of date. */
export function attentionItems(documents:Entity[],jobs:Entity[],datasets:Entity[],scope:AttentionScope={}):AttentionItem[]{
 const datasetName=(id:string)=>datasets.find(d=>d.id===id)?.name||'Unknown dataset';
 const latestJob=(docId:string)=>jobs.filter(job=>(job.document_id||job.target_id)===docId).sort((a,b)=>(b.created_at||0)-(a.created_at||0))[0];
 const items:AttentionItem[]=[];
 for(const doc of documents){
  const datasetId=doc.dataset_id||doc.kb_id||'';
  const failed=['failed','cancelled'].includes(doc.status),stale=doc.status==='ready'&&doc.requires_reindex;
  if(!failed&&!stale)continue;
  const job=latestJob(doc.id),kind=failed?'failed':'reindex';
  const error=failed?(job?.error||doc.error||(doc.status==='cancelled'?'Processing was cancelled before it finished.':'Processing failed.')):'Index is out of date.';
  items.push({id:doc.id,kind,name:doc.name||doc.filename||'Untitled file',dataset:datasetName(datasetId),datasetId,job:failed&&job&&['failed','cancelled'].includes(job.status)?job:undefined,error,stage:failed?stageName(failedStage(job)):'Index',advice:adviceFor(error,kind)});
 }
 for(const job of jobs){
  if(!['failed','cancelled'].includes(job.status)||items.some(item=>item.job?.id===job.id||item.id===(job.document_id||job.target_id)))continue;
  const doc=documents.find(d=>d.id===(job.document_id||job.target_id));
  const datasetId=doc?.dataset_id||doc?.kb_id||job.dataset_id||'';
  const error=job.error||'Processing failed.';
  items.push({id:job.id,kind:'failed',name:doc?.name||`${kindName(job.kind)} job`,dataset:datasetName(datasetId),datasetId,job,error,stage:stageName(failedStage(job)),advice:adviceFor(error,'failed')});
 }
 return items.filter(item=>(!scope.datasetId||item.datasetId===scope.datasetId)&&(!scope.jobId||item.job?.id===scope.jobId)&&(!scope.documentId||item.id===scope.documentId));
}

function StageTrack({job}:{job:Entity}){
 const stages=Object.entries(job.workflow?.stages||{}) as [string,Entity][];
 if(!stages.length)return null;
 return <ol className="attention-stages" aria-label="Processing stages">{stages.map(([name,stage])=><li key={name} data-status={stage.status}>{stage.status==='completed'?<CheckCircle2 size={13}/>:stage.status==='failed'?<XCircle size={13}/>:<CircleDashed size={13}/>}{stageName(name)}</li>)}</ol>;
}

export function NeedsAttentionDialog({items,isAdmin,busy,onClose,onRetry,onNavigate}:{items:AttentionItem[];isAdmin:boolean;busy:boolean;onClose:()=>void;onRetry:(job:Entity)=>void;onNavigate:(view:AttentionView)=>void}){
 const panel=useRef<HTMLDivElement>(null);
 useEffect(()=>{const previous=document.activeElement as HTMLElement|null;panel.current?.querySelector<HTMLElement>('button')?.focus();const key=(event:KeyboardEvent)=>{if(event.key==='Escape')onClose();};document.addEventListener('keydown',key);return()=>{document.removeEventListener('keydown',key);previous?.focus?.();};},[onClose]);
 return <div className="attention-backdrop" onClick={event=>{if(event.target===event.currentTarget)onClose();}}>
  <div ref={panel} className="attention-dialog" role="dialog" aria-modal="true" aria-labelledby="attention-title">
   <header><span className="attention-icon"><AlertTriangle size={18}/></span><div><h2 id="attention-title">Needs attention</h2><p>{items.length?`${items.length} item${items.length===1?'':'s'} need${items.length===1?'s':''} an action. Originals are preserved.`:'Nothing needs attention right now.'}</p></div><button type="button" className="btn icon" aria-label="Close" onClick={onClose}><X size={16}/></button></header>
   <div className="attention-list">
    {!items.length&&<p className="attention-clear"><CheckCircle2 size={16}/>All files and jobs are healthy.</p>}
    {items.map(item=>{const retryable=Boolean(item.job)&&item.kind==='failed';const adminBlocked=item.advice.adminOnly&&!isAdmin;
     return <article key={item.id} className="attention-item" data-kind={item.kind}>
      <div className="attention-item-head"><FileText size={16}/><div><strong title={item.name}>{item.name}</strong><span>{item.dataset}{item.job?.attempts?` · attempt ${item.job.attempts}`:''}</span></div><em>{item.kind==='reindex'?'Reindex needed':`${item.stage||'Processing'} failed`}</em></div>
      {item.job&&<StageTrack job={item.job}/>}
      <p className="attention-error" role="note"><strong>What happened</strong>{item.error}</p>
      <p className="attention-advice"><strong>What to do</strong>{item.advice.text}{adminBlocked&&' This needs an administrator; ask one to make the change.'}</p>
      <div className="attention-actions">
       {retryable&&<button type="button" className="btn primary" disabled={busy} onClick={()=>onRetry(item.job!)}><RefreshCw size={15}/>Retry</button>}
       {item.advice.view&&!adminBlocked&&<button type="button" className={`btn${retryable?'':' primary'}`} onClick={()=>onNavigate(item.advice.view!)}>Open {item.advice.view}</button>}
       {isAdmin&&item.advice.view!=='Files & processing'&&<button type="button" className="btn" onClick={()=>onNavigate('Files & processing')}>Open Files & processing</button>}
       {item.job&&<button type="button" className="btn" onClick={()=>onNavigate('Jobs & activity')}>View in Jobs</button>}
       <button type="button" className="btn" onClick={()=>onNavigate('Datasets')}>Open dataset</button>
      </div>
     </article>;})}
   </div>
  </div>
 </div>;
}
