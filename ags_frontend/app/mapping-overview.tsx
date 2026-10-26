"use client";
import {CheckCircle2,CircleAlert,Database} from "lucide-react";
import {SummaryTiles} from "./summary-tiles";
type Entity=Record<string,any>;
const ROLES=[["embedding_model_id","Embedding"],["default_chat_model_id","Chat"],["default_extraction_model_id","Extraction"]] as const;
/** Which model roles a dataset still needs before it can index, answer and extract. */
export function missingRoles(dataset:Entity){return ROLES.filter(([key])=>!dataset[key]).map(([,label])=>label);}
export function mappingTiles(datasets:Entity[]){
 return [
  {label:"Datasets",value:datasets.length,detail:`${datasets.filter(d=>d.active===false).length} inactive`,tone:""},
  {label:"Fully mapped",value:datasets.filter(d=>!missingRoles(d).length).length,detail:"embedding, chat and extraction",tone:"ok"},
  {label:"Missing embedding",value:datasets.filter(d=>!d.embedding_model_id).length,detail:"cannot index documents",tone:"error"},
 ];
}
export function MappingOverview({datasets,selected,busy,onSelect}:{datasets:Entity[];selected:string;busy:boolean;onSelect:(id:string)=>void}){
 if(!datasets.length)return null;
 return <>
  <SummaryTiles label="Model mapping summary" tiles={mappingTiles(datasets)}/>
  <div className="mapping-picks" role="group" aria-label="Choose a dataset to map">{datasets.map(d=>{const missing=missingRoles(d);return <button key={d.id} type="button" className="mapping-pick" aria-pressed={d.id===selected} disabled={busy} onClick={()=>onSelect(d.id)}>
   <span className="mapping-pick-name"><Database size={15} aria-hidden="true"/><strong title={d.name}>{d.name}</strong></span>
   <span className="mapping-pick-state" data-state={missing.length?"missing":"ready"}>{missing.length?<><CircleAlert size={13} aria-hidden="true"/>Needs {missing.join(", ")}</>:<><CheckCircle2 size={13} aria-hidden="true"/>All roles mapped</>}</span>
  </button>;})}</div>
 </>;
}
