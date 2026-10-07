"use client";
import { useEffect, useRef, useState } from "react";
import { AlertCircle, CheckCircle2, FileText, Loader2, RefreshCw, UploadCloud, X } from "lucide-react";
import "./document-upload.css";

type Entity = Record<string, any>;
type Api = (path: string, method?: string, body?: unknown) => Promise<any>;
type Entry = { id: string; datasetId: string; file?: File; name: string; size: number; status: "selected" | "invalid" | "uploading" | "submitted" | "failed" | "uncertain"; error?: string; document?: Entity };
type Options = {
  dataset?: Entity; enabled: boolean; externalRequired: boolean; consent: boolean; setConsent: (value: boolean) => void;
  maxMb: number; contextKey: string; sessionKey: string; documents: Entity[]; jobs: Entity[]; api: Api; onUploaded: (data: Entity) => void;
  refresh: () => void; onManage: () => void; pollError: boolean;
};

// Both Datasets and Ask Aegis use this controller and the same server endpoint.
// Submit one file at a time because the existing endpoint can partially accept a
// multi-file batch before a later file fails. Accepted originals are never retried.
export function useDocumentUpload(options: Options) {
  const [entries, setEntries] = useState<Entry[]>([]);
  const [notice, setNotice] = useState("");
  const [uploading, setUploading] = useState(false);
  const [uploadDestination, setUploadDestination] = useState("");
  const [retrying, setRetrying] = useState<string[]>([]);
  const inFlight = useRef(false);
  const retryLocks = useRef(new Set<string>());
  const currentSession = useRef(options.sessionKey);
  currentSession.current = options.sessionKey;
  const currentContext = useRef(options.contextKey);
  currentContext.current = options.contextKey;
  const datasetId = options.dataset?.id || "";
  const blocked = !datasetId ? "Choose a dataset below before attaching documents." : !options.enabled ? "This dataset needs an active, mapped embedding model before documents can be uploaded." : "";
  const selected = entries.filter(e => e.datasetId === datasetId);
  useEffect(() => { setNotice(""); }, [datasetId]);
  useEffect(() => { setEntries([]); setNotice(""); }, [options.sessionKey]);
  useEffect(() => {
    if (!uploading) return;
    const warn = (event: BeforeUnloadEvent) => { event.preventDefault(); };
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [uploading]);
  const choose = (files: File[]) => {
    if (blocked) { setNotice(blocked); return; }
    if (inFlight.current) { setNotice("Wait for the current upload to finish before adding more files."); return; }
    if (!files.length) return;
    setNotice("");
    setEntries(previous => {
      const existing = previous.filter(e => e.datasetId === datasetId && e.file);
      const additions = files.filter((file, index) => !existing.some(e => e.file!.name === file.name && e.file!.size === file.size && e.file!.lastModified === file.lastModified) && !files.slice(0, index).some(f => f.name === file.name && f.size === file.size && f.lastModified === file.lastModified));
      if (existing.length + additions.length > 20) { setNotice("Choose at most 20 files at once. Remove some files and try again."); return previous; }
      return [...previous, ...additions.map(file => {
        const error = !/\.(pdf|docx|txt)$/i.test(file.name) ? "Only PDF, DOCX and UTF-8 TXT files are supported." : !file.size ? "Empty files cannot be uploaded." : file.size > options.maxMb * 1024 * 1024 ? `Exceeds the ${options.maxMb} MB upload limit.` : undefined;
        return { id: crypto.randomUUID(), datasetId, name: file.name, size: file.size, file, status: error ? "invalid" as const : "selected" as const, error };
      })];
    });
  };
  const patch = (id: string, update: Partial<Entry>) => setEntries(previous => previous.map(e => e.id === id ? { ...e, ...update } : e));
  const pending = selected.filter(e => (e.status === "selected" || e.status === "failed") && e.file);
  const start = async () => {
    if (inFlight.current || blocked || !pending.length) return;
    if (options.externalRequired && !options.consent) { setNotice("Approve the external processing notice before uploading."); return; }
    inFlight.current = true; setUploading(true); setUploadDestination(options.dataset?.name || "selected dataset"); setNotice("");
    const context = options.contextKey;
    try {
      for (const entry of pending) {
        if (currentContext.current !== context || currentSession.current !== options.sessionKey) { setNotice("Dataset or processing settings changed. Remaining files were not uploaded; review their destination and consent before continuing."); break; }
        patch(entry.id, { status: "uploading", error: undefined });
        const body = new FormData();
        body.append("files", entry.file!);
        body.append("dataset_id", datasetId);
        body.append("allow_external", String(options.consent));
        try {
          const result = await options.api("/documents/upload", "POST", body);
          if (currentSession.current !== options.sessionKey) break;
          if (!result.documents?.[0]) throw new Error("The server did not confirm a document.");
          patch(entry.id, { status: "submitted", file: undefined, document: result.documents[0] });
          options.onUploaded({ ...result, newUpload: true });
        } catch (error) {
          const status = (error as { status?: number }).status;
          const definite = !!status && status >= 400 && status < 500;
          patch(entry.id, { status: definite ? "failed" : "uncertain", error: error instanceof Error ? error.message : "Upload failed." });
          // An uncertain response may have persisted an original. Never retry it
          // automatically, and stop the rest of the batch until the user checks.
          if (!definite || status === 401 || status === 403 || status === 409) break;
        }
      }
    } finally { inFlight.current = false; setUploading(false); options.refresh(); }
  };
  const retryIndex = async (document: Entity) => {
    if (retryLocks.current.has(document.id) || blocked) return;
    if (options.externalRequired && !options.consent) { setNotice("Approve the external processing notice before retrying indexing."); return; }
    retryLocks.current.add(document.id); setRetrying(ids => [...ids, document.id]); setNotice("");
    try {
      const job = await options.api(`/documents/${document.id}/reindex`, "POST", { allow_external: options.consent });
      if (currentSession.current !== options.sessionKey) return;
      options.onUploaded({ documents: [{ ...document, status: "queued", error: null }], jobs: [job] });
    } catch (error) { if (currentSession.current === options.sessionKey) setNotice(error instanceof Error ? error.message : "Could not retry indexing. Check the document status before trying again."); }
    finally { retryLocks.current.delete(document.id); setRetrying(ids => ids.filter(id => id !== document.id)); options.refresh(); }
  };
  const trackedIds = new Set(selected.flatMap(e => e.document ? [e.document.id] : []));
  // Pending/failed persisted documents remain visible after refresh or navigation.
  const recovered: Entry[] = options.documents.filter(d => (d.dataset_id || d.kb_id) === datasetId && !trackedIds.has(d.id) && (["queued", "processing", "failed", "cancelled"].includes(d.status) || d.requires_reindex)).map(d => ({ id: d.id, datasetId, name: d.name, size: d.size, status: "submitted", document: d }));
  const rows = [...selected, ...recovered].map(entry => {
    const document = entry.document && options.documents.find(d => d.id === entry.document!.id);
    const job = document && options.jobs.filter(j => (j.document_id || j.target_id) === document.id && j.kind === "index").sort((a, b) => b.created_at - a.created_at)[0];
    const ready = document?.status === "ready" && !document.requires_reindex;
    // Document and job polling can cross. Current document state wins over an older job.
    const failed = !!document && ["failed", "cancelled"].includes(document.status);
    const processing = !!document && ["queued", "processing"].includes(document.status) && !failed;
    const label = !document ? ({ selected: "Ready to upload", invalid: "Needs attention", uploading: "Uploading original…", failed: "Upload failed", uncertain: "Upload not confirmed", submitted: "Document unavailable · check dataset" }[entry.status]) : ready ? "Ready for questions" : processing ? (document.status === "queued" ? "Stored · queued for indexing" : "Indexing…") : failed ? "Indexing needs attention" : document.requires_reindex ? "Reindex required" : "Document unavailable";
    return { ...entry, document, job, ready, failed, processing, label };
  });
  const processing = rows.filter(r => r.status === "uploading" || r.processing).length;
  const summary = uploading ? `Uploading to ${uploadDestination}…` : processing ? `${processing} indexing` : pending.length ? `${pending.length} selected` : rows.some(r => r.status === "invalid" || r.status === "failed" || r.status === "uncertain" || r.failed || r.document?.requires_reindex) ? "Needs attention" : rows.some(r => r.ready) ? "Documents ready" : "";
  return { ...options, datasetId, blocked, rows, notice, uploading, uploadDestination, retrying, pending, summary, choose, start, retryIndex, remove: (id: string) => { if (!inFlight.current) setEntries(previous => previous.filter(e => e.id !== id)); } };
}
export type DocumentUploadController = ReturnType<typeof useDocumentUpload>;

export function DocumentUploadPanel({ upload: u }: { upload: DocumentUploadController }) {
  return <section className="document-upload-panel" aria-label="Document uploads">
    <p className="upload-destination">Destination: <strong>{u.dataset?.name || "No dataset selected"}</strong></p>
    <p className="muted small">PDF, DOCX or UTF-8 TXT · up to {u.maxMb} MB per file · 20 files at a time. Originals are stored, then indexed using this dataset’s configuration.</p>
    {u.uploading && u.uploadDestination !== u.dataset?.name && <p className="upload-notice" role="status">Finishing the current upload to {u.uploadDestination}. Remaining files will stay with that dataset.</p>}
    {u.blocked && <p className="upload-notice" role="status"><AlertCircle size={16} />{u.blocked}</p>}
    <div className="dropzone shared-dropzone" onDragOver={e => { if (e.dataTransfer.types.includes("Files")) e.preventDefault(); }} onDrop={e => { if (!e.dataTransfer.types.includes("Files")) return; e.preventDefault(); e.stopPropagation(); u.choose(Array.from(e.dataTransfer.files)); }}>
      <UploadCloud size={28} /><strong>Drop documents here, or choose files</strong>
      <input aria-label="Choose documents" disabled={!!u.blocked || u.uploading} type="file" accept=".pdf,.docx,.txt" multiple onChange={e => { u.choose(Array.from(e.target.files || [])); e.target.value = ""; }} />
    </div>
    {u.rows.length > 0 && <ul className="upload-files" aria-label="Selected and processing documents">{u.rows.map(row => <li key={row.id}>
      <div className="upload-file-icon">{row.ready ? <CheckCircle2 size={19} /> : row.status === "uploading" || row.processing ? <Loader2 className="animate-spin" size={19} /> : <FileText size={19} />}</div>
      <div className="upload-file-detail"><strong>{row.name}</strong><span className={`upload-file-status ${row.ready ? "is-ready" : ""}`} role="status">{row.label}</span>
        {(row.error || (row.failed && (row.document?.error || row.job?.error))) && <p className="upload-file-error">{row.error || row.document?.error || row.job?.error}</p>}
        {row.status === "uncertain" && <p className="upload-file-error">The original may already be stored. Check this dataset’s documents before selecting this file again to avoid a duplicate.</p>}
        {row.processing && <progress aria-label={`Indexing ${row.name}`} />}
        {row.document && !row.processing && (row.failed || row.document.requires_reindex) && <button type="button" className="text-button" disabled={!!u.blocked || u.retrying.includes(row.document.id) || (u.externalRequired && !u.consent)} onClick={() => u.retryIndex(row.document!)}><RefreshCw size={13} />{u.retrying.includes(row.document.id) ? "Retrying…" : "Retry indexing"}</button>}
      </div>
      {!row.document && row.status !== "uploading" && <button type="button" className="btn icon" aria-label={`Remove ${row.name}`} disabled={u.uploading} onClick={() => u.remove(row.id)}><X size={16} /></button>}
    </li>)}</ul>}
    {u.externalRequired && <label className="check upload-consent"><input type="checkbox" checked={u.consent} disabled={u.uploading} onChange={e => u.setConsent(e.target.checked)} /><span>I approve sending original files to the configured external storage, and document text to external search or embedding providers. API usage may be billed separately.</span></label>}
    {u.notice && <p className="upload-notice" role="alert"><AlertCircle size={16} />{u.notice}</p>}
    {u.pollError && <p className="upload-notice" role="status">Could not refresh processing status. <button type="button" className="text-button" onClick={u.refresh}>Check again</button></p>}
    <div className="upload-actions"><button type="button" className="text-button" onClick={u.onManage}>View dataset documents</button><button type="button" className="btn primary" disabled={u.uploading || !!u.blocked || !u.pending.length || (u.externalRequired && !u.consent)} onClick={u.start}>{u.uploading ? <Loader2 className="animate-spin" size={16} /> : <UploadCloud size={16} />}{u.uploading ? "Uploading originals…" : `${u.pending.some(e => e.status === "failed") ? "Retry upload" : "Upload"} ${u.pending.length || ""}`}</button></div>
    <p className="upload-footnote">Only ready, current-index documents are available to chat. If you use a document selection, add new files in Document scope when ready. Uploading never sends a question.</p>
  </section>;
}
