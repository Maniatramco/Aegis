"use client";
import {useState,type ReactNode,type DragEvent} from 'react';
import dynamic from 'next/dynamic';
import {ArrowRight,CheckCircle2,Database,FileText,FolderOpen,ShieldCheck,Search,Plus,PanelRightClose,PanelRightOpen,ChevronDown,GripVertical,Network,Maximize2,Minimize2,LayoutDashboard,CloudUpload,X} from 'lucide-react';
import {AgentLogo} from './agent-logo';
import {DatasetKnowledgePicker,type DatasetKnowledgeScope} from './dataset-knowledge-picker';
import type {DashboardChatOptions} from './dataset-knowledge-chat';
import {availableKnowledge,boundedKnowledge,addDatasetKnowledge,removeDatasetKnowledge,DATASET_DRAG_TYPE,droppedDatasetIds} from './dataset-knowledge-scope';
import './dataset-dashboard.css';
import './dashboard-landing.css';
import './metadata-relationships.css';

type Entity=Record<string,any>;
const MetadataRelationships=dynamic(()=>import('./metadata-relationships').then(module=>module.MetadataRelationships),{ssr:false});
export function datasetDocuments(documents:Entity[],id:string){return documents.filter(doc=>(doc.dataset_id||doc.kb_id||doc.parent_id)===id);}
export function datasetReadiness(dataset:Entity,documents:Entity[]){
 const ready=documents.filter(doc=>doc.status==='ready'&&!doc.requires_reindex).length;
 const failed=documents.filter(doc=>['failed','cancelled'].includes(doc.status)).length;
 const pending=documents.filter(doc=>['queued','processing','running'].includes(doc.status)).length;
 const stale=documents.filter(doc=>doc.status==='ready'&&doc.requires_reindex).length;
 return {ready,label:dataset.active===false?'Inactive':failed?`${failed} need attention`:pending?`${pending} processing`:stale?`${stale} need reindex`:ready?'Knowledge indexed':'No indexed documents',state:dataset.active===false?'inactive':failed?'failed':pending||stale?'pending':ready?'ready':'empty'};
}

export const DASHBOARD_SUGGESTIONS=['Summarize key findings','Find important terms and dates','Compare details across sources'];
const greeting=(hour:number)=>hour<12?'Good morning':hour<17?'Good afternoon':'Good evening';
/** Counts come only from the loaded, accessible records; nothing is estimated. */
export function dashboardSummary(datasets:Entity[],documents:Entity[]){
 const active=datasets.filter(d=>d.active!==false),docs=documents.filter(doc=>active.some(d=>d.id===(doc.dataset_id||doc.kb_id||doc.parent_id)));
 return {datasets:active.length,indexed:docs.filter(doc=>doc.status==='ready'&&!doc.requires_reindex).length,
  attention:docs.filter(doc=>['failed','cancelled'].includes(doc.status)||doc.status==='ready'&&doc.requires_reindex).length,
  processing:docs.filter(doc=>['queued','processing','running'].includes(doc.status)).length,
  empty:active.filter(d=>!datasetDocuments(documents,d.id).length).length};
}
/** Tell the new chat what was just added and offer questions about it. */
export function knowledgeAnnouncement(next:DatasetKnowledgeScope,previous:DatasetKnowledgeScope,datasets:Entity[],documents:Entity[]){
 const added=next.datasetIds.filter(id=>!previous.datasetIds.includes(id)),ids=added.length?added:next.datasetIds;
 const names=ids.map(id=>datasets.find(d=>d.id===id)?.name).filter(Boolean) as string[];
 const count=next.documentIds?next.documentIds.length:documents.filter(doc=>next.datasetIds.includes(doc.dataset_id||doc.kb_id||doc.parent_id)&&doc.status==='ready'&&!doc.requires_reindex).length;
 if(!names.length)return {notice:'',suggestions:undefined};
 const label=names.length>2?`${names.slice(0,2).join(', ')} and ${names.length-2} more`:names.join(' and ');
 return {notice:`${added.length?'Added':'Using'} ${label} · ${count} indexed source${count===1?'':'s'} in this chat. Earlier chats for other knowledge stay in history.`,
  suggestions:names.length===1?[`Summarize ${names[0]}`,`What are the key facts in ${names[0]}?`,`How does ${names[0]} relate to the other included knowledge?`]:[`Summarize ${label}`,`Compare ${names[0]} with ${names[1]}`,'What evidence supports the main findings?']};
}

