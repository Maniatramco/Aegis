"use client";
import { useEffect, useRef, useState } from "react";
import { ArrowLeft, ArrowRight, Check, CheckCircle2, ChevronRight, Database, FileSearch, FileText, Layers, MessageSquare, Plus, Search, Settings2, Shield, X } from "lucide-react";
import "./dataset-focus.css";
import {DirectoryRows} from "./dataset-directory";

type Entity = Record<string, any>;
type Api = (path: string, method?: string, body?: unknown) => Promise<any>;
export const eligibleModels = (dataset: Entity | undefined, capability: string): Entity[] =>
  (dataset?.active === false ? [] : dataset?.models || []).filter((m: Entity) => m.enabled !== false && m.mapping_enabled !== false && m.capabilities?.includes(capability));
export const modelLabel = (model: Entity | undefined) => model?.name || model?.provider_model || "Model not selected";
export const recordedModel = (record: Entity | null | undefined) => {
  const snapshot = record?.model_selection || record?.model_snapshot || record?.model_config;
  return snapshot?.name || snapshot?.model_name || snapshot?.provider_model || record?.model_name || record?.provider_model || "";
};

export function ModelPicker({ dataset, capability, value, onChange, onConfigure, disabled = false }: {
  dataset?: Entity; capability: "chat" | "extraction"; value: string; onChange: (id: string) => void; onConfigure: () => void; disabled?: boolean;
}) {
  const models = eligibleModels(dataset, capability);
  const label = capability === "chat" ? "Chat model" : "Extraction model";
  const [localModels,setLocalModels]=useState<Entity | null>(null);
  const selected=models.find(m=>m.id===value) || (models.length===1 ? models[0] : undefined);
  const local=selected?.provider==="ollama";
  useEffect(()=>{let active=true;if(local)fetch("/api/local-models",{credentials:"include"}).then(r=>r.ok?r.json():null).then(data=>{if(active)setLocalModels(data);}).catch(()=>{if(active)setLocalModels({available:false,models:[]});});return()=>{active=false;};},[local,value]);
  const installed=localModels?.models?.some((m:Entity)=>m.name===selected?.provider_model || m.name===selected?.provider_model+":latest");

  const defaultId = dataset?.[capability === "chat" ? "default_chat_model_id" : "default_extraction_model_id"];
  return <div className="model-picker">
    <label className="control-label">{label}</label>
    {!dataset ? <div className="model-readonly muted"><Layers size={15} />Choose a dataset first</div> : dataset.active === false ? <div className="model-unavailable"><strong>This dataset is inactive</strong><p>Activate it in its dataset settings before starting new work.</p><button type="button" className="text-button" onClick={onConfigure}>Open dataset settings <ArrowRight size={13} /></button></div> : models.length === 0 ?
      <div className="model-unavailable"><strong>No eligible {capability} models</strong><p>Map an enabled model with {capability} capability to this dataset.</p><button type="button" className="text-button" onClick={onConfigure}>Configure dataset models <ArrowRight size={13} /></button></div> : models.length === 1 ?
      <div className="model-readonly" aria-label={label}><Layers size={16} /><span>{modelLabel(models[0])}<small>{models[0].provider_model} · Only eligible model</small></span><CheckCircle2 size={15} /></div> :
      <select aria-label={label} value={value} onChange={e => onChange(e.target.value)} disabled={disabled}><option value="" disabled>Select a mapped model</option>{models.map(m => <option key={m.id} value={m.id}>{modelLabel(m)}{m.id === defaultId ? " · Dataset default" : ""}</option>)}</select>}
    {local && <p className="muted small" role="status">Local · Ollama · {localModels === null ? "Checking installation…" : !localModels.available ? "Ollama unavailable" : installed ? "Installed · No paid API" : "Model not installed"}<br />Embedding: {dataset?.models?.find((m:Entity)=>m.id===dataset?.embedding_model_id)?.provider_model || "Not mapped"}. Changing the chat model keeps this dataset’s embedding index.</p>}
  </div>;
}

