"use client";
import type {ButtonHTMLAttributes} from 'react';
import {Archive,ArrowLeft,BookOpen,Database,FileScan,FileSearch,History,KeyRound,Layers,MessageSquare,Pencil,Play,Plus,RefreshCw,RotateCcw,Save,Scan,Shield,Square,Trash2,Users,X} from 'lucide-react';
const icons={add:Plus,review:FileSearch,reextract:FileScan,chat:MessageSquare,save:Save,retry:RefreshCw,remove:Trash2,mapping:Layers,password:KeyRound,role:Users,access:Shield,activate:Play,close:X,archive:Archive,restore:RotateCcw,documents:BookOpen,stop:Square,back:ArrowLeft,status:RefreshCw,fit:Scan,versions:History,database:Database,edit:Pencil};
type Props=Omit<ButtonHTMLAttributes<HTMLButtonElement>,'children'> & {label:string;action:keyof typeof icons;showLabel?:boolean};
/** Save actions keep a visible label alongside their accessible name. */
export function ActionButton({label,action,showLabel=action==='save',className='',title,...props}:Props){
 const Icon=icons[action];
 return <button {...props} className={`btn ${showLabel?'action-label':'icon action-icon'} ${className}`} title={title??label} aria-label={props['aria-label']??label}><Icon size={17} aria-hidden="true"/>{showLabel&&<span>{label}</span>}</button>;
}
