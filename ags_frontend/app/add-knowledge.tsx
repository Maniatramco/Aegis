"use client";
import {useEffect,useRef,useState} from 'react';
import {ArrowLeft,ArrowRight,CheckCircle2,Cloud,Database,FileText,Folder,Loader2,RefreshCw,ShieldCheck,AlertCircle,ChevronRight} from 'lucide-react';
import type {DatasetKnowledgeScope} from './dataset-knowledge-picker';
import './add-knowledge.css';

type Entity=Record<string,any>;
type Api=(path:string,method?:string,body?:unknown)=>Promise<any>;
type Step='choose'|'connect'|'select'|'vectorize';
export const STORAGE_PROVIDERS=[
 {id:'s3',name:'Amazon S3',help:'A bucket and optional folder prefix',auth:'Read-only access key or server IAM identity'},
 {id:'azure_blob',name:'Azure Blob Storage',help:'A storage account container',auth:'Container SAS token with read and list only'},
 {id:'oci_object',name:'OCI Object Storage',help:'A namespace bucket in your region',auth:'Customer secret key (S3-compatible)'},
 {id:'sharepoint',name:'SharePoint',help:'A site document library',auth:'Microsoft Entra application'},
 {id:'google_drive',name:'Google Drive',help:'A folder shared with a service account',auth:'Google service-account key'},
] as const;
const STEPS:[Step,string][]=[['choose','Choose storage'],['connect','Connect & test'],['select','Select documents'],['vectorize','Vectorize']];
export const MAX_SELECTION=20;
export const blankConnection=(provider:string,datasetId:string):Entity=>({name:'',provider,dataset_id:datasetId,enabled:true,auth_mode:'access_key',bucket:'',region:provider==='oci_object'?'ap-mumbai-1':provider==='s3'?'ap-south-1':'',prefix:'',expected_owner:'',tenant_id:'',client_id:'',site_id:'',drive_id:'',folder_id:'',account:'',container:'',namespace:'',endpoint:'',credentials:{}});
/** Only fields the server accepts; saved metadata never goes back. */
export const connectionPayload=(form:Entity)=>{const {id,version,updated_at,credentials_configured,secret_ref,owner,...body}=form;return body;};
/** A copied file is ready to ask only after indexing succeeds and its knowledge is published to chat. */
export function vectorizeState(result:Entity,documents:Entity[],published:string[]=[]){
 if(result.status==='failed')return {state:'failed',label:result.message||'Could not import this file.'};
 const doc=documents.find(d=>d.id===result.document_id);
 if(!doc||['queued','processing','running','uploaded'].includes(doc.status))return {state:'running',label:'Indexing…'};
 if(doc.status==='ready'&&!doc.requires_reindex&&!published.includes(doc.id))return {state:'publishing',label:'Indexed · publishing to chat…'};
 if(doc.status==='ready'&&!doc.requires_reindex)return {state:'ready',label:result.status==='already_imported'?'Already indexed · ready to ask':'Ready to ask'};
 if(['failed','cancelled'].includes(doc.status))return {state:'failed',label:'Indexing failed. Retry it from Files & processing.'};
 return {state:'running',label:doc.status||'Indexing…'};
}

