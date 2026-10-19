"use client";
import {useEffect,useRef,useState} from 'react';
import {ArrowUp,History,Plus,Square} from 'lucide-react';
import {AgentLogo} from './agent-logo';
import {AgentRequest,AgentChatAnswer} from './agent-v2-chat';
import {DatasetChatStatus} from './dataset-chat-status';
import {readChatStream} from './chat-stream';
import {eligibleAgentModels} from './agent-document-selection';
import type {DatasetKnowledgeScope} from './dataset-knowledge-picker';
import './agent-v2.css';

type Entity=Record<string,any>;
type Api=(path:string,method?:string,body?:unknown,signal?:AbortSignal,quiet?:boolean)=>Promise<any>;
export const knowledgeScopeKey=(scope:DatasetKnowledgeScope)=>JSON.stringify({datasets:[...new Set(scope.datasetIds)].sort(),documents:scope.documentIds===null?null:[...new Set(scope.documentIds)].sort()});
export function DatasetKnowledgeChat({api,stream,username,scope,onBusy,onReview,onOpenAgent,catalogRevision=0}:{api:Api;stream:(path:string,body:unknown,signal:AbortSignal)=>Promise<Response>;username:string;scope:DatasetKnowledgeScope;onBusy?:(busy:boolean)=>void;onReview?:(id:string)=>void;onOpenAgent?:()=>void;catalogRevision?:number}){
 const [catalog,setCatalog]=useState<Entity>({datasets:[],documents:[],models:[]}),[loading,setLoading]=useState(true),[error,setError]=useState('');
 const [model,setModel]=useState(''),[text,setText]=useState(''),[messages,setMessages]=useState<Entity[]>([]),[conversation,setConversation]=useState('');
 const [busy,setBusy]=useState(false),[history,setHistory]=useState<Entity[]|null>(null),[attempt,setAttempt]=useState(0),[restoring,setRestoring]=useState(true);
 const controller=useRef<AbortController|null>(null),locked=useRef(false),mounted=useRef(true),thread=useRef<HTMLDivElement>(null);
 const signature=knowledgeScopeKey(scope),login=typeof sessionStorage==='undefined'?'':sessionStorage.getItem(`aegis-agent-v2:${username}-login-session`)||'preview';
 // This storage namespace and these server threads belong only to Dataset Chat.
 const key=`aegis-dataset-chat:${username}:${login}:${signature}`;
 const dataset=scope.datasetIds.length===1?catalog.datasets.find((item:Entity)=>item.id===scope.datasetIds[0]):undefined;
 const models=eligibleAgentModels(catalog.models,dataset),selectedModel=models.find((item:Entity)=>item.id===model)?.id||models.find((item:Entity)=>item.id===dataset?.default_chat_model_id)?.id||models[0]?.id||'';
 useEffect(()=>{mounted.current=true;return()=>{mounted.current=false;controller.current?.abort();};},[]);
 useEffect(()=>{onBusy?.(busy);return()=>onBusy?.(false);},[busy,onBusy]);
 useEffect(()=>{let stopped=false;setLoading(true);void api('/dataset-chat/catalog','GET',undefined,undefined,true).then(result=>{if(!stopped){setCatalog(result);setError('');}}).catch(e=>{if(!stopped)setError(e.message);}).finally(()=>{if(!stopped)setLoading(false);});return()=>{stopped=true;};},[api,catalogRevision,attempt]);
 useEffect(()=>{let stopped=false;setRestoring(true);const id=sessionStorage.getItem(key);if(id)void api(`/dataset-chat/conversations/${id}`,'GET',undefined,undefined,true).then(saved=>{if(!stopped){if(knowledgeScopeKey({datasetIds:saved.dataset_ids,documentIds:saved.document_ids})!==signature)throw new Error('Saved chat has different dataset knowledge.');setMessages(saved.messages||[]);setConversation(saved.id);}}).catch(e=>{if(!stopped)setError(e.message);}).finally(()=>{if(!stopped)setRestoring(false);});else setRestoring(false);return()=>{stopped=true;};},[api,key,signature]);
 useEffect(()=>{thread.current?.scrollTo({top:thread.current.scrollHeight,behavior:'auto'});},[messages]);
 const send=async(request=text,summary=false)=>{
  if(locked.current||loading||restoring||!request.trim())return;
  if(!selectedModel){setError('Choose an available chat model.');return;}
  if(!scope.datasetIds.length||scope.datasetIds.some(id=>!catalog.datasets.some((item:Entity)=>item.id===id))){setError('Dataset access changed. Refresh your dataset knowledge.');return;}
  if(scope.documentIds!==null&&(!scope.documentIds.length||scope.documentIds.some(id=>!catalog.documents.some((doc:Entity)=>doc.id===id&&scope.datasetIds.includes(doc.parent_id||doc.dataset_id||doc.kb_id)&&doc.status==='ready'&&!doc.requires_reindex)))){setError('Include available indexed files before asking a question.');return;}
  const id='pending-'+Date.now(),abort=new AbortController();controller.current=abort;locked.current=true;setBusy(true);setError('');setText('');
  setMessages(previous=>[...previous,{id:id+'-request',role:'user',text:request,summary},{id,role:'assistant',text:'',status:'streaming',request,summary}]);
  const update=(values:Entity)=>setMessages(previous=>previous.map(message=>message.id===id?{...message,...values}:message));
  try{
   const response=await stream('/dataset-chat/reply',{text:request,dataset_ids:scope.datasetIds,document_ids:scope.documentIds,model_id:selectedModel,conversation_id:conversation,summary},abort.signal);
   if(!response.ok){const data=await response.json();throw new Error(typeof data.detail==='string'?data.detail:'Dataset chat could not start.');}
   if(!response.body)throw new Error('The answer stream is unavailable.');
   await readChatStream(response.body,({type,payload})=>{
    if(type==='progress')update({answer_workflow:payload.workflow});
    if(type==='sources')update({source_summary:payload.source_summary});
    if(type==='error')throw new Error(payload.detail||'Dataset chat could not finish.');
    if(type==='done'){setConversation(payload.conversation_id);sessionStorage.setItem(key,payload.conversation_id);update({...payload.message,id});}
   });
  }catch(e){if(mounted.current){const stopped=e instanceof Error&&e.name==='AbortError',status=stopped?'aborted':'failed';setMessages(previous=>previous.map(message=>message.id!==id?message:{...message,status,error:stopped?undefined:{detail:e instanceof Error?e.message:'Dataset chat could not finish.'},answer_workflow:message.answer_workflow?{...message.answer_workflow,status,steps:message.answer_workflow.steps.map((step:Entity)=>step.status==='running'?{...step,status:stopped?'cancelled':'failed',duration_ms:Math.max(0,Date.now()-step.started_at)}:step)}:undefined}));}}
  finally{locked.current=false;controller.current=null;if(mounted.current)setBusy(false);}
 };
 const fresh=()=>{if(locked.current)return;setMessages([]);setConversation('');setText('');setError('');setHistory(null);sessionStorage.removeItem(key);};
 const openHistory=async()=>{try{const result=await api('/dataset-chat/conversations','GET',undefined,undefined,true);setHistory(result.filter((item:Entity)=>knowledgeScopeKey({datasetIds:item.dataset_ids,documentIds:item.document_ids})===signature));}catch(e){setError(e instanceof Error?e.message:'Chat history is unavailable.');}};
 const restore=async(id:string)=>{try{const saved=await api(`/dataset-chat/conversations/${id}`,'GET',undefined,undefined,true);if(knowledgeScopeKey({datasetIds:saved.dataset_ids,documentIds:saved.document_ids})!==signature)throw new Error('Choose the same dataset knowledge to open this chat.');setMessages(saved.messages||[]);setConversation(saved.id);sessionStorage.setItem(key,saved.id);setHistory(null);setError('');}catch(e){setError(e instanceof Error?e.message:'Saved chat is unavailable.');}};
 return <div className="agent-v2 dataset-knowledge-chat" aria-label="Dataset Knowledge Chat">
  <header className="agent-v2-context"><span className="small muted">Dataset Knowledge Chat · Read only</span>{onOpenAgent&&<button type="button" className="text-button" onClick={onOpenAgent}>Open Aegis Agent</button>}<button type="button" className="btn icon" aria-label="Dataset chat history" title="Dataset chat history" disabled={busy} onClick={()=>void openHistory()}><History size={17}/></button><button type="button" className="btn icon" aria-label="New dataset chat" title="New dataset chat" disabled={busy} onClick={fresh}><Plus size={18}/></button></header>
  {history&&<div className="agent-v2-history"><strong>Dataset chat history</strong><button className="text-button" onClick={()=>setHistory(null)}>Close</button>{history.length?history.map(item=><button key={item.id} className="text-button" onClick={()=>void restore(item.id)}>{item.name}</button>):<p>No dataset chats in this scope yet.</p>}</div>}
  <div ref={thread} className="agent-v2-thread" aria-label="Dataset chat conversation" tabIndex={0}>
   {loading&&<p role="status">Loading accessible dataset knowledge…</p>}
   {error&&<div role="alert" className="agent-v2-error">{error}<button className="btn" onClick={()=>setAttempt(value=>value+1)}>Refresh chat catalog</button></div>}
   {!loading&&!messages.length&&<div className="agent-v2-welcome"><AgentLogo size={48}/><h2>{username}'s Knowledge Source</h2><p>Ask questions about the included indexed files and saved results. Answers include source citations.</p><div className="agent-v2-suggestions">{['Summarize the key themes','Compare the included knowledge','What evidence supports the main findings?'].map(prompt=><button key={prompt} className="btn" onClick={()=>setText(prompt)}>{prompt}</button>)}</div></div>}
   {messages.map(message=>message.role==='user'?<AgentRequest key={message.id} text={message.summary?'Workspace overview · Included dataset knowledge':message.text} attachments={[]}/>:<section key={message.id} className="agent-v2-message"><div className="agent-v2-speaker"><AgentLogo size={23}/><strong>Dataset Knowledge Chat</strong><DatasetChatStatus message={message}/></div><AgentChatAnswer message={message} api={api} onError={setError} onReview={onReview}/>{['failed','aborted'].includes(message.status)&&message.request&&<button className="btn" disabled={busy} onClick={()=>void send(message.request,message.summary)}>Retry question</button>}</section>)}
  </div>
  <div className="agent-v2-composer"><div className="agent-v2-compose-box"><div className="agent-v2-input"><textarea autoFocus aria-label="Message Dataset Knowledge Chat" placeholder="Ask about your included dataset knowledge…" value={text} rows={2} disabled={busy} onChange={e=>setText(e.target.value)} onKeyDown={e=>{if(e.key==='Enter'&&!e.shiftKey){e.preventDefault();void send();}}}/></div><div className="agent-v2-compose-controls"><label className="agent-v2-model-control"><span>Chat model</span><select aria-label="Dataset chat model" value={selectedModel} disabled={busy||loading} onChange={e=>setModel(e.target.value)}><option value="">Choose a Chat model</option>{models.map((item:Entity)=><option key={item.id} value={item.id}>{item.name}</option>)}</select></label><div className="agent-v2-send-controls">{busy?<button className="btn icon" aria-label="Stop dataset chat" onClick={()=>controller.current?.abort()}><Square size={17}/></button>:<button className="btn icon primary" aria-label="Send dataset chat question" disabled={loading||!text.trim()||!selectedModel} onClick={()=>void send()}><ArrowUp size={20}/></button>}</div></div></div><div className="agent-v2-footer"><span>Read-only knowledge chat. Open Aegis Agent for onboarding, uploads and extraction.</span></div></div>
 </div>;
}
