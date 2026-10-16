"use client";
import {useEffect,useState} from 'react';
import {BookOpen,ChevronRight,Database,FileSearch,FileText,FolderPlus,Layers,Settings2,Table2} from 'lucide-react';
import {AgentLogo} from './agent-logo';

type Item={name:string;icon:typeof Database};
export function WorkspaceNavigation({view,isAdmin,onNavigate,adminItems,adminOpen,onAdminToggle}:{view:string;isAdmin:boolean;onNavigate:(name:any)=>void;adminItems:Item[];adminOpen:boolean;onAdminToggle:()=>void}){
 const onboardViews=['Onboard dataset','Datasets','Prompt templates','Extract','Extract Data','Review'],modelViews=['Model Registration','Model Mapping'];
 const [onboardOpen,setOnboardOpen]=useState(onboardViews.includes(view));
 useEffect(()=>{if(onboardViews.includes(view))setOnboardOpen(true);},[view]);
 const link=(name:string,label:string,Icon:typeof Database)=>{
  const selected=view===name||(name==='Extract'&&view==='Review');
  return <button key={name} className={`nav-item${selected?' selected':''}`} aria-label={label} title={label} aria-current={selected?'page':undefined} onClick={()=>onNavigate(name)}>{name==='Aegis agent V2'?<AgentLogo size={24}/>:<Icon size={18}/>}<span className="nav-item-label">{label}</span></button>;
 };
 return <nav aria-label="Workspace pages">
  {link('Home','Home',Database)}
  {link('Aegis agent V2','Aegis Agent',Database)}
  <button className={`nav-item nav-group-toggle${onboardViews.includes(view)?' group-active':''}`} aria-label="Onboard" aria-expanded={onboardOpen} aria-controls="onboard-navigation" onClick={()=>setOnboardOpen(!onboardOpen)}><FolderPlus size={18}/><span className="nav-item-label">Onboard</span><ChevronRight size={14} className={onboardOpen?'rotated':''}/></button>
  <div id="onboard-navigation" className="nav-submenu" hidden={!onboardOpen}>
   {isAdmin&&link('Onboard dataset','Onboard dataset',FolderPlus)}{link('Datasets','Dataset',BookOpen)}{link('Prompt templates','Prompt',FileText)}{link('Extract Data','Extract',Table2)}{link('Extract','Review',FileSearch)}
  </div>
  <button className={`nav-item nav-more${modelViews.includes(view)?' group-active':''}`} aria-label="Manage workspace" aria-expanded={adminOpen} aria-controls="admin-navigation" onClick={onAdminToggle}><Settings2 size={18}/><span className="nav-item-label">Manage workspace</span><ChevronRight size={14} className={adminOpen?'rotated':''}/></button>
  {adminOpen&&<div id="admin-navigation" className="admin-navigation">{isAdmin&&<>{link('Model Registration','Model Registration',Layers)}{link('Model Mapping','Model Mapping',BookOpen)}</>}{adminItems.map(item=>link(item.name,item.name,item.icon))}</div>}
 </nav>;
}
