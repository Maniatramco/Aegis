"use client";
import {useCallback, useEffect, useRef, useState} from 'react';
import {Bot, CheckCircle2, FileText, Loader2, Mic, Paperclip, Send, Volume2, VolumeX} from 'lucide-react';
import {BatchProgress} from './batch-progress';
import {JobProgress} from './operation-progress';
import {currentUploadStep, type UploadProgressItem} from './batch-workflow';
import './agent-v2.css';
import {speechCapabilities,startSpeechInput,speakResponse,type SpeechEnvironment} from './agent-voice';

type Entity=Record<string,any>;
type Api=(path:string,method?:string,body?:unknown,signal?:AbortSignal,quiet?:boolean)=>Promise<any>;
const active=(plan:Entity)=>plan.calls.some((call:Entity)=>['running','waiting'].includes(call.status));
const nextCall=(plan:Entity)=>plan.calls.findIndex((call:Entity)=>call.status!=='completed');
export const explainPlan=(plan:Entity)=>{
 if(!plan.calls.length)return 'No document action is queued. V2 supports upload, extraction, and re-extraction. Other tasks stay in the existing Aegis screens.';
 const labels:Record<string,string>={upload:'Upload documents',extract:'Extract fields',reextract:'Re-extract fields'};
 return `Proposed workflow: ${plan.calls.map((call:Entity)=>labels[call.tool]).join(' → ')}. Review the details and confirm each tool before it runs.${plan.calls.some((call:Entity)=>call.tool==='upload')&&plan.calls.some((call:Entity)=>call.tool==='extract')?' Extraction will use the uploaded references after indexing finishes.':''}${plan.calls.some((call:Entity)=>call.tool==='reextract')?' Earlier extraction results will be retained.':''}`;
};

