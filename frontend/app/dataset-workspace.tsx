"use client";
import { useEffect, useRef, useState } from "react";
import { ArrowLeft, ArrowRight, Check, CheckCircle2, ChevronRight, Database, FileSearch, FileText, Layers, MessageSquare, Plus, Settings2, Shield, UploadCloud, X } from "lucide-react";

type Entity = Record<string, any>;
type Api = (path: string, method?: string, body?: unknown) => Promise<any>;
export const eligibleModels = (dataset: Entity | undefined, capability: string): Entity[] =>
  (dataset?.models || []).filter((m: Entity) => m.enabled !== false && m.mapping_enabled !== false && m.capabilities?.includes(capability));
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
  const defaultId = dataset?.[capability === "chat" ? "default_chat_model_id" : "default_extraction_model_id"];
  return <div className="model-picker">
    <label className="control-label">{label}</label>
    {!dataset ? <div className="model-readonly muted"><Layers size={15} />Choose a dataset first</div> : models.length === 0 ?
      <div className="model-unavailable"><strong>No eligible {capability} models</strong><p>Map an enabled model with {capability} capability to this dataset.</p><button type="button" className="text-button" onClick={onConfigure}>Configure dataset models <ArrowRight size={13} /></button></div> : models.length === 1 ?
      <div className="model-readonly" aria-label={label}><Layers size={16} /><span>{modelLabel(models[0])}<small>{models[0].provider_model} · Only eligible model</small></span><CheckCircle2 size={15} /></div> :
      <select aria-label={label} value={value} onChange={e => onChange(e.target.value)} disabled={disabled}><option value="" disabled>Select a mapped model</option>{models.map(m => <option key={m.id} value={m.id}>{modelLabel(m)}{m.id === defaultId ? " · Dataset default" : ""}</option>)}</select>}
  </div>;
}

