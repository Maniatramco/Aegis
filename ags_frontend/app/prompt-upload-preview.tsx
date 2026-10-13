"use client";
import { useEffect, useRef } from 'react';
import { CheckCircle2, X } from 'lucide-react';
import { type PromptUpload } from './prompt-upload';
import './prompt-upload-preview.css';
export function PromptUploadPreview({prompt,datasetName,onConfirm,onCancel}:{prompt:PromptUpload|null;datasetName:string;onConfirm:()=>void;onCancel:()=>void}) {
 const dialog=useRef<HTMLDialogElement>(null);
 useEffect(()=>{if(prompt&&!dialog.current?.open)dialog.current?.showModal();else if(!prompt)dialog.current?.close();},[prompt]);
 return <dialog className="prompt-upload-preview" ref={dialog} aria-label="Review uploaded prompt" onCancel={onCancel} onClose={onCancel}>
  {prompt&&<><header><div><h2>Review your prompt</h2><p>{prompt.fileName}</p></div><button type="button" className="btn icon" aria-label="Close prompt preview" onClick={onCancel}><X size={18}/></button></header>
   <p className="prompt-validation-success"><CheckCircle2 size={16}/>Valid JSON and extraction schema</p>
   <dl><div><dt>Template filename</dt><dd>{prompt.name}</dd></div><div><dt>Dataset</dt><dd>{datasetName}</dd></div></dl>
   {prompt.replacesExisting&&<p className="prompt-preview-hint">This filename already exists in this dataset. Send will update that template with a new version. Earlier versions are preserved.</p>}
   <pre tabIndex={0} aria-label="Uploaded prompt JSON">{prompt.preview}</pre>
   <p className="prompt-preview-hint">Confirm to attach this prompt. Use Send to save it for this dataset. Extraction starts only when requested in your message.</p>
   <footer><button type="button" className="btn" onClick={onCancel}>Cancel</button><button type="button" className="btn primary" onClick={onConfirm}>Confirm prompt</button></footer></>}
 </dialog>;
}
