"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { ArrowLeft, X } from "lucide-react";

export default function PasswordRecoveryPage() {
  const heading = useRef<HTMLHeadingElement>(null);
  const token = useRef("");
  const csrf = useRef("");
  const router = useRouter();
  const [state, setState] = useState("loading");
  const [password, setPassword] = useState("");
  const [confirmation, setConfirmation] = useState("");
  const [visible, setVisible] = useState(false);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const endpoint = () => `http://${window.location.hostname}:8000/api/auth/recovery`;
  useEffect(() => {
    heading.current?.focus();
    const close = (event: KeyboardEvent) => { if (event.key === "Escape") router.push("/"); };
    window.addEventListener("keydown", close);
    const fragment = new URLSearchParams(window.location.hash.slice(1)).get("recovery");
    if (fragment) {
      token.current = fragment;
      window.history.replaceState(null, "", window.location.pathname);
    }
    let active = true;
    if (!token.current) setState("missing");
    else if (!["127.0.0.1", "localhost"].includes(window.location.hostname) || window.location.port !== "3000") {
      setState("invalid"); setError("Open a private recovery link on the computer running Aegis.");
    } else {
      fetch(`${endpoint()}/prepare`, { method: "POST", credentials: "include", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ token: token.current }) })
        .then(async response => { const body = await response.json(); if (!response.ok) throw new Error(body.detail || "Recovery link could not be verified."); return body; })
        .then(body => { if (active) { csrf.current = body.csrf_token; setState("ready"); } })
        .catch(reason => { if (active) { setState("invalid"); setError(reason instanceof Error && reason.message !== "Failed to fetch" ? reason.message : "Aegis could not be reached. Check that it is running and reopen your private link."); } });
    }
    return () => { active = false; window.removeEventListener("keydown", close); };
  }, [router]);

  async function reset(event: React.FormEvent) {
    event.preventDefault(); setError("");
    if (password.length < 12 || password.length > 200) { setError("Use a password of 12 to 200 characters."); document.getElementById("new-password")?.focus(); return; }
    if (password !== confirmation) { setError("Passwords do not match."); document.getElementById("confirm-password")?.focus(); return; }
    setBusy(true); setVisible(false);
    try {
      const response = await fetch(`${endpoint()}/reset`, { method: "POST", credentials: "include", headers: { "Content-Type": "application/json", "X-CSRF-Token": csrf.current }, body: JSON.stringify({ token: token.current, password, confirmation }) });
      const body = await response.json();
      if (!response.ok) throw new Error(body.detail || "Password could not be changed.");
      token.current = ""; csrf.current = ""; setState("success"); heading.current?.focus();
    } catch (reason) { setError(reason instanceof Error && reason.message !== "Failed to fetch" ? reason.message : "Connection interrupted. Try signing in with your new password before requesting another link."); }
    finally { setPassword(""); setConfirmation(""); setBusy(false); }
  }

  return <main className="recovery-shell"><section className="recovery-card" aria-labelledby="recovery-heading">
    <header className="recovery-header"><span className="brand"><img src="/aegis-logo.png" alt="" width={32} height={32} /> Aegis</span><Link href="/" className="btn icon" aria-label="Close password recovery"><X size={18} /></Link></header>
    <h1 id="recovery-heading" ref={heading} tabIndex={-1}>{state === "success" ? "Password changed" : "Recover your access"}</h1>
    <p className="muted">Your account, documents, and model settings stay in place.</p>
    {state === "loading" && <p role="status">Checking your private recovery link…</p>}
    {state === "missing" && <p>Ask the local installation owner to open a private recovery link on this computer. Then choose your new password here. Each link expires in five minutes and works once.</p>}
    {error && <p className="error" role="alert">{error}</p>}
    {state === "ready" && <form onSubmit={reset} noValidate className="login-form">
      <p>Choose a new password. Your other sign-in sessions will end.</p>
      <label htmlFor="new-password">New password</label>
      <div className="login-password"><input id="new-password" type={visible ? "text" : "password"} autoComplete="new-password" minLength={12} maxLength={200} value={password} onChange={event => setPassword(event.target.value)} aria-describedby="password-hint" disabled={busy} /><button type="button" className="password-toggle" aria-label={visible ? "Hide passwords" : "Show passwords"} aria-pressed={visible} aria-controls="new-password confirm-password" onClick={() => setVisible(!visible)} disabled={busy}>{visible ? "Hide" : "Show"}</button></div>
      <small id="password-hint" className="muted">12 to 200 characters</small>
      <label htmlFor="confirm-password">Confirm new password</label><input id="confirm-password" type={visible ? "text" : "password"} autoComplete="new-password" maxLength={200} value={confirmation} onChange={event => setConfirmation(event.target.value)} disabled={busy} />
      <button type="submit" className="btn primary" disabled={busy}>{busy ? "Changing password…" : "Reset password"}</button>
    </form>}
    {state === "success" && <p role="status">Sign in with your existing username and new password.</p>}
    <Link href="/" className="btn recovery-back"><ArrowLeft size={16} aria-hidden="true" /> Back to sign in</Link>
  </section></main>;
}
