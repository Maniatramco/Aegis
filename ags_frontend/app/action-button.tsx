"use client";
import type {ButtonHTMLAttributes} from 'react';
import {Archive,ArrowLeft,BookOpen,Check,Database,FileScan,FileSearch,History,KeyRound,Layers,MessageSquare,Pencil,Play,Plus,RefreshCw,RotateCcw,Scan,Shield,Square,Trash2,Users,X} from 'lucide-react';
const icons={add:Plus,review:FileSearch,reextract:FileScan,chat:MessageSquare,save:Check,retry:RefreshCw,remove:Trash2,mapping:Layers,password:KeyRound,role:Users,access:Shield,activate:Play,close:X,archive:Archive,restore:RotateCcw,documents:BookOpen,stop:Square,back:ArrowLeft,status:RefreshCw,fit:Scan,versions:History,database:Database,edit:Pencil};
type Props=Omit<ButtonHTMLAttributes<HTMLButtonElement>,'children'> & {label:string;action:keyof typeof icons};
/** Compact workspace actions retain the original native button behavior. */
export function ActionButton({label,action,className='',title,...props}:Props){
 const Icon=icons[action];
 return <button {...props} className={`btn icon action-icon ${className}`} title={title??label} aria-label={props['aria-label']??label}><Icon size={17} aria-hidden="true"/></button>;
}
