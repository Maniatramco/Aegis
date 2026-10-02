"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import {
  Activity,
  ArrowDownToLine,
  ArrowRight,
  BookOpen,
  Check,
  ChevronRight,
  Cloud,
  Cog,
  Copy,
  Database,
  FileJson,
  FileSearch,
  FileText,
  FolderPlus,
  Layers,
  LayoutDashboard,
  Loader2,
  LogOut,
  Menu,
  MessageSquare,
  Play,
  Plus,
  RefreshCw,
  Search,
  Send,
  Settings2,
  Shield,
  Square,
  ThumbsDown,
  ThumbsUp,
  Trash2,
  UploadCloud,
  X,
  AlertCircle,
  ExternalLink,
  CheckCircle2,
  KeyRound,
  Server,
} from "lucide-react";

type Entity = Record<string, any>;
type View =
  | "Dashboard"
  | "Knowledge library"
  | "Ask Aegis"
  | "Extract"
  | "Templates"
  | "Index inspector"
  | "Jobs & activity"
  | "Connections"
  | "Services & migration"
  | "Setup";
const sections: { name: View; icon: typeof Shield; group?: string }[] = [
  { name: "Dashboard", icon: LayoutDashboard, group: "WORKSPACE" },
  { name: "Knowledge library", icon: BookOpen },
  { name: "Ask Aegis", icon: MessageSquare },
  { name: "Extract", icon: FileSearch },
  { name: "Templates", icon: FileJson },
  { name: "Index inspector", icon: Layers, group: "OPERATIONS" },
  { name: "Jobs & activity", icon: Activity },
  { name: "Connections", icon: Settings2 },
  { name: "Services & migration", icon: Cloud },
  { name: "Setup", icon: Cog },
];
const descriptions: Record<View, string> = {
  Dashboard:
    "Your documents, processing activity, and connected services at a glance.",
  "Knowledge library":
    "Keep originals safe. Build searchable knowledge on your terms.",
  "Ask Aegis": "Ask across your knowledge, with evidence you can inspect.",
  Extract: "Turn document content into structured, reviewable data.",
  Templates: "Define the fields and structure your extraction needs.",
  "Index inspector":
    "Inspect document chunks and the retrieval layer behind your answers.",
  "Jobs & activity": "Follow processing work and resolve what needs attention.",
  Connections: "Configure providers, credentials, and processing defaults.",
  "Services & migration":
    "A clear path from local deployment to your cloud environment.",
  Setup: "Get your workspace ready, one deliberate step at a time.",
};
const byteSize = (n: number) =>
  n > 1048576
    ? `${(n / 1048576).toFixed(1)} MB`
    : `${Math.ceil((n || 0) / 1024)} KB`;
const date = (v: string | number) =>
  v
    ? new Date(
        typeof v === "number" && v < 100000000000 ? v * 1000 : v,
      ).toLocaleString()
    : "—";
const json = (v: unknown) => JSON.stringify(v, null, 2);
const getText = (v: unknown): string => (typeof v === "string" ? v : json(v));
function Status({ value }: { value: string }) {
  const green = [
    "ready",
    "completed",
    "succeeded",
    "healthy",
    "connected",
    "available",
  ].includes(value);
  const red = ["failed", "error", "unavailable", "cancelled"].includes(value);
  return (
    <span className={`pill ${green ? "green" : red ? "red" : "amber"}`}>
      <span className="dot" />
      {(value || "unknown").replaceAll("_", " ")}
    </span>
  );
}
function Empty({
  title,
  detail,
  icon: Icon = FileText,
}: {
  title: string;
  detail: string;
  icon?: typeof Shield;
}) {
  return (
    <div className="empty">
      <Icon size={32} strokeWidth={1.3} />
      <h3>{title}</h3>
      <p className="small">{detail}</p>
    </div>
  );
}
function Field({
  label,
  help,
  children,
}: {
  label: string;
  help?: string;
  children: React.ReactNode;
}) {
  return (
    <div className="field">
      <label>{label}</label>
      {children}
      {help && <small>{help}</small>}
    </div>
  );
}
function Notice({
  children,
  tone = "info",
}: {
  children: React.ReactNode;
  tone?: string;
}) {
  return (
    <div
      className={`notice ${tone === "error" ? "error" : tone === "warn" ? "warn" : ""}`}
    >
      <AlertCircle size={16} />
      <div>{children}</div>
    </div>
  );
}
function Download({
  path,
  children,
}: {
  path: string;
  children: React.ReactNode;
}) {
  return (
    <a className="btn" href={`/api${path}`} download>
      <ArrowDownToLine size={14} />
      {children}
    </a>
  );
}