type SourceSelection={datasetId:string;ids:string[]}|null;
export function DatasetDashboard({username,datasets,documents,loading,search,onClearSearch,onBrowse,onAddNew,startScope,canManage,renderAgent,guide,selectedId,onSelect,metadataApi,onMetadataReview}:{metadataApi:(path:string,method?:string,body?:unknown,signal?:AbortSignal,quiet?:boolean)=>Promise<any>;onMetadataReview:(id:string)=>void;username:string;selectedId:string;onSelect:(id:string)=>void;datasets:Entity[];documents:Entity[];loading:boolean;search:string;onClearSearch:()=>void;onBrowse:()=>void;onAddNew?:()=>void;startScope?:DatasetKnowledgeScope|null;canManage:boolean;renderAgent:(id:string,onBusy:(busy:boolean)=>void,sourceScope:string[]|null,onSourceChange:(ids:string[])=>void,knowledgeScope?:DatasetKnowledgeScope,options?:DashboardChatOptions)=>ReactNode;guide:ReactNode}){
 // Documents handed over from Add knowledge open straight into chat with exactly that scope.
 const handed=startScope?boundedKnowledge(startScope,datasets,documents):null;
 const [busy,setBusy]=useState(false),[sourcesCollapsed,setSourcesCollapsed]=useState(false),[chatOpen,setChatOpen]=useState(Boolean(handed));
 const [sourceSearch,setSourceSearch]=useState(''),[selection,setSelection]=useState<SourceSelection>(null);
 const [pickerOpen,setPickerOpen]=useState(false),[included,setIncluded]=useState<DatasetKnowledgeScope|null>(handed);
 const [dropActive,setDropActive]=useState(false),[notice,setNotice]=useState('');
 const [metadataOpen,setMetadataOpen]=useState(false);
 const [chatFocused,setChatFocused]=useState(false);
 const [mobilePanel,setMobilePanel]=useState<'datasets'|'chat'|'sources'>('chat');
 // Appended so earlier state slots keep their order.
 const [overview,setOverview]=useState(false),[autoRoom,setAutoRoom]=useState(true),[draft,setDraft]=useState('');
 const [quickOpen,setQuickOpen]=useState(false);
 const [question,setQuestion]=useState<{id:string;text:string}|null>(null),[announcement,setAnnouncement]=useState<{notice:string;suggestions?:string[]}>(handed?knowledgeAnnouncement(handed,{datasetIds:[],documentIds:null},datasets,documents):{notice:''});
 const selected=datasets.find(d=>d.id===selectedId);
 const visible=datasets.filter(d=>`${d.name} ${d.description||''}`.toLowerCase().includes(search.trim().toLowerCase()));
 const workspace=!selectedId;
 const workspaceIds=(included?.datasetIds||datasets.map(d=>d.id)).filter(id=>datasets.some(d=>d.id===id&&d.active!==false)).sort();
 const scoped=selected?datasetDocuments(documents,selected.id):documents.filter(doc=>workspaceIds.includes(doc.dataset_id||doc.kb_id||doc.parent_id)&&(!included?.documentIds||included.documentIds.includes(doc.id)));
 const ready=scoped.filter(doc=>doc.status==='ready'&&!doc.requires_reindex),readyIds=ready.map(doc=>doc.id);
 const selectedSources=selection?.datasetId===selectedId?selection.ids.filter(id=>readyIds.includes(id)):readyIds;
 const allSelected=readyIds.length>0&&selectedSources.length===readyIds.length;
 const sourceScope=allSelected&&ready.length===scoped.length?null:selectedSources;
 const knowledgeScope:DatasetKnowledgeScope={datasetIds:workspaceIds,documentIds:selection?.datasetId===selectedId?selectedSources:included?.documentIds||null};
 const currentScope:DatasetKnowledgeScope=workspace?knowledgeScope:{datasetIds:[selectedId],documentIds:sourceScope};
 const includedIds=workspace?workspaceIds:[selectedId];
 const setSources=(ids:string[])=>setSelection({datasetId:selectedId,ids});
 const landing=!chatOpen||overview,summary=dashboardSummary(datasets,documents);
 const openChat=()=>{setChatOpen(true);setOverview(false);setMobilePanel('chat');};
 const expandChat=()=>{setChatFocused(true);setSourcesCollapsed(true);setMobilePanel('chat');};
 const restoreDashboard=()=>{setChatFocused(false);setSourcesCollapsed(false);setAutoRoom(false);};
 const showOverview=()=>{restoreDashboard();setOverview(true);};
 // Asking is what earns the chat the whole page; selecting knowledge alone does not.
 const grow=()=>{if(autoRoom&&!chatFocused)expandChat();};
 const ask=(event?:{preventDefault?:()=>void})=>{event?.preventDefault?.();const text=draft.trim();if(!text||busy)return;setQuestion({id:String(Date.now()),text});setDraft('');openChat();setAutoRoom(true);expandChat();};
 const addNew=()=>{setPickerOpen(false);(onAddNew||onBrowse)();};
 const choose=(id:string)=>{if(busy)return;setChatOpen(true);setOverview(false);setAutoRoom(true);setMobilePanel('chat');setSourceSearch('');setSelection(null);setNotice('');setAnnouncement({notice:''});if(!id)setIncluded(null);onSelect(id);};
 const include=(scope:DatasetKnowledgeScope)=>{if(busy)return;const next=boundedKnowledge(scope,datasets,documents);setAnnouncement(knowledgeAnnouncement(next,currentScope,datasets,documents));setChatOpen(true);setOverview(false);setMobilePanel('chat');setIncluded(next);setSelection(null);setPickerOpen(false);setSourceSearch('');onSelect('');};
 // Quick add/remove edits the chat's knowledge from the hero without opening the chat.
 const hasIndexed=(id:string)=>datasetDocuments(documents,id).some(doc=>doc.status==='ready'&&!doc.requires_reindex);
 const inScope=datasets.filter(d=>d.active!==false&&includedIds.includes(d.id)&&hasIndexed(d.id)),addable=datasets.filter(d=>d.active!==false&&!includedIds.includes(d.id)&&hasIndexed(d.id));
 // Datasets without indexed files add nothing to search, so they do not count as knowledge here.
 const noKnowledge=!inScope.length;
 const quickToggle=(id:string)=>{if(busy)return;const already=includedIds.includes(id),next=boundedKnowledge(already?removeDatasetKnowledge(currentScope,id,datasets,documents):addDatasetKnowledge(currentScope,[id],datasets,documents),datasets,documents);setAnnouncement(knowledgeAnnouncement(next,currentScope,datasets,documents));setIncluded(next);setSelection(null);setSourceSearch('');if(selectedId)onSelect('');setNotice(`${datasets.find(d=>d.id===id)?.name||'Dataset'} ${already?'removed from':'added to'} this chat's knowledge.`);};
 const useAll=()=>{if(busy)return;setIncluded(null);setSelection(null);setAnnouncement({notice:''});if(selectedId)onSelect('');setNotice('This chat uses all accessible knowledge.');};
 const chatOptions:DashboardChatOptions={initialQuestion:question,onInitialSent:()=>setQuestion(null),onAsk:grow,notice:announcement.notice,suggestions:announcement.suggestions};
 const scopeLabel=workspace?included?`${workspaceIds.length} included dataset${workspaceIds.length===1?'':'s'}`:`All accessible knowledge · ${summary.datasets} dataset${summary.datasets===1?'':'s'}`:selected?.name||'Selected dataset';
 const toggleDataset=(id:string)=>{if(busy)return;const already=includedIds.includes(id);include(already?removeDatasetKnowledge(currentScope,id,datasets,documents):addDatasetKnowledge(currentScope,[id],datasets,documents));setNotice(`${datasets.find(d=>d.id===id)?.name||'Dataset'} ${already?'removed from':'added to'} this chat's knowledge.`);};
 const drop=(event:DragEvent<HTMLElement>)=>{event.preventDefault();setDropActive(false);if(busy)return;const ids=droppedDatasetIds(event.dataTransfer.getData(DATASET_DRAG_TYPE),datasets).filter(id=>availableKnowledge(datasets,documents).some(doc=>(doc.dataset_id||doc.kb_id||doc.parent_id)===id));if(!ids.length){setNotice('Choose an accessible dataset with indexed files to add knowledge.');return;}include(addDatasetKnowledge(currentScope,ids,datasets,documents));setNotice(`${ids.map(id=>datasets.find(d=>d.id===id)?.name).join(', ')} included in this chat's knowledge.`);};
 const dragOver=(event:DragEvent<HTMLElement>)=>{if(!busy&&event.dataTransfer.types.includes(DATASET_DRAG_TYPE)){event.preventDefault();event.dataTransfer.dropEffect='copy';setDropActive(true);}};
 return <section className="dataset-dashboard notebook-dashboard" aria-label="Dataset dashboard" data-chat-focused={chatFocused} data-mobile-panel={mobilePanel} data-mode={landing?'landing':'workspace'}>
  <div className="dashboard-top" hidden={chatFocused}>
  <header className="notebook-heading"><div><Database size={19}/><h2>{username}'s Knowledge Source</h2><span className="notebook-private"><ShieldCheck size={12}/>Dataset access protected</span></div><div className="metadata-dashboard-actions"><button data-open-metadata type="button" className="btn" aria-label="Metadata Relationships" title="Metadata Relationships" disabled={busy||loading} onClick={()=>setMetadataOpen(true)}><Network size={16}/><span>Metadata Relationships</span></button>{!canManage&&<button type="button" className="btn" aria-label="Browse datasets" title="Browse datasets" onClick={onBrowse}><Plus size={15}/><span>Browse datasets</span></button>}</div></header>
  {landing&&<div className="dashboard-hero">
   <div className="dashboard-hero-main">
    <h1 className="dashboard-greeting">{greeting(new Date().getHours())}, {username}</h1>
    <p className="dashboard-hero-lead">{summary.datasets?`Ask across your ${summary.datasets} authorized dataset${summary.datasets===1?'':'s'} and ${summary.indexed} indexed source${summary.indexed===1?'':'s'}. Answers cite their evidence and stay within your access.`:'Your datasets appear here once they are assigned to you.'}</p>
    <form className="dashboard-ask" onSubmit={ask}>
     <label htmlFor="dashboard-ask-input" className="sr-only">Ask about your knowledge</label>
     <textarea id="dashboard-ask-input" rows={2} placeholder="Ask about your knowledge…" value={draft} disabled={busy||!summary.datasets} onChange={event=>setDraft(event.target.value)} onKeyDown={event=>{if(event.key==='Enter'&&!event.shiftKey){event.preventDefault();ask();}}}/>
     <div className="dashboard-ask-controls">
      <div className="dashboard-scope-chips" role="group" aria-label={`Knowledge in this chat: ${scopeLabel}`}>
       {inScope.slice(0,4).map(d=><span key={d.id} className="dashboard-chip"><span className="dashboard-chip-label" title={d.name}>{d.name}</span><button type="button" aria-label={`Remove ${d.name} from this chat`} title={`Remove ${d.name}`} disabled={busy} onClick={()=>quickToggle(d.id)}><X size={13}/></button></span>)}
       {inScope.length>4&&<button type="button" className="dashboard-chip dashboard-chip-more" onClick={()=>setPickerOpen(true)}>+{inScope.length-4} more</button>}
       {noKnowledge&&<span className="dashboard-chip dashboard-chip-empty">No indexed knowledge selected</span>}
       <button type="button" className="dashboard-chip-add" aria-expanded={quickOpen} aria-controls="dashboard-quick-add" disabled={busy||!datasets.some(d=>d.active!==false)} onClick={()=>setQuickOpen(!quickOpen)}><Plus size={14}/>Add</button>
      </div>
      <div className="dashboard-ask-actions"><button type="button" className="btn" disabled={busy||!datasets.length} onClick={openChat}>Open chat</button><button type="submit" className="btn primary" disabled={busy||!draft.trim()||noKnowledge}>Ask Aegis<ArrowRight size={16}/></button></div>
     </div>
     {quickOpen&&<div id="dashboard-quick-add" className="dashboard-quick-add" role="group" aria-label="Quick add knowledge">
      <span className="dashboard-quick-title">Add to this chat</span>
      <div className="dashboard-quick-options">{addable.map(d=><button key={d.id} type="button" disabled={busy} onClick={()=>quickToggle(d.id)} aria-label={`Add ${d.name} to this chat`}><Plus size={14}/>{d.name}<small>{datasetDocuments(documents,d.id).filter(doc=>doc.status==='ready'&&!doc.requires_reindex).length} files</small></button>)}{!addable.length&&<span className="dashboard-quick-none">Every indexed dataset is already in this chat.</span>}</div>
      <div className="dashboard-quick-links"><button type="button" className="text-button" onClick={()=>{setQuickOpen(false);setPickerOpen(true);}}>Choose individual files…</button>{(included||selectedId)&&<button type="button" className="text-button" onClick={useAll}>Use all knowledge</button>}<button type="button" className="text-button" onClick={addNew}><CloudUpload size={14}/>Add new knowledge</button></div>
     </div>}
    </form>
    <div className="dashboard-suggestions">{DASHBOARD_SUGGESTIONS.map(prompt=><button key={prompt} type="button" disabled={busy||!summary.datasets} onClick={()=>{setDraft(prompt);document.getElementById('dashboard-ask-input')?.focus();}}>{prompt}</button>)}<button type="button" className="dashboard-new-knowledge" onClick={addNew}><CloudUpload size={15}/>Add new knowledge</button></div>
   </div>
   <dl className="dashboard-stats" aria-label="Knowledge summary">
    <div><dt>Datasets</dt><dd>{summary.datasets}</dd><span>{summary.empty?`${summary.empty} without documents`:'authorized'}</span></div>
    <div><dt>Indexed sources</dt><dd>{summary.indexed}</dd><span>ready to ask</span></div>
    <div data-tone={summary.attention?'warn':undefined}><dt>Need attention</dt><dd>{summary.attention}</dd><span>failed or need reindex</span></div>
    <div><dt>Processing</dt><dd>{summary.processing}</dd><span>{summary.processing?'indexing now':'nothing running'}</span></div>
   </dl>
  </div>}
  </div>
  <nav className="dashboard-panel-switcher" aria-label="Dashboard panels">{(['datasets','chat','sources'] as const).map(panel=><button key={panel} type="button" aria-pressed={mobilePanel===panel} onClick={()=>{restoreDashboard();setMobilePanel(panel);}}>{panel==='datasets'?`Datasets (${datasets.length})`:panel==='sources'?`Sources (${scoped.length})`:'Knowledge Chat'}</button>)}</nav>
  <div className="notebook-workspace" data-sources-collapsed={sourcesCollapsed}>
   <aside className="dashboard-datasets notebook-panel" aria-label="Authorized datasets" hidden={chatFocused}><header className="notebook-panel-heading"><h3><Database size={16}/>Authorized datasets <span>{datasets.length}</span></h3>{landing&&<button type="button" className="btn primary notebook-add-source" disabled={busy||!datasets.some(d=>d.active!==false)} onClick={()=>setPickerOpen(true)}><Plus size={16}/>Add Dataset Knowledge</button>}</header>
  <div className="dashboard-dataset-rail" role="region" aria-label="Onboarded datasets" tabIndex={0} aria-busy={loading}>
   {datasets.length>0&&<button type="button" className="dashboard-dataset workspace-knowledge-card" aria-label="Chat with all accessible dataset knowledge" aria-pressed={workspace&&!included} disabled={busy} onClick={()=>choose('')}><span className="dashboard-dataset-icon"><Database size={17}/></span><span className="notebook-card-copy"><strong>All accessible knowledge</strong><span>{datasets.filter(d=>d.active!==false).length} authorized datasets</span></span>{workspace&&!included?<CheckCircle2 size={16}/>:<ArrowRight size={16}/>}</button>}
   {loading&&!datasets.length?<p className="dashboard-empty">Loading your datasets…</p>:visible.map(d=>{const docs=datasetDocuments(documents,d.id),state=datasetReadiness(d,docs),canInclude=d.active!==false&&state.ready>0;return <div key={d.id} className="dashboard-dataset-tile" data-included={includedIds.includes(d.id)} draggable={!busy&&canInclude} onDragStart={event=>{if(busy||!canInclude){event.preventDefault();return;}event.dataTransfer.setData(DATASET_DRAG_TYPE,JSON.stringify([d.id]));event.dataTransfer.effectAllowed='copy';}} onDragEnd={()=>setDropActive(false)}><button type="button" className="dashboard-dataset" aria-label={`Ask Aegis about ${d.name}`} aria-pressed={selectedId===d.id} disabled={busy} onClick={()=>choose(d.id)}><span className="dashboard-dataset-icon"><Database size={17}/></span><span className="notebook-card-copy"><strong title={d.name}>{d.name}</strong><span>{docs.length} source{docs.length===1?'':'s'} · <span data-state={state.state}>{state.label}</span></span></span><ArrowRight size={16}/></button><label className="dashboard-dataset-include" title={canInclude?'Include this dataset with your other selected knowledge':'Indexed files are required'}><input type="checkbox" aria-label={`Include dataset ${d.name} in knowledge`} checked={includedIds.includes(d.id)} disabled={busy||!canInclude} onChange={()=>toggleDataset(d.id)}/><span>{includedIds.includes(d.id)?'Included':'Include dataset'}</span><GripVertical size={13} aria-hidden="true"/></label></div>;})}
   {!loading&&!visible.length&&<div className="dashboard-empty"><strong>{datasets.length?'No matching datasets':canManage?'No datasets available':'No datasets assigned'}</strong><p>{datasets.length?'Try a different name or description.':canManage?'Open the dataset workspace to get started.':'Ask your administrator to assign a dataset.'}</p><button type="button" className="btn" onClick={datasets.length?onClearSearch:onBrowse}>{datasets.length?'Clear search':'Browse datasets'}</button></div>}
  </div>
<div className="dashboard-datasets-footer"><ShieldCheck size={14}/><span>Only datasets you can access.</span></div></aside>
   <section className="dashboard-agent notebook-chat notebook-panel" aria-label="Dataset knowledge workspace chat" hidden={landing}><header className="notebook-panel-heading"><h3><AgentLogo size={24}/>Dataset Knowledge Chat</h3><div className="notebook-chat-heading-actions"><button type="button" className="btn icon dashboard-layout-icon" aria-label="Back to Dashboard overview" title="Back to Dashboard overview" onClick={showOverview}><LayoutDashboard size={18} aria-hidden="true"/></button><span className="notebook-chat-scope">{workspace?included?`${workspaceIds.length} included datasets`:'All accessible datasets':allSelected?'All indexed sources':`${selectedSources.length} selected sources`}</span>{chatOpen&&<button type="button" className="btn icon dashboard-layout-icon notebook-layout-toggle" aria-label={chatFocused?'Restore Dashboard layout':'Expand Dataset Knowledge Chat'} title={chatFocused?'Restore Dashboard layout':'Expand Dataset Knowledge Chat'} aria-pressed={chatFocused} onClick={chatFocused?restoreDashboard:expandChat}>{chatFocused?<Minimize2 size={18} aria-hidden="true"/>:<Maximize2 size={18} aria-hidden="true"/>}</button>}</div></header>  <div className="dashboard-knowledge-toolbar" role="toolbar" aria-label="Dataset knowledge actions"><div><strong>Included knowledge</strong><span>{includedIds.length} dataset{includedIds.length===1?'':'s'} · {selectedSources.length} source{selectedSources.length===1?'':'s'} included</span></div><div className="dashboard-knowledge-controls">{chatFocused&&<button type="button" className="btn icon dashboard-layout-icon dashboard-show-sources" aria-label={sourcesCollapsed?'Show sources':'Hide sources'} title={sourcesCollapsed?'Show sources':'Hide sources'} aria-expanded={!sourcesCollapsed} aria-controls="dashboard-dataset-sources" onClick={()=>{setSourcesCollapsed(!sourcesCollapsed);if(sourcesCollapsed)setMobilePanel('sources');}}>{sourcesCollapsed?<PanelRightOpen size={18} aria-hidden="true"/>:<PanelRightClose size={18} aria-hidden="true"/>}</button>}<button type="button" className="btn primary notebook-add-source" disabled={busy||!datasets.some(d=>d.active!==false)} onClick={()=>setPickerOpen(true)}><Plus size={16}/>Add Dataset Knowledge</button><button type="button" className="btn notebook-new-knowledge" aria-label="Add new knowledge from cloud storage" title="Add new knowledge from cloud storage" disabled={busy} onClick={addNew}><CloudUpload size={16} aria-hidden="true"/><span>New</span></button></div></div>
  <p className="dashboard-knowledge-notice" role="status" aria-live="polite">{notice}</p>
{selected?.active===false?<div className="dashboard-agent-empty"><h3>This dataset is inactive</h3><p>Activate it in the dataset workspace before starting new work.</p></div>:workspace&&included&&!workspaceIds.length?<div className="dashboard-agent-empty"><AgentLogo size={55}/><h3>Choose knowledge for this chat</h3><p>Select dataset checkboxes, drag a dataset into Sources, or use Add Dataset Knowledge.</p></div>:(selected||workspace&&datasets.length>0)?chatOpen?renderAgent(selected?.id||'',setBusy,workspace?null:sourceScope,setSources,workspace?knowledgeScope:undefined,chatOptions):<div className="dashboard-agent-empty"><AgentLogo size={65}/><h3>Ask about your knowledge</h3><p>Choose datasets on the left, review Sources on the right, then open chat. No summary runs automatically.</p><button type="button" className="btn primary" onClick={openChat}>Open chat</button></div>:<div className="dashboard-agent-empty"><AgentLogo size={65}/><h3>Your sources. A conversation away.</h3><p>Choose an onboarded dataset to ask questions, connect details across documents and follow the evidence.</p><div className="notebook-empty-prompts"><span>Summarize key findings<ArrowRight size={13}/></span><span>Find important terms and dates<ArrowRight size={13}/></span><span>Compare details across sources<ArrowRight size={13}/></span></div></div>}</section>
   <aside id="dashboard-dataset-sources" className="notebook-sources notebook-panel" aria-label="Dataset sources" hidden={chatFocused&&sourcesCollapsed} data-drop-active={dropActive} onDragOver={dragOver} onDragLeave={event=>{if(!event.currentTarget.contains(event.relatedTarget as Node|null))setDropActive(false);}} onDrop={drop}><header className="notebook-panel-heading"><h3><FileText size={16}/>Sources <span>{scoped.length}</span></h3><button type="button" className="btn icon" aria-label={sourcesCollapsed?'Expand sources':'Collapse sources'} aria-expanded={!sourcesCollapsed} aria-controls="notebook-source-content" onClick={()=>setSourcesCollapsed(!sourcesCollapsed)}>{sourcesCollapsed?<PanelRightOpen size={17}/>:<PanelRightClose size={17}/>}</button></header><div id="notebook-source-content" className="notebook-source-content" hidden={sourcesCollapsed}>
    <div className="notebook-dataset-drop-hint"><Database size={16}/><span>{dropActive?'Drop to include dataset knowledge':'Use dataset checkboxes or drop a dataset here.'}</span></div>
    {(selected||workspace&&datasets.length>0)?<><label className="notebook-source-search"><Search size={14}/><input aria-label="Search dataset sources" placeholder="Search sources" value={sourceSearch} onChange={event=>setSourceSearch(event.target.value)}/></label><div className="notebook-source-selection"><span>{selectedSources.length} / {ready.length} indexed selected</span><label>Select all<input type="checkbox" aria-label="Select all indexed sources" checked={allSelected} disabled={busy||!ready.length} onChange={()=>setSources(allSelected?[]:readyIds)}/></label></div>
     {!workspace&&selectedSources.length>20&&sourceScope!==null&&<p className="notebook-source-warning" role="status">Choose up to 20 sources, or select all to search the entire dataset.</p>}
     <ul className="dashboard-source-list">{scoped.filter(doc=>doc.name.toLowerCase().includes(sourceSearch.trim().toLowerCase())).map(doc=>{const indexed=readyIds.includes(doc.id);return <li key={doc.id}><label title={doc.name}><span className="notebook-file-icon"><FileText size={16}/></span><span className="notebook-source-copy"><strong>{doc.name}</strong><small>{doc.requires_reindex?'Reindex required':doc.status==='ready'?(workspace?datasets.find(d=>d.id===(doc.dataset_id||doc.kb_id||doc.parent_id))?.name||'Indexed source':'Indexed source'):doc.status||'Pending'}</small></span><input type="checkbox" aria-label={`Include source ${doc.name}`} checked={selectedSources.includes(doc.id)} disabled={busy||!indexed} onChange={()=>setSources(selectedSources.includes(doc.id)?selectedSources.filter(id=>id!==doc.id):[...selectedSources,doc.id])}/></label></li>;})}</ul>
     {!scoped.length&&<div className="notebook-empty"><FolderOpen size={28}/><p>{workspace?'Include datasets or indexed files using Add Dataset Knowledge.':'Add documents to this dataset to start building its knowledge.'}</p></div>}
     {scoped.length>0&&!scoped.some(doc=>doc.name.toLowerCase().includes(sourceSearch.trim().toLowerCase()))&&<p className="notebook-muted">No matching sources.</p>}
    </>:<div className="notebook-empty"><FolderOpen size={30}/><h4>Your evidence lives here</h4><p>Choose a dataset to see its documents and select sources for your questions.</p></div>}
    <div className="notebook-source-footer"><ShieldCheck size={14}/><span>Originals preserved. Answers stay within your permitted scope.</span></div>
   </div></aside>
  </div>
  {pickerOpen&&<DatasetKnowledgePicker datasets={datasets} documents={documents} initial={currentScope} onInclude={scope=>{include(scope);setNotice('Selected dataset knowledge is included in this chat.');}} onAddNew={addNew} onClose={()=>setPickerOpen(false)}/>}
  {metadataOpen&&<MetadataRelationships datasets={datasets} initialDatasetIds={currentScope.datasetIds} api={metadataApi} onReview={onMetadataReview} onClose={()=>{setMetadataOpen(false);requestAnimationFrame(()=>document.querySelector<HTMLButtonElement>('[data-open-metadata]')?.focus());}}/>}
  <details className="dashboard-guide" hidden={chatFocused}><summary>How Aegis works <span>Explore the end-to-end document workflow</span><ChevronDown size={13}/></summary>{guide}</details>
 </section>;
}
