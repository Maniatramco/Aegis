export const agentCommands=[{operation:'onboard',label:'@Onboard',description:'Set up a dataset, models, documents and prompt'},{operation:'upload',label:'@Upload',description:'Upload and index documents'},{operation:'extract',label:'@Extract',description:'Extract fields with a prompt template'},{operation:'reextract',label:'@ReExtract',description:'Re-extract saved documents and keep earlier results'}] as const;
export function agentOperation(text:string){
 const directive=/^\s*@(onboard|upload|extract|reextract)(?=\s|$)/i.exec(text)?.[1].toLowerCase();
 if(directive)return directive as 'onboard'|'upload'|'extract'|'reextract';
 if(/^re[- ]?extract[.!]?$/i.test(text.trim()))return 'reextract';
 if(/^(?:please\s+|pls\s+)?extract(?:\s+only)?[.!]?$/i.test(text.trim()))return 'extract';
 if(/^\s*(?:(?:please|pls)\s+)?(?:(?:can|could|would|will)\s+(?:you|u)\s+(?:(?:please|pls)\s+)?)?(?:onboard|create|register)\s+(?:(?:a|an|one|new)\s+)*dataset\b/i.test(text))return 'onboard';
 return undefined;
}
export function agentInputIssue(text:string){
 const value=text.trim();
 if(value.startsWith('@')&&!agentOperation(value))return 'Choose @Onboard, @Upload, @Extract or @ReExtract from the agent menu, then add your request.';
 if(value&&!/[\p{L}\p{N}]/u.test(value))return 'Please enter a question or choose @Onboard, @Upload, @Extract or @ReExtract.';
 return '';
}
export function agentMention(text:string,caret:number){
 const match=/^\s*@([^\s]*)$/i.exec(text.slice(0,caret));
 if(!match)return null;
 const prefix=match[1].toLowerCase();const query=agentCommands.some(command=>command.label.slice(1).toLowerCase().startsWith(prefix))?match[1]:'';
 return {start:text.indexOf('@'),end:caret,query};
}
export function insertAgentCommand(text:string,mention:{start:number;end:number},label:string){return text.slice(0,mention.start)+label+' '+text.slice(mention.end);}
