"use client";
import {ActionButton} from "./action-button";
import {openDatasetEditor} from './manage-dataset';
import {useEffect,useRef,useState} from 'react';
import {Database,Loader2,X} from 'lucide-react';
import {WorkflowStepper} from './workflow-stepper';
import {useAgentConsent} from './agent-consent';
import {onboardingModelSelection} from './onboarding-draft';
import './agent-onboarding.css';

type Entity=Record<string,any>;
type Api=(path:string,method?:string,body?:unknown,signal?:AbortSignal,quiet?:boolean)=>Promise<any>;
const roles=[['embedding_model_id','embedding','Embedding model'],['default_chat_model_id','chat','Chat model'],['default_extraction_model_id','extraction','Extraction model']];
export function AgentOnboarding({api,models,defaults,proposal={},storageKey,planId='',workflowId='',initialDocuments=[],initialPrompt,onBusy,onReady,onUse,onClose,onReview,datasetOnly=false,onCompleted,onEdit}:{api:Api;models:Entity[];defaults?:Entity;proposal?:Entity;storageKey:string;planId?:string;workflowId?:string;initialDocuments?:File[];initialPrompt?:Entity;onBusy:(busy:boolean)=>void;onReady:()=>void;onUse:(id:string)=>void;onClose?:(completed:boolean)=>void;onReview?:(id:string)=>void;datasetOnly?:boolean;onEdit?:(datasetId:string)=>void;onCompleted?:(dataset:Entity)=>void}){
 const [name,setName]=useState<string>(proposal.name||'');const [description,setDescription]=useState<string>(proposal.description||'');
 const [selection,setSelection]=useState<Record<string,string>>(()=>onboardingModelSelection(models,roles,defaults));
 const [workflow,setWorkflow]=useState<Entity|null>(null);const [confirmed,setConfirmed]=useState<Entity|null>(null);const [busy,setBusy]=useState(false);const [loading,setLoading]=useState(true);const [error,setError]=useState('');
 const [process,setProcess]=useState(!datasetOnly&&Boolean(proposal.process_documents));const [files,setFiles]=useState<File[]>(initialDocuments);const [promptName,setPromptName]=useState(initialPrompt?.fileName||'extraction-prompt.json');const [promptText,setPromptText]=useState(initialPrompt?.schema?JSON.stringify(initialPrompt.schema,null,2):'');const [instructions,setInstructions]=useState(initialPrompt?.instructions||'');const [mode,setMode]=useState('independent');const [strategy,setStrategy]=useState('records');const consent=useAgentConsent(api);
 const request=useRef('');const live=useRef(true);const running=useRef(false);const busyCallback=useRef(onBusy);busyCallback.current=onBusy;
 useEffect(()=>{live.current=true;const id=workflowId||sessionStorage.getItem(storageKey);
  const receipt=sessionStorage.getItem(storageKey+'-request');if(receipt){try{const value=JSON.parse(receipt);setConfirmed(value);request.current=value.request_id;setName(value.name);setDescription(value.description);setSelection(Object.fromEntries(roles.map(([key])=>[key,value[key]])));}catch{sessionStorage.removeItem(storageKey+'-request');}}
  if(id)void api(`/agent-v2/onboarding/${id}`,'GET',undefined,undefined,true).then(value=>{if(live.current){setWorkflow(value);setName(value.name);setDescription(value.description);setSelection(Object.fromEntries(roles.map(([key])=>[key,value[key]])));}}).catch(e=>{if(live.current)setError(e.message);}).finally(()=>{if(live.current)setLoading(false);});
  else setLoading(false);
  return ()=>{live.current=false;busyCallback.current(false);};
 },[api,storageKey,workflowId]);
 useEffect(()=>{
  if(workflow||confirmed||busy)return;
  setSelection(previous=>{const next=onboardingModelSelection(models,roles,defaults,previous);return roles.every(([key])=>next[key]===previous[key])?previous:next;});
  setName(value=>value||proposal.name||'');setDescription(value=>value||proposal.description||'');
 },[models,defaults,workflow,confirmed,busy,proposal.name,proposal.description]);
 const completionNotified=useRef(false);
 useEffect(()=>{if(datasetOnly&&workflow?.status==='completed'&&workflow.dataset&&!completionNotified.current){completionNotified.current=true;onCompleted?.(workflow.dataset);}},[datasetOnly,workflow?.status,workflow?.id,onCompleted]);
 const execute=async()=>{
  if(running.current)return;running.current=true;setBusy(true);onBusy(true);setError('');
  let accepted=Boolean(workflow);
  try{
   let external=false;
   if(!workflow&&(confirmed?.processing||!confirmed&&process)){const permission=await consent.request({roles:['embedding','extraction'],model_ids:{embedding:confirmed?.embedding_model_id||selection.embedding_model_id,extraction:confirmed?.default_extraction_model_id||selection.default_extraction_model_id}});if(!permission)return;external=permission.required;}
   request.current ||= crypto.randomUUID();
   let processing:Entity|null=null;
   if(!confirmed&&!workflow&&process){
    if(!files.length||files.length>20)throw new Error('Choose 1 to 20 documents.');
    let parsed:Entity;try{parsed=JSON.parse(promptText);}catch{throw new Error('Enter valid prompt JSON or upload a prompt .json file.');}
    const schema=parsed?.schema??parsed;if(!schema||Array.isArray(schema)||typeof schema!=='object')throw new Error('The prompt must contain a JSON Schema object.');
    const documents=await Promise.all(files.map(async file=>{
     const digest=new Uint8Array(await crypto.subtle.digest('SHA-256',await file.arrayBuffer()));
     return {name:file.name,size:file.size,sha256:Array.from(digest).map(b=>b.toString(16).padStart(2,'0')).join('')};
    }));
    processing={prompt_name:promptName,schema,instructions:instructions||parsed.instructions||'',extraction_mode:mode,merge_strategy:strategy,allow_external:external,documents};
   }
   const body=confirmed?(workflow?confirmed:{...confirmed,processing:confirmed.processing?{...confirmed.processing,allow_external:external}:null}):{request_id:request.current,name:name.trim(),description,...selection,plan_id:planId,processing};
   sessionStorage.setItem(storageKey+'-request',JSON.stringify(body));setConfirmed(body);
   let value=workflow||await api('/agent-v2/onboarding','POST',body,undefined,true);
   accepted=true;
   sessionStorage.setItem(storageKey,value.id);if(live.current)setWorkflow(value);
   if(value.processing&&!value.files_saved){
    if(!files.length)throw new Error('Reattach the confirmed documents to resume. The dataset setup and prompt are saved.');
    const form=new FormData();files.forEach(file=>form.append('files',file));
    value=await api(`/agent-v2/onboarding/${value.id}/files`,'POST',form,undefined,true);if(live.current)setWorkflow(value);
   }
   // The worker owns confirmed execution. The browser observes persisted
   // progress; only an explicit retry changes a failed workflow.
   if(value.status==='failed')value=await api(`/agent-v2/onboarding/${value.id}/advance`,'POST',{retry:true},undefined,true);
   while(live.current&&value.status!=='completed'&&value.status!=='failed'){
    if(typeof document!=='undefined'&&document.visibilityState==='hidden'){await new Promise(resolve=>setTimeout(resolve,10000));continue;}
    value=await api(`/agent-v2/onboarding/${value.id}`,'GET',undefined,undefined,true);
    if(live.current)setWorkflow(value);
    if(value.status==='failed')break;
    if(value.status!=='completed'&&value.status!=='failed')await new Promise(resolve=>setTimeout(resolve,4000));
   }
   if(value.status==='completed'&&live.current)onReady();
  }catch(e){if(live.current){setError(e instanceof Error?e.message:'Unable to finish onboarding. Retry the saved setup.');
   // A definitive validation/access rejection created no workflow. Let the
   // user correct the draft; uncertain network errors retain its receipt.
   if(!accepted&&[400,403,404,422].includes((e as Entity)?.status)){setConfirmed(null);request.current='';sessionStorage.removeItem(storageKey+'-request');}
  }}
  finally{running.current=false;if(live.current){setBusy(false);onBusy(false);}}
 };
 const complete=workflow?.status==='completed';const frozen=busy||Boolean(workflow)||Boolean(confirmed);const full=workflow?Boolean(workflow.processing):confirmed?Boolean(confirmed.processing):process;
 const needsFiles=Boolean((workflow?.processing||confirmed?.processing)&&!workflow?.files_saved);
 const steps=workflow?.steps||(full?['Validate setup','Create dataset','Map models','Save prompt','Upload documents','Index documents','Extract fields','Publish knowledge','Ready for review']:['Validate setup','Create dataset','Map models','Publish knowledge','Ready for documents']).map((label,i)=>({id:String(i),label,status:'pending'}));
 const importPrompt=async(file?:File)=>{if(!file)return;try{if(!/\.json$/i.test(file.name)||!file.size||file.size>1024*1024)throw new Error('Choose a non-empty prompt .json file of 1 MB or smaller.');const value=JSON.parse((await file.text()).replace(/^\uFEFF/,''));setPromptName(file.name);setPromptText(JSON.stringify(value.schema??value,null,2));setInstructions(value.instructions||'');setError('');}catch(e){setError(e instanceof Error?e.message:'Unable to read prompt JSON.');}};
 return <section className="agent-onboarding" aria-label="Dataset onboarding workflow">
  {consent.popup}
  <header><Database size={20}/><strong>{datasetOnly?'New dataset':full?'Onboard & Extract Agent':'Onboard Agent'}</strong>{!datasetOnly&&<span className="small muted">{full?'Dataset setup and processing':'Dataset setup'}</span>}{onClose&&<button title="Close dataset onboarding" className="btn icon" aria-label="Close dataset onboarding" disabled={busy} onClick={()=>onClose(Boolean(complete))}><X size={16}/></button>}</header>
  {(!datasetOnly||frozen)&&<WorkflowStepper label="Dataset onboarding steps" steps={steps} compact/>}
  {loading?<p role="status">Restoring saved setup…</p>:<>
   {frozen&&workflow?<dl className="agent-onboarding-receipt"><div><dt>Dataset</dt><dd>{workflow!.name}</dd></div>{roles.map(([key,,label])=><div key={key}><dt>{label}</dt><dd>{workflow!.models?.[key]?.name||models.find(m=>m.id===selection[key])?.name||'Saved model'}</dd></div>)}</dl>:<><div className="agent-onboarding-fields"><label>Dataset name<input aria-label="Onboarding dataset name" maxLength={200} value={name} disabled={frozen} onChange={e=>setName(e.target.value)} placeholder="Name your dataset"/></label><label>Description (optional)<input aria-label="Onboarding dataset description" maxLength={10000} value={description} disabled={frozen} onChange={e=>setDescription(e.target.value)}/></label></div>
   <details className="agent-onboarding-model-options" open={datasetOnly||roles.some(([key])=>!selection[key])}><summary>{roles.every(([key])=>selection[key])?'Default models selected':'Choose model mappings'}<span>{roles.filter(([key])=>selection[key]).length} / 3 roles</span></summary><div className="agent-onboarding-models">{roles.map(([key,cap,label])=>{
    const eligible=models.filter(m=>m.enabled&&m.credential_configured&&m.capabilities.includes(cap));
    return <label key={key}>{label}<select aria-label={`Onboarding ${label.toLowerCase()}`} value={selection[key]||''} disabled={frozen} onChange={e=>setSelection(previous=>({...previous,[key]:e.target.value}))}><option value="">Choose a registered model</option>{eligible.map(m=><option key={m.id} value={m.id}>{m.name} · {m.provider_model}</option>)}</select>{!eligible.length&&<span className="small muted">Register an enabled {cap} model with its connection configured in Model Registration first.</span>}</label>;
   })}</div></details></>}
   {!datasetOnly&&!frozen&&<label className="agent-onboarding-toggle"><input type="checkbox" aria-label="Upload documents and run extraction" checked={process} onChange={e=>setProcess(e.target.checked)}/>Upload documents, set up a prompt and run extraction</label>}
   {full&&!frozen&&<div className="agent-onboarding-processing">
    <label>Documents<input type="file" aria-label="Onboarding documents" multiple accept=".pdf,.docx,.txt,.json" disabled={busy} onChange={e=>setFiles(Array.from(e.target.files||[]))}/><span className="small muted">PDF, DOCX, TXT or JSON · up to 20 files. Prompt JSON belongs in the separate prompt input below.</span></label>
    {files.length>0&&<ul className="agent-onboarding-files">{files.map((file,i)=><li key={i}>{file.name} · {Math.ceil(file.size/1024)} KB</li>)}</ul>}
    <div className="agent-onboarding-fields"><label>Prompt filename<input aria-label="Onboarding prompt filename" value={promptName} maxLength={200} onChange={e=>setPromptName(e.target.value)}/></label><label>Upload prompt JSON<input type="file" aria-label="Onboarding prompt JSON file" accept=".json" onChange={e=>void importPrompt(e.target.files?.[0])}/></label></div>
    <label>Prompt JSON Schema<textarea aria-label="Onboarding prompt schema" rows={5} value={promptText} placeholder={'{"type":"object","properties":{},"required":[],"additionalProperties":false}'} onChange={e=>setPromptText(e.target.value)}/></label>
    <label>Extraction instructions <span className="small muted">(optional)</span><textarea aria-label="Onboarding prompt instructions" rows={2} maxLength={12000} value={instructions} onChange={e=>setInstructions(e.target.value)}/></label>
    <div className="agent-onboarding-fields"><label>Extraction mode<select aria-label="Onboarding extraction mode" value={mode} onChange={e=>setMode(e.target.value)}><option value="independent">Extract each document independently</option><option value="merge">Merge into one result</option></select></label>{mode==='merge'&&<label>Merged result<select aria-label="Onboarding merge strategy" value={strategy} onChange={e=>setStrategy(e.target.value)}><option value="records">Separate records in one result</option><option value="single">One combined record</option></select></label>}</div>

   </div>}
   {needsFiles&&<label>Reattach confirmed documents<input type="file" aria-label="Reattach onboarding documents" multiple accept=".pdf,.docx,.txt,.json" disabled={busy} onChange={e=>setFiles(Array.from(e.target.files||[]))}/></label>}
   {workflow?.processing&&<p className="small muted">Prompt: {workflow.processing.prompt_name} · {workflow.processing.documents.map((d:Entity)=>d.name).join(', ')} · {workflow.processing.extraction_mode==='merge'?'Merged result':'Independent results'}</p>}
   <p className="small muted" role="status">{complete?(full?'Documents are indexed and extraction results are ready for review.':'Dataset and model mappings are saved.'):busy?(workflow?.steps?.find((s:Entity)=>s.status==='running')?.label||'Saving confirmed setup…'):full?'Confirm the dataset, documents and prompt to start processing.':'Confirm to create this dataset and map its models. Upload and extraction can be requested later.'}</p>
   {(error||workflow?.error)&&<p className="agent-onboarding-error" role="alert">{error||workflow?.error}</p>}
   {workflow?.dataset_id&&!complete&&<p className="small muted">Dataset creation is saved. Resume or retry will reuse it.</p>}
   {complete&&workflow?.vector_publication&&<p className="small" role="status">Knowledge updated · {workflow.vector_publication.provider==='oracle'?'OCI':workflow.vector_publication.provider==='qdrant'?'Local Qdrant':'Local'} · {workflow.vector_publication.verified_vectors} verified vectors{workflow.vector_publication.parquet_files?.length>0?' · JSON and Parquet results saved':''}.</p>}
   <footer>{complete?<><ActionButton className="btn primary" onClick={()=>onUse(workflow!.dataset_id)} label="Use dataset in Aegis Agent" action="chat"/><ActionButton className="btn" onClick={()=>onEdit?onEdit(workflow!.dataset_id):openDatasetEditor(workflow!.dataset_id)} label="Edit dataset" action="edit" showLabel/></>:<button className="btn primary" disabled={busy||!name.trim()||roles.some(([key])=>!selection[key])||(!frozen&&full&&(!files.length||!promptText.trim()))||(needsFiles&&!files.length)} onClick={()=>void execute()}>{busy?<><Loader2 size={15} className="animate-spin"/>Onboarding dataset…</>:workflow?.status==='failed'?'Retry onboarding workflow':workflow||confirmed?'Resume onboarding workflow':datasetOnly?'Create dataset':'Confirm dataset onboarding'}</button>}{complete&&onClose&&<ActionButton className="btn" onClick={()=>onClose(true)} label="Done" action="close"/>}</footer>
   {workflow?.results?.length>0&&<div className="agent-onboarding-results">{workflow!.results.map((result:Entity)=><div key={result.id}><span>{result.name} · Ready for review</span>{onReview&&<ActionButton className="btn" onClick={()=>onReview(result.id)} label="Review" action="review"/>}</div>)}</div>}
  </>}
 </section>;
}
