"use client";
import {useState} from 'react';
import {Copy,ThumbsUp,ThumbsDown,FileText} from 'lucide-react';
import {attachmentSize} from './agent-attachments';
type Entity=Record<string,any>;
export function AgentRequest({text,attachments=[],pending=false}:{text:string;attachments:{name:string;size?:number}[];pending?:boolean}){
 return <div className={`agent-v2-request${pending?' agent-v2-pending':''}`}>
  {attachments.length>0&&<ul className="agent-v2-submitted-files" aria-label="Files sent with this message">{attachments.map((file,index)=><li className="agent-v2-submitted-file" key={index}><FileText size={18} aria-hidden="true"/><span><strong title={file.name}>{file.name}</strong>{file.size!==undefined&&<small>{attachmentSize(file.size)}</small>}</span></li>)}</ul>}
  {text&&<div className="agent-v2-user">{text}</div>}
 </div>;
}
export function conversationExchanges(conversation:Entity){
 const entries:Entity[]=[];
 for(const message of conversation.messages||[]){
  if(message.role==='user')entries.push({id:'history-'+message.id,historical:true,request:message.text,messageAttachments:message.attachments||[],runtime:conversation.runtime,calls:[],dataset_id:conversation.dataset_id||'',document_ids:conversation.document_ids||[],answer_mode:conversation.mode==='general'?'general':'documents',planner:{id:message.model_selection?.model_id||'',name:message.model_selection?.model_name||'Saved chat'},conversation_id:conversation.id});
  else if(message.role==='assistant'&&entries.length)entries[entries.length-1].chat=message;
 }
 return entries;
}
function InlineText({text,citations=[],onCitation}:{text:string;citations?:Entity[];onCitation?:(source:Entity)=>void}){
 return <>{text.split(/(\*\*[^*]+\*\*|`[^`]+`|\[\d+\])/g).map((part,index)=>{
  const source=/^\[\d+\]$/.test(part)?citations.find(s=>s.index===Number(part.slice(1,-1))):undefined;
  return source?<button className="agent-citation" key={index} aria-label={`Open citation ${source.index}`} onClick={()=>onCitation?.(source)}>{part}</button>:part.startsWith('**')?<strong key={index}>{part.slice(2,-2)}</strong>:part.startsWith('`')?<code key={index}>{part.slice(1,-1)}</code>:part;
 })}</>;
}
export function AgentAnswerText({text,citations=[],onCitation}:{text:string;citations?:Entity[];onCitation?:(source:Entity)=>void}){
 return <div className="agent-v2-reply">{text.split(/```/g).map((part,index)=>index%2?<pre key={index}><code>{part.replace(/^\w*\n/,'')}</code></pre>:<div key={index}>{part.split('\n').map((line,row)=>line.startsWith('#')?<p key={row}><strong><InlineText text={line.replace(/^#+\s*/,'')} citations={citations} onCitation={onCitation}/></strong></p>:<div key={row}><InlineText text={line} citations={citations} onCitation={onCitation}/>{!line&&<br/>}</div>)}</div>)}</div>;
}
export function AgentChatAnswer({message,api,onError,onReview,onRecovery}:{message:Entity;api:(path:string,method?:string,body?:unknown)=>Promise<any>;onError:(error:string)=>void;onReview?:(id:string)=>void;onRecovery?:(action:Entity)=>void}){
 const [rating,setRating]=useState('');
 const incomplete=['failed','aborted','streaming'].includes(message.status);
 const feedback=async(value:string)=>{try{await api(`/messages/${message.id}/feedback`,'POST',{rating:value});setRating(value);}catch(e){onError(e instanceof Error?e.message:'Feedback could not be saved.');}};
 const openCitation=(source:Entity)=>{if(source.kind==='extraction')onReview?.(source.extraction_id);else window.open(`/api/documents/${source.document_id}/source#page=${source.page||1}`,'_blank','noopener,noreferrer');};
 return <div className="agent-v2-chat-answer" data-streaming={message.status==='streaming'}>
  <AgentAnswerText text={message.text||''} citations={message.citations||[]} onCitation={openCitation}/>
  {message.citations?.some((source:Entity)=>source.ocr)&&<p className="small muted" role="status">Some sources use AI OCR. Verify names, numbers and tables against the originals.</p>}
  {message.recovery_actions?.length>0&&<div className="agent-v2-result-actions">{message.recovery_actions.map((action:Entity,index:number)=><button className="btn" key={index} onClick={()=>onRecovery?.(action)}>{action.label}</button>)}</div>}
  {message.review_actions?.some((action:Entity)=>action.fields?.length>0)&&<p className="muted small">This answer uses selected fields. Review opens the complete saved results.</p>}
  {message.review_actions?.length>0&&<div className="agent-v2-result-actions">{message.review_actions.map((action:Entity)=><button className="btn" key={action.extraction_id} onClick={()=>onReview?.(action.extraction_id)} title={`${action.name} — version ${action.version}`}>{action.label||'Review result'} <code>{action.extraction_id.slice(0,8)}</code></button>)}</div>}
  {message.status==='aborted'&&<p className="small muted">{message.text?'Stopped · partial answer kept':'Stopped before an answer was generated'}</p>}
  {message.error&&<p role="alert" className="agent-v2-error">{message.error.detail||'The answer could not finish.'}</p>}
  {message.citations?.length>0&&<details className="agent-v2-sources"><summary>Sources · {message.citations.length}</summary>{message.citations.map((source:Entity,index:number)=><section key={source.chunk_id||index}><strong>[{source.index}] {source.document_name}</strong>{source.kind==='extraction'?<><p className="small">Saved extraction · version {source.version} · {source.review_status}<br/><code>{source.extraction_id}</code></p><pre className="extraction-source-values">{source.text}</pre><p className="small muted">Saved values; check original evidence in Review.</p><button className="text-button" onClick={()=>onReview?.(source.extraction_id)}>Open extraction source</button></>:<>{source.page&&<span> · page {source.page}</span>}<p>{source.text||source.excerpt}</p><a href={`/api/documents/${source.document_id}/source#page=${source.page||1}`} target="_blank" rel="noopener noreferrer">Open source</a></>}</section>)}</details>}
  {!!message.text&&message.status!=='streaming'&&<div className="agent-v2-chat-actions"><button className="btn icon" aria-label="Copy agent answer" onClick={()=>void navigator.clipboard.writeText(message.text).catch(()=>onError('The browser could not copy this answer.'))}><Copy size={14}/></button><button className="btn icon" aria-label="Helpful agent answer" aria-pressed={rating==='up'} disabled={incomplete||!message.id} onClick={()=>void feedback('up')}><ThumbsUp size={14}/></button><button className="btn icon" aria-label="Unhelpful agent answer" aria-pressed={rating==='down'} disabled={incomplete||!message.id} onClick={()=>void feedback('down')}><ThumbsDown size={14}/></button></div>}
 </div>;
}
