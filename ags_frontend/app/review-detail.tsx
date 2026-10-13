"use client";
import {useEffect,useState,type ReactNode} from 'react';
import {ReviewSelectors} from './review-selectors';
import {ExtractionReview} from './extraction-review';
import {extractionDataset} from './extraction-directory';
type Entity=Record<string,any>;
type Api=(path:string,method?:string,body?:unknown,signal?:AbortSignal,quiet?:boolean)=>Promise<any>;
export function ReviewDetail({routeId,extraction:result,datasets,templates,extractions,documents,jobs,api,onOpen,onSaved,onDirty,onBeforeChange,back,openRequest}:{routeId:string;extraction:Entity|null;datasets:Entity[];templates:Entity[];extractions:Entity[];documents:Entity[];jobs:Entity[];api:Api;onOpen:(id:string)=>boolean;onSaved:(value:Entity)=>void;onDirty:(dirty:boolean)=>void;onBeforeChange:()=>boolean;back:ReactNode;openRequest:number}){
 const initial=result||extractions.find(e=>e.id===routeId);
 const [dataset,setDataset]=useState(initial?extractionDataset(initial,documents):''),[template,setTemplate]=useState(initial?.template_id||''),[id,setId]=useState(routeId);
 useEffect(()=>{const item=result?.id===routeId?result:extractions.find(e=>e.id===routeId);if(item){setDataset(extractionDataset(item,documents));setTemplate(item.template_id||'');setId(item.id);}},[routeId,result?.id]);
 const prompts=templates.filter(t=>!dataset||!(t.dataset_id||t.parent_id)||(t.dataset_id||t.parent_id)===dataset);
 const matches=extractions.filter(e=>extractionDataset(e,documents)===dataset&&e.template_id===template);
 const selectScope=(nextDataset:string,nextTemplate:string)=>{
  if(!onBeforeChange())return;
  const target=extractions.find(e=>extractionDataset(e,documents)===nextDataset&&e.template_id===nextTemplate);
  if(target&&!onOpen(target.id))return;
  setDataset(nextDataset);setTemplate(nextTemplate);setId(target?.id||'');
 };
 return <div className="review-detail-browser">
  <div className="review-detail-selectorbar"><div className="review-return-bar">{back}</div>
  <ReviewSelectors datasets={datasets} templates={prompts} extractions={matches} dataset={dataset} template={template} extraction={id} onDataset={next=>{if(next===dataset)return;const candidates=extractions.filter(e=>extractionDataset(e,documents)===next);const available=templates.filter(t=>!(t.dataset_id||t.parent_id)||(t.dataset_id||t.parent_id)===next);selectScope(next,candidates[0]?.template_id||available[0]?.id||'');}} onTemplate={next=>{if(next!==template)selectScope(dataset,next);}} onExtraction={next=>{if(next===id)return;if(!onOpen(next))return;setId(next);}}/>
  </div>
  {id&&result?.id===id?<ExtractionReview openRequest={openRequest} extraction={result} datasetName={datasets.find(d=>d.id===dataset)?.name} documents={documents} jobs={jobs} api={api} onDirty={onDirty} onSaved={onSaved}/>:<div className="review-selection-empty"><h2>{id?'Opening extraction…':'No results for this selection'}</h2><p>{id?'Loading saved fields and the original document.':'Choose another dataset or prompt template to review a saved extraction.'}</p></div>}
 </div>;
}
