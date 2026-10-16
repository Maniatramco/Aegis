"use client";
import {useState,type ReactNode} from 'react';
import {ArrowRight,CheckCircle2,Database,FileText,FolderOpen,ShieldCheck,Search,Plus,PanelLeftClose,PanelLeftOpen,ChevronDown} from 'lucide-react';
import {AgentLogo} from './agent-logo';
import {DatasetKnowledgePicker,type DatasetKnowledgeScope} from './dataset-knowledge-picker';
import './dataset-dashboard.css';

type Entity=Record<string,any>;
export function datasetDocuments(documents:Entity[],id:string){return documents.filter(doc=>(doc.dataset_id||doc.kb_id||doc.parent_id)===id);}
export function datasetReadiness(dataset:Entity,documents:Entity[]){
 const ready=documents.filter(doc=>doc.status==='ready'&&!doc.requires_reindex).length;
 const failed=documents.filter(doc=>['failed','cancelled'].includes(doc.status)).length;
 const pending=documents.filter(doc=>['queued','processing','running'].includes(doc.status)).length;
 const stale=documents.filter(doc=>doc.status==='ready'&&doc.requires_reindex).length;
 return {ready,label:dataset.active===false?'Inactive':failed?`${failed} need attention`:pending?`${pending} processing`:stale?`${stale} need reindex`:ready?'Knowledge indexed':'No indexed documents',state:dataset.active===false?'inactive':failed?'failed':pending||stale?'pending':ready?'ready':'empty'};
}
type SourceSelection={datasetId:string;ids:string[]}|null;
export function DatasetDashboard({username,datasets,documents,loading,search,onClearSearch,onBrowse,onOnboard,canManage,renderAgent,guide,selectedId,onSelect}:{username:string;selectedId:string;onSelect:(id:string)=>void;datasets:Entity[];documents:Entity[];loading:boolean;search:string;onClearSearch:()=>void;onBrowse:()=>void;onOnboard:()=>void;canManage:boolean;renderAgent:(id:string,onBusy:(busy:boolean)=>void,sourceScope:string[]|null,onSourceChange:(ids:string[])=>void,knowledgeScope?:DatasetKnowledgeScope,autoSummary?:boolean)=>ReactNode;guide:ReactNode}){
 const [busy,setBusy]=useState(false),[sourcesCollapsed,setSourcesCollapsed]=useState(false);
 const [sourceSearch,setSourceSearch]=useState(''),[selection,setSelection]=useState<SourceSelection>(null);
 const [pickerOpen,setPickerOpen]=useState(false),[included,setIncluded]=useState<DatasetKnowledgeScope|null>(null);
 const selected=datasets.find(d=>d.id===selectedId);
 const visible=datasets.filter(d=>`${d.name} ${d.description||''}`.toLowerCase().includes(search.trim().toLowerCase()));
 const workspace=!selectedId;
 const workspaceIds=(included?.datasetIds||datasets.map(d=>d.id)).filter(id=>datasets.some(d=>d.id===id)).sort();
 const scoped=selected?datasetDocuments(documents,selected.id):documents.filter(doc=>workspaceIds.includes(doc.dataset_id||doc.kb_id||doc.parent_id)&&(!included?.documentIds||included.documentIds.includes(doc.id)));
 const ready=scoped.filter(doc=>doc.status==='ready'&&!doc.requires_reindex),readyIds=ready.map(doc=>doc.id);
 const selectedSources=selection?.datasetId===selectedId?selection.ids.filter(id=>readyIds.includes(id)):readyIds;
 const allSelected=readyIds.length>0&&selectedSources.length===readyIds.length;
 const sourceScope=allSelected&&ready.length===scoped.length?null:selectedSources;
 const knowledgeScope:DatasetKnowledgeScope={datasetIds:workspaceIds,documentIds:selection?.datasetId===selectedId?selectedSources:included?.documentIds||null};
 const setSources=(ids:string[])=>setSelection({datasetId:selectedId,ids});
 const choose=(id:string)=>{setSourceSearch('');setSelection(null);if(!id)setIncluded(null);onSelect(id);};
 const include=(scope:DatasetKnowledgeScope)=>{setIncluded(scope);setSelection(null);setPickerOpen(false);setSourceSearch('');onSelect('');};
 return <section className="dataset-dashboard notebook-dashboard" aria-label="Dataset dashboard">
  <header className="notebook-heading"><div><Database size={19}/><h2>{username}'s Knowledge Source</h2><span className="notebook-private"><ShieldCheck size={12}/>Dataset access protected</span></div><button type="button" className="btn" onClick={canManage?onOnboard:onBrowse}><Plus size={15}/>{canManage?'Onboard dataset':'Browse datasets'}</button></header>
  <div className="dashboard-section-label"><h3>Onboarded datasets <span>{datasets.length}</span></h3><span>{busy?'Finish the current Agent request before switching datasets.':'Choose a dataset to explore its sources and results.'}</span></div>
  <div className="dashboard-dataset-rail" role="region" aria-label="Onboarded datasets" tabIndex={0} aria-busy={loading}>
   {datasets.length>0&&<button type="button" className="dashboard-dataset workspace-knowledge-card" aria-label="Chat with all accessible dataset knowledge" aria-pressed={workspace&&!included} disabled={busy} onClick={()=>choose('')}><span className="dashboard-dataset-icon"><Database size={17}/></span><span className="notebook-card-copy"><strong>All accessible knowledge</strong><span>{datasets.length} datasets · Workspace overview</span></span>{workspace&&!included?<CheckCircle2 size={16}/>:<ArrowRight size={16}/>}</button>}
   {loading&&!datasets.length?<p className="dashboard-empty">Loading your datasets…</p>:visible.map(d=>{const docs=datasetDocuments(documents,d.id),state=datasetReadiness(d,docs);return <button type="button" key={d.id} className="dashboard-dataset" aria-label={`Ask Aegis about ${d.name}`} aria-pressed={selectedId===d.id} disabled={busy} onClick={()=>choose(d.id)}><span className="dashboard-dataset-icon"><Database size={17}/></span><span className="notebook-card-copy"><strong title={d.name}>{d.name}</strong><span>{docs.length} source{docs.length===1?'':'s'}<span> · </span><span data-state={state.state}>{state.label}</span></span></span>{selectedId===d.id?<CheckCircle2 size={16}/>:<ArrowRight size={16}/>}</button>;})}
   {!loading&&!visible.length&&<div className="dashboard-empty"><strong>{datasets.length?'No matching datasets':canManage?'Onboard your first dataset':'No datasets assigned'}</strong><p>{datasets.length?'Try a different name or description.':canManage?'Add your documents to begin.':'Ask your administrator to assign a dataset.'}</p><button type="button" className="btn" onClick={datasets.length?onClearSearch:onBrowse}>{datasets.length?'Clear search':'Browse datasets'}</button></div>}
  </div>
  <div className="notebook-workspace" data-sources-collapsed={sourcesCollapsed}>
   <aside className="notebook-sources notebook-panel" aria-label="Dataset sources"><header className="notebook-panel-heading"><h3><FileText size={16}/>Sources <span>{scoped.length}</span></h3><button type="button" className="btn icon" aria-label={sourcesCollapsed?'Expand sources':'Collapse sources'} aria-expanded={!sourcesCollapsed} aria-controls="notebook-source-content" onClick={()=>setSourcesCollapsed(!sourcesCollapsed)}>{sourcesCollapsed?<PanelLeftOpen size={17}/>:<PanelLeftClose size={17}/>}</button></header><div id="notebook-source-content" className="notebook-source-content" hidden={sourcesCollapsed}>
    <button type="button" className="btn notebook-add-source" disabled={busy||!datasets.length} onClick={()=>setPickerOpen(true)}><Plus size={15}/>Add Dataset Knowledge</button>
    {(selected||workspace&&datasets.length>0)?<><label className="notebook-source-search"><Search size={14}/><input aria-label="Search dataset sources" placeholder="Search sources" value={sourceSearch} onChange={event=>setSourceSearch(event.target.value)}/></label><div className="notebook-source-selection"><span>{selectedSources.length} / {ready.length} indexed selected</span><label>Select all<input type="checkbox" aria-label="Select all indexed sources" checked={allSelected} disabled={busy||!ready.length} onChange={()=>setSources(allSelected?[]:readyIds)}/></label></div>
     {!workspace&&selectedSources.length>20&&sourceScope!==null&&<p className="notebook-source-warning" role="status">Choose up to 20 sources, or select all to search the entire dataset.</p>}
     <ul className="dashboard-source-list">{scoped.filter(doc=>doc.name.toLowerCase().includes(sourceSearch.trim().toLowerCase())).map(doc=>{const indexed=readyIds.includes(doc.id);return <li key={doc.id}><label title={doc.name}><span className="notebook-file-icon"><FileText size={16}/></span><span className="notebook-source-copy"><strong>{doc.name}</strong><small>{doc.requires_reindex?'Reindex required':doc.status==='ready'?(workspace?datasets.find(d=>d.id===(doc.dataset_id||doc.kb_id||doc.parent_id))?.name||'Indexed source':'Indexed source'):doc.status||'Pending'}</small></span><input type="checkbox" aria-label={`Include source ${doc.name}`} checked={selectedSources.includes(doc.id)} disabled={busy||!indexed} onChange={()=>setSources(selectedSources.includes(doc.id)?selectedSources.filter(id=>id!==doc.id):[...selectedSources,doc.id])}/></label></li>;})}</ul>
     {!scoped.length&&<div className="notebook-empty"><FolderOpen size={28}/><p>Add documents to this dataset to start building its knowledge.</p></div>}
     {scoped.length>0&&!scoped.some(doc=>doc.name.toLowerCase().includes(sourceSearch.trim().toLowerCase()))&&<p className="notebook-muted">No matching sources.</p>}
    </>:<div className="notebook-empty"><FolderOpen size={30}/><h4>Your evidence lives here</h4><p>Choose a dataset above to see its documents and select sources for your questions.</p></div>}
    <div className="notebook-source-footer"><ShieldCheck size={14}/><span>Originals preserved. Answers stay within your permitted scope.</span></div>
   </div></aside>
   <section className="dashboard-agent notebook-chat notebook-panel" aria-label="Dataset knowledge workspace chat"><header className="notebook-panel-heading"><h3><AgentLogo size={24}/>Dataset Knowledge Chat</h3><span className="notebook-chat-scope">{workspace?included?'Included dataset knowledge':'All accessible datasets':allSelected?'All indexed sources':`${selectedSources.length} selected sources`}</span></header>{selected?.active===false?<div className="dashboard-agent-empty"><h3>This dataset is inactive</h3><p>Activate it in the dataset workspace before starting new work.</p></div>:(selected||workspace&&datasets.length>0)?renderAgent(selected?.id||'',setBusy,workspace?null:sourceScope,setSources,workspace?knowledgeScope:undefined,workspace&&selection===null):<div className="dashboard-agent-empty"><AgentLogo size={65}/><h3>Your sources. A conversation away.</h3><p>Choose an onboarded dataset to ask questions, connect details across documents and follow the evidence.</p><div className="notebook-empty-prompts"><span>Summarize key findings<ArrowRight size={13}/></span><span>Find important terms and dates<ArrowRight size={13}/></span><span>Compare details across sources<ArrowRight size={13}/></span></div></div>}</section>

  </div>
  {pickerOpen&&<DatasetKnowledgePicker datasets={datasets} documents={documents} initial={workspace?knowledgeScope:{datasetIds:[selectedId],documentIds:selectedSources}} onInclude={include} onClose={()=>setPickerOpen(false)}/>}
  <details className="dashboard-guide"><summary>How Aegis works <span>Explore the end-to-end document workflow</span><ChevronDown size={13}/></summary>{guide}</details>
 </section>;
}
