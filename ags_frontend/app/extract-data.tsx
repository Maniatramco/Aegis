"use client";
import {useEffect,useRef,useState} from 'react';
import {ChevronDown,ChevronLeft,ChevronRight,Download,Table2,Database,FileJson,FileSpreadsheet,FileText,FileSearch,Loader2} from 'lucide-react';
import './extract-data.css';
type Entity=Record<string,any>;
type Api=(path:string,method?:string,body?:unknown,signal?:AbortSignal,quiet?:boolean)=>Promise<any>;
type Column={key:string;label:string;kind:string};
type Results={columns:Column[];rows:Entity[];total:number;extraction_count:number};
function valueText(value:any){return value===undefined||value===null?'—':Array.isArray(value)&&value.length&&value.every(item=>typeof item==='string')?value.join(', '):typeof value==='object'?JSON.stringify(value):String(value);}
export function ExtractData({datasets,templates,selectedDataset,onDatasetChange,onReview,api,revision}:{datasets:Entity[];templates:Entity[];selectedDataset:string;onDatasetChange:(id:string)=>void;onReview:(id:string)=>void;api:Api;revision:Entity[]}){
 const [template,setTemplate]=useState(''),[page,setPage]=useState(0),[data,setData]=useState<Results|null>(null),[loading,setLoading]=useState(true),[error,setError]=useState(''),[exporting,setExporting]=useState('');
 const exportMenu=useRef<HTMLDetailsElement>(null);
 const promptOptions=templates.filter(t=>!selectedDataset||!t.dataset_id||t.dataset_id===selectedDataset);
 const selectedTemplate=promptOptions.some(t=>t.id===template)?template:promptOptions[0]?.id||'';
 const params=new URLSearchParams();if(selectedDataset)params.set('dataset_id',selectedDataset);if(selectedTemplate)params.set('template_id',selectedTemplate);
 const query=params.toString();
 useEffect(()=>{
  if(!selectedTemplate){setLoading(false);setError('');setData(null);return;}
  const controller=new AbortController();let active=true;
  setLoading(true);setError('');setData(null);
  api(`/extract-data?${query}&offset=${page*25}&limit=25`,'GET',undefined,controller.signal,true).then(result=>{
   if(!active)return;
   if(page>0&&page*25>=result.total){setPage(Math.max(0,Math.ceil(result.total/25)-1));return;}
   setData(result);
  }).catch(err=>{if(active)setError(err.message);}).finally(()=>{if(active)setLoading(false);});
  return()=>{active=false;controller.abort();};
 },[api,query,page,revision,selectedTemplate]);
 const download=async(format:string)=>{
  if(exporting||!selectedTemplate||!data?.total)return;setExporting(format);setError('');
  try{
   const response=await fetch(`/api/extract-data/export?${query}&format=${format}`,{credentials:'same-origin'});
   if(!response.ok){const payload=await response.json().catch(()=>null);throw new Error(payload?.detail||'Export failed. Please retry.');}
   const blob=await response.blob(),url=URL.createObjectURL(blob),link=document.createElement('a');
   link.href=url;link.download=`aegis-extract-data.${format}`;document.body.appendChild(link);link.click();link.remove();setTimeout(()=>URL.revokeObjectURL(url),1000);
  }catch(err){setError((err as Error).message);}finally{setExporting('');}
 };
 const columns=data?.columns.filter(c=>c.kind==='field')||[];
 return <section className="extract-data" aria-label="Extract results">
  <div className="extract-data-toolbar">
   <label><span><Database size={14} aria-hidden="true"/>Dataset</span><select aria-label="Extract dataset" value={selectedDataset} onChange={event=>{if(event.target.value===selectedDataset)return;setTemplate('');setPage(0);setData(null);onDatasetChange(event.target.value);}}><option value="">All datasets</option>{datasets.map(d=><option key={d.id} value={d.id}>{d.name}</option>)}</select></label>
   <label><span><FileJson size={14} aria-hidden="true"/>Prompt template</span><select aria-label="Extract prompt template" value={selectedTemplate} disabled={!promptOptions.length} onChange={event=>{if(event.target.value===selectedTemplate)return;setTemplate(event.target.value);setPage(0);setData(null);}}>{!promptOptions.length&&<option value="">No prompt templates available</option>}{promptOptions.map(t=><option key={t.id} value={t.id}>{t.name}</option>)}</select></label>
   <details ref={exportMenu} className="extract-data-export"><summary className="btn extract-export-icon" role="button" aria-label="Export Extract results" title={exporting?'Exporting results…':'Export results'} aria-disabled={loading||!data?.total||!!exporting} onClick={event=>{if(loading||!data?.total||exporting)event.preventDefault();}}>{exporting?<Loader2 size={18} className="animate-spin" aria-hidden="true"/>:<Download size={18} aria-hidden="true"/>}<ChevronDown size={12} aria-hidden="true"/></summary><div>{[['xlsx','Excel (.xlsx)'],['csv','CSV (.csv)'],['json','JSON (.json)']].map(([format,label])=>{const Icon=format==='xlsx'?FileSpreadsheet:format==='csv'?FileText:FileJson;return <button key={format} title={`Export ${label}`} onClick={()=>{if(exportMenu.current)exportMenu.current.open=false;void download(format);}} disabled={loading||!data?.total||!!exporting}><Icon size={16} aria-hidden="true"/>{label}</button>;})}<small>All rows matching these filters. Latest saved values.</small></div></details>
  </div>
  {loading&&<div className="extract-data-state" role="status"><Loader2 size={18} className="animate-spin" aria-hidden="true"/>Loading saved results…</div>}
  {!loading&&!selectedTemplate&&<div className="extract-data-empty"><FileJson size={26} aria-hidden="true"/><p>Add a prompt template to view its extracted results.</p></div>}
  {error&&<p className="review-error" role="alert">{error}</p>}
  {!loading&&data?.total===0&&<div className="extract-data-empty"><Table2 size={28}/><p>No completed results match these filters.</p><small>Run an extraction in Aegis Agent or Review to see its saved fields here.</small></div>}
  {!!data?.total&&<><div className="extract-data-table" tabIndex={0} role="region" aria-label="Extracted results table"><table><thead><tr><th scope="col">Document</th><th scope="col">Extraction</th>{columns.map(c=><th key={c.key} scope="col">{c.label}</th>)}<th scope="col">Review status</th><th scope="col">Actions</th></tr></thead><tbody>{data.rows.map(row=><tr key={`${row.extraction_id}:${row.record_number}`}><td><strong>{row.document}</strong><small>{row.dataset} · {row.prompt_template}</small></td><td>{row.extraction}<small>v{row.version} · Record {row.record_number}{row.extracted_at?` · ${new Date(row.extracted_at*1000).toLocaleString()}`:''}</small></td>{columns.map(c=><td key={c.key} className="extract-data-value">{valueText(row[c.key])}</td>)}<td><span className={`extraction-status ${row.review_status==='reviewed'?'reviewed':'pending-review'}`}>{row.review_status==='reviewed'?'Reviewed':'Pending review'}</span></td><td className="extract-data-actions"><button className="btn icon extract-review-icon" aria-label={`Review extraction ${row.extraction_id} record ${row.record_number}`} title={`Review ${row.extraction}`} onClick={()=>onReview(row.extraction_id)}><FileSearch size={18} aria-hidden="true"/></button></td></tr>)}</tbody></table></div>
  <footer className="extract-list-pagination"><span role="status">{page*25+1}–{Math.min((page+1)*25,data.total)} of {data.total} records</span><div><button className="btn icon" aria-label="Previous Extract page" title="Previous page" disabled={page===0||loading} onClick={()=>setPage(page-1)}><ChevronLeft size={16} aria-hidden="true"/></button><span>Page {page+1} of {Math.max(1,Math.ceil(data.total/25))}</span><button className="btn icon" aria-label="Next Extract page" title="Next page" disabled={(page+1)*25>=data.total||loading} onClick={()=>setPage(page+1)}><ChevronRight size={16} aria-hidden="true"/></button></div></footer></>}
 </section>;
}