export function AddKnowledge({api,datasets,documents,selectedDataset,onChanged,onAsk,onExtract,onBack}:{api:Api;datasets:Entity[];documents:Entity[];selectedDataset:string;onChanged:()=>void;onAsk:(scope:DatasetKnowledgeScope)=>void;onExtract:()=>void;onBack:()=>void}){
 const usable=datasets.filter(d=>d.active!==false);
 const [step,setStep]=useState<Step>('choose'),[connections,setConnections]=useState<Entity[]>([]),[active,setActive]=useState<Entity|null>(null);
 const [form,setForm]=useState<Entity|null>(null),[busy,setBusy]=useState(''),[error,setError]=useState(''),[message,setMessage]=useState(''),[tested,setTested]=useState(false);
 const [items,setItems]=useState<Entity[]>([]),[trail,setTrail]=useState<{id:string;name:string}[]>([]),[cursor,setCursor]=useState(''),[chosen,setChosen]=useState<Entity[]>([]);
 const [share,setShare]=useState(false),[external,setExternal]=useState(false),[needsConsent,setNeedsConsent]=useState(false),[results,setResults]=useState<Entity[]>([]);
 const [published,setPublished]=useState<string[]>([]),[publishFailed,setPublishFailed]=useState('');
 const sequence=useRef(0),publishing=useRef('');
 useEffect(()=>{let live=true;api('/source-connections').then(rows=>{if(live)setConnections(rows);}).catch(e=>{if(live)setError(e.message);});return()=>{live=false;sequence.current++;};},[api]);
 const states=results.map(r=>vectorizeState(r,documents,published)),pending=states.some(s=>s.state==='running');
 // Indexing runs in the worker; refresh the document list until every copy settles.
 useEffect(()=>{if(step!=='vectorize'||!pending)return;const timer=setInterval(onChanged,3000);return()=>clearInterval(timer);},[step,pending,onChanged]);
 // Once copies are indexed, publish them to the chat knowledge instead of waiting for the background refresh.
 const waiting=results.filter((r,i)=>states[i].state==='publishing').map(r=>r.document_id),waitingKey=waiting.join(',');
 const publish=async(ids:string[])=>{if(!active||publishing.current===ids.join(','))return;publishing.current=ids.join(',');setPublishFailed('');try{const data=await api(`/source-connections/${encodeURIComponent(active.id)}/publish`,'POST',{document_ids:ids,allow_external:external});setPublished(current=>[...new Set([...current,...data.published])]);}catch(e){setPublishFailed(e instanceof Error?e.message:'Publishing to chat failed.');}finally{publishing.current='';}};
 useEffect(()=>{if(step==='vectorize'&&waiting.length&&!publishFailed)void publish(waiting);},[step,waitingKey,publishFailed]);
 const run=async(label:string,action:()=>Promise<void>)=>{setBusy(label);setError('');setMessage('');try{await action();}catch(e){const text=e instanceof Error?e.message:'Storage request failed.';if(/external/i.test(text))setNeedsConsent(true);setError(text);}finally{setBusy('');}};
 const dataset=usable.find(d=>d.id===(active?.dataset_id||form?.dataset_id));
 const change=(key:string,value:unknown)=>{setForm(current=>current?{...current,[key]:value}:current);setTested(false);setMessage('');};
 const secret=(key:string,value:string)=>{setForm(current=>current?{...current,credentials:{...current.credentials,[key]:value}}:current);setTested(false);setMessage('');};
 const pick=(provider:string)=>{setForm(blankConnection(provider,usable.some(d=>d.id===selectedDataset)?selectedDataset:usable[0]?.id||''));setActive(null);setTested(false);setError('');setMessage('');setStep('connect');};
 const browse=async(connection:Entity,path:{id:string;name:string}[]=[],page='')=>{const request=++sequence.current;await run('Reading documents',async()=>{const data=await api(`/source-connections/${encodeURIComponent(connection.id)}/files?folder=${encodeURIComponent(path.at(-1)?.id||'')}${page?'&cursor='+encodeURIComponent(page):''}`);if(request!==sequence.current)return;setItems(previous=>page?[...previous,...data.items]:data.items);setCursor(data.next_cursor);setTrail(path);});};
 const open=(connection:Entity)=>{setActive(connection);setForm(null);setItems([]);setChosen([]);setResults([]);setPublished([]);setPublishFailed('');setShare(false);setExternal(false);setNeedsConsent(false);setStep('select');void browse(connection);};
 const test=()=>form&&run('Testing connection',async()=>{const result=await api('/source-connections/test','POST',connectionPayload(form));setTested(true);setMessage(result.message);});
 const save=()=>form&&run('Saving connection',async()=>{const saved=await api('/source-connections','POST',connectionPayload(form));setConnections(current=>[...current.filter(c=>c.id!==saved.id),saved].sort((a,b)=>a.name.localeCompare(b.name)));open(saved);});
 const toggle=(item:Entity)=>setChosen(current=>current.some(c=>c.id===item.id)?current.filter(c=>c.id!==item.id):current.length>=MAX_SELECTION?current:[...current,item]);
 const vectorize=()=>active&&run('Vectorizing',async()=>{const data=await api(`/source-connections/${encodeURIComponent(active.id)}/import`,'POST',{selections:chosen.map(item=>item.selection),publish_to_dataset:share,allow_external:external});setResults(data.results);setMessage(data.notice);setStep('vectorize');onChanged();});
 const ready=results.filter((r,i)=>states[i].state==='ready').map(r=>r.document_id);
 const field=(key:string,label:string,help='',required=true)=><label className="knowledge-field" key={key}><span>{label}{!required&&<em> · optional</em>}</span><input value={form?.[key]||''} required={required} onChange={e=>change(key,e.target.value)} autoComplete="off" spellCheck={false}/>{help&&<small>{help}</small>}</label>;
 const credential=(key:string,label:string,help='',multiline=false,required=true)=><label className={`knowledge-field${multiline?' wide':''}`} key={key}><span>{label}{!required&&<em> · optional</em>}</span>{multiline?<textarea rows={5} value={form?.credentials?.[key]||''} required={required} onChange={e=>secret(key,e.target.value)} spellCheck={false}/>:<input type="password" value={form?.credentials?.[key]||''} required={required} onChange={e=>secret(key,e.target.value)} autoComplete="new-password"/>}{help&&<small>{help}</small>}</label>;
 const provider=STORAGE_PROVIDERS.find(p=>p.id===(form?.provider||active?.provider));
 const index=STEPS.findIndex(([id])=>id===step);
 return <section className="add-knowledge" aria-labelledby="add-knowledge-title">
  <header className="add-knowledge-hero">
   <button type="button" className="add-knowledge-back" onClick={onBack}><ArrowLeft size={16}/>Dashboard</button>
   <h1 id="add-knowledge-title">Add new knowledge</h1>
   <p>Connect your cloud storage, choose documents and vectorize them into a dataset. Copies are read-only snapshots; your cloud files are never changed.</p>
   <ol className="add-knowledge-steps" aria-label="Progress">{STEPS.map(([id,label],i)=><li key={id} data-state={i<index?'done':i===index?'current':'todo'} aria-current={i===index?'step':undefined}><span>{i<index?<CheckCircle2 size={15}/>:i+1}</span>{label}</li>)}</ol>
  </header>
  {error&&<div role="alert" className="add-knowledge-alert"><AlertCircle size={17}/><span>{error}</span></div>}
  {message&&<div role="status" className="add-knowledge-message"><CheckCircle2 size={17}/><span>{message}</span></div>}

  {step==='choose'&&<div className="add-knowledge-body">
   {!usable.length&&<p className="add-knowledge-empty">You need access to an active dataset before adding knowledge. Ask your administrator to assign one.</p>}
   <h2>Where are your documents?</h2>
   <div className="storage-grid" role="list">{STORAGE_PROVIDERS.map(p=><button key={p.id} type="button" role="listitem" className="storage-card" disabled={!usable.length} onClick={()=>pick(p.id)} data-provider={p.id}><span className="storage-icon"><Cloud size={22}/></span><strong>{p.name}</strong><span>{p.help}</span><small>{p.auth}</small><ArrowRight size={16} className="storage-go"/></button>)}</div>
   {connections.length>0&&<><h2>Your saved connections</h2><ul className="saved-connections">{connections.map(c=><li key={c.id}><button type="button" onClick={()=>open(c)} disabled={!c.enabled}><Cloud size={17}/><span><strong>{c.name}</strong><small>{STORAGE_PROVIDERS.find(p=>p.id===c.provider)?.name} · {datasets.find(d=>d.id===c.dataset_id)?.name||'Dataset'}{c.enabled?'':' · disabled'}</small></span><span className="saved-action">Browse documents<ChevronRight size={15}/></span></button></li>)}</ul></>}
  </div>}

  {step==='connect'&&form&&provider&&<form className="add-knowledge-body" onSubmit={e=>{e.preventDefault();void save();}}>
   <div className="knowledge-section-head"><h2>Connect {provider.name}</h2><button type="button" className="text-button" onClick={()=>setStep('choose')}>Choose different storage</button></div>
   <fieldset disabled={!!busy}><legend className="sr-only">{provider.name} location and credentials</legend>
   <div className="knowledge-fields">
    {field('name','Connection name','For example: Finance contracts')}
    <label className="knowledge-field"><span>Add documents to dataset</span><select value={form.dataset_id} required onChange={e=>change('dataset_id',e.target.value)}>{usable.map(d=><option key={d.id} value={d.id}>{d.name}</option>)}</select><small>Copies follow this dataset's access and embedding model.</small></label>
    {form.provider==='s3'&&<>{field('bucket','S3 bucket','Bucket name, without s3://')}{field('region','AWS region','For example: ap-south-1')}{field('prefix','Folder prefix','End with / to limit browsing to one folder.',false)}{field('expected_owner','Expected bucket owner','12-digit AWS account ID.',false)}
     <label className="knowledge-field"><span>Sign-in method</span><select value={form.auth_mode} onChange={e=>{change('auth_mode',e.target.value);change('credentials',{});}}><option value="access_key">Access key</option><option value="server_identity">Server IAM identity</option></select></label>
     {form.auth_mode==='access_key'&&<>{credential('access_key_id','Access key ID')}{credential('secret_access_key','Secret access key','Use a key that can only list and read.')}{credential('session_token','Session token','',false,false)}</>}</>}
    {form.provider==='azure_blob'&&<>{field('account','Storage account','For example: contosodocs')}{field('container','Container')}{field('prefix','Folder prefix','End with / to limit browsing to one folder.',false)}{credential('sas_token','Container SAS token','Read (r) and list (l) permissions only. Paste the part after ?.',true)}</>}
    {form.provider==='oci_object'&&<>{field('namespace','Object Storage namespace','Shown on the bucket details page.')}{field('bucket','Bucket')}{field('region','Region','For example: ap-mumbai-1')}{field('prefix','Folder prefix','End with / to limit browsing to one folder.',false)}{credential('access_key_id','Customer secret key: access key')}{credential('secret_access_key','Customer secret key: secret','From your OCI user profile > Customer secret keys.')}</>}
    {form.provider==='sharepoint'&&<>{field('tenant_id','Entra tenant ID','Directory UUID')}{field('client_id','Application client ID','Entra application UUID')}{credential('client_secret','Application client secret')}{field('site_id','SharePoint site ID','Not the site URL.')}{field('drive_id','Document library drive ID')}{field('folder_id','Folder item ID','Leave empty for the library root.',false)}</>}
    {form.provider==='google_drive'&&<>{field('folder_id','Google Drive folder ID','Share the folder with the service-account email.')}{credential('service_account','Service-account JSON key','Google Docs import as DOCX; Sheets and Slides as PDF.',true)}</>}
   </div>
   {['s3','azure_blob'].includes(form.provider)&&<details className="knowledge-advanced"><summary>Local storage emulator (development only)</summary>{field('endpoint','Emulator endpoint',form.provider==='azure_blob'?'For example: http://127.0.0.1:10000/devstoreaccount1':'For example: http://127.0.0.1:9000',false)}<small>Only accepted when this Aegis server enables local emulators. Leave empty for the real provider.</small></details>}
   </fieldset>
   <p className="knowledge-note"><ShieldCheck size={15}/>Credentials are encrypted on the server and never shown again. Aegis only lists and reads; it never writes to your storage.</p>
   <div className="knowledge-actions">
    <button type="button" className="btn" disabled={!!busy} onClick={e=>{if(e.currentTarget.form?.reportValidity())void test();}}>{busy==='Testing connection'?<Loader2 size={16} className="animate-spin"/>:<RefreshCw size={16}/>}Test connection</button>
    <button type="submit" className="btn primary" disabled={!!busy}>{busy==='Saving connection'?<Loader2 size={16} className="animate-spin"/>:null}{tested?'Save and browse documents':'Save and browse'}<ArrowRight size={16}/></button>
   </div>
  </form>}

  {step==='select'&&active&&<div className="add-knowledge-body">
   <div className="knowledge-section-head"><div><h2>Select documents</h2><p className="knowledge-sub">{active.name} · into <strong>{dataset?.name||'dataset'}</strong> · up to {MAX_SELECTION} files, PDF, DOCX, TXT or JSON</p></div><button type="button" className="text-button" onClick={()=>setStep('choose')}>Change storage</button></div>
   <nav className="knowledge-trail" aria-label="Folder path"><button type="button" onClick={()=>void browse(active,[])}>{active.name}</button>{trail.map((part,i)=><span key={part.id}><ChevronRight size={14}/><button type="button" onClick={()=>void browse(active,trail.slice(0,i+1))}>{part.name}</button></span>)}</nav>
   <ul className="knowledge-files" aria-busy={busy==='Reading documents'}>
    {items.map(item=>item.folder?<li key={item.id}><button type="button" className="knowledge-folder" onClick={()=>void browse(active,[...trail,{id:item.id,name:item.name}])}><Folder size={18}/><span>{item.name}</span><ChevronRight size={15}/></button></li>:<li key={item.id}><label data-disabled={!item.selection}><input type="checkbox" checked={chosen.some(c=>c.id===item.id)} disabled={!item.selection||(!chosen.some(c=>c.id===item.id)&&chosen.length>=MAX_SELECTION)} onChange={()=>toggle(item)} aria-label={`Select ${item.name}`}/><FileText size={18}/><span><strong>{item.name}</strong><small>{item.selection?`${Math.max(1,Math.round((item.size||0)/1024))} KB`:'Unsupported file type'}</small></span></label></li>)}
    {!items.length&&busy!=='Reading documents'&&<li className="knowledge-files-empty">No documents in this folder.</li>}
    {busy==='Reading documents'&&<li className="knowledge-files-empty"><Loader2 size={16} className="animate-spin"/>Reading documents…</li>}
   </ul>
   {cursor&&<button type="button" className="btn" disabled={!!busy} onClick={()=>void browse(active,trail,cursor)}>Load more</button>}
   <div className="knowledge-consent">
    <label><input type="checkbox" checked={share} onChange={e=>setShare(e.target.checked)}/><span>Everyone who can access <strong>{dataset?.name||'this dataset'}</strong> may read these copies.</span></label>
    <label data-highlight={needsConsent}><input type="checkbox" checked={external} onChange={e=>setExternal(e.target.checked)}/><span>If this dataset uses an external embedding service, allow sending the documents' text to it.</span></label>
   </div>
   <div className="knowledge-actions"><span className="knowledge-count">{chosen.length} of {MAX_SELECTION} selected</span><button type="button" className="btn primary" disabled={!!busy||!chosen.length||!share} onClick={()=>void vectorize()}>{busy==='Vectorizing'?<Loader2 size={16} className="animate-spin"/>:<Database size={16}/>}Vectorize {chosen.length||''} document{chosen.length===1?'':'s'}</button></div>
  </div>}

  {step==='vectorize'&&<div className="add-knowledge-body">
   <div className="knowledge-section-head"><div><h2>{pending||waiting.length?'Vectorizing into '+(dataset?.name||'dataset'):'Vectorizing finished'}</h2><p className="knowledge-sub">{pending?'Indexing runs in the background. You can leave this page; progress continues.':waiting.length?'Publishing the indexed copies to chat…':`${ready.length} of ${results.length} ready to ask.`}</p></div></div>
   {publishFailed&&<div role="alert" className="add-knowledge-alert"><AlertCircle size={17}/><span>{publishFailed}</span><button type="button" className="btn" onClick={()=>setPublishFailed('')}>Retry publishing</button></div>}
   <ul className="vectorize-list">{results.map((result,i)=><li key={result.document_id||result.name} data-state={states[i].state}>{['running','publishing'].includes(states[i].state)?<Loader2 size={18} className="animate-spin"/>:states[i].state==='ready'?<CheckCircle2 size={18}/>:<AlertCircle size={18}/>}<span><strong>{result.name}</strong><small>{states[i].label}</small></span></li>)}</ul>
   <div className="knowledge-actions">
    <button type="button" className="btn" onClick={()=>active&&open(active)}>Vectorize more</button>
    <button type="button" className="btn" onClick={onExtract}>Extract & review</button>
    <button type="button" className="btn primary" disabled={!ready.length||!dataset} onClick={()=>dataset&&onAsk({datasetIds:[dataset.id],documentIds:ready})}>Ask about {ready.length===1?'this document':'these documents'}<ArrowRight size={16}/></button>
   </div>
  </div>}
 </section>;
}
