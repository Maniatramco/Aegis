type Template = {name?:string;source_filename?:string|null;schema?:Record<string,unknown>;schema_json?:Record<string,unknown>;dataset_id?:string|null;version?:number};
export function filterPromptTemplates<T extends Template>(templates:T[],dataset:string,search:string):T[]{
 const query=search.trim().toLocaleLowerCase();
 return templates.filter(t=>(dataset==='all'||(dataset==='shared'?!t.dataset_id:t.dataset_id===dataset))&&[t.name,t.source_filename].some(value=>(value||'').toLocaleLowerCase().includes(query)));
}
export function promptTemplateDownload(template:Template):{fileName:string;json:string}{
 const schema=template.schema||template.schema_json;
 if(!schema||typeof schema!=='object'||Array.isArray(schema))throw new Error('This template has no valid schema to download.');
 // Portable Upload Prompt format: the destination dataset is chosen when importing.
 const name=(template.name||'Prompt template').trim(),safeName=name.replace(/[<>:"/\\|?*\x00-\x1f]/g,'-').replace(/[. ]+$/g,'').slice(0,100)||'prompt-template';
 return {fileName:template.source_filename||`${safeName}-v${template.version||1}.json`,json:JSON.stringify({name,schema},null,2)+'\n'};
}
