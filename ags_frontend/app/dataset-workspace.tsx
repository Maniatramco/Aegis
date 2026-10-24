"use client";
import {ActionButton} from "./action-button";
import { useEffect, useRef, useState } from "react";
import { CheckCircle2, Database, Layers, Settings2, X } from "lucide-react";
import "./dataset-focus.css";
import "./model-configuration.css";
import {useDatasetLifecycle} from "./dataset-lifecycle";
import {DirectoryRows} from "./dataset-directory";
import {AgentOnboarding} from "./agent-onboarding";
import {selectMappingDefault,setMappingEnabled,type MappingDraft} from './dataset-mapping-draft';

type Entity = Record<string, any>;
type Api = (path: string, method?: string, body?: unknown) => Promise<any>;
export const eligibleModels = (dataset: Entity | undefined, capability: string): Entity[] =>
  (dataset?.active === false ? [] : dataset?.models || []).filter((m: Entity) => m.enabled !== false && m.mapping_enabled !== false && m.capabilities?.includes(capability));
export const modelLabel = (model: Entity | undefined) => model?.name || model?.provider_model || "Model not selected";
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
    {!dataset ? <div className="model-readonly muted"><Layers size={15} />Choose a dataset first</div> : dataset.active === false ? <div className="model-unavailable"><strong>This dataset is inactive</strong><p>Ask your workspace administrator to activate it before starting new work.</p></div> : models.length === 0 ?
      <div className="model-unavailable"><strong>No eligible {capability} models</strong><p>Map an enabled model with {capability} capability to this dataset.</p><ActionButton type="button" className="text-button" onClick={onConfigure} label="Configure dataset models" action="mapping"/></div> : models.length === 1 ?
      <div className="model-readonly" aria-label={label}><Layers size={16} /><span>{modelLabel(models[0])}<small>{models[0].provider_model} · Only eligible model</small></span><CheckCircle2 size={15} /></div> :
      <select aria-label={label} value={value} onChange={e => onChange(e.target.value)} disabled={disabled}><option value="" disabled>Select a mapped model</option>{models.map(m => <option key={m.id} value={m.id}>{modelLabel(m)}{m.id === defaultId ? " · Dataset default" : ""}</option>)}</select>}
    {local && <p className="muted small" role="status">Local · Ollama · {localModels === null ? "Checking installation…" : !localModels.available ? "Ollama unavailable" : installed ? "Installed · No paid API" : "Model not installed"}<br />Embedding: {dataset?.models?.find((m:Entity)=>m.id===dataset?.embedding_model_id)?.provider_model || "Not mapped"}. Changing the chat model keeps this dataset’s embedding index.</p>}
  </div>;
}

