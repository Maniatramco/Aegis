"use client";
import {useCallback,useEffect,useRef,useState} from 'react';
import {FileText,RefreshCw,Search,Shield,Trash2,X} from 'lucide-react';
import {WorkflowStepper} from './workflow-stepper';
import './admin-documents.css';

type Entity=Record<string,any>;
type Api=(path:string,method?:string,body?:any)=>Promise<any>;
const stamp=(v:number)=>new Date(v*1000).toLocaleString();
const active=(status:string)=>['queued','running','processing','blocked'].includes(status);
const stageNames:Record<string,string>={upload:'Upload',extract:'Text / OCR',index:'Index',ready:'Ready'};
function State({value}:{value:string}){
 const color=['ready','present','completed','reviewed'].includes(value)?'green':['failed','missing','unavailable','deleting'].includes(value)?'red':'amber';
 return <span className={`pill ${color}`}>{(value||'Not started').replaceAll('_',' ')}</span>;
}
export function AdminDocuments({api,onChanged,onReview}:{api:Api;onChanged:()=>void;onReview:(id:string)=>void}){
 const [data,setData]=useState<Entity>({items:[],datasets:[],total:0}),[search,setSearch]=useState(''),[dataset,setDataset]=useState(''),[offset,setOffset]=useState(0);
 const [loading,setLoading]=useState(true),[busy,setBusy]=useState(false),[error,setError]=useState(''),[notice,setNotice]=useState('');
 const [operation,setOperation]=useState<Entity|null>(null),[confirmation,setConfirmation]=useState(''),[consent,setConsent]=useState(false),[selected,setSelected]=useState('');
 const sequence=useRef(0),mounted=useRef(true),form=useRef<HTMLDivElement>(null);
 const load=useCallback(async(quiet=false)=>{
  const request=++sequence.current;if(!quiet)setLoading(true);
  try{const next=await api(`/admin/documents?limit=25&offset=${offset}&search=${encodeURIComponent(search)}&dataset_id=${encodeURIComponent(dataset)}`);if(mounted.current&&request===sequence.current){setData(next);if(!quiet)setError('');}}
  catch(e){if(mounted.current&&request===sequence.current)setError(e instanceof Error?e.message:'Unable to load files.');}
  finally{if(mounted.current&&request===sequence.current)setLoading(false);}
 },[api,offset,search,dataset]);
 useEffect(()=>{mounted.current=true;const timer=setTimeout(()=>void load(),250);return()=>{clearTimeout(timer);mounted.current=false;sequence.current++;};},[load]);
 useEffect(()=>{const timer=setInterval(()=>{if(!busy&&!operation&&document.visibilityState==='visible')void load(true);},10000);return()=>clearInterval(timer);},[load,busy,operation]);
 useEffect(()=>{if(operation){form.current?.focus();form.current?.scrollIntoView({block:'nearest'});}},[operation]);
 async function open(kind:string,row:Entity,extraction?:Entity){
  if(busy)return;setBusy(true);setError('');setNotice('');setConsent(false);setConfirmation('');
  try{
   const detail=kind==='delete'?await api(`/admin/documents/${row.id}/deletion-preview`):kind==='extract'?await api(`/extractions/${extraction!.id}`):null;
   setOperation({kind,row,detail,key:crypto.randomUUID()});
  }catch(e){setError(e instanceof Error?e.message:'Unable to check this file.');}finally{setBusy(false);}
 }
 async function submit(){
  if(!operation||busy)return;setBusy(true);setError('');
  try{
   const {kind,row,detail,key}=operation;
   if(kind==='delete'){
    await api(`/admin/documents/${row.id}`,'DELETE',{confirmation,expected_version:detail.version,expected_impact:detail.impact_token});
    setNotice(`Deleted ${row.name} and its related files, indexes, results and affected chats/workflows.`);setSelected('');
   }else if(kind==='extract'){
    const result=await api(`/extractions/${detail.id}/rerun`,'POST',{source_version:detail.version,template_id:detail.template_id,display_name:`${detail.name} · new run`.slice(0,200),idempotency_key:key,allow_external:consent});
    const failed=result.calls?.find((call:Entity)=>call.status==='failed');
    if(failed)throw new Error(failed.error||'Re-extraction could not be submitted. Inspect Jobs & activity.');
    setNotice('New extraction accepted using current dataset models. Outdated source indexes are rebuilt first. Earlier results are retained.');
   }else{
    await api(`/admin/documents/${row.id}/retry`,'POST',{allow_external:consent});
    setNotice(`Indexing queued for ${row.name} using the current dataset embedding and OCR models.`);
   }
   setOperation(null);onChanged();await load(true);
  }catch(e){setError(e instanceof Error?e.message:'Operation failed. Retry after checking service health.');await load(true);}finally{setBusy(false);}
 }
 const row=data.items.find((item:Entity)=>item.id===selected);
 return <div className="admin-documents">
  <section className="panel file-intro"><div><div className="eyebrow"><Shield size={15}/> ADMINISTRATION</div><h2>Files & processing</h2><p className="muted">Application source files in OCI and their pinned storage locations, with indexing, OCR and extraction status.</p></div><button className="btn" disabled={loading||busy} onClick={()=>void load()}><RefreshCw size={16}/> Refresh</button></section>
  {notice&&<div className="notice" role="status">{notice}</div>}
  {error&&<div className="error" role="alert">{error}</div>}
  {data.metadata_warnings>0&&<div className="notice" role="status">Some extraction metadata could not be read. Results may be incomplete; deletion will require readable metadata.</div>}
  {operation&&<section className="panel file-operation" role="dialog" aria-modal="false" aria-labelledby="file-operation-title" tabIndex={-1} ref={form}>
   <div className="file-operation-heading"><h3 id="file-operation-title">{operation.kind==='delete'?'Permanently delete file':operation.kind==='extract'?'Start a new extraction':'Retry indexing with current models'}</h3><button className="btn icon" aria-label="Close file operation" disabled={busy} onClick={()=>setOperation(null)}><X size={18}/></button></div>
   <strong className="file-name">{operation.row.name}</strong>
   {operation.kind==='delete'?<>
    <p>{operation.detail.note}</p>
    <p><strong>{operation.detail.affected.extractions}</strong> extraction runs · <strong>{operation.detail.affected.conversations}</strong> chats · <strong>{operation.detail.affected.workflows}</strong> workflows · <strong>{operation.detail.affected.jobs}</strong> processing jobs</p>
    {operation.detail.cleanup_stage!=='planned'&&<p>Previous cleanup paused at {operation.detail.cleanup_stage}. This action resumes the remaining cleanup.</p>}
    <p className="muted">Active dataset processing must finish before deletion can proceed. This action cannot be undone.</p>
    <label>Type the exact filename to confirm<input autoComplete="off" value={confirmation} disabled={busy} onChange={e=>setConfirmation(e.target.value)}/></label>
   </>:<>
    <p>{operation.kind==='extract'?'Creates a separate result with the saved prompt and current dataset extraction model. It rebuilds outdated source indexes using the current embedding and OCR mappings.':'Reads the unchanged original again and rebuilds its index using the dataset’s current embedding and OCR mappings.'}</p>
    <label className="file-consent"><input type="checkbox" checked={consent} disabled={busy} onChange={e=>setConsent(e.target.checked)}/> Allow document content to be sent to the configured cloud models for this operation.</label>
   </>}
   <div className="file-operation-actions"><button className="btn" disabled={busy} onClick={()=>setOperation(null)}>Cancel</button><button className={`btn ${operation.kind==='delete'?'danger':'primary'}`} disabled={busy||(operation.kind==='delete'?confirmation!==operation.row.name:!consent)} onClick={()=>void submit()}>{busy?'Working…':operation.kind==='delete'?'Delete permanently':operation.kind==='extract'?'Start new extraction':'Retry indexing'}</button></div>
  </section>}
  <section className="panel file-catalog" aria-busy={loading}>
   <div className="file-filters"><label className="file-search"><Search size={17}/><input aria-label="Search files" placeholder="Search filename, dataset or document ID" value={search} onChange={e=>{setSearch(e.target.value);setOffset(0);}}/></label><label>Dataset<select aria-label="Filter files by dataset" value={dataset} onChange={e=>{setDataset(e.target.value);setOffset(0);}}><option value="">All datasets</option>{data.datasets.map((d:Entity)=><option key={d.id} value={d.id}>{d.name}</option>)}</select></label><span className="muted small">{data.total} files</span></div>
   <p className="file-table-hint">Scroll across the table for statuses and actions.</p>
   <div className="file-table-scroll"><table><thead><tr><th>File / dataset</th><th>Source storage</th><th>Index</th><th>OCR</th><th>Extractions</th><th>Actions</th></tr></thead><tbody>
    {data.items.map((item:Entity)=><tr key={item.id} className={selected===item.id?'file-selected':''}>
     <td><button className="file-title" onClick={()=>setSelected(selected===item.id?'':item.id)}><FileText size={17}/><span>{item.name}</span></button><div className="muted small">{item.dataset_name}{item.dataset_deleted?' · archived dataset':''} · v{item.version}</div><div className="muted small">{(item.size/1024).toFixed(1)} KB · {stamp(item.created_at)}</div></td>
     <td><State value={item.storage.status}/><div className="muted small">{item.storage.provider==='oci'?'OCI · '+item.storage.bucket:'Local storage'}</div></td>
     <td><State value={item.status}/>{item.requires_reindex&&item.status==='ready'&&<div className="small">New mappings · reindex needed</div>}{item.index_job&&<div className="muted small">{item.index_job.stage} · {item.index_job.progress}%</div>}</td>
     <td>{item.ocr?<><span>{item.ocr.ocr_page_count} pages</span><div className="muted small">{item.ocr.model}</div></>:<span className="muted small">{item.status==='ready'?'Native text':'Not completed'}</span>}</td>
     <td>{item.extractions.length?<><State value={item.extractions[0].status}/><div className="muted small">{item.extractions.length} runs · latest {item.extractions[0].review_status}</div></>:<span className="muted small">Not started</span>}</td>
     <td><div className="file-row-actions"><button className="btn" disabled={busy||active(item.status)||item.status==='deleting'||item.storage.status!=='present'||item.dataset_deleted} onClick={()=>void open('index',item)}><RefreshCw size={14}/>{item.status==='failed'?'Retry index':'Reindex'}</button><button className="btn" disabled={busy} onClick={()=>setSelected(selected===item.id?'':item.id)}>Details</button><button className="btn danger" disabled={busy} onClick={()=>void open('delete',item)}><Trash2 size={14}/>{item.status==='deleting'?'Retry deletion':'Delete'}</button></div></td>
    </tr>)}
   </tbody></table></div>
   {!data.items.length&&<div className="empty"><FileText size={28}/><h3>{loading?'Loading files…':'No files found'}</h3><p>Upload documents to a dataset, or adjust your filters.</p></div>}
   <div className="file-pagination"><span className="muted small">{data.total?`${offset+1}–${Math.min(offset+25,data.total)} of ${data.total}`:'0 files'}</span><button className="btn" disabled={!offset||loading} onClick={()=>setOffset(Math.max(0,offset-25))}>Previous</button><button className="btn" disabled={offset+25>=data.total||loading} onClick={()=>setOffset(offset+25)}>Next</button></div>
  </section>
  {row&&<section className="panel file-details"><div className="file-operation-heading"><h3 className="file-name">{row.name}</h3><button className="btn icon" aria-label="Close file details" onClick={()=>setSelected('')}><X size={18}/></button></div><dl><dt>Document ID</dt><dd>{row.id}</dd><dt>Object key</dt><dd>{row.storage.key}</dd><dt>Current state</dt><dd>{row.error||row.index_notice||'No processing error reported.'}</dd></dl>
   {row.index_job&&<div aria-label="Indexing workflow"><h3>Indexing workflow</h3><WorkflowStepper label="Indexing workflow steps" steps={Object.entries(row.index_job.workflow?.stages||{}).map(([id,value])=>{const stage=value as Entity;return {id,label:stageNames[id]||id,status:stage.status,detail:stage.detail,statusLabel:stage.status==='blocked'?'Waiting':undefined};})}/></div>}
   <h3>Extraction runs</h3><p className="muted small">New extraction creates a separate run using current model mappings and the saved prompt.</p>
   {row.extractions.length?row.extractions.map((result:Entity)=><div className="file-extraction" key={result.id}><div><strong>{result.name}</strong><div className="muted small">{stamp(result.created_at)} · {result.review_status}</div><State value={result.status}/>{result.error&&<p className="small">{result.error}</p>}</div><div className="file-row-actions"><button className="btn" onClick={()=>onReview(result.id)}>Open result</button><button className="btn" disabled={busy||active(result.status)||row.status!=='ready'||row.dataset_deleted} onClick={()=>void open('extract',row,result)}><RefreshCw size={14}/> New extraction</button></div></div>):<p>No extraction has been started for this file.</p>}
  </section>}
 </div>;
}
