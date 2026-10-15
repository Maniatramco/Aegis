type Entity=Record<string,any>;
function requestedField(text:string,field:string){
 const prefix=field==='name'?'(?:name(?:\\s+of)?|named|called)':'(?:description|desc)';
 const quoted=new RegExp('\\b'+prefix+'\\s*(?:is|:|=)?\\s*(?:"([^"]+)"|“([^”]+)”|\'([^\']+)\'|‘([^’]+)’)', 'i').exec(text);
 if(quoted)return quoted.slice(1).find(value=>value!==undefined)?.trim()||'';
 const plain=new RegExp('\\b'+prefix+'(?:\\s*(?:is|:|=)\\s*|\\s+)([^\\n]+?)(?=\\s+(?:and\\s+)?(?:description|desc)\\s*(?:is|:|=)|$)','i').exec(text);
 return plain?.[1].trim().replace(/[.!]$/,'')||'';
}
export function onboardingDraft(request:string,proposal:Entity={}){
 const intent=request.replace(/"[^"]*"|“[^”]*”|'[^']*'|‘[^’]*’/g,'');
 const processing=!/\b(?:only|later|not now|without|do not|don't)\b/i.test(intent)&&
  (/\b(?:and|then|also)\s+(?:(?:please|run|do)\s+)?(?:upload|extract|extraction)\b/i.test(intent)||/\bonboard\s*(?:&|and)\s*extract\b/i.test(intent));
 return {...proposal,name:requestedField(request,'name')||proposal.name||'',description:requestedField(request,'description')||proposal.description||'',process_documents:processing};
}
export function onboardingModelSelection(models:Entity[],roles:string[][],defaults:Entity={},previous:Record<string,string>={}){
 return Object.fromEntries(roles.map(([key,cap])=>{
  const eligible=models.filter(m=>m.enabled&&m.credential_configured&&m.capabilities?.includes(cap));
  return [key,eligible.find(m=>m.id===previous[key])?.id||eligible.find(m=>m.id===defaults[key])?.id||eligible[0]?.id||''];
 }));
}
