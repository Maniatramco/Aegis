"use client";
import {useCallback, useEffect, useRef, useState,type DragEvent} from 'react';
import {History,Square, Plus, Bot, CheckCircle2, Loader2, Mic, ArrowUp, Volume2, VolumeX,X,FileText,UploadCloud} from 'lucide-react';
import {isFileDrag,mergeAgentAttachments,attachmentSize,attachmentKey,isJsonAttachment} from './agent-attachments';
import {readPromptUpload,type PromptUpload} from './prompt-upload';
import {PromptUploadPreview} from './prompt-upload-preview';
import {promptSelections,restoreSavedPrompt,rememberSavedPrompt} from './agent-prompt-selection';
import {AgentDocumentFilter} from './agent-document-filter';
import {documentMention,documentOptionLabel,matchingDocuments,readyDatasetDocuments,eligibleAgentModels} from './agent-document-selection';
import {readChatStream} from './chat-stream';
import {AgentChatAnswer,conversationExchanges} from './agent-v2-chat';
import {BatchProgress} from './batch-progress';
import {AgentJobProgress,AgentResult} from './agent-v2-output';
import {currentUploadStep, type UploadProgressItem} from './batch-workflow';
import './agent-v2.css';
import {speechCapabilities,startSpeechInput,speakResponse,type SpeechEnvironment} from './agent-voice';

type Entity=Record<string,any>;
type AttachedPrompt=PromptUpload&{fileKey:string;datasetId:string;savedId?:string};
type Api=(path:string,method?:string,body?:unknown,signal?:AbortSignal,quiet?:boolean)=>Promise<any>;
const active=(plan:Entity)=>plan.calls.some((call:Entity)=>['running','waiting'].includes(call.status));
const nextCall=(plan:Entity)=>plan.calls.findIndex((call:Entity)=>call.status!=='completed');
export const explainPlan=(plan:Entity)=>{
 if(!plan.calls.length)return plan.explanation?.trim()||'I can help you upload documents, extract fields, or re-extract saved documents. What would you like to do?';
 const labels:Record<string,string>={upload:'Upload documents',extract:'Extract fields',reextract:'Re-extract fields'};
 return `Proposed workflow: ${plan.calls.map((call:Entity)=>labels[call.tool]).join(' → ')}. Review the details and confirm each tool before it runs.${plan.calls.some((call:Entity)=>call.tool==='upload')&&plan.calls.some((call:Entity)=>call.tool==='extract')?' Extraction will use the uploaded references after indexing finishes.':''}${plan.calls.some((call:Entity)=>call.tool==='reextract')?' Earlier extraction results will be retained.':''}`;
};

