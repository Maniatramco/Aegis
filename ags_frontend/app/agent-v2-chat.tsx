"use client";
import {useState} from 'react';
import {Copy,FileText} from 'lucide-react';
import {attachmentSize} from './agent-attachments';
import {CitationPanel} from './citation-panel';
import {extractionCitationId} from './citation-source';
import {agentTokenUsage} from './agent-token-usage';
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
type AnswerLinks={citations?:Entity[];onCitation?:(source:Entity)=>void;extractionIds?:string[];onReview?:(id:string)=>void};
function InlineText({text,citations=[],onCitation,extractionIds=[],onReview}:{text:string}&AnswerLinks){
 return <>{text.split(/(\*\*[^*]+\*\*|`[^`]+`|\[\d+\]|\b[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}\b)/gi).map((part,index)=>{
  const source=/^\[\d+\]$/.test(part)?citations.find(s=>s.index===Number(part.slice(1,-1))):undefined;
  const extractionId=extractionIds.find(id=>id.toLowerCase()===part.toLowerCase());
  const links={citations,onCitation,extractionIds,onReview};
  return source?<button className="agent-citation" key={index} aria-label={`Open citation ${source.index}`} onClick={()=>onCitation?.(source)}>{part}</button>:extractionId?<a className="agent-extraction-link" key={index} href={`#${encodeURIComponent(`Review/${extractionId}`)}`} aria-label={`Review extraction ${extractionId}`} onClick={event=>{if(onReview&&!event.button&&!event.metaKey&&!event.ctrlKey&&!event.shiftKey&&!event.altKey){event.preventDefault();onReview(extractionId);}}}>{part}</a>:part.startsWith('**')?<strong key={index}><InlineText text={part.slice(2,-2)} {...links}/></strong>:part.startsWith('`')?<code key={index}><InlineText text={part.slice(1,-1)} {...links}/></code>:part;
 })}</>;
}
export function AgentAnswerText({text,...links}:{text:string}&AnswerLinks){
 return <div className="agent-v2-reply">{text.split(/```/g).map((part,index)=>index%2?<pre key={index}><code>{part.replace(/^\w*\n/,'')}</code></pre>:<div key={index}>{part.split('\n').map((line,row)=>line.startsWith('#')?<p key={row}><strong><InlineText text={line.replace(/^#+\s*/,'')} {...links}/></strong></p>:<div key={row}><InlineText text={line} {...links}/>{!line&&<br/>}</div>)}</div>)}</div>;
}
export function AgentChatAnswer({message,api,onError,onReview,onRecovery}:{message:Entity;api:(path:string,method?:string,body?:unknown,signal?:AbortSignal,quiet?:boolean)=>Promise<any>;onError:(error:string)=>void;onReview?:(id:string)=>void;onRecovery?:(action:Entity)=>void}){
 const [citation,setCitation]=useState<Entity|null>(null);
 const usage=agentTokenUsage(message.token_usage,message.status);
 const openCitation=(source:Entity)=>setCitation({...source,requested_fields:message.review_actions?.find((action:Entity)=>action.extraction_id===extractionCitationId(source))?.fields||[]});
 // Only result IDs recorded in the answer's sources/actions become Review links.
 const extractionIds=Array.from(new Set<string>([...(message.review_actions||[]).map((action:Entity)=>action.extraction_id),...(message.citations||[]).map(extractionCitationId)].filter((id:unknown):id is string=>typeof id==='string'&&/^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$/i.test(id))));
 return <div className="agent-v2-chat-answer" data-streaming={message.status==='streaming'}>
  <AgentAnswerText text={message.text||''} citations={message.citations||[]} onCitation={openCitation} extractionIds={extractionIds} onReview={onReview}/>
  <p className="small muted agent-token-usage" aria-label="Answer token usage" title={usage.title}>{usage.text}</p>
  {message.citations?.some((source:Entity)=>source.ocr)&&<p className="small muted" role="status">Some sources use AI OCR. Verify names, numbers and tables against the originals.</p>}
  {message.recovery_actions?.length>0&&<div className="agent-v2-result-actions">{message.recovery_actions.map((action:Entity,index:number)=><button className="btn" key={index} onClick={()=>onRecovery?.(action)}>{action.label}</button>)}</div>}
  {message.review_actions?.some((action:Entity)=>action.fields?.length>0)&&<p className="muted small">This answer uses selected fields. Review opens the complete saved results.</p>}
  {message.review_actions?.length>0&&<div className="agent-v2-result-actions">{message.review_actions.map((action:Entity)=><button className="btn" key={action.extraction_id} onClick={()=>onReview?.(action.extraction_id)} title={`${action.name} — version ${action.version}`}>{action.label||'Review result'} <code>{action.extraction_id.slice(0,8)}</code></button>)}</div>}
  {message.status==='aborted'&&<p className="small muted">{message.text?'Stopped · partial answer kept':'Stopped before an answer was generated'}</p>}
  {message.error&&<p role="alert" className="agent-v2-error">{message.error.detail||'The answer could not finish.'}</p>}
  {message.citations?.length>0&&<details className="agent-v2-sources"><summary>Sources · {message.citations.length}</summary>{message.citations.map((source:Entity,index:number)=><section key={source.knowledge_id||source.chunk_id||index}><button className="text-button" onClick={()=>openCitation(source)}>[{source.index}] {source.document_name||source.title||'Source'}{source.page?` · page ${source.page}`:''}</button><p className="small muted">{source.kind==='extraction'?`Saved extraction · version ${source.version}`:source.source_type||'Document passage'}</p></section>)}</details>}
  {citation&&<CitationPanel source={citation} api={api} onClose={()=>setCitation(null)} onReview={onReview}/>}
  {!!message.text&&message.status!=='streaming'&&<div className="agent-v2-chat-actions"><button className="btn icon" aria-label="Copy agent answer" onClick={()=>void navigator.clipboard.writeText(message.text).catch(()=>onError('The browser could not copy this answer.'))}><Copy size={14}/></button></div>}
 </div>;
}