export function AgentV2({api,username,onJobs,onVisibleJobs,onReview}:{api:Api;username:string;onJobs:(jobs:Entity[])=>void;onVisibleJobs:(ids:string[])=>void;onReview:(id:string)=>void}) {
 const [catalog,setCatalog]=useState<Entity>({datasets:[],documents:[],templates:[],models:[]});
 const [plans,setPlans]=useState<Entity[]>([]);
 const [dataset,setDataset]=useState(''); const [planner,setPlanner]=useState('');
 const [text,setText]=useState(''); const [files,setFiles]=useState<File[]>([]);
 const [working,setWorking]=useState(''); const [error,setError]=useState('');
 const [external,setExternal]=useState(false); const [spoken,setSpoken]=useState(false);
 const [voiceSupported,setVoiceSupported]=useState(false); const [speechSupported,setSpeechSupported]=useState(false); const [listening,setListening]=useState(false);
 const fileInput=useRef<HTMLInputElement>(null); const end=useRef<HTMLDivElement>(null);
 const lock=useRef(false); const mounted=useRef(true); const recognition=useRef<any>(null);
 const onJobsRef=useRef(onJobs); onJobsRef.current=onJobs;
 const onVisibleJobsRef=useRef(onVisibleJobs); onVisibleJobsRef.current=onVisibleJobs;
 const spokenRef=useRef(spoken); spokenRef.current=spoken;
 const announced=useRef(new Set<string>());
 const key=`aegis-agent-v2:${username}`;
 const speak=useCallback((message:string)=>{if(spokenRef.current)speakResponse(window as unknown as SpeechEnvironment,message,message=>{if(mounted.current)setError(message);});},[]);
 const replacePlan=useCallback((plan:Entity)=>{
  if(!mounted.current)return;
  setPlans(previous=>previous.some(p=>p.id===plan.id)?previous.map(p=>p.id===plan.id?plan:p):[...previous,plan]);
  // Publish ownership before publishing jobs, so the global popup cannot flash
  // a second workflow during the first render of a newly submitted tool.
  onVisibleJobsRef.current(plan.calls.flatMap((call:Entity)=>call.status==='waiting'?(call.job_ids||[]):[]));
  const jobs=plan.calls.flatMap((c:Entity)=>c.jobs||[]); if(jobs.length)onJobsRef.current(jobs);
  for(const [index,call] of plan.calls.entries())if(call.status==='completed'&&!announced.current.has(`${plan.id}:${index}`)){
   announced.current.add(`${plan.id}:${index}`);speak(`${call.title} completed.`);
  }
 },[speak]);
 const loadCatalog=useCallback(async()=>{const result=await api('/agent-v2/catalog','GET',undefined,undefined,true);if(mounted.current)setCatalog(result);return result;},[api]);
 useEffect(()=>{
  mounted.current=true;let cancelled=false;
  const capabilities=speechCapabilities(window as unknown as SpeechEnvironment);setVoiceSupported(capabilities.input);setSpeechSupported(capabilities.output);
  void loadCatalog().then(async(result)=>{
   if(cancelled)return;
   const local=result.models.filter((m:Entity)=>m.enabled!==false&&m.capabilities.includes('chat'));
   if(local.length===1)setPlanner(local[0].id);
   const previous=sessionStorage.getItem(key);if(previous){const plan=await api(`/agent-v2/plans/${previous}`,'GET',undefined,undefined,true);if(!cancelled){replacePlan(plan);setDataset(plan.dataset_id);setPlanner(plan.planner.id);}}
  }).catch(e=>{if(!cancelled)setError(e.message);});
  return()=>{cancelled=true;mounted.current=false;recognition.current?.abort();if('speechSynthesis' in window)window.speechSynthesis.cancel();};
 },[api,key,loadCatalog,replacePlan]);
 useEffect(()=>{onVisibleJobs(plans.flatMap(plan=>plan.calls.flatMap((call:Entity)=>call.status==='waiting'?(call.job_ids||[]):[])));},[plans,onVisibleJobs]);
 useEffect(()=>()=>onVisibleJobs([]),[onVisibleJobs]);
 useEffect(()=>{end.current?.scrollIntoView({block:'nearest',behavior:'smooth'});},[plans.length,working]);
 const update=useCallback((id:string,changes:Entity)=>setPlans(previous=>previous.map(plan=>plan.id===id?{...plan,...changes}:plan)),[]);
 const perform=useCallback(async(plan:Entity,index:number)=>{
  if(lock.current)return; lock.current=true;
  const call=plan.calls[index];setWorking(call.tool==='upload'?'Uploading documents…':'Starting extraction…');setError('');
  try {
   let result;
   if(call.tool==='upload'){
    const data=new FormData();for(const file of files)data.append('files',file);data.append('dataset_id',plan.dataset_id);data.append('allow_external',String(external));data.append('confirmed','true');
    result=await api(`/agent-v2/plans/${plan.id}/calls/${index}/upload`,'POST',data,undefined,true);setFiles([]);
   } else result=await api(`/agent-v2/plans/${plan.id}/calls/${index}`,'POST',{dataset_id:plan.dataset_id,document_ids:plan.document_ids,template_id:plan.template_id,allow_external:external,confirmed:true},undefined,true);
   replacePlan(result);
  } catch(e){if(mounted.current)setError(e instanceof Error?e.message:'The action could not finish.');}
  finally{lock.current=false;if(mounted.current)setWorking('');}
 },[api,external,files,replacePlan]);
 // Live server events report real jobs. Reconnect after a bounded stream ends;
 // submitting a completed call never starts another run on the server.
 const activeIds=plans.filter(active).map(p=>p.id).join(',');
 useEffect(()=>{
  const streams=activeIds.split(',').filter(Boolean).map(id=>{
   const stream=new EventSource(`/api/agent-v2/plans/${id}/events`);
   stream.addEventListener('workflow',event=>{try{replacePlan(JSON.parse((event as MessageEvent).data));}catch{setError('Could not read workflow progress. Check status to reconnect.');}});
   return stream;
  });return()=>streams.forEach(stream=>stream.close());
 },[activeIds,replacePlan]);
 const send=async()=>{
  if(lock.current||!text.trim()||plans.some(active))return;
  if(!planner){setError('Choose a registered Chat model to plan the workflow.');return;}
  lock.current=true;setWorking('Understanding your request…');setError('');
  try{
   const previous=plans.at(-1);const unfinished=previous&&!previous.superseded&&!previous.calls.some((call:Entity)=>call.status==='failed')&&previous.calls.some((call:Entity)=>call.status==='pending')?previous:null;
   const references=unfinished?.calls.flatMap((call:Entity)=>call.uploaded_document_ids||[])||[];
   const earlierRequest=unfinished?`${unfinished.request}\nPending tools from the unfinished plan: ${unfinished.calls.filter((call:Entity)=>call.status==='pending').map((call:Entity)=>call.tool).join(', ')}`.slice(0,12000):'';
   const plan=await api('/agent-v2/plans','POST',{text:text.trim(),earlier_request:earlierRequest,completed_tools:unfinished?.calls.filter((call:Entity)=>call.status==='completed').map((call:Entity)=>call.tool)||[],attached_filenames:files.map(file=>file.name),planner_model_id:planner,dataset_id:unfinished?.dataset_id||dataset,document_ids:references.length?references:unfinished?.document_ids||[],template_id:unfinished?.template_id||'',allow_external:external},undefined,true);
   setPlans(existing=>existing.map(item=>({...item,superseded:!active(item)&&item.calls.some((call:Entity)=>call.status==='pending')})));
   sessionStorage.setItem(key,plan.id);replacePlan(plan);setText('');speak(explainPlan(plan));
  }catch(e){setError(e instanceof Error?e.message:'The agent could not plan this request.');}
  finally{lock.current=false;setWorking('');}
 };
 const toggleMic=()=>{
  if(listening){recognition.current?.stop();return;}
  try{recognition.current=startSpeechInput(window as unknown as SpeechEnvironment,{text:transcript=>{if(mounted.current)setText(previous=>`${previous}${previous?' ':''}${transcript}`);},listening:value=>{if(mounted.current)setListening(value);},error:message=>{if(mounted.current)setError(message);}},navigator.language||'en-US');}catch(e){setError(e instanceof Error?e.message:'Could not start the microphone. Check browser permissions.');}
 };
 const chatModels=catalog.models.filter((m:Entity)=>m.enabled!==false&&m.capabilities.includes('chat'));
 return <section className="agent-v2" aria-label="Aegis agent V2 conversation">
  <header className="agent-v2-context">
   <label>Planning model<select aria-label="Agent planning model" value={planner} disabled={Boolean(working)||plans.some(active)} onChange={e=>setPlanner(e.target.value)}><option value="">Choose a Chat model</option>{chatModels.map((m:Entity)=><option key={m.id} value={m.id}>{m.name}</option>)}</select></label>
   <label>Dataset<select aria-label="Agent dataset" value={dataset} disabled={Boolean(working)||plans.some(active)} onChange={e=>setDataset(e.target.value)}><option value="">Let the agent ask</option>{catalog.datasets.map((d:Entity)=><option key={d.id} value={d.id}>{d.name}</option>)}</select></label>
   <button className="btn icon" aria-label={spoken?'Turn off spoken responses':'Turn on spoken responses'} title={speechSupported?'Spoken responses':'Speech playback unavailable in this browser'} aria-pressed={spoken} disabled={!speechSupported} onClick={()=>{setSpoken(!spoken);if(spoken)window.speechSynthesis.cancel();}}>{spoken?<Volume2 size={18}/>:<VolumeX size={18}/>}</button>
  </header>
  <div className="agent-v2-thread" aria-label="Agent conversation" tabIndex={0}>
   {!plans.length&&<div className="agent-v2-welcome"><Bot size={34}/><h2>What should we do?</h2><p>Upload, extract, or re-extract your documents. I’ll connect the steps and keep you informed.</p><div className="agent-v2-suggestions">{['Upload and extract documents','Extract fields from an existing document','Re-extract a document'].map(s=><button key={s} className="btn" onClick={()=>setText(s)}>{s}</button>)}</div><p className="small muted">Uses your registered Chat model to choose tools. Dataset mappings handle indexing and extraction.</p></div>}
   {plans.map(plan=>{
    const index=nextCall(plan);const call=index>=0?plan.calls[index]:null;
    const needInputs=call?.status==='pending'&&!plan.superseded;const uploaded=plan.calls.some((c:Entity)=>c.uploaded_document_ids?.length);
    const docs=catalog.documents.filter((d:Entity)=>d.parent_id===plan.dataset_id);
    const templates=catalog.templates.filter((t:Entity)=>!t.parent_id||t.parent_id===plan.dataset_id);
    return <article key={plan.id} className="agent-v2-exchange"><div className="agent-v2-user">{plan.request}</div><div className="agent-v2-response"><div className="agent-v2-speaker"><Bot size={18}/><strong>Aegis agent V2</strong><span>{plan.planner.name}</span></div><p>{explainPlan(plan)}</p>
     {plan.clarification?.length>0&&needInputs&&<p className="small muted">{plan.clarification.join(' · ')}</p>}
     {plan.calls.length>0&&<ol className="agent-v2-tools">{plan.calls.map((tool:Entity,i:number)=><li key={i} data-status={tool.status}><div className="agent-v2-tool-heading">{tool.status==='completed'?<CheckCircle2 size={17}/>:['waiting','running'].includes(tool.status)?<Loader2 size={17} className="animate-spin"/>:<span className="agent-v2-tool-number">{i+1}</span>}<strong>{tool.title}</strong><code>{tool.tool}</code><span>{tool.status==='pending'?(plan.calls.slice(0,i).some((c:Entity)=>c.status==='failed')?'Blocked by failed tool':i>index?'Waiting for previous tool':'Awaiting confirmation'):tool.status==='waiting'?'Processing':tool.status}</span></div>
      {tool.tool==='upload'&&tool.jobs?.length>0&&<UploadWorkflow call={tool}/>}
      {tool.tool!=='upload'&&tool.jobs?.map((job:Entity)=>tool.status==='completed'?<details className="agent-v2-completed-stages" key={job.id}><summary>All extraction stages completed</summary><JobProgress job={job}/></details>:<JobProgress key={job.id} job={job}/>)}
      {tool.error&&!tool.jobs?.some((job:Entity)=>job.error===tool.error)&&<p role="alert" className="agent-v2-error">{tool.error}</p>}
      {tool.result&&<div className="agent-v2-tool-result"><p>{tool.status==='failed'?'This tool stopped. Following tools will not run. Correct the file or service issue, then send a new request.':tool.status==='completed'&&tool.tool==='upload'?'Documents indexed. Their references are available to the next tool.':tool.result.message}</p>{tool.result.documents&&<details><summary>{tool.result.documents.length} document references</summary><ul>{tool.result.documents.map((d:Entity)=><li key={d.id}><FileText size={13}/>{d.name}<code>{d.id}</code></li>)}</ul></details>}{tool.status==='completed'&&tool.result.extraction_id&&<><details><summary>Extracted fields</summary><pre>{JSON.stringify(tool.result.data,null,2)}</pre></details><button className="btn" onClick={()=>onReview(tool.result.extraction_id)}>Review result and evidence</button></>}</div>}
     </li>)}</ol>}
     {needInputs&&<div className="agent-v2-details"><strong>A few details to continue</strong><label>Dataset<select aria-label="Workflow dataset" value={plan.dataset_id} disabled={uploaded} onChange={e=>update(plan.id,{dataset_id:e.target.value,document_ids:[],template_id:''})}><option value="">Choose a dataset</option>{catalog.datasets.map((d:Entity)=><option key={d.id} value={d.id}>{d.name}</option>)}</select></label>
      {call.tool!=='upload'&&!uploaded&&<label>Documents · choose up to 20<select aria-label="Workflow documents" multiple size={Math.min(4,Math.max(2,docs.length))} value={plan.document_ids} onChange={e=>update(plan.id,{document_ids:Array.from(e.target.selectedOptions).map(o=>o.value).slice(0,20)})}>{docs.map((d:Entity)=><option key={d.id} value={d.id}>{d.name}{docs.filter((other:Entity)=>other.name===d.name).length>1?` · ${new Date(d.created_at*1000).toLocaleString()}`:''}{d.status!=='ready'?` · ${d.status}`:''}</option>)}</select></label>}
      {plan.calls.some((c:Entity)=>c.tool!=='upload')&&<label>Prompt template<select aria-label="Workflow prompt template" value={plan.template_id} onChange={e=>update(plan.id,{template_id:e.target.value})}><option value="">Choose a template</option>{templates.map((t:Entity)=><option key={t.id} value={t.id}>{t.name}</option>)}</select></label>}
      {call.tool==='upload'&&<p className="small">{files.length?`${files.length} files attached below.`:'Attach the documents using the paperclip below.'}</p>}
      <p className="small muted">Review the selected dataset, files and template. This tool runs only after you confirm.</p>
      <button className="btn primary" disabled={Boolean(working)||!plan.dataset_id||(call.tool==='upload'?!files.length:(!uploaded&&!plan.document_ids.length)||!plan.template_id)} onClick={()=>void perform(plan,index)}>{call.tool==='upload'?'Confirm upload':call.tool==='reextract'?'Confirm re-extraction':'Confirm extraction'}</button>
     </div>}
     {active(plan)&&<button className="text-button" onClick={()=>void api(`/agent-v2/plans/${plan.id}`,'GET',undefined,undefined,true).then(replacePlan).catch(e=>setError(e.message))}>Check status</button>}
     {plan.superseded&&<p className="small muted">Replaced by your next request. Pending tools will not start.</p>}
     {plan.calls.length>0&&index<0&&<p className="agent-v2-done" role="status"><CheckCircle2 size={16}/>Workflow completed</p>}
    </div></article>;
   })}
   {working&&<p className="agent-v2-working" role="status"><Loader2 size={17} className="animate-spin"/>{working}</p>}
   {error&&<p className="agent-v2-error" role="alert">{error}</p>}<div ref={end}/>
  </div>
  <div className="agent-v2-composer">
   {files.length>0&&<div className="agent-v2-files">{files.map((file,index)=><span key={`${file.name}-${index}`}>{file.name}</span>)}<button className="text-button" onClick={()=>setFiles([])}>Clear files</button></div>}
   <div className="agent-v2-input"><input ref={fileInput} type="file" hidden multiple accept=".pdf,.docx,.txt" onChange={e=>{const selection=Array.from(e.target.files||[]);if(selection.length>20){setError('Attach at most 20 documents.');return;}setFiles(selection);e.target.value='';}}/><button className="btn icon" aria-label="Attach documents for agent" title="Attach PDF, DOCX or TXT" disabled={Boolean(working)||plans.some(active)} onClick={()=>fileInput.current?.click()}><Paperclip size={19}/></button><textarea aria-label="Message Aegis agent V2" placeholder="Tell me what to do with your documents…" value={text} rows={2} onChange={e=>setText(e.target.value)} onKeyDown={e=>{if(e.key==='Enter'&&!e.shiftKey){e.preventDefault();void send();}}}/><button className={`btn icon${listening?' primary':''}`} aria-label={listening?'Stop listening':'Speak your request'} title={voiceSupported?'Speech input':'Speech input unavailable in this browser'} disabled={!voiceSupported||Boolean(working)} onClick={toggleMic}><Mic size={18}/></button><button className="btn primary icon" aria-label="Send agent request" disabled={!text.trim()||Boolean(working)||plans.some(active)} onClick={()=>void send()}><Send size={18}/></button></div>
   <div className="agent-v2-footer"><span>PDF, DOCX, TXT · up to 20 files · general documents</span><details><summary>Privacy & cloud consent</summary><p>Files use your dataset’s storage, embedding and extraction models. Workflow requests and results are saved in your workspace. Browser speech recognition may send audio to its speech service; voice is optional and text remains available.</p><label><input type="checkbox" checked={external} onChange={e=>setExternal(e.target.checked)}/>Allow this request, catalog names and selected document data to reach configured external providers</label></details></div>
  </div>
 </section>;
}

function UploadWorkflow({call}:{call:Entity}) {
 const documents=call.result?.documents||[];
 const items:UploadProgressItem[]=documents.map((document:Entity)=>{
  const job=call.jobs.find((j:Entity)=>j.target_id===document.id);
  const ready=job?.status==='completed';const failed=['failed','cancelled'].includes(job?.status);
  return {id:document.id,name:document.name,status:'submitted',document:{id:document.id,status:ready?'ready':failed?'failed':'processing'},job,ready,failed,processing:!ready&&!failed,error:job?.error};
 });
 const statuses=<ul className="agent-v2-document-status">{items.map(item=><li key={item.id}><span>{item.name}</span><span>{currentUploadStep(item)}</span>{item.error&&<p role="alert">{item.error}</p>}</li>)}</ul>;
 return <><BatchProgress items={items} compact/>{call.status==='completed'?<details className="agent-v2-completed-stages"><summary>{items.length} documents indexed · view statuses</summary>{statuses}</details>:statuses}</>;
}
