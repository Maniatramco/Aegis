"use client";
import { useEffect, useRef, useState, type ReactNode } from "react";
import { AlertCircle, ArrowDown, ChevronDown, ChevronsLeft, Copy, FileText, History, Loader2, Plus, Paperclip, UploadCloud, RefreshCw, Send, Shield, Square, ThumbsDown, ThumbsUp, X } from "lucide-react";
import { DocumentUploadPanel, type DocumentUploadController } from "./document-upload";
import { recordedModel } from "./dataset-workspace";
import "./focused-chat.css";
import { PromptUploadPreview } from "./prompt-upload-preview";
import { type PromptUpload } from "./prompt-upload";

type Entity = Record<string, any>;
type Props = {
  error: string; onDismissError: () => void; datasetName: string; localProcessing: boolean; reranker: Entity;
  onTemporary: () => void;
  upload: DocumentUploadController;
  onUploadWorkflowVisible?: (visible:boolean)=>void;
  templateAttachment: string; templateFeedback: string; onTemplateAttach:(files:File[])=>void; promptPreview:PromptUpload|null; promptLoading:boolean; onConfirmPrompt:()=>void; onCancelPrompt:()=>void; onTemplateRemove:()=>void;
  conversation: Entity | null; conversations: Entity[]; prompt: string; setPrompt: (value: string) => void;
  answering: boolean; lastPrompt: string; canSend: boolean; externalChat: boolean; setExternalChat: (value: boolean) => void;
  providerNotice: string; modelName: string; scopeCount: number; readyCount: number;
  datasetControl: ReactNode; modelControl: ReactNode; documentControl: ReactNode; exportControl: ReactNode;
  onNew: () => void; onOpen: (id: string) => void; onSend: (text?: string) => void; onStop: () => void;
  onReload: () => void; onRefresh: () => void; loading: boolean; onCopy: (text: string) => void; onFeedback: (id: string, rating: string) => void;
};
export function FocusedChat(p: Props) {
  const [uploadOpen, setUploadOpen] = useState(false);
  const [uploadView, setUploadView] = useState<"attach" | "workflow">("attach");
  useEffect(()=>{p.onUploadWorkflowVisible?.(uploadOpen&&uploadView==='workflow');return()=>p.onUploadWorkflowVisible?.(false);},[uploadOpen,uploadView,p.onUploadWorkflowVisible]);
  const [dragging, setDragging] = useState(false);
  const dragDepth = useRef(0);
  const uploadDialog = useRef<HTMLDialogElement>(null);
  const attachTrigger = useRef<HTMLButtonElement>(null);
  const [historyOpen, setHistoryOpen] = useState(false);
  const [compact, setCompact] = useState(false);
  const [source, setSource] = useState<Entity | null>(null);
  const [sourcesOpen, setSourcesOpen] = useState(false);
  const [away, setAway] = useState(false);
  const [elapsed, setElapsed] = useState(0);
  useEffect(() => { if (!p.answering) return; setElapsed(0); const started = Date.now(); const timer = setInterval(() => setElapsed(Math.floor((Date.now()-started)/1000)),1000); return () => clearInterval(timer); }, [p.answering]);
  const thread = useRef<HTMLDivElement>(null);
  const textarea = useRef<HTMLTextAreaElement>(null);
  const templateInput=useRef<HTMLInputElement>(null);
  const dialog = useRef<HTMLDialogElement>(null);
  const historyDialog = useRef<HTMLDialogElement>(null);
  const historyTrigger = useRef<HTMLButtonElement>(null);
  const atEnd = useRef(true);
  const messages: Entity[] = p.conversation?.messages || [];
  const citations: Entity[] = messages.flatMap(m => m.citations || []);
  const sources = citations.filter((c, i) => citations.findIndex(v => (v.chunk_id || JSON.stringify(v)) === (c.chunk_id || JSON.stringify(c))) === i);
  useEffect(() => {
    const media = matchMedia("(max-width: 1100px)");
    const sync = () => { setCompact(media.matches); setHistoryOpen(false); };
    sync(); media.addEventListener("change", sync); return () => media.removeEventListener("change", sync);
  }, []);
  useEffect(() => {
    const el = textarea.current;
    if (el) { el.style.height = "auto"; el.style.height = `${Math.min(el.scrollHeight, 160)}px`; }
  }, [p.prompt]);
  useEffect(() => {
    const el = textarea.current;
    if (!el) return;
    let width = 0;
    const observer = new ResizeObserver(([entry]) => {
      if (entry.contentRect.width === width) return;
      width = entry.contentRect.width;
      el.style.height = "auto";
      el.style.height = `${Math.min(el.scrollHeight, 160)}px`;
    });
    observer.observe(el);
    return () => observer.disconnect();
  }, []);
  useEffect(() => { atEnd.current = true; setAway(false); setSourcesOpen(false); }, [p.conversation?.id]);
  useEffect(() => { if (p.answering) { atEnd.current = true; setAway(false); } }, [p.answering]);
  useEffect(() => {
    const el = thread.current;
    if (el && atEnd.current) el.scrollTop = el.scrollHeight;
  }, [messages, p.answering]);
  useEffect(() => {
    if (sourcesOpen) dialog.current?.showModal(); else dialog.current?.close();
  }, [sourcesOpen]);
  useEffect(() => {
    const el = historyDialog.current;
    if (!el) return;
    if (historyOpen && !el.open) el.showModal();
    else if (!historyOpen && el.open) el.close();
  }, [compact, historyOpen]);
  useEffect(() => {
    if (uploadOpen) uploadDialog.current?.showModal(); else uploadDialog.current?.close();
    setDragging(false); dragDepth.current = 0;
  }, [uploadOpen]);
  useEffect(() => {
    const reset = () => { setDragging(false); dragDepth.current = 0; };
    const key = (event: KeyboardEvent) => { if (event.key === "Escape") reset(); };
    window.addEventListener("dragend", reset); window.addEventListener("drop", reset); window.addEventListener("blur", reset); window.addEventListener("keydown", key);
    return () => { window.removeEventListener("dragend", reset); window.removeEventListener("drop", reset); window.removeEventListener("blur", reset); window.removeEventListener("keydown", key); };
  }, []);
  const closeUpload = () => { setUploadOpen(false); setDragging(false); dragDepth.current = 0; };
  const openAttachments = () => { setUploadView("attach"); setUploadOpen(true); };
  const openWorkflow = () => { setUploadView("workflow"); setUploadOpen(true); };
  const closeHistory = () => {
    historyDialog.current?.close();
    setHistoryOpen(false);
    if (!compact) requestAnimationFrame(() => historyTrigger.current?.focus());
  };
  const showSource = (c: Entity | null) => { setSource(c); setSourcesOpen(true); };
  const completedAnswer = [...messages].reverse().find(m => m.role === "assistant" && !!(m.text || m.content) && !["failed", "aborted", "streaming"].includes(m.status) && m.id !== "streaming-answer");
  const historyContent = <div className="history-content">
      <div className="history-heading"><h2>Conversations</h2><button className="btn icon" aria-label={compact ? "Close conversations" : "Hide conversations"} onClick={closeHistory}>{compact ? <X size={19} /> : <ChevronsLeft size={19} />}</button></div>
      <button className="new-chat" aria-label="New conversation" disabled={p.answering} onClick={() => { p.onNew(); if (compact) closeHistory(); textarea.current?.focus(); }}><Plus size={22} />New chat</button>
      <div className="chat-list">
        {p.conversations.length ? p.conversations.map(c => <button key={c.id} className={p.conversation?.id === c.id ? "selected" : ""} aria-current={p.conversation?.id === c.id ? "true" : undefined} disabled={p.answering} onClick={() => { p.onOpen(c.id); if (compact) closeHistory(); }}><strong>{c.title || "Untitled conversation"}</strong><span>{c.updated_at || c.created_at ? new Date(typeof (c.updated_at || c.created_at) === "number" ? (c.updated_at || c.created_at) * 1000 : c.updated_at || c.created_at).toLocaleDateString(undefined, { month: "short", day: "numeric" }) : "Saved conversation"}</span></button>) : <p className="history-empty">Your conversations will appear here after your first question.</p>}
      </div>
    </div>;
  return <div className={`focused-chat ${historyOpen ? "history-open" : ""}`}>
    {compact ? <dialog className="chat-history history-dialog" ref={historyDialog} aria-label="Saved conversations" aria-modal="true"
      onCancel={() => setHistoryOpen(false)} onClose={() => setHistoryOpen(false)}
      onClick={e => { if (e.target === e.currentTarget) closeHistory(); }}>{historyContent}</dialog>
      : <aside className="chat-history" hidden={!historyOpen} aria-label="Saved conversations">{historyContent}</aside>}
    <section className="chat-main"
      onDragEnter={e => { if (e.dataTransfer.types.includes("Files")) { e.preventDefault(); dragDepth.current += 1; setDragging(true); } }}
      onDragOver={e => { if (e.dataTransfer.types.includes("Files")) { e.preventDefault(); e.dataTransfer.dropEffect = p.upload.blocked || p.upload.uploading ? "none" : "copy"; } }}
      onDragLeave={e => { if (e.dataTransfer.types.includes("Files")) { dragDepth.current = Math.max(0, dragDepth.current - 1); if (!dragDepth.current) setDragging(false); } }}
      onDrop={e => { if (!e.dataTransfer.types.includes("Files")) return; e.preventDefault(); dragDepth.current = 0; setDragging(false); const files=Array.from(e.dataTransfer.files),templates=files.filter(file=>/\.json$/i.test(file.name)),documents=files.filter(file=>!/\.json$/i.test(file.name));if(templates.length)p.onTemplateAttach(templates);if(documents.length){p.upload.choose(documents);openAttachments();} }}>
      {dragging && <div className="chat-drop-overlay" role="status"><UploadCloud size={38} /><strong>Drop documents to attach</strong><span>{p.upload.blocked || `Upload to ${p.upload.dataset?.name}`}</span><span>Review files before uploading</span></div>}
      <header className="chat-heading">
        <div className="chat-heading-row">
          <div className="chat-title"><button ref={historyTrigger} className="btn icon history-trigger" aria-label="Conversations" aria-expanded={historyOpen} onClick={() => setHistoryOpen(!historyOpen)}><History size={20} /></button><div><h2>Chat</h2><p>Answers grounded in your documents</p></div></div>
          <div className="chat-header-actions"><button className="btn icon chat-refresh" aria-label="Refresh workspace" title="Refresh workspace" disabled={p.loading || p.answering} onClick={p.onRefresh}><RefreshCw size={16}/></button><button className="btn sources-toggle" onClick={() => showSource(null)}><FileText size={16} />Sources <span>{sources.length}</span></button><button className="btn compact-new" aria-label="New conversation" disabled={p.answering} onClick={p.onNew}><Plus size={17} /><span>New chat</span></button></div>
        </div>
        <div className="chat-context-row">
          <div className="chat-dataset-control"><span className="sr-only">Dataset</span>{p.datasetControl}</div>
          <div className="chat-model-control">{p.modelControl}</div>
          <details className="disclosure chat-scope"><summary><FileText size={15} /><span>{p.scopeCount ? `${p.scopeCount} selected` : `${p.readyCount} ready document${p.readyCount===1 ? "" : "s"}`}</span><ChevronDown size={14} /></summary><div className="scope-content"><p className="muted small">No selection searches all ready documents in this dataset.</p>{p.documentControl}</div></details>
          <button type="button" className="chat-mode-toggle" aria-pressed={false} disabled={p.answering || p.upload.uploading} onClick={p.onTemporary}><span className="temporary-switch" aria-hidden="true"/>Temporary chat</button>
          {p.conversation?.id && <div className="thread-actions"><button className="btn icon" title="Reload conversation" aria-label="Reload conversation" disabled={p.answering} onClick={p.onReload}><RefreshCw size={15} /></button>{p.exportControl}</div>}
        </div>
      </header>
      <div className="chat-messages" ref={thread} tabIndex={0} aria-label="Conversation messages" onScroll={() => { const el = thread.current!; atEnd.current = el.scrollHeight - el.scrollTop - el.clientHeight < 80; setAway(!atEnd.current); }}>
        {messages.length ? messages.map((m, i) => {
          const text = m.text || m.content || "";
          const incomplete = m.role !== "user" && (["failed", "aborted"].includes(m.status) || (!text && m.id !== "streaming-answer" && m.status !== "streaming"));
          const question = messages.slice(0,i).reverse().find(item => item.role === "user")?.text || p.lastPrompt;
          return <article key={m.id || i} className={`message ${m.role === "user" ? "user" : "assistant"} ${incomplete ? "incomplete" : ""}`} aria-label={m.role === "user" ? "Your message" : "Aegis answer"}>
          {m.role !== "user" && <img className="answer-logo" src="/aegis-logo.png" alt="" width={38} height={38} />}
          <div className="message-body"><div className="message-label">{m.mock && <span className="pill amber">MOCK TEST OUTPUT</span>}{m.role !== "user" && recordedModel(m) && <span className="message-model">{recordedModel(m)}</span>}<span className="sr-only">{m.role === "user" ? "You" : "Aegis"}</span></div>{text && <div className="message-text">{m.role==="user"?text:text.split(/(\[\d+\])/g).map((part:string,index:number)=>{const cited=m.citations?.find((c:Entity)=>`[${c.index}]`===part);return cited?<button key={index} className="inline-citation" aria-label={`Citation ${cited.index}: ${cited.document_name}`} onClick={()=>showSource(cited)}>{part}</button>:part;})}</div>}
          {incomplete && <div className="answer-failure" role="status"><AlertCircle size={19} aria-hidden="true" /><div><strong>{m.status === "aborted" ? "Generation stopped" : "This answer could not be completed"}</strong><p>{m.error?.detail || (text ? "This response is incomplete. Retry the question for a complete answer." : "This earlier request did not return an answer. You can retry it with the current model.")}</p><button className="btn retry-answer" disabled={p.answering || !p.canSend || !question} onClick={() => p.onSend(question)}><RefreshCw size={14} />Retry question</button></div></div>}
          {!!m.citations?.length && <div className="answer-citations">{m.citations.map((c: Entity, n: number) => <button className="citation" key={n} onClick={() => showSource(c)}><FileText size={15} /><span>{c.index || n + 1} · {c.document_name || c.name || c.document_id || "Source document"}{c.page ? ` · page ${c.page}` : ""}</span></button>)}</div>}
          {m.role !== "user" && !!text && m.id !== "streaming-answer" && <div className="message-actions"><button className="btn icon" title="Copy answer" aria-label="Copy answer" onClick={() => p.onCopy(m.text || m.content || "")}><Copy size={18} /></button><button className="btn icon" title="Helpful answer" aria-label="Helpful answer" disabled={incomplete} onClick={() => p.onFeedback(m.id, "up")}><ThumbsUp size={18} /></button><button className="btn icon" title="Unhelpful answer" aria-label="Unhelpful answer" disabled={incomplete} onClick={() => p.onFeedback(m.id, "down")}><ThumbsDown size={18} /></button></div>}</div>
        </article>; }) : <div className="chat-welcome"><img src="/aegis-logo.png" alt="" width={60} height={60} /><h2>What would you like to know?</h2><p>Choose a dataset above, then ask a question.<br />Every grounded answer connects back to its source.</p><div className="suggested-prompts">{["Summarize the key points", "What needs my attention?", "Find important dates and deadlines"].map(text => <button className="btn" key={text} onClick={() => { p.setPrompt(text); textarea.current?.focus(); }}>{text}</button>)}</div>{!p.readyCount && <p className="small muted">Add and index documents in your dataset to get started.</p>}</div>}
        <div className="answer-status" role="status">{p.answering && <><Loader2 size={16} className="animate-spin" />Working on your answer{elapsed > 0 ? ` · ${elapsed}s` : ""}…</>}</div>
      </div>
      {away && <button className="btn jump-latest" onClick={() => { const el = thread.current!; el.scrollTop = el.scrollHeight; atEnd.current = true; setAway(false); }}><ArrowDown size={15} />Latest message</button>}
      <div className="sr-only" role="status" aria-live="polite" aria-atomic="true">{!p.answering && completedAnswer ? `Aegis answer: ${completedAnswer.text || completedAnswer.content}` : ""}</div>
      <div className="chat-compose-area">
        <div className="composer-heading"><span className="model-status"><span className="status-dot" />{p.localProcessing ? "Local model" : "Selected model"}<strong>{p.modelName}</strong></span>{p.reranker?.enabled && <span className="retrieval-status" title={`${p.reranker.model} · up to ${p.reranker.candidate_limit} candidates, then the configured number of source chunks`}>{p.reranker.ready ? "Local reranking" : "Reranker unavailable"}</span>}</div>
        {p.error && !messages.at(-1)?.error && <div className="chat-error" role="alert"><AlertCircle size={17} aria-hidden="true" /><span>{p.error}</span><button className="btn icon" aria-label="Dismiss error" onClick={p.onDismissError}><X size={15} /></button></div>}
        <div className="template-import-control"><input type="file" ref={templateInput} accept=".json,application/json" hidden aria-label="Upload prompt JSON file" onChange={e=>{const files=Array.from(e.target.files||[]);if(files.length)p.onTemplateAttach(files);e.target.value='';}}/><button type="button" className="text-button" disabled={p.answering||p.promptLoading} onClick={()=>templateInput.current?.click()}>Upload Prompt</button><span className="small muted">JSON only · review and confirm before sending</span></div>
        {p.promptLoading&&<p role="status" className="template-feedback">Validating prompt JSON…</p>}
        {p.templateFeedback&&<p role="status" className="template-feedback">{p.templateFeedback}</p>}
        {p.templateAttachment&&<div className="template-attachment"><FileText size={18}/><span>{p.templateAttachment} · Confirmed prompt for {p.datasetName}</span><button type="button" className="btn icon" aria-label="Remove template attachment" disabled={p.answering} onClick={p.onTemplateRemove}><X size={16}/></button></div>}
        <form className="composer" onSubmit={e => { e.preventDefault(); p.onSend(); }}>
          <button ref={attachTrigger} type="button" className="btn attach-documents" aria-label="Attach documents" title="Attach documents to the selected dataset" aria-haspopup="dialog" onClick={openAttachments}><Paperclip size={22} /></button>
          <textarea ref={textarea} aria-label="Ask a question" placeholder={messages.length ? "Ask a follow-up about your documents…" : "Ask a question about your documents…"} rows={1} value={p.prompt} onChange={e => p.setPrompt(e.target.value)} onKeyDown={e => { if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing && e.keyCode !== 229) { e.preventDefault(); if (!p.answering) p.onSend(); } }} />
          {p.answering ? <button key="stop" type="button" className="btn primary send-message" aria-label="Stop" title="Stop generating" onClick={event => { event.preventDefault(); p.onStop(); }}><Square size={19} /></button> : <button key="send" type="submit" className="btn primary send-message" aria-label="Send" title="Send message" disabled={(!p.prompt.trim()&&!p.templateAttachment) || !p.canSend}><Send size={22} /></button>}
        </form>
        {p.upload.summary && <div className="chat-upload-status"><button type="button" className="text-button" aria-label="View document workflows" onClick={openWorkflow}><FileText size={13} /><span role="status">{p.upload.summary}</span></button></div>}
        <div className="composer-meta">{!p.localProcessing&&<label className="check"><input type="checkbox" aria-label={p.providerNotice} checked={p.externalChat} disabled={p.answering} onChange={e => p.setExternalChat(e.target.checked)} /><span>Allow selected documents to be sent to this model</span></label>}<span className="composer-hint">{p.localProcessing ? "Local · Ollama · compatible dataset embeddings" : "Review sources before use"}</span></div>

      </div>
    </section>
    <PromptUploadPreview prompt={p.promptPreview} datasetName={p.datasetName} onConfirm={p.onConfirmPrompt} onCancel={p.onCancelPrompt}/>
    <dialog className="chat-upload-dialog" ref={uploadDialog} aria-label={uploadView === "attach" ? "Attach documents" : "Document processing"} onKeyDown={event => {
      if (event.key !== "Tab") return;
      const controls = Array.from(event.currentTarget.querySelectorAll<HTMLElement>('button:not(:disabled), input:not(:disabled), select:not(:disabled), textarea:not(:disabled), a[href], [tabindex]:not([tabindex="-1"])')).filter(element => element.getClientRects().length > 0);
      const first = controls[0], last = controls[controls.length - 1];
      if (!first) { event.preventDefault(); return; }
      if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
      else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
    }} onCancel={closeUpload} onClose={closeUpload} onClick={e => { if (e.target === e.currentTarget) { const rect = e.currentTarget.getBoundingClientRect(); if (e.clientX < rect.left || e.clientX > rect.right || e.clientY < rect.top || e.clientY > rect.bottom) closeUpload(); } }}>
      <div className="chat-upload-heading"><h2>{uploadView === "attach" ? "Add documents" : "Document processing"}</h2><button type="button" className="btn icon" aria-label="Close uploads" onClick={closeUpload}><X size={19} /></button></div>
      {uploadView === "attach" && <section className="upload-privacy-notice" aria-label="Upload privacy"><Shield size={19} aria-hidden="true" /><div><h3>Privacy before upload</h3><p>{p.upload.externalRequired ? "Originals are retained in the dataset’s configured storage. Document text may be sent to configured external embedding or search providers. Review and approve external processing below before uploading." : "Originals are stored in your workspace. Document text is read and indexed locally using this dataset’s configured embedding model. Documents remain in the dataset until you delete them."}</p></div></section>}
      <DocumentUploadPanel upload={p.upload} attachmentOnly={uploadView === "attach"} workflowOnly={uploadView === "workflow"} onStart={() => setUploadView("workflow")} onWorkflow={openWorkflow} />
      <p className="upload-footnote">You can close this panel and keep writing. Accepted uploads continue indexing in your dataset.</p>
    </dialog>
    <dialog className="chat-sources" ref={dialog} aria-label="Sources" onCancel={() => setSourcesOpen(false)} onClose={() => setSourcesOpen(false)} onClick={e => { if (e.target === e.currentTarget) setSourcesOpen(false); }}><div className="sources-surface"><div className="sources-heading"><div><h2>Sources</h2><p>Evidence from your stored documents</p></div><button className="btn icon" aria-label="Close sources" onClick={() => setSourcesOpen(false)}><X size={19} /></button></div>{sources.length ? <>{source && <button className="text-button" onClick={() => setSource(null)}>View all {sources.length} sources</button>}{(source ? [source] : sources).map((c, i) => <section className="source-evidence" key={i}><h3><FileText size={18} />{c.document_name || c.name || "Source document"}</h3>{c.page && <span className="small muted">Page {c.page}</span>}<p>{c.excerpt || c.text || c.chunk_text || "No excerpt was returned for this source."}</p>{c.document_id && <a className="text-button" href={`/api/documents/${c.document_id}/source#page=${c.page||1}`} target="_blank" rel="noopener">Open original source{c.page ? ` · page ${c.page}` : ""}</a>}{c.chunk_id && <small className="muted">Chunk: {c.chunk_id}</small>}</section>)}</> : <p className="muted">Cited evidence will appear here when an answer includes sources.</p>}</div></dialog>
  </div>;
}
