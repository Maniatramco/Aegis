"use client";
import {useState} from 'react';
import {ArrowLeft,Database,FileText,Layers,ShieldCheck} from 'lucide-react';
import {AgentOnboarding} from './agent-onboarding';
import './dataset-onboarding-screen.css';

type Entity=Record<string,any>;
type Api=(path:string,method?:string,body?:unknown,signal?:AbortSignal,quiet?:boolean)=>Promise<any>;
export function DatasetOnboardingScreen({api,models,defaults,storageKey,canManage,loading,onBack,onReady,onUse,onReview,onModels}:{api:Api;models:Entity[];defaults?:Entity;storageKey:string;canManage:boolean;loading:boolean;onBack:()=>void;onReady:()=>void;onUse:(id:string)=>void;onReview:(id:string)=>void;onModels:()=>void}){
 const [busy,setBusy]=useState(false);
 const close=(complete:boolean)=>{if(busy)return;if(complete){sessionStorage.removeItem(storageKey);sessionStorage.removeItem(storageKey+'-request');}onBack();};
 const useDataset=(id:string)=>{sessionStorage.removeItem(storageKey);sessionStorage.removeItem(storageKey+'-request');onUse(id);};
 return <section className="dataset-onboarding-screen" aria-label="Onboard a dataset">
  <button type="button" className="btn onboarding-back" disabled={busy} onClick={onBack}><ArrowLeft size={15}/>Back to Home</button>
  <header className="onboarding-screen-heading"><span><Database size={23}/></span><div><h2>Onboard a dataset</h2><p>Create a knowledge workspace and choose the models it will use.</p></div></header>
  {!canManage?<div className="notice warn" role="alert">Only an administrator can onboard datasets. Ask your administrator to create one and assign access.</div>:loading&&!models.length?<p role="status">Loading registered models…</p>:<div className="onboarding-screen-layout">
   <AgentOnboarding api={api} models={models} defaults={defaults} storageKey={storageKey} onBusy={setBusy} onReady={onReady} onUse={useDataset} onClose={close} onReview={onReview}/>
   <aside className="onboarding-screen-help" aria-label="Onboarding guidance"><h3>Ready for your knowledge</h3><p>Set up the dataset here, then explore its sources with Aegis on Home.</p><div><Layers size={18}/><span><strong>Choose your models</strong>Map an embedding, chat and extraction model from your registered connections.</span></div><div><FileText size={18}/><span><strong>Add documents when ready</strong>Create the dataset first, or enable upload and extraction to include documents and a prompt in this setup.</span></div><div><ShieldCheck size={18}/><span><strong>Review before processing</strong>The existing confirmation, provider consent and progress checks apply.</span></div><button type="button" className="btn" disabled={busy} onClick={onModels}>Manage registered models</button></aside>
  </div>}
 </section>;
}
