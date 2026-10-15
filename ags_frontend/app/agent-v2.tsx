"use client";
import {useCallback, useEffect, useLayoutEffect, useRef, useState,type DragEvent} from 'react';
import {Database,History,Square, Plus, CheckCircle2, Loader2, Mic, ArrowUp, ArrowDown,X,FileText,UploadCloud,Eraser,RotateCcw} from 'lucide-react';
import {isFileDrag,mergeAgentAttachments,attachmentSize,attachmentKey,isJsonAttachment} from './agent-attachments';
import {readPromptUpload,type PromptUpload} from './prompt-upload';
import {PromptUploadPreview} from './prompt-upload-preview';
import {AgentPromptProgress,type PromptProgress} from './agent-prompt-progress';
import {promptSelections,restoreSavedPrompt,rememberSavedPrompt,rememberAssistantDataset,assistantDatasetPreference} from './agent-prompt-selection';
import {AgentDocumentFilter} from './agent-document-filter';
import {documentMention,documentOptionLabel,matchingDocuments,readyDatasetDocuments,eligibleAgentModels} from './agent-document-selection';
import {agentCommands,agentMention,agentOperation,agentInputIssue,insertAgentCommand} from './agent-commands';
import {readChatStream} from './chat-stream';
import {AgentChatAnswer,AgentRequest,conversationExchanges} from './agent-v2-chat';
import {BatchProgress} from './batch-progress';
import {WorkflowStepper} from './workflow-stepper';
import {AgentLogo} from './agent-logo';
import {AgentOnboarding} from './agent-onboarding';
import {AgentAnswerWorkflow} from './agent-answer-workflow';
import {useAgentConsent,type ConsentReceipt} from './agent-consent';
import {AgentJobProgress,AgentResult} from './agent-v2-output';
import {currentUploadStep, type UploadProgressItem} from './batch-workflow';
import './agent-v2.css';
import {speechCapabilities,startSpeechInput,type SpeechEnvironment} from './agent-voice';

type Entity=Record<string,any>;
const goalWorkflow=(plan:Entity)=>{
 const start=(plan.goal.started_at||plan.goal.created_at)*1000;
 return plan.goal.status==='running'&&plan.goal.answer_workflow?plan.goal.answer_workflow:{status:'running',started_at:start,steps:[{id:'goal',label:plan.goal.status==='retry_wait'?'Waiting to retry answer':'Preparing result answer',status:'running',started_at:start}]};
};
type AttachedPrompt=PromptUpload&{fileKey:string;datasetId:string;savedId?:string};
type Api=(path:string,method?:string,body?:unknown,signal?:AbortSignal,quiet?:boolean)=>Promise<any>;
const active=(plan:Entity)=>plan.calls.some((call:Entity)=>['running','waiting'].includes(call.status))||['queued','running','retry_wait'].includes(plan.goal?.status);
const nextCall=(plan:Entity)=>plan.calls.findIndex((call:Entity)=>call.status!=='completed');
const conversationScope=(plan:Entity)=>plan.runtime==='langgraph'?(plan.dataset_id||'general'):(plan.answer_mode==='general'?'general':plan.dataset_id);
export const explainPlan=(plan:Entity)=>{
 if(!plan.calls.length)return plan.explanation?.trim()||'I can help you upload documents, extract fields, or re-extract saved documents. What would you like to do?';
 const labels:Record<string,string>={upload:'Upload documents',extract:'Extract fields',reextract:'Re-extract fields'};
 return `Proposed workflow: ${plan.calls.map((call:Entity)=>labels[call.tool]).join(' → ')}. Review the details and confirm the workflow before it runs.${plan.calls.some((call:Entity)=>call.tool==='upload')&&plan.calls.some((call:Entity)=>call.tool==='extract'||call.tool==='reextract')?' Extraction will use the uploaded references after indexing finishes.':''}${plan.calls.some((call:Entity)=>call.tool==='reextract')?' Earlier extraction results will be retained.':''}`;
};

