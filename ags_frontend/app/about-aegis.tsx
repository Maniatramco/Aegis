"use client";
import {Activity,Award,BookOpen,CheckCircle2,CloudUpload,Cpu,FileText,Folder,History,MessageSquareText,ScanText,ShieldCheck,User,UserCheck,Users} from 'lucide-react';
import application from './application-version.json';
import './about-aegis.css';

const day=(date:string)=>new Date(date+'T00:00:00Z').toLocaleDateString('en-GB',{day:'numeric',month:'long',year:'numeric',timeZone:'UTC'});
const MODELS=[['Embedding','indexes knowledge'],['Chat','answers questions'],['Extraction','fills prompt fields'],['OCR','reads scans and images']];
const DATASETS=['Contracts','Invoices','Policies'];
const PROMPTS=[
 {icon:ScanText,title:'Extract key terms',text:'“Find party, fee and due date, with pages”'},
 {icon:ScanText,title:'Extract renewals',text:'“Find renewal period and notice terms”'},
 {icon:MessageSquareText,title:'Ask a question',text:'“Which contracts renew this quarter?”'},
];
const FIELDS=[['Party','Northwind Supplies Ltd'],['Total fee','$48,500'],['Due date','30 Jun 2027'],['Renewal','12 months']];

/** A worked example of one dataset: predefined prompts read an unstructured document, reviewers approve the fields, and the approved record becomes the golden copy. */
function WorkflowDiagram(){
 return <figure className="about-diagram golden" aria-labelledby="about-flow-title">
  <div className="golden-layout">
   <aside className="golden-workspace" aria-label="Workspace">
    <span className="golden-label">Workspace</span>
    <div className="golden-card-dark"><span className="golden-chip-icon"><User size={15} aria-hidden="true"/></span><span><strong>My workspace</strong><small>Datasets assigned to you, with their prompts</small></span></div>
    <span className="golden-label golden-sublabel">Datasets</span>
    <ul className="golden-datasets">{DATASETS.map((name,index)=><li key={name} data-active={index===0||undefined}><Folder size={15} aria-hidden="true"/><span><strong>{name}</strong><small>Sources, prompts, knowledge base</small></span></li>)}</ul>
    <div className="golden-card-dark"><span className="golden-chip-icon"><Users size={15} aria-hidden="true"/></span><span><strong>Shared with your team</strong><small>Administrators assign each dataset to the people who need it</small></span></div>
    <p className="golden-sources"><CloudUpload size={14} aria-hidden="true"/>Sources: upload, Amazon S3, Azure Blob, OCI Object Storage, SharePoint or Google Drive</p>
   </aside>
   <div className="golden-example">
    <span className="golden-label golden-label-light">Worked example · Contracts dataset</span>
    <p className="diagram-scroll-hint">Scroll sideways to follow the flow.</p>
    <div className="golden-canvas" role="region" aria-label="Worked example diagram" tabIndex={0}>
     <div className="golden-grid">
      <section className="golden-node golden-prompts" aria-label="Predefined prompts"><span className="golden-label golden-label-light">Predefined prompts</span>
       <ul>{PROMPTS.map(({icon:Icon,title,text},index)=><li key={title} data-active={index===0||undefined}><span className="golden-chip-icon light"><Icon size={14} aria-hidden="true"/></span><span><strong>{title}</strong><small>{text}</small></span></li>)}</ul>
       <span className="golden-down" data-label="asks" aria-hidden="true"/></section>
      <article className="golden-node golden-document" aria-label="Unstructured document"><span className="golden-chip-icon light"><FileText size={15} aria-hidden="true"/></span><strong>Supplier agreement.pdf</strong><small>Unstructured · page 2</small>
       <p>This Supply Agreement is made between <mark>Northwind Supplies Ltd</mark> (“Supplier”) and the Customer. The Customer shall pay a total fee of <mark>$48,500</mark> under Schedule B, due no later than <mark>30 June 2027</mark>. The Agreement renews automatically for <mark>12 months</mark> unless either party gives 60 days’ notice.</p>
       <span className="golden-down" data-label="indexed" aria-hidden="true"/></article>
      <section className="golden-node golden-fields" aria-label="Structured fields"><span className="golden-label golden-label-light">Structured fields</span>
       <table><thead><tr><th>Field</th><th>Value</th><th>Source</th></tr></thead><tbody>{FIELDS.map(([field,value])=><tr key={field}><td>{field}</td><td><strong>{value}</strong></td><td><span className="golden-page">p. 2</span></td></tr>)}</tbody></table>
       <div className="golden-approved"><span className="golden-chip-icon light"><UserCheck size={14} aria-hidden="true"/></span><span><strong>Reviewer approved</strong><small>Ready for the golden copy</small></span></div>
       <span className="golden-down" data-label="approved" aria-hidden="true"/></section>
      <div className="golden-node golden-result golden-answers"><span className="golden-chip-icon light"><MessageSquareText size={15} aria-hidden="true"/></span><span><strong>Answers with evidence</strong><small>Hybrid search, reranking and checked citations to the source page</small></span></div>
      <div className="golden-node golden-result golden-kb"><span className="golden-chip-icon light"><BookOpen size={15} aria-hidden="true"/></span><span><strong>Knowledge base</strong><small>Document content indexed with the dataset’s embedding model</small></span></div>
      <div className="golden-node golden-result golden-copy"><span className="golden-chip-icon gold"><Award size={15} aria-hidden="true"/></span><span><strong>Golden copy</strong><small>Approved fields become the trusted record, exported to Excel, CSV or JSON</small></span></div>
     </div>
    </div>
   </div>
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
  <section className="about-flow" aria-labelledby="about-flow-title"><span className="about-eyebrow">Inside an Aegis workspace</span><h2 id="about-flow-title">Predefined prompts turn unstructured documents into trusted data</h2><p className="about-flow-intro">Each dataset keeps its own sources, prompts and knowledge base. Reviewed fields become the golden copy.</p><WorkflowDiagram/></section>
  <section className="about-release-history" aria-labelledby="about-release-title"><h2 id="about-release-title">What's included in each version</h2>
   <ol className="about-timeline">
    <li className="about-release" data-current="true"><header><div><h3>v{current.version}</h3><span className="about-latest">Current version</span></div><time dateTime={current.date}>{day(current.date)}</time></header><h4>{current.title}</h4><ul>{current.changes.map(change=><li key={change}><CheckCircle2 size={14} aria-hidden="true"/>{change}</li>)}</ul></li>
    {earlier.map(release=><li key={release.version} className="about-release"><details><summary><span className="about-release-name"><strong>v{release.version}</strong>{release.title}</span><time dateTime={release.date}>{day(release.date)}</time></summary><ul>{release.changes.map(change=><li key={change}><CheckCircle2 size={14} aria-hidden="true"/>{change}</li>)}</ul></details></li>)}
   </ol>
  </section>
 </section>;
}
