"use client";
import {useCallback,useEffect,useRef,useState} from 'react';
import {Cloud, X} from 'lucide-react';
import './agent-consent.css';
type Destination={key:string;title:string;description:string};
export type ConsentReceipt={dataset_id:string;required:boolean;destinations:Destination[]};
type Scope={dataset_id?:string;planner_model_id?:string;roles:string[];model_ids?:Record<string,string>};
type Api=(path:string,method?:string,body?:unknown,signal?:AbortSignal,quiet?:boolean)=>Promise<any>;
export function consentCovers(previous:ConsentReceipt|undefined,current:ConsentReceipt){
 return Boolean(previous&&previous.dataset_id===current.dataset_id&&current.destinations.every(item=>previous.destinations.some(approved=>approved.key===item.key)));
}
export function ConsentPopup({scope,onResolve}:{scope:ConsentReceipt|null;onResolve:(agree:boolean)=>void}){
 const dialog=useRef<HTMLDialogElement>(null);
 useEffect(()=>{if(scope&&!dialog.current?.open)dialog.current?.showModal();else if(!scope)dialog.current?.close();},[scope]);
 return <dialog ref={dialog} className="agent-consent-popup" aria-labelledby="agent-consent-title" aria-describedby="agent-consent-description" onCancel={event=>{event.preventDefault();onResolve(false);}}>
  {scope&&<><header><Cloud size={20}/><h2 id="agent-consent-title">Allow external processing?</h2><button type="button" className="btn icon" aria-label="Close external processing approval" onClick={()=>onResolve(false)}><X size={16}/></button></header>
   <p id="agent-consent-description">This workflow uses these configured destinations:</p>
   <ul>{scope.destinations.map(item=><li key={item.key}><strong>{item.title}</strong><span>{item.description}</span></li>)}</ul>
   <p className="small muted">Approval applies to this request and its confirmed workflow. Provider charges may apply.</p>
   <footer><button type="button" className="btn" autoFocus onClick={()=>onResolve(false)}>Cancel</button><button type="button" className="btn primary" onClick={()=>onResolve(true)}>Agree and continue</button></footer>
  </>}
 </dialog>;
}
export function useAgentConsent(api:Api){
 const [scope,setScope]=useState<ConsentReceipt|null>(null);
 const pending=useRef<((agree:boolean)=>void)|null>(null);
 const resolve=useCallback((agree:boolean)=>{const answer=pending.current;pending.current=null;setScope(null);answer?.(agree);},[]);
 useEffect(()=>()=>{pending.current?.(false);pending.current=null;},[]);
 const request=useCallback(async(input:Scope,previous?:ConsentReceipt):Promise<ConsentReceipt|null>=>{
  const current:ConsentReceipt=await api('/agent-v2/consent','POST',input,undefined,true);
  if(!current.required)return current;
  if(consentCovers(previous,current))return {...current,destinations:[...previous!.destinations,...current.destinations.filter(item=>!previous!.destinations.some(old=>old.key===item.key))]};
  const agreed=await new Promise<boolean>(answer=>{pending.current=answer;setScope(current);});
  return agreed?current:null;
 },[api]);
 return {request,popup:<ConsentPopup scope={scope} onResolve={resolve}/>};
}