export default function App() {
  const [view, setView] = useState<View>("Dashboard");
  const [user, setUser] = useState<Entity | null>(null);
  const [authChecked, setAuthChecked] = useState(false);
  const [csrf, setCsrf] = useState("");
  const [bootstrap, setBootstrap] = useState(false);
  const [bootstrapToken, setBootstrapToken] = useState("");
  const [username, setUsername] = useState("admin");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [toast, setToast] = useState("");
  const [mobile, setMobile] = useState(false);
  const [refresh, setRefresh] = useState(0);
  const [overview, setOverview] = useState<Entity>({});
  const [docs, setDocs] = useState<Entity[]>([]);
  const [kbs, setKbs] = useState<Entity[]>([]);
  const [kb, setKb] = useState("");
  const [query, setQuery] = useState("");
  const [jobs, setJobs] = useState<Entity[]>([]);
  const [caps, setCaps] = useState<Entity>({});
  const [settings, setSettings] = useState<Entity>({});
  const [modal, setModal] = useState<{
    title: string;
    data: Entity | string;
  } | null>(null);
  const [confirm, setConfirm] = useState<{
    title: string;
    body: string;
    action: () => Promise<void>;
  } | null>(null);
  const [newKb, setNewKb] = useState("");
  const [files, setFiles] = useState<File[]>([]);
  const [externalUpload, setExternalUpload] = useState(false);
  const [conversations, setConversations] = useState<Entity[]>([]);
  const [conversation, setConversation] = useState<Entity | null>(null);
  const [prompt, setPrompt] = useState("");
  const [scope, setScope] = useState<string[]>([]);
  const [externalChat, setExternalChat] = useState(false);
  const [answering, setAnswering] = useState(false);
  const [lastPrompt, setLastPrompt] = useState("");
  const abort = useRef<AbortController | null>(null);
  const [templates, setTemplates] = useState<Entity[]>([]);
  const [templateId, setTemplateId] = useState("");
  const [templateName, setTemplateName] = useState("");
  const [schema, setSchema] = useState(
    json({
      type: "object",
      properties: {
        invoice_number: { type: "string", description: "Invoice reference" },
        total: { type: "number", description: "Total amount" },
      },
      required: ["invoice_number", "total"],
      additionalProperties: false,
    }),
  );
  const [extractions, setExtractions] = useState<Entity[]>([]);
  const [extraction, setExtraction] = useState<Entity | null>(null);
  const [resultText, setResultText] = useState("");
  const [externalExtract, setExternalExtract] = useState(false);
  const [indexDoc, setIndexDoc] = useState("");
  const [indexData, setIndexData] = useState<Entity>({});
  const [retrievalQuery, setRetrievalQuery] = useState("");
  const [retrievalConsent, setRetrievalConsent] = useState(false);
  const [retrievalResult, setRetrievalResult] = useState<Entity | null>(null);
  const [settingsForm, setSettingsForm] = useState<Entity>({});
  const [apiKey, setApiKey] = useState("");
  const [ociApiKey, setOciApiKey] = useState("");
  const [testResult, setTestResult] = useState<Entity | null>(null);
  const [profiles, setProfiles] = useState<Entity[]>([]);
  const [profileName, setProfileName] = useState("");
  const api = useCallback(
    async (
      path: string,
      method = "GET",
      body?: unknown,
      signal?: AbortSignal,
    ) => {
      const headers: Record<string, string> = {};
      if (body && !(body instanceof FormData))
        headers["Content-Type"] = "application/json";
      if (csrf) headers["X-CSRF-Token"] = csrf;
      const r = await fetch(`/api${path}`, {
        method,
        headers,
        credentials: "include",
        body:
          body instanceof FormData
            ? body
            : body
              ? JSON.stringify(body)
              : undefined,
        signal,
      });
      let data;
      try {
        data = await r.json();
      } catch {
        data = {
          detail: `Request failed (${r.status}). Check the API service.`,
        };
      }
      if (!r.ok) {
        throw new Error(
          typeof data.detail === "string"
            ? data.detail
            : JSON.stringify(data.detail || data),
        );
      }
      return data;
    },
    [csrf],
  );
  useEffect(() => {
    if (user && view === "Connections")
      api("/settings/profiles")
        .then(setProfiles)
        .catch((e) => setError(e.message));
  }, [user, view, refresh, api]);
  const run = async (fn: () => Promise<void>) => {
    setBusy(true);
    setError("");
    try {
      await fn();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Something went wrong.");
    } finally {
      setBusy(false);
    }
  };
  const notify = (s: string) => {
    setToast(s);
    setTimeout(() => setToast(""), 5500);
  };
  useEffect(() => {
    fetch("/api/auth/me", { credentials: "include" })
      .then(async (r) => {
        const d = await r.json();
        if (r.ok) {
          setUser(d.user || d);
          setCsrf(d.csrf_token || "");
        }
      })
      .catch(() => {})
      .finally(() => setAuthChecked(true));
    fetch("/api/auth/status")
      .then((r) => (r.ok ? r.json() : {}))
      .then((d: Entity) =>
        setBootstrap(!!(d.setup_required || d.bootstrap_required)),
      )
      .catch(() => {});
  }, []);
  useEffect(() => {
    if (!user) return;
    let active = true;
    setLoading(true);
    Promise.all([
      api("/overview"),
      api("/documents"),
      api("/knowledge-bases"),
      api("/jobs"),
      api("/capabilities"),
      api("/settings"),
      api("/templates"),
      api("/conversations"),
      api("/extractions"),
    ])
      .then(([o, d, k, j, c, s, t, co, e]) => {
        if (!active) return;
        setOverview(o);
        setDocs(Array.isArray(d) ? d : d.documents || []);
        setKbs(Array.isArray(k) ? k : k.knowledge_bases || []);
        setJobs(Array.isArray(j) ? j : j.jobs || []);
        setCaps(c);
        setSettings(s);
        setSettingsForm(s);
        setTemplates(Array.isArray(t) ? t : t.templates || []);
        setConversations(Array.isArray(co) ? co : co.conversations || []);
        setExtractions(Array.isArray(e) ? e : e.extractions || []);
      })
      .catch((e) => active && setError(e.message))
      .finally(() => active && setLoading(false));
    return () => {
      active = false;
    };
  }, [user, refresh, api]);
  useEffect(() => {
    if (!user) return;
    const timer = setInterval(() => {
      api("/jobs")
        .then((d) => {
          const next = Array.isArray(d) ? d : d.jobs || [];
          setJobs(next);
          api("/documents")
            .then((d) => setDocs(Array.isArray(d) ? d : d.documents || []))
            .catch(() => {});
        })
        .catch(() => {});
    }, 6000);
    return () => clearInterval(timer);
  }, [user, api]);
  const navigate = (name: View) => {
    setView(name);
    setError("");
    setMobile(false);
  };
  const externalProvider =
    settings.embedding_provider === "openai" ||
    settings.search_provider === "oci" ||
    settings.storage_provider === "oci";
  const filtered = docs.filter(
    (d) =>
      (!kb || d.kb_id === kb) &&
      d.name.toLowerCase().includes(query.toLowerCase()),
  );
  const selectDoc = (id: string) =>
    setScope((s) => (s.includes(id) ? s.filter((v) => v !== id) : [...s, id]));
  const reload = () => setRefresh((v) => v + 1);
  const authenticate = () =>
    run(async () => {
      if (bootstrap) {
        await api("/auth/setup", "POST", {
          username,
          password,
          bootstrap_token: bootstrapToken,
        });
        setBootstrapToken("");
        setBootstrap(false);
      }
      const d = await api("/auth/login", "POST", { username, password });
      setUser(d.user);
      setCsrf(d.csrf_token || "");
      setPassword("");
    });
  const upload = () =>
    run(async () => {
      if (!files.length) throw new Error("Choose one or more documents first.");
      if (externalProvider && !externalUpload)
        throw new Error(
          "Please approve the external processing notice before uploading.",
        );
      const fd = new FormData();
      files.forEach((f) => fd.append("files", f));
      if (kb) fd.append("kb_id", kb);
      fd.append("allow_external", String(externalUpload));
      await api("/documents/upload", "POST", fd);
      setFiles([]);
      notify(
        "Originals uploaded. Follow their processing status in Jobs & activity.",
      );
      reload();
    });
  const openPreview = (d: Entity) =>
    run(async () =>
      setModal({
        title: d.name,
        data: await api(`/documents/${d.id}/preview`),
      }),
    );
  const docAction = (d: Entity, action: string) => {
    setConfirm({
      title: action === "delete" ? "Delete document?" : "Reindex document?",
      body:
        action === "delete"
          ? `Delete “${d.name}”, its stored original, and its search index? This cannot be undone through Aegis.`
          : `Rebuild the search index for “${d.name}”. Its original stays stored. If an external embedding provider is configured, document content will be sent to that provider and usage may be billed.`,
      action: async () => {
        await api(
          `/documents/${d.id}${action === "delete" ? "" : "/reindex"}`,
          action === "delete" ? "DELETE" : "POST",
          action === "delete" ? undefined : { allow_external: true },
        );
        notify(
          action === "delete" ? "Document deleted." : "Reindex job queued.",
        );
        reload();
      },
    });
  };
  const openConversation = async (id: string) => {
    const d = await api(`/conversations/${id}`);
    setConversation(d);
  };
  const sendMessage = async (text = prompt) => {
    if (!text.trim()) return;
    if (!externalChat) {
      setError("Approve the provider notice before sending a question.");
      return;
    }
    setError("");
    setAnswering(true);
    setLastPrompt(text);
    abort.current = new AbortController();
    try {
      let c = conversation;
      if (!c) {
        c = await api("/conversations", "POST", {
          title: text.slice(0, 70),
          kb_id: kb,
          document_ids: scope,
        });
        setConversation(c);
      }
      setConversation({
        ...c,
        messages: [
          ...(c!.messages || []),
          { id: "pending-user", role: "user", text },
        ],
      });
      setPrompt("");
      const response = await fetch(
        `/api/conversations/${c!.id}/messages/stream`,
        {
          method: "POST",
          credentials: "include",
          headers: { "Content-Type": "application/json", "X-CSRF-Token": csrf },
          body: JSON.stringify({
            text,
            document_ids: scope,
            kb_id: kb,
            allow_external: true,
          }),
          signal: abort.current.signal,
        },
      );
      if (!response.ok) {
        const failure = await response.json();
        throw new Error(failure.detail || "Answer request failed.");
      }
      if (!response.body)
        throw new Error("The server did not return an answer stream.");
      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "",
        answer = "";
      const baseMessages = [
        ...(c!.messages || []),
        { id: "pending-user", role: "user", text },
      ];
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const events = buffer.split("\n\n");
        buffer = events.pop() || "";
        for (const event of events) {
          const type = event
            .split("\n")
            .find((l) => l.startsWith("event:"))
            ?.slice(6)
            .trim();
          const raw = event
            .split("\n")
            .filter((l) => l.startsWith("data:"))
            .map((l) => l.slice(5).trim())
            .join("\n");
          if (!raw) continue;
          const payload = JSON.parse(raw);
          if (type === "error")
            throw new Error(payload.detail || "Answer interrupted.");
          if (type === "delta") {
            answer += payload.text;
            setConversation({
              ...c,
              messages: [
                ...baseMessages,
                {
                  id: "streaming-answer",
                  role: "assistant",
                  text: answer,
                  mock: settings.model_provider === "mock",
                },
              ],
            });
          }
          if (type === "done")
            setConversation({
              ...c,
              messages: [...baseMessages, payload.message],
            });
        }
      }
      await openConversation(c!.id);
      const cs = await api("/conversations");
      setConversations(Array.isArray(cs) ? cs : cs.conversations || []);
    } catch (e) {
      if (e instanceof Error && e.name === "AbortError") {
        setError(
          "Stopped waiting for the answer. Server or provider processing may continue. Refresh this conversation before retrying.",
        );
      } else setError(e instanceof Error ? e.message : "Question failed.");
    } finally {
      setAnswering(false);
    }
  };
  const copy = async (t: string) => {
    try {
      await navigator.clipboard.writeText(t);
      notify("Copied to clipboard.");
    } catch {
      setError("Clipboard is unavailable. Select and copy the text manually.");
    }
  };
  const chooseTemplate = (id: string) => {
    setTemplateId(id);
    const t = templates.find((t) => t.id === id);
    if (t) {
      setTemplateName(t.name);
      setSchema(json(t.schema || t.schema_json || {}));
    }
  };
  const saveTemplate = () =>
    run(async () => {
      let parsed;
      try {
        parsed = JSON.parse(schema);
      } catch {
        throw new Error("The schema must be valid JSON.");
      }
      if (!templateName.trim()) throw new Error("Give the template a name.");
      const d = await api(
        `/templates${templateId ? "/" + templateId : ""}`,
        templateId ? "PUT" : "POST",
        { name: templateName, schema: parsed },
      );
      setTemplateId(d.id);
      notify(`Template saved${d.version ? " · version " + d.version : ""}.`);
      reload();
    });
  const extract = () =>
    run(async () => {
      if (!scope.length || !templateId)
        throw new Error("Select at least one document and a template.");
      if (!externalExtract)
        throw new Error("Approve the external processing notice first.");
      const d = await api("/extractions", "POST", {
        document_ids: scope,
        template_id: templateId,
        allow_external: true,
      });
      setExtraction(d);
      setResultText(json(d.result || {}));
      notify(
        "Extraction submitted. Review the job status before using the result.",
      );
      reload();
    });
  const inspect = () =>
    run(async () => {
      const data = await api(
        `/index${indexDoc ? "?document_id=" + encodeURIComponent(indexDoc) : ""}`,
      );
      setIndexData({
        ...data,
        ...data.settings,
        dimensions: data.documents?.[0]?.dimensions,
        chunks: (data.documents || []).flatMap((d: Entity) =>
          (d.chunks || []).map((c: Entity) => ({
            ...c,
            document_name: d.name,
            document_id: d.id,
            requires_reindex: d.requires_reindex,
          })),
        ),
      });
    });
  const readyCount = docs.filter((d) => d.status === "ready").length;
  const docSelection = (
    <div className="selection">
      {docs.length ? (
        docs.map((d) => (
          <label key={d.id}>
            <input
              type="checkbox"
              checked={scope.includes(d.id)}
              onChange={() => selectDoc(d.id)}
            />
            <span>
              {d.name} <span className="muted">· {d.status}</span>
            </span>
          </label>
        ))
      ) : (
        <p className="small muted">
          Upload documents in the knowledge library first.
        </p>
      )}
    </div>
  );
  const externalNotice = `I approve sending this request and relevant document content to the configured providers: model ${settings.model_provider || "not configured"}, embeddings ${settings.embedding_provider || "not configured"}, search ${settings.search_provider || "not configured"}. OpenAI API and OCI usage are billed separately by those providers; ChatGPT does not cover these charges.`;
  if (!authChecked)
    return (
      <div className="auth-form" style={{ minHeight: "100vh" }}>
        <Loader2 className="animate-spin" size={26} />
      </div>
    );
  if (!user)
    return (
      <div className="auth-shell">
        <section className="auth-brand">
          <div className="brand">
            <span className="brandmark">
              <Shield size={23} />
            </span>
            Aegis
          </div>
          <div className="auth-art">
            <div className="eyebrow" style={{ color: "#90aaff" }}>
              DOCUMENT INTELLIGENCE, GROUNDED.
            </div>
            <h1>
              Your knowledge.
              <br />
              Clear answers.
              <br />A source for each.
            </h1>
            <p>
              A private workspace for document search, grounded conversations,
              and structured extraction. Originals stay safely stored,
              independent of your search index.
            </p>
            <div className="row" style={{ marginTop: 34, color: "#bac8e3" }}>
              <Shield size={18} />
              <span className="small">
                Local-first · Your providers · Your control
              </span>
            </div>
          </div>
          <span className="small" style={{ color: "#7085a7" }}>
            AEGIS / DOCUMENT INTELLIGENCE WORKSPACE
          </span>
        </section>
        <section className="auth-form">
          <div>
            <div className="eyebrow">WELCOME TO AEGIS</div>
            <h1>{bootstrap ? "Create your workspace" : "Welcome back"}</h1>
            <p className="muted" style={{ marginBottom: 30 }}>
              {bootstrap
                ? "Set up your first administrator account."
                : "Sign in to your document intelligence workspace."}
            </p>
            {error && <Notice tone="error">{error}</Notice>}
            <form
              onSubmit={(e) => {
                e.preventDefault();
                authenticate();
              }}
            >
              {bootstrap && (
                <Field
                  label="Bootstrap token"
                  help="Use AEGIS_BOOTSTRAP_TOKEN from your deployment environment."
                >
                  <input
                    aria-label="Bootstrap token"
                    type="password"
                    autoComplete="off"
                    value={bootstrapToken}
                    onChange={(e) => setBootstrapToken(e.target.value)}
                    required
                  />
                </Field>
              )}
              <Field label="Username">
                <input
                  aria-label="Username"
                  autoComplete="username"
                  value={username}
                  onChange={(e) => setUsername(e.target.value)}
                  required
                />
              </Field>
              <Field
                label="Password"
                help={bootstrap ? "Use a strong, unique password." : ""}
              >
                <input
                  aria-label="Password"
                  autoComplete={bootstrap ? "new-password" : "current-password"}
                  type="password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  required
                  minLength={bootstrap ? 12 : 1}
                />
              </Field>
              <button
                className="btn primary"
                type="submit"
                disabled={busy}
                style={{ width: "100%", padding: 13 }}
              >
                {busy ? (
                  <Loader2 size={16} className="animate-spin" />
                ) : (
                  <ArrowRight size={16} />
                )}{" "}
                {bootstrap ? "Create administrator" : "Sign in"}
              </button>
            </form>
            <div className="notice" style={{ marginTop: 26 }}>
              <KeyRound size={17} />
              <div>
                No API key is needed to store documents. Add your own provider
                key in Connections when you’re ready. Keys stay encrypted on the
                server.
              </div>
            </div>
            <button
              className="btn"
              style={{ width: "100%" }}
              onClick={() => {
                setBootstrap(!bootstrap);
                setError("");
              }}
            >
              {bootstrap
                ? "Already configured? Sign in"
                : "First run? Set up administrator"}
            </button>
          </div>
        </section>
      </div>
    );
  return (
    <>
      <aside className={`sidebar ${mobile ? "open" : ""}`}>
        <button
          className="btn icon mobile-close"
          onClick={() => setMobile(false)}
          aria-label="Close navigation"
        >
          <X size={15} />
        </button>
        <div className="brand">
          <span className="brandmark">
            <Shield size={23} />
          </span>
          Aegis
        </div>
        <div className="brand-sub">Document intelligence</div>
        <nav>
          {sections.map((s) => (
            <div key={s.name}>
              {s.group && <div className="nav-label">{s.group}</div>}
              <button
                className={`nav-item ${view === s.name ? "selected" : ""}`}
                onClick={() => navigate(s.name)}
              >
                <s.icon size={17} />
                {s.name}
              </button>
            </div>
          ))}
        </nav>
        <div className="nav-footer">
          <div className="row" style={{ marginBottom: 9 }}>
            <Server size={14} />
            <span>Local workspace</span>
          </div>
          Originals protected. Insights grounded.
        </div>
      </aside>
      <div className="shell">
        <header className="topbar">
          <div className="breadcrumb">
            <button
              className="btn icon menu-toggle"
              onClick={() => setMobile(true)}
              aria-label="Open navigation"
            >
              <Menu size={17} />
            </button>
            <span className="crumb-workspace">Workspace</span>
            <ChevronRight size={13} />
            <span style={{ color: "#2a3b57" }}>{view}</span>
          </div>
          <div className="top-actions">
            <span className="pill">
              <span className="dot" />
              Private workspace
            </span>
            <div className="avatar" title={user.username}>
              {(user.username || "A").slice(0, 2).toUpperCase()}
            </div>
            <button
              className="btn icon"
              title="Sign out"
              aria-label="Sign out"
              onClick={() =>
                run(async () => {
                  await api("/auth/logout", "POST");
                  setUser(null);
                  setCsrf("");
                })
              }
            >
              <LogOut size={14} />
            </button>
          </div>
        </header>
        <main className="workspace">
          <div className="page-head">
            <div>
              <div className="eyebrow">
                {view === "Connections" || view === "Services & migration"
                  ? "CONFIGURE & CONNECT"
                  : "YOUR KNOWLEDGE, WORKING FOR YOU"}
              </div>
              <h1>{view === "Dashboard" ? "Workspace overview" : view}</h1>
              <p className="muted small">{descriptions[view]}</p>
            </div>
            <div className="row">
              <button
                className="btn"
                onClick={reload}
                disabled={loading}
                aria-label="Refresh workspace"
              >
                <RefreshCw
                  size={14}
                  className={loading ? "animate-spin" : ""}
                />
                <span>Refresh</span>
              </button>
              {view === "Dashboard" && (
                <button
                  className="btn primary"
                  onClick={() => navigate("Knowledge library")}
                >
                  <Plus size={15} />
                  Add documents
                </button>
              )}
            </div>
          </div>
          {error && (
            <Notice tone="error">
              {error}
              <button
                className="btn icon"
                onClick={() => setError("")}
                style={{ marginLeft: 12 }}
                aria-label="Dismiss error"
              >
                <X size={12} />
              </button>
            </Notice>
          )}
          {loading && !docs.length && view === "Dashboard" ? (
            <div className="stats">
              {[1, 2, 3, 4].map((n) => (
                <div className="skeleton" key={n} />
              ))}
            </div>
          ) : null}
          {view === "Dashboard" && (
            <>
              <div className="stats">
                {[
                  {
                    label: "Stored documents",
                    value: overview.documents ?? docs.length,
                    icon: FileText,
                    sub: "Originals in durable storage",
                  },
                  {
                    label: "Ready to search",
                    value: overview.ready ?? readyCount,
                    icon: Search,
                    sub: "Processed and indexed",
                  },
                  {
                    label: "Knowledge bases",
                    value:
                      typeof overview.knowledge_bases === "number"
                        ? overview.knowledge_bases
                        : kbs.length,
                    icon: Database,
                    sub: "Organized collections",
                  },
                  {
                    label: "Active jobs",
                    value: jobs.filter((j) =>
                      ["running", "queued", "pending"].includes(j.status),
                    ).length,
                    icon: Activity,
                    sub: "Background processing",
                  },
                ].map((s) => (
                  <div className="stat-card" key={s.label}>
                    <div className="stat-icon">
                      <s.icon size={18} />
                    </div>
                    <div className="stat-label">{s.label}</div>
                    <div className="stat-value">{s.value}</div>
                    <div className="stat-label">{s.sub}</div>
                  </div>
                ))}
              </div>
              <div className="grid2 dashboard-grid">
                <section className="panel">
                  <div className="panel-head">
                    <div>
                      <h2>Recent documents</h2>
                      <p className="muted small">
                        Your latest additions to the workspace
                      </p>
                    </div>
                    <button
                      className="btn"
                      onClick={() => navigate("Knowledge library")}
                    >
                      View library
                      <ArrowRight size={13} />
                    </button>
                  </div>
                  {docs.length ? (
                    <div className="table-scroll">
                      <table>
                        <thead>
                          <tr>
                            <th>Document</th>
                            <th>Status</th>
                            <th>Size</th>
                          </tr>
                        </thead>
                        <tbody>
                          {docs.slice(0, 6).map((d) => (
                            <tr key={d.id}>
                              <td>
                                <button
                                  className="filecell"
                                  style={{
                                    background: "none",
                                    border: 0,
                                    textAlign: "left",
                                  }}
                                  onClick={() => openPreview(d)}
                                >
                                  <span className="file-icon">
                                    <FileText size={16} />
                                  </span>
                                  <span>
                                    {d.name}
                                    <br />
                                    <span
                                      className="muted"
                                      style={{ fontSize: 10 }}
                                    >
                                      {date(d.created_at)}
                                    </span>
                                  </span>
                                </button>
                              </td>
                              <td>
                                <Status value={d.status} />
                              </td>
                              <td className="muted">{byteSize(d.size)}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  ) : (
                    <Empty
                      title="A fresh place for your knowledge"
                      detail="Upload your first document to start building a searchable library."
                    />
                  )}
                </section>
                <section className="panel">
                  <div className="panel-head">
                    <h2>Workspace readiness</h2>
                    <Shield size={18} color="#7d96ce" />
                  </div>
                  {[
                    {
                      title: "Original storage",
                      detail:
                        settings.storage_provider ||
                        settings.storage ||
                        "Local filesystem",
                      ok: docs.length > 0,
                    },
                    {
                      title: "Search index",
                      detail:
                        settings.search_provider ||
                        settings.search ||
                        "Configure in Connections",
                      ok: readyCount > 0,
                    },
                    {
                      title: "Model provider",
                      detail:
                        settings.model_provider ||
                        settings.model ||
                        "Not configured",
                      ok: !!(
                        settings.api_key_configured ||
                        settings.openai_api_key_configured
                      ),
                    },
                  ].map((s) => (
                    <div className="item row" key={s.title}>
                      <div className="file-icon">
                        {s.ok ? (
                          <CheckCircle2 size={16} />
                        ) : (
                          <Settings2 size={16} />
                        )}
                      </div>
                      <div>
                        <h3 style={{ margin: 0 }}>{s.title}</h3>
                        <span className="muted small">{s.detail}</span>
                      </div>
                    </div>
                  ))}
                  <button
                    className="btn"
                    style={{ width: "100%", marginTop: 20 }}
                    onClick={() => navigate("Connections")}
                  >
                    Manage connections
                    <ArrowRight size={13} />
                  </button>
                </section>
              </div>
              <section className="panel">
                <div className="panel-head">
                  <h2>Make more of your documents</h2>
                  <span className="pill">Evidence first</span>
                </div>
                <div className="grid3">
                  {[
                    {
                      name: "Ask your knowledge",
                      text: "Get answers grounded in your selected documents.",
                      view: "Ask Aegis" as View,
                      icon: MessageSquare,
                    },
                    {
                      name: "Extract with structure",
                      text: "Use reusable schemas to bring order to document data.",
                      view: "Extract" as View,
                      icon: FileSearch,
                    },
                    {
                      name: "Inspect the evidence",
                      text: "See the chunks and configuration behind retrieval.",
                      view: "Index inspector" as View,
                      icon: Layers,
                    },
                  ].map((a) => (
                    <button
                      key={a.name}
                      className="btn"
                      style={{
                        padding: 20,
                        whiteSpace: "normal",
                        textAlign: "left",
                        justifyContent: "flex-start",
                      }}
                      onClick={() => navigate(a.view)}
                    >
                      <a.icon size={25} color="#5275d5" />
                      <div>
                        <h3>{a.name}</h3>
                        <span
                          className="muted small"
                          style={{ fontWeight: 400 }}
                        >
                          {a.text}
                        </span>
                      </div>
                    </button>
                  ))}
                </div>
              </section>
            </>
          )}
          {view === "Knowledge library" && (
            <>
              <div className="grid2">
                <section className="panel">
                  <h2>Upload documents</h2>
                  <p className="muted small">
                    PDF, DOCX, and TXT. Originals are stored before processing
                    starts.
                  </p>
                  <div
                    className="dropzone"
                    onDragOver={(e) => e.preventDefault()}
                    onDrop={(e) => {
                      e.preventDefault();
                      setFiles(Array.from(e.dataTransfer.files));
                    }}
                  >
                    <UploadCloud size={29} />
                    <h3>Drop documents here, or choose files</h3>
                    <p className="muted small">
                      {files.length
                        ? `${files.length} file${files.length === 1 ? "" : "s"} selected`
                        : "Choose multiple files to process together"}
                    </p>
                    <input
                      aria-label="Choose documents"
                      type="file"
                      accept=".pdf,.docx,.txt"
                      multiple
                      onChange={(e) =>
                        setFiles(Array.from(e.target.files || []))
                      }
                    />
                  </div>
                  {externalProvider && (
                    <label className="check" style={{ marginBottom: 15 }}>
                      <input
                        type="checkbox"
                        checked={externalUpload}
                        onChange={(e) => setExternalUpload(e.target.checked)}
                      />
                      <span>
                        I approve sending uploaded document text to the
                        configured external storage, search, or embedding
                        provider. API usage may be billed separately.
                      </span>
                    </label>
                  )}
                  <div className="row">
                    <select
                      aria-label="Upload knowledge base"
                      value={kb}
                      onChange={(e) => setKb(e.target.value)}
                    >
                      <option value="">All documents / no collection</option>
                      {kbs.map((k) => (
                        <option key={k.id} value={k.id}>
                          {k.name}
                        </option>
                      ))}
                    </select>
                    <button
                      className="btn primary"
                      onClick={upload}
                      disabled={busy || !files.length}
                    >
                      <UploadCloud size={14} />
                      Upload {files.length || ""}
                    </button>
                  </div>
                </section>
                <section className="panel">
                  <h2>Knowledge bases</h2>
                  <p className="muted small">
                    Organize documents into clear, reusable scopes.
                  </p>
                  <div className="row" style={{ marginTop: 22 }}>
                    <input
                      placeholder="New knowledge base name"
                      aria-label="New knowledge base name"
                      value={newKb}
                      onChange={(e) => setNewKb(e.target.value)}
                    />
                    <button
                      className="btn"
                      disabled={busy || !newKb.trim()}
                      onClick={() =>
                        run(async () => {
                          await api("/knowledge-bases", "POST", {
                            name: newKb,
                            description: "",
                          });
                          setNewKb("");
                          notify("Knowledge base created.");
                          reload();
                        })
                      }
                    >
                      <FolderPlus size={15} />
                      Create
                    </button>
                  </div>
                  {kbs.length ? (
                    kbs.map((k) => (
                      <div className="item row between" key={k.id}>
                        <div className="row">
                          <Database size={17} color="#6d88c4" />
                          <span>{k.name}</span>
                        </div>
                        <span className="pill">
                          {docs.filter((d) => d.kb_id === k.id).length} docs
                        </span>
                      </div>
                    ))
                  ) : (
                    <Empty
                      title="A home for every collection"
                      detail="Create a knowledge base for a team, topic, or project."
                      icon={Database}
                    />
                  )}
                </section>
              </div>
              <section className="panel flush">
                <div className="panel-head" style={{ padding: "20px 20px 0" }}>
                  <div>
                    <h2>Document library</h2>
                    <span className="muted small">
                      {filtered.length} documents · storage and index tracked
                      separately
                    </span>
                  </div>
                  <div style={{ maxWidth: 240 }}>
                    <input
                      value={query}
                      onChange={(e) => setQuery(e.target.value)}
                      placeholder="Search document names…"
                      aria-label="Search documents"
                    />
                  </div>
                </div>
                {filtered.length ? (
                  <div className="table-scroll">
                    <table>
                      <thead>
                        <tr>
                          <th>Document</th>
                          <th>Processing</th>
                          <th>Size</th>
                          <th>Added</th>
                          <th>Actions</th>
                        </tr>
                      </thead>
                      <tbody>
                        {filtered.map((d) => (
                          <tr key={d.id}>
                            <td>
                              <div className="filecell">
                                <span className="file-icon">
                                  <FileText size={16} />
                                </span>
                                <div>
                                  {d.name}
                                  {d.error && (
                                    <div
                                      className="small"
                                      style={{
                                        color: "#b54a5a",
                                        maxWidth: 270,
                                      }}
                                    >
                                      {d.error}
                                    </div>
                                  )}
                                </div>
                              </div>
                            </td>
                            <td>
                              <Status value={d.status} />
                            </td>
                            <td className="muted">{byteSize(d.size)}</td>
                            <td className="muted">{date(d.created_at)}</td>
                            <td>
                              <div className="row" style={{ gap: 6 }}>
                                <button
                                  className="btn icon"
                                  title="Preview document"
                                  onClick={() => openPreview(d)}
                                >
                                  <Search size={14} />
                                </button>
                                <a
                                  className="btn icon"
                                  title="Download original"
                                  href={`/api/documents/${d.id}/download`}
                                >
                                  <ArrowDownToLine size={14} />
                                </a>
                                <button
                                  className="btn icon"
                                  title="Reindex document"
                                  onClick={() => docAction(d, "reindex")}
                                >
                                  <RefreshCw size={14} />
                                </button>
                                <button
                                  className="btn icon danger"
                                  title="Delete document"
                                  onClick={() => docAction(d, "delete")}
                                >
                                  <Trash2 size={14} />
                                </button>
                              </div>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                ) : (
                  <Empty
                    title="No documents here yet"
                    detail="Upload a document above, or select another collection."
                  />
                )}
              </section>
            </>
          )}
          {view === "Ask Aegis" && (
            <div className="chat-layout">
              <aside>
                <section className="panel">
                  <button
                    className="btn primary"
                    style={{ width: "100%", marginBottom: 20 }}
                    onClick={() => {
                      setConversation(null);
                      setPrompt("");
                      setError("");
                    }}
                  >
                    <Plus size={15} />
                    New conversation
                  </button>
                  <div className="eyebrow" style={{ fontSize: 9 }}>
                    SAVED CONVERSATIONS
                  </div>
                  <div className="chat-list">
                    {conversations.length ? (
                      conversations.map((c) => (
                        <button
                          key={c.id}
                          className={
                            conversation?.id === c.id ? "selected" : ""
                          }
                          onClick={() => run(() => openConversation(c.id))}
                        >
                          {c.title || "Untitled conversation"}
                        </button>
                      ))
                    ) : (
                      <p className="muted small">
                        Your conversations will appear here.
                      </p>
                    )}
                  </div>
                </section>
                <section className="panel">
                  <h3>Knowledge scope</h3>
                  <p className="muted small">
                    No selection searches all accessible documents in the
                    selected base.
                  </p>
                  <select
                    aria-label="Chat knowledge base"
                    value={kb}
                    onChange={(e) => setKb(e.target.value)}
                    style={{ marginBottom: 14 }}
                  >
                    <option value="">All knowledge bases</option>
                    {kbs.map((k) => (
                      <option value={k.id} key={k.id}>
                        {k.name}
                      </option>
                    ))}
                  </select>
                  {docSelection}
                </section>
              </aside>
              <section className="panel chat-window">
                <div className="panel-head">
                  <div>
                    <h2>{conversation?.title || "Ask your knowledge"}</h2>
                    <span className="small muted">
                      {scope.length
                        ? `${scope.length} selected documents`
                        : "All documents"}{" "}
                      · source-grounded answers
                    </span>
                  </div>
                  {conversation?.id && (
                    <div className="row">
                      <button
                        className="btn icon"
                        title="Reload conversation"
                        onClick={() =>
                          run(() => openConversation(conversation.id))
                        }
                      >
                        <RefreshCw size={14} />
                      </button>
                      <Download
                        path={`/conversations/${conversation.id}/export`}
                      >
                        Export
                      </Download>
                    </div>
                  )}
                </div>
                <div className="chat-messages" aria-live="polite">
                  {conversation?.messages?.length ? (
                    conversation.messages.map((m: Entity, i: number) => (
                      <article
                        key={m.id || i}
                        className={`message ${m.role === "user" ? "user" : ""}`}
                      >
                        <div className="message-label">
                          {m.mock && (
                            <span className="pill amber">MOCK TEST OUTPUT</span>
                          )}{" "}
                          {m.role === "user" ? "You" : "Aegis"}
                        </div>
                        <div style={{ whiteSpace: "pre-wrap" }}>
                          {m.text || m.content}
                        </div>
                        {m.citations?.map((c: Entity, n: number) => (
                          <button
                            className="citation"
                            key={n}
                            onClick={() =>
                              setModal({
                                title:
                                  c.document_name ||
                                  c.name ||
                                  `Source ${n + 1}`,
                                data: c,
                              })
                            }
                          >
                            <div className="row">
                              <FileText size={13} />
                              <strong>
                                [{n + 1}]{" "}
                                {c.document_name ||
                                  c.name ||
                                  c.document_id ||
                                  "Source document"}
                              </strong>
                            </div>
                            {c.excerpt || c.text || c.chunk_text}
                          </button>
                        ))}
                        {m.role !== "user" && (
                          <div className="row" style={{ marginTop: 14 }}>
                            <button
                              className="btn icon"
                              title="Copy answer"
                              onClick={() => copy(m.text || m.content || "")}
                            >
                              <Copy size={12} />
                            </button>
                            <button
                              className="btn icon"
                              title="Helpful answer"
                              onClick={() =>
                                run(async () => {
                                  await api(
                                    `/messages/${m.id}/feedback`,
                                    "POST",
                                    { rating: "up" },
                                  );
                                  notify("Feedback saved.");
                                })
                              }
                            >
                              <ThumbsUp size={12} />
                            </button>
                            <button
                              className="btn icon"
                              title="Unhelpful answer"
                              onClick={() =>
                                run(async () => {
                                  await api(
                                    `/messages/${m.id}/feedback`,
                                    "POST",
                                    { rating: "down" },
                                  );
                                  notify("Feedback saved.");
                                })
                              }
                            >
                              <ThumbsDown size={12} />
                            </button>
                          </div>
                        )}
                      </article>
                    ))
                  ) : (
                    <Empty
                      icon={MessageSquare}
                      title="Good questions start with good sources"
                      detail="Select your knowledge scope and ask about a document, a decision, or a detail."
                    />
                  )}
                  {answering && (
                    <div className="row muted small">
                      <Loader2 size={15} className="animate-spin" />
                      Retrieving evidence and generating an answer…
                    </div>
                  )}
                </div>
                <label className="check" style={{ marginBottom: 13 }}>
                  <input
                    type="checkbox"
                    checked={externalChat}
                    onChange={(e) => setExternalChat(e.target.checked)}
                  />
                  <span className="muted" style={{ fontSize: 10 }}>
                    {externalNotice}
                  </span>
                </label>
                <form
                  className="composer"
                  onSubmit={(e) => {
                    e.preventDefault();
                    sendMessage();
                  }}
                >
                  <textarea
                    aria-label="Ask a question"
                    placeholder="Ask a question about your documents…"
                    value={prompt}
                    onChange={(e) => setPrompt(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === "Enter" && !e.shiftKey) {
                        e.preventDefault();
                        if (!answering) sendMessage();
                      }
                    }}
                  />
                  <div className="row between">
                    <span className="small muted">
                      Check cited sources before relying on an answer.
                    </span>
                    <div className="row">
                      {lastPrompt && !answering && (
                        <button
                          type="button"
                          className="btn"
                          onClick={() => sendMessage(lastPrompt)}
                        >
                          <RefreshCw size={13} />
                          Retry
                        </button>
                      )}
                      {answering ? (
                        <button
                          type="button"
                          className="btn"
                          onClick={() => abort.current?.abort()}
                        >
                          <Square size={13} />
                          Stop
                        </button>
                      ) : (
                        <button
                          type="submit"
                          className="btn primary"
                          disabled={!prompt.trim() || !externalChat}
                        >
                          <Send size={14} />
                          Send
                        </button>
                      )}
                    </div>
                  </div>
                </form>
              </section>
            </div>
          )}
          {view === "Extract" && (
            <>
              <div className="grid2">
                <section className="panel">
                  <h2>Create an extraction</h2>
                  <p className="muted small">
                    Select a schema and documents. Review extracted values and
                    their evidence.
                  </p>
                  <Field label="Extraction template">
                    <select
                      aria-label="Extraction template"
                      value={templateId}
                      onChange={(e) => chooseTemplate(e.target.value)}
                    >
                      <option value="">Select a template</option>
                      {templates.map((t) => (
                        <option key={t.id} value={t.id}>
                          {t.name} · v{t.version || 1}
                        </option>
                      ))}
                    </select>
                  </Field>
                  <Field label="Source documents">{docSelection}</Field>
                  <label className="check" style={{ marginBottom: 20 }}>
                    <input
                      type="checkbox"
                      checked={externalExtract}
                      onChange={(e) => setExternalExtract(e.target.checked)}
                    />
                    <span className="muted small">{externalNotice}</span>
                  </label>
                  <button
                    className="btn primary"
                    disabled={
                      busy || !externalExtract || !templateId || !scope.length
                    }
                    onClick={extract}
                  >
                    <Play size={14} />
                    Run extraction
                  </button>
                </section>
                <section className="panel">
                  <div className="panel-head">
                    <h2>Extraction history</h2>
                    <span className="pill">{extractions.length} runs</span>
                  </div>
                  {extractions.length ? (
                    extractions.map((e) => (
                      <div className="item row between" key={e.id}>
                        <div>
                          <h3>
                            {templates.find((t) => t.id === e.template_id)
                              ?.name ||
                              e.template_name ||
                              e.name ||
                              "Extraction"}
                          </h3>
                          <span className="muted small">
                            {date(e.created_at)}
                          </span>
                        </div>
                        <div className="row">
                          <Status value={e.status} />
                          <button
                            className="btn"
                            onClick={() =>
                              run(async () => {
                                const d = await api(`/extractions/${e.id}`);
                                setExtraction(d);
                                setResultText(json(d.result || {}));
                              })
                            }
                          >
                            Review
                          </button>
                        </div>
                      </div>
                    ))
                  ) : (
                    <Empty
                      icon={FileSearch}
                      title="From documents to structured data"
                      detail="Your extraction runs will appear here."
                    />
                  )}
                </section>
              </div>
              {extraction && (
                <section className="panel">
                  <div className="panel-head">
                    <div>
                      <h2>Review extraction</h2>
                      <p className="small muted">
                        Review all values against the source before exporting.
                        Edits are saved to this result.
                      </p>
                    </div>
                    <div className="row">
                      <Status value={extraction.status} />
                      <button
                        className="btn icon"
                        title="Reload extraction"
                        onClick={() =>
                          run(async () => {
                            const d = await api(
                              `/extractions/${extraction.id}`,
                            );
                            setExtraction(d);
                            setResultText(json(d.result || {}));
                          })
                        }
                      >
                        <RefreshCw size={14} />
                      </button>
                      <Download
                        path={`/extractions/${extraction.id}/export?format=json`}
                      >
                        JSON
                      </Download>
                      <Download
                        path={`/extractions/${extraction.id}/export?format=csv`}
                      >
                        CSV
                      </Download>
                    </div>
                  </div>
                  {extraction.mock && (
                    <Notice tone="warn">
                      MOCK TEST OUTPUT · Synthetic development data, not model
                      extraction. Review against the original source.
                    </Notice>
                  )}
                  {extraction.error && (
                    <Notice tone="error">{extraction.error}</Notice>
                  )}
                  <textarea
                    className="mono"
                    style={{ minHeight: 280 }}
                    aria-label="Extraction result JSON"
                    value={resultText}
                    onChange={(e) => setResultText(e.target.value)}
                  />
                  {(extraction.evidence ||
                    extraction.citations ||
                    extraction.sources) && (
                    <details style={{ marginTop: 15 }}>
                      <summary>Source evidence</summary>
                      <pre className="code mono">
                        {json({
                          field_evidence: extraction.evidence || [],
                          sources:
                            extraction.citations || extraction.sources || [],
                        })}
                      </pre>
                    </details>
                  )}
                  <button
                    className="btn primary"
                    style={{ marginTop: 16 }}
                    disabled={busy}
                    onClick={() =>
                      run(async () => {
                        const result = JSON.parse(resultText);
                        const d = await api(
                          `/extractions/${extraction.id}`,
                          "PATCH",
                          { result },
                        );
                        setExtraction(d);
                        notify("Reviewed result saved.");
                        reload();
                      })
                    }
                  >
                    <Check size={14} />
                    Save reviewed result
                  </button>
                </section>
              )}
            </>
          )}
          {view === "Templates" && (
            <div className="grid2">
              <section className="panel">
                <div className="panel-head">
                  <h2>Extraction schemas</h2>
                  <button
                    className="btn"
                    onClick={() => {
                      setTemplateId("");
                      setTemplateName("");
                      setSchema(
                        json({
                          type: "object",
                          properties: {},
                          required: [],
                          additionalProperties: false,
                        }),
                      );
                    }}
                  >
                    <Plus size={14} />
                    New template
                  </button>
                </div>
                {templates.length ? (
                  templates.map((t) => (
                    <div className="item row between" key={t.id}>
                      <div>
                        <h3>{t.name}</h3>
                        <span className="muted small">
                          Version {t.version || 1} ·{" "}
                          {date(t.updated_at || t.created_at)}
                        </span>
                      </div>
                      <div className="row">
                        <button
                          className="btn"
                          onClick={() =>
                            run(async () => {
                              const versions = await api(
                                `/templates/${t.id}/versions`,
                              );
                              setModal({
                                title: `${t.name} · version history`,
                                data: { versions },
                              });
                            })
                          }
                        >
                          Versions
                        </button>
                        <button
                          className="btn"
                          onClick={() => chooseTemplate(t.id)}
                        >
                          Edit
                        </button>
                      </div>
                    </div>
                  ))
                ) : (
                  <Empty
                    icon={FileJson}
                    title="Reusable structure, consistent results"
                    detail="Create a template to define what Aegis should extract."
                  />
                )}
                <Notice>
                  Use JSON Schema to define field names, types, required fields,
                  nested objects, and arrays. Saving an existing template
                  creates a new version.
                </Notice>
              </section>
              <section className="panel">
                <h2>{templateId ? "Edit template" : "New template"}</h2>
                <Field label="Template name">
                  <input
                    aria-label="Template name"
                    placeholder="e.g. Invoice summary"
                    value={templateName}
                    onChange={(e) => setTemplateName(e.target.value)}
                  />
                </Field>
                <Field
                  label="JSON Schema"
                  help="Supported structure is validated by the server before saving. Use additionalProperties: false on every object and mark every property required. Use nullable types for values that may be missing."
                >
                  <textarea
                    className="mono"
                    aria-label="Template JSON schema"
                    style={{ minHeight: 340 }}
                    value={schema}
                    onChange={(e) => setSchema(e.target.value)}
                  />
                </Field>
                <div className="row">
                  <button
                    className="btn primary"
                    disabled={busy}
                    onClick={saveTemplate}
                  >
                    <Check size={14} />
                    Save {templateId ? "new version" : "template"}
                  </button>
                  <button
                    className="btn"
                    disabled={!templateId}
                    onClick={() => navigate("Extract")}
                  >
                    <Play size={14} />
                    Test with documents
                  </button>
                </div>
              </section>
            </div>
          )}
          {view === "Index inspector" && (
            <>
              <section className="panel">
                <div className="row">
                  <select
                    aria-label="Document to inspect"
                    value={indexDoc}
                    onChange={(e) => setIndexDoc(e.target.value)}
                  >
                    <option value="">All documents</option>
                    {docs.map((d) => (
                      <option key={d.id} value={d.id}>
                        {d.name}
                      </option>
                    ))}
                  </select>
                  <button
                    className="btn primary"
                    disabled={busy}
                    onClick={inspect}
                  >
                    <Search size={14} />
                    Inspect index
                  </button>
                </div>
              </section>
              <div className="stats">
                {[
                  {
                    label: "Embedding provider",
                    value:
                      indexData.embedding_provider ||
                      settings.embedding_provider ||
                      settings.embedding ||
                      "Not set",
                  },
                  {
                    label: "Vector dimensions",
                    value:
                      indexData.dimensions ||
                      indexData.embedding_dimensions ||
                      "—",
                  },
                  {
                    label: "Chunk size",
                    value: indexData.chunk_size || settings.chunk_size || "—",
                  },
                  {
                    label: "Chunk overlap",
                    value:
                      indexData.chunk_overlap ?? settings.chunk_overlap ?? "—",
                  },
                ].map((s) => (
                  <div className="stat-card" key={s.label}>
                    <div className="stat-label">{s.label}</div>
                    <div
                      style={{ fontSize: 20, fontWeight: 650, marginTop: 9 }}
                    >
                      {s.value}
                    </div>
                  </div>
                ))}
              </div>
              <section className="panel">
                <div className="panel-head">
                  <div>
                    <h2>Retrieval diagnostics</h2>
                    <p className="muted small">
                      Test source retrieval without generating an answer. Uses
                      the document selection above.
                    </p>
                  </div>
                  <Search size={18} color="#718bc6" />
                </div>
                <Field label="Diagnostic query">
                  <input
                    aria-label="Diagnostic query"
                    value={retrievalQuery}
                    onChange={(e) => setRetrievalQuery(e.target.value)}
                    placeholder="Which passages discuss the payment terms?"
                  />
                </Field>
                <label className="check" style={{ marginBottom: 15 }}>
                  <input
                    type="checkbox"
                    checked={retrievalConsent}
                    onChange={(e) => setRetrievalConsent(e.target.checked)}
                  />
                  <span className="small muted">
                    I approve sending this query to the configured embedding and
                    search providers when external retrieval is enabled (OpenAI
                    embeddings or OCI search). Provider usage may be billed.
                  </span>
                </label>
                <button
                  className="btn primary"
                  disabled={busy || !retrievalQuery.trim() || !retrievalConsent}
                  onClick={() =>
                    run(async () =>
                      setRetrievalResult(
                        await api("/index/search", "POST", {
                          text: retrievalQuery,
                          document_ids: indexDoc ? [indexDoc] : [],
                          allow_external: true,
                        }),
                      ),
                    )
                  }
                >
                  <Search size={14} />
                  Test retrieval
                </button>
                {retrievalResult && (
                  <div style={{ marginTop: 20 }}>
                    <div className="row wrap" style={{ marginBottom: 15 }}>
                      <span className="pill">
                        {retrievalResult.count} matches
                      </span>
                      <span className="pill">
                        {retrievalResult.duration_ms} ms
                      </span>
                      <span className="pill">{retrievalResult.provider}</span>
                      <span className="muted small">
                        {retrievalResult.ready_documents} ready /{" "}
                        {retrievalResult.scoped_documents} scoped documents
                      </span>
                    </div>
                    {retrievalResult.matches?.map((m: Entity, i: number) => (
                      <button
                        key={m.chunk_id || i}
                        className="citation"
                        onClick={() =>
                          setModal({
                            title: m.document_name || "Retrieved source",
                            data: m,
                          })
                        }
                      >
                        <div className="row between">
                          <strong>
                            {m.document_name} {m.page ? `· page ${m.page}` : ""}
                          </strong>
                          <span>
                            Score{" "}
                            {typeof m.score === "number"
                              ? m.score.toFixed(4)
                              : "—"}
                          </span>
                        </div>
                        <p style={{ margin: "8px 0 0" }}>
                          {m.excerpt || m.text}
                        </p>
                      </button>
                    ))}
                    {!retrievalResult.count && (
                      <Empty
                        icon={Search}
                        title="No matching evidence"
                        detail="Check document readiness, scope, and your query."
                      />
                    )}
                    <p className="muted small">{retrievalResult.note}</p>
                  </div>
                )}
              </section>
              <section className="panel">
                <div className="panel-head">
                  <h2>Indexed chunks</h2>
                  <span className="pill">
                    {indexData.chunks?.length || 0} shown
                  </span>
                </div>
                {indexData.chunks?.length ? (
                  indexData.chunks.map((c: Entity, i: number) => (
                    <div className="item" key={c.id || i}>
                      <div className="row between">
                        <h3>Chunk {c.chunk_index ?? c.index ?? i + 1}</h3>
                        <span className="small muted">
                          {c.document_name || c.document_id}{" "}
                          {c.page ? `· page ${c.page}` : ""}
                        </span>
                      </div>
                      <>
                        {c.requires_reindex && (
                          <span className="pill amber">Reindex required</span>
                        )}
                        <pre className="code mono">{c.text || c.content}</pre>
                      </>
                    </div>
                  ))
                ) : (
                  <Empty
                    icon={Layers}
                    title="Look beneath the answer"
                    detail="Choose a document and inspect its chunks, embedding configuration, and diagnostics."
                  />
                )}
                {Object.keys(indexData).length > 0 && (
                  <details style={{ marginTop: 20 }}>
                    <summary>Full index and retrieval diagnostics</summary>
                    <pre className="code mono">{json(indexData)}</pre>
                  </details>
                )}
              </section>
            </>
          )}
          {view === "Jobs & activity" && (
            <section className="panel flush">
              <div className="panel-head" style={{ padding: "22px 22px 0" }}>
                <div>
                  <h2>Processing activity</h2>
                  <p className="muted small">
                    Automatically refreshes every 6 seconds. Failed work never
                    changes the stored original.
                  </p>
                </div>
                <span className="pill">{jobs.length} jobs</span>
              </div>
              {jobs.length ? (
                <div className="table-scroll">
                  <table>
                    <thead>
                      <tr>
                        <th>Job / document</th>
                        <th>Status</th>
                        <th>Progress</th>
                        <th>Attempts</th>
                        <th>Created</th>
                        <th>Actions</th>
                      </tr>
                    </thead>
                    <tbody>
                      {jobs.map((j) => (
                        <tr key={j.id}>
                          <td>
                            <strong>
                              {(j.kind || j.type || "Processing").replaceAll(
                                "_",
                                " ",
                              )}
                            </strong>
                            <div className="muted" style={{ marginTop: 5 }}>
                              {docs.find((d) => d.id === j.document_id)?.name ||
                                j.document_id ||
                                j.id}
                            </div>
                            {j.error && (
                              <div
                                style={{
                                  color: "#ae4a5b",
                                  fontSize: 11,
                                  maxWidth: 360,
                                  marginTop: 6,
                                }}
                              >
                                {j.error}
                              </div>
                            )}
                          </td>
                          <td>
                            <Status value={j.status} />
                          </td>
                          <td style={{ minWidth: 100 }}>
                            {Math.round(j.progress || 0)}%
                            <div className="progress">
                              <span
                                style={{
                                  width: `${Math.min(100, j.progress || 0)}%`,
                                }}
                              />
                            </div>
                          </td>
                          <td>{j.attempts || 0}</td>
                          <td className="muted">{date(j.created_at)}</td>
                          <td>
                            <div className="row">
                              {["failed", "cancelled"].includes(j.status) && (
                                <button
                                  className="btn"
                                  disabled={busy}
                                  onClick={() =>
                                    run(async () => {
                                      await api(`/jobs/${j.id}/retry`, "POST");
                                      notify("Retry requested.");
                                      reload();
                                    })
                                  }
                                >
                                  <RefreshCw size={13} />
                                  Retry
                                </button>
                              )}
                              {["pending", "queued", "running"].includes(
                                j.status,
                              ) && (
                                <button
                                  className="btn danger"
                                  disabled={busy}
                                  onClick={() =>
                                    setConfirm({
                                      title: "Cancel processing job?",
                                      body: "Cancellation is best-effort. A request already sent to a model provider may continue and incur usage charges.",
                                      action: async () => {
                                        await api(
                                          `/jobs/${j.id}/cancel`,
                                          "POST",
                                        );
                                        notify("Cancellation requested.");
                                        reload();
                                      },
                                    })
                                  }
                                >
                                  <Square size={13} />
                                  Cancel
                                </button>
                              )}
                            </div>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : (
                <Empty
                  icon={Activity}
                  title="No processing jobs yet"
                  detail="Document uploads, reindexing, and extractions will be tracked here."
                />
              )}
            </section>
          )}
          {view === "Connections" && (
            <>
              <Notice tone="warn">
                Provider keys are encrypted on the server and never saved in
                browser storage. OpenAI usage is separate from a ChatGPT
                subscription. Changing an embedding model requires reindexing
                existing documents.
              </Notice>
              <section className="panel">
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
                  <button
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
                  >
                    <Plus size={14} />
                    Save current profile
                  </button>
                </div>
                {profiles.length ? (
                  profiles.map((p) => (
                    <div className="item row between wrap" key={p.id}>
                      <div>
                        <h3>{p.name}</h3>
                        <span className="muted small">
                          Version {p.version} · {date(p.created_at)} ·{" "}
                          {p.api_key_configured || p.oci_api_key_configured
                            ? "Encrypted credentials saved"
                            : "No provider key saved"}
                        </span>
                      </div>
                      <div className="row wrap">
                        <button
                          className="btn"
                          disabled={busy}
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
                                setExternalChat(false);
                                setExternalExtract(false);
                                setExternalUpload(false);
                                setRetrievalConsent(false);
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
                        <button
                          className="btn"
                          disabled={busy}
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
                        >
                          Save new version
                        </button>
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
              <div className="grid2">
                <section className="panel">
                  <div className="panel-head">
                    <h2>Model & embedding providers</h2>
                    <span className="pill">Server-side configuration</span>
                  </div>
                  <Field label="Answer and extraction provider">
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
                      <option value="openai">OpenAI</option>
                      <option value="oci">
                        OCI Generative AI · requires validation
                      </option>
                      <option value="mock">
                        Mock · explicit development test mode
                      </option>
                    </select>
                  </Field>
                  <Field label="Answer model">
                    <input
                      aria-label="Answer model"
                      value={settingsForm.model || ""}
                      onChange={(e) =>
                        setSettingsForm({
                          ...settingsForm,
                          model: e.target.value,
                        })
                      }
                      placeholder="gpt-4.1-mini"
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
                      <option value="openai">OpenAI</option>
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
                      settings.api_key_configured
                        ? "A key is configured. Leave blank to keep it unchanged."
                        : "No key configured. Enter your own provider key; it is encrypted by the server."
                    }
                  >
                    <input
                      aria-label="OpenAI API key"
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
                <section className="panel">
                  <h2>Storage & retrieval</h2>
                  <Field label="Original document storage">
                    <select
                      aria-label="Storage provider"
                      value={settingsForm.storage_provider || "local"}
                      onChange={(e) =>
                        setSettingsForm({
                          ...settingsForm,
                          storage_provider: e.target.value,
                        })
                      }
                    >
                      <option value="local">Local durable volume</option>
                      <option value="oci">
                        OCI Object Storage · requires validation
                      </option>
                    </select>
                  </Field>
                  <Field label="Search provider">
                    <select
                      aria-label="Search provider"
                      value={settingsForm.search_provider || "qdrant"}
                      onChange={(e) =>
                        setSettingsForm({
                          ...settingsForm,
                          search_provider: e.target.value,
                        })
                      }
                    >
                      <option value="qdrant">Qdrant</option>
                      <option value="local">Local exact vector search</option>
                      <option value="oci">
                        OCI managed vector store · requires validation
                      </option>
                    </select>
                  </Field>
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
                  <div className="row wrap">
                    <button
                      className="btn primary"
                      disabled={busy}
                      onClick={() =>
                        run(async () => {
                          const allowed = [
                            "storage_provider",
                            "search_provider",
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
                            "oci_storage_namespace",
                            "oci_storage_bucket",
                            "oci_storage_prefix",
                            "oci_storage_region",
                            "oci_storage_auth_mode",
                            "oci_storage_profile",
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
                    >
                      <Check size={14} />
                      Save settings
                    </button>
                    <button
                      className="btn"
                      disabled={busy}
                      onClick={() =>
                        run(async () => {
                          setTestResult(await api("/settings/test", "POST"));
                        })
                      }
                    >
                      <Activity size={14} />
                      Test saved connections
                    </button>
                    <Download path="/settings/export">
                      Export safe config
                    </Download>
                  </div>
                </section>
              </div>
              <section className="panel">
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
                {settingsForm.storage_provider === "oci" && (
                  <>
                    <h3>Object Storage destination</h3>
                    <Notice tone="warn">
                      Changing an existing workspace’s storage destination
                      requires a stopped-application migration. Never change
                      buckets or prefixes without transferring and validating
                      stored objects.
                    </Notice>
                    <div className="grid3">
                      {[
                        {
                          key: "oci_storage_namespace",
                          label: "Storage namespace",
                        },
                        { key: "oci_storage_bucket", label: "Storage bucket" },
                        {
                          key: "oci_storage_prefix",
                          label: "Storage key prefix",
                        },
                        { key: "oci_storage_region", label: "Storage region" },
                        {
                          key: "oci_storage_profile",
                          label: "Storage SDK profile",
                        },
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
                      <Field label="Storage authentication">
                        <select
                          aria-label="Storage authentication"
                          value={
                            settingsForm.oci_storage_auth_mode || "config_file"
                          }
                          onChange={(e) =>
                            setSettingsForm({
                              ...settingsForm,
                              oci_storage_auth_mode: e.target.value,
                            })
                          }
                        >
                          <option value="config_file">
                            Server-mounted OCI config
                          </option>
                          <option value="instance_principal">
                            Instance principal
                          </option>
                          <option value="resource_principal">
                            Resource principal
                          </option>
                        </select>
                      </Field>
                    </div>
                  </>
                )}
                <p className="muted small">
                  Use Save settings above to save this profile. Do not paste
                  private keys, tokens, or signing credentials into these
                  fields.
                </p>
              </section>
              {testResult && (
                <section className="panel">
                  <h2>Connection test result</h2>
                  <pre className="code mono">{json(testResult)}</pre>
                </section>
              )}
              <section className="panel">
                <h2>Provider capabilities</h2>
                <p className="muted small">
                  Readiness is reported by the server; an unavailable adapter
                  cannot process your data.
                </p>
                <pre className="code mono">{json(caps)}</pre>
              </section>
            </>
          )}
          {view === "Services & migration" && (
            <>
              <Notice>
                Local storage and the search index are separate. Back up the
                stored originals, database, and encryption key before moving
                environments. A search index can be rebuilt; a lost original or
                encryption key cannot.
              </Notice>
              <div className="grid3">
                {[
                  {
                    name: "Local deployment",
                    icon: Server,
                    state: "available",
                    text: "Next.js frontend, Python API, durable local volumes, and configurable vector search.",
                  },
                  {
                    name: "OpenAI models",
                    icon: MessageSquare,
                    state: settings.api_key_configured
                      ? "configured"
                      : "setup required",
                    text: "Bring your own API key. Content is sent only with explicit external processing approval.",
                  },
                  {
                    name: "OCI migration",
                    icon: Cloud,
                    state: "unverified",
                    text: "Storage, model, and managed vector adapters are implemented. Live tenancy validation is still required before production use.",
                  },
                ].map((s) => (
                  <section className="panel" key={s.name}>
                    <s.icon
                      size={25}
                      color="#5e7ed2"
                      style={{ marginBottom: 20 }}
                    />
                    <div className="row between">
                      <h2>{s.name}</h2>
                      <Status value={s.state} />
                    </div>
                    <p
                      className="muted small"
                      style={{ lineHeight: 1.8, marginTop: 13 }}
                    >
                      {s.text}
                    </p>
                  </section>
                ))}
              </div>
              <div className="grid2">
                <section className="panel">
                  <h2>Migration checklist</h2>
                  <p className="muted small">
                    Validate each layer before changing the active provider.
                  </p>
                  {[
                    {
                      title: "Create a verified backup",
                      text: "Stop writes and back up the persistent data volume, originals, database, and encryption key. Test a restore in a separate environment.",
                    },
                    {
                      title: "Provision the destination",
                      text: "Confirm OCI region, compartment permissions, Object Storage, model availability, and the supported vector-search service.",
                    },
                    {
                      title: "Validate the cloud adapters",
                      text: "Verify authentication, storage reads and writes, retries, timeouts, vector dimensions, and model limits. Adapter tests do not substitute for a live tenancy round-trip.",
                    },
                    {
                      title: "Copy originals and metadata",
                      text: "Keep document identifiers stable and compare object checksums. Never delete local originals before validating the destination.",
                    },
                    {
                      title: "Rebuild and compare indexes",
                      text: "Reindex when the embedding provider, model, dimensions, or chunk strategy changes. Run known queries and inspect their evidence.",
                    },
                    {
                      title: "Switch with a rollback plan",
                      text: "Run a canary workload, compare answers and extraction results, then switch providers. Retain the tested backup and prior configuration.",
                    },
                  ].map((s, i) => (
                    <div
                      className="item row"
                      style={{ alignItems: "flex-start" }}
                      key={s.title}
                    >
                      <span className="stepnum">{i + 1}</span>
                      <div>
                        <h3>{s.title}</h3>
                        <p className="muted small" style={{ lineHeight: 1.8 }}>
                          {s.text}
                        </p>
                      </div>
                    </div>
                  ))}
                </section>
                <section className="panel">
                  <h2>Operational boundaries</h2>
                  <div className="item">
                    <h3>Storage-first ingestion</h3>
                    <p className="muted small">
                      A failed embedding or indexing job leaves the original
                      stored. Retry from Jobs & activity after fixing the
                      provider.
                    </p>
                  </div>
                  <div className="item">
                    <h3>Independent cloud billing</h3>
                    <p className="muted small">
                      OpenAI API and OCI service charges are billed by those
                      providers. A ChatGPT plan does not include this
                      application’s API usage.
                    </p>
                  </div>
                  <div className="item">
                    <h3>No silent provider fallbacks</h3>
                    <p className="muted small">
                      Unavailable model and cloud adapters report a clear error.
                      Mock mode must be selected explicitly for development
                      tests.
                    </p>
                  </div>
                  <div className="item">
                    <h3>Backups and restore</h3>
                    <p className="muted small">
                      Use the repository deployment guide and backup scripts.
                      Configuration export is sanitized and is not a complete
                      data backup.
                    </p>
                    <Download path="/settings/export">
                      Export sanitized settings
                    </Download>
                  </div>
                  <div className="item">
                    <h3>Live readiness report</h3>
                    <pre className="code mono">{json(caps)}</pre>
                  </div>
                </section>
              </div>
            </>
          )}
          {view === "Setup" && (
            <>
              <section className="panel">
                <div className="panel-head">
                  <div>
                    <h2>A considered start</h2>
                    <p className="muted small">
                      Your workspace is ready for storage. Configure
                      intelligence when you need it.
                    </p>
                  </div>
                  <span className="pill green">
                    <Check size={12} />
                    Administrator signed in
                  </span>
                </div>
                {[
                  {
                    title: "Administrator account",
                    text: `Signed in as ${user.username}. Authentication uses an HttpOnly session cookie.`,
                    action: "Account configured",
                    to: "Setup" as View,
                  },
                  {
                    title: "Connect your providers",
                    text: "Choose local embeddings or add your own OpenAI key. Keys stay encrypted on the server.",
                    action: "Configure connections",
                    to: "Connections" as View,
                  },
                  {
                    title: "Build your knowledge library",
                    text: "Upload PDF, DOCX, and TXT files. Verify the original and processing status separately.",
                    action: "Add documents",
                    to: "Knowledge library" as View,
                  },
                  {
                    title: "Verify your first answer",
                    text: "Approve external processing, ask a focused question, and inspect the cited excerpts.",
                    action: "Ask Aegis",
                    to: "Ask Aegis" as View,
                  },
                  {
                    title: "Protect your workspace",
                    text: "Review the deployment and backup guide before making this service accessible to other users.",
                    action: "Review operations",
                    to: "Services & migration" as View,
                  },
                ].map((s, i) => (
                  <div className="item row between" key={s.title}>
                    <div className="row" style={{ alignItems: "flex-start" }}>
                      <span className="stepnum">{i + 1}</span>
                      <div>
                        <h3>{s.title}</h3>
                        <p className="muted small">{s.text}</p>
                      </div>
                    </div>
                    <button
                      className="btn"
                      disabled={i === 0}
                      onClick={() => navigate(s.to)}
                    >
                      {s.action}
                      <ArrowRight size={13} />
                    </button>
                  </div>
                ))}
              </section>
              <Notice tone="warn">
                Before using an external provider, review what content is sent
                and who is billed. Aegis asks for approval for document
                processing, chat, and extraction. Always review generated
                answers against their original sources.
              </Notice>
            </>
          )}
        </main>
      </div>
      {toast && (
        <div className="toast" role="status">
          <CheckCircle2 size={17} />
          {toast}
          <button
            style={{ border: 0, background: "none", color: "white" }}
            onClick={() => setToast("")}
            aria-label="Dismiss notification"
          >
            <X size={15} />
          </button>
        </div>
      )}
      {modal && (
        <div className="modal-bg" onClick={() => setModal(null)}>
          <section
            className="modal wide"
            role="dialog"
            aria-modal="true"
            aria-label={modal.title}
            onClick={(e) => e.stopPropagation()}
          >
            <div className="panel-head">
              <h2>{modal.title}</h2>
              <button
                className="btn icon"
                onClick={() => setModal(null)}
                aria-label="Close preview"
              >
                <X size={17} />
              </button>
            </div>
            {typeof modal.data === "string" ? (
              <pre className="code mono">{modal.data}</pre>
            ) : (
              <>
                <pre className="code mono" style={{ maxHeight: "55vh" }}>
                  {modal.data.text ||
                    modal.data.excerpt ||
                    modal.data.chunk_text ||
                    json(modal.data)}
                </pre>
                {modal.data.chunks?.length > 0 && (
                  <details>
                    <summary>{modal.data.chunks.length} source chunks</summary>
                    <pre className="code mono">{json(modal.data.chunks)}</pre>
                  </details>
                )}
              </>
            )}
          </section>
        </div>
      )}
      {confirm && (
        <div className="modal-bg">
          <section
            className="modal"
            style={{ maxWidth: 490 }}
            role="dialog"
            aria-modal="true"
            aria-label={confirm.title}
          >
            <h2>{confirm.title}</h2>
            <p
              className="muted"
              style={{ lineHeight: 1.8, margin: "18px 0 24px" }}
            >
              {confirm.body}
            </p>
            <div className="row" style={{ justifyContent: "flex-end" }}>
              <button
                className="btn"
                disabled={busy}
                onClick={() => setConfirm(null)}
              >
                Cancel
              </button>
              <button
                className="btn primary"
                disabled={busy}
                onClick={() =>
                  run(async () => {
                    await confirm.action();
                    setConfirm(null);
                  })
                }
              >
                {busy ? (
                  <Loader2 className="animate-spin" size={14} />
                ) : (
                  <Check size={14} />
                )}
                Confirm
              </button>
            </div>
          </section>
        </div>
      )}
    </>
  );
}
