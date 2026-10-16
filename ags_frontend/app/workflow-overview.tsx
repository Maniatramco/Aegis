"use client";
import {useEffect,useId,useRef,useState} from 'react';
import {Activity,ArrowRight,Braces,CheckCheck,ChevronDown,Database,FileCheck2,FileText,FolderInput,GitBranch,Layers,LockKeyhole,Maximize2,MessagesSquare,ScanText,Search,Settings2,ShieldCheck,Users,X} from 'lucide-react';
import {AgentLogo} from './agent-logo';
import './workflow-overview.css';

type Destination='Datasets'|'Prompt templates'|'Extract Data'|'Extract'|'Aegis agent V2'|'Jobs & activity'|'Model Registration'|'Model Mapping'|'Storage'|'Users & passwords';
type Icon=typeof Database;
type Stage={title:string;summary:string;tools:{label:string;icon:Icon}[];heading:string;detail:string;points:string[];action:string;destination:Destination;boundary:string};
const stages:Stage[]=[
 {title:'Onboard your data',summary:'Organize documents and define the result you need.',tools:[{label:'Dataset',icon:Database},{label:'Source files',icon:FolderInput},{label:'Saved originals',icon:ShieldCheck}],heading:'Give every document a place and a purpose',detail:'Choose an accessible dataset, add source files and define a reusable extraction prompt. Dataset model mappings determine which models are available.',points:['Keep related files and access permissions together.','Use prompt schemas to describe the fields you want to extract.','Confirm the processing scope before a workflow starts.'],action:'Explore datasets',destination:'Datasets',boundary:'Dataset access is enforced throughout the workflow.'},
 {title:'Enrich knowledge',summary:'Turn source files into searchable evidence.',tools:[{label:'Read / OCR',icon:ScanText},{label:'Embed',icon:Layers},{label:'Index',icon:Search}],heading:'Make source material ready for retrieval',detail:'The processing worker reads documents, uses OCR when needed, creates embeddings and publishes searchable knowledge through the configured services.',points:['Track processing and errors in Jobs & activity.','Use the embedding and OCR connections mapped to the dataset.','Preserve original documents alongside their saved results.'],action:'View jobs & activity',destination:'Jobs & activity',boundary:'External model processing requires the existing consent checks.'},
 {title:'Extract & review',summary:'Create structured results and keep people in control.',tools:[{label:'Prompt & schema',icon:FileText},{label:'Extract',icon:Braces},{label:'Review & save',icon:FileCheck2}],heading:'Get structured results you can check and reuse',detail:'Select documents, a prompt and an eligible extraction model. Review the saved result against the source, correct fields and use re-extraction when the instructions change.',points:['Review the plan and approve processing before execution.','Retain saved results and their version history.','Use the existing result downloads and review controls.'],action:'Open Extract',destination:'Extract Data',boundary:'Opening a screen never starts an extraction automatically.'},
 {title:'Ask grounded questions',summary:'Ask across your permitted evidence, with citations.',tools:[{label:'Scope & retrieve',icon:Search},{label:'Rerank & answer',icon:MessagesSquare},{label:'Validate & cite',icon:CheckCheck}],heading:'Ask Aegis and follow the evidence',detail:'Aegis Agent uses the selected dataset and document scope to retrieve evidence, rerank it, generate an answer and validate the answer and its citations.',points:['Choose a dataset and narrow the document scope.','Use a model that is enabled for that dataset.','Inspect source citations and export the conversation.'],action:'Open Aegis Agent',destination:'Aegis agent V2',boundary:'Scope → hybrid retrieval → CPU rerank → generation → validation.'},
];
const features:{title:string;detail:string;icon:Icon;destination:Destination}[]=[
 {title:'Dataset workspace',detail:'Organize source documents and work within your assigned datasets.',icon:Database,destination:'Datasets'},
 {title:'Prompt templates',detail:'Define reusable instructions and structured extraction schemas.',icon:FileText,destination:'Prompt templates'},
 {title:'Document extraction',detail:'Choose source files, a prompt and a mapped model before confirming.',icon:Braces,destination:'Extract Data'},
 {title:'Review & re-extract',detail:'Check source evidence, correct saved fields and revisit result versions.',icon:FileCheck2,destination:'Extract'},
 {title:'Aegis Agent',detail:'Ask scoped questions, inspect citations and coordinate supported workflows.',icon:MessagesSquare,destination:'Aegis agent V2'},
 {title:'Jobs & activity',detail:'Follow real processing progress and inspect failures or completed work.',icon:Activity,destination:'Jobs & activity'},
];
const adminFeatures:{title:string;detail:string;icon:Icon;destination:Destination}[]=[
 {title:'Model registration',detail:'Manage supported provider connections and registered models.',icon:Layers,destination:'Model Registration'},
 {title:'Dataset model mappings',detail:'Assign eligible models and defaults to each dataset.',icon:GitBranch,destination:'Model Mapping'},
 {title:'Storage & connections',detail:'Manage saved destinations and inspect connection diagnostics.',icon:Settings2,destination:'Storage'},
 {title:'Users & access',detail:'Manage accounts, roles and dataset permissions.',icon:Users,destination:'Users & passwords'},
];
function WorkflowMap({selected,onSelect}:{selected:number;onSelect:(stage:number)=>void}){
 const outputs=['Protected source files','Searchable knowledge','Versioned JSON / Parquet','Validated answers & citations'];
 return <><div className="aegis-flow-scroll" role="region" aria-label="End-to-end Aegis workflow" tabIndex={0}>
  <div className="aegis-workflow-map" aria-label="Continuous document-to-answer flow">{stages.map((stage,index)=><section key={stage.title} className="aegis-workflow-zone" aria-label={`Stage ${index+1}: ${stage.title}`}>
   <button type="button" className="aegis-flow-phase" aria-pressed={selected===index} onClick={()=>onSelect(index)}><span className="aegis-stage-number">{index+1}</span><strong>{stage.title}</strong></button>
   <div className="aegis-flow-tools">{stage.tools.map(({label,icon:Icon},toolIndex)=><div className="aegis-flow-node" key={label}>
    <span className="aegis-flow-icon"><Icon size={28} strokeWidth={1.6} aria-hidden="true"/></span><span className="aegis-flow-label">{label}</span>
    {(index<stages.length-1||toolIndex<stage.tools.length-1)&&<ArrowRight className="aegis-flow-arrow" size={17} strokeWidth={1.5} aria-hidden="true"/>}
   </div>)}</div>
   <p className="aegis-flow-summary">{stage.summary}</p><span className="aegis-flow-output">{outputs[index]}</span>
  </section>)}</div>
 </div><p className="aegis-flow-scroll-hint">Scroll horizontally to follow the complete workflow <ArrowRight size={12} aria-hidden="true"/></p></>;
}
function StageDetail({selected,onNavigate}:{selected:number;onNavigate:(destination:Destination)=>void}){
 const stage=stages[selected];
 return <section className="aegis-stage-detail" aria-label={`${stage.title} details`}>
  <div className="aegis-stage-copy"><span className="aegis-guide-eyebrow">STAGE {selected+1} / 4</span><h3>{stage.heading}</h3><p>{stage.detail}</p><button type="button" className="btn aegis-guide-action" onClick={()=>onNavigate(stage.destination)}>{stage.action}<ArrowRight size={15} aria-hidden="true"/></button></div>
  <div><ul>{stage.points.map(point=><li key={point}><CheckCheck size={16} aria-hidden="true"/><span>{point}</span></li>)}</ul><p className="aegis-guide-boundary"><ShieldCheck size={15} aria-hidden="true"/><span>{stage.boundary}</span></p></div>
 </section>;
}
function ExpandedWorkflow({selected,onSelect,onClose,onNavigate}:{selected:number;onSelect:(stage:number)=>void;onClose:()=>void;onNavigate:(destination:Destination)=>void}){
 const dialog=useRef<HTMLDialogElement>(null),title=useId(),[details,setDetails]=useState(false);
 useEffect(()=>{const element=dialog.current;element?.showModal();return()=>element?.close();},[]);
 return <dialog ref={dialog} className="aegis-workflow-dialog" aria-labelledby={title} onCancel={onClose} onClick={event=>{if(event.target===event.currentTarget)onClose();}}>
  <div className="aegis-workflow-dialog-inner"><header><div><span className="aegis-guide-eyebrow">END-TO-END WORKFLOW</span><h2 id={title}>From documents to grounded answers</h2></div><button type="button" className="btn icon" aria-label="Close expanded workflow" onClick={onClose}><X size={18}/></button></header>
   <WorkflowMap selected={selected} onSelect={stage=>{onSelect(stage);setDetails(true);}}/>
   <p className="aegis-flow-caption">Original documents and saved results feed the same scoped knowledge. Structured extraction and review can be used when needed.</p>
   {details&&<StageDetail selected={selected} onNavigate={onNavigate}/>}
  </div>
 </dialog>;
}
export function WorkflowOverview({isAdmin,onNavigate}:{isAdmin:boolean;onNavigate:(destination:Destination)=>void}){
 const [selected,setSelected]=useState(0),[expanded,setExpanded]=useState(false),[showDetails,setShowDetails]=useState(false);
 const expandButton=useRef<HTMLButtonElement>(null),restoreFocus=useRef(false),detailsId=useId();
 useEffect(()=>{if(!expanded&&restoreFocus.current){restoreFocus.current=false;expandButton.current?.focus();}},[expanded]);
 const close=()=>{restoreFocus.current=true;setExpanded(false);};
 const go=(destination:Destination)=>{setExpanded(false);onNavigate(destination);};
 return <section className="aegis-workflow-overview" aria-label="How Aegis works">
  <header className="aegis-overview-heading"><div><span className="aegis-guide-eyebrow">ONE CONNECTED DOCUMENT WORKFLOW</span><h2>How Aegis works</h2><p>Follow your documents from ingestion to searchable knowledge, structured results and cited answers.</p></div><span className="aegis-overview-identity"><AgentLogo size={35}/><span>Aegis<span>AI Data Platform</span></span></span></header>
  <section className="aegis-workflow-panel" aria-label="Aegis document workflow"><header><div><h3>Documents in. Knowledge and answers out.</h3><p>Follow the arrows end to end. Select a stage for its details.</p></div><button type="button" className="btn aegis-guide-expand" aria-label="Expand workflow" ref={expandButton} onClick={()=>setExpanded(true)}><Maximize2 size={15} aria-hidden="true"/><span>Expand workflow</span></button></header>
   <WorkflowMap selected={selected} onSelect={stage=>{setSelected(stage);setShowDetails(true);}}/>
   <p className="aegis-flow-caption"><ArrowRight size={15} aria-hidden="true"/><span>Original documents and saved results feed the same scoped knowledge. Extraction and review are available when structured results are needed.</span></p>
   <div className="aegis-flow-shared"><span><ShieldCheck size={16} aria-hidden="true"/><strong>Across the entire flow</strong></span><span>Dataset access & scope</span><span>Processing confirmation & consent</span><span>Saved model connections</span></div>
   <div className="aegis-flow-feature-links" aria-label="Open workflow tools">{features.map(({title,icon:Icon,destination})=><button type="button" className="aegis-flow-feature-link" key={title} onClick={()=>go(destination)}><Icon size={15} aria-hidden="true"/>{title}<ArrowRight size={12} aria-hidden="true"/></button>)}</div>
   <div className="aegis-flow-detail-toggle"><button type="button" className="btn aegis-feature-toggle" aria-expanded={showDetails} aria-controls={detailsId} onClick={()=>setShowDetails(!showDetails)}>{showDetails?'Hide stage details':'Explore stage details'}<ChevronDown size={15} className={showDetails?'is-open':''} aria-hidden="true"/></button><span>Select a numbered stage above to explore that part of the flow.</span></div>
   <div id={detailsId} hidden={!showDetails}>{showDetails&&<StageDetail selected={selected} onNavigate={go}/>}</div>
   {isAdmin&&<details className="aegis-admin-features"><summary><LockKeyhole size={14} aria-hidden="true"/>Configure this workflow<span>Models, connections & access</span><ChevronDown size={15} aria-hidden="true"/></summary><div className="aegis-flow-feature-links">{adminFeatures.map(({title,icon:Icon,destination})=><button type="button" className="aegis-flow-feature-link" key={title} onClick={()=>go(destination)}><Icon size={16} aria-hidden="true"/>{title}<ArrowRight size={12} aria-hidden="true"/></button>)}</div></details>}
  </section>
  {expanded&&<ExpandedWorkflow selected={selected} onSelect={setSelected} onClose={close} onNavigate={go}/>}
 </section>;
}
