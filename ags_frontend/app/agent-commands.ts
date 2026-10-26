export const agentCommands=[{operation:'onboard',label:'/Onboard',description:'Set up a dataset, models, documents and prompt'},{operation:'upload',label:'/Upload',description:'Upload and index documents'},{operation:'extract',label:'/Extract',description:'Extract fields with a prompt template'},{operation:'reextract',label:'/ReExtract',description:'Re-extract saved documents and keep earlier results'},{operation:'manage',label:'/Manage',description:'Edit a dataset’s details, models, documents and prompts'}] as const;
// "/" is the command key; a leading "@" from earlier versions is still understood.
const COMMAND=/^\s*[/@](onboard|upload|extract|reextract)(?=\s|$)/i;
const COMMAND_LIST='/Onboard, /Upload, /Extract, /ReExtract or /Manage';
/** /Manage opens the dataset card inside the Agent; it is never sent to the server. */
export const isManageCommand=(text:string)=>/^\s*[/@]manage(?=\s|$)/i.test(text);
export function agentOperation(text:string){
 const directive=COMMAND.exec(text)?.[1].toLowerCase();
 if(directive)return directive as 'onboard'|'upload'|'extract'|'reextract';
 if(/^re[- ]?extract[.!]?$/i.test(text.trim()))return 'reextract';
 if(/^(?:please\s+|pls\s+)?extract(?:\s+only)?[.!]?$/i.test(text.trim()))return 'extract';
 if(/^\s*(?:(?:please|pls)\s+)?(?:(?:can|could|would|will)\s+(?:you|u)\s+(?:(?:please|pls)\s+)?)?(?:onboard|create|register)\s+(?:(?:a|an|one|new)\s+)*dataset\b/i.test(text))return 'onboard';
 return undefined;
}
/** A leading "/word" (or any leading "@") is a command attempt; paths such as "/docs/a.pdf" stay ordinary text. */
const commandAttempt=(value:string)=>value.startsWith('@')||/^\/[\p{L}\p{N}_]*(?=\s|$)/u.test(value);
export function agentInputIssue(text:string){
 const value=text.trim();
 if(commandAttempt(value)&&!agentOperation(value)&&!isManageCommand(value))return `Choose ${COMMAND_LIST} from the agent menu, then add your request.`;
 if(value&&!/[\p{L}\p{N}]/u.test(value))return `Please enter a question or choose ${COMMAND_LIST}.`;
 return '';
}
export function agentMention(text:string,caret:number){
 const match=/^(\s*)[/@]([^\s]*)$/i.exec(text.slice(0,caret));
 if(!match)return null;
 const prefix=match[2].toLowerCase();const query=agentCommands.some(command=>command.label.slice(1).toLowerCase().startsWith(prefix))?match[2]:'';
 return {start:match[1].length,end:caret,query};
}
export function insertAgentCommand(text:string,mention:{start:number;end:number},label:string){return text.slice(0,mention.start)+label+' '+text.slice(mention.end);}
