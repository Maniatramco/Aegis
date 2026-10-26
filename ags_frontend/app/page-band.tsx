"use client";
import './page-template.css';

type Intro={group:string;step?:string;title:string;text:string};
/** Purpose lines for workspace screens. Dashboard, Aegis Agent and Add knowledge have their own heroes. */
export const PAGE_INTROS:Record<string,Intro>={
 'Datasets':{group:'Onboard',step:'Step 1 of 4',title:'Datasets',text:'Create datasets, map their models and upload documents. Each dataset keeps its own access and knowledge.'},
 'Prompt templates':{group:'Onboard',step:'Step 2 of 4',title:'Prompts',text:'Save extraction templates that define which fields to pull from documents.'},
 'Extract Data':{group:'Onboard',step:'Step 3 of 4',title:'Extract',text:'Run a saved prompt over indexed documents and compare the extracted fields side by side.'},
 'Extract':{group:'Onboard',step:'Step 4 of 4',title:'Review',text:'Check extracted fields against the source before they are trusted in answers and exports.'},
 'Model Registration':{group:'Manage workspace',title:'Model registration',text:'Register chat, extraction, embedding and OCR models and test their connections.'},
 'Model Mapping':{group:'Manage workspace',title:'Model mapping',text:'Choose which models each dataset uses for embedding, chat, extraction and OCR.'},
 'Users & passwords':{group:'Manage workspace',title:'Users & passwords',text:'Manage people, roles and dataset access, and change your own password.'},
 'Jobs & activity':{group:'Manage workspace',title:'Jobs & activity',text:'Indexing, extraction and cleanup run in the background. Follow each stage and retry failures here.'},
 'Storage':{group:'Manage workspace',title:'Storage',text:'See where originals, databases and knowledge are kept, and configure file storage.'},
 'Files & processing':{group:'Manage workspace',title:'Files & processing',text:"Review every source file's storage, indexing, OCR and extraction status."},
 'About':{group:'Aegis',title:'About Aegis',text:'What Aegis does, how it keeps knowledge grounded, and what changed in each version.'},
};

/** Brand band at the top of a screen. The page h1 already names the screen, so the large title is visual only. */
export function PageBand({view}:{view:string}){
 const intro=PAGE_INTROS[view];
 if(!intro)return null;
 return <section className="page-band" aria-label={`${intro.title} overview`}>
  <div className="page-band-copy">
   <span className="page-band-eyebrow">{intro.group}{intro.step?` · ${intro.step}`:''}</span>
   <p className="page-band-title" aria-hidden="true">{intro.title}</p>
   <p className="page-band-text">{intro.text}</p>
  </div>
 </section>;
}
