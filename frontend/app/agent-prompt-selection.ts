type Template={id:string;name:string;parent_id?:string|null;dataset_id?:string|null};
export function promptSelections(raw:string|null):Record<string,string>{
 try{const parsed=raw?JSON.parse(raw):{};if(!parsed||typeof parsed!=='object'||Array.isArray(parsed))return {};return Object.fromEntries(Object.entries(parsed).filter(([,id])=>typeof id==='string')) as Record<string,string>;}catch{return {};}
}
export function restoreSavedPrompt(raw:string|null,templates:Template[],datasetId:string){
 const id=promptSelections(raw)[datasetId];
 return templates.find(template=>template.id===id&&(!(template.parent_id||template.dataset_id)||(template.parent_id||template.dataset_id)===datasetId))||null;
}
export function rememberSavedPrompt(storage:Pick<Storage,'getItem'|'setItem'>,key:string,datasetId:string,id:string){
 storage.setItem(key,JSON.stringify({...promptSelections(storage.getItem(key)),[datasetId]:id}));
}