export function DatasetWorkspace({datasets,models,documents,onSelect,onCreated,api,reload,notify,onUse,canManage=true,directorySearch,onClearDirectorySearch,onDirectoryVisibilityChange,storageKey,defaults}: {
  datasets:Entity[];models:Entity[];documents:Entity[];onSelect:(id:string)=>void;onCreated:(dataset:Entity)=>void;api:Api;reload:()=>void;notify:(text:string)=>void;onUse:(view:"Aegis agent V2"|"Extract")=>void;canManage?:boolean;directorySearch:string;onClearDirectorySearch:()=>void;onDirectoryVisibilityChange:(visible:boolean)=>void;storageKey:string;defaults?:Entity;
}) {
  const lifecycle=useDatasetLifecycle(api,reload,canManage);
  const [creating,setCreating]=useState(false),[onboardingBusy,setOnboardingBusy]=useState(false);
  useEffect(()=>{onDirectoryVisibilityChange(!creating);return()=>onDirectoryVisibilityChange(false);},[creating,onDirectoryVisibilityChange]);
  const completed=(dataset:Entity)=>{
    sessionStorage.removeItem(storageKey);sessionStorage.removeItem(storageKey+'-request');
    onCreated(dataset);setCreating(false);notify('Dataset created with its model mappings.');reload();
  };
  return <div className="dataset-focus">
    {!creating&&lifecycle.controls}
    {!creating&&<div className="dataset-intro dataset-navigation"><span className="pill">{datasets.length} dataset{datasets.length===1?'':'s'}</span>{canManage&&<ActionButton className="btn primary" onClick={()=>setCreating(true)} label="New dataset" action="add"/>}</div>}
    {creating?<AgentOnboarding datasetOnly api={api} models={models} defaults={defaults} storageKey={storageKey} onBusy={setOnboardingBusy} onReady={()=>{}} onCompleted={completed} onUse={()=>{}} onClose={()=>{if(!onboardingBusy)setCreating(false);}}/>:<>
      {datasets.length>0&&<DirectoryRows onDelete={canManage?lifecycle.requestDelete:undefined} datasets={datasets} documents={documents} search={directorySearch} onClearSearch={onClearDirectorySearch} onChat={id=>{onSelect(id);onUse('Aegis agent V2');}}/>}
      {!datasets.length&&<div className="panel dataset-empty"><Database size={30}/><h3>{canManage?'Your first dataset starts here':'No datasets assigned'}</h3><p>{canManage?'Create a dataset and choose its models.':'Ask your administrator to assign a dataset to your account.'}</p>{canManage&&<ActionButton className="btn primary" onClick={()=>setCreating(true)} label="New dataset" action="add"/>}</div>}
    </>}
  </div>;
}

