"use client";
type Entity=Record<string,any>;
export function MergedDetails({merge,extractionId}:{merge:Entity|null|undefined;extractionId?:string}) {
 if(!merge)return null;
 return <div className="merged-details">
  <p><strong>{merge.logical?'Extraction name:':'Merged file:'}</strong> {merge.filename}</p>
  <p className="small">{merge.source_count} original files retained{!merge.logical&&<> · {merge.sources?.reduce((n:number,s:Entity)=>n+(s.page_count||0),0)} source pages</>}</p>
  {!merge.logical&&<a className="text-button" href={extractionId?`/api/extractions/${extractionId}/merged-file`:`/api/documents/${merge.document_id}/download`} download>Download merged file</a>}
  <details><summary>Files included in this extraction ({merge.source_count})</summary><ul>{merge.sources?.map((s:Entity)=><li key={s.key||s.document_id}><strong>{s.name}</strong><span className="small">{s.size!=null&&<> · {s.size.toLocaleString()} bytes</>}{s.page_count!=null&&<> · {s.page_count} page{s.page_count===1?'':'s'}</>}{s.merged_page_start!=null&&<> · merged pages {s.merged_page_start}–{s.merged_page_end}</>}</span>{(merge.document_id||s.document_id)&&<a className="text-button" href={merge.document_id?`/api/documents/${merge.document_id}/merged-sources/${s.key}/download`:`/api/documents/${s.document_id}/download`} download> Download original</a>}</li>)}</ul></details>
 </div>;
}
