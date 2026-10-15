"use client";
import {useEffect,useRef,useState} from 'react';
import {RotateCcw,Trash2,X} from 'lucide-react';
import './dataset-lifecycle.css';

type Entity=Record<string,any>;
type Api=(path:string,method?:string,body?:unknown)=>Promise<any>;

function DeleteDialog({dataset,api,onClose,onDeleted}:{dataset:Entity;api:Api;onClose:()=>void;onDeleted:()=>void}){
 const dialog=useRef<HTMLDialogElement>(null);
 const [confirmation,setConfirmation]=useState(''),[busy,setBusy]=useState(false),[error,setError]=useState('');
 useEffect(()=>{dialog.current?.showModal();},[]);
 const remove=async()=>{
  if(busy||confirmation!==dataset.name)return;
  setBusy(true);setError('');
  try{await api(`/datasets/${encodeURIComponent(dataset.id)}`,'DELETE',{confirmation,expected_version:dataset.version});onDeleted();}
  catch(error){setError(error instanceof Error?error.message:'Dataset could not be deleted.');setBusy(false);}
 };
 return <dialog className="dataset-delete-dialog" ref={dialog} aria-labelledby="dataset-delete-title" onCancel={event=>{event.preventDefault();if(!busy)onClose();}}>
  <form onSubmit={event=>{event.preventDefault();void remove();}}>
   <div className="panel-head"><h2 id="dataset-delete-title">Delete dataset?</h2><button type="button" className="btn icon" aria-label="Cancel dataset deletion" disabled={busy} onClick={onClose}><X size={18}/></button></div>
   <p><strong>{dataset.name}</strong> and its documents, prompts, results and dataset chats will leave the active workspace. You can recover them from <strong>Deleted datasets</strong>.</p>
   <p>Registered models remain available. Finish or cancel active processing before deleting.</p>
   <label className="field">Type the dataset name to confirm<input autoFocus aria-label="Dataset name confirmation" value={confirmation} disabled={busy} autoComplete="off" onChange={event=>setConfirmation(event.target.value)}/></label>
   {error&&<p role="alert" className="field-error">{error}</p>}
   <div className="row dataset-delete-actions"><button type="button" className="btn" disabled={busy} onClick={onClose}>Cancel</button><button type="submit" className="btn danger" disabled={busy||confirmation!==dataset.name}><Trash2 size={16}/>{busy?'Deleting…':'Delete dataset'}</button></div>
  </form>
 </dialog>;
}

export function useDatasetLifecycle(api:Api,onChanged:()=>void,canManage:boolean){
 const [choice,setChoice]=useState<Entity|null>(null),[showTrash,setShowTrash]=useState(false),[deleted,setDeleted]=useState<Entity[]>([]);
 const [loading,setLoading]=useState(false),[restoring,setRestoring]=useState(''),[error,setError]=useState(''),[message,setMessage]=useState('');
 const load=async()=>{setLoading(true);setError('');try{setDeleted(await api('/dataset-trash'));}catch(error){setError(error instanceof Error?error.message:'Deleted datasets could not load.');}finally{setLoading(false);}};
 useEffect(()=>{if(showTrash&&canManage)void load();},[showTrash,canManage]);
 const restore=async(dataset:Entity)=>{
  if(restoring)return;setRestoring(dataset.id);setError('');
  try{await api(`/dataset-trash/${encodeURIComponent(dataset.id)}/restore`,'POST');setDeleted(previous=>previous.filter(row=>row.id!==dataset.id));setMessage(`${dataset.name} restored.`);onChanged();}
  catch(error){setError(error instanceof Error?error.message:'Dataset could not be restored.');}
  finally{setRestoring('');}
 };
 return {
  requestDelete:(dataset:Entity)=>{if(canManage){setMessage('');setChoice(dataset);}},
  controls:canManage?<div className="dataset-lifecycle">
   <button type="button" className="btn" aria-expanded={showTrash} onClick={()=>setShowTrash(value=>!value)}><Trash2 size={16}/>Deleted datasets</button>
   {message&&<p role="status">{message}</p>}
   {showTrash&&<section className="panel dataset-trash" aria-label="Deleted datasets">
    <div className="panel-head"><h3>Deleted datasets</h3><button type="button" className="btn" disabled={loading||!!restoring} onClick={()=>void load()}>Refresh deleted datasets</button></div>
    <p className="muted small">Restore a dataset with its documents, saved results, model mappings and existing user assignments.</p>
    {loading?<p role="status">Loading deleted datasets…</p>:deleted.length?<ul>{deleted.map(dataset=><li key={dataset.id}><span><strong>{dataset.name}</strong><small>Deleted {new Date(dataset.deleted_at*1000).toLocaleString()}</small></span><button type="button" className="btn" aria-label={`Restore ${dataset.name}`} disabled={!!restoring} onClick={()=>void restore(dataset)}><RotateCcw size={15}/>{restoring===dataset.id?'Restoring…':'Restore'}</button></li>)}</ul>:!error&&<p>No deleted datasets.</p>}
    {error&&<p role="alert" className="field-error">{error}</p>}
   </section>}
   {choice&&<DeleteDialog key={choice.id} dataset={choice} api={api} onClose={()=>setChoice(null)} onDeleted={()=>{setMessage(`${choice.name} moved to Deleted datasets.`);setChoice(null);onChanged();if(showTrash)void load();}}/>}
  </div>:null,
 };
}
