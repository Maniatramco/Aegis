export type ModelMapping = {model_id:string; enabled?:boolean; [key:string]:unknown};
export type MappingDraft = {mappings:ModelMapping[]; chatDefault:string; extractDefault:string; embedding:string};

/** A default is one choice among enabled models, not the complete mapping list. */
export function selectMappingDefault(current:MappingDraft,key:'chatDefault'|'extractDefault'|'embedding',value:string):MappingDraft {
 const next={...current,[key]:value};
 const mappings=current.mappings.map(item=>({...item}));
 for(const id of [next.chatDefault,next.extractDefault,next.embedding].filter(Boolean)){
  const existing=mappings.find(item=>item.model_id===id);
  if(existing)existing.enabled=true;
  else mappings.push({model_id:id,enabled:true});
 }
 return {...next,mappings};
}

export function setMappingEnabled(current:MappingDraft,id:string,enabled:boolean):MappingDraft {
 if(!enabled&&[current.chatDefault,current.extractDefault,current.embedding].includes(id))return current;
 const found=current.mappings.some(item=>item.model_id===id);
 return {...current,mappings:found?current.mappings.map(item=>item.model_id===id?{...item,enabled}:item):[...current.mappings,{model_id:id,enabled}]};
}