export function DatasetMappings({ dataset, models, api, run, busy, reload, notify, onConnections }: { dataset: Entity; models: Entity[]; api: Api; run: (fn: () => Promise<void>) => Promise<void>; busy: boolean; reload: () => void; notify: (text: string) => void; onConnections: () => void }) {
  const savedDraft = (source: Entity): MappingDraft => ({
    mappings: (source.mappings || (source.models || []).map((m: Entity) => ({ model_id: m.id, enabled: m.mapping_enabled !== false }))).map((m: Entity) => ({ ...m })),
    chatDefault: source.default_chat_model_id || "",
    extractDefault: source.default_extraction_model_id || "",
    embedding: source.embedding_model_id || "",
    ocr: source.ocr_model_id || "",
  });
  const [draft, setDraft] = useState<MappingDraft>(() => savedDraft(dataset));
  const { mappings, chatDefault, extractDefault, embedding, ocr = "" } = draft;
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
  const candidates = (capability: string) => models.filter(m => m.enabled !== false && m.capabilities?.includes(capability));
  const changeDefault = (key: "chatDefault" | "extractDefault" | "embedding" | "ocr", value: string) => {
    dirty.current = true;
    setDraft(current => selectMappingDefault(current,key,value));
    if (key === "embedding") setAckReindex(false);
  };
  const selectedEmbedding = models.find(m => m.id === embedding);
  const ocrCandidates = models.filter(m=>m.enabled!==false&&m.ocr_eligible===true);
  const selectedOcr = ocrCandidates.find(m=>m.id===ocr);
  const complete=candidates('chat').some(m=>m.id===chatDefault)&&candidates('extraction').some(m=>m.id===extractDefault)&&candidates('embedding').some(m=>m.id===embedding)&&(!ocr||!!selectedOcr);
  const ocrChanged = ocr !== (dataset.ocr_model_id || '');
  const pinnedEmbedding = dataset.embedding_selection;
  const embeddingChanged = !!dataset.embedding_model_id && (embedding !== dataset.embedding_model_id || !!pinnedEmbedding && !!selectedEmbedding && (pinnedEmbedding.model_version !== selectedEmbedding.version || pinnedEmbedding.connection_profile_version !== selectedEmbedding.connection_profile_version));
  return <div className="dataset-mappings">
    {remoteChanged && <div className="notice warn"><Settings2 size={16} /><div><strong>Saved mappings changed while you were editing.</strong><p>Your unsaved selections are preserved. Load the latest saved mappings before making further changes.</p><button className="btn" onClick={loadSavedDraft}>Discard draft and load saved mappings</button></div></div>}
    <div className="panel-head"><span className="pill">3 required categories · OCR configurable</span><ActionButton className="btn" onClick={onConnections} label="Register model" action="add"/></div>
    <div className="mapping-table" role="region" aria-label="Dataset model mappings table" tabIndex={0}>
      <table aria-label="Dataset model mappings"><colgroup><col className="mapping-category-column"/><col className="mapping-model-column"/><col/><col/><col/><col/></colgroup>
        <thead><tr><th scope="col">Category</th><th scope="col">Default model</th><th scope="col">Provider</th><th scope="col" className="mapping-tokens" title="Configured input limit for embeddings; total context limit for chat and extraction">Input / context</th><th scope="col" className="mapping-tokens" title="Configured maximum output tokens">Output</th><th scope="col">Status</th></tr></thead>
        <tbody>{[{label:"Embedding model", cap:"embedding", value:embedding, key:"embedding" as const}, {label:"Chat model", cap:"chat", value:chatDefault, key:"chatDefault" as const}, {label:"Extraction model", cap:"extraction", value:extractDefault, key:"extractDefault" as const}].map(f=>{
          const options=candidates(f.cap);const selected=options.find(m=>m.id===f.value);
          const purpose=f.cap==='embedding'?'Indexing and search':f.cap==='chat'?'Dataset questions':'Structured extraction';
          const provider=selected?.connection?.protocol||selected?.provider;
          const providerLabel:Record<string,string>={'ollama':'Ollama','openai-compatible':'OpenAI-compatible','azure-openai':'Azure OpenAI','anthropic':'Anthropic Claude','bedrock':'Amazon Bedrock','vertex':'Google Vertex AI','oci':'OCI','openai':'OpenAI','sentence_transformers':'Sentence Transformers'};
          return <tr key={f.cap}>
            <th scope="row"><label htmlFor={`mapping-${f.cap}`}>{f.cap==='embedding'?'Embedding':f.cap==='chat'?'Chat':'Extraction'}</label><small>{purpose}</small></th>
            <td><select id={`mapping-${f.cap}`} aria-label={f.label} value={f.value} onChange={e=>changeDefault(f.key,e.target.value)} disabled={busy} required title={selected?`${modelLabel(selected)} · ${selected.provider_model}`:`Choose ${f.label.toLowerCase()}`}><option value="">Select {f.cap==='extraction'?'an extraction':f.cap==='embedding'?'an embedding':'a chat'} model</option>{options.map(m=><option key={m.id} value={m.id}>{modelLabel(m)} · {m.provider_model}</option>)}</select>{!options.length&&<small className="field-error">Register an enabled {f.cap} model first.</small>}</td>
            <td>{providerLabel[provider]||provider||'—'}</td>
            <td className="mapping-tokens" title={f.cap==='embedding'?'Input tokens':'Context tokens'}>{selected?.context_limit?.toLocaleString()||'—'}</td>
            <td className="mapping-tokens" title={f.cap==='embedding'?'Not applicable to embeddings':'Maximum output tokens'}>{f.cap==='embedding'?'—':selected?.max_output_tokens?.toLocaleString()||'—'}</td>
            <td><span className={`pill ${selected?'green':'amber'}`} title={selected?'Model selected for this category; Save & Apply commits the mapping':'A model is required for this category'}>{selected?'Selected':'Required'}</span></td>
          </tr>;
        })}<tr>
          <th scope="row"><label htmlFor="mapping-ocr">OCR</label><small>Scans and document images</small></th>
          <td><select id="mapping-ocr" aria-label="OCR model" title={selectedOcr?`${modelLabel(selectedOcr)} · ${selectedOcr.provider_model}`:'Automatic · cloud extraction default'} value={ocr} onChange={e=>changeDefault('ocr',e.target.value)} disabled={busy}>
            <option value="">Automatic · cloud extraction default</option>
            {ocrCandidates.map(model=><option key={model.id} value={model.id}>{modelLabel(model)} · {model.provider_model}</option>)}
            {ocr&&!selectedOcr&&<option value={ocr} disabled>Choose a cloud OCR model</option>}
          </select></td>
          <td>{selectedOcr?(selectedOcr.connection?.endpoint?.includes('api.openai.com')?'OpenAI':'Google Gemini'):'Cloud'}</td>
          <td className="mapping-tokens">{selectedOcr?.context_limit?.toLocaleString()||'—'}</td>
          <td className="mapping-tokens">{selectedOcr?.max_output_tokens?.toLocaleString()||'—'}</td>
          <td><span className={`pill ${!ocr||selectedOcr?'green':'amber'}`}>{!ocr?'Automatic':selectedOcr?'Selected':'Unavailable'}</span></td>
        </tr></tbody>
      </table>
    </div>
    <p className="muted small">OCR reads text from scanned PDFs and images in Word documents using cloud models only. Choose a compatible OpenAI or Gemini extraction registration. Automatic uses the compatible cloud extraction default; it never falls back to local OCR.</p>
    {ocrChanged&&<p className="notice" role="status">The next indexing job will use this OCR choice. Reindex existing documents to read their images again; their embedding model stays the same.</p>}
    <div className="mapping-availability">
      {(['chat','extraction'] as const).map(capability=><fieldset key={capability} disabled={busy||remoteChanged}>
        <legend>Available {capability} models</legend>
        <p className="muted small">Enable models to offer them in this dataset's {capability==='chat'?'chat':'extraction'} selector. Keep one default above.</p>
        <div className="mapping-model-options">{candidates(capability).map(model=>{
          const isDefault=[chatDefault,extractDefault,embedding,ocr==='local'?'':ocr].includes(model.id);
          const enabled=mappings.some(item=>item.model_id===model.id&&item.enabled!==false);
          return <label className="check mapping-model-option" key={model.id}>
            <input type="checkbox" aria-label={`Enable ${modelLabel(model)} for ${capability}`} checked={enabled} disabled={isDefault}
              onChange={event=>{dirty.current=true;setDraft(current=>setMappingEnabled(current,model.id,event.target.checked));}}/>
            <span>{modelLabel(model)}<small>{model.provider_model}{[chatDefault,extractDefault,embedding].includes(model.id)?' · Dataset default':''}{ocr===model.id?' · OCR default':''}</small></span>
          </label>;
        })}</div>
      </fieldset>)}
    </div>
    {embeddingChanged && <div className="notice warn"><Settings2 size={17} /><div><strong>Changing the embedding model requires reindexing.</strong><p>Existing documents must be reindexed before they can be used again. Changing chat or extraction models does not change this embedding space.</p><label className="check"><input type="checkbox" checked={ackReindex} onChange={e => setAckReindex(e.target.checked)} />I understand existing documents will need reindexing.</label></div></div>}
    <div className="row between wrap mapping-actions"><span className="muted small">Index generation {dataset.index_generation || 1} · Connection credentials remain encrypted</span><ActionButton className="btn primary" disabled={busy || remoteChanged || !complete || embeddingChanged && !ackReindex} onClick={() => run(async () => { const saved = await api(`/datasets/${dataset.id}/models`, "PUT", { mappings, default_chat_model_id: chatDefault || null, default_extraction_model_id: extractDefault || null, embedding_model_id: embedding || null, ocr_model_id: ocr || null, expected_version: dataset.version, acknowledge_reindex: ackReindex }); setDraft(savedDraft(saved)); dirty.current = false; notify(embeddingChanged ? "Mappings saved. Reindex existing documents with the new embedding model." : "Mappings applied. The next operation will use these selections."); reload(); })} label="Save & Apply" action="save"/></div>
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
    {!showForm && <div className="panel-head"><div><h2>Model catalog</h2><p className="muted small">Shared models available to your datasets.</p></div><ActionButton className="btn primary" onClick={() => { setForm(blank); setEditing(""); setShowForm(true); }} label="Add model" action="add"/></div>}
    {!showForm && models.length > 6 && <div className="field"><input aria-label="Search shared models" placeholder="Search shared models" value={catalogSearch} onChange={e => setCatalogSearch(e.target.value)} /></div>}
    {!showForm && !!models.length && !visibleModels.length && <p className="muted">No matching models.</p>}
    {!showForm && <div className="catalog-list">{visibleModels.map(m => <div key={m.id} className="catalog-row"><span className="file-icon"><Layers size={18} /></span><div className="catalog-name"><strong>{modelLabel(m)}</strong><small>{m.provider_model} · {profiles.find(p => p.id === m.connection_profile_id)?.name || "Saved connection"}</small></div><div className="model-chips">{(m.capabilities || []).map((c: string) => <span className="model-chip" key={c}>{c}</span>)}<span className={`pill ${m.enabled !== false ? "green" : "amber"}`}>{m.enabled !== false ? "Enabled" : "Disabled"}</span></div><ActionButton className="btn" onClick={() => { setForm({ name:m.name, connection_profile_id:m.connection_profile_id, provider_model:m.provider_model, capabilities:m.capabilities || [], enabled:m.enabled !== false }); setEditing(m.id); setShowForm(true); }} label="Edit model" action="edit"/></div>)}</div>}
    {!models.length && !showForm && <div className="empty"><Layers size={30} /><h3>Build your shared model catalog</h3><p>Save a connection in the Profiles section, then add chat, extraction, or embedding models.</p></div>}
    {showForm && <form className="catalog-form" onSubmit={e => { e.preventDefault(); run(async () => { await api(`/models${editing ? "/" + editing : ""}`, editing ? "PUT" : "POST", form); setShowForm(false); notify(editing ? "Catalog model updated. Review its dataset mappings." : "Model added to the catalog. Map it to a dataset to use it."); reload(); }); }}><div className="panel-head"><h3>{editing ? "Edit catalog model" : "Add a catalog model"}</h3><button title="Cancel model edit" type="button" className="btn icon" aria-label="Cancel model edit" onClick={() => setShowForm(false)}><X size={14} /></button></div><div className="grid3"><div className="field"><label>Model name</label><input autoFocus aria-label="Model name" value={form.name} onChange={e => setForm({...form, name:e.target.value})} placeholder="e.g. Research assistant" required /></div><div className="field"><label>Connection profile</label><select aria-label="Model connection profile" value={form.connection_profile_id} onChange={e => setForm({...form, connection_profile_id:e.target.value})} required><option value="">Select saved connection</option>{profiles.map(p => <option key={p.id} value={p.id}>{p.name} · v{p.version}</option>)}</select></div><div className="field"><label>Provider model ID</label><input aria-label="Provider model ID" value={form.provider_model} onChange={e => setForm({...form, provider_model:e.target.value})} placeholder="e.g. gpt-4.1-mini" required /></div></div><div className="row between wrap"><div className="row wrap">{["chat", "extraction", "embedding"].map(cap => <label className="check" key={cap}><input type="checkbox" aria-label={`Model capability ${cap}`} checked={form.capabilities.includes(cap)} onChange={e => setForm({...form, capabilities:e.target.checked ? cap === "embedding" ? ["embedding"] : [...form.capabilities.filter((c: string) => c !== "embedding"), cap] : form.capabilities.filter((c: string) => c !== cap)})} />{cap}</label>)}<label className="check"><input type="checkbox" aria-label="Model enabled" checked={form.enabled} onChange={e => setForm({...form, enabled:e.target.checked})} />Enabled</label></div><ActionButton className="btn primary" disabled={busy || !profiles.length || !form.capabilities.length} label="Save catalog model" action="save"/></div>{!profiles.length && <p className="small muted" style={{marginTop:14}}>Save a connection in the Profiles section before adding this model.</p>}<p className="small muted" style={{marginTop:14, marginBottom:0}}>Embedding models are separate from chat and extraction models. Select supported capabilities; adding embedding clears generation capabilities. Credentials are never copied into the dataset or returned to the browser.</p></form>}
  </section>;
}
