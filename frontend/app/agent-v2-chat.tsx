"use client";
import {useState} from 'react';
import {Copy,ThumbsUp,ThumbsDown} from 'lucide-react';
type Entity=Record<string,any>;
export function conversationExchanges(conversation:Entity){
 const entries:Entity[]=[];
 for(const message of conversation.messages||[]){
  if(message.role==='user')entries.push({id:'history-'+message.id,historical:true,request:message.text,calls:[],dataset_id:conversation.dataset_id||'',document_ids:conversation.document_ids||[],answer_mode:conversation.mode==='general'?'general':'documents',planner:{id:message.model_selection?.model_id||'',name:message.model_selection?.model_name||'Saved chat'},conversation_id:conversation.id});
  else if(message.role==='assistant'&&entries.length)entries[entries.length-1].chat=message;
 }
 return entries;
}
function InlineText({text}:{text:string}){
 return <>{text.split(/(\*\*[^*]+\*\*|`[^`]+`)/g).map((part,index)=>part.startsWith('**')?<strong key={index}>{part.slice(2,-2)}</strong>:part.startsWith('`')?<code key={index}>{part.slice(1,-1)}</code>:part)}</>;
}
export function AgentAnswerText({text}:{text:string}){
 return <div className="agent-v2-reply">{text.split(/```/g).map((part,index)=>index%2?<pre key={index}><code>{part.replace(/^\w*\n/,'')}</code></pre>:<div key={index}>{part.split('\n').map((line,row)=>line.startsWith('#')?<p key={row}><strong><InlineText text={line.replace(/^#+\s*/,'')}/></strong></p>:<div key={row}><InlineText text={line}/>{!line&&<br/>}</div>)}</div>)}</div>;
}
export function AgentChatAnswer({message,api,onError}:{message:Entity;api:(path:string,method?:string,body?:unknown)=>Promise<any>;onError:(error:string)=>void}){
 const [rating,setRating]=useState('');
 const incomplete=['failed','aborted','streaming'].includes(message.status);
 const feedback=async(value:string)=>{try{await api(`/messages/${message.id}/feedback`,'POST',{rating:value});setRating(value);}catch(e){onError(e instanceof Error?e.message:'Feedback could not be saved.');}};
 return <div className="agent-v2-chat-answer">
  <AgentAnswerText text={message.text||''}/>
  {message.status==='aborted'&&<p className="small muted">{message.text?'Stopped · partial answer kept':'Stopped before an answer was generated'}</p>}
  {message.error&&<p role="alert" className="agent-v2-error">{message.error.detail||'The answer could not finish.'}</p>}
  {message.citations?.length>0&&<details className="agent-v2-sources"><summary>Sources · {message.citations.length}</summary>{message.citations.map((source:Entity,index:number)=><section key={source.chunk_id||index}><strong>[{source.index}] {source.document_name}</strong>{source.page&&<span> · page {source.page}</span>}<p>{source.text||source.excerpt}</p><a href={`/api/documents/${source.document_id}/source#page=${source.page||1}`} target="_blank" rel="noopener noreferrer">Open source</a></section>)}</details>}
  {!!message.text&&message.status!=='streaming'&&<div className="agent-v2-chat-actions"><button className="btn icon" aria-label="Copy agent answer" onClick={()=>void navigator.clipboard.writeText(message.text).catch(()=>onError('The browser could not copy this answer.'))}><Copy size={14}/></button><button className="btn icon" aria-label="Helpful agent answer" aria-pressed={rating==='up'} disabled={incomplete||!message.id} onClick={()=>void feedback('up')}><ThumbsUp size={14}/></button><button className="btn icon" aria-label="Unhelpful agent answer" aria-pressed={rating==='down'} disabled={incomplete||!message.id} onClick={()=>void feedback('down')}><ThumbsDown size={14}/></button></div>}
 </div>;
}