export function DatasetWorkspace({ datasets, models, documents, selectedId, onSelect, onCreated, api, run, busy, reload, notify, onConnections, onUse, uploadPanel, documentsPanel, modelsFocus }: {
  datasets: Entity[]; models: Entity[]; documents: Entity[]; selectedId: string; onSelect: (id: string) => void; onCreated: (dataset: Entity) => void; api: Api; run: (fn: () => Promise<void>) => Promise<void>; busy: boolean; reload: () => void; notify: (text: string) => void; onConnections: () => void; onUse: (view: "Ask Aegis" | "Extract") => void; uploadPanel: React.ReactNode; documentsPanel: React.ReactNode; modelsFocus: boolean;
}) {
  const [creating, setCreating] = useState(false);
  const [showList, setShowList] = useState(!selectedId);
  const [showUpload, setShowUpload] = useState(false);
  const [search, setSearch] = useState("");
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [tab, setTab] = useState<"documents" | "models" | "settings">("documents");
  const newlyCreated = useRef("");
  const dataset = datasets.find(d => d.id === selectedId);
  const datasetDocs = documents.filter(d => (d.dataset_id || d.kb_id) === selectedId);
  const ready = datasetDocs.filter(d => d.status === "ready" && !d.requires_reindex).length;
  const mapped = dataset?.models?.filter((m: Entity) => m.mapping_enabled !== false && m.enabled !== false) || [];
  const chat = eligibleModels(dataset, "chat");
  const extraction = eligibleModels(dataset, "extraction");
  const embedding = mapped.find((m: Entity) => m.id === dataset?.embedding_model_id);
  const visibleDatasets = datasets.filter(d => `${d.name} ${d.description || ""}`.toLowerCase().includes(search.toLowerCase()));
  useEffect(() => {
    setTab(modelsFocus && dataset?.active === false ? "settings" : modelsFocus || newlyCreated.current === selectedId ? "models" : "documents");
    setShowUpload(false);
    if (selectedId) setShowList(false);
    newlyCreated.current = "";
  }, [selectedId, modelsFocus]);
  const startCreating = () => { setCreating(true); setName(""); setDescription(""); };
  const openDataset = (id: string) => { onSelect(id); setShowList(false); setCreating(false); setTab("documents"); setShowUpload(false); };
  return <div className="dataset-focus">
    <div className="dataset-intro dataset-navigation">
      {!creating && dataset && !showList ? <button className="text-button" onClick={() => { setShowList(true); setShowUpload(false); }}><ArrowLeft size={15} />All datasets</button> : <div><h2>{creating ? "New dataset" : "Your datasets"}</h2><p>{creating ? "Give your documents a name and a place." : `${datasets.length} dataset${datasets.length === 1 ? "" : "s"} · Choose one to view its documents`}</p></div>}
      {!creating && <button className={`btn ${showList || !dataset ? "primary" : ""}`} onClick={startCreating}><Plus size={15} />New dataset</button>}
    </div>
    {creating ? <section className="panel onboarding-panel">
      <div className="panel-head"><div><h2>Name your dataset</h2><p className="muted small">You can choose its models after creating it.</p></div><button className="btn icon" aria-label="Cancel dataset onboarding" onClick={() => setCreating(false)}><X size={16} /></button></div>
      <form onSubmit={e => { e.preventDefault(); run(async () => { const d = await api("/datasets", "POST", { name: name.trim(), description: description.trim() }); newlyCreated.current = d.id; onCreated(d); setCreating(false); setShowList(false); setTab("models"); notify("Dataset created. Map its models before adding documents."); reload(); }); }}>
        <div className="field"><label htmlFor="new-dataset-name">Dataset name</label><input id="new-dataset-name" aria-label="Dataset name" placeholder="e.g. Finance operations" value={name} onChange={e => setName(e.target.value)} required maxLength={160} autoFocus /></div>
        <div className="field"><label htmlFor="new-dataset-description">Dataset description <span className="muted">(optional)</span></label><input id="new-dataset-description" aria-label="Dataset description" placeholder="What will you keep here?" value={description} onChange={e => setDescription(e.target.value)} maxLength={2000} /></div>
        <div className="row dataset-create-actions"><button type="button" className="btn" onClick={() => setCreating(false)}>Cancel</button><button className="btn primary" disabled={busy || !name.trim()}>Create dataset <ArrowRight size={14} /></button></div>
      </form>
    </section> : showList || !dataset ? <>
      {datasets.length > 0 && <DirectoryRows datasets={datasets} documents={documents} onChat={id=>{onSelect(id);onUse("Ask Aegis");}}/>}
      <div className="dataset-grid" hidden={datasets.length>0}>
        {visibleDatasets.map(d => {
          const all = documents.filter(doc => (doc.dataset_id || doc.kb_id) === d.id);
          const usable = all.filter(doc => doc.status === "ready" && !doc.requires_reindex).length;
          const mappedModels: Entity[] = d.models?.filter((m: Entity) => m.mapping_enabled !== false && m.enabled !== false) || [];
          const taskConfigured = mappedModels.some(m => m.id === d.embedding_model_id) && mappedModels.some(m => m.capabilities?.includes("chat") || m.capabilities?.includes("extraction"));
          const state = d.active === false ? "Inactive" : usable > 0 && taskConfigured ? "Ready to use" : !taskConfigured ? "Models needed" : "Add documents";
          return <button key={d.id} className="dataset-card" onClick={() => openDataset(d.id)} aria-label={`Open dataset ${d.name}`}>
            <div className="row between"><span className="dataset-icon"><Database size={19} /></span><span className={`pill ${d.active === false ? "inactive" : usable > 0 && taskConfigured ? "green" : "amber"}`}>{state}</span></div>
            <h3>{d.name}</h3><p>{d.description || "No description"}</p>
            <div className="dataset-card-count"><strong>{all.length}</strong> documents <span>·</span>{usable} ready</div>
            <span className="dataset-card-link">Open dataset<ChevronRight size={14} /></span>
          </button>;
        })}
        {!datasets.length && <div className="panel dataset-empty"><Database size={30} /><h3>Your first dataset starts here</h3><p>Create a dataset, choose its models, and add documents.</p><button className="btn primary" onClick={startCreating}>New dataset <ArrowRight size={14} /></button></div>}
        {!!datasets.length && !visibleDatasets.length && <div className="panel dataset-empty"><Search size={28} /><h3>No matching datasets</h3><p>Try another name or description.</p><button className="btn" onClick={() => setSearch("")}>Clear search</button></div>}
      </div>
    </> : <>
      <section className="panel dataset-detail">
        <div className="panel-head dataset-detail-heading"><div><div className="row wrap"><h2>{dataset.name}</h2><span className={`pill ${dataset.active === false ? "inactive" : "green"}`}>{dataset.active === false ? "Inactive" : "Active"}</span></div>{dataset.description && <p className="muted small">{dataset.description}</p>}<p className="dataset-document-summary">{datasetDocs.length} document{datasetDocs.length === 1 ? "" : "s"} · {ready} ready</p></div><div className="row wrap dataset-use-actions"><button className="btn" onClick={() => onUse("Ask Aegis")} disabled={!chat.length || !ready}><MessageSquare size={14} />Ask this dataset</button><button className="btn" onClick={() => onUse("Extract")} disabled={!extraction.length || !ready}><FileSearch size={14} />Extract from dataset</button></div></div>
        <div className="tabs dataset-tabs" aria-label="Dataset sections">
          <button className={`btn ${tab === "documents" ? "primary" : ""}`} aria-pressed={tab === "documents"} onClick={() => setTab("documents")}><FileText size={14} />Documents</button>
          <button className={`btn ${tab === "models" ? "primary" : ""}`} aria-pressed={tab === "models"} onClick={() => setTab("models")}><Layers size={14} />Map models</button>
          <button className={`btn ${tab === "settings" ? "primary" : ""}`} aria-pressed={tab === "settings"} onClick={() => setTab("settings")}><Settings2 size={14} />Settings</button>
        </div>
        <div hidden={tab !== "documents"}>
          {dataset.active === false ? <div className="notice"><Settings2 size={16} /><div>This dataset is inactive. You can review its documents or <button className="text-button" onClick={() => setTab("settings")}>open settings to activate it</button>.</div></div> : !embedding && <div className="notice warn"><Layers size={16} /><div>Choose an embedding model before adding documents. <button className="text-button" onClick={() => setTab("models")}>Choose models <ArrowRight size={12} /></button></div></div>}
          <div className="dataset-documents-toolbar"><span className="muted small">Originals and their processing status</span><button className={`btn ${showUpload ? "" : "primary"}`} aria-expanded={showUpload} aria-controls="dataset-add-documents" disabled={dataset.active === false || !embedding} onClick={() => setShowUpload(!showUpload)}>{showUpload ? <X size={14} /> : <Plus size={14} />}{showUpload ? "Cancel upload" : "Add documents"}</button></div>
          <div id="dataset-add-documents" className="dataset-upload-panel" hidden={!showUpload}>{uploadPanel}</div>
        </div>
        <div hidden={tab !== "models"}>
          <p><button className="btn" disabled={busy} onClick={()=>run(async()=>{await api(`/datasets/${dataset.id}/local-models`,"POST",{});notify("Installed local models mapped. Existing embedding index selection preserved.");reload();})}>Use installed local models</button></p>
          {dataset.migration_required && <div className="notice warn"><Settings2 size={16} /><div><strong>This dataset needs model mappings.</strong><p>Import your current deployment settings, then review the models below.</p><button className="btn" disabled={busy} onClick={() => run(async () => { await api(`/datasets/${dataset.id}/migrate-settings`, "POST", {}); notify("Current settings imported. Review the dataset’s model mappings."); reload(); })}>Import current settings</button></div></div>}
          <DatasetMappings key={dataset.id} dataset={dataset} models={models} api={api} run={run} busy={busy} reload={reload} notify={notify} onConnections={onConnections} />
        </div>
        <div hidden={tab !== "settings"}>
          <div className="dataset-status-setting"><div><strong>Dataset status: {dataset.active !== false ? "Active" : "Inactive"}</strong><p className="muted small">Inactive datasets remain available to review. New processing, questions, and extractions are paused; work already queued may finish.</p></div><button className="btn" disabled={busy} onClick={() => run(async () => { const active = dataset.active === false; await api(`/datasets/${dataset.id}/status`, "PATCH", { active }); notify(`Dataset ${active ? "activated" : "deactivated"}.`); reload(); })}>{dataset.active !== false ? "Deactivate dataset" : "Activate dataset"}</button></div>
          <div className="dataset-storage"><Shield size={17} /><div><strong>Document storage</strong><p>Original files use your deployment’s durable storage. Model mappings control answering, extraction, and indexing. Connection credentials stay encrypted on the server.</p></div></div>
        </div>
      </section>
      {tab === "documents" && documentsPanel}
    </>}
  </div>;
}