export function AgentV2({api,stream,username,onJobs,onVisibleJobs,onReview,onPromptSaved,onDatasetChange,onWorkspaceChanged,maxUploadMb=25,catalogRevision=0}:{api:Api;stream:(path:string,body:unknown,signal:AbortSignal)=>Promise<Response>;username:string;onJobs:(jobs:Entity[])=>void;onVisibleJobs:(ids:string[])=>void;onReview:(id:string)=>void;onPromptSaved?:(template:Entity)=>void;onDatasetChange?:(id:string)=>void;onWorkspaceChanged?:()=>void;maxUploadMb?:number;catalogRevision?:number}) {
 const [catalog,setCatalog]=useState<Entity>({datasets:[],documents:[],templates:[],models:[]});
 const [catalogLoading,setCatalogLoading]=useState(true);const [catalogError,setCatalogError]=useState('');const [catalogAttempt,setCatalogAttempt]=useState(0);
 const [plans,setPlans]=useState<Entity[]>([]);
 const [history,setHistory]=useState<Entity[]>([]); const [historyOpen,setHistoryOpen]=useState(false);
 const [documents,setDocuments]=useState<string[]>([]); const conversations=useRef<Record<string,string>>({}); const answerController=useRef<AbortController|null>(null);
 const [dataset,setDataset]=useState(''); const [planner,setPlanner]=useState('');
 const [scopeReady,setScopeReady]=useState(false);const datasetChangeRef=useRef(onDatasetChange);datasetChangeRef.current=onDatasetChange;
 const [caret,setCaret]=useState(0);const [mentionClosed,setMentionClosed]=useState(false);const [mentionIndex,setMentionIndex]=useState(0);
 const [text,setText]=useState(''); const [files,setFiles]=useState<File[]>([]);
 // Keep bytes bound to the submitted request until its confirmed upload succeeds.
 const submittedFiles=useRef<Record<string,File[]>>({});const [pendingFiles,setPendingFiles]=useState<File[]>([]);
 const submittedOnboardingPrompts=useRef<Record<string,AttachedPrompt>>({});
 const retrySubmittedPrompt=useRef('');
 const retryPlanId=useRef('');
 const [jsonDocuments,setJsonDocuments]=useState<Record<string,boolean>>({});
 const [attachmentErrors,setAttachmentErrors]=useState<Record<string,string>>({});
 const [savedPromptId,setSavedPromptId]=useState('');const catalogLoaded=useRef(false);
 const [promptPreview,setPromptPreview]=useState<AttachedPrompt|null>(null);const [promptAttachment,setPromptAttachment]=useState<AttachedPrompt|null>(null);
 const [promptNotice,setPromptNotice]=useState('');const promptReadToken=useRef(0);
 const [promptProgress,setPromptProgress]=useState<PromptProgress|null>(null);
 const [dragging,setDragging]=useState(false);const dragDepth=useRef(0);
 const [working,setWorking]=useState(''); const [error,setError]=useState(''); const [pendingRequest,setPendingRequest]=useState('');
 const [requestStartedAt,setRequestStartedAt]=useState(0);
 const consent=useAgentConsent(api);const approvals=useRef<Record<string,ConsentReceipt>>({});const consentPaused=useRef(new Set<string>());
 const [voiceSupported,setVoiceSupported]=useState(false); const [listening,setListening]=useState(false);
 const fileInput=useRef<HTMLInputElement>(null); const end=useRef<HTMLDivElement>(null); const composer=useRef<HTMLTextAreaElement>(null);
 const composerContainer=useRef<HTMLDivElement>(null);
 const composerHighlight=useRef<HTMLDivElement>(null);
 const thread=useRef<HTMLDivElement>(null);const followBottom=useRef(true);const [showLatest,setShowLatest]=useState(false);
 const lock=useRef(false); const mounted=useRef(true); const recognition=useRef<any>(null);
 const onJobsRef=useRef(onJobs); onJobsRef.current=onJobs;
 const onVisibleJobsRef=useRef(onVisibleJobs); onVisibleJobsRef.current=onVisibleJobs;
 const key=`aegis-agent-v2:${username}`;
 const [onboardingOpen,setOnboardingOpen]=useState(false);const [onboardingBusy,setOnboardingBusy]=useState(false);
 const clearConversation=()=>{
  if(lock.current||working||onboardingBusy||plans.some(active))return;
  setPlans([]);setHistoryOpen(false);setText('');setPendingRequest('');setPendingFiles([]);setPromptProgress(null);setRequestStartedAt(0);
  retrySubmittedPrompt.current='';retryPlanId.current='';submittedFiles.current={};conversations.current={};
  approvals.current={};
  sessionStorage.removeItem(key);sessionStorage.setItem(key+'-history','[]');sessionStorage.removeItem(key+'-conversation');
  setError('');followBottom.current=true;setShowLatest(false);composer.current?.focus();
 };
 const datasetConfig=catalog.datasets.find((d:Entity)=>d.id===dataset);
 const chatModels=eligibleAgentModels(catalog.models,datasetConfig);
 // Resolve the displayed model synchronously: history restoration and catalog effects
 // can settle in different orders after returning from Review. Send uses this same ID.
 const effectivePlanner=chatModels.find((m:Entity)=>m.id===planner)?.id||chatModels.find((m:Entity)=>m.id===datasetConfig?.default_chat_model_id)?.id||chatModels[0]?.id||planner||'';
 const savedPrompt=catalog.templates.find((template:Entity)=>template.id===savedPromptId&&(!template.parent_id||template.parent_id===dataset));
 const clearSavedPrompt=()=>{rememberSavedPrompt(sessionStorage,key+'-prompts',dataset,'');setSavedPromptId('');setPromptNotice('');};
 const attachmentsBlocked=Boolean(working)||onboardingBusy||plans.some(active)||Boolean(promptPreview);
 const documentFiles=files.filter(file=>!isJsonAttachment(file)||jsonDocuments[attachmentKey(file)]);
 const unresolvedJson=files.filter(file=>isJsonAttachment(file)&&!jsonDocuments[attachmentKey(file)]&&promptAttachment?.fileKey!==attachmentKey(file));
 const removeAttachment=(file:File)=>{
  const id=attachmentKey(file);setError('');setFiles(previous=>previous.filter(current=>attachmentKey(current)!==id));
  setJsonDocuments(previous=>{const next={...previous};delete next[id];return next;});
  setAttachmentErrors(previous=>{const next={...previous};delete next[id];return next;});
  if(promptAttachment?.fileKey===id&&promptAttachment.savedId===savedPromptId)clearSavedPrompt();
  if(promptAttachment?.fileKey===id){setPromptAttachment(null);setPromptNotice('');setPromptProgress(null);}
 };
 const cancelPrompt=()=>{promptReadToken.current++;setPromptPreview(null);};
 const chooseJsonDocument=(file:File)=>{
  const id=attachmentKey(file);setJsonDocuments(previous=>({...previous,[id]:true}));setError('');
  setAttachmentErrors(previous=>{const next={...previous};delete next[id];return next;});
  if(promptAttachment?.fileKey===id&&promptAttachment.savedId===savedPromptId)clearSavedPrompt();
  if(promptAttachment?.fileKey===id){setPromptAttachment(null);setPromptNotice('');setPromptProgress(null);}
 };
 const chooseJsonPrompt=async(file:File)=>{
  if(attachmentsBlocked)return;
  if(!dataset){setError('Choose a dataset before attaching a prompt template.');return;}
  if(promptAttachment&&promptAttachment.fileKey!==attachmentKey(file)){setError('Remove the current prompt template before choosing another. Use one prompt per message.');return;}
  const token=++promptReadToken.current;lock.current=true;setWorking('Validating prompt.');setError('');
  setPromptProgress({name:file.name,phase:'validating'});
  setAttachmentErrors(previous=>{const next={...previous};delete next[attachmentKey(file)];return next;});
  try{
   const parsed=await readPromptUpload(file);
   const validation=await api('/templates/validate','POST',{name:parsed.name,schema:parsed.schema,instructions:parsed.instructions||'',dataset_id:dataset,source_filename:parsed.fileName},undefined,true);
   if(mounted.current&&token===promptReadToken.current){setPromptPreview({...parsed,replacesExisting:Boolean(validation.existing_template_id),fileKey:attachmentKey(file),datasetId:dataset,savedId:promptAttachment?.savedId});setPromptProgress(null);}
  }catch(e){if(mounted.current&&token===promptReadToken.current){setPromptProgress(null);setAttachmentErrors(previous=>({...previous,[attachmentKey(file)]:`${file.name}: ${e instanceof Error?e.message:'The prompt could not be validated.'}`}));}}
  finally{lock.current=false;if(mounted.current)setWorking('');}
 };
 const confirmPrompt=()=>{
  if(!promptPreview||promptPreview.datasetId!==dataset)return;
  setPromptAttachment(promptPreview);setJsonDocuments(previous=>{const next={...previous};delete next[promptPreview.fileKey];return next;});setPromptPreview(null);
  setPromptNotice('Prompt confirmed. Send to save it for this dataset; extraction still requires confirmation.');setError('');
  setPromptProgress({name:promptPreview.fileName,phase:'confirmed'});
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
  conversations.current[conversation.mode==='general'?'general':conversation.dataset_id||'general']=conversation.id;
 },[]);
 const replacePlan=useCallback((plan:Entity)=>{
  if(!mounted.current)return;
  if(plan.conversation_id)conversations.current[conversationScope(plan)]=plan.conversation_id;
  setPlans(previous=>previous.some(p=>p.id===plan.id)?previous.map(p=>p.id===plan.id?{...plan,messageAttachments:plan.messageAttachments||p.messageAttachments}:p):[...previous,plan]);
  // Publish ownership before publishing jobs, so the global popup cannot flash
  // a second workflow during the first render of a newly submitted tool.
  onVisibleJobsRef.current(plan.calls.flatMap((call:Entity)=>call.status==='waiting'?(call.job_ids||[]):[]));
  const jobs=plan.calls.flatMap((c:Entity)=>c.jobs||[]); if(jobs.length)onJobsRef.current(jobs);
 },[]);
 const loadCatalog=useCallback(async()=>{
  setCatalogLoading(true);setCatalogError('');
  try{const result=await api('/agent-v2/catalog?selectors_only=true','GET',undefined,undefined,true);if(mounted.current){catalogLoaded.current=true;setCatalog(result);}return result;}
  catch(e){if(mounted.current)setCatalogError(e instanceof Error?e.message:'Could not load datasets and models.');throw e;}
  finally{if(mounted.current)setCatalogLoading(false);}
 },[api]);
 useEffect(()=>{if(catalogLoaded.current)void loadCatalog().catch(()=>{});},[catalogRevision,loadCatalog]);
 useEffect(()=>{if(!catalogLoaded.current)return;const restored=restoreSavedPrompt(sessionStorage.getItem(key+'-prompts'),catalog.templates,dataset);setSavedPromptId(restored?.id||'');},[catalog,dataset,key]);
 useEffect(()=>{if(scopeReady)datasetChangeRef.current?.(dataset);},[dataset,scopeReady]);
 useEffect(()=>{
  mounted.current=true;let cancelled=false;
  const capabilities=speechCapabilities(window as unknown as SpeechEnvironment);setVoiceSupported(capabilities.input);
  if(sessionStorage.getItem(key+'-onboarding')||sessionStorage.getItem(key+'-onboarding-request'))setOnboardingOpen(true);
  void loadCatalog().then(async(result)=>{
   if(cancelled)return;
   const local=result.models.filter((m:Entity)=>m.enabled!==false&&m.capabilities.includes('chat'));
   if(local.length===1)setPlanner(local[0].id);
   let restoredDataset='';const opened=sessionStorage.getItem(key+'-conversation');if(opened){const conversation=await api(`/conversations/${opened}`,'GET',undefined,undefined,true);if(cancelled)return;restoredDataset=conversation.dataset_id||'';restoreConversation(conversation);}
   const saved=sessionStorage.getItem(key+'-history'); let ids:string[]=saved?JSON.parse(saved):[sessionStorage.getItem(key)].filter(Boolean);
   // An explicitly empty history means the user started or cleared a chat.
   // Recover goals only when there is no saved chat choice for this session.
   if(!ids.length&&!opened&&saved===null){const goals=await api('/agent-v2/goals','GET',undefined,undefined,true);if(cancelled)return;ids=goals.filter((goal:Entity)=>!['completed','cancelled'].includes(goal.status)).map((goal:Entity)=>goal.id);if(!ids.length&&goals[0])ids=[goals[0].id];ids.reverse();}
   let lastPlan:Entity|undefined;
   for(const id of ids){const plan=await api(`/agent-v2/plans/${id}`,'GET',undefined,undefined,true);if(cancelled)return;lastPlan=plan;replacePlan(plan);if(plan.conversation_id)conversations.current[conversationScope(plan)]=plan.conversation_id;setDataset(plan.dataset_id);setPlanner(plan.planner.id);setDocuments(plan.calls.some((c:Entity)=>c.tool==='upload')?[]:plan.document_ids||[]);}
   if(lastPlan?.template_id&&promptSelections(sessionStorage.getItem(key+'-prompts'))[lastPlan.dataset_id]===undefined){rememberSavedPrompt(sessionStorage,key+'-prompts',lastPlan.dataset_id,lastPlan.template_id);setSavedPromptId(restoreSavedPrompt(sessionStorage.getItem(key+'-prompts'),result.templates,lastPlan.dataset_id)?.id||'');}
   const preferred=assistantDatasetPreference(sessionStorage,username,result.datasets,lastPlan?.dataset_id||restoredDataset);
   setDataset(preferred);setDocuments(previous=>previous.filter(id=>result.documents.some((item:Entity)=>item.id===id&&item.parent_id===preferred)));setScopeReady(true);
  }).catch(e=>{if(!cancelled)setError(e.message);});
  return()=>{cancelled=true;mounted.current=false;answerController.current?.abort();recognition.current?.abort();};
 },[api,key,loadCatalog,replacePlan,restoreConversation,catalogAttempt]);
 useEffect(()=>{onVisibleJobs(plans.flatMap(plan=>plan.calls.flatMap((call:Entity)=>call.status==='waiting'?(call.job_ids||[]):[])));},[plans,onVisibleJobs]);
 const completedUploads=plans.filter(plan=>plan.calls.some((call:Entity)=>call.tool==='upload'&&call.status==='completed')).map(plan=>plan.id).join(',');
 useEffect(()=>{if(completedUploads)void loadCatalog().catch(e=>{if(mounted.current)setError(e.message);});},[completedUploads,loadCatalog]);
 useEffect(()=>()=>onVisibleJobs([]),[onVisibleJobs]);
 useEffect(()=>{const area=thread.current;if(area&&followBottom.current)area.scrollTop=area.scrollHeight;},[plans,working,error,files.length]);
 const followLatest=()=>{followBottom.current=true;setShowLatest(false);if(thread.current)thread.current.scrollTop=thread.current.scrollHeight;};
 const resizeComposer=useCallback(()=>{
  const input=composer.current;const container=composerContainer.current;const workspace=container?.closest('.agent-v2');
  if(!input||!container||!workspace||!workspace.clientHeight)return;
  const styles=getComputedStyle(input);const minimum=parseFloat(styles.minHeight)||28;
  // Reserve space for attachments, filters and controls, and keep the conversation visible.
  const chrome=container.offsetHeight-input.offsetHeight;
  const viewportHeight=window.visualViewport?.height||window.innerHeight;
  const maximum=Math.max(minimum,Math.min(240,viewportHeight*.3,workspace.clientHeight*.6-chrome));
  input.style.height='auto';input.style.overflowY='hidden';
  const height=Math.max(minimum,Math.min(input.scrollHeight,maximum));
  input.style.height=`${height}px`;input.style.overflowY=input.scrollHeight>height?'auto':'hidden';
  if(composerHighlight.current){composerHighlight.current.style.width=`${input.clientWidth}px`;composerHighlight.current.scrollTop=input.scrollTop;}
 },[]);
 useLayoutEffect(resizeComposer,[text,resizeComposer]);
 useEffect(()=>{
  const container=composerContainer.current;const workspace=container?.closest('.agent-v2');
  if(!container||!workspace)return;
  const observer=new ResizeObserver(resizeComposer);observer.observe(container);observer.observe(workspace);
  window.addEventListener('resize',resizeComposer);window.visualViewport?.addEventListener('resize',resizeComposer);
  return()=>{observer.disconnect();window.removeEventListener('resize',resizeComposer);window.visualViewport?.removeEventListener('resize',resizeComposer);};
 },[resizeComposer]);
 const update=useCallback((id:string,changes:Entity)=>setPlans(previous=>previous.map(plan=>plan.id===id?{...plan,...changes}:plan)),[]);
 const retryKnowledge=async(plan:Entity)=>{
  if(lock.current)return;lock.current=true;setWorking('Updating saved knowledge…');setError('');
  try{replacePlan(await api(`/agent-v2/plans/${plan.id}/knowledge/retry`,'POST',{confirmed:true},undefined,true));}
  catch(e){setError(e instanceof Error?e.message:'Knowledge publication could not finish. Saved files and results are preserved.');}
  finally{lock.current=false;setWorking('');}
 };
 const perform=useCallback(async(plan:Entity,index:number)=>{
  if(lock.current)return; lock.current=true;
  const call=plan.calls[index];setWorking(call.tool==='upload'?'Uploading documents…':'Starting extraction…');setError('');
  try {
   const permission=await consent.request({dataset_id:plan.dataset_id,roles:call.tool==='upload'&&!plan.calls.some((c:Entity)=>c.tool==='extract'||c.tool==='reextract')?['embedding']:['embedding','extraction']},approvals.current[plan.id]);
   if(!permission){consentPaused.current.add(plan.id);return;}consentPaused.current.delete(plan.id);approvals.current[plan.id]=permission;const external=permission.required;
   let result;
   if(call.tool==='upload'){
    const bound=submittedFiles.current[plan.id];const uploadFiles=bound?.length?bound:documentFiles;
    if(!uploadFiles.length||(!bound?.length&&unresolvedJson.length))throw new Error('Attach documents and choose how to use each JSON attachment before uploading.');
    const data=new FormData();for(const file of uploadFiles)data.append('files',file);data.append('dataset_id',plan.dataset_id);data.append('allow_external',String(external));data.append('confirmed','true');
    if(plan.calls.some((c:Entity)=>c.tool==='extract'||c.tool==='reextract')){data.append('continue_extraction','true');data.append('template_id',plan.template_id);if(plan.extraction_mode)data.append('extraction_mode',plan.extraction_mode);data.append('merge_strategy',plan.merge_strategy||'records');data.append('display_name',plan.display_name||'');}
    result=await api(`/agent-v2/plans/${plan.id}/calls/${index}/upload`,'POST',data,undefined,true);if(!bound?.length){result.messageAttachments=uploadFiles.map(file=>({name:file.name,size:file.size}));setFiles(previous=>previous.filter(file=>!uploadFiles.includes(file)));}
    delete submittedFiles.current[plan.id];
   } else result=await api(`/agent-v2/plans/${plan.id}/calls/${index}`,'POST',{dataset_id:plan.dataset_id,document_ids:plan.document_ids,template_id:plan.template_id,extraction_mode:plan.extraction_mode||null,merge_strategy:plan.merge_strategy||'records',display_name:plan.display_name||'',allow_external:external,confirmed:true},undefined,true);
   replacePlan(result);
  } catch(e){if(mounted.current)setError(e instanceof Error?e.message:'The action could not finish.');await api(`/agent-v2/plans/${plan.id}`,'GET',undefined,undefined,true).then(replacePlan).catch(()=>{});}
  finally{lock.current=false;if(mounted.current)setWorking('');}
 },[api,consent.request,documentFiles,unresolvedJson.length,promptAttachment,replacePlan]);
 // Confirmation of an upload-and-extract workflow authorizes its next step.
 // The server returns the exact indexed references; failures stop continuation.
 useEffect(()=>{
  if(working||lock.current)return;
  const plan=plans.find(p=>p.auto_continue&&!consentPaused.current.has(p.id)&&!p.superseded&&!active(p)&&nextCall(p)>=0&&p.calls[nextCall(p)].status==='pending'&&p.calls[nextCall(p)].tool!=='upload');
  if(plan)void perform(plan,nextCall(plan));
 },[plans,working,perform]);
 const recover=async(plan:Entity,index:number,action:string)=>{
  if(lock.current)return;lock.current=true;setWorking('Updating workflow.');setError('');
  try{let external=false;if(action==='restart'){const permission=await consent.request({dataset_id:plan.dataset_id,roles:['embedding','extraction']},approvals.current[plan.id]);if(!permission)return;approvals.current[plan.id]=permission;external=permission.required;}replacePlan(await api(action==='restart'?`/agent-v2/plans/${plan.id}/restart`:`/agent-v2/plans/${plan.id}/calls/${index}/recover`,'POST',action==='restart'?{dataset_id:plan.dataset_id,document_ids:plan.document_ids||[],template_id:plan.template_id,extraction_mode:plan.extraction_mode||null,merge_strategy:plan.merge_strategy||'records',display_name:plan.display_name||'',allow_external:external,confirmed:true}:{action,confirmed:true},undefined,true));}
  catch(e){setError(e instanceof Error?e.message:'Recovery could not start.');}
  finally{lock.current=false;setWorking('');}
 };
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
  if(lock.current||onboardingBusy||promptPreview||(!text.trim()&&!files.length)||plans.some(active))return;
  const issue=agentInputIssue(text);if(issue){setError('');setMentionClosed(false);composer.current?.focus();return;}
  const requestedOperation=agentOperation(text);const onboardingRequest=requestedOperation==='onboard';
  if(onboardingRequest&&!catalog.can_onboard_datasets){setError('Only the administrator can onboard datasets.');return;}
  if(unresolvedJson.length){setError('Is each JSON attachment a prompt template or a document? Choose below its filename.');return;}
  if(promptAttachment&&promptAttachment.datasetId!==dataset){setError('Attach the prompt again for the selected dataset.');return;}
  followLatest();
  const savePromptOnly=Boolean(promptAttachment)&&!text.trim()&&!documentFiles.length;
  if(!savePromptOnly&&!effectivePlanner){setError('Choose an Agent Model to continue.');return;}
  const request=text.trim()||(documentFiles.length?'Upload the attached documents.':'');
  lock.current=true;setWorking('Checking processing permissions…');setError('');let permission:ConsentReceipt|null=null;
  try{if(!savePromptOnly&&!onboardingRequest){const roles=['chat'];if(dataset&&(documentFiles.length||requestedOperation==='extract'||requestedOperation==='reextract')){roles.push('embedding');if(savedPromptId||promptAttachment||requestedOperation==='extract'||requestedOperation==='reextract')roles.push('extraction');}permission=await consent.request({dataset_id:dataset,planner_model_id:effectivePlanner,roles});}}
  catch(e){setError(e instanceof Error?e.message:'Could not check processing permissions.');return;}
  finally{lock.current=false;setWorking('');}
  if(!savePromptOnly&&!onboardingRequest&&!permission)return;const external=Boolean(permission?.required);
  const outgoing=files;let answering=false,accepted=false;let receipt:PromptProgress['receipt'];lock.current=true;setRequestStartedAt(Date.now());setPendingRequest(request);setPendingFiles(outgoing);setFiles([]);setText('');setWorking(promptAttachment&&!promptAttachment.savedId&&!onboardingRequest?'Saving prompt.':'Checking workspace and request.');setError('');
  if(promptAttachment&&!onboardingRequest)setPromptProgress({name:promptAttachment.fileName,phase:promptAttachment.savedId?'preparing':'saving'});else setPromptProgress(null);
  try{
   let attachedTemplateId=promptAttachment?.savedId||savedPrompt?.id||retrySubmittedPrompt.current||'';
   if(promptAttachment&&!promptAttachment.savedId&&!onboardingRequest){
     const imported=await api('/templates','POST',{name:promptAttachment.name,schema:promptAttachment.schema,instructions:promptAttachment.instructions||'',dataset_id:dataset,source_filename:promptAttachment.fileName},undefined,true);
     attachedTemplateId=imported.id;setPromptAttachment({...promptAttachment,savedId:imported.id});setPromptNotice(`Saved "${imported.name}" · Version ${imported.version||1}. This prompt is selected for extraction.`);
     receipt={name:imported.name,version:imported.version||1};setPromptProgress({name:imported.name,receipt,phase:'preparing'});setWorking('Preparing request.');
    rememberSavedPrompt(sessionStorage,key+'-prompts',dataset,imported.id);rememberAssistantDataset(sessionStorage,username,dataset);setSavedPromptId(imported.id);
     onPromptSaved?.(imported);
    await loadCatalog();
   }
    if(savePromptOnly){accepted=true;setPromptAttachment(null);setPromptProgress({name:promptAttachment!.fileName,receipt:receipt||{name:promptAttachment!.fileName,version:savedPrompt?.version||1},phase:'saved'});return;}
   const previous=plans.at(-1);const unfinished=!requestedOperation&&previous&&previous.dataset_id===dataset&&!previous.superseded&&!previous.calls.some((call:Entity)=>call.status==='failed')&&previous.calls.some((call:Entity)=>call.status==='pending')?previous:null;
   const references=unfinished?.calls.flatMap((call:Entity)=>call.uploaded_document_ids||[])||[];
   const inherited=unfinished?.calls.some((call:Entity)=>call.tool==='upload'&&call.status==='pending')?submittedFiles.current[unfinished.id]||[]:[];
   const combined=documentFiles.length?mergeAgentAttachments(inherited,documentFiles,maxUploadMb):{files:inherited,error:''};if(combined.error)throw new Error(combined.error);
   const workflowFiles=combined.files;
   const earlierRequest=unfinished?`${unfinished.request}\nPending tools from the unfinished plan: ${unfinished.calls.filter((call:Entity)=>call.status==='pending').map((call:Entity)=>call.tool).join(', ')}`.slice(0,12000):'';
   const plan=await api('/agent-v2/plans','POST',{text:request,agent_operation:requestedOperation||null,stream_answers:true,conversation_id:conversations.current[dataset||'general']||'',earlier_request:earlierRequest,completed_tools:unfinished?.calls.filter((call:Entity)=>call.status==='completed').map((call:Entity)=>call.tool)||[],attached_filenames:workflowFiles.map(file=>file.name),planner_model_id:effectivePlanner,dataset_id:unfinished?.dataset_id||dataset,document_ids:onboardingRequest?[]:references.length?references:unfinished?.document_ids||documents,answer_scope:documents.length?'documents':'auto',template_id:onboardingRequest?'':attachedTemplateId||unfinished?.template_id||'',submitted_prompt_id:onboardingRequest?'':promptAttachment?attachedTemplateId:retrySubmittedPrompt.current,allow_external:external},undefined,true);
   if(retryPlanId.current){const retried=retryPlanId.current;setPlans(previous=>previous.map(item=>item.id===retried?{...item,superseded:true}:item));}
   retrySubmittedPrompt.current='';retryPlanId.current='';
   if(permission)approvals.current[plan.id]=permission;
   accepted=true;plan.messageAttachments=[...inherited,...outgoing].map(file=>({name:file.name,size:file.size}));
   if(plan.phase==='queued'||plan.calls.some((call:Entity)=>call.tool==='upload'))submittedFiles.current[plan.id]=workflowFiles;
   if(onboardingRequest&&promptAttachment)submittedOnboardingPrompts.current[plan.id]=promptAttachment;
   if(unfinished&&plan.calls.length)delete submittedFiles.current[unfinished.id];
   setPromptAttachment(null);setJsonDocuments({});setAttachmentErrors({});
   if(plan.calls.length)setPlans(existing=>existing.map(item=>({...item,superseded:!active(item)&&item.calls.some((call:Entity)=>call.status==='pending')})));
   const ids=plans.filter(p=>!p.historical).map(p=>p.id).concat(plan.id).slice(-30);sessionStorage.setItem(key+'-history',JSON.stringify(ids));sessionStorage.setItem(key,plan.id);replacePlan(plan);setPendingRequest('');setPendingFiles([]);setPromptProgress(null);
   if(plan.calls.length)return;
   answering=true;setWorking('Answering…');const connectedAt=Date.now();update(plan.id,{chat:{text:'',status:'streaming',citations:[]},answer_workflow:{status:'running',started_at:connectedAt,steps:[{id:'connecting',label:'Connecting to agent',status:'running',started_at:connectedAt}]}});
   const controller=new AbortController();answerController.current=controller;
   const response=await stream(`/agent-v2/plans/${plan.id}/reply`,{conversation_id:conversations.current[conversationScope(plan)]||'',document_model_id:planner||null,allow_external:external},controller.signal);
   if(!response.ok){const data=await response.json();throw new Error(typeof data.detail==='string'?data.detail:'The answer could not start.');}
   if(!response.body)throw new Error('The answer stream is unavailable.');
   let answer='';
   await readChatStream(response.body,({type,payload})=>{
    if(type==='progress')update(plan.id,{answer_workflow:payload.workflow});
    if(type==='delta'){answer+=payload.text||'';update(plan.id,{chat:{text:answer,status:'streaming',citations:[]}});}
    if(type==='done'){
     if(payload.message?.request_route?.decision?.intent==='clarify'&&workflowFiles.length){
      setFiles(previous=>mergeAgentAttachments(previous,workflowFiles,maxUploadMb).files);
      setJsonDocuments(previous=>({...previous,...Object.fromEntries(workflowFiles.filter(isJsonAttachment).map(file=>[attachmentKey(file),true]))}));
     }
     conversations.current[conversationScope(plan)]=payload.conversation_id;
     if(payload.plan){
      const finished={...payload.plan,chat:payload.plan.calls.length?undefined:payload.message};
      if(finished.calls.length){setPlans(previous=>previous.map(item=>item.id!==plan.id?{...item,superseded:!active(item)&&item.calls.some((call:Entity)=>call.status==='pending')}:item));if(unfinished)delete submittedFiles.current[unfinished.id];}
      else if(!finished.onboarding)delete submittedFiles.current[plan.id];
      replacePlan(finished);
     }else update(plan.id,{chat:payload.message,answer_workflow:payload.message.answer_workflow,conversation_id:payload.conversation_id});
    }
    if(type==='error'){update(plan.id,{chat:payload.message,answer_workflow:payload.message.answer_workflow});throw new Error(payload.detail);}
   });
  }catch(e){
   if(!accepted&&promptAttachment&&!onboardingRequest)setPromptProgress({name:promptAttachment.fileName,receipt,phase:receipt?'prepare_failed':'save_failed',error:e instanceof Error?e.message:'The request could not finish.'});
   if(!accepted){setText(current=>current||request);setFiles(current=>mergeAgentAttachments(outgoing,current,maxUploadMb).files);}
   if(!(e instanceof Error&&e.name==='AbortError'))setError(e instanceof Error?e.message:'The request could not finish.');
   const id=sessionStorage.getItem(key);if(answering&&id){
    setPlans(previous=>previous.map(p=>p.id===id&&p.chat?.status==='streaming'?{...p,chat:{...p.chat,status:e instanceof Error&&e.name==='AbortError'?'aborted':'failed'},answer_workflow:p.answer_workflow?{...p.answer_workflow,status:e instanceof Error&&e.name==='AbortError'?'aborted':'failed',steps:p.answer_workflow.steps.map((s:Entity)=>s.status==='running'?{...s,status:e instanceof Error&&e.name==='AbortError'?'cancelled':'failed',duration_ms:Math.max(0,Date.now()-s.started_at)}:s)}:undefined}:p));
    try{const saved=await api(`/agent-v2/plans/${id}`,'GET',undefined,undefined,true);if(saved.chat)replacePlan(saved);if(saved.conversation_id)conversations.current[conversationScope(saved)]=saved.conversation_id;}catch{}
   }
  }
  finally{answerController.current=null;lock.current=false;if(mounted.current){setPendingRequest('');setPendingFiles([]);setWorking('');}}
 };
 const retryAnswer=(plan:Entity)=>{
  if(attachmentsBlocked)return;
  const retained=submittedFiles.current[plan.id]||[];
  const result=retained.length?mergeAgentAttachments(files,retained,maxUploadMb):{files,error:''};
  if(result.error){setError(result.error);return;}
  setDataset(plan.dataset_id||'');setDocuments(plan.document_ids||[]);setPlanner(plan.planner.id||'');
  retrySubmittedPrompt.current=plan.submitted_prompt_id||'';
  retryPlanId.current=plan.id;
  rememberSavedPrompt(sessionStorage,key+'-prompts',plan.dataset_id||'',plan.template_id||'');setSavedPromptId(plan.template_id||'');
  setFiles(result.files);setText(plan.request);setError(plan.attached_filenames?.length&&!retained.length?'Attach the files again to retry this request.':'');
  followLatest();composer.current?.focus();
 };
 const toggleMic=()=>{
  if(listening){recognition.current?.stop();return;}
  try{recognition.current=startSpeechInput(window as unknown as SpeechEnvironment,{text:transcript=>{if(mounted.current)setText(previous=>`${previous}${previous?' ':''}${transcript}`);},listening:value=>{if(mounted.current)setListening(value);},error:message=>{if(mounted.current)setError(message);}},navigator.language||'en-US');}catch(e){setError(e instanceof Error?e.message:'Could not start the microphone. Check browser permissions.');}
 };
 const readyDocuments=readyDatasetDocuments(catalog.documents,dataset);
 const mention=!mentionClosed&&!working&&!plans.some(active)?documentMention(text,caret):null;
 const commandMention=!mentionClosed&&!working&&!plans.some(active)?agentMention(text,caret):null;
 const commandOptions=commandMention?agentCommands.filter(command=>(command.operation!=='onboard'||catalog.can_onboard_datasets)&&command.label.slice(1).toLowerCase().startsWith(commandMention.query.toLowerCase())):[];
 const inputIssue=agentInputIssue(text);
 const displayedChatError=Boolean(error)&&plans.some(plan=>plan.chat?.error?.detail===error&&(!plan.goal||!plan.calls.some((call:Entity)=>call.started_at)));
 const mentionDocuments=mention?matchingDocuments(readyDocuments,mention.query):[];
 useEffect(()=>{if(mention&&mentionDocuments[mentionIndex])document.getElementById(`agent-document-option-${mentionDocuments[mentionIndex].id}`)?.scrollIntoView({block:'nearest'});},[mentionIndex,mention?.query]);
 useEffect(()=>{if(!mention&&!commandMention)return;const dismiss=(e:PointerEvent)=>{if(!(e.target instanceof Element)||!e.target.closest('.agent-v2-composer'))setMentionClosed(true);};document.addEventListener('pointerdown',dismiss);return()=>document.removeEventListener('pointerdown',dismiss);},[Boolean(mention),Boolean(commandMention)]);
 useEffect(()=>{if(!catalog.models.length)return;setPlanner(current=>chatModels.some((m:Entity)=>m.id===current)?current:chatModels.find((m:Entity)=>m.id===datasetConfig?.default_chat_model_id)?.id||chatModels[0]?.id||'');},[catalog,dataset]);
 const chooseMention=(doc:Entity)=>{
  if(!mention)return;if(!documents.includes(doc.id)&&documents.length>=20){setError('Choose at most 20 documents.');return;}
  setDocuments(previous=>previous.includes(doc.id)?previous:[...previous,doc.id]);
  const next=text.slice(0,mention.start)+text.slice(mention.end);setText(next);setCaret(mention.start);setMentionClosed(true);setMentionIndex(0);
  requestAnimationFrame(()=>{composer.current?.focus();composer.current?.setSelectionRange(mention.start,mention.start);});
 };
 const chooseCommand=(command:typeof agentCommands[number])=>{
  if(!commandMention)return;
  const next=insertAgentCommand(text,commandMention,command.label),position=commandMention.start+command.label.length+1;
  setText(next);setCaret(position);setMentionClosed(true);setMentionIndex(0);
  requestAnimationFrame(()=>{composer.current?.focus();composer.current?.setSelectionRange(position,position);});
 };
 const commandToken=/^(\s*)(@\S+)(?=\s|$)/.exec(text);
 const highlightedCommand=commandToken&&agentCommands.some(command=>command.label.toLowerCase()===commandToken[2].toLowerCase())?commandToken:null;
 return <section className={`agent-v2${dragging?' agent-v2-dragging':''}`} aria-label="Aegis Agent conversation" onDragEnter={onFileDragEnter} onDragOver={onFileDragOver} onDragLeave={onFileDragLeave} onDrop={onFileDrop}>
  {dragging&&<div className="agent-v2-drop-overlay" role="status"><UploadCloud size={36}/><strong>{attachmentsBlocked?'Finish the current workflow first':'Drop documents here'}</strong><span>{attachmentsBlocked?'You can attach files when it finishes.':`PDF, DOCX, TXT, JSON · up to 20 files · ${maxUploadMb} MB each`}</span></div>}
  <header className="agent-v2-context">
   <label>Dataset<select aria-label="Agent dataset" value={dataset} disabled={attachmentsBlocked||(!catalogLoaded.current&&catalogLoading)} onChange={e=>{if(e.target.value===dataset)return;retrySubmittedPrompt.current='';retryPlanId.current='';setPromptProgress(null);setDataset(e.target.value);sessionStorage.setItem(key+'-dataset',e.target.value);setSavedPromptId('');setDocuments([]);setMentionClosed(true);cancelPrompt();setPromptAttachment(null);setPromptNotice('');}}><option value="">{!catalogLoaded.current?(catalogLoading?'Loading datasets…':catalogError?'Datasets unavailable':'General chat'):'General chat'}</option>{catalog.datasets.map((d:Entity)=><option key={d.id} value={d.id}>{d.name}</option>)}</select></label>
   {dataset&&<AgentDocumentFilter key={dataset} documents={readyDocuments} selected={documents} onChange={setDocuments} disabled={Boolean(working)||onboardingBusy||plans.some(active)}/>}
   {catalog.can_onboard_datasets&&<button className="btn agent-v2-onboard" aria-label="Onboard dataset in Aegis Agent" disabled={attachmentsBlocked} onClick={()=>{setOnboardingOpen(true);followLatest();}}><Database size={16}/>Onboard dataset</button>}
   <button className="btn icon" aria-label="Agent chat history" title="Chat history" disabled={Boolean(working)||onboardingBusy||plans.some(active)} onClick={()=>void api('/conversations','GET',undefined,undefined,true).then(result=>{setHistory(result);setHistoryOpen(!historyOpen);}).catch(e=>setError(e.message))}><History size={18}/></button>
   <button className="btn icon" aria-label="New agent conversation" title="New conversation" disabled={Boolean(working)||onboardingBusy||plans.some(active)||!scopeReady} onClick={clearConversation}><Plus size={18}/></button>
   <button className="btn agent-v2-clear-chat" aria-label="Clear agent chat" title="Clear the current chat. Saved chats remain in history." disabled={Boolean(working)||onboardingBusy||plans.some(active)||!scopeReady||(!plans.length&&!pendingRequest)} onClick={clearConversation}><Eraser size={16}/><span>Clear chat</span></button>
  </header>
  {historyOpen&&<div className="agent-v2-history"><strong>Saved chats · shared with Aegis Agent</strong><button className="text-button" onClick={()=>setHistoryOpen(false)}>Close</button>{history.length?history.map(c=><button className="text-button" key={c.id} onClick={()=>void api(`/conversations/${c.id}`,'GET',undefined,undefined,true).then(conversation=>{restoreConversation(conversation);sessionStorage.setItem(key+'-conversation',c.id);sessionStorage.removeItem(key);sessionStorage.removeItem(key+'-history');setHistoryOpen(false);setError('');}).catch(e=>setError(e.message))}>{c.title||c.name}</button>):<p>No saved chats yet.</p>}</div>}
  <div ref={thread} className="agent-v2-thread" aria-label="Agent conversation" tabIndex={0} onScroll={event=>{const area=event.currentTarget;const bottom=area.scrollHeight-area.scrollTop-area.clientHeight<64;followBottom.current=bottom;setShowLatest(!bottom);}}>
   {onboardingOpen&&catalog.can_onboard_datasets&&<AgentOnboarding initialDocuments={documentFiles} initialPrompt={promptAttachment||undefined} onReview={onReview} api={api} models={catalog.models} defaults={datasetConfig} storageKey={key+'-onboarding'} onBusy={setOnboardingBusy} onReady={()=>{onWorkspaceChanged?.();void loadCatalog().catch(e=>setError(e.message));}} onUse={id=>{setDataset(id);setDocuments([]);setSavedPromptId('');rememberAssistantDataset(sessionStorage,username,id);setOnboardingOpen(false);sessionStorage.removeItem(key+'-onboarding');sessionStorage.removeItem(key+'-onboarding-request');}} onClose={completed=>{setOnboardingOpen(false);if(completed){sessionStorage.removeItem(key+'-onboarding');sessionStorage.removeItem(key+'-onboarding-request');}}}/>}
   {catalogError&&<div className="agent-v2-catalog-error" role="alert"><span>Could not load datasets and models. {catalogError}</span><button className="btn" disabled={catalogLoading} onClick={()=>{setError('');setCatalogAttempt(value=>value+1);}}>Retry datasets and models</button></div>}
   {!plans.length&&!onboardingOpen&&<div className="agent-v2-welcome"><AgentLogo size={64} label="Aegis Agent"/>{!scopeReady?<p role="status">{catalogError?'Workspace choices are unavailable. Retry loading above.':'Preparing your workspace…'}</p>:<><h2>How can I help?</h2><p>Ask about Aegis, search indexed documents and saved results, or onboard and extract in one conversation.</p><div className="agent-v2-suggestions">{['What can you do?','Summarize the key points','Upload and extract documents'].map(s=><button key={s} className="btn" onClick={()=>setText(s)}>{s}</button>)}</div></>}</div>}
   {plans.map(plan=>{
    const index=nextCall(plan);const call=index>=0?plan.calls[index]:null;
    const needInputs=call?.status==='pending'&&!plan.superseded;const uploaded=plan.calls.some((c:Entity)=>c.uploaded_document_ids?.length);
    const boundFiles=submittedFiles.current[plan.id];const uploadFiles=boundFiles?.length?boundFiles:documentFiles;
    const docs=catalog.documents.filter((d:Entity)=>d.parent_id===plan.dataset_id);
    const templates=catalog.templates.filter((t:Entity)=>!t.parent_id||t.parent_id===plan.dataset_id);
    const count=call?.tool==='upload'?uploadFiles.length:(plan.recovery_document_ids?.length?plan.document_ids.length:plan.calls.flatMap((c:Entity)=>c.uploaded_document_ids||[]).length||plan.document_ids.length);
    const hasExtraction=plan.calls.some((c:Entity)=>c.tool!=='upload');
    const failed=plan.calls.some((c:Entity)=>c.status==='failed');
    return <article key={plan.id} className="agent-v2-exchange"><AgentRequest text={plan.request} attachments={plan.messageAttachments||(plan.attached_filenames||[]).map((name:string)=>({name}))}/><div className="agent-v2-response"><div className="agent-v2-speaker"><AgentLogo size={24}/><strong>Aegis Agent</strong><AgentAnswerWorkflow workflow={['queued','running','retry_wait'].includes(plan.goal?.status)?goalWorkflow(plan):plan.answer_workflow||plan.chat?.answer_workflow} status={plan.chat?.status||'completed'}/><span title={plan.chat?.model_selection?.model_name||plan.planner.name}>{plan.chat?.model_selection?.model_name||plan.planner.name}</span></div>{(needInputs||(!plan.calls.length&&!plan.chat&&!plan.reply_started))&&<p className="agent-v2-reply">{explainPlan(plan)}</p>}
     {plan.onboarding&&catalog.can_onboard_datasets&&<AgentOnboarding initialDocuments={submittedFiles.current[plan.id]||[]} initialPrompt={submittedOnboardingPrompts.current[plan.id]} onReview={onReview} api={api} models={catalog.models} proposal={plan.onboarding} planId={plan.id} workflowId={plan.onboarding_workflow_id||''} defaults={datasetConfig} storageKey={key+'-onboarding-'+plan.id} onBusy={setOnboardingBusy} onReady={()=>{onWorkspaceChanged?.();void loadCatalog().catch(e=>setError(e.message));void api(`/agent-v2/plans/${plan.id}`,'GET',undefined,undefined,true).then(replacePlan).catch(e=>setError(e.message));}} onUse={id=>{setDataset(id);setDocuments([]);setSavedPromptId('');rememberAssistantDataset(sessionStorage,username,id);}}/>}
     {['onboard_extract','reextract'].includes(plan.agent)&&plan.calls.some((call:Entity)=>call.publication_error)&&<div className="agent-v2-recovery"><p>Processing results are saved. Retry the knowledge update to finish this workflow.</p><button className="btn" disabled={Boolean(working)||onboardingBusy||plans.some(active)} onClick={()=>void retryKnowledge(plan)}>Retry knowledge update</button></div>}
     {plan.prompt_receipt&&<AgentPromptProgress progress={{name:plan.prompt_receipt.name,receipt:plan.prompt_receipt,phase:plan.chat?.status==='completed'||plan.calls.length?'completed':['failed','aborted'].includes(plan.chat?.status)?plan.chat.status:plan.chat?.status==='streaming'?'responding':'preparing'}}/>}
     {plan.chat&&(!plan.goal||!plan.calls.some((c:Entity)=>c.started_at))&&<AgentChatAnswer message={plan.chat} api={api} onError={setError} onReview={onReview} onRecovery={action=>void api(`/agent-v2/plans/${action.workflow_id}`,'GET',undefined,undefined,true).then(workflow=>recover(workflow,action.index,action.action)).catch(e=>setError(e.message))}/>}
     {['failed','aborted'].includes(plan.chat?.status)&&!plan.calls.length&&!plan.superseded&&plan.id===plans.at(-1)?.id&&<button className="text-button" disabled={attachmentsBlocked} onClick={()=>retryAnswer(plan)}>{plan.prompt_receipt?'Retry response':'Retry request'}</button>}
     {plan.conversation_id&&plan.chat?.status==='completed'&&plan.id===plans.at(-1)?.id&&<a className="agent-v2-export" href={`/api/conversations/${plan.conversation_id}/export`} download>Export chat</a>}
     {plan.clarification?.length>0&&needInputs&&<p className="small muted">{plan.clarification.join(' · ')}</p>}
     {hasExtraction&&<p role="status" className="small">{failed?'Extraction workflow needs attention. Successfully uploaded documents are kept.':plan.calls.every((c:Entity)=>c.status==='completed')?'Extraction workflow complete — results are ready for review.':active(plan)?(plan.auto_continue?'Upload → indexing → extraction → review. Extraction starts automatically after indexing.':'Extraction is processing. Completed results appear below for review.'):'Extraction has not completed. Review and confirm the workflow below.'}</p>}
     <WorkflowStepper label="Assistant workflow steps" steps={plan.calls.map((tool:Entity,i:number)=>({id:`${plan.id}:${i}`,label:tool.publication_pending?'Publish updated knowledge':tool.title||({upload:'Upload documents',extract:'Extract fields',reextract:'Re-extract fields'} as Record<string,string>)[tool.tool]||tool.tool,status:tool.status==='waiting'?'running':tool.status,statusLabel:tool.status==='pending'?(plan.calls.slice(0,i).some((c:Entity)=>c.status==='failed')?'Blocked by failed tool':i>index?'Waiting for previous tool':'Awaiting confirmation'):undefined}))}/>
     {!plan.superseded&&!active(plan)&&plan.calls.some((tool:Entity)=>tool.status==='failed'||tool.error)&&!plan.calls.some((tool:Entity)=>tool.submission_uncertain||/status is uncertain/i.test(tool.error||''))&&<div className="agent-v2-restart"><button className="btn primary" disabled={attachmentsBlocked||!(plan.document_ids?.length||plan.calls.some((tool:Entity)=>tool.uploaded_document_ids?.length))||(hasExtraction&&!plan.template_id)} onClick={()=>void recover(plan,0,'restart')}>Restart workflow</button><p className="small muted">Re-read the saved originals, rebuild knowledge, and run every requested step again. Earlier results remain available.</p></div>}
     {plan.calls.length>0&&<ol className="agent-v2-tools">{plan.calls.map((tool:Entity,i:number)=><li key={i} data-status={tool.status}><div className="agent-v2-tool-heading">{tool.status==='completed'?<CheckCircle2 size={17}/>:['waiting','running'].includes(tool.status)?<Loader2 size={17} className="animate-spin"/>:<span className="agent-v2-tool-number">{i+1}</span>}<strong>{tool.title}</strong><code>{tool.tool}</code><span>{tool.status==='pending'?(plan.calls.slice(0,i).some((c:Entity)=>c.status==='failed')?'Blocked by failed tool':i>index?'Waiting for previous tool':'Awaiting confirmation'):tool.status==='waiting'?'Processing':tool.status}</span></div>
      {tool.tool==='upload'&&tool.jobs?.length>0&&<UploadWorkflow call={tool}/>}
      {tool.publication_pending&&<p role="status" className="small">Updated Parquet is saved. Publishing and verifying vector knowledge…</p>}
      {tool.vector_publication&&<p role="status" className="small">Knowledge updated · {tool.vector_publication.provider==='oracle'?'OCI':tool.vector_publication.provider} · {tool.vector_publication.verified_vectors} verified vectors · {tool.vector_publication.parquet_files?.length||0} saved Parquet files.</p>}
      {tool.tool!=='upload'&&tool.jobs?.map((job:Entity)=><AgentJobProgress key={job.id} job={job}/>)}
      {tool.error&&!tool.jobs?.some((job:Entity)=>job.error===tool.error)&&<p role="alert" className="agent-v2-error">{tool.error}</p>}
      <AgentResult tool={tool} onReview={onReview}/>
      {(tool.status==='failed'||(tool.status==='pending'&&tool.error))&&!tool.publication_error&&!plan.superseded&&<div className="agent-v2-recovery"><p className="small">{tool.tool==='upload'?'Upload/indexing stopped. Retry indexing, continue with ready documents, or end this request.':'Extraction stopped; uploaded files are still available. Retry uses current model settings and keeps successful results.'}</p>
       {tool.tool!=='upload'&&/context budget|context limit/i.test(tool.error||'')&&<p className="small">Choose independent extraction or fewer documents below. If current settings are still too small, increase the mapped extraction model’s context limit in Model Registration; then retry. Content will not be silently truncated.</p>}
       {tool.tool!=='upload'&&/timed out/i.test(tool.error||'')&&<p className="small">Increase the extraction model’s Timeout in Model Registration, or use a smaller template/scope, then retry.</p>}
       {tool.tool!=='upload'&&/incomplete/i.test(tool.error||'')&&<p className="small">Increase Maximum output tokens for the extraction model or use a smaller template, then retry. Keep enough context space for both the documents and the answer.</p>}
       {tool.submission_uncertain||/status is uncertain/i.test(tool.error||'')?<a className="btn" href={tool.tool==='upload'?'#Datasets':'#Review'}>Check accepted work before resubmitting</a>:<button className="btn" disabled={attachmentsBlocked} onClick={()=>void recover(plan,i,'retry')}>{tool.tool==='upload'?'Retry failed indexing':'Adjust scope and retry extraction'}</button>}
       {tool.tool==='upload'&&tool.jobs?.some((j:Entity)=>j.status==='completed')&&<button className="btn" disabled={attachmentsBlocked} onClick={()=>void recover(plan,i,'continue_ready')}>Continue with ready documents</button>}
       {tool.tool!=='upload'&&<a className="btn" href="#Model%20Registration">Open Model Registration</a>}
       <button className="text-button" disabled={attachmentsBlocked} onClick={()=>void recover(plan,i,'cancel')}>End this request</button>
      </div>}
     </li>)}</ol>}
     {needInputs&&<div className="agent-v2-details"><strong>A few details to continue</strong><label>Dataset<select aria-label="Workflow dataset" value={plan.dataset_id} disabled={uploaded} onChange={e=>update(plan.id,{dataset_id:e.target.value,document_ids:[],template_id:''})}><option value="">Choose a dataset</option>{catalog.datasets.map((d:Entity)=><option key={d.id} value={d.id}>{d.name}</option>)}</select></label>
      {call.tool!=='upload'&&(!uploaded||plan.recovery_document_ids)&&<label>Documents · choose up to 20<select aria-label="Workflow documents" multiple size={Math.min(4,Math.max(2,docs.length))} value={plan.document_ids} onChange={e=>update(plan.id,{document_ids:Array.from(e.target.selectedOptions).map(o=>o.value).slice(0,20)})}>{docs.filter((d:Entity)=>!plan.recovery_document_ids||plan.recovery_document_ids.includes(d.id)).map((d:Entity)=><option key={d.id} value={d.id}>{d.name}{docs.filter((other:Entity)=>other.name===d.name).length>1?` · ${new Date(d.created_at*1000).toLocaleString()}`:''}{d.status!=='ready'?` · ${d.status}`:''}</option>)}</select></label>}
      {plan.calls.some((c:Entity)=>c.tool!=='upload')&&<label>Prompt template<select aria-label="Workflow prompt template" value={plan.template_id} onChange={e=>update(plan.id,{template_id:e.target.value})}><option value="">Choose a template</option>{templates.map((t:Entity)=><option key={t.id} value={t.id}>{t.name}</option>)}</select></label>}
      {call.tool==='upload'&&<p className="small">{uploadFiles.length?`${uploadFiles.length} files attached to this request.`:'Attach the original files again to confirm upload.'}</p>}
      {hasExtraction&&count>1&&<label>How should these {count} documents be extracted?<select aria-label="Extraction mode" value={plan.extraction_mode||''} onChange={e=>update(plan.id,{extraction_mode:e.target.value})}><option value="">Choose single or independent extraction</option><option value="merge">Single extraction — merge files into one result</option><option value="independent">Extract independently - one result per document</option></select><span className="small muted">Merge creates one extraction ID and retains every original file. Independent creates a separate extraction ID per document.</span></label>}
      {hasExtraction&&plan.extraction_mode==='merge'&&<label>What do the merged files contain?<select aria-label="Merged content" value={plan.merge_strategy||'records'} onChange={e=>update(plan.id,{merge_strategy:e.target.value})}><option value="records">Different profiles or items — keep every file's fields</option><option value="single">Parts of the same profile or item — combine fields</option></select><span className="small muted">Separate profiles are extracted one source at a time and collected into one result, so one person's name cannot replace the others. Each source still follows your template.</span></label>}
      {hasExtraction&&<label>Extraction name<input aria-label="Extraction name" maxLength={200} placeholder={count>1?`Merged extraction - ${count} documents`:(uploadFiles[0]?.name?.replace(/\.[^.]+$/, '')||'Document extraction')} value={plan.display_name||''} onChange={e=>update(plan.id,{display_name:e.target.value})}/><span className="small muted">Leave blank to use the suggested name.</span></label>}
      <p className="small muted">{call.tool==='upload'&&hasExtraction?'Confirm once to upload, index and extract with the selected template and mode. Any failure pauses the workflow.':call.tool!=='upload'&&docs.some((doc:Entity)=>plan.document_ids.includes(doc.id)&&doc.requires_reindex)?'Selected documents need their indexes rebuilt. Confirm once to reindex them, then extract with the selected template. Originals and earlier results are retained.':'Review the selected dataset, files and template, then confirm. Outdated document indexes will be rebuilt automatically before extraction.'} {plan.goal&&'After processing, Aegis will inspect the saved results and finish your original request, even if you close this page.'}</p>
      <button className="btn primary" disabled={attachmentsBlocked||!plan.dataset_id||(hasExtraction&&count>1&&!plan.extraction_mode)||(call.tool==='upload'?(!uploadFiles.length||(!boundFiles?.length&&Boolean(unresolvedJson.length))||(hasExtraction&&!plan.template_id)):(!count||!plan.template_id))} onClick={()=>void perform(plan,index)}>{call.tool==='upload'?(hasExtraction?(plan.calls.some((c:Entity)=>c.tool==='reextract')?'Confirm upload and re-extraction':'Confirm upload and extraction'):'Confirm upload'):call.tool==='reextract'?'Confirm re-extraction':'Confirm extraction'}</button>
     </div>}
     {plan.calls.some((call:Entity)=>['running','waiting'].includes(call.status))&&<button className="text-button" onClick={()=>void api(`/agent-v2/plans/${plan.id}`,'GET',undefined,undefined,true).then(replacePlan).catch(e=>setError(e.message))}>Check status</button>}
     {plan.superseded&&<p className="small muted">Replaced by your next request. Pending tools will not start.</p>}
     {plan.goal?.answer&&<><div className="agent-v2-speaker"><AgentLogo size={20}/><strong>Aegis Agent</strong><AgentAnswerWorkflow workflow={plan.goal.answer.answer_workflow} status={plan.goal.answer.status}/></div><AgentChatAnswer message={plan.goal.answer} api={api} onError={setError} onReview={onReview}/></>}
    </div></article>;
   })}
   {(pendingRequest||pendingFiles.length>0)&&<AgentRequest text={pendingRequest} attachments={pendingFiles.map(file=>({name:file.name,size:file.size}))} pending/>}
   {promptProgress&&<AgentPromptProgress progress={promptProgress}/>}
   {working&&pendingRequest&&!promptProgress&&<div className="agent-v2-speaker"><AgentLogo size={24}/><strong>Aegis Agent</strong><AgentAnswerWorkflow workflow={{status:'running',started_at:requestStartedAt,steps:[{id:'submitting',label:'Submitting request',status:'running',started_at:requestStartedAt}]}}/></div>}
   {working&&!pendingRequest&&!plans.some(p=>p.chat?.status==='streaming')&&<p className="agent-v2-working" role="status"><Loader2 size={15} className="animate-spin"/>{working}</p>}
   {error&&!displayedChatError&&<p className="agent-v2-error" role="alert">{error}</p>}<div ref={end}/>
  </div>
  <div className="agent-v2-composer" ref={composerContainer}>
   {showLatest&&<button className="agent-v2-latest btn" aria-label="Scroll to latest message" onClick={followLatest}><ArrowDown size={16}/>Latest message</button>}
   {savedPrompt&&!promptAttachment&&<div className="agent-v2-selected-documents" aria-label="Selected saved prompt"><span>Prompt: {savedPrompt.name}<button aria-label="Clear selected prompt" disabled={attachmentsBlocked} onClick={clearSavedPrompt}><X size={12}/></button></span></div>}
   {documents.length>0&&<div className="agent-v2-selected-documents" aria-label="Selected document filters">{documents.map(id=>{const doc=readyDocuments.find((d:Entity)=>d.id===id);return doc?<span key={id} title={documentOptionLabel(doc,readyDocuments)}>{documentOptionLabel(doc,readyDocuments)}<button aria-label={`Remove document ${documentOptionLabel(doc,readyDocuments)}`} disabled={Boolean(working)||onboardingBusy||plans.some(active)} onClick={()=>setDocuments(previous=>previous.filter(value=>value!==id))}><X size={12}/></button></span>:null;})}<button className="text-button" disabled={Boolean(working)||onboardingBusy||plans.some(active)} onClick={()=>setDocuments([])}>Clear filter</button></div>}
   {mention&&<div className="agent-v2-mention-popover agent-v2-document-popover"><div className="agent-v2-picker-heading"><strong>Documents in this dataset</strong><button className="btn icon" aria-label="Close document suggestions" onClick={()=>{setMentionClosed(true);composer.current?.focus();}}><X size={15}/></button></div><div id="agent-document-mentions" role="listbox" aria-label="Dataset document suggestions" className="agent-v2-document-options">{mentionDocuments.map((doc:Entity,index:number)=><button type="button" role="option" id={`agent-document-option-${doc.id}`} key={doc.id} aria-selected={index===mentionIndex} onMouseDown={e=>e.preventDefault()} onClick={()=>chooseMention(doc)}><span>{documentOptionLabel(doc,readyDocuments)}</span>{documents.includes(doc.id)&&<CheckCircle2 size={14}/>}</button>)}{!mentionDocuments.length&&<p>{dataset?'No matching ready documents.':'Choose a dataset to see its documents.'}</p>}</div><p className="muted small">↑ ↓ to browse · Enter to select · Esc to close</p></div>}
   {commandMention&&<div className="agent-v2-mention-popover agent-v2-document-popover agent-v2-command-popover"><div className="agent-v2-picker-heading"><strong>Choose an agent</strong><button className="btn icon" aria-label="Close agent suggestions" onClick={()=>{setMentionClosed(true);composer.current?.focus();}}><X size={15}/></button></div><div id="agent-command-mentions" role="listbox" aria-label="Agent shortcuts" className="agent-v2-document-options">{commandOptions.map((command,index)=><button type="button" role="option" id={`agent-command-${command.operation}`} key={command.operation} aria-selected={index===mentionIndex} onMouseDown={event=>event.preventDefault()} onClick={()=>chooseCommand(command)}>{command.operation==='onboard'?<Database size={18}/>:command.operation==='upload'?<UploadCloud size={18}/>:command.operation==='reextract'?<RotateCcw size={18}/>:<FileText size={18}/>}<span><strong>{command.label}</strong><small>{command.description}</small></span></button>)}{!commandOptions.length&&<p>Choose an available agent from the menu.</p>}</div><p className="muted small">↑ ↓ to browse · Enter to select · Esc to close</p></div>}
   <div className="agent-v2-compose-box">
    {files.length>0&&<div className="agent-v2-files" aria-label="Attached files">{files.map(file=>{
     const id=attachmentKey(file);const json=isJsonAttachment(file);const prompt=promptAttachment?.fileKey===id;
     return <div className={`agent-v2-file-card${json?' agent-v2-json-card':''}`} key={id}><FileText size={20}/><span><strong title={file.name}>{file.name}</strong><small>{attachmentSize(file.size)}{json?` · ${prompt?(promptAttachment.savedId?'Saved prompt':'Prompt template'):jsonDocuments[id]?'Document':'Choose file type'}`:''}</small>{json&&<span className="agent-v2-json-choice" role="group" aria-label={`Use ${file.name} as`}><button type="button" aria-pressed={prompt} disabled={attachmentsBlocked} onClick={()=>void chooseJsonPrompt(file)}>Prompt template</button><button type="button" aria-pressed={Boolean(jsonDocuments[id])} disabled={attachmentsBlocked} onClick={()=>chooseJsonDocument(file)}>Document</button></span>}{attachmentErrors[id]&&<span className="agent-v2-attachment-error" role="alert">{attachmentErrors[id]}</span>}</span><button aria-label={`Remove attachment ${file.name}`} disabled={attachmentsBlocked} onClick={()=>removeAttachment(file)}><X size={14}/></button></div>;
    })}<button className="text-button" disabled={attachmentsBlocked} onClick={()=>{setFiles([]);setJsonDocuments({});setAttachmentErrors({});setPromptAttachment(null);clearSavedPrompt();cancelPrompt();}}>Clear files</button></div>}
    <div className="agent-v2-input"><div className="agent-v2-editor">
    <div ref={composerHighlight} className="agent-v2-input-highlight" aria-hidden="true">{highlightedCommand?<>{highlightedCommand[1]}<span className="agent-v2-command-token">{highlightedCommand[2]}</span>{text.slice(highlightedCommand[0].length)}</>:text}{text.endsWith('\n')?' ':''}</div>
    <textarea ref={composer} aria-label="Message Aegis Agent" placeholder="Ask anything · @ agents · # documents" value={text} rows={1} aria-autocomplete="list" aria-expanded={Boolean(mention||commandMention)} aria-controls={commandMention?'agent-command-mentions':mention?'agent-document-mentions':undefined} aria-activedescendant={commandMention&&commandOptions[mentionIndex]?`agent-command-${commandOptions[mentionIndex].operation}`:mentionDocuments[mentionIndex]?`agent-document-option-${mentionDocuments[mentionIndex].id}`:undefined} onScroll={e=>{if(composerHighlight.current){composerHighlight.current.scrollTop=e.currentTarget.scrollTop;composerHighlight.current.scrollLeft=e.currentTarget.scrollLeft;}}} onSelect={e=>setCaret(e.currentTarget.selectionStart)} onChange={e=>{setText(e.target.value);setCaret(e.target.selectionStart);setMentionClosed(false);setMentionIndex(0);}} onKeyDown={e=>{
     if(commandMention){
      if(e.key==='Escape'){e.preventDefault();setMentionClosed(true);return;}
      if(e.key==='ArrowDown'||e.key==='ArrowUp'){e.preventDefault();setMentionIndex(index=>commandOptions.length?(index+(e.key==='ArrowDown'?1:-1)+commandOptions.length)%commandOptions.length:0);return;}
      if(e.key==='Enter'&&!e.shiftKey&&!e.nativeEvent.isComposing){e.preventDefault();if(commandOptions[mentionIndex])chooseCommand(commandOptions[mentionIndex]);return;}
     }
     if(mention){
      if(e.key==='Escape'){e.preventDefault();setMentionClosed(true);return;}
      if(e.key==='ArrowDown'||e.key==='ArrowUp'){e.preventDefault();setMentionIndex(index=>mentionDocuments.length?(index+(e.key==='ArrowDown'?1:-1)+mentionDocuments.length)%mentionDocuments.length:0);return;}
      if(e.key==='Enter'&&!e.shiftKey&&!e.nativeEvent.isComposing){e.preventDefault();if(mentionDocuments[mentionIndex])chooseMention(mentionDocuments[mentionIndex]);return;}
     }
     if(e.key==='Enter'&&!e.shiftKey&&!e.nativeEvent.isComposing){e.preventDefault();void send();}
    }}/></div></div>
    <div className="agent-v2-compose-controls">
     <input ref={fileInput} type="file" hidden multiple accept=".pdf,.docx,.txt,.json" onChange={e=>{attachFiles(Array.from(e.target.files||[]));e.target.value='';}}/>
     <button className="btn icon" aria-label="Attach documents for agent" title="Attach PDF, DOCX, TXT or JSON" disabled={attachmentsBlocked} onClick={()=>fileInput.current?.click()}><Plus size={21}/></button>
     <label className="agent-v2-model-control"><span>Agent Model</span><select aria-label="Agent Model" value={effectivePlanner} disabled={Boolean(working)||onboardingBusy||plans.some(active)||(!catalogLoaded.current&&catalogLoading)} onChange={e=>setPlanner(e.target.value)}><option value="">{!catalogLoaded.current?(catalogLoading?'Loading models…':catalogError?'Models unavailable':'Choose an Agent Model'):'Choose an Agent Model'}</option>{chatModels.map((m:Entity)=><option key={m.id} value={m.id}>{m.name}</option>)}</select></label>
     <div className="agent-v2-send-controls">
      <button className={`btn icon${listening?' primary':''}`} aria-label={listening?'Stop listening':'Speak your request'} title={voiceSupported?'Speech input':'Speech input unavailable in this browser'} disabled={!voiceSupported||Boolean(working)} onClick={toggleMic}><Mic size={20}/></button>
      {working&&answerController.current?<button className="btn icon agent-v2-send" aria-label="Stop answer" onClick={()=>answerController.current?.abort()}><Square size={18}/></button>:<button className="btn icon agent-v2-send" aria-label="Send agent request" disabled={(!text.trim()&&!files.length)||Boolean(mention||commandMention)||attachmentsBlocked||Boolean(unresolvedJson.length)||Boolean(inputIssue)} onClick={()=>void send()}><ArrowUp size={21}/></button>}
     </div>
    </div>
   </div>
   {inputIssue&&<p className="agent-v2-prompt-notice" role="status">{inputIssue}</p>}
   {promptNotice&&<p className="agent-v2-prompt-notice" role="status">{promptNotice}</p>}
   <div className="agent-v2-footer"><span>Drag & drop PDF, DOCX, TXT, JSON · up to 20 files</span><details><summary>Privacy & cloud consent</summary><p>Files use your dataset’s storage, embedding and extraction models. Workflow requests and results are saved in your workspace. Browser speech recognition may send audio to its speech service; voice is optional and text remains available.</p><p>When external processing is required, a popup names the destinations and asks for approval before continuing. Approval covers only that request and its confirmed workflow.</p></details></div>
  </div>
  {consent.popup}
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
