"use client";
import {ActionButton} from "./action-button";
import {useEffect,useRef,useState} from 'react';
import {Activity,ArrowDownToLine,Layers} from 'lucide-react';
import {WorkflowStepper} from './workflow-stepper';

type Entity=Record<string,any>;
type Api=(path:string,method?:string,body?:unknown,signal?:AbortSignal)=>Promise<any>;
function Field({label,help,children}:{label:string;help?:string;children:React.ReactNode}){
 return <div className="field"><label>{label}</label>{children}{help&&<small className="muted">{help}</small>}</div>;
}
function Notice({children}:{children:React.ReactNode;tone?:string}){return <div className="notice warn">{children}</div>;}
function Download({path,children}:{path:string;children:React.ReactNode}){return <a className="btn" href={'/api'+path} download><ArrowDownToLine size={14}/>{children}</a>;}
const json=(value:unknown)=>JSON.stringify(value,null,2);
const date=(value:string|number)=>new Date(typeof value==='number'&&value<100000000000?value*1000:value).toLocaleString();

export function ConnectionSettings({api,onChanged,onModels}:{api:Api;onChanged:()=>void;onModels:()=>void}){
 const [settings,setSettings]=useState<Entity>({}),[settingsForm,setSettingsForm]=useState<Entity>({});
 const [caps,setCaps]=useState<Entity>({}),[profiles,setProfiles]=useState<Entity[]>([]);
 const [apiKey,setApiKey]=useState(''),[ociApiKey,setOciApiKey]=useState(''),[profileName,setProfileName]=useState('');
 const [connectionTab,setConnectionTab]=useState('Processing'),[testResult,setTestResult]=useState<Entity|null>(null);
 const [ready,setReady]=useState(false),[busy,setBusy]=useState(false),[error,setError]=useState(''),[message,setMessage]=useState('');
 const lock=useRef(false);
 const [confirm,setConfirm]=useState<{title:string;body:string;action:()=>Promise<void>}|null>(null);
 const load=async(signal?:AbortSignal)=>{
  const [saved,capabilities,registered]=await Promise.all([api('/settings','GET',undefined,signal),api('/capabilities','GET',undefined,signal),api('/settings/profiles','GET',undefined,signal)]);
  if(signal?.aborted)return;
  setSettings(saved);setSettingsForm(saved);setCaps(capabilities);setProfiles(Array.isArray(registered)?registered:registered.profiles||[]);setReady(true);
 };
 useEffect(()=>{const controller=new AbortController();void load(controller.signal).catch(e=>{if(!controller.signal.aborted)setError(e.message);});return()=>controller.abort();},[api]);
 const run=async(action:()=>Promise<void>)=>{
  if(lock.current)return;lock.current=true;setBusy(true);setError('');setMessage('');
  try{await action();}catch(e){setError(e instanceof Error?e.message:'Connection operation failed.');}finally{lock.current=false;setBusy(false);}
 };
 const notify=(value:string)=>setMessage(value);
 const reload=()=>{onChanged();};
 return <details className="panel connection-settings" aria-label="Advanced connections">
  <summary>Advanced connections</summary>
  <p className="small muted">Provider defaults, processing, OCI generation, saved profiles and diagnostics.</p>
  {!ready?<><p role="status">{error||'Loading connection settings…'}</p><ActionButton className="btn" onClick={()=>void run(()=>load())} label="Retry loading connections" action="retry"/></>:<>

              <div className="section-tabs" aria-label="Advanced connection sections">{["Profiles", "Providers", "Processing", "OCI", "Diagnostics"].map(tab => <button key={tab} className={`btn ${connectionTab === tab ? "primary" : ""}`} aria-pressed={connectionTab === tab} onClick={() => setConnectionTab(tab)}>{tab}</button>)}</div>
              <div hidden={!["Providers", "Processing", "OCI"].includes(connectionTab)}><Notice tone="warn">
                Provider keys are encrypted on the server and never saved in
                browser storage. OpenAI usage is separate from a ChatGPT
                subscription. Changing an embedding model requires reindexing
                existing documents.
              </Notice></div>
              <section className="panel" hidden={connectionTab !== "Profiles"}>
                <div className="panel-head">
                  <div>
                    <h2>Connection profiles</h2>
                    <p className="muted small">
                      Save the current server configuration and encrypted
                      provider keys as a reusable, versioned profile. Save any
                      form changes first.
                    </p>
                  </div>
                  <Layers size={20} color="#718ac4" />
                </div>
                <div
                  className="row"
                  style={{ maxWidth: 600, marginBottom: 20 }}
                >
                  <input
                    aria-label="Profile name"
                    placeholder="e.g. Local development or OCI production"
                    value={profileName}
                    onChange={(e) => setProfileName(e.target.value)}
                  />
                  <ActionButton
                    className="btn primary"
                    disabled={busy || !profileName.trim()}
                    onClick={() =>
                      run(async () => {
                        await api("/settings/profiles", "POST", {
                          name: profileName,
                        });
                        setProfileName("");
                        setProfiles(await api("/settings/profiles"));
                        notify(
                          "Current server configuration saved as an encrypted profile.",
                        );
                      })
                    }
                   label="Save current profile" action="save"/>
                </div>
                {profiles.length ? (
                  profiles.map((p) => (
                    <div className="item row between wrap" key={p.id}>
                      <div>
                        <h3>{p.name}</h3>
                        <span className="muted small">
                          Version {p.version} · {date(p.created_at)} ·{" "}
                          {p.api_key_configured || p.oci_api_key_configured || p.connection_credentials_configured
                            ? "Encrypted credentials saved"
                            : "No provider key saved"}
                        </span>
                      </div>
                      <div className="row wrap">
                        {p.registration_model_id && <ActionButton className="btn" onClick={() => onModels()} label="Edit in Model Registration" action="edit"/>}
                        <button
                          className="btn"
                          disabled={busy || !!p.registration_model_id}
                          onClick={() =>
                            setConfirm({
                              title: `Activate ${p.name}?`,
                              body: "This replaces the active model, embedding, search, storage, queue configuration and provider credentials with this saved profile. External processing requires approval again. Embedding changes require reindexing. The server blocks unsafe storage changes and active jobs.",
                              action: async () => {
                                const d = await api(
                                  `/settings/profiles/${p.id}/activate`,
                                  "POST",
                                  {},
                                );
                                setSettings(d);
                                setSettingsForm(d);
                                setApiKey("");
                                setOciApiKey("");
                                notify(
                                  "Connection profile activated. Check connection readiness and reindex if needed.",
                                );
                                reload();
                              },
                            })
                          }
                        >
                          Activate
                        </button>
                        <ActionButton
                          className="btn"
                          disabled={busy || !!p.registration_model_id}
                          onClick={() =>
                            setConfirm({
                              title: `Save a new version of ${p.name}?`,
                              body: "Save the current server configuration and encrypted provider credentials as a new version of this profile. Unsaved form edits are not included.",
                              action: async () => {
                                await api(`/settings/profiles/${p.id}`, "PUT", {
                                  name: p.name,
                                });
                                setProfiles(await api("/settings/profiles"));
                                notify("Profile version saved.");
                              },
                            })
                          }
                         label="Save new version" action="save"/>
                        <Download path={`/settings/profiles/${p.id}/export`}>
                          Safe export
                        </Download>
                      </div>
                    </div>
                  ))
                ) : (
                  <p className="muted small">No saved profiles yet.</p>
                )}
              </section>
              <div className="settings-focus">
                <section className="panel" hidden={connectionTab !== "Providers"}>
                  <div className="panel-head">
                    <h2>Connection configuration</h2>
                    <span className="pill">Server-side configuration</span>
                  </div>
                  <Field label="Connection's generation provider">
                    <select
                      value={settingsForm.model_provider || "openai"}
                      aria-label="Model provider"
                      onChange={(e) =>
                        setSettingsForm({
                          ...settingsForm,
                          model_provider: e.target.value,
                        })
                      }
                    >
                      <option value="ollama">Ollama — local, no API key</option>
                      <option value="openai" disabled={settings.local_only}>OpenAI</option>
                      <option value="oci" disabled={settings.local_only}>
                        OCI Generative AI · requires validation
                      </option>
                      <option value="mock">
                        Mock · explicit development test mode
                      </option>
                    </select>
                  </Field>
                  {settingsForm.model_provider === "ollama" && (
                    <p className="muted small">Runs on this computer through Ollama. No API key is needed. Download the selected models before use.</p>
                  )}
                  <Field label="Connection’s default generation model">
                    <input
                      aria-label="Answer model"
                      value={settingsForm.model || ""}
                      onChange={(e) =>
                        setSettingsForm({
                          ...settingsForm,
                          model: e.target.value,
                        })
                      }
                      placeholder={settingsForm.model_provider === "ollama" ? "qwen3:4b" : "gpt-4.1-mini"}
                    />
                  </Field>
                  <Field label="Embedding provider">
                    <select
                      aria-label="Embedding provider"
                      value={
                        settingsForm.embedding_provider ||
                        "sentence_transformers"
                      }
                      onChange={(e) =>
                        setSettingsForm({
                          ...settingsForm,
                          embedding_provider: e.target.value,
                        })
                      }
                    >
                      <option value="sentence_transformers">
                        Local · Sentence Transformers
                      </option>
                      <option value="ollama">Ollama — local embeddings</option>
                      <option value="openai" disabled={settings.local_only}>OpenAI</option>
                      <option value="mock">
                        Mock · explicit development test mode
                      </option>
                    </select>
                  </Field>
                  <Field label="Embedding model">
                    <input
                      aria-label="Embedding model"
                      value={settingsForm.embedding_model || ""}
                      onChange={(e) =>
                        setSettingsForm({
                          ...settingsForm,
                          embedding_model: e.target.value,
                        })
                      }
                    />
                  </Field>
                  <Field
                    label="OpenAI API key"
                    help={
                      settings.local_only ? "Provider credentials are disabled in this local-only workspace." : settings.api_key_configured
                        ? "A key is configured. Leave blank to keep it unchanged."
                        : "No key configured. Enter your own provider key; it is encrypted by the server."
                    }
                  >
                    <input
                      aria-label="OpenAI API key"
                      disabled={settings.local_only}
                      type="password"
                      autoComplete="off"
                      value={apiKey}
                      placeholder={
                        settings.api_key_configured
                          ? "•••••••• · configured"
                          : "sk-…"
                      }
                      onChange={(e) => setApiKey(e.target.value)}
                    />
                  </Field>
                  {settingsForm.model_provider === "mock" && (
                    <Notice tone="warn">
                      Mock mode generates synthetic test output. It is not model
                      intelligence and must not be used as a production answer
                      or extraction.
                    </Notice>
                  )}
                </section>
                <section className="panel" hidden={connectionTab !== "Processing"}>
                  <h2>Processing &amp; retrieval</h2>
                  <p className="small muted">File, database and vector destinations are configured above. These controls apply to processing defaults.</p>
                  <Field
                    label="Job queue"
                    help="OCI Queue sends job identifiers only; originals and job state stay in their configured stores. Configure the queue endpoint and identity server-side before switching."
                  >
                    <select
                      aria-label="Job queue"
                      value={settingsForm.queue_provider || "database"}
                      onChange={(e) =>
                        setSettingsForm({
                          ...settingsForm,
                          queue_provider: e.target.value,
                        })
                      }
                    >
                      <option value="database">
                        Database-backed durable queue
                      </option>
                      <option value="oci">
                        OCI Queue · requires validation
                      </option>
                    </select>
                  </Field>
                  <div className="grid2">
                    {[
                      {
                        key: "chunk_size",
                        label: "Chunk size",
                        fallback: 1000,
                      },
                      {
                        key: "chunk_overlap",
                        label: "Chunk overlap",
                        fallback: 150,
                      },
                      { key: "top_k", label: "Retrieved chunks", fallback: 5 },
                      {
                        key: "timeout",
                        label: "Request timeout (sec)",
                        fallback: 60,
                      },
                      {
                        key: "max_upload_mb",
                        label: "Upload limit (MB)",
                        fallback: 25,
                      },
                    ].map((f) => (
                      <Field label={f.label} key={f.key}>
                        <input
                          type="number"
                          min={f.key === "chunk_overlap" ? 0 : 1}
                          aria-label={f.label}
                          value={settingsForm[f.key] ?? f.fallback}
                          onChange={(e) =>
                            setSettingsForm({
                              ...settingsForm,
                              [f.key]: Number(e.target.value),
                            })
                          }
                        />
                      </Field>
                    ))}
                  </div>

                </section>
              </div>
              <section className="panel" hidden={connectionTab !== "OCI"}>
                <h2>OCI migration profile</h2>
                <p className="muted small">
                  OCI adapters are implemented and tested with mocked SDK
                  responses. Validate your tenancy, permissions, and a live
                  round-trip before production use.
                </p>
                <div className="grid3">
                  {[
                    { key: "oci_region", label: "Region" },
                    {
                      key: "oci_project_id",
                      label: "Project / compartment ID",
                    },
                    { key: "oci_auth_mode", label: "Authentication mode" },
                    { key: "oci_model", label: "Model identifier" },
                    {
                      key: "oci_vector_store_id",
                      label: "Vector store identifier",
                    },
                    { key: "oci_profile", label: "OCI SDK profile" },
                  ].map((f) => (
                    <Field label={f.label} key={f.key}>
                      <input
                        aria-label={f.label}
                        value={settingsForm[f.key] || ""}
                        onChange={(e) =>
                          setSettingsForm({
                            ...settingsForm,
                            [f.key]: e.target.value,
                          })
                        }
                      />
                    </Field>
                  ))}
                </div>
                <Field
                  label="OCI Generative AI API key"
                  help="Optional for API key auth. Leave blank to keep the existing server-encrypted key. Signing keys and SDK credentials must be mounted server-side."
                >
                  <input
                    aria-label="OCI Generative AI API key"
                    type="password"
                    autoComplete="off"
                    value={ociApiKey}
                    onChange={(e) => setOciApiKey(e.target.value)}
                  />
                </Field>

              </section>
              <div className="settings-actions" hidden={!["Providers", "Processing", "OCI", "Diagnostics"].includes(connectionTab)}>                  <div className="row wrap">
                    <ActionButton
                      className="btn primary"
                      disabled={busy}
                      onClick={() =>
                        run(async () => {
                          const allowed = [
                            "queue_provider",
                            "model_provider",
                            "embedding_provider",
                            "model",
                            "embedding_model",
                            "chunk_size",
                            "chunk_overlap",
                            "top_k",
                            "timeout",
                            "max_upload_mb",
                            "oci_region",
                            "oci_project_id",
                            "oci_auth_mode",
                            "oci_model",
                            "oci_vector_store_id",
                            "oci_profile",
                          ];
                          const payload: Entity = Object.fromEntries(
                            allowed
                              .filter((k) => k in settingsForm)
                              .map((k) => [k, settingsForm[k]]),
                          );
                          if (apiKey) payload.api_key = apiKey;
                          if (ociApiKey) payload.oci_api_key = ociApiKey;
                          const s = await api("/settings", "PATCH", payload);
                          setSettings(s);
                          setSettingsForm(s);
                          setApiKey("");
                          setOciApiKey("");
                          notify(
                            "Settings saved securely. Reindex documents if embedding settings changed.",
                          );
                          reload();
                        })
                      }
                     label="Save settings" action="save"/>
                    <button
                      className="btn"
                      disabled={busy}
                      onClick={() =>
                        run(async () => {
                          setTestResult(await api("/settings/test", "POST"));
                          setConnectionTab("Diagnostics");
                        })
                      }
                    >
                      <Activity size={14} />
                      Test saved connections
                    </button>
                    <Download path="/settings/export">
                      Export safe config
                    </Download>
                  </div></div>
              {testResult && (
                <section className="panel" hidden={connectionTab !== "Diagnostics"}>
                  <h2>Connection test result</h2>
                  <pre className="code mono">{json(testResult)}</pre>
                </section>
              )}
              <section className="panel" hidden={connectionTab !== "Diagnostics"}>
                <h2>Provider capabilities</h2>
                <p className="muted small">
                  Readiness is reported by the server; an unavailable adapter
                  cannot process your data.
                </p>
                <details className="disclosure"><summary>View technical capabilities</summary><pre className="code mono">{json(caps)}</pre></details>
              </section>

  </>}
  {busy&&<WorkflowStepper label="Connection operation" steps={[{id:'connection-operation',label:'Updating connections',status:'running'}]}/>}
  {message&&<div className="notice" role="status">{message}</div>}{error&&ready&&<div className="notice warn" role="alert">{error}</div>}
  {confirm&&<div className="modal-bg"><section className="modal" role="dialog" aria-modal="true" aria-label={confirm.title}>
   <h2>{confirm.title}</h2><p>{confirm.body}</p><div className="row">
    <button className="btn" disabled={busy} onClick={()=>setConfirm(null)}>Cancel</button>
    <button className="btn primary" disabled={busy} onClick={()=>void run(async()=>{await confirm.action();setConfirm(null);})}>Confirm</button>
   </div>
  </section></div>}
 </details>;
}
