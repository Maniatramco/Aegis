"use client";
import {ActionButton} from "./action-button";
import { useEffect, useState } from "react";
import { Check, Layers, Search, X, Pencil } from "lucide-react";
import "./model-configuration.css";
import { parseModelParameters, supportedModelParameters } from "./model-parameters";

type Entity = Record<string, any>;
type Api = (path: string, method?: string, body?: unknown) => Promise<any>;
type ProviderChoice = {id: string; name: string; protocol: string; endpoint: string; region: string; auth_modes: string[]; categories: string[]};
function providerId(connection: Entity) {
  if (connection.protocol !== "openai-compatible") return connection.protocol;
  try { const host = new URL(connection.endpoint).hostname; return host === "generativelanguage.googleapis.com" ? "gemini" : host === "api.openai.com" ? "openai" : "openai-compatible"; } catch { return "openai-compatible"; }
}
const authOptions: Record<string, [string, string][]> = {
  ollama: [["none", "No credentials · local service"]],
  "openai-compatible": [["api_key", "API key"], ["bearer_token", "Bearer token"]],
  "azure-openai": [["api_key", "API key"], ["bearer_token", "Bearer token"]],
  bedrock: [["aws_keys", "Access keys"], ["server_identity", "Server / workload identity"]],
  vertex: [["service_account", "Service account JSON"], ["server_identity", "Server / workload identity"], ["bearer_token", "Bearer token"]],
  oci: [["oci_credentials", "API signing credentials"], ["server_identity", "Resource principal"], ["config_profile", "Server credential profile"]],
};
const endpointHints: Record<string, string> = {
  ollama: "http://127.0.0.1:11435", "openai-compatible": "https://your-service.example.com/v1",
  "azure-openai": "https://your-resource.openai.azure.com/openai/v1",
  bedrock: "https://bedrock-runtime.us-east-1.amazonaws.com",
  vertex: "https://us-central1-aiplatform.googleapis.com", oci: "https://inference.generativeai.us-chicago-1.oci.oraclecloud.com",
};
const credentialFields: Record<string, [string, string, boolean?][]> = {
  api_key: [["api_key", "API key"]], bearer_token: [["token", "Bearer token"]],
  aws_keys: [["access_key_id", "Access key ID"], ["secret_access_key", "Secret access key"], ["session_token", "Session token (optional)"]],
  service_account: [["service_account", "Service account JSON", true]],
  oci_credentials: [["tenancy", "Tenancy OCID"], ["user", "User OCID"], ["fingerprint", "Key fingerprint"], ["key_content", "Private key (PEM)", true], ["pass_phrase", "Key passphrase (optional)"]],
};

