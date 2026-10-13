type Source=Record<string,any>;
export function citationRequest(source:Source){
 const path=source.source_url;
 if(typeof path==='string'&&/^\/api\/knowledge\/(?:published-sources|sources)\/[a-f0-9-]+(?:\?[^#]*)?$/i.test(path))return path.slice(4);
 if(typeof source.knowledge_id==='string'&&/^[a-f0-9-]+$/i.test(source.knowledge_id))return `/knowledge/sources/${source.knowledge_id}${source.knowledge_collection?`?collection=${encodeURIComponent(source.knowledge_collection)}`:''}`;
 if(typeof source.document_id==='string'&&/^[a-f0-9-]+$/i.test(source.document_id))return `/documents/${source.document_id}/preview`;
 return '';
}
export function recordedPage(value:unknown){return typeof value==='number'&&Number.isInteger(value)&&value>0?value:null;}
export function extractionCitationId(source:Source){
 const id=source.extraction_id||(source.source_type==='extraction'?source.entity_id?.split(':')[0]:'');
 return typeof id==='string'&&/^[a-f0-9-]+$/i.test(id)?id:'';
}
export function citedValues(fields:any,names:unknown){
 if(!fields||typeof fields!=='object'||Array.isArray(fields)||!Array.isArray(names))return fields;
 const keys=names.filter((name):name is string=>typeof name==='string'&&Object.prototype.hasOwnProperty.call(fields,name));
 return keys.length?Object.fromEntries(keys.map(key=>[key,fields[key]])):fields;
}
export function evidenceExcerpt(text:string,values:unknown[],length=420){
 const terms=values.flatMap(value=>typeof value==='string'&&value.length>=3?[value]:typeof value==='number'?[String(value)]:Array.isArray(value)?value.filter(v=>typeof v==='string'&&v.length>=3):[]);
 for(const term of terms){
  let at=text.indexOf(term);
  while(at>=0){
   if(!/^\d+$/.test(term)||(!/\d/.test(text[at-1]||'')&&!/\d/.test(text[at+term.length]||''))){
    const start=Math.max(0,at-Math.floor(length/3)),end=Math.min(text.length,start+Math.max(length,term.length));
    return (start?'…':'')+text.slice(start,end)+(end<text.length?'…':'');
   }
   at=text.indexOf(term,at+1);
  }
 }
 return text;
}