export function AgentV2({api,stream,username,onJobs,onVisibleJobs,onReview,onPromptSaved,maxUploadMb=25}:{api:Api;stream:(path:string,body:unknown,signal:AbortSignal)=>Promise<Response>;username:string;onJobs:(jobs:Entity[])=>void;onVisibleJobs:(ids:string[])=>void;onReview:(id:string)=>void;onPromptSaved?:(template:Entity)=>void;maxUploadMb?:number}) {
 const [catalog,setCatalog]=useState<Entity>({datasets:[],documents:[],templates:[],models:[]});
 const [plans,setPlans]=useState<Entity[]>([]);
 const [history,setHistory]=useState<Entity[]>([]); const [historyOpen,setHistoryOpen]=useState(false);
 const [documents,setDocuments]=useState<string[]>([]); const conversations=useRef<Record<string,string>>({}); const answerController=useRef<AbortController|null>(null);
 const [dataset,setDataset]=useState(''); const [planner,setPlanner]=useState('');
 const [caret,setCaret]=useState(0);const [mentionClosed,setMentionClosed]=useState(false);const [mentionIndex,setMentionIndex]=useState(0);
 const [text,setText]=useState(''); const [files,setFiles]=useState<File[]>([]);
 const [jsonDocuments,setJsonDocuments]=useState<Record<string,boolean>>({});
 const [attachmentErrors,setAttachmentErrors]=useState<Record<string,string>>({});
 const [savedPromptId,setSavedPromptId]=useState('');const catalogLoaded=useRef(false);
 const [promptPreview,setPromptPreview]=useState<AttachedPrompt|null>(null);const [promptAttachment,setPromptAttachment]=useState<AttachedPrompt|null>(null);
 const [promptNotice,setPromptNotice]=useState('');const promptReadToken=useRef(0);
 const [dragging,setDragging]=useState(false);const dragDepth=useRef(0);
 const [working,setWorking]=useState(''); const [error,setError]=useState(''); const [pendingRequest,setPendingRequest]=useState('');
 const [external,setExternal]=useState(false); const [spoken,setSpoken]=useState(false);
 const [voiceSupported,setVoiceSupported]=useState(false); const [speechSupported,setSpeechSupported]=useState(false); const [listening,setListening]=useState(false);
 const fileInput=useRef<HTMLInputElement>(null); const end=useRef<HTMLDivElement>(null); const composer=useRef<HTMLTextAreaElement>(null);
 const lock=useRef(false); const mounted=useRef(true); const recognition=useRef<any>(null);
 const onJobsRef=useRef(onJobs); onJobsRef.current=onJobs;
 const onVisibleJobsRef=useRef(onVisibleJobs); onVisibleJobsRef.current=onVisibleJobs;
 const spokenRef=useRef(spoken); spokenRef.current=spoken;
 const announced=useRef(new Set<string>());
 const key=`aegis-agent-v2:${username}`;
 const savedPrompt=catalog.templates.find((template:Entity)=>template.id===savedPromptId&&(!template.parent_id||template.parent_id===dataset));
 const clearSavedPrompt=()=>{rememberSavedPrompt(sessionStorage,key+'-prompts',dataset,'');setSavedPromptId('');setPromptNotice('');};
 const attachmentsBlocked=Boolean(working)||plans.some(active)||Boolean(promptPreview);
 const documentFiles=files.filter(file=>!isJsonAttachment(file)||jsonDocuments[attachmentKey(file)]);
 const unresolvedJson=files.filter(file=>isJsonAttachment(file)&&!jsonDocuments[attachmentKey(file)]&&promptAttachment?.fileKey!==attachmentKey(file));
 const removeAttachment=(file:File)=>{
  const id=attachmentKey(file);setError('');setFiles(previous=>previous.filter(current=>attachmentKey(current)!==id));
  setJsonDocuments(previous=>{const next={...previous};delete next[id];return next;});
  setAttachmentErrors(previous=>{const next={...previous};delete next[id];return next;});
  if(promptAttachment?.fileKey===id&&promptAttachment.savedId===savedPromptId)clearSavedPrompt();
  if(promptAttachment?.fileKey===id){setPromptAttachment(null);setPromptNotice('');}
 };
 const cancelPrompt=()=>{promptReadToken.current++;setPromptPreview(null);};
 const chooseJsonDocument=(file:File)=>{
  const id=attachmentKey(file);setJsonDocuments(previous=>({...previous,[id]:true}));setError('');
  setAttachmentErrors(previous=>{const next={...previous};delete next[id];return next;});
  if(promptAttachment?.fileKey===id&&promptAttachment.savedId===savedPromptId)clearSavedPrompt();
  if(promptAttachment?.fileKey===id){setPromptAttachment(null);setPromptNotice('');}
 };
 const chooseJsonPrompt=async(file:File)=>{
  if(attachmentsBlocked)return;
  if(!dataset){setError('Choose a dataset before attaching a prompt template.');return;}
  if(promptAttachment&&promptAttachment.fileKey!==attachmentKey(file)){setError('Remove the current prompt template before choosing another. Use one prompt per message.');return;}
  const token=++promptReadToken.current;lock.current=true;setWorking('Validating prompt.');setError('');
  setAttachmentErrors(previous=>{const next={...previous};delete next[attachmentKey(file)];return next;});
  try{
   const parsed=await readPromptUpload(file);
   const validation=await api('/templates/validate','POST',{name:parsed.name,schema:parsed.schema,dataset_id:dataset,source_filename:parsed.fileName},undefined,true);
   if(mounted.current&&token===promptReadToken.current)setPromptPreview({...parsed,replacesExisting:Boolean(validation.existing_template_id),fileKey:attachmentKey(file),datasetId:dataset,savedId:promptAttachment?.savedId});
  }catch(e){if(mounted.current&&token===promptReadToken.current)setAttachmentErrors(previous=>({...previous,[attachmentKey(file)]:`${file.name}: ${e instanceof Error?e.message:'The prompt could not be validated.'}`}));}
  finally{lock.current=false;if(mounted.current)setWorking('');}
 };
 const confirmPrompt=()=>{
  if(!promptPreview||promptPreview.datasetId!==dataset)return;
  setPromptAttachment(promptPreview);setJsonDocuments(previous=>{const next={...previous};delete next[promptPreview.fileKey];return next;});setPromptPreview(null);
  setPromptNotice('Prompt confirmed. Send to save it for this dataset; extraction still requires confirmation.');setError('');
 };
 const attachFiles=(incoming:File[])=>{
  if(attachmentsBlocked){setError('Wait for the current workflow to finish before attaching documents.');return;}
  const result=mergeAgentAttachments(files,incoming,maxUploadMb);setError(result.error);
  if(result.error)return;setFiles(result.files);setMentionClosed(true);composer.current?.focus();
 };
 const onFileDragEnter=(event:DragEvent<HTMLElement>)=>{if(!isFileDrag(Array.from(event.dataTransfer.types)))return;event.preventDefault();event.stopPropagation();dragDepth.current++;setDragging(true);};
 const onFileDragOver=(event:DragEvent<HTMLElement>)=>{if(!isFileDrag(Array.from(event.dataTransfer.types)))return;event.preventDefault();event.stopPropagation();event.dataTransfer.dropEffect=attachmentsBlocked?'none':'copy';};
 const onFileDragLeave=(event:DragEvent<HTMLElement>)=>{if(!dragDepth.current)return;event.preventDefault();event.stopPropagation();dragDepth.current=Math.max(0,dragDepth.current-1);if(!dragDepth.current)setDragging(false);};
 const onFileDrop=(event:DragEvent<HTMLElement>)=>{
  if(!isFileDrag(Array.from(event.dataTransfer.types)))return;event.preventDefault();event.stopPropagation();dragDepth.current=0;setDragging(false);
  const folder=Array.from(event.dataTransfer.items||[]).some(item=>item.kind==='file'&&item.webkitGetAsEntry?.()?.isDirectory);
  if(folder){setError('Folders are not supported. Drop PDF, DOCX, TXT or JSON files instead.');return;}
  attachFiles(Array.from(event.dataTransfer.files));
 };
 useEffect(()=>{
  const reset=()=>{dragDepth.current=0;setDragging(false);};
  const protect=(event:globalThis.DragEvent)=>{if(isFileDrag(Array.from(event.dataTransfer?.types||[])))event.preventDefault();};
  const outsideDrop=(event:globalThis.DragEvent)=>{protect(event);reset();};
  window.addEventListener('dragover',protect);window.addEventListener('drop',outsideDrop);window.addEventListener('dragend',reset);window.addEventListener('blur',reset);
  return()=>{window.removeEventListener('dragover',protect);window.removeEventListener('drop',outsideDrop);window.removeEventListener('dragend',reset);window.removeEventListener('blur',reset);};
 },[]);
 const restoreConversation=useCallback((conversation:Entity)=>{
  const exchanges=conversationExchanges(conversation);setPlans(exchanges);setDataset(conversation.dataset_id||'');setDocuments(conversation.document_ids||[]);
  const latest=exchanges.at(-1);if(latest?.planner.id)setPlanner(latest.planner.id);
  conversations.current[conversation.mode==='general'?'general':conversation.dataset_id]=conversation.id;
 },[]);
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
 const loadCatalog=useCallback(async()=>{const result=await api('/agent-v2/catalog','GET',undefined,undefined,true);if(mounted.current){catalogLoaded.current=true;setCatalog(result);}return result;},[api]);
 useEffect(()=>{if(!catalogLoaded.current)return;const restored=restoreSavedPrompt(sessionStorage.getItem(key+'-prompts'),catalog.templates,dataset);setSavedPromptId(restored?.id||'');},[catalog,dataset,key]);
 useEffect(()=>{
  mounted.current=true;let cancelled=false;
  const capabilities=speechCapabilities(window as unknown as SpeechEnvironment);setVoiceSupported(capabilities.input);setSpeechSupported(capabilities.output);
  void loadCatalog().then(async(result)=>{
   if(cancelled)return;
   const local=result.models.filter((m:Entity)=>m.enabled!==false&&m.capabilities.includes('chat'));
   if(local.length===1)setPlanner(local[0].id);
   const opened=sessionStorage.getItem(key+'-conversation');if(opened){const conversation=await api(`/conversations/${opened}`,'GET',undefined,undefined,true);if(cancelled)return;restoreConversation(conversation);}
   const saved=sessionStorage.getItem(key+'-history'); const ids:string[]=saved?JSON.parse(saved):[sessionStorage.getItem(key)].filter(Boolean);
   let lastPlan:Entity|undefined;
   for(const id of ids){const plan=await api(`/agent-v2/plans/${id}`,'GET',undefined,undefined,true);if(cancelled)return;lastPlan=plan;replacePlan(plan);if(plan.conversation_id)conversations.current[plan.answer_mode==='general'?'general':plan.dataset_id]=plan.conversation_id;setDataset(plan.dataset_id);setPlanner(plan.planner.id);setDocuments(plan.document_ids||[]);}
   if(lastPlan?.template_id&&promptSelections(sessionStorage.getItem(key+'-prompts'))[lastPlan.dataset_id]===undefined){rememberSavedPrompt(sessionStorage,key+'-prompts',lastPlan.dataset_id,lastPlan.template_id);setSavedPromptId(restoreSavedPrompt(sessionStorage.getItem(key+'-prompts'),result.templates,lastPlan.dataset_id)?.id||'');}
   const preferred=sessionStorage.getItem(key+'-dataset');
   if(preferred!==null&&(preferred===''||result.datasets.some((item:Entity)=>item.id===preferred))){setDataset(preferred);setDocuments(previous=>previous.filter(id=>result.documents.some((item:Entity)=>item.id===id&&item.parent_id===preferred)));}
  }).catch(e=>{if(!cancelled)setError(e.message);});
  return()=>{cancelled=true;mounted.current=false;answerController.current?.abort();recognition.current?.abort();if('speechSynthesis' in window)window.speechSynthesis.cancel();};
 },[api,key,loadCatalog,replacePlan,restoreConversation]);
 useEffect(()=>{onVisibleJobs(plans.flatMap(plan=>plan.calls.flatMap((call:Entity)=>call.status==='waiting'?(call.job_ids||[]):[])));},[plans,onVisibleJobs]);
 const completedUploads=plans.filter(plan=>plan.calls.some((call:Entity)=>call.tool==='upload'&&call.status==='completed')).map(plan=>plan.id).join(',');
 useEffect(()=>{if(completedUploads)void loadCatalog().catch(e=>{if(mounted.current)setError(e.message);});},[completedUploads,loadCatalog]);
 useEffect(()=>()=>onVisibleJobs([]),[onVisibleJobs]);
 useEffect(()=>{end.current?.scrollIntoView({block:'nearest',behavior:'smooth'});},[plans,working,error,files.length]);
 useEffect(()=>{if(composer.current){composer.current.style.height='auto';composer.current.style.height=`${Math.min(composer.current.scrollHeight,160)}px`;}},[text]);
 const update=useCallback((id:string,changes:Entity)=>setPlans(previous=>previous.map(plan=>plan.id===id?{...plan,...changes}:plan)),[]);
 const perform=useCallback(async(plan:Entity,index:number)=>{
  if(lock.current)return; lock.current=true;
  const call=plan.calls[index];setWorking(call.tool==='upload'?'Uploading documents…':'Starting extraction…');setError('');
  try {
   let result;
   if(call.tool==='upload'){
    if(!documentFiles.length||unresolvedJson.length)throw new Error('Choose how to use each JSON attachment before uploading documents.');
    const data=new FormData();for(const file of documentFiles)data.append('files',file);data.append('dataset_id',plan.dataset_id);data.append('allow_external',String(external));data.append('confirmed','true');
    result=await api(`/agent-v2/plans/${plan.id}/calls/${index}/upload`,'POST',data,undefined,true);setFiles(previous=>previous.filter(file=>promptAttachment?.fileKey===attachmentKey(file)));setJsonDocuments({});
   } else result=await api(`/agent-v2/plans/${plan.id}/calls/${index}`,'POST',{dataset_id:plan.dataset_id,document_ids:plan.document_ids,template_id:plan.template_id,allow_external:external,confirmed:true},undefined,true);
   replacePlan(result);
  } catch(e){if(mounted.current)setError(e instanceof Error?e.message:'The action could not finish.');}
  finally{lock.current=false;if(mounted.current)setWorking('');}
 },[api,external,documentFiles,unresolvedJson.length,promptAttachment,replacePlan]);
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
  if(lock.current||promptPreview||(!text.trim()&&!files.length)||plans.some(active))return;
  if(unresolvedJson.length){setError('Is each JSON attachment a prompt template or a document? Choose below its filename.');return;}
  if(promptAttachment&&promptAttachment.datasetId!==dataset){setError('Attach the prompt again for the selected dataset.');return;}
  const savePromptOnly=Boolean(promptAttachment)&&!text.trim()&&!documentFiles.length;
  if(!savePromptOnly&&!planner){setError('Choose an Agent Model to continue.');return;}
  const request=text.trim()||(documentFiles.length?'Upload the attached documents.':'');let answering=false;lock.current=true;setPendingRequest(request);setText('');setWorking(promptAttachment&&!promptAttachment.savedId?'Saving prompt.':'Thinking…');setError('');
  try{
   let attachedTemplateId=promptAttachment?.savedId||savedPrompt?.id||'';
   if(promptAttachment&&!promptAttachment.savedId){
     const imported=await api('/templates','POST',{name:promptAttachment.name,schema:promptAttachment.schema,dataset_id:dataset,source_filename:promptAttachment.fileName},undefined,true);
     attachedTemplateId=imported.id;setPromptAttachment({...promptAttachment,savedId:imported.id});setPromptNotice(`Saved "${imported.name}" · Version ${imported.version||1}. This prompt is selected for extraction.`);
    rememberSavedPrompt(sessionStorage,key+'-prompts',dataset,imported.id);sessionStorage.setItem(key+'-dataset',dataset);setSavedPromptId(imported.id);
     onPromptSaved?.(imported);
    await loadCatalog();
   }
    if(savePromptOnly){setFiles(previous=>previous.filter(file=>attachmentKey(file)!==promptAttachment!.fileKey));setPromptAttachment(null);return;}
   const previous=plans.at(-1);const unfinished=previous&&previous.dataset_id===dataset&&!previous.superseded&&!previous.calls.some((call:Entity)=>call.status==='failed')&&previous.calls.some((call:Entity)=>call.status==='pending')?previous:null;
   const references=unfinished?.calls.flatMap((call:Entity)=>call.uploaded_document_ids||[])||[];
   const earlierRequest=unfinished?`${unfinished.request}\nPending tools from the unfinished plan: ${unfinished.calls.filter((call:Entity)=>call.status==='pending').map((call:Entity)=>call.tool).join(', ')}`.slice(0,12000):'';
   const plan=await api('/agent-v2/plans','POST',{text:request,conversation_id:conversations.current[dataset||'general']||conversations.current.general||'',earlier_request:earlierRequest,completed_tools:unfinished?.calls.filter((call:Entity)=>call.status==='completed').map((call:Entity)=>call.tool)||[],attached_filenames:documentFiles.map(file=>file.name),planner_model_id:planner,dataset_id:unfinished?.dataset_id||dataset,document_ids:references.length?references:unfinished?.document_ids||documents,answer_scope:documents.length?'documents':'auto',template_id:attachedTemplateId||unfinished?.template_id||'',allow_external:external},undefined,true);
   if(plan.calls.length)setPlans(existing=>existing.map(item=>({...item,superseded:!active(item)&&item.calls.some((call:Entity)=>call.status==='pending')})));
   const ids=plans.filter(p=>!p.historical).map(p=>p.id).concat(plan.id).slice(-30);sessionStorage.setItem(key+'-history',JSON.stringify(ids));sessionStorage.setItem(key,plan.id);replacePlan(plan);setPendingRequest('');
   if(plan.calls.length){speak(explainPlan(plan));return;}
   answering=true;setWorking('Answering…');update(plan.id,{chat:{text:'',status:'streaming',citations:[]}});
   const controller=new AbortController();answerController.current=controller;
   const response=await stream(`/agent-v2/plans/${plan.id}/reply`,{conversation_id:conversations.current[plan.answer_mode==='general'?'general':plan.dataset_id]||'',document_model_id:planner||null,allow_external:external},controller.signal);
   if(!response.ok){const data=await response.json();throw new Error(typeof data.detail==='string'?data.detail:'The answer could not start.');}
   if(!response.body)throw new Error('The answer stream is unavailable.');
   let answer='';
   await readChatStream(response.body,({type,payload})=>{
    if(type==='delta'){answer+=payload.text||'';update(plan.id,{chat:{text:answer,status:'streaming',citations:[]}});}
    if(type==='done'){conversations.current[plan.answer_mode==='general'?'general':plan.dataset_id]=payload.conversation_id;update(plan.id,{chat:payload.message,conversation_id:payload.conversation_id});speak(payload.message.text);}
    if(type==='error'){update(plan.id,{chat:payload.message});throw new Error(payload.detail);}
   });
  }catch(e){
   if(!answering)setText(current=>current||request);
   if(!(e instanceof Error&&e.name==='AbortError'))setError(e instanceof Error?e.message:'The request could not finish.');
   const id=sessionStorage.getItem(key);if(answering&&id){
    setPlans(previous=>previous.map(p=>p.id===id&&p.chat?.status==='streaming'?{...p,chat:{...p.chat,status:e instanceof Error&&e.name==='AbortError'?'aborted':'failed'}}:p));
    try{const saved=await api(`/agent-v2/plans/${id}`,'GET',undefined,undefined,true);if(saved.chat)replacePlan(saved);if(saved.conversation_id)conversations.current[saved.answer_mode==='general'?'general':saved.dataset_id]=saved.conversation_id;}catch{}
   }
  }
  finally{answerController.current=null;lock.current=false;if(mounted.current){setPendingRequest('');setWorking('');}}
 };
 const toggleMic=()=>{
  if(listening){recognition.current?.stop();return;}
  try{recognition.current=startSpeechInput(window as unknown as SpeechEnvironment,{text:transcript=>{if(mounted.current)setText(previous=>`${previous}${previous?' ':''}${transcript}`);},listening:value=>{if(mounted.current)setListening(value);},error:message=>{if(mounted.current)setError(message);}},navigator.language||'en-US');}catch(e){setError(e instanceof Error?e.message:'Could not start the microphone. Check browser permissions.');}
 };
 const datasetConfig=catalog.datasets.find((d:Entity)=>d.id===dataset);
 const chatModels=eligibleAgentModels(catalog.models,datasetConfig);
 const readyDocuments=readyDatasetDocuments(catalog.documents,dataset);
 const mention=!mentionClosed&&!working&&!plans.some(active)?documentMention(text,caret):null;
 const mentionDocuments=mention?matchingDocuments(readyDocuments,mention.query):[];
 useEffect(()=>{if(mention&&mentionDocuments[mentionIndex])document.getElementById(`agent-document-option-${mentionDocuments[mentionIndex].id}`)?.scrollIntoView({block:'nearest'});},[mentionIndex,mention?.query]);
 useEffect(()=>{if(!mention)return;const dismiss=(e:PointerEvent)=>{if(!(e.target instanceof Element)||!e.target.closest('.agent-v2-composer'))setMentionClosed(true);};document.addEventListener('pointerdown',dismiss);return()=>document.removeEventListener('pointerdown',dismiss);},[Boolean(mention)]);
 useEffect(()=>{if(!catalog.models.length)return;setPlanner(current=>chatModels.some((m:Entity)=>m.id===current)?current:chatModels.find((m:Entity)=>m.id===datasetConfig?.default_chat_model_id)?.id||chatModels[0]?.id||'');},[catalog,dataset]);
 const chooseMention=(doc:Entity)=>{
  if(!mention)return;if(!documents.includes(doc.id)&&documents.length>=20){setError('Choose at most 20 documents.');return;}
  setDocuments(previous=>previous.includes(doc.id)?previous:[...previous,doc.id]);
  const next=text.slice(0,mention.start)+text.slice(mention.end);setText(next);setCaret(mention.start);setMentionClosed(true);setMentionIndex(0);
  requestAnimationFrame(()=>{composer.current?.focus();composer.current?.setSelectionRange(mention.start,mention.start);});
 };
 return <section className={`agent-v2${dragging?' agent-v2-dragging':''}`} aria-label="Aegis Assistant conversation" onDragEnter={onFileDragEnter} onDragOver={onFileDragOver} onDragLeave={onFileDragLeave} onDrop={onFileDrop}>
  {dragging&&<div className="agent-v2-drop-overlay" role="status"><UploadCloud size={36}/><strong>{attachmentsBlocked?'Finish the current workflow first':'Drop documents here'}</strong><span>{attachmentsBlocked?'You can attach files when it finishes.':`PDF, DOCX, TXT, JSON · up to 20 files · ${maxUploadMb} MB each`}</span></div>}
  <header className="agent-v2-context">
   <label>Dataset<select aria-label="Agent dataset" value={dataset} disabled={attachmentsBlocked} onChange={e=>{setDataset(e.target.value);sessionStorage.setItem(key+'-dataset',e.target.value);setSavedPromptId('');setDocuments([]);setMentionClosed(true);cancelPrompt();setPromptAttachment(null);setPromptNotice('');}}><option value="">General chat</option>{catalog.datasets.map((d:Entity)=><option key={d.id} value={d.id}>{d.name}</option>)}</select></label>
   {dataset&&<AgentDocumentFilter key={dataset} documents={readyDocuments} selected={documents} onChange={setDocuments} disabled={Boolean(working)||plans.some(active)}/>}
   <button className="btn icon" aria-label={spoken?'Turn off spoken responses':'Turn on spoken responses'} title={speechSupported?'Spoken responses':'Speech playback unavailable in this browser'} aria-pressed={spoken} disabled={!speechSupported} onClick={()=>{setSpoken(!spoken);if(spoken)window.speechSynthesis.cancel();}}>{spoken?<Volume2 size={18}/>:<VolumeX size={18}/>}</button>
   <button className="btn icon" aria-label="Agent chat history" title="Chat history" disabled={Boolean(working)||plans.some(active)} onClick={()=>void api('/conversations','GET',undefined,undefined,true).then(result=>{setHistory(result);setHistoryOpen(!historyOpen);}).catch(e=>setError(e.message))}><History size={18}/></button>
   <button className="btn icon" aria-label="New agent conversation" title="New conversation" disabled={Boolean(working)||plans.some(active)} onClick={()=>{setPlans([]);conversations.current={};sessionStorage.removeItem(key);sessionStorage.removeItem(key+'-history');sessionStorage.removeItem(key+'-conversation');setError('');}}><Plus size={18}/></button>
  </header>
  {historyOpen&&<div className="agent-v2-history"><strong>Saved chats · shared with Aegis Agent</strong><button className="text-button" onClick={()=>setHistoryOpen(false)}>Close</button>{history.length?history.map(c=><button className="text-button" key={c.id} onClick={()=>void api(`/conversations/${c.id}`,'GET',undefined,undefined,true).then(conversation=>{restoreConversation(conversation);sessionStorage.setItem(key+'-conversation',c.id);sessionStorage.removeItem(key);sessionStorage.removeItem(key+'-history');setHistoryOpen(false);setError('');}).catch(e=>setError(e.message))}>{c.title||c.name}</button>):<p>No saved chats yet.</p>}</div>}
  <div className="agent-v2-thread" aria-label="Agent conversation" tabIndex={0}>
   {!plans.length&&<div className="agent-v2-welcome"><Bot size={34}/><h2>How can I help?</h2><p>Ask general questions, chat with your documents, or upload and extract in one conversation.</p><div className="agent-v2-suggestions">{['What can you do?','Summarize the key points','Upload and extract documents'].map(s=><button key={s} className="btn" onClick={()=>setText(s)}>{s}</button>)}</div><p className="small muted">General chat uses your selected model. Choose a dataset for answers with document evidence.</p></div>}
   {plans.map(plan=>{
    const index=nextCall(plan);const call=index>=0?plan.calls[index]:null;
    const needInputs=call?.status==='pending'&&!plan.superseded;const uploaded=plan.calls.some((c:Entity)=>c.uploaded_document_ids?.length);
    const docs=catalog.documents.filter((d:Entity)=>d.parent_id===plan.dataset_id);
    const templates=catalog.templates.filter((t:Entity)=>!t.parent_id||t.parent_id===plan.dataset_id);
    return <article key={plan.id} className="agent-v2-exchange"><div className="agent-v2-user">{plan.request}</div><div className="agent-v2-response"><div className="agent-v2-speaker"><Bot size={16} aria-hidden="true"/><strong>Aegis</strong><span title={plan.chat?.model_selection?.model_name||plan.planner.name}>{plan.chat?.model_selection?.model_name||plan.planner.name}</span></div>{(needInputs||(!plan.calls.length&&!plan.chat&&!plan.reply_started))&&<p className="agent-v2-reply">{explainPlan(plan)}</p>}
     {plan.chat&&<AgentChatAnswer message={plan.chat} api={api} onError={setError}/>}
     {plan.conversation_id&&plan.chat?.status==='completed'&&plan.id===plans.at(-1)?.id&&<a className="agent-v2-export" href={`/api/conversations/${plan.conversation_id}/export`} download>Export chat</a>}
     {plan.clarification?.length>0&&needInputs&&<p className="small muted">{plan.clarification.join(' · ')}</p>}
     {plan.calls.length>0&&<ol className="agent-v2-tools">{plan.calls.map((tool:Entity,i:number)=><li key={i} data-status={tool.status}><div className="agent-v2-tool-heading">{tool.status==='completed'?<CheckCircle2 size={17}/>:['waiting','running'].includes(tool.status)?<Loader2 size={17} className="animate-spin"/>:<span className="agent-v2-tool-number">{i+1}</span>}<strong>{tool.title}</strong><code>{tool.tool}</code><span>{tool.status==='pending'?(plan.calls.slice(0,i).some((c:Entity)=>c.status==='failed')?'Blocked by failed tool':i>index?'Waiting for previous tool':'Awaiting confirmation'):tool.status==='waiting'?'Processing':tool.status}</span></div>
      {tool.tool==='upload'&&tool.jobs?.length>0&&<UploadWorkflow call={tool}/>}
      {tool.tool!=='upload'&&tool.jobs?.map((job:Entity)=><AgentJobProgress key={job.id} job={job}/>)}
      {tool.error&&!tool.jobs?.some((job:Entity)=>job.error===tool.error)&&<p role="alert" className="agent-v2-error">{tool.error}</p>}
      <AgentResult tool={tool} onReview={onReview}/>
     </li>)}</ol>}
     {needInputs&&<div className="agent-v2-details"><strong>A few details to continue</strong><label>Dataset<select aria-label="Workflow dataset" value={plan.dataset_id} disabled={uploaded} onChange={e=>update(plan.id,{dataset_id:e.target.value,document_ids:[],template_id:''})}><option value="">Choose a dataset</option>{catalog.datasets.map((d:Entity)=><option key={d.id} value={d.id}>{d.name}</option>)}</select></label>
      {call.tool!=='upload'&&!uploaded&&<label>Documents · choose up to 20<select aria-label="Workflow documents" multiple size={Math.min(4,Math.max(2,docs.length))} value={plan.document_ids} onChange={e=>update(plan.id,{document_ids:Array.from(e.target.selectedOptions).map(o=>o.value).slice(0,20)})}>{docs.map((d:Entity)=><option key={d.id} value={d.id}>{d.name}{docs.filter((other:Entity)=>other.name===d.name).length>1?` · ${new Date(d.created_at*1000).toLocaleString()}`:''}{d.status!=='ready'?` · ${d.status}`:''}</option>)}</select></label>}
      {plan.calls.some((c:Entity)=>c.tool!=='upload')&&<label>Prompt template<select aria-label="Workflow prompt template" value={plan.template_id} onChange={e=>update(plan.id,{template_id:e.target.value})}><option value="">Choose a template</option>{templates.map((t:Entity)=><option key={t.id} value={t.id}>{t.name}</option>)}</select></label>}
      {call.tool==='upload'&&<p className="small">{files.length?`${files.length} files attached below.`:'Drop documents into the chat or use the + button below.'}</p>}
      <p className="small muted">Review the selected dataset, files and template. This tool runs only after you confirm.</p>
      <button className="btn primary" disabled={attachmentsBlocked||!plan.dataset_id||(call.tool==='upload'?(!documentFiles.length||Boolean(unresolvedJson.length)):(!uploaded&&!plan.document_ids.length)||!plan.template_id)} onClick={()=>void perform(plan,index)}>{call.tool==='upload'?'Confirm upload':call.tool==='reextract'?'Confirm re-extraction':'Confirm extraction'}</button>
     </div>}
     {active(plan)&&<button className="text-button" onClick={()=>void api(`/agent-v2/plans/${plan.id}`,'GET',undefined,undefined,true).then(replacePlan).catch(e=>setError(e.message))}>Check status</button>}
     {plan.superseded&&<p className="small muted">Replaced by your next request. Pending tools will not start.</p>}
    </div></article>;
   })}
   {pendingRequest&&<div className="agent-v2-user agent-v2-pending">{pendingRequest}</div>}
   {working&&<p className="agent-v2-working" role="status"><Loader2 size={15} className="animate-spin"/>{working}</p>}
   {error&&<p className="agent-v2-error" role="alert">{error}</p>}<div ref={end}/>
  </div>
  <div className="agent-v2-composer">
   {savedPrompt&&!promptAttachment&&<div className="agent-v2-selected-documents" aria-label="Selected saved prompt"><span>Prompt: {savedPrompt.name}<button aria-label="Clear selected prompt" disabled={attachmentsBlocked} onClick={clearSavedPrompt}><X size={12}/></button></span></div>}
   {documents.length>0&&<div className="agent-v2-selected-documents" aria-label="Selected document filters">{documents.map(id=>{const doc=readyDocuments.find((d:Entity)=>d.id===id);return doc?<span key={id} title={documentOptionLabel(doc,readyDocuments)}>{documentOptionLabel(doc,readyDocuments)}<button aria-label={`Remove document ${documentOptionLabel(doc,readyDocuments)}`} disabled={Boolean(working)||plans.some(active)} onClick={()=>setDocuments(previous=>previous.filter(value=>value!==id))}><X size={12}/></button></span>:null;})}<button className="text-button" disabled={Boolean(working)||plans.some(active)} onClick={()=>setDocuments([])}>Clear filter</button></div>}
   {mention&&<div className="agent-v2-mention-popover agent-v2-document-popover"><div className="agent-v2-picker-heading"><strong>Documents in this dataset</strong><button className="btn icon" aria-label="Close document suggestions" onClick={()=>{setMentionClosed(true);composer.current?.focus();}}><X size={15}/></button></div><div id="agent-document-mentions" role="listbox" aria-label="Dataset document suggestions" className="agent-v2-document-options">{mentionDocuments.map((doc:Entity,index:number)=><button type="button" role="option" id={`agent-document-option-${doc.id}`} key={doc.id} aria-selected={index===mentionIndex} onMouseDown={e=>e.preventDefault()} onClick={()=>chooseMention(doc)}><span>{documentOptionLabel(doc,readyDocuments)}</span>{documents.includes(doc.id)&&<CheckCircle2 size={14}/>}</button>)}{!mentionDocuments.length&&<p>{dataset?'No matching ready documents.':'Choose a dataset to see its documents.'}</p>}</div><p className="muted small">↑ ↓ to browse · Enter to select · Esc to close</p></div>}
   <div className="agent-v2-compose-box">
    {files.length>0&&<div className="agent-v2-files" aria-label="Attached files">{files.map(file=>{
     const id=attachmentKey(file);const json=isJsonAttachment(file);const prompt=promptAttachment?.fileKey===id;
     return <div className={`agent-v2-file-card${json?' agent-v2-json-card':''}`} key={id}><FileText size={20}/><span><strong title={file.name}>{file.name}</strong><small>{attachmentSize(file.size)}{json?` · ${prompt?(promptAttachment.savedId?'Saved prompt':'Prompt template'):jsonDocuments[id]?'Document':'Choose file type'}`:''}</small>{json&&<span className="agent-v2-json-choice" role="group" aria-label={`Use ${file.name} as`}><button type="button" aria-pressed={prompt} disabled={attachmentsBlocked} onClick={()=>void chooseJsonPrompt(file)}>Prompt template</button><button type="button" aria-pressed={Boolean(jsonDocuments[id])} disabled={attachmentsBlocked} onClick={()=>chooseJsonDocument(file)}>Document</button></span>}{attachmentErrors[id]&&<span className="agent-v2-attachment-error" role="alert">{attachmentErrors[id]}</span>}</span><button aria-label={`Remove attachment ${file.name}`} disabled={attachmentsBlocked} onClick={()=>removeAttachment(file)}><X size={14}/></button></div>;
    })}<button className="text-button" disabled={attachmentsBlocked} onClick={()=>{setFiles([]);setJsonDocuments({});setAttachmentErrors({});setPromptAttachment(null);clearSavedPrompt();cancelPrompt();}}>Clear files</button></div>}
    <div className="agent-v2-input"><textarea ref={composer} aria-label="Message Aegis Assistant" placeholder="Ask anything · # to choose documents" value={text} rows={1} aria-autocomplete="list" aria-expanded={Boolean(mention)} aria-controls={mention?'agent-document-mentions':undefined} aria-activedescendant={mentionDocuments[mentionIndex]?`agent-document-option-${mentionDocuments[mentionIndex].id}`:undefined} onSelect={e=>setCaret(e.currentTarget.selectionStart)} onChange={e=>{setText(e.target.value);setCaret(e.target.selectionStart);setMentionClosed(false);setMentionIndex(0);}} onKeyDown={e=>{
     if(mention){
      if(e.key==='Escape'){e.preventDefault();setMentionClosed(true);return;}
      if(e.key==='ArrowDown'||e.key==='ArrowUp'){e.preventDefault();setMentionIndex(index=>mentionDocuments.length?(index+(e.key==='ArrowDown'?1:-1)+mentionDocuments.length)%mentionDocuments.length:0);return;}
      if(e.key==='Enter'&&!e.shiftKey&&!e.nativeEvent.isComposing){e.preventDefault();if(mentionDocuments[mentionIndex])chooseMention(mentionDocuments[mentionIndex]);return;}
     }
     if(e.key==='Enter'&&!e.shiftKey&&!e.nativeEvent.isComposing){e.preventDefault();void send();}
    }}/></div>
    <div className="agent-v2-compose-controls">
     <input ref={fileInput} type="file" hidden multiple accept=".pdf,.docx,.txt,.json" onChange={e=>{attachFiles(Array.from(e.target.files||[]));e.target.value='';}}/>
     <button className="btn icon" aria-label="Attach documents for agent" title="Attach PDF, DOCX, TXT or JSON" disabled={attachmentsBlocked} onClick={()=>fileInput.current?.click()}><Plus size={21}/></button>
     <label className="agent-v2-model-control"><span>Agent Model</span><select aria-label="Agent Model" value={planner} disabled={Boolean(working)||plans.some(active)} onChange={e=>setPlanner(e.target.value)}><option value="">Choose an Agent Model</option>{chatModels.map((m:Entity)=><option key={m.id} value={m.id}>{m.name}</option>)}</select></label>
     <div className="agent-v2-send-controls">
      <button className={`btn icon${listening?' primary':''}`} aria-label={listening?'Stop listening':'Speak your request'} title={voiceSupported?'Speech input':'Speech input unavailable in this browser'} disabled={!voiceSupported||Boolean(working)} onClick={toggleMic}><Mic size={20}/></button>
      {working&&answerController.current?<button className="btn icon agent-v2-send" aria-label="Stop answer" onClick={()=>answerController.current?.abort()}><Square size={18}/></button>:<button className="btn icon agent-v2-send" aria-label="Send agent request" disabled={(!text.trim()&&!files.length)||Boolean(mention)||attachmentsBlocked||Boolean(unresolvedJson.length)} onClick={()=>void send()}><ArrowUp size={21}/></button>}
     </div>
    </div>
   </div>
   {promptNotice&&<p className="agent-v2-prompt-notice" role="status">{promptNotice}</p>}
   <div className="agent-v2-footer"><span>Drag & drop PDF, DOCX, TXT, JSON · up to 20 files</span><details><summary>Privacy & cloud consent</summary><p>Files use your dataset’s storage, embedding and extraction models. Workflow requests and results are saved in your workspace. Browser speech recognition may send audio to its speech service; voice is optional and text remains available.</p><label><input type="checkbox" checked={external} onChange={e=>setExternal(e.target.checked)}/>Allow this request, catalog names and selected document data to reach configured external providers</label></details></div>
  </div>
  <PromptUploadPreview prompt={promptPreview} datasetName={datasetConfig?.name||''} onConfirm={confirmPrompt} onCancel={cancelPrompt}/>
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
 const ready=items.filter(item=>item.ready).length;const failed=items.filter(item=>item.failed).length;
 return <><details className="agent-v2-progress-details"><summary>{ready}/{items.length} documents ready{failed?` · ${failed} need attention`:''}<span>View progress</span></summary><BatchProgress items={items} compact/>{statuses}</details>{items.filter(item=>item.error).map(item=><p key={item.id} role="alert" className="agent-v2-error">{item.name}: {item.error}</p>)}</>;
}
