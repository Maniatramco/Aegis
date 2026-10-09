export const MAX_AGENT_ATTACHMENTS=20;
type Attachment={name:string;size:number;lastModified:number};
export function attachmentKey(file:Attachment){return JSON.stringify([file.name,file.size,file.lastModified]);}
export function isJsonAttachment(file:Pick<Attachment,'name'>){return /\.json$/i.test(file.name);}
export function isFileDrag(types:readonly string[]){return types.includes('Files');}
export function mergeAgentAttachments<T extends Attachment>(existing:T[],incoming:T[],maxMb=25):{files:T[];error:string}{
 const limit=Number.isFinite(maxMb)&&maxMb>0?maxMb:25;
 if(!incoming.length)return {files:existing,error:'Drop PDF, DOCX, TXT or JSON files. Folders are not supported.'};
 for(const file of incoming){
  const reason=!/\.(pdf|docx|txt|json)$/i.test(file.name)?'Only PDF, DOCX, TXT and JSON files are supported.':!file.size?'Empty files cannot be attached.':file.size>limit*1024*1024?`This file exceeds the ${limit} MB limit.`:'';
  if(reason)return {files:existing,error:`${file.name}: ${reason}`};
 }
 const files=[...existing];
 for(const file of incoming)if(!files.some(current=>current.name===file.name&&current.size===file.size&&current.lastModified===file.lastModified))files.push(file);
 if(files.length>MAX_AGENT_ATTACHMENTS)return {files:existing,error:'Attach at most 20 documents. Remove some files and try again.'};
 return {files,error:''};
}
export function attachmentSize(bytes:number){return bytes>=1024*1024?`${(bytes/(1024*1024)).toFixed(1)} MB`:`${Math.max(1,Math.ceil(bytes/1024))} KB`;}
