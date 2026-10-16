"use client";
import {BookOpen,History,ShieldCheck} from 'lucide-react';
import application from './application-version.json';
import './about-aegis.css';

export function AboutAegis(){
 return <section className="about-aegis" aria-label="About Aegis"><header className="about-aegis-heading"><div><span className="about-eyebrow">AEGIS DATA PLATFORM</span><h2>Your documents. Connected knowledge.</h2><p>Explore permitted knowledge, ask questions with evidence, and turn documents into reviewable results.</p></div><span className="about-current-version" aria-label={`Current application version v${application.version}`}>v{application.version}</span></header><div className="about-aegis-principles"><span><BookOpen size={17}/>Documents and saved results</span><span><ShieldCheck size={17}/>Dataset access protected</span><span><History size={17}/>Version history</span></div><section className="about-release-history" aria-labelledby="about-release-title"><h2 id="about-release-title">What's included in each version</h2>{application.releases.map((release,index)=><article key={release.version} className="about-release"><header><div><h3>v{release.version}</h3>{index===0&&<span className="about-latest">Current version</span>}</div><time dateTime={release.date}>{new Date(release.date+'T00:00:00Z').toLocaleDateString('en-GB',{day:'numeric',month:'long',year:'numeric',timeZone:'UTC'})}</time></header><h4>{release.title}</h4><ul>{release.changes.map(change=><li key={change}>{change}</li>)}</ul></article>)}</section></section>;
}