export function DatasetWorkspace({ datasets, models, documents, selectedId, onSelect, onCreated, api, run, busy, reload, notify, onConnections, onUse, uploadPanel, documentsPanel, modelsFocus }: {
  datasets: Entity[]; models: Entity[]; documents: Entity[]; selectedId: string; onSelect: (id: string) => void; onCreated: (dataset: Entity) => void; api: Api; run: (fn: () => Promise<void>) => Promise<void>; busy: boolean; reload: () => void; notify: (text: string) => void; onConnections: () => void; onUse: (view: "Ask Aegis" | "Extract") => void; uploadPanel: React.ReactNode; documentsPanel: React.ReactNode; modelsFocus: boolean;
}) {
  const [creating, setCreating] = useState(false);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [tab, setTab] = useState<"documents" | "models">("documents");
  const dataset = datasets.find(d => d.id === selectedId);
  const datasetDocs = documents.filter(d => (d.dataset_id || d.kb_id) === selectedId);
  const ready = datasetDocs.filter(d => d.status === "ready" && !d.requires_reindex).length;
  const mapped = dataset?.models?.filter((m: Entity) => m.mapping_enabled !== false && m.enabled !== false) || [];
  const chat = eligibleModels(dataset, "chat");
  const extraction = eligibleModels(dataset, "extraction");
  const embedding = mapped.find((m: Entity) => m.id === dataset?.embedding_model_id);
  useEffect(() => { setTab(modelsFocus || !dataset?.embedding_model_id ? "models" : "documents"); }, [selectedId, modelsFocus]);
  return <>
    <div className="dataset-intro">
      <div><span className="eyebrow">START WITH YOUR DATA</span><h2>A defined source. The right models. Trusted results.</h2><p>Onboard a dataset, map its models, then bring its documents into Ask Aegis and Extract.</p></div>
      <button className="btn primary" onClick={() => { setCreating(true); setName(""); setDescription(""); }}><Plus size={15} />Onboard dataset</button>
    </div>
    {creating && <section className="panel onboarding-panel">
      <div className="panel-head"><div><div className="eyebrow">STEP 1 OF 3</div><h2>Name your dataset</h2><p className="muted small">Give a team, topic, or project its own document scope and model configuration.</p></div><button className="btn icon" aria-label="Cancel dataset onboarding" onClick={() => setCreating(false)}><X size={16} /></button></div>
      <form onSubmit={e => { e.preventDefault(); run(async () => { const d = await api("/datasets", "POST", { name: name.trim(), description: description.trim() }); onCreated(d); setCreating(false); setTab("models"); notify("Dataset created. Map its models before adding documents."); reload(); }); }}>
        <div className="grid2"><div className="field"><label>Dataset name</label><input aria-label="Dataset name" placeholder="e.g. Finance operations" value={name} onChange={e => setName(e.target.value)} required maxLength={160} autoFocus /></div><div className="field"><label>Dataset description</label><input aria-label="Dataset description" placeholder="What is in this dataset, and who is it for?" value={description} onChange={e => setDescription(e.target.value)} maxLength={2000} /></div></div>
        <div className="row between wrap"><span className="muted small"><Shield size={13} style={{ display: "inline", verticalAlign: "middle" }} /> Originals use your deployment’s configured durable storage.</span><button className="btn primary" disabled={busy || !name.trim()}>Create dataset <ArrowRight size={14} /></button></div>
      </form>
    </section>}
    <div className="dataset-grid">
      {datasets.map(d => {
        const all = documents.filter(doc => (doc.dataset_id || doc.kb_id) === d.id);
        const usable = all.filter(doc => doc.status === "ready" && !doc.requires_reindex).length;
        const mappedModels: Entity[] = d.models?.filter((m: Entity) => m.mapping_enabled !== false && m.enabled !== false) || [];
        const taskConfigured = mappedModels.some(m => m.id === d.embedding_model_id) && mappedModels.some(m => m.capabilities?.includes("chat") || m.capabilities?.includes("extraction"));
        const usableForTask = usable > 0 && taskConfigured;
        return <button key={d.id} className={`dataset-card ${selectedId === d.id ? "selected" : ""}`} onClick={() => { onSelect(d.id); setCreating(false); }} aria-pressed={selectedId === d.id} aria-label={`Open dataset ${d.name}`}>
          <div className="row between"><span className="dataset-icon"><Database size={20} /></span><span className={`pill ${usableForTask ? "green" : "amber"}`}>{usableForTask ? "Ready to use" : d.migration_required ? "Setup required" : !taskConfigured ? "Models needed" : "Onboarding"}</span></div>
          <h3>{d.name}</h3><p>{d.description || "A dedicated document scope with its own model mappings."}</p>
          <div className="dataset-card-count"><strong>{all.length}</strong> documents <span>·</span><strong>{usable}</strong> ready</div>
          <div className="model-chips">{mappedModels.length ? mappedModels.slice(0, 3).map(m => <span className="model-chip" key={m.id}>{modelLabel(m)}</span>) : <span className="muted small">No models mapped yet</span>}{mappedModels.length > 3 && <span className="model-chip">+{mappedModels.length - 3}</span>}</div>
          <span className="dataset-card-link">{selectedId === d.id ? "Viewing dataset" : "Open dataset"}<ChevronRight size={14} /></span>
        </button>;
      })}
      {!datasets.length && !creating && <div className="panel dataset-empty"><Database size={34} /><h3>Your first dataset starts here</h3><p>Name your dataset, connect it to models, and add documents.</p><button className="btn primary" onClick={() => setCreating(true)}>Onboard dataset <ArrowRight size={14} /></button></div>}
    </div>
    {dataset ? <>
      <section className="panel dataset-detail">
        <div className="panel-head"><div><div className="eyebrow">DATASET WORKSPACE</div><h2>{dataset.name}</h2><p className="muted small">{dataset.description || "Manage documents and model routing for this dataset."}</p></div><div className="row wrap"><button className="btn" onClick={() => onUse("Ask Aegis")} disabled={!chat.length || !ready}><MessageSquare size={14} />Ask this dataset</button><button className="btn primary" onClick={() => onUse("Extract")} disabled={!extraction.length || !ready}><FileSearch size={14} />Extract from dataset</button></div></div>
        <div className="dataset-steps">
          {[{ n: 1, title: "Dataset created", detail: "Name & document scope", complete: true, action: () => {} }, { n: 2, title: "Map models", detail: `${mapped.length} enabled · ${embedding ? "Embedding set" : "Embedding needed"}`, complete: !!embedding && (!!chat.length || !!extraction.length), action: () => setTab("models") }, { n: 3, title: "Add documents", detail: `${ready} ready of ${datasetDocs.length} stored`, complete: ready > 0, action: () => setTab("documents") }].map(step => <button key={step.n} className={`dataset-step ${step.complete ? "complete" : ""}`} aria-label={`Step ${step.n}: ${step.title}`} onClick={step.action}><span>{step.complete ? <Check size={14} /> : step.n}</span><div><strong>{step.title}</strong><small>{step.detail}</small></div></button>)}
        </div>
        <div className="tabs dataset-tabs"><button className={`btn ${tab === "documents" ? "primary" : ""}`} onClick={() => setTab("documents")}><FileText size={14} />Documents</button><button className={`btn ${tab === "models" ? "primary" : ""}`} onClick={() => setTab("models")}><Layers size={14} />Map models</button></div>
        {dataset.migration_required && <div className="notice warn"><Settings2 size={16} /><div><strong>This dataset needs explicit model mappings.</strong><p>Reuse the current deployment’s model and embedding settings to create a saved connection profile and model catalog entries, then review its mappings.</p><button className="btn" disabled={busy} onClick={() => run(async () => { await api(`/datasets/${dataset.id}/migrate-settings`, "POST", {}); notify("Current settings imported. Review the dataset’s model mappings."); reload(); setTab("models"); })}>Import current settings</button></div></div>}
        {tab === "models" ? <DatasetMappings key={dataset.id} dataset={dataset} models={models} api={api} run={run} busy={busy} reload={reload} notify={notify} onConnections={onConnections} /> : <>
          <div className="dataset-storage"><Shield size={17} /><div><strong>Storage-first, dataset-scoped</strong><p>Original files use deployment storage. Dataset model mappings control answering, extraction, and the embedding space. Connection credentials stay encrypted on the server.</p></div></div>
          {!embedding && <div className="notice warn"><Settings2 size={16} /><div>Map an embedding model before uploading documents. <button className="text-button" onClick={() => setTab("models")}>Map models <ArrowRight size={12} /></button></div></div>}
          {uploadPanel}
        </>}
      </section>
      {tab === "documents" && documentsPanel}
    </> : datasets.length > 0 && <div className="dataset-select-hint"><ArrowLeft size={17} /><span>Open a dataset to manage its documents and model mappings.</span></div>}
  </>;
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
  return <div>
    {remoteChanged && <div className="notice warn"><Settings2 size={16} /><div><strong>Saved mappings changed while you were editing.</strong><p>Your unsaved selections are preserved. Load the latest saved mappings before making further changes.</p><button className="btn" onClick={loadSavedDraft}>Discard draft and load saved mappings</button></div></div>}
    <div className="panel-head"><div><h3>Models approved for this dataset</h3><p className="muted small">Map shared catalog models, then choose defaults for each task. Only enabled, capable models appear in Ask and Extract.</p></div><button className="btn" onClick={onConnections}><Plus size={14} />Manage model catalog</button></div>
    {models.length ? <div className="mapping-grid">{models.map(m => <label key={m.id} className={`mapping-card ${mapped(m.id) ? "selected" : ""} ${m.enabled === false ? "disabled" : ""}`}><input type="checkbox" aria-label={`Mapped model ${m.name}`} checked={mapped(m.id)} onChange={() => toggle(m.id)} disabled={busy || m.enabled === false && !mapped(m.id)} /><div><div className="row wrap"><strong>{modelLabel(m)}</strong>{m.enabled === false && <span className="pill amber">Disabled</span>}</div><small>{m.provider_model} · {m.provider || m.connection_profile_name || "Saved connection"}</small><div className="model-chips">{(m.capabilities || []).map((c: string) => <span className="model-chip" key={c}>{c}</span>)}</div></div></label>)}</div> : <div className="notice"><Layers size={17} /><div>Create a saved connection profile and add a model to the shared catalog first. <button className="text-button" onClick={onConnections}>Open Connections <ArrowRight size={12} /></button></div></div>}
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
  return <section className="panel" id="model-catalog">
    <div className="panel-head"><div><div className="eyebrow">SHARED MODEL CATALOG</div><h2>Connect once. Map to each dataset.</h2><p className="muted small">Models use versioned connection profiles. Datasets choose which models are allowed and which are defaults.</p></div><button className="btn primary" onClick={() => { setForm(blank); setEditing(""); setShowForm(true); }}><Plus size={14} />Add model</button></div>
    <div className="catalog-list">{models.map(m => <div key={m.id} className="catalog-row"><span className="file-icon"><Layers size={18} /></span><div className="catalog-name"><strong>{modelLabel(m)}</strong><small>{m.provider_model} · {profiles.find(p => p.id === m.connection_profile_id)?.name || "Saved connection"}</small></div><div className="model-chips">{(m.capabilities || []).map((c: string) => <span className="model-chip" key={c}>{c}</span>)}<span className={`pill ${m.enabled !== false ? "green" : "amber"}`}>{m.enabled !== false ? "Enabled" : "Disabled"}</span></div><button className="btn" onClick={() => { setForm({ name:m.name, connection_profile_id:m.connection_profile_id, provider_model:m.provider_model, capabilities:m.capabilities || [], enabled:m.enabled !== false }); setEditing(m.id); setShowForm(true); }}>Edit model</button></div>)}</div>
    {!models.length && !showForm && <div className="empty"><Layers size={30} /><h3>Build your shared model catalog</h3><p>Save a connection profile below, then add chat, extraction, or embedding models.</p></div>}
    {showForm && <form className="catalog-form" onSubmit={e => { e.preventDefault(); run(async () => { await api(`/models${editing ? "/" + editing : ""}`, editing ? "PUT" : "POST", form); setShowForm(false); notify(editing ? "Catalog model updated. Review its dataset mappings." : "Model added to the catalog. Map it to a dataset to use it."); reload(); }); }}><div className="panel-head"><h3>{editing ? "Edit catalog model" : "Add a catalog model"}</h3><button type="button" className="btn icon" aria-label="Cancel model edit" onClick={() => setShowForm(false)}><X size={14} /></button></div><div className="grid3"><div className="field"><label>Model name</label><input aria-label="Model name" value={form.name} onChange={e => setForm({...form, name:e.target.value})} placeholder="e.g. Research assistant" required /></div><div className="field"><label>Connection profile</label><select aria-label="Model connection profile" value={form.connection_profile_id} onChange={e => setForm({...form, connection_profile_id:e.target.value})} required><option value="">Select saved connection</option>{profiles.map(p => <option key={p.id} value={p.id}>{p.name} · v{p.version}</option>)}</select></div><div className="field"><label>Provider model ID</label><input aria-label="Provider model ID" value={form.provider_model} onChange={e => setForm({...form, provider_model:e.target.value})} placeholder="e.g. gpt-4.1-mini" required /></div></div><div className="row between wrap"><div className="row wrap">{["chat", "extraction", "embedding"].map(cap => <label className="check" key={cap}><input type="checkbox" aria-label={`Model capability ${cap}`} checked={form.capabilities.includes(cap)} onChange={e => setForm({...form, capabilities:e.target.checked ? cap === "embedding" ? ["embedding"] : [...form.capabilities.filter((c: string) => c !== "embedding"), cap] : form.capabilities.filter((c: string) => c !== cap)})} />{cap}</label>)}<label className="check"><input type="checkbox" aria-label="Model enabled" checked={form.enabled} onChange={e => setForm({...form, enabled:e.target.checked})} />Enabled</label></div><button className="btn primary" disabled={busy || !profiles.length || !form.capabilities.length}><Check size={14} />Save catalog model</button></div>{!profiles.length && <p className="small muted" style={{marginTop:14}}>Save a connection profile below before adding this model.</p>}<p className="small muted" style={{marginTop:14, marginBottom:0}}>Embedding models are separate from chat and extraction models. Select supported capabilities; adding embedding clears generation capabilities. Credentials are never copied into the dataset or returned to the browser.</p></form>}
  </section>;
}