export function ModelRegistration({ models, settings, api, run, busy, onSaved, onMapping }: {
  models: Entity[]; settings: Entity; api: Api; run: (fn: () => Promise<void>) => Promise<void>;
  busy: boolean; onSaved: (model: Entity) => void; onMapping: () => void;
}) {
  const defaults = settings.model_defaults;
  const blank = (): Entity => ({ name: "", category: "chat", provider_model: "", timeout: defaults?.timeout, context_limit: defaults?.context_limit, max_output_tokens: defaults?.max_output_tokens, enabled: true,
    credentials: {}, clear_credentials: false, allow_external: false,
    connection: { protocol: "ollama", endpoint: settings.ollama_endpoint || endpointHints.ollama, auth_mode: "none", region: "", project_id: "", compartment_id: "", profile: "DEFAULT", embedding_format: "titan", chat_format: "generic", dimensions: null, structured_output: true } });
  const [form, setForm] = useState<Entity>(blank);
  const [editing, setEditing] = useState<Entity | null>(null);
  const [open, setOpen] = useState(false);
  const [search, setSearch] = useState("");
  const [test, setTest] = useState<Entity | null>(null);
  const [testing, setTesting] = useState(false);
  const [providerChoices, setProviderChoices] = useState<ProviderChoice[]>([]);
  const [providerChoice, setProviderChoice] = useState("ollama");
  const [providerError, setProviderError] = useState("");
  useEffect(() => { let active = true; api("/model-providers").then(value => { if (active) setProviderChoices(value); }).catch(() => { if (active) setProviderError("Provider choices could not load. Reload this screen to retry."); }); return () => { active = false; }; }, [api]);
  const [extraText, setExtraText] = useState("{}");
  const [extraOpen, setExtraOpen] = useState(false);
  const change = (key: string, value: any) => { setForm(current => ({ ...current, [key]: value, ...(key === "category" ? { context_limit: value === "embedding" ? defaults?.embedding_context_limit : defaults?.context_limit } : {}) })); if (key === "category") setExtraText("{}"); setTest(null); };
  const connectionChange = (key: string, value: any) => {
    setForm(current => ({ ...current, connection: { ...current.connection, [key]: value },
      ...(["protocol", "endpoint", "auth_mode"].includes(key) ? { credentials: {}, allow_external: false } : {}) }));
    setTest(null);
    if (["protocol", "embedding_format", "chat_format"].includes(key)) setExtraText("{}");
  };
  const start = (model?: Entity) => {
    if (!defaults) return;
    const initial = blank();
    if (model) {
      initial.name = model.name; initial.provider_model = model.provider_model;
      initial.category = model.capabilities[0]; initial.enabled = model.enabled; initial.timeout = model.timeout || defaults.timeout; initial.context_limit = model.context_limit || (initial.category === "embedding" ? defaults.embedding_context_limit : defaults.context_limit); initial.max_output_tokens = model.max_output_tokens || defaults.max_output_tokens;
      if (model.connection) initial.connection = { ...initial.connection, ...model.connection };
      else if (model.provider !== "ollama") {
        initial.connection = { ...initial.connection, protocol: "openai-compatible", auth_mode: "api_key", endpoint: "" };
      }
    }
    setEditing(model || null); setForm(initial); setExtraText(JSON.stringify(model?.extra_parameters || {}, null, 2)); setExtraOpen(!!Object.keys(model?.extra_parameters || {}).length); setTest(null); setOpen(true);
    setProviderChoice(providerId(initial.connection));
  };
  const close = () => { setOpen(false); setEditing(null); setForm(blank()); setTest(null); };
  const native = ["bedrock", "vertex", "oci"].includes(form.connection.protocol);
  const remote = form.connection.protocol !== "ollama";
  const visible = models.filter(m => `${m.name} ${m.provider_model} ${m.capabilities.join(" ")}`.toLowerCase().includes(search.toLowerCase()));
  const retainedCredentials = editing?.credential_configured && editing?.connection && ["endpoint", "protocol", "auth_mode"].every(key => editing.connection[key] === form.connection[key]);
  const supported = supportedModelParameters(form.connection.protocol, form.category, form.connection);
  let parameterError = "";
  try { parseModelParameters(extraText, supported); } catch (error) { parameterError = (error as Error).message; }
  const payload = () => ({ ...form, max_output_tokens: form.category === "embedding" ? null : form.max_output_tokens, extra_parameters: parseModelParameters(extraText, supported), existing_model_id: editing?.id || null });

  return <div className="model-registration">
    {settings.local_only && <div className="notice"><Layers size={17} /><div>This deployment runs in local-only mode. You can register cloud connections, but testing and applying them require cloud use to be enabled by the deployment administrator.</div></div>}
    {!open ? <section className="panel registration-directory">
      <div className="panel-head"><span className="pill">{models.length} models</span><ActionButton className="btn primary" disabled={busy || !defaults} onClick={() => start()} label="Register model" action="add"/></div>
      {!!models.length && <label className="registration-search"><Search size={16} aria-hidden="true" /><input type="search" aria-label="Search registered models" value={search} onChange={e => setSearch(e.target.value)} onKeyDown={e=>{if(e.key==='Escape')setSearch('');}} placeholder="Search models or categories" />{search&&<button className="btn icon" type="button" title="Clear search" aria-label="Clear model search" onClick={()=>setSearch('')}><X size={14}/></button>}</label>}
      {!!models.length && <div className="registration-table" role="region" aria-label="Registered models table" tabIndex={0}>
        <table aria-label="Registered models"><thead><tr><th scope="col">Model</th><th scope="col">Category</th><th scope="col">Provider</th><th scope="col">Endpoint</th><th scope="col" className="registration-tokens" title="Configured input limit for embeddings; total context limit for chat and extraction">Input / context</th><th scope="col" className="registration-tokens" title="Configured maximum output tokens">Output</th><th scope="col">Status</th><th scope="col">Actions</th></tr></thead>
          <tbody>{visible.map(m=><tr key={m.id}>
            <th scope="row"><div className="registration-model-cell"><Layers size={16} aria-hidden="true"/><div><strong>{m.name}</strong><small>{m.provider_model}</small>{!!Object.keys(m.extra_parameters||{}).length&&<small>{Object.keys(m.extra_parameters).length} extra parameters</small>}</div></div></th>
            <td><div className="model-chips">{m.capabilities.map((cap:string)=><span className="model-chip" key={cap}>{cap==='extraction'?'Extraction':cap==='embedding'?'Embedding':'Chat'}</span>)}</div></td>
            <td>{providerChoices.find(p=>p.id===providerId(m.connection||{protocol:m.provider}))?.name||m.provider}</td>
            <td><span className="registration-endpoint" title={m.connection?.endpoint||'No endpoint configured'}>{m.connection?.endpoint||'—'}</span></td>
            <td className="registration-tokens" title={m.capabilities[0]==='embedding'?'Input tokens':'Context tokens'}>{m.context_limit?.toLocaleString()||'—'}</td>
            <td className="registration-tokens" title={m.capabilities[0]==='embedding'?'Not applicable to embeddings':'Maximum output tokens'}>{m.capabilities[0]==='embedding'?'—':m.max_output_tokens?.toLocaleString()||'—'}</td>
            <td><span className={`pill ${m.enabled?'green':'amber'}`}>{m.enabled?'Enabled':'Disabled'}</span></td>
            <td><button className="btn icon registration-edit" disabled={busy || !defaults} title={`Edit ${m.name}`} aria-label={`Edit ${m.name}`} onClick={()=>start(m)}><Pencil size={15}/></button></td>
          </tr>)}{!visible.length&&<tr><td colSpan={8} className="registration-table-empty">No models match your search.</td></tr>}</tbody>
        </table>
      </div>}
      {!models.length && <div className="empty"><Layers size={30} /><h3>Start with your models</h3><p>Register an Embedding, Chat, and Extraction model. Each dataset needs all three categories.</p></div>}
      <div className="registration-footer"><ActionButton className="btn" onClick={onMapping} label="Open Model Mapping" action="mapping"/></div>
    </section> : <section className="panel registration-form-panel">
      <form onSubmit={e => { e.preventDefault(); if (!test) return; run(async () => { const saved = await api(`/model-registrations${editing ? "/" + editing.id : ""}`, editing ? "PUT" : "POST", payload()); onSaved(saved); close(); }); }}>
        <div className="panel-head"><h2>{editing ? "Edit model" : "Register model"}</h2><button title="Cancel model registration" className="btn icon" type="button" aria-label="Cancel model registration" disabled={busy} onClick={close}><X size={16} /></button></div>
        <fieldset disabled={busy}>
          <div className="registration-fields">
            <div className="field"><label htmlFor="registration-name">Name</label><input id="registration-name" autoFocus value={form.name} onChange={e => change("name", e.target.value)} required maxLength={120} placeholder="e.g. Document extraction" /></div>
            <div className="field"><label htmlFor="registration-category">Category</label><select id="registration-category" value={form.category} disabled={!!editing} onChange={e => change("category", e.target.value)}>{[["embedding", "Embedding"], ["chat", "Chat"], ["extraction", "Extraction"]].map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></div>
            <div className="field"><label htmlFor="registration-protocol">Provider</label><select id="registration-protocol" value={providerChoice} disabled={!providerChoices.length} onChange={e => { const choice = providerChoices.find(p => p.id === e.target.value); if (!choice) return; setProviderChoice(choice.id); const protocol = choice.protocol; setForm(current => ({ ...current, provider_model: "", credentials: {}, clear_credentials: false, allow_external: false, connection: { ...blank().connection, protocol, region: choice.region, endpoint: protocol === "ollama" ? settings.ollama_endpoint || choice.endpoint : choice.endpoint, auth_mode: choice.auth_modes[0] } })); setExtraText("{}"); setTest(null); }}>{providerChoices.length ? providerChoices.map(p => <option key={p.id} value={p.id}>{p.name}</option>) : <option value="ollama">Loading providers…</option>}</select>{providerError && <small role="alert">{providerError}</small>}</div>
            <div className="field"><label htmlFor="registration-model">Model / deployment ID</label><input id="registration-model" value={form.provider_model} onChange={e => change("provider_model", e.target.value)} required maxLength={200} placeholder={form.connection.protocol === "azure-openai" ? "Deployment name" : "Model ID"} /></div>
            <div className="field registration-full"><label htmlFor="registration-endpoint">Endpoint</label><input id="registration-endpoint" type="url" value={form.connection.endpoint} onChange={e => connectionChange("endpoint", e.target.value)} required maxLength={500} placeholder={endpointHints[form.connection.protocol]} /><small>Use the service base URL. Custom gateway hosts must be approved in the deployment.</small></div>
            {native && <div className="field"><label htmlFor="registration-region">Region / location</label><input id="registration-region" value={form.connection.region} onChange={e => connectionChange("region", e.target.value)} required placeholder="e.g. us-east-1" /></div>}
            {form.connection.protocol === "vertex" && <div className="field"><label htmlFor="registration-project">Project ID</label><input id="registration-project" value={form.connection.project_id} onChange={e => connectionChange("project_id", e.target.value)} required /></div>}
            {form.connection.protocol === "oci" && <div className="field"><label htmlFor="registration-compartment">Compartment OCID</label><input id="registration-compartment" value={form.connection.compartment_id} onChange={e => connectionChange("compartment_id", e.target.value)} required /></div>}
            <div className="field"><label htmlFor="registration-auth">Authentication</label><select id="registration-auth" value={form.connection.auth_mode} onChange={e => connectionChange("auth_mode", e.target.value)}>{authOptions[form.connection.protocol].map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></div>
            <div className="field"><label htmlFor="registration-timeout">Timeout (seconds)</label><input id="registration-timeout" type="number" min={defaults?.timeout_min} max={defaults?.timeout_max} value={form.timeout} onChange={e => change("timeout", Number(e.target.value))} required /><small>Detailed local extraction on CPU may need 1,200 seconds. This is a limit, not an estimated completion time.</small></div>
            <div className="field"><label htmlFor="registration-context-limit">{form.category === "embedding" ? "Input token limit" : "Context token limit"}</label><input id="registration-context-limit" type="number" min={1} max={defaults?.context_max} step={1} value={form.context_limit} onChange={e => change("context_limit", Number(e.target.value))} aria-describedby="registration-context-help" required /><small id="registration-context-help">{form.category === "embedding" ? "Maximum input per text chunk or query. No output tokens; embeddings return vectors." : `Total input and output budget, including instructions and history. Keep ${defaults?.headroom_tokens} tokens of headroom beyond the output limit.`} Aegis uses a conservative text estimate. Set this within the model’s supported capacity.</small></div>
            {form.category !== "embedding" && <div className="field"><label htmlFor="registration-output-limit">Maximum output tokens</label><input id="registration-output-limit" type="number" min={1} max={defaults?.output_max} step={1} value={form.max_output_tokens} onChange={e => change("max_output_tokens", Number(e.target.value))} required /><small>Maximum tokens generated per answer or extraction. Default: {defaults?.max_output_tokens?.toLocaleString()}. Larger limits can take longer and use more memory or provider credits.</small></div>}
            {form.connection.auth_mode === "config_profile" && <div className="field"><label htmlFor="registration-profile">Server credential profile</label><input id="registration-profile" value={form.connection.profile} onChange={e => connectionChange("profile", e.target.value)} required /></div>}
          </div>
          {!!credentialFields[form.connection.auth_mode]?.length && <div className="registration-credentials"><h3>Credentials</h3><p className="muted small">{retainedCredentials ? "Leave all credential fields empty to retain the saved credentials. Enter the complete set to replace them." : "Enter credentials for this endpoint. They are never returned to the browser."}</p><div className="registration-fields">
            {credentialFields[form.connection.auth_mode].map(([key, label, multiline]) => <div className={`field ${multiline ? "registration-full" : ""}`} key={key}><label htmlFor={`credential-${key}`}>{label}</label>{multiline ? <textarea id={`credential-${key}`} rows={4} value={form.credentials[key] || ""} spellCheck={false} autoComplete="off" onChange={e => change("credentials", { ...form.credentials, [key]: e.target.value })} /> : <input id={`credential-${key}`} type="password" autoComplete="new-password" value={form.credentials[key] || ""} onChange={e => change("credentials", { ...form.credentials, [key]: e.target.value })} />}</div>)}
          </div>{!!editing && <label className="check"><input type="checkbox" checked={form.clear_credentials} onChange={e => change("clear_credentials", e.target.checked)} />Remove saved credentials (disable the model first)</label>}</div>}
          {form.connection.auth_mode === "server_identity" && <p className="muted small">The API and worker hosts must have an identity permitted to invoke this model.</p>}
          {form.category === "embedding" && <div className="registration-fields registration-options">
            <div className="field"><label htmlFor="registration-dimensions">Output dimensions (optional)</label><input id="registration-dimensions" type="number" min={1} max={65536} value={form.connection.dimensions || ""} onChange={e => connectionChange("dimensions", e.target.value ? Number(e.target.value) : null)} /><small>Leave empty for the model’s default dimensions.</small></div>
            {form.connection.protocol === "bedrock" && <div className="field"><label htmlFor="registration-embedding-format">Embedding request format</label><select id="registration-embedding-format" value={form.connection.embedding_format} onChange={e => connectionChange("embedding_format", e.target.value)}><option value="titan">Titan Text</option><option value="cohere-v3">Cohere Embed v3</option><option value="cohere-v4">Cohere Embed v4</option></select></div>}
          </div>}
          {form.category !== "embedding" && form.connection.protocol === "oci" && <div className="field"><label htmlFor="registration-chat-format">Chat request format</label><select id="registration-chat-format" value={form.connection.chat_format} onChange={e => connectionChange("chat_format", e.target.value)}><option value="generic">Generic</option><option value="cohere">Cohere</option></select></div>}
          {form.category === "extraction" && ["openai-compatible", "azure-openai"].includes(form.connection.protocol) && <label className="check"><input type="checkbox" checked={form.connection.structured_output} onChange={e => connectionChange("structured_output", e.target.checked)} />Request native JSON schema output <span className="muted small">All extraction responses are validated against the template.</span></label>}
          <details className="registration-options registration-extra" open={extraOpen} onToggle={e => setExtraOpen(e.currentTarget.open)}><summary>Add extra parameters</summary><div className="field"><label htmlFor="registration-extra-parameters">Extra parameters (JSON)</label><small id="registration-parameter-help">{supported.length ? `Supported keys: ${supported.join(", ")}.` : "This adapter has no additional parameters. Use the token limit and dimensions fields."} Leave empty to use defaults. Use only options supported by your deployed model. These values are visible to workspace users; keep credentials in Authentication.</small><textarea id="registration-extra-parameters" rows={4} spellCheck={false} value={extraText} onChange={e => { setExtraText(e.target.value); setTest(null); }} aria-invalid={!!parameterError} aria-describedby="registration-parameter-help registration-parameter-error" placeholder={form.category === "embedding" ? '{"keep_alive": "5m"}' : '{"temperature": 0.2}'} />{parameterError && <small id="registration-parameter-error" role="alert">{parameterError}</small>}</div></details>
          <div className="registration-options"><label className="check"><input type="checkbox" checked={form.enabled} onChange={e => change("enabled", e.target.checked)} />Enabled for dataset mapping</label></div>
          {remote && <label className="check registration-test-consent"><input type="checkbox" checked={form.allow_external} onChange={e => change("allow_external", e.target.checked)} />Allow a small synthetic test request to this external model. Provider usage may be billed.</label>}
        </fieldset>
        {test && <div className="notice" role="status"><Check size={17} /><div>Connection passed in {(test.elapsed_ms / 1000).toFixed(2)}s.{test.dimensions && ` Embedding dimensions: ${test.dimensions}.`}{test.schema_validated && " Extraction schema validated."}{test.agent_tool_call_validated && " Agent function calling validated."}</div></div>}
        <div className="registration-actions"><button className="btn" type="button" disabled={busy || !!parameterError || !form.name.trim() || !form.provider_model.trim() || !form.connection.endpoint || remote && (!form.allow_external || settings.local_only)} onClick={e => { if (!e.currentTarget.form?.reportValidity()) return; setTest(null); setTesting(true); run(async () => { try { setTest(await api("/model-registrations/test", "POST", payload())); } finally { setTesting(false); } }); }}>{testing ? "Testing connection…" : "Test Connection"}</button><div className="row wrap"><button className="btn" type="button" disabled={busy} onClick={close}>Cancel</button><ActionButton className="btn primary" disabled={busy || !!parameterError || !test} label="Save Model" action="save"/></div></div>
        <p className="muted small">Test the connection before saving. Chat tests verify Agent function calling. New chat and extraction runs use the latest saved connection. Embedding changes require applying the dataset mapping and reindexing its documents. Work already queued keeps its saved version.</p>
      </form>
    </section>}
  </div>;
}
