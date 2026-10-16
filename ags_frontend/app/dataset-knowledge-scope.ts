import type {DatasetKnowledgeScope} from './dataset-knowledge-picker';
type Entity=Record<string,any>;
export const knowledgeDatasetId=(document:Entity):string=>document.dataset_id||document.kb_id||document.parent_id;
export function availableKnowledge(datasets:Entity[],documents:Entity[]){
 const ids=new Set(datasets.filter(dataset=>dataset.active!==false).map(dataset=>dataset.id));
 return documents.filter(document=>ids.has(knowledgeDatasetId(document))&&document.status==='ready'&&!document.requires_reindex);
}
export function boundedKnowledge(scope:DatasetKnowledgeScope,datasets:Entity[],documents:Entity[]):DatasetKnowledgeScope{
 const permitted=new Set(datasets.filter(dataset=>dataset.active!==false).map(dataset=>dataset.id));
 const datasetIds=[...new Set(scope.datasetIds)].filter(id=>permitted.has(id)).sort();
 const documentIds=scope.documentIds===null?null:availableKnowledge(datasets,documents).filter(document=>datasetIds.includes(knowledgeDatasetId(document))&&scope.documentIds!.includes(document.id)).map(document=>document.id).sort();
 return {datasetIds,documentIds};
}
export function addDatasetKnowledge(scope:DatasetKnowledgeScope,ids:string[],datasets:Entity[],documents:Entity[]):DatasetKnowledgeScope{
 const current=boundedKnowledge(scope,datasets,documents),available=availableKnowledge(datasets,documents);
 const added=[...new Set(ids)].filter(id=>!current.datasetIds.includes(id)&&available.some(document=>knowledgeDatasetId(document)===id));
 const selected=current.documentIds===null?available.filter(document=>current.datasetIds.includes(knowledgeDatasetId(document))).map(document=>document.id):current.documentIds;
 return {datasetIds:[...new Set([...current.datasetIds,...added])].sort(),documentIds:[...new Set([...selected,...available.filter(document=>added.includes(knowledgeDatasetId(document))).map(document=>document.id)])].sort()};
}
export function removeDatasetKnowledge(scope:DatasetKnowledgeScope,id:string,datasets:Entity[],documents:Entity[]):DatasetKnowledgeScope{
 const current=boundedKnowledge(scope,datasets,documents),datasetIds=current.datasetIds.filter(value=>value!==id);
 return {datasetIds,documentIds:availableKnowledge(datasets,documents).filter(document=>datasetIds.includes(knowledgeDatasetId(document))&&(current.documentIds===null||current.documentIds.includes(document.id))).map(document=>document.id).sort()};
}
export const DATASET_DRAG_TYPE='application/x-aegis-dataset-ids';
export function droppedDatasetIds(raw:string,datasets:Entity[]):string[]{
 try{const ids:unknown=JSON.parse(raw);if(!Array.isArray(ids)||ids.length>500||!ids.every(id=>typeof id==='string'))return [];return [...new Set(ids)].filter(id=>datasets.some(dataset=>dataset.id===id&&dataset.active!==false));}catch{return [];}
}
