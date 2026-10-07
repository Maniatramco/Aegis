"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import { DocumentUploadPanel, useDocumentUpload } from "./document-upload";
import { FocusedChat } from "./focused-chat";
import { readChatStream } from "./chat-stream";
import { DatasetHome } from "./dataset-directory";
import { ExtractionReview } from "./extraction-review";
import { PromptTemplates } from "./prompt-templates";
import { ReExtract } from "./re-extract";
import "./workspace-flow.css";
import { DatasetWorkspace, ModelCatalog, ModelPicker, eligibleModels, modelLabel, recordedModel } from "./dataset-workspace";
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
  | "Home"
  | "Dashboard"
  | "Datasets"
  | "Ask Aegis"
  | "Extract"
  | "Re-extract"
  | "Prompt templates"
  | "Index inspector"
  | "Jobs & activity"
  | "Connections"
  | "Services & migration"
  | "Setup";
const sections: { name: View; icon: typeof Shield; group?: string }[] = [
  { name: "Home", icon: Database, group: "WORKSPACE" },
  { name: "Dashboard", icon: LayoutDashboard },
  { name: "Datasets", icon: BookOpen },
  { name: "Ask Aegis", icon: MessageSquare },
  { name: "Extract", icon: FileSearch },
  { name: "Re-extract", icon: RefreshCw },
  { name: "Prompt templates", icon: FileText },
  { name: "Index inspector", icon: Layers, group: "OPERATIONS" },
  { name: "Jobs & activity", icon: Activity },
  { name: "Connections", icon: Settings2 },
  { name: "Services & migration", icon: Cloud },
  { name: "Setup", icon: Cog },
];
const descriptions: Record<View, string> = {
  Home: "Your registered datasets. Open one to view its documents and settings.",
  Dashboard:
    "Your documents, processing activity, and connected services at a glance.",
  "Datasets":
    "Onboard your data, map its models, and put a trusted source to work.",
  "Ask Aegis": "Ask across your knowledge, with evidence you can inspect.",
  Extract: "Turn document content into structured, reviewable data.",
  "Prompt templates": "Describe what to find and choose the fields you need.",
  "Re-extract": "Find a document and choose how to extract it again.",
  "Index inspector":
    "Inspect document chunks and the retrieval layer behind your answers.",
  "Jobs & activity": "Follow processing work and resolve what needs attention.",
  Connections: "Manage shared model connections and deployment infrastructure.",
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
  const [view, setView] = useState<View>("Ask Aegis");
  const [user, setUser] = useState<Entity | null>(null);
  const [authChecked, setAuthChecked] = useState(false);
  const [csrf, setCsrf] = useState("");
  const [bootstrap, setBootstrap] = useState(false);
  const [bootstrapToken, setBootstrapToken] = useState("");
  const [username, setUsername] = useState("admin");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [signInErrors, setSignInErrors] = useState<{ username?: string; password?: string; code?: string }>({});
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [toast, setToast] = useState("");
  const [mobile, setMobile] = useState(false);
  const [compactNavigation, setCompactNavigation] = useState(false);
  const navigationRef = useRef<HTMLElement>(null);
  const navigationTrigger = useRef<HTMLButtonElement>(null);
  const drawerOpen = mobile && compactNavigation;
  useEffect(() => {
    const media = window.matchMedia("(max-width: 960px)");
    const sync = () => {
      setCompactNavigation(media.matches);
      if (!media.matches) setMobile(false);
    };
    sync();
    media.addEventListener("change", sync);
    return () => media.removeEventListener("change", sync);
  }, []);
  useEffect(() => {
    if (!drawerOpen || !user) return;
    const drawer = navigationRef.current;
    if (!drawer) return;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    const focusable = () => Array.from(drawer.querySelectorAll<HTMLElement>("button:not(:disabled), a[href], [tabindex='0']")).filter(el => el.getClientRects().length);
    focusable()[0]?.focus();
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") { event.preventDefault(); setMobile(false); }
      if (event.key !== "Tab") return;
      const controls = focusable();
      const first = controls[0], last = controls[controls.length - 1];
      if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last?.focus(); }
      else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first?.focus(); }
    };
    drawer.addEventListener("keydown", onKey);
    return () => {
      document.body.style.overflow = previousOverflow;
      drawer.removeEventListener("keydown", onKey);
      if (window.matchMedia("(max-width: 960px)").matches) navigationTrigger.current?.focus();
    };
  }, [drawerOpen, user]);
  const [adminNavigation, setAdminNavigation] = useState(false);
  const [connectionTab, setConnectionTab] = useState("Models");
  const [extractionTab, setExtractionTab] = useState("Create");
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
  const [models, setModels] = useState<Entity[]>([]);
  const [datasetModelsFocus, setDatasetModelsFocus] = useState(false);
  const [chatModelId, setChatModelId] = useState("");
  const [extractModelId, setExtractModelId] = useState("");
  const [documentPollError, setDocumentPollError] = useState(false);
  const [externalUpload, setExternalUpload] = useState(false);
  const [conversations, setConversations] = useState<Entity[]>([]);
  const [conversation, setConversation] = useState<Entity | null>(null);
  const [temporary, setTemporary] = useState(false);
  const [temporaryUploads, setTemporaryUploads] = useState<string[]>([]);
  useEffect(() => { setTemporary(false); setTemporaryUploads([]); }, [user?.id]);
  const [prompt, setPrompt] = useState("");
  const [scope, setScope] = useState<string[]>([]);
  const [externalChat, setExternalChat] = useState(false);
  const [answering, setAnswering] = useState(false);
  const [lastPrompt, setLastPrompt] = useState("");
  const abort = useRef<AbortController | null>(null);
  const sending = useRef(false);
  const conversationRequest = useRef(0);
  const openingConversation = useRef(false);
  const [templates, setTemplates] = useState<Entity[]>([]);
  const [templateId, setTemplateId] = useState("");
  const [extractions, setExtractions] = useState<Entity[]>([]);
  const [extraction, setExtraction] = useState<Entity | null>(null);
  const [resultText, setResultText] = useState("");
  const reviewDirty = useRef(false);
  const templateDirty = useRef(false);
  const onTemplateDirty = useCallback((dirty: boolean) => { templateDirty.current = dirty; }, []);
  const onReviewDirty = useCallback((dirty: boolean) => { reviewDirty.current = dirty; }, []);
  const [temporarySession, setTemporarySession] = useState("");
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
        throw Object.assign(new Error(
          typeof data.detail === "string"
            ? data.detail
            : JSON.stringify(data.detail || data),
        ), { status: r.status });
      }
      return data;
    },
    [csrf],
  );
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
      api("/datasets"),
      api("/jobs"),
      api("/capabilities"),
      api("/settings"),
      api("/templates"),
      api("/conversations"),
      api("/extractions"),
      api("/models"),
      api("/settings/profiles"),
    ])
      .then(([o, d, k, j, c, s, t, co, e, m, p]) => {
        if (!active) return;
        setOverview(o);
        setDocs(Array.isArray(d) ? d : d.documents || []);
        setDocumentPollError(false);
        setKbs(Array.isArray(k) ? k : k.datasets || []);
        setJobs(Array.isArray(j) ? j : j.jobs || []);
        setCaps(c);
        setSettings(s);
        setSettingsForm(s);
        setTemplates(Array.isArray(t) ? t : t.templates || []);
        setConversations(Array.isArray(co) ? co : co.conversations || []);
        setExtractions(Array.isArray(e) ? e : e.extractions || []);
        setModels(Array.isArray(m) ? m : m.models || []);
        setProfiles(Array.isArray(p) ? p : p.profiles || []);
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
            .then((d) => { setDocs(Array.isArray(d) ? d : d.documents || []); setDocumentPollError(false); })
            .catch(() => setDocumentPollError(true));
        })
        .catch(() => setDocumentPollError(true));
    }, 6000);
    return () => clearInterval(timer);
  }, [user, api]);
  const navigate = (name: View) => {
    if ((reviewDirty.current || templateDirty.current) && !window.confirm("Discard unsaved changes before leaving?")) return;
    reviewDirty.current = false; templateDirty.current = false;
    window.location.hash = encodeURIComponent(name);
    setView(name);
    if (!["Home", "Datasets", "Ask Aegis", "Extract", "Re-extract", "Prompt templates"].includes(name)) setAdminNavigation(true);
    setDatasetModelsFocus(false);
    setError("");
    setMobile(false);
  };
  const selectedDataset = kbs.find(d => d.id === kb);
  const chatModels = eligibleModels(selectedDataset, "chat");
  const extractionModels = eligibleModels(selectedDataset, "extraction");
  const selectedChatModel = chatModels.find(m => m.id === chatModelId);
  const selectedExtractModel = extractionModels.find(m => m.id === extractModelId);
  const datasetEmbedding = selectedDataset?.active === false ? undefined : (selectedDataset?.models || []).find((m: Entity) => m.id === selectedDataset?.embedding_model_id && m.enabled !== false && m.mapping_enabled !== false);
  const datasetDocs = docs.filter(d => (d.dataset_id || d.kb_id) === kb);
  const readyDatasetDocs = datasetDocs.filter(d => d.status === "ready" && !d.requires_reindex);
  const changeDataset = (id: string) => {
    if (id === kb) return;
    if (answering) { setError("Stop the current answer before changing datasets."); return; }
    conversationRequest.current += 1;
    openingConversation.current = false;
    setKb(id);
    setDatasetModelsFocus(false);
    setScope([]);
    setChatModelId("");
    setExtractModelId("");
    setExternalChat(false);
    setExternalExtract(false);
    setExternalUpload(false);
    setConversation(null);
    setPrompt("");
    setLastPrompt("");
    setQuery("");
  };
  const routeHandler = useRef<(hash: string) => void>(() => {});
  routeHandler.current = (hash: string) => {
    if ((reviewDirty.current || templateDirty.current) && !window.confirm("Discard unsaved changes before leaving?")) { window.history.replaceState(null, "", "#" + encodeURIComponent(view)); return; }
    reviewDirty.current = false; templateDirty.current = false;
    let route: string;
    try { route = decodeURIComponent(hash.slice(1)); } catch { route = "Ask Aegis"; }
    if (route.startsWith("dataset/")) {
      changeDataset(route.slice(8));
      setView("Datasets");
    } else {
      const next = sections.find(s => s.name.toLowerCase() === (route.toLowerCase() === "templates" ? "prompt templates" : route.toLowerCase()))?.name || "Ask Aegis";
      setView(next);
      if (!["Home", "Datasets", "Ask Aegis", "Extract", "Re-extract", "Prompt templates"].includes(next)) setAdminNavigation(true);
    }
    setMobile(false);
    setError("");
  };
  useEffect(() => {
    const followHash = () => routeHandler.current(window.location.hash);
    followHash();
    window.addEventListener("hashchange", followHash);
    return () => window.removeEventListener("hashchange", followHash);
  }, []);
  useEffect(() => {
    const dataset = kbs.find(d => d.id === kb);
    const pick = (current: string, capability: string, defaultKey: string) => {
      const available = eligibleModels(dataset, capability);
      if (available.some(m => m.id === current)) return current;
      if (available.some(m => m.id === dataset?.[defaultKey])) return dataset![defaultKey];
      return available.length === 1 ? available[0].id : "";
    };
    setChatModelId(current => pick(current, "chat", "default_chat_model_id"));
    setExtractModelId(current => pick(current, "extraction", "default_extraction_model_id"));
  }, [kb, kbs]);
  useEffect(() => {
    setScope(current => current.filter(id => docs.some(d => d.id === id && (d.dataset_id || d.kb_id) === kb && d.status === "ready" && !d.requires_reindex)));
  }, [kb, docs]);
  useEffect(() => { setExternalChat(false); }, [kb, chatModelId, selectedChatModel?.version, selectedChatModel?.connection_profile_version]);
  useEffect(() => { setExternalExtract(false); }, [kb, extractModelId, selectedExtractModel?.version, selectedExtractModel?.connection_profile_version]);
  const uploadContextKey = JSON.stringify([kb, selectedDataset?.active, selectedDataset?.embedding_selection,
    ...["storage_provider", "search_provider", "oci_storage_namespace", "oci_storage_bucket", "oci_storage_prefix", "oci_storage_region", "oci_storage_auth_mode", "oci_storage_profile", "oci_region", "oci_project_id", "oci_vector_store_id"].map(key => settings[key]),
  ]);
  useEffect(() => { setExternalUpload(false); }, [uploadContextKey, csrf]);
  const externalProvider =
    ["openai", "oci"].includes(selectedDataset?.embedding_selection?.embedding_provider || datasetEmbedding?.provider) ||
    selectedDataset?.embedding_selection?.search_provider === "oci" ||
    settings.search_provider === "oci" ||
    settings.storage_provider === "oci";
  const filtered = datasetDocs.filter(d => d.name.toLowerCase().includes(query.toLowerCase()));
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
      navigate("Ask Aegis");
      setUser(d.user);
      setCsrf(d.csrf_token || "");
      setPassword("");
    });
  const documentUpload = useDocumentUpload({
    dataset: selectedDataset, enabled: !!datasetEmbedding, externalRequired: externalProvider,
    consent: externalUpload, setConsent: setExternalUpload, maxMb: Number(settings.max_upload_mb || 25),
    sessionKey: user ? csrf : "",
    temporarySessionId: temporary ? temporarySession : "",
    contextKey: uploadContextKey,
    documents: docs, jobs, api, refresh: reload, pollError: documentPollError,
    onManage: () => navigate("Datasets"),
    onUploaded: data => {
      if (temporary && data.newUpload) setTemporaryUploads(previous => [...new Set([...previous, ...(data.documents || []).map((d: Entity) => d.id)])]);
      setDocs(previous => [...(data.documents || []), ...previous.filter(d => !(data.documents || []).some((next: Entity) => next.id === d.id))]);
      setJobs(previous => [...(data.jobs || []), ...previous.filter(j => !(data.jobs || []).some((next: Entity) => next.id === j.id))]);
    },
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
  const openConversation = async (id: string, preserveDraft = false) => {
    const request = ++conversationRequest.current;
    openingConversation.current = true;
    if (!preserveDraft) setPrompt("");
    try {
    const d = await api(`/conversations/${id}`);
    if (request !== conversationRequest.current) return;
    setKb(d.dataset_id || d.kb_id || "");
    setScope(d.document_ids || []);
    const historicalModel = [...(d.messages || [])].reverse().find((m: Entity) => m.model_selection)?.model_selection?.model_id;
    const dataset = kbs.find(k => k.id === (d.dataset_id || d.kb_id));
    const available = eligibleModels(dataset, "chat");
    setChatModelId(available.some(m => m.id === historicalModel) ? historicalModel : available.some(m => m.id === dataset?.default_chat_model_id) ? dataset!.default_chat_model_id : available.length === 1 ? available[0].id : "");
    setExternalChat(false);
    setTemporary(false);
    setConversation(d);
    setLastPrompt([...(d.messages || [])].reverse().find((m: Entity) => m.role === "user")?.text || "");
    } catch (error) { if (request === conversationRequest.current) throw error; }
    finally { if (request === conversationRequest.current) openingConversation.current = false; }
  };
  const sendMessage = async (text = prompt) => {
    if (!text.trim() || answering || sending.current || openingConversation.current) return;
    if (!kb || !selectedChatModel || !readyDatasetDocs.length) {
      setError("Choose a dataset with ready documents and an eligible chat model.");
      return;
    }
    if (selectedChatModel?.provider !== "ollama" && !externalChat) {
      setError("Approve the provider notice before sending a question.");
      return;
    }
    setError("");
    sending.current = true;
    setAnswering(true);
    setLastPrompt(text);
    abort.current = new AbortController();
    try {
      let c: Entity | null = conversation ? { ...conversation, messages: (conversation.messages || []).filter((m: Entity) => !["pending-user", "streaming-answer"].includes(m.id)) } : null;
      if (temporary) {
        const history = (c?.messages || []).filter((m: Entity) => m.role === "user" || m.role === "assistant").slice(-20).map((m: Entity) => ({ role: m.role, text: m.text || m.content || "" }));
        const baseMessages = [...(c?.messages || []), { id: crypto.randomUUID(), role: "user", text }];
        const thread = c || { id: "temporary", title: "Temporary chat", dataset_id: kb };
        setConversation({ ...thread, messages: baseMessages }); setPrompt("");
        const result = await api("/temporary-chat/messages", "POST", { text, dataset_id: kb, document_ids: scope, model_id: chatModelId, allow_external: true, history }, abort.current.signal);
        setConversation({ ...thread, messages: [...baseMessages, result.message] });
        return;
      }
      if (!c) {
        c = await api("/conversations", "POST", {
          title: text.slice(0, 70),
          dataset_id: kb,
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
            dataset_id: kb,
            model_id: chatModelId,
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
      let answer = "";
      const baseMessages = [...(c!.messages || []), { id: "pending-user", role: "user", text }];
      await readChatStream(response.body, ({ type, payload }) => {
        if (type === "delta") {
          answer += payload.text;
          setConversation({ ...c, messages: [...baseMessages, {
            id: "streaming-answer", role: "assistant", text: answer, status: "streaming",
            mock: selectedChatModel?.provider === "mock",
            model_selection: { model_id: chatModelId, model_name: modelLabel(selectedChatModel), provider_model: selectedChatModel?.provider_model },
          }] });
        }
        if (type === "done" || type === "error") {
          if (payload.message) setConversation({ ...c, messages: [...baseMessages.slice(0,-1), payload.user_message || baseMessages.at(-1), payload.message] });
          if (type === "error") throw new Error(payload.detail || "The model could not complete this answer.");
        }
      });
      const cs = await api("/conversations");
      setConversations(Array.isArray(cs) ? cs : cs.conversations || []);
    } catch (e) {
      const stopped = e instanceof Error && e.name === "AbortError";
      const detail = stopped ? "Generation stopped. Any partial response is kept below. The model may take a moment to finish stopping." : e instanceof Error ? e.message : "The question could not be completed. Try again.";
      setError(detail);
      setPrompt(text);
      setConversation(current => {
        if (!current) return current;
        const messages = [...(current.messages || [])];
        const last = messages.at(-1);
        if (last?.role === "assistant" && last.status === "failed") return current;
        const failed = { id: crypto.randomUUID(), role: "assistant", text: last?.id === "streaming-answer" ? last.text : "", status: stopped ? "aborted" : "failed", error: { detail, retryable: true } };
        if (last?.id === "streaming-answer") messages[messages.length-1] = failed;
        else if (last?.role === "user") messages.push(failed);
        else return current;
        return { ...current, messages };
      });
    } finally {
      sending.current = false;
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
  const chooseTemplate = (id: string) => setTemplateId(id);
  const extract = () =>
    run(async () => {
      if (!kb || !selectedExtractModel) throw new Error("Choose a dataset and an eligible extraction model.");
      if (!scope.length || !templateId)
        throw new Error("Select at least one document and a template.");
      if (!externalExtract)
        throw new Error("Approve the external processing notice first.");
      const d = await api("/extractions", "POST", {
        dataset_id: kb,
        model_id: extractModelId,
        document_ids: scope,
        template_id: templateId,
        allow_external: true,
      });
      setExtraction(d);
      setExtractionTab("Review");
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
      {datasetDocs.length ? (
        datasetDocs.map((d) => (
          <label key={d.id}>
            <input
              type="checkbox"
              checked={scope.includes(d.id)}
              disabled={answering || d.status !== "ready" || !!d.requires_reindex}
              onChange={() => selectDoc(d.id)}
            />
            <span>
              {d.name} <span className="muted">· {d.status === "ready" && d.requires_reindex ? "reindex required" : d.status}</span>
            </span>
          </label>
        ))
      ) : (
        <p className="small muted">
          {kb ? "Add documents to this dataset first." : "Choose a dataset to see its documents."}
        </p>
      )}
    </div>
  );
  const externalNotice = (model: Entity | undefined) => model?.provider === "ollama" && !externalProvider ? `I approve running this question and selected document content with ${modelLabel(model)} locally through Ollama. No paid model API is used.` : `I approve sending this request and relevant document content to ${modelLabel(model)} (${model?.provider || "model provider"}), with the dataset’s pinned embedding model ${selectedDataset?.embedding_selection?.provider_model || datasetEmbedding?.provider_model || "not configured"} and configured retrieval connection. External API usage is billed separately by those providers; ChatGPT does not cover these charges.`;
  const datasetSelect = (label: string) => <select aria-label={label} value={kb} onChange={e => changeDataset(e.target.value)} disabled={answering}><option value="">Choose a dataset</option>{kbs.map(d => <option key={d.id} value={d.id}>{d.name}</option>)}</select>;
  const configureDataset = () => { navigate("Datasets"); setDatasetModelsFocus(true); };

  if (!authChecked)
    return (
      <div className="auth-form" style={{ minHeight: "100vh" }}>
        <Loader2 className="animate-spin" size={26} />
      </div>
    );
  if (!user)
    return (
      <main className="login-shell">
        <section className="login-card" aria-labelledby="login-heading">
          <div className="login-brand"><img src="/aegis-logo.png" alt="" width={38} height={38} /><span>Aegis</span></div>
          <h1 id="login-heading">{bootstrap ? "Create your workspace" : "Welcome back"}</h1>
          <p className="login-description">{bootstrap ? "Set up your first account to get started." : "Sign in to your workspace."}</p>
          {error && <div className="login-error" role="alert"><AlertCircle size={18} aria-hidden="true" /><span>{error}</span></div>}
          <form noValidate aria-busy={busy} onSubmit={e => {
            e.preventDefault();
            if (busy) return;
            const next: { username?: string; password?: string; code?: string } = {};
            if (!username.trim()) next.username = "Enter your username.";
            if (!password) next.password = "Enter your password.";
            else if (bootstrap && password.length < 12) next.password = "Use at least 12 characters.";
            if (bootstrap && !bootstrapToken) next.code = "Enter your setup code.";
            setSignInErrors(next);
            if (Object.keys(next).length) {
              document.getElementById(next.code ? "login-code" : next.username ? "login-username" : "login-password")?.focus();
              return;
            }
            setShowPassword(false);
            authenticate();
          }}>
            {bootstrap && <div className="field">
              <label htmlFor="login-code">Bootstrap token</label>
              <input id="login-code" autoComplete="off" type="password" value={bootstrapToken} required
                aria-invalid={!!signInErrors.code} aria-describedby={signInErrors.code ? "login-code-error" : "login-code-help"}
                onChange={e => { setBootstrapToken(e.target.value); setSignInErrors(current => ({ ...current, code: undefined })); setError(""); }} />
              <small id="login-code-help">Use the one-time setup code from your installation.</small>
              {signInErrors.code && <small className="field-error" id="login-code-error">{signInErrors.code}</small>}
            </div>}
            <div className="field">
              <label htmlFor="login-username">Username</label>
              <input id="login-username" autoComplete="username" autoCapitalize="none" spellCheck={false} value={username} required
                aria-invalid={!!signInErrors.username} aria-describedby={signInErrors.username ? "login-username-error" : undefined}
                onChange={e => { setUsername(e.target.value); setSignInErrors(current => ({ ...current, username: undefined })); setError(""); }} />
              {signInErrors.username && <small className="field-error" id="login-username-error">{signInErrors.username}</small>}
            </div>
            <div className="field">
              <label htmlFor="login-password">Password</label>
              <div className="login-password-entry">
                <input id="login-password" autoComplete={bootstrap ? "new-password" : "current-password"} type={showPassword ? "text" : "password"}
                  value={password} required minLength={bootstrap ? 12 : 1} maxLength={200}
                  aria-invalid={!!signInErrors.password} aria-describedby={signInErrors.password ? "login-password-error" : undefined}
                  onChange={e => { setPassword(e.target.value); setSignInErrors(current => ({ ...current, password: undefined })); setError(""); }} />
                <button type="button" className="login-password-toggle" aria-label={showPassword ? "Hide password" : "Show password"}
                  aria-controls="login-password" aria-pressed={showPassword} onClick={() => setShowPassword(value => !value)} disabled={busy}>
                  {showPassword ? "Hide" : "Show"}
                </button>
              </div>
              {signInErrors.password && <small className="field-error" id="login-password-error">{signInErrors.password}</small>}
            </div>
            <button className="btn primary login-submit" type="submit" disabled={busy}>
              {busy && <Loader2 size={17} className="animate-spin" aria-hidden="true" />}
              {busy ? (bootstrap ? "Creating account..." : "Signing in...") : (bootstrap ? "Create administrator" : "Sign in")}
            </button>
          </form>
          {!bootstrap && <a className="recovery-entry" href="/recover-password">Forgot password?</a>}
          {bootstrap && <button className="login-switch" type="button" onClick={() => {
            setBootstrap(false); setPassword(""); setShowPassword(false); setSignInErrors({}); setError("");
          }}>Already configured? Sign in</button>}
        </section>
      </main>
    );

  return (
    <>
      {drawerOpen && <div className="navigation-backdrop" aria-hidden="true" onClick={() => setMobile(false)} />}
      <aside id="workspace-navigation" ref={navigationRef} className={`sidebar ${view === "Ask Aegis" ? "chat-rail" : ""} ${drawerOpen ? "open" : ""}`} role={drawerOpen ? "dialog" : undefined} aria-modal={drawerOpen ? true : undefined} aria-label="Workspace navigation" inert={compactNavigation && !drawerOpen}>
        <button
          className="btn icon mobile-close"
          onClick={() => setMobile(false)}
          aria-label="Close navigation"
        >
          <X size={15} />
        </button>
        <div className="brand">
          <span className="brandmark">
            <img src="/aegis-logo.png" alt="" width={40} height={40} />
          </span>
          <span className="brand-name">Aegis</span>
        </div>
        <div className="brand-sub">Document intelligence</div>
        <nav>
          {sections.filter(s => ["Home", "Datasets", "Ask Aegis", "Extract", "Re-extract", "Prompt templates"].includes(s.name)).map(s => (
            <button key={s.name} aria-label={s.name} title={s.name} className={`nav-item ${view === s.name ? "selected" : ""}`} aria-current={view === s.name ? "page" : undefined} onClick={() => navigate(s.name)}><s.icon size={18} /><span className="nav-item-label">{s.name}</span></button>
          ))}
          <button className="nav-item nav-more" aria-label="Manage workspace" title="Manage workspace" aria-expanded={adminNavigation} aria-controls="admin-navigation" onClick={() => setAdminNavigation(!adminNavigation)}><Settings2 size={18} /><span className="nav-item-label">Manage workspace</span><ChevronRight size={14} className={adminNavigation ? "rotated" : ""} /></button>
          {adminNavigation && <div id="admin-navigation" className="admin-navigation">
            {sections.filter(s => !["Home", "Datasets", "Ask Aegis", "Extract", "Re-extract", "Prompt templates"].includes(s.name)).map(s => <button key={s.name} aria-label={s.name} title={s.name} className={`nav-item ${view === s.name ? "selected" : ""}`} aria-current={view === s.name ? "page" : undefined} onClick={() => navigate(s.name)}><s.icon size={16} /><span className="nav-item-label">{s.name}</span></button>)}
          </div>}
        </nav>
        <div className="nav-footer">
          <div className="row" style={{ marginBottom: 9 }}>
            <Server size={14} />
            <span>Local workspace</span>
          </div>
          Originals protected. Insights grounded.
        </div>
      </aside>
      <div className={`shell ${view === "Ask Aegis" ? "chat-shell" : ""}`} inert={drawerOpen}>
        <header className="topbar">
          <div className="breadcrumb">
            <button
              className="btn icon menu-toggle"
              onClick={() => setMobile(true)}
              aria-label="Open navigation"
              ref={navigationTrigger}
              aria-expanded={drawerOpen}
              aria-controls="workspace-navigation"
            >
              <Menu size={17} />
            </button>
            <img className="header-logo" src="/aegis-logo.png" alt="Aegis" width={28} height={28} /><span className="crumb-workspace">Workspace</span>
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
          {view !== "Ask Aegis" && <div className="page-head">
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
                  onClick={() => navigate("Datasets")}
                >
                  <Plus size={15} />
                  Add documents
                </button>
              )}
            </div>
          </div>}
          {error && view !== "Home" && view !== "Ask Aegis" && (
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
                    label: "Datasets",
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
                      onClick={() => navigate("Datasets")}
                    >
                      View datasets
                      <ArrowRight size={13} />
                    </button>
                  </div>
                  {docs.length ? (
                    <div className="table-scroll" role="region" aria-label="Scrollable data table" tabIndex={0}>
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
          {view === "Home" && <DatasetHome api={api} refresh={refresh} onLoaded={setKbs} documents={docs} onBrowse={() => navigate("Datasets")} onChat={id => { changeDataset(id); navigate("Ask Aegis"); }} onCreated={d => { changeDataset(d.id); navigate("Datasets"); setDatasetModelsFocus(true); reload(); }} />}
          {view === "Datasets" && (
            <>
            <DatasetWorkspace datasets={kbs} models={models} documents={docs} selectedId={kb} modelsFocus={datasetModelsFocus}
              onSelect={changeDataset} onCreated={d => { setKbs(current => [...current, d]); changeDataset(d.id); }}
              api={api} run={run} busy={busy || answering} reload={reload} notify={notify}
              onConnections={() => navigate("Connections")} onUse={navigate}
              uploadPanel={<DocumentUploadPanel upload={documentUpload} />}
              documentsPanel={
              <section className="panel flush">
                <div className="panel-head" style={{ padding: "20px 20px 0" }}>
                  <div>
                    <h2>Dataset documents</h2>
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
                  <div className="table-scroll" role="region" aria-label="Scrollable data table" tabIndex={0}>
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
                              <Status value={d.status === "ready" && d.requires_reindex ? "reindex_required" : d.status} />
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
                    detail="Upload a document above, or open another dataset."
                  />
                )}
              </section>
              }
            />
            {docs.some(d => !(d.dataset_id || d.kb_id)) && <section className="panel legacy-documents">
              <div className="panel-head"><div><h2>Unassigned documents</h2><p className="muted small">These originals were uploaded before dataset onboarding. Assign them to a dataset to use its model configuration, then reindex.</p></div><span className="pill amber">{docs.filter(d => !(d.dataset_id || d.kb_id)).length} need a dataset</span></div>
              <div className="selection">{docs.filter(d => !(d.dataset_id || d.kb_id)).map(d => <div className="item row between" key={d.id}><span className="small">{d.name}</span><div className="row"><button className="btn icon" title={`Preview unassigned ${d.name}`} onClick={() => openPreview(d)}><Search size={13} /></button><Download path={`/documents/${d.id}/download`}>Original</Download></div></div>)}</div>
              <div className="row between wrap" style={{marginTop:17}}><span className="small muted">{selectedDataset ? `Destination: ${selectedDataset.name}` : "Open or onboard a dataset above to choose the destination."}</span><button className="btn primary" disabled={busy || !selectedDataset} onClick={() => setConfirm({title:"Assign unassigned documents?", body:`Assign all ${docs.filter(d => !(d.dataset_id || d.kb_id)).length} unassigned documents to “${selectedDataset?.name}”? Originals are preserved. You must reindex them with this dataset’s embedding model before asking questions or extracting. Existing dataset documents will not move.`, action:async () => {const ids = docs.filter(d => !(d.dataset_id || d.kb_id)).map(d => d.id); for (let start = 0; start < ids.length; start += 100) await api(`/datasets/${kb}/assign-documents`, "POST", {document_ids:ids.slice(start, start + 100)}); notify("Documents assigned. Reindex them to use this dataset’s embedding model."); reload();}})}>Assign to selected dataset</button></div>
            </section>}
            </>
          )}
          {view === "Ask Aegis" && (
            <FocusedChat temporary={temporary} temporaryUploadCount={docs.filter(d=>d.temporary_session_id===temporarySession).length}
              onTemporary={() => run(async () => { if (!temporary) { const session = await api("/temporary-chat/sessions", "POST", {}); setTemporarySession(session.id); } conversationRequest.current += 1; setTemporary(!temporary); setConversation(null); setPrompt(""); setLastPrompt(""); setError(""); })}
              onCleanup={() => setConfirm({ title: "Clean up temporary-only uploads?", body: "Delete this temporary session’s originals and indexes? Permanent dataset documents and uploads kept or used in saved chat/extraction are preserved.", action: async () => { const result = await api(`/temporary-chat/sessions/${temporarySession}`, "DELETE"); setTemporaryUploads(result.pending_document_ids || []); reload(); notify(result.pending_document_ids?.length ? "Some cleanup remains pending; check service health and retry." : "Temporary-only uploads cleaned up. Permanent documents preserved."); } })}
              upload={documentUpload} conversation={conversation} conversations={conversations} prompt={prompt} setPrompt={setPrompt}
              error={error} onDismissError={() => setError("")} datasetName={selectedDataset?.name || "Choose a dataset"} localProcessing={settings.local_only || (selectedChatModel?.provider === "ollama" && !externalProvider)} reranker={settings.reranker || {}}
              answering={answering} lastPrompt={lastPrompt} canSend={!busy && (selectedChatModel?.provider === "ollama" || externalChat) && !!selectedChatModel && !!readyDatasetDocs.length}
              externalChat={externalChat} setExternalChat={setExternalChat} providerNotice={settings.local_only ? "Questions and document content are processed locally through Ollama with a compatible dataset embedding index. Choose an installed mapped model to continue." : externalNotice(selectedChatModel)} modelName={modelLabel(selectedChatModel)}
              scopeCount={scope.length} readyCount={readyDatasetDocs.length} documentControl={docSelection}
              datasetControl={datasetSelect("Chat dataset")} modelControl={<ModelPicker dataset={selectedDataset} capability="chat" value={chatModelId} onChange={setChatModelId} onConfigure={configureDataset} disabled={answering} />}
              exportControl={!temporary && conversation?.id ? <Download path={`/conversations/${conversation.id}/export`}>Export</Download> : null}
              onNew={() => { conversationRequest.current += 1; openingConversation.current = false; setConversation(null); setPrompt(""); setLastPrompt(""); setExternalChat(false); setError(""); }}
              onOpen={id => run(() => openConversation(id))} onSend={sendMessage} onStop={() => abort.current?.abort()}
              onReload={() => { if (!temporary) run(() => openConversation(conversation!.id)); }} onRefresh={reload} loading={loading} onCopy={copy}
              onFeedback={(id, rating) => run(async () => { await api(`/messages/${id}/feedback`, "POST", { rating }); notify("Feedback saved."); })}
            />
          )}
          {view === "Extract" && (
            <>
              <div className="section-tabs" aria-label="Extraction sections">
                {["Create", "History", ...(extraction ? ["Review"] : [])].map(tab => <button key={tab} className={`btn ${extractionTab === tab ? "primary" : ""}`} aria-pressed={extractionTab === tab} onClick={() => { if (reviewDirty.current && !window.confirm("Discard unsaved changes before changing sections?")) return; setExtractionTab(tab); }}>{tab === "Create" ? "New extraction" : tab === "History" ? "Extraction history" : "Review result"}</button>)}
              </div>
              <div className="extraction-focus">
                <section className="panel" hidden={extractionTab !== "Create"}>
                  <h2>Create an extraction</h2>
                  <p className="muted small">
                    Select a prompt template and documents. Review extracted values and
                    their evidence.
                  </p>
                  <Field label="Dataset">{datasetSelect("Extraction dataset")}</Field>
                  <ModelPicker dataset={selectedDataset} capability="extraction" value={extractModelId} onChange={setExtractModelId} onConfigure={configureDataset} />
                  <Field label="Prompt template">
                    <select
                      aria-label="Prompt template"
                      value={templateId}
                      onChange={(e) => chooseTemplate(e.target.value)}
                    >
                      <option value="">Select a prompt template</option>
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
                    <span className="muted small">{externalNotice(selectedExtractModel)}</span>
                  </label>
                  <button
                    className="btn primary"
                    disabled={
                      busy || !externalExtract || !templateId || !scope.length || !selectedExtractModel
                    }
                    onClick={extract}
                  >
                    <Play size={14} />
                    Run extraction
                  </button>
                </section>
                <section className="panel" hidden={extractionTab !== "History"}>
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
                            {date(e.created_at)}{recordedModel(e) ? ` · ${recordedModel(e)}` : ""}
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
                                setExtractionTab("Review");
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
              {extraction && extractionTab === "Review" && <ExtractionReview extraction={extraction} documents={docs} api={api} onDirty={onReviewDirty} onSaved={d => { setExtraction(d); setResultText(json(d.result || {})); reload(); }} />}
            </>
          )}
          {view === "Prompt templates" && <PromptTemplates templates={templates} api={api} initialId={templateId} onDirty={onTemplateDirty} onSaved={() => { notify("Prompt template saved."); reload(); }} onUse={id => { chooseTemplate(id); setExtractionTab("Create"); navigate("Extract"); }} />}
          {view === "Re-extract" && <ReExtract documents={docs} datasets={kbs} templates={templates} extractions={extractions} api={api} onRefresh={reload} onConfigure={id => { changeDataset(id); navigate("Datasets"); setDatasetModelsFocus(true); }} onReview={d => { changeDataset(d.dataset_id || d.parent_id); setExtraction(d); setExtractionTab("Review"); navigate("Extract"); reload(); }} />}
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
                      {retrievalResult.reranking?.enabled && <span className="pill">Local reranking · {retrievalResult.reranking.candidate_count} → {retrievalResult.count} chunks · {retrievalResult.reranking.rerank_ms} ms</span>}
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
                            {typeof m.rerank_score === "number" ? "Rerank" : "Similarity"}{" "}
                            {typeof (m.rerank_score ?? m.score) === "number"
                              ? (m.rerank_score ?? m.score).toFixed(4)
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
                <div className="table-scroll" role="region" aria-label="Scrollable data table" tabIndex={0}>
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
              <div className="section-tabs" aria-label="Connection sections">{["Models", "Profiles", "Providers", "Storage", "OCI", "Diagnostics"].map(tab => <button key={tab} className={`btn ${connectionTab === tab ? "primary" : ""}`} aria-pressed={connectionTab === tab} onClick={() => setConnectionTab(tab)}>{tab}</button>)}</div>
              <div hidden={connectionTab !== "Models"}><ModelCatalog models={models} profiles={profiles} api={api} run={run} busy={busy} reload={reload} notify={notify} /></div>
              <div hidden={!["Providers", "Storage", "OCI"].includes(connectionTab)}><Notice tone="warn">
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
                <section className="panel" hidden={connectionTab !== "Storage"}>
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
                  Use Save settings below to save this profile. Do not paste
                  private keys, tokens, or signing credentials into these
                  fields.
                </p>
              </section>
              <div className="settings-actions" hidden={!["Providers", "Storage", "OCI", "Diagnostics"].includes(connectionTab)}>                  <div className="row wrap">
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
                    title: settings.local_only ? "Configure local models" : "Connect your providers",
                    text: settings.local_only ? "Use installed Qwen3 or SmolLM2 through Ollama and compatible Nomic embeddings. No paid API or cloud fallback is enabled." : "Choose local embeddings or add your own OpenAI key. Keys stay encrypted on the server.",
                    action: "Configure connections",
                    to: "Connections" as View,
                  },
                  {
                    title: "Create a dataset",
                    text: "Name your dataset, map its chat, extraction, and embedding models, then upload PDF, DOCX, or TXT files.",
                    action: "Add documents",
                    to: "Datasets" as View,
                  },
                  {
                    title: "Verify your first answer",
                    text: settings.local_only ? "Ask a focused question locally and inspect its clickable source evidence." : "Approve external processing, ask a focused question, and inspect the cited excerpts.",
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
                {settings.local_only ? "This workspace runs inference locally through Ollama. No paid API or cloud fallback is enabled. Review generated answers against their original sources." : "Before using an external provider, review what content is sent and who is billed. Aegis asks for approval for document processing, chat, and extraction. Always review generated answers against their original sources."}
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
