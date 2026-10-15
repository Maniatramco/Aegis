type Entity=Record<string,any>;

/** One editable name per proposal; local date/time is explicit in the form. */
export function suggestedExtractionName(names:string[],when:Date=new Date(),timeZone?:string):string {
 const parts=new Intl.DateTimeFormat('en-CA',{timeZone,year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',second:'2-digit',hourCycle:'h23'}).formatToParts(when);
 const part=(name:string)=>parts.find(p=>p.type===name)?.value||'';
 const suffix=`_${part('year')}-${part('month')}-${part('day')}_${part('hour')}-${part('minute')}-${part('second')}`;
 const base=(names.length>1?`Merged extraction - ${names.length} documents`:names[0]?.replace(/\.(pdf|docx|txt|json)$/i,'')||'Document extraction').trim().replace(/_\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2}$/,'');
 return (base||'Document extraction').slice(0,200-suffix.length)+suffix;
}

export function withExtractionName(plan:Entity,documents:Entity[]):Entity {
 if(!plan.calls?.some((call:Entity)=>['extract','reextract'].includes(call.tool))||plan.display_name)return plan;
 const names=plan.attached_filenames?.length?plan.attached_filenames:documents.filter(doc=>plan.document_ids?.includes(doc.id)).map(doc=>doc.name);
 const created=Number(plan.created_at)*1000;
 return {...plan,display_name:suggestedExtractionName(names,created>0?new Date(created):new Date())};
}
