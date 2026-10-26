"use client";
import {BookOpen,CheckCircle2,ClipboardCheck,CloudUpload,History,Layers,MessageSquareText,ShieldCheck} from 'lucide-react';
import application from './application-version.json';
import './about-aegis.css';

const day=(date:string)=>new Date(date+'T00:00:00Z').toLocaleDateString('en-GB',{day:'numeric',month:'long',year:'numeric',timeZone:'UTC'});
const FLOW=[
 {icon:CloudUpload,title:'Bring documents in',text:'Upload files or connect cloud storage. Originals are kept unchanged.'},
 {icon:Layers,title:'Index knowledge',text:'Text and OCR are embedded with each dataset’s mapped model.'},
 {icon:MessageSquareText,title:'Ask with evidence',text:'Hybrid search and reranking find evidence; answers cite it and are checked before you see them.'},
 {icon:ClipboardCheck,title:'Extract and review',text:'Prompt templates turn documents into fields you review, correct and export.'},
];

export function AboutAegis(){
 const [current,...earlier]=application.releases;
 return <section className="about-aegis" aria-label="About Aegis">
  <div className="about-overview">
   <header className="about-aegis-heading"><span className="about-eyebrow">AEGIS DATA PLATFORM</span><h2>Your documents. Connected knowledge.</h2><p>Explore permitted knowledge, ask questions with evidence, and turn documents into reviewable results.</p>
    <div className="about-aegis-principles"><span><BookOpen size={16}/>Documents and saved results</span><span><ShieldCheck size={16}/>Dataset access protected</span><span><History size={16}/>Version history</span></div></header>
   <aside className="about-version-card" aria-label="Current release"><span className="about-version-label">Current version</span><strong className="about-current-version" aria-label={`Current application version v${application.version}`}>v{application.version}</strong><span>{current.title}</span><time dateTime={current.date}>Released {day(current.date)}</time><small>{application.releases.length} releases recorded</small></aside>
  </div>
  <section className="about-flow" aria-labelledby="about-flow-title"><h2 id="about-flow-title">How Aegis works</h2><ol>{FLOW.map(({icon:Icon,title,text},index)=><li key={title}><span className="about-flow-step"><Icon size={18} aria-hidden="true"/><small>{index+1}</small></span><h3>{title}</h3><p>{text}</p></li>)}</ol></section>
  <section className="about-release-history" aria-labelledby="about-release-title"><h2 id="about-release-title">What's included in each version</h2>
   <ol className="about-timeline">
    <li className="about-release" data-current="true"><header><div><h3>v{current.version}</h3><span className="about-latest">Current version</span></div><time dateTime={current.date}>{day(current.date)}</time></header><h4>{current.title}</h4><ul>{current.changes.map(change=><li key={change}><CheckCircle2 size={14} aria-hidden="true"/>{change}</li>)}</ul></li>
    {earlier.map(release=><li key={release.version} className="about-release"><details><summary><span className="about-release-name"><strong>v{release.version}</strong>{release.title}</span><time dateTime={release.date}>{day(release.date)}</time></summary><ul>{release.changes.map(change=><li key={change}><CheckCircle2 size={14} aria-hidden="true"/>{change}</li>)}</ul></details></li>)}
   </ol>
  </section>
 </section>;
}