function DatasetMappings({ dataset, models, api, run, busy, reload, notify, onConnections }: { dataset: Entity; models: Entity[]; api: Api; run: (fn: () => Promise<void>) => Promise<void>; busy: boolean; reload: () => void; notify: (text: string) => void; onConnections: () => void }) {
  type MappingDraft = { mappings: Entity[]; chatDefault: string; extractDefault: string; embedding: string };
  const savedDraft = (source: Entity): MappingDraft => ({
    mappings: (source.mappings || (source.models || []).map((m: Entity) => ({ model_id: m.id, enabled: m.mapping_enabled !== false }))).map((m: Entity) => ({ ...m })),
    chatDefault: source.default_chat_model_id || "",
    extractDefault: source.default_extraction_model_id || "",
    embedding: source.embedding_model_id || "",
  });
  const [draft, setDraft] = useState<MappingDraft>(() => savedDraft(dataset));
  const { mappings, chatDefault, extractDefault, embedding } = draft;
  const [ackReindex, setAckReindex] = useState(false);
  const [modelSearch, setModelSearch] = useState("");
  const [remoteChanged, setRemoteChanged] = useState(false);
  const dirty = useRef(false);
  const savedRevision = useRef({ id: dataset.id, version: dataset.version });
  const loadSavedDraft = () => {
    setDraft(savedDraft(dataset));
    savedRevision.current = { id: dataset.id, version: dataset.version };
    dirty.current = false;
    setRemoteChanged(false);
    setAckReindex(false);
  };
  useEffect(() => {
    // A workspace refresh returns new objects, even when nothing was saved.
    // Only a new persisted revision may reconcile the editor's local draft.
    if (savedRevision.current.id === dataset.id && savedRevision.current.version === dataset.version) return;
    if (dirty.current && savedRevision.current.id === dataset.id) {
      setRemoteChanged(true);
      return;
    }
    loadSavedDraft();
  }, [dataset.id, dataset.version]);
  const mapped = (id: string) => mappings.some(m => m.model_id === id && m.enabled !== false);
  const candidates = (capability: string) => models.filter(m => mapped(m.id) && m.enabled !== false && m.capabilities?.includes(capability));
  const changeDefault = (key: "chatDefault" | "extractDefault" | "embedding", value: string) => {
    dirty.current = true;
    setDraft(current => ({ ...current, [key]: value }));
    if (key === "embedding") setAckReindex(false);
  };
  const toggle = (id: string) => {
    dirty.current = true;
    setDraft(current => {
      const removing = current.mappings.some(m => m.model_id === id && m.enabled !== false);
      const remaining = current.mappings.filter(m => m.model_id !== id);
      return {
        mappings: removing ? remaining : [...remaining, { model_id: id, enabled: true }],
        chatDefault: removing && current.chatDefault === id ? "" : current.chatDefault,
        extractDefault: removing && current.extractDefault === id ? "" : current.extractDefault,
        embedding: removing && current.embedding === id ? "" : current.embedding,
      };
    });
    setAckReindex(false);
  };
  const selectedEmbedding = models.find(m => m.id === embedding);
  const pinnedEmbedding = dataset.embedding_selection;
  const embeddingChanged = !!dataset.embedding_model_id && (embedding !== dataset.embedding_model_id || !!pinnedEmbedding && !!selectedEmbedding && (pinnedEmbedding.model_version !== selectedEmbedding.version || pinnedEmbedding.connection_profile_version !== selectedEmbedding.connection_profile_version));
  const visibleModels = models.filter(m => `${modelLabel(m)} ${m.provider_model || ""} ${(m.capabilities || []).join(" ")}`.toLowerCase().includes(modelSearch.toLowerCase()));
  return <div className="dataset-mappings">
    {remoteChanged && <div className="notice warn"><Settings2 size={16} /><div><strong>Saved mappings changed while you were editing.</strong><p>Your unsaved selections are preserved. Load the latest saved mappings before making further changes.</p><button className="btn" onClick={loadSavedDraft}>Discard draft and load saved mappings</button></div></div>}
    <div className="panel-head"><div><h3>Models approved for this dataset</h3><p className="muted small">Choose the models this dataset can use, then set its defaults.</p></div><button className="btn" onClick={onConnections}><Plus size={14} />Manage model catalog</button></div>
    {models.length > 6 && <label className="dataset-search mapping-search"><Search size={16} /><input aria-label="Search catalog models" placeholder="Search models or capabilities" value={modelSearch} onChange={e => setModelSearch(e.target.value)} /></label>}
    {models.length ? <><div className="mapping-grid">{visibleModels.map(m => <label key={m.id} className={`mapping-card ${mapped(m.id) ? "selected" : ""} ${m.enabled === false ? "disabled" : ""}`}><input type="checkbox" aria-label={`Mapped model ${m.name}`} checked={mapped(m.id)} onChange={() => toggle(m.id)} disabled={busy || m.enabled === false && !mapped(m.id)} /><div><div className="row wrap"><strong>{modelLabel(m)}</strong>{m.enabled === false && <span className="pill amber">Disabled</span>}</div><small>{m.provider_model} · {m.provider || m.connection_profile_name || "Saved connection"}</small><div className="model-chips">{(m.capabilities || []).map((c: string) => <span className="model-chip" key={c}>{c}</span>)}</div></div></label>)}</div>{!visibleModels.length && <p className="muted small">No models match your search.</p>}</> : <div className="notice"><Layers size={17} /><div>Create a saved connection profile and add a model to the shared catalog first. <button className="text-button" onClick={onConnections}>Open Connections <ArrowRight size={12} /></button></div></div>}
    <div className="grid3 mapping-defaults">
      {[{label:"Default chat model", cap:"chat", value:chatDefault, key:"chatDefault" as const}, {label:"Default extraction model", cap:"extraction", value:extractDefault, key:"extractDefault" as const}, {label:"Embedding model", cap:"embedding", value:embedding, key:"embedding" as const}].map(f => <div className="field" key={f.cap}><label>{f.label}</label><select aria-label={f.label} value={f.value} onChange={e => changeDefault(f.key, e.target.value)} disabled={busy}><option value="">{f.cap === "embedding" ? "Select an embedding model" : "No default · choose at runtime"}</option>{candidates(f.cap).map(m => <option key={m.id} value={m.id}>{modelLabel(m)}</option>)}</select><small>{f.cap === "embedding" ? "A fixed embedding model keeps this dataset’s index consistent." : "One eligible model is automatic. Multiple models offer a dropdown."}</small></div>)}
    </div>
    {embeddingChanged && <div className="notice warn"><Settings2 size={17} /><div><strong>Changing the embedding model requires reindexing.</strong><p>Existing documents must be reindexed before they can be used again. Changing chat or extraction models does not change this embedding space.</p><label className="check"><input type="checkbox" checked={ackReindex} onChange={e => setAckReindex(e.target.checked)} />I understand existing documents will need reindexing.</label></div></div>}
    <div className="row between wrap"><span className="muted small">Index generation {dataset.index_generation || 1} · Credentials inherited from saved connections</span><button className="btn primary" disabled={busy || remoteChanged || embeddingChanged && !ackReindex} onClick={() => run(async () => { const saved = await api(`/datasets/${dataset.id}/models`, "PUT", { mappings, default_chat_model_id: chatDefault || null, default_extraction_model_id: extractDefault || null, embedding_model_id: embedding || null }); setDraft(savedDraft(saved)); dirty.current = false; notify(embeddingChanged ? "Mappings saved. Reindex existing documents with the new embedding model." : "Dataset model mappings saved."); reload(); })}><Check size={14} />Save model mappings</button></div>
  </div>;
}

