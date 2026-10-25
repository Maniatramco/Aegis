type Entity=Record<string,any>;
export function datasetMilestones(datasetId:string|undefined,documents:Entity[],extractions:Entity[]=[]){
 const docs=datasetId?documents.filter(doc=>(doc.dataset_id||doc.kb_id||doc.parent_id)===datasetId):documents;
 const ids=new Set(docs.map(doc=>doc.id));
 const saved=extractions.filter(result=>result.status==='ready'&&(!datasetId||result.dataset_id===datasetId||result.document_ids?.some((id:string)=>ids.has(id))));
 const unique=(results:Entity[])=>new Set(results.flatMap(result=>(result.document_ids||[]).filter((id:string)=>ids.has(id)))).size;
 return {added:docs.length,indexed:docs.filter(doc=>doc.status==='ready'&&!doc.requires_reindex).length,extracted:unique(saved),reviewed:unique(saved.filter(result=>result.review_status==='reviewed')),attention:docs.filter(doc=>['failed','cancelled'].includes(doc.status)||doc.requires_reindex).length};
}
