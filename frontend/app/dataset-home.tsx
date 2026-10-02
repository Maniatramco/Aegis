"use client";
import { useEffect, useState } from "react";
import { AlertCircle, ArrowRight, Database, Loader2, Plus } from "lucide-react";

type Entity = Record<string, any>;
export function DatasetHome({ api, refresh, onBrowse, onLoaded }: {
  api: (path: string) => Promise<any>; refresh: number; onBrowse: () => void; onLoaded: (datasets: Entity[]) => void;
}) {
  const [datasets, setDatasets] = useState<Entity[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [retry, setRetry] = useState(0);
  useEffect(() => {
    let current = true;
    setLoading(true);
    setError("");
    api("/datasets").then(data => {
      if (current) {
        const next = Array.isArray(data) ? data : data.datasets || [];
        setDatasets(next);
        onLoaded(next);
      }
    }).catch(e => {
      if (current) setError(e instanceof Error ? e.message : "Datasets could not be loaded.");
    }).finally(() => { if (current) setLoading(false); });
    return () => { current = false; };
  }, [api, refresh, retry, onLoaded]);
  return <section aria-label="Registered datasets" className="home-datasets">
    <div className="panel-head"><h2>Registered datasets</h2><button className="btn primary" onClick={onBrowse}><Plus size={15} />Onboard dataset</button></div>
    {loading ? <div className="panel home-state" role="status"><Loader2 size={22} className="animate-spin" /><p>Loading datasets…</p></div> : error ?
      <div className="panel home-state" role="alert"><AlertCircle size={24} /><h3>Couldn’t load datasets</h3><p>{error}</p><button className="btn" onClick={() => setRetry(n => n + 1)}>Try again</button></div> : !datasets.length ?
      <div className="panel home-state"><Database size={30} /><h3>No registered datasets yet</h3><p>Onboard your first dataset to organize its documents and models.</p><button className="btn" onClick={onBrowse}>Get started <ArrowRight size={14} /></button></div> :
      <div className="dataset-grid home-grid">{datasets.map(d => <a key={d.id} href={`#dataset/${encodeURIComponent(d.id)}`} className="dataset-card home-card" aria-label={`Open dataset ${d.name}`}>
        <div className="row between"><span className="dataset-icon"><Database size={20} aria-hidden="true" /></span><span className={`pill ${d.active !== false ? "green" : "inactive"}`}><span className="dot" aria-hidden="true" />{d.active !== false ? "Active" : "Inactive"}</span></div>
        <h3>{d.name}</h3><p>{d.description || "No description added."}</p>
        <span className="dataset-card-link">View dataset <ArrowRight size={15} aria-hidden="true" /></span>
      </a>)}</div>}
  </section>;
}
