"use client";
import {Activity,BookOpen,CheckCircle2,ClipboardCheck,CloudUpload,Cpu,Database,History,Layers,MessageSquareText,ShieldCheck} from 'lucide-react';
import application from './application-version.json';
import './about-aegis.css';

const day=(date:string)=>new Date(date+'T00:00:00Z').toLocaleDateString('en-GB',{day:'numeric',month:'long',year:'numeric',timeZone:'UTC'});
const INTAKE=[
 {icon:CloudUpload,title:'Sources',text:'Bring documents in',items:['Upload files','Amazon S3','Azure Blob','OCI Object Storage','SharePoint','Google Drive']},
 {icon:Database,title:'Dataset',text:'Organise and protect',items:['Access by assignment','Originals kept unchanged','Cloud files read-only']},
 {icon:Layers,title:'Unified knowledge',text:'Index for search',items:['OCR for scans and images','Embed with the dataset model','Vector + keyword index']},
];
const LANES=[
 {key:'ask',icon:MessageSquareText,title:'Ask with evidence',where:'Aegis Agent and Dashboard chat',model:'Chat model',steps:['Check access and scope','Hybrid search','Rerank evidence','Generate answer','Validate citations'],result:'Answer with citations'},
 {key:'extract',icon:ClipboardCheck,title:'Extract and review',where:'Extract, Review and Prompt',model:'Extraction model',steps:['Choose a prompt template','Extract fields','Review and correct','Export Excel, CSV or JSON'],result:'Reviewed results'},
];
const MODELS=[['Embedding','indexes knowledge'],['Chat','answers questions'],['Extraction','fills prompt fields'],['OCR','reads scans and images']];

function WorkflowDiagram(){
 return <figure className="about-diagram" aria-labelledby="about-flow-title">
  <p className="diagram-scroll-hint">Scroll sideways to follow the flow.</p>
  <div className="diagram-canvas" role="region" aria-label="Workflow diagram" tabIndex={0}>
  <ol className="diagram-intake" aria-label="Bring knowledge in">{INTAKE.map(({icon:Icon,title,text,items},index)=><li key={title} className="diagram-node">
   <span className="diagram-node-head"><span className="diagram-icon"><Icon size={18} aria-hidden="true"/></span><span><small>Step {index+1} · {text}</small><strong>{title}</strong></span></span>
   <ul>{items.map(item=><li key={item}>{item}</li>)}</ul>
  </li>)}</ol>
  <div className="diagram-split" aria-hidden="true"><span/></div>
  <div className="diagram-lanes">{LANES.map(({key,icon:Icon,title,where,model,steps,result},index)=><section key={key} className="diagram-lane" data-lane={key} aria-label={title}>
   <header><span className="diagram-icon"><Icon size={18} aria-hidden="true"/></span><span><small>Step {INTAKE.length+1+index} · {where}</small><strong>{title}</strong></span><em>{model}</em></header>
   <ol>{steps.map(step=><li key={step}>{step}</li>)}<li className="diagram-result"><CheckCircle2 size={14} aria-hidden="true"/>{result}</li></ol>
  </section>)}</div>
  </div>
  <div className="diagram-models"><span className="diagram-models-title"><Cpu size={15} aria-hidden="true"/>Models mapped per dataset</span>{MODELS.map(([name,role])=><span key={name}><strong>{name}</strong>{role}</span>)}</div>
  <figcaption><span><ShieldCheck size={14} aria-hidden="true"/>Access and dataset scope are enforced before search and checked again after the answer.</span><span><Activity size={14} aria-hidden="true"/>Jobs & activity tracks every indexing and extraction run.</span><span><MessageSquareText size={14} aria-hidden="true"/>Greetings and general questions in Dashboard chat are answered by the chat model and labelled as using no knowledge lookup.</span></figcaption>
 </figure>;
}

export function AboutAegis(){
 const [current,...earlier]=application.releases;
 return <section className="about-aegis" aria-label="About Aegis">
  <div className="about-overview">
   <header className="about-aegis-heading"><span className="about-eyebrow">AEGIS DATA PLATFORM</span><h2>Your documents. Connected knowledge.</h2><p>Explore permitted knowledge, ask questions with evidence, and turn documents into reviewable results.</p>
    <div className="about-aegis-principles"><span><BookOpen size={16}/>Documents and saved results</span><span><ShieldCheck size={16}/>Dataset access protected</span><span><History size={16}/>Version history</span></div></header>
   <aside className="about-version-card" aria-label="Current release"><span className="about-version-label">Current version</span><strong className="about-current-version" aria-label={`Current application version v${application.version}`}>v{application.version}</strong><span>{current.title}</span><time dateTime={current.date}>Released {day(current.date)}</time><small>{application.releases.length} releases recorded</small></aside>
  </div>
  <section className="about-flow" aria-labelledby="about-flow-title"><h2 id="about-flow-title">How Aegis works</h2><p className="about-flow-intro">From source documents to cited answers and reviewed results, inside the datasets you are allowed to see.</p><WorkflowDiagram/></section>
  <section className="about-release-history" aria-labelledby="about-release-title"><h2 id="about-release-title">What's included in each version</h2>
   <ol className="about-timeline">
    <li className="about-release" data-current="true"><header><div><h3>v{current.version}</h3><span className="about-latest">Current version</span></div><time dateTime={current.date}>{day(current.date)}</time></header><h4>{current.title}</h4><ul>{current.changes.map(change=><li key={change}><CheckCircle2 size={14} aria-hidden="true"/>{change}</li>)}</ul></li>
    {earlier.map(release=><li key={release.version} className="about-release"><details><summary><span className="about-release-name"><strong>v{release.version}</strong>{release.title}</span><time dateTime={release.date}>{day(release.date)}</time></summary><ul>{release.changes.map(change=><li key={change}><CheckCircle2 size={14} aria-hidden="true"/>{change}</li>)}</ul></details></li>)}
   </ol>
  </section>
 </section>;
}
