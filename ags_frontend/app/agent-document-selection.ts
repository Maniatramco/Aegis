type Entity=Record<string,any>;
export function readyDatasetDocuments(documents:Entity[],dataset:string){
 return dataset?documents.filter(d=>d.parent_id===dataset&&d.status==='ready'):[];
}
export function matchingDocuments(documents:Entity[],query:string){
 const search=query.trim().toLocaleLowerCase();return documents.filter(d=>d.name.toLocaleLowerCase().includes(search));
}
export function documentMention(text:string,caret:number){
 const before=text.slice(0,caret);const match=/(?:^|\s)#([^\n#]*)$/.exec(before);
 if(!match)return null;
 return {start:before.lastIndexOf('#'),end:caret,query:match[1]};
}
export function documentOptionLabel(document:Entity,documents:Entity[]){
 return documents.filter(d=>d.name===document.name).length>1?`${document.name} · ${document.id.slice(-6)}`:document.name;
}
export function eligibleAgentModels(models:Entity[],dataset:Entity|undefined){
 return (dataset?dataset.models||[]:models).filter((m:Entity)=>m.enabled!==false&&m.mapping_enabled!==false&&m.capabilities.includes('chat'));
}