export function ModelCatalog({ models, profiles, api, run, busy, reload, notify }: { models: Entity[]; profiles: Entity[]; api: Api; run: (fn: () => Promise<void>) => Promise<void>; busy: boolean; reload: () => void; notify: (text: string) => void }) {
  const blank = { name: "", connection_profile_id: "", provider_model: "", capabilities: ["chat", "extraction"], enabled: true };
  const [form, setForm] = useState<Entity>(blank);
  const [editing, setEditing] = useState("");
  const [showForm, setShowForm] = useState(false);
  const [catalogSearch, setCatalogSearch] = useState("");
  const visibleModels = models.filter(m => `${modelLabel(m)} ${m.provider_model || ""}`.toLowerCase().includes(catalogSearch.toLowerCase()));
  return <section className="panel model-catalog-focus" id="model-catalog">
    {!showForm && <div className="panel-head"><div><h2>Model catalog</h2><p className="muted small">Shared models available to your datasets.</p></div><button className="btn primary" onClick={() => { setForm(blank); setEditing(""); setShowForm(true); }}><Plus size={14} />Add model</button></div>}
    {!showForm && models.length > 6 && <div className="field"><input aria-label="Search shared models" placeholder="Search shared models" value={catalogSearch} onChange={e => setCatalogSearch(e.target.value)} /></div>}
    {!showForm && !!models.length && !visibleModels.length && <p className="muted">No matching models.</p>}
    {!showForm && <div className="catalog-list">{visibleModels.map(m => <div key={m.id} className="catalog-row"><span className="file-icon"><Layers size={18} /></span><div className="catalog-name"><strong>{modelLabel(m)}</strong><small>{m.provider_model} · {profiles.find(p => p.id === m.connection_profile_id)?.name || "Saved connection"}</small></div><div className="model-chips">{(m.capabilities || []).map((c: string) => <span className="model-chip" key={c}>{c}</span>)}<span className={`pill ${m.enabled !== false ? "green" : "amber"}`}>{m.enabled !== false ? "Enabled" : "Disabled"}</span></div><button className="btn" onClick={() => { setForm({ name:m.name, connection_profile_id:m.connection_profile_id, provider_model:m.provider_model, capabilities:m.capabilities || [], enabled:m.enabled !== false }); setEditing(m.id); setShowForm(true); }}>Edit model</button></div>)}</div>}
    {!models.length && !showForm && <div className="empty"><Layers size={30} /><h3>Build your shared model catalog</h3><p>Save a connection in the Profiles section, then add chat, extraction, or embedding models.</p></div>}
    {showForm && <form className="catalog-form" onSubmit={e => { e.preventDefault(); run(async () => { await api(`/models${editing ? "/" + editing : ""}`, editing ? "PUT" : "POST", form); setShowForm(false); notify(editing ? "Catalog model updated. Review its dataset mappings." : "Model added to the catalog. Map it to a dataset to use it."); reload(); }); }}><div className="panel-head"><h3>{editing ? "Edit catalog model" : "Add a catalog model"}</h3><button type="button" className="btn icon" aria-label="Cancel model edit" onClick={() => setShowForm(false)}><X size={14} /></button></div><div className="grid3"><div className="field"><label>Model name</label><input autoFocus aria-label="Model name" value={form.name} onChange={e => setForm({...form, name:e.target.value})} placeholder="e.g. Research assistant" required /></div><div className="field"><label>Connection profile</label><select aria-label="Model connection profile" value={form.connection_profile_id} onChange={e => setForm({...form, connection_profile_id:e.target.value})} required><option value="">Select saved connection</option>{profiles.map(p => <option key={p.id} value={p.id}>{p.name} · v{p.version}</option>)}</select></div><div className="field"><label>Provider model ID</label><input aria-label="Provider model ID" value={form.provider_model} onChange={e => setForm({...form, provider_model:e.target.value})} placeholder="e.g. gpt-4.1-mini" required /></div></div><div className="row between wrap"><div className="row wrap">{["chat", "extraction", "embedding"].map(cap => <label className="check" key={cap}><input type="checkbox" aria-label={`Model capability ${cap}`} checked={form.capabilities.includes(cap)} onChange={e => setForm({...form, capabilities:e.target.checked ? cap === "embedding" ? ["embedding"] : [...form.capabilities.filter((c: string) => c !== "embedding"), cap] : form.capabilities.filter((c: string) => c !== cap)})} />{cap}</label>)}<label className="check"><input type="checkbox" aria-label="Model enabled" checked={form.enabled} onChange={e => setForm({...form, enabled:e.target.checked})} />Enabled</label></div><button className="btn primary" disabled={busy || !profiles.length || !form.capabilities.length}><Check size={14} />Save catalog model</button></div>{!profiles.length && <p className="small muted" style={{marginTop:14}}>Save a connection in the Profiles section before adding this model.</p>}<p className="small muted" style={{marginTop:14, marginBottom:0}}>Embedding models are separate from chat and extraction models. Select supported capabilities; adding embedding clears generation capabilities. Credentials are never copied into the dataset or returned to the browser.</p></form>}
  </section>;
}
