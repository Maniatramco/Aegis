"use client";
import { useEffect, useRef, useState } from 'react';
import { AlertCircle, CheckCircle2, FileText, Loader2, Paperclip, Send, Shield, Square, X } from 'lucide-react';
import './temporary-document-chat.css';

type Entity = Record<string, any>;
type Api = (path: string, method?: string, body?: unknown, signal?: AbortSignal) => Promise<any>;

export function TemporaryDocumentChat({ models, initialModelId, settings, api, onExit }: {
  models: Entity[]; initialModelId: string; settings: Entity; api: Api; onExit: () => void;
}) {
  const eligible = models.filter(model => model.enabled !== false && model.capabilities?.includes('chat') && (model.provider !== 'mock' || settings.mock_allowed));
  const [modelId, setModelId] = useState(() => eligible.some(model => model.id === initialModelId) ? initialModelId : (eligible.find(model => model.provider === 'ollama') || eligible[0])?.id || '');
  const model = eligible.find(item => item.id === modelId);
  const remote = !!model && !['ollama', 'mock'].includes(model.provider);
  const [document, setDocument] = useState<Entity | null>(null);
  const [messages, setMessages] = useState<Entity[]>([]);
  const [prompt, setPrompt] = useState('');
  const [error, setError] = useState('');
  const [uploading, setUploading] = useState(false);
  const [answering, setAnswering] = useState(false);
  const [consent, setConsent] = useState(false);
  const [elapsed, setElapsed] = useState(0);
  const session = useRef(crypto.randomUUID());
  const documentId = useRef('');
  const input = useRef<HTMLInputElement>(null);
  const thread = useRef<HTMLDivElement>(null);
  const controller = useRef<AbortController | null>(null);
  const lock = useRef(false);
  const mounted = useRef(true);
  useEffect(() => { mounted.current = true; return () => { mounted.current = false; controller.current?.abort(); if (documentId.current) void api(`/temporary-chat/documents/${documentId.current}`, 'DELETE').catch(() => {}); }; }, [api]);
  useEffect(() => { if (!uploading && !answering) return; const started = Date.now(); setElapsed(0); const timer = setInterval(() => setElapsed(Math.floor((Date.now() - started) / 1000)), 1000); return () => clearInterval(timer); }, [uploading, answering]);
  useEffect(() => { if (thread.current) thread.current.scrollTop = thread.current.scrollHeight; }, [messages, answering]);
  const upload = async (files: File[]) => {
    if (lock.current) return;
    if (files.length !== 1) { setError('Temporary chat accepts one document only. Choose one PDF, DOCX, or UTF-8 TXT file.'); return; }
    const file = files[0];
    if (!/\.(pdf|docx|txt)$/i.test(file.name)) { setError('Choose a PDF, DOCX, or UTF-8 TXT document.'); return; }
    if (!file.size || file.size > Math.min(Number(settings.max_upload_mb || 25), 25) * 1048576) { setError('The file is empty or exceeds the upload size limit.'); return; }
    lock.current = true; setUploading(true); setError(''); controller.current = new AbortController();
    const form = new FormData(); form.append('files', file); form.append('session_id', session.current);
    try {
      const result = await api('/temporary-chat/documents', 'POST', form, controller.current.signal);
      if (!mounted.current) { void api(`/temporary-chat/documents/${result.id}`, 'DELETE').catch(() => {}); return; }
      documentId.current = result.id; setDocument(result); setMessages([]); setPrompt('');
    } catch (reason) { if (mounted.current) setError(reason instanceof Error ? reason.message : 'The document could not be read.'); }
    finally { lock.current = false; if (mounted.current) setUploading(false); }
  };
  const clearDocument = async () => {
    if (lock.current || !document) return;
    lock.current = true; setError('');
    try { await api(`/temporary-chat/documents/${document.id}`, 'DELETE'); documentId.current = ''; setDocument(null); setMessages([]); setPrompt(''); }
    catch (reason) {
      if ((reason as Entity)?.status === 404) { documentId.current = ''; setDocument(null); setMessages([]); }
      else setError(reason instanceof Error ? reason.message : 'Could not clear the temporary document.');
    } finally { lock.current = false; }
  };
  const send = async (question = prompt) => {
    if (!question.trim() || lock.current || !document || !model || (remote && !consent)) return;
    lock.current = true; setAnswering(true); setError(''); setPrompt(''); controller.current = new AbortController();
    const history = messages.filter(message => ['user', 'assistant'].includes(message.role) && message.status !== 'failed').slice(-8).map(message => ({ role: message.role, text: message.text }));
    const base = [...messages, { id: crypto.randomUUID(), role: 'user', text: question }]; setMessages(base);
    try {
      const result = await api('/temporary-chat/messages', 'POST', { text: question, document_id: document.id, model_id: model.id, history, allow_external: remote && consent }, controller.current.signal);
      if (mounted.current) setMessages([...base, result.message]);
    } catch (reason) {
      if (mounted.current) { setError(reason instanceof Error && reason.name === 'AbortError' ? 'Generation stopped. The model may take a moment to finish its current request.' : reason instanceof Error ? reason.message : 'The model could not answer.'); setMessages([...base, { id: crypto.randomUUID(), role: 'assistant', text: '', status: 'failed' }]); setPrompt(question); }
    } finally { lock.current = false; if (mounted.current) setAnswering(false); }
  };
  return <section className="temporary-direct-chat" aria-label="Single-document temporary chat" onDragOver={event => { if (event.dataTransfer.types.includes('Files')) event.preventDefault(); }} onDrop={event => { if (!event.dataTransfer.types.includes('Files')) return; event.preventDefault(); void upload(Array.from(event.dataTransfer.files)); }}>
    <header className="temporary-chat-heading"><div><h2>Temporary chat</h2><p>Ask directly about one document.</p></div><button className="chat-mode-toggle" type="button" aria-pressed="true" disabled={uploading || answering} onClick={onExit}><span className="temporary-switch on" aria-hidden="true" />Temporary chat</button></header>
    <div className="temporary-chat-notice"><Shield size={18} /><p>No embeddings, index, or saved conversation. Messages clear when you leave or reload. Parsed text stays in server memory for up to one hour; clearing the document or leaving this view requests its removal. A server restart clears it too.</p></div>
    <label className="temporary-model-label">Chat model<select aria-label="Temporary chat model" value={modelId} disabled={uploading || answering} onChange={event => { setModelId(event.target.value); setConsent(false); setError(''); }}><option value="">Choose a registered Chat model</option>{eligible.map(item => <option key={item.id} value={item.id} disabled={settings.local_only && !['ollama', 'mock'].includes(item.provider)}>{item.name} · {item.provider_model}{settings.local_only && !['ollama', 'mock'].includes(item.provider) ? ' (cloud disabled)' : ''}</option>)}</select></label>
    <input type="file" ref={input} hidden accept=".pdf,.docx,.txt" aria-label="Temporary document file" onChange={event => { const files = Array.from(event.target.files || []); if (files.length) void upload(files); event.target.value = ''; }} />
    <div className={`temporary-document-card ${document ? 'attached' : ''}`}>
      {uploading ? <><Loader2 size={22} className="animate-spin" /><div role="status"><strong>Reading document{elapsed ? ` · ${elapsed}s` : ''}…</strong><small>Reading text directly. No indexing or embeddings.</small></div></> : document ? <><FileText size={24} /><div><strong>{document.name}</strong><small><CheckCircle2 size={13} />Ready for direct questions · one document</small></div><button className="btn" disabled={answering} onClick={() => input.current?.click()}>Replace document</button><button className="btn icon" disabled={answering} aria-label="Clear temporary document" onClick={() => void clearDocument()}><X size={17} /></button></> : <><Paperclip size={24} /><div><strong>Upload one document</strong><small>PDF, DOCX, or UTF-8 TXT · up to 40 KB of readable text</small></div><button className="btn primary" onClick={() => input.current?.click()}>Choose document</button></>}
    </div>
    {error && <div className="temporary-chat-error" role="alert"><AlertCircle size={18} /><span>{error}</span><button className="btn icon" aria-label="Dismiss temporary chat error" onClick={() => setError('')}><X size={15} /></button></div>}
    <div className="temporary-chat-messages" ref={thread} aria-label="Temporary conversation messages" tabIndex={0}>
      {!messages.length && <div className="temporary-chat-welcome"><FileText size={32} /><h3>{document ? 'Your document is ready' : 'One document. Direct answers.'}</h3><p>{document ? 'Ask a question or request a summary. Only this document supplies the evidence.' : 'Upload a document to begin. You do not need a dataset or an embedding model.'}</p></div>}
      {messages.map(message => <article key={message.id} className={`temporary-message ${message.role}`} aria-label={message.role === 'user' ? 'Your temporary message' : 'Temporary answer'}><strong>{message.role === 'user' ? 'You' : 'Aegis'}</strong><p>{message.status === 'failed' ? 'No answer was saved. You can retry your question.' : message.text}</p>{message.citations?.map((citation: Entity) => <details className="temporary-evidence" key={citation.index}><summary>Source {citation.index} · {citation.document_name}{citation.page ? ` · page ${citation.page}` : ''}</summary><p>{citation.excerpt}</p></details>)}</article>)}
      {answering && <p className="temporary-answer-status" role="status"><Loader2 size={16} className="animate-spin" />Answering directly from your document{elapsed ? ` · ${elapsed}s` : ''}…</p>}
    </div>
    <div className="temporary-compose-area">{remote && <label className="check"><input type="checkbox" checked={consent} disabled={answering} onChange={event => setConsent(event.target.checked)} />Allow this document and question to be sent to {model?.name}. The provider’s own retention policy applies.</label>}<form className="temporary-composer" onSubmit={event => { event.preventDefault(); void send(); }}><textarea aria-label="Ask a temporary question" placeholder={document ? 'Ask about this document…' : 'Upload one document first…'} value={prompt} disabled={uploading} rows={2} onChange={event => setPrompt(event.target.value)} onKeyDown={event => { if (event.key === 'Enter' && !event.shiftKey && !event.nativeEvent.isComposing) { event.preventDefault(); void send(); } }} />{answering ? <button className="btn primary" type="button" aria-label="Stop temporary answer" onClick={() => controller.current?.abort()}><Square size={18} /></button> : <button className="btn primary" type="submit" aria-label="Send temporary question" disabled={!document || !model || uploading || !prompt.trim() || (remote && !consent)}><Send size={20} /></button>}</form><div className="temporary-compose-meta"><span>One document · No index · No embeddings</span>{messages.length > 0 && <button className="text-button" disabled={answering || uploading} onClick={() => { setMessages([]); setPrompt(''); setError(''); }}>Clear conversation</button>}</div></div>
  </section>;
}
